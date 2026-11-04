"""The governed host backup wrapper (scripts/p3/ops/tlos_runtime_backup.sh), end to end, with failure injection.

The real wrapper runs with the real scripts/p3/backup.py. Only the host boundary is stubbed:
- `systemctl` keeps tlos-runtime's state in a file;
- `docker` emulates compose containers that exist only while the runtime runs (`compose down` removes them), with
  bind mounts, published loopback ports and the read-only root helper (tar and the listing script, run locally);
- `findmnt` answers the store UUID;
- the three applications' readiness endpoints are local HTTP servers.
Synthetic data and real SQLite databases stand in for Grafana, MLflow and Prometheus. Nothing on any host is touched.

Proved here:
- the lifecycle: one stop and one proven restore per run, coverage observed before the stop and bound into
  *this* run's set, and only that set verified and mirrored;
- failures: each produces its documented exit code, with the runtime restored or the failure reported, never masked;
- interruptions: SIGTERM to the process group (systemd stop or timeout, KillMode=control-group) restores the
  runtime; after SIGKILL the next run finds the marker, recovers and proves the runtime *before* it backs up, then
  observes fresh coverage; a failed recovery refuses the backup;
- hardened vs archive-only: exit 0 / BACKUP = PASS only with LIVE_DATA_COVERAGE = PASS bound into the set (checked
  on every run of every test); a runtime stopped on purpose stays stopped and its set is archive-only (exit 7);
- concurrency: a second run is refused while one holds the lock, so the runtime is stopped and started once.

Synthetic tests are not host acceptance.
"""

from __future__ import annotations

import json
import os
import re
import signal
import sqlite3
import stat
import subprocess
import sys
import textwrap
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "research"))

from p3 import backup  # noqa: E402

WRAPPER = REPO / "scripts" / "p3" / "ops" / "tlos_runtime_backup.sh"
UUID = "6d45029b-05c4-47ca-92a3-76d33d40f507"
SERVICES = ("grafana", "prometheus", "mlflow")
PORTS = {"grafana": "3000/tcp", "prometheus": "9090/tcp", "mlflow": "5000/tcp"}

SYSTEMCTL = r'''#!/usr/bin/env python3
import json, os, sys, time
state_path = os.environ["TLOS_TEST_STATE"]
def load():
    return json.load(open(state_path))
def save(s):
    tmp = state_path + ".tmp"; json.dump(s, open(tmp, "w")); os.replace(tmp, state_path)
args = [a for a in sys.argv[1:] if a not in ("--user", "--quiet")]
with open(os.environ["TLOS_TEST_LOG"], "a") as log:
    log.write(" ".join(args) + "\n")
verb, unit = args[0], args[1]
assert unit == "tlos-runtime.service", unit
s = load()
if verb == "is-active":
    sys.exit(0 if s["active"] else 3)
if verb == "stop":
    s["active"] = False; save(s); sys.exit(0)
if verb == "start":
    if s.get("fail_start"):
        sys.exit(1)
    s["active"] = True; s["started"] = time.time(); save(s); sys.exit(0)
sys.exit(2)
'''

DOCKER = r'''#!/usr/bin/env python3
import json, os, subprocess, sys, time
from datetime import datetime, timezone
s = json.load(open(os.environ["TLOS_TEST_STATE"]))
args = sys.argv[1:]
def containers():
    if not s["active"]:
        return []  # compose down removed them
    out = []
    for svc in ("grafana", "prometheus", "mlflow"):
        mounts = [{"Type": "bind", "Source": os.path.join(s["data"], svc), "Destination": "/data", "RW": True}]
        mounts += [{k: v for k, v in m.items() if k != "svc"} for m in s.get("extra_mounts", []) if m.get("svc", svc) == svc]
        out.append({"Id": "id-" + svc, "Name": "/tlos_runtime-%s-1" % svc,
                    "Config": {"Labels": {"com.docker.compose.project": "tlos_runtime",
                                          "com.docker.compose.service": svc}},
                    "Mounts": mounts,
                    "State": {"Status": "running", "Restarting": False,
                              "StartedAt": datetime.fromtimestamp(s["started"], timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000000000Z")},
                    "NetworkSettings": {"Ports": {s["port_keys"][svc]: [{"HostIp": "127.0.0.1", "HostPort": str(s["ports"][svc])}]}}})
    return out
if args[0] == "ps":
    filters = [args[i + 1].split("=", 1)[1] for i, a in enumerate(args) if a == "--filter"]
    ids = []
    for c in containers():
        labels = c["Config"]["Labels"]
        if all(labels.get(f.rsplit("=", 1)[0]) == f.rsplit("=", 1)[1] for f in filters):
            ids.append(c["Id"])
    print("\n".join(ids)); sys.exit(0)
if args[0] == "inspect":
    print(json.dumps([c for c in containers() if c["Id"] in args[1:]])); sys.exit(0)
if args[0] == "run":
    spec = dict(kv.split("=", 1) for kv in args[args.index("--mount") + 1].split(",") if "=" in kv)
    src = spec["src"]
    if not os.path.isdir(src):
        sys.stderr.write("bind source path does not exist\n"); sys.exit(125)
    tail = args[args.index(os.environ["TLOS_TEST_IMAGE"]) + 1:]
    if tail[0] == "tar":
        time.sleep(s.get("slow_export_s", 0))
        if os.path.basename(src) in s.get("fail_export", []):
            sys.stderr.write("injected export failure\n"); sys.exit(1)
        os.execvp("tar", ["tar", "-C", src, "-cf", "-", "."])
    os.execvp("sh", ["sh", "-c", tail[2].replace("cd /v ", "cd '%s' " % src, 1)])
sys.exit(2)
'''


class _Probe(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def do_GET(self):
        state = json.loads(Path(self.server.state_path).read_text())
        service = self.server.service
        if service in state.get("probe_fail", []):
            self.send_response(503)
            self.end_headers()
            return
        body = json.dumps({"database": "ok"}) if service == "grafana" else "OK"
        self.send_response(200)
        self.end_headers()
        self.wfile.write(body.encode())


def sqlite_db(path: Path, table: str) -> None:
    con = sqlite3.connect(path)
    con.execute(f"create table {table} (id integer primary key, v text)")
    con.executemany(f"insert into {table}(v) values (?)", [(f"row{i}",) for i in range(50)])
    con.commit()
    con.close()


@pytest.fixture
def host(tmp_path):
    h = tmp_path / "home"
    trading = h / "projects" / "trading"
    app = trading / "trading_lab_os_final"
    app.mkdir(parents=True)
    subprocess.run(["git", "-C", str(app), "init", "-q", "-b", "main"], check=True)
    (app / "docker-compose.yml").write_text("services: {}\n")
    subprocess.run(["git", "-C", str(app), "add", "."], check=True)
    subprocess.run(["git", "-C", str(app), "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "c"],
                   check=True)
    (trading / "tlos-runtime").mkdir()
    (trading / "tlos-runtime" / "runtime.override.yaml").write_text("services: {}\n")
    for d in ("tlos-paper/p3-evidence", "tlos-ar-render", "Documents/TLOS-Evidence",
              ".claude/projects/-home-hamza-projects-trading/memory"):
        (h / d).mkdir(parents=True)
        (h / d / "note.txt").write_text(d + "\n")
    mount = tmp_path / "srv"
    (mount / "tlos-backups").mkdir(parents=True)
    data = mount / "trading-data" / "runtime" / "data"
    (data / "grafana").mkdir(parents=True)
    sqlite_db(data / "grafana" / "grafana.db", "dashboard")
    (data / "grafana" / "csv").mkdir()
    (data / "prometheus" / "wal").mkdir(parents=True)
    (data / "prometheus" / "wal" / "00000001").write_bytes(os.urandom(4096))
    (data / "prometheus" / "chunks_head").mkdir()
    (data / "mlflow" / "artifacts" / "1" / "run1").mkdir(parents=True)
    sqlite_db(data / "mlflow" / "mlflow.db", "runs")
    (data / "mlflow" / "artifacts" / "1" / "run1" / "model.pkl").write_bytes(b"artifact")
    # legacy SSD mirror generations (volumes-only partial copies) that must survive untouched
    mirror = h / "tlos-backups-ssd-mirror"
    for gen in ("latest", "previous"):
        (mirror / gen / "volumes").mkdir(parents=True)
        (mirror / gen / "volumes" / "tlos_runtime_grafana_data.tar").write_bytes(gen.encode())
        (mirror / gen / "SOURCE_SET").write_text("20261103T183447Z\n")
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("systemctl", SYSTEMCTL), ("docker", DOCKER),
                       ("findmnt", '#!/bin/sh\necho "$TLOS_TEST_UUID"\n')):
        (bin_dir / name).write_text(body)
        (bin_dir / name).chmod(0o755)
    state_path = tmp_path / "state.json"
    servers, ports = [], {}
    for svc in SERVICES:
        srv = ThreadingHTTPServer(("127.0.0.1", 0), _Probe)
        srv.state_path, srv.service = str(state_path), svc
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        servers.append(srv)
        ports[svc] = srv.server_address[1]
    state = {"active": True, "started": time.time() - 3600, "data": str(data), "ports": ports, "port_keys": PORTS}
    state_path.write_text(json.dumps(state))
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "TLOS_HOME": str(h), "TLOS_MOUNT": str(mount),
           "TLOS_P3": str(REPO), "TLOS_PYTHON": sys.executable, "XDG_RUNTIME_DIR": str(run_dir),
           "TLOS_MIRROR_MARGIN_GIB": "0", "TLOS_RUNTIME_WAIT_S": "6", "TLOS_TEST_UUID": UUID,
           "TLOS_TEST_STATE": str(state_path), "TLOS_TEST_LOG": str(tmp_path / "systemctl.log"),
           "TLOS_TEST_IMAGE": backup.VOLUME_HELPER_IMAGE}
    yield {"home": h, "mount": mount, "data": data, "mirror": mirror, "run": run_dir, "state": state_path,
           "env": env, "log": tmp_path / "systemctl.log", "evid": h / "tlos-paper" / "p3-evidence"}
    for srv in servers:
        srv.shutdown()


def set_state(host, **changes) -> None:
    state = json.loads(host["state"].read_text())
    state.update(changes)
    host["state"].write_text(json.dumps(state))


def state(host) -> dict:
    return json.loads(host["state"].read_text())


def run(host, *, wait=True, **kw):
    proc = subprocess.Popen(["bash", str(WRAPPER)], env=host["env"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, start_new_session=True, **kw)
    if not wait:
        return proc
    out, err = proc.communicate(timeout=180)
    time.sleep(1.1)  # the next run gets a new second-resolution stamp
    assert_no_unhardened_pass(host, proc.returncode, out, err)
    return proc.returncode, out, err


def record(host, stamp) -> dict:
    return json.loads((host["mount"] / "tlos-backups" / stamp / backup.RECORD).read_text())


def assert_no_unhardened_pass(host, code, out, err) -> None:
    """Exit 0 and BACKUP = PASS mean a hardened backup, and only that: the set's own record carries
    LIVE_DATA_COVERAGE = PASS observed before the runtime stop. Exit 0 with coverage UNPROVEN is a defect."""
    if code != 0 and "BACKUP = PASS" not in out:
        return
    assert code == 0 and "BACKUP = PASS" in out, (code, out, err)
    assert "UNPROVEN" not in out + err and "ARCHIVE_ONLY" not in out + err, err
    stamp = re.search(r"BACKUP = PASS \(\S*/(\d{8}T\d{6}Z), ", out).group(1)
    cov = record(host, stamp)["live_data_coverage"]
    assert cov["LIVE_DATA_COVERAGE"] == "PASS" and cov["observed"] == "before_runtime_stop", cov
    assert "LIVE_DATA_COVERAGE = PASS" in out and "ARCHIVE_INTEGRITY = PASS" in out


def calls(host) -> list[str]:
    return host["log"].read_text().split("\n")[:-1] if host["log"].exists() else []


def sets(host) -> list[str]:
    return sorted(p.name for p in (host["mount"] / "tlos-backups").iterdir() if not p.name.startswith("."))


def marker(host) -> Path:
    return host["run"] / "tlos-p3-backup.runtime-stopped"


# ----------------------------------------------------------------------------------------------------------------
# The normal run
# ----------------------------------------------------------------------------------------------------------------

def test_a_normal_run_backs_up_the_live_data_binds_its_coverage_restores_and_mirrors(host, tmp_path):
    code, out, err = run(host)
    assert code == 0, err
    assert calls(host) == ["is-active tlos-runtime.service", "is-active tlos-runtime.service",
                           "stop tlos-runtime.service", "start tlos-runtime.service"]
    assert state(host)["active"] and not marker(host).exists()
    (stamp,) = sets(host)
    set_dir = host["mount"] / "tlos-backups" / stamp
    record = json.loads((set_dir / backup.RECORD).read_text())
    cov = host["evid"] / f"backup_coverage_{stamp}.json"
    assert record["live_data_coverage"]["observed"] == "before_runtime_stop"
    assert record["live_data_coverage"]["report_sha256"] == backup.sha256_file(cov)
    assert sorted(record["data_sources"]) == sorted(SERVICES) and record["volumes"] == []
    assert backup.group_or_other_accessible(set_dir) == []
    # the SSD copy is this run's set, verified; the legacy partial copies are untouched
    assert os.readlink(host["mirror"] / "current") == f"sets/{stamp}"
    assert (host["mirror"] / "latest" / "volumes" / "tlos_runtime_grafana_data.tar").read_bytes() == b"latest"
    assert (host["mirror"] / "previous" / "SOURCE_SET").read_text() == "20261103T183447Z\n"
    assert json.loads((host["evid"] / f"backup_mirror_{stamp}.json").read_text())["SSD_MIRROR"] == "PASS"
    assert "BACKUP = PASS" in out and "application PASS" in out


def test_the_ssd_copy_restores_and_the_restored_databases_and_wal_are_consistent(host, tmp_path):
    code, _, err = run(host)
    assert code == 0, err
    drill = backup.restore_drill(host["mirror"] / "current", tmp_path / "scratch")
    assert drill["PLN_03_RESTORE_DRILL"] == "PASS" and drill["source"]["tier"] == "SECOND_DEVICE_MIRROR"
    restored = tmp_path / "scratch" / "data"
    for db, table in (("grafana/grafana.db", "dashboard"), ("mlflow/mlflow.db", "runs")):
        con = sqlite3.connect(f"file:{restored / db}?mode=ro", uri=True)
        assert con.execute("pragma integrity_check").fetchone()[0] == "ok"
        assert con.execute(f"select count(*) from {table}").fetchone()[0] == 50
        con.close()
    assert (restored / "mlflow" / "artifacts" / "1" / "run1" / "model.pkl").read_bytes() == b"artifact"
    assert (restored / "prometheus" / "wal" / "00000001").read_bytes() == \
        (host["data"] / "prometheus" / "wal" / "00000001").read_bytes()


def test_only_this_runs_set_is_verified_and_mirrored_never_another(host):
    # A set that sorts after any real stamp: the original wrapper's `find | sort | tail -1` would have taken it.
    decoy = host["mount"] / "tlos-backups" / "29991231T000000Z"
    decoy.mkdir()
    (decoy / "BACKUP_RECORD.json").write_text("{}")
    code, _, err = run(host)
    assert code == 0, err
    (stamp,) = [s for s in sets(host) if s != "29991231T000000Z"]
    assert os.readlink(host["mirror"] / "current") == f"sets/{stamp}"
    assert (decoy / "BACKUP_RECORD.json").read_text() == "{}"


def test_an_intentionally_stopped_runtime_stays_stopped_and_its_set_is_archive_only_exit_7(host):
    set_state(host, active=False)
    code, out, err = run(host)
    assert code == 7, err
    assert "stop tlos-runtime.service" not in calls(host) and "start tlos-runtime.service" not in calls(host)
    assert not state(host)["active"] and not marker(host).exists()
    (stamp,) = sets(host)
    assert record(host, stamp)["live_data_coverage"] is None
    # The archive is real and separate from coverage: verified, mirrored, and said so.
    assert backup.verify_backup(host["mount"] / "tlos-backups" / stamp)["status"] == "PASS"
    assert os.readlink(host["mirror"] / "current") == f"sets/{stamp}"
    assert f"ARCHIVE_INTEGRITY = PASS ({host['mount']}/tlos-backups/{stamp} verified" in out
    assert "RUNTIME_LEFT_STOPPED" in err and "LIVE_DATA_COVERAGE = UNPROVEN" in err
    assert f"BACKUP = ARCHIVE_ONLY ({host['mount']}/tlos-backups/{stamp})" in err and "BACKUP = PASS" not in out


# ----------------------------------------------------------------------------------------------------------------
# Refusals before anything is stopped
# ----------------------------------------------------------------------------------------------------------------

def test_the_wrong_store_is_refused_before_anything(host):
    host["env"]["TLOS_TEST_UUID"] = "other"
    code, _, err = run(host)
    assert code == 3 and "not the expected HDD" in err and calls(host) == [] and sets(host) == []


def test_coverage_failure_refuses_before_the_stop(host):
    extra = host["data"] / "loki"
    extra.mkdir()
    set_state(host, extra_mounts=[{"svc": "grafana", "Type": "bind", "Source": str(extra), "Destination": "/loki",
                                   "RW": True}])
    code, _, err = run(host)
    assert code == 4 and "LIVE_DATA_COVERAGE before the stop" in err
    assert "stop tlos-runtime.service" not in calls(host) and state(host)["active"]
    assert sets(host) == [] and not marker(host).exists()


# ----------------------------------------------------------------------------------------------------------------
# Failures after the stop: the runtime comes back, or the failure is reported, never masked
# ----------------------------------------------------------------------------------------------------------------

def test_a_failed_create_restores_the_runtime_and_publishes_nothing(host):
    set_state(host, fail_export=["prometheus"])
    code, _, err = run(host)
    assert code not in (0, 6) and "injected export failure" in err
    assert calls(host)[-2:] == ["stop tlos-runtime.service", "start tlos-runtime.service"]
    assert state(host)["active"] and not marker(host).exists()
    assert sets(host) == [] and not (host["mirror"] / "current").exists()


def test_a_failed_restart_is_exit_6_and_never_masked(host):
    set_state(host, fail_start=True)
    code, out, err = run(host)
    assert code == 6 and "RUNTIME_RESTORE_FAILED" in err and "BACKUP = PASS" not in out
    assert not state(host)["active"] and marker(host).exists(), "the marker records who stopped it"


def test_a_backup_failure_and_a_restart_failure_together_exit_6_and_keep_the_original_status(host):
    set_state(host, fail_export=["prometheus"], fail_start=True)
    code, _, err = run(host)
    assert code == 6, err
    assert "injected export failure" in err
    assert "RUNTIME_RESTORE_FAILED (the run had ended with exit 2 before the restore was attempted)" in err
    assert not state(host)["active"] and marker(host).exists() and sets(host) == []


def test_an_interrupted_run_whose_restart_fails_is_exit_6_not_143(host):
    set_state(host, slow_export_s=4, fail_start=True)
    proc = run(host, wait=False)
    wait_for_stop(host, proc)
    os.killpg(proc.pid, signal.SIGTERM)
    _, err = proc.communicate(timeout=60)
    assert proc.returncode == 6 and "ended with exit 143" in err


def test_a_running_container_whose_application_does_not_answer_is_not_a_recovery(host):
    set_state(host, probe_fail=["grafana"])
    code, out, err = run(host)
    assert code == 6 and "RUNTIME_RESTORE_FAILED" in err
    assert "grafana" in out and "application FAIL" in out and "HTTP" in out


def test_after_a_failed_restart_the_next_run_recovers_first_then_takes_a_hardened_backup(host):
    set_state(host, fail_start=True)
    assert run(host)[0] == 6
    set_state(host, fail_start=False)
    before = len(calls(host))
    code, out, err = run(host)
    assert code == 0, err  # run() also checks the bound coverage
    assert "RECOVERING" in err and "RECOVERED" in err
    assert [c for c in calls(host)[before:] if c.split()[0] in ("start", "stop")] == \
        ["start tlos-runtime.service", "stop tlos-runtime.service", "start tlos-runtime.service"]
    assert state(host)["active"] and not marker(host).exists()


def test_a_mirror_failure_is_exit_5_with_the_set_valid_and_the_runtime_back(host):
    host["mirror"].joinpath("sets").write_text("not a directory")  # the mirror cannot publish
    code, _, err = run(host)
    assert code == 5 and "SSD_MIRROR=FAIL" in err
    (stamp,) = sets(host)
    assert backup.verify_backup(host["mount"] / "tlos-backups" / stamp)["status"] == "PASS"
    assert state(host)["active"] and not marker(host).exists()


# ----------------------------------------------------------------------------------------------------------------
# Interruptions and concurrency
# ----------------------------------------------------------------------------------------------------------------

def wait_for_stop(host, proc, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if "stop tlos-runtime.service" in calls(host):
            return
        if proc.poll() is not None:
            raise AssertionError(proc.communicate())
        time.sleep(0.1)
    raise AssertionError("the wrapper never stopped the runtime")


def test_sigterm_to_the_unit_cgroup_restores_the_runtime(host):
    # systemctl stop / TimeoutStartUSec: systemd sends SIGTERM to every process of the unit (KillMode=control-group)
    set_state(host, slow_export_s=4)
    proc = run(host, wait=False)
    wait_for_stop(host, proc)
    time.sleep(0.5)
    os.killpg(proc.pid, signal.SIGTERM)
    out, err = proc.communicate(timeout=60)
    assert proc.returncode == 143, err
    assert calls(host)[-1] == "start tlos-runtime.service" and state(host)["active"]
    assert not marker(host).exists() and sets(host) == []


def test_after_sigkill_the_next_run_finds_the_marker_and_restores_the_runtime(host):
    set_state(host, slow_export_s=4)
    proc = run(host, wait=False)
    wait_for_stop(host, proc)
    os.killpg(proc.pid, signal.SIGKILL)  # no trap can run: power-cut-like for this process
    proc.communicate(timeout=30)
    assert not state(host)["active"] and marker(host).exists()
    time.sleep(1.1)
    set_state(host, slow_export_s=0)
    code, _, err = run(host)  # the lock died with its holder
    assert code == 0, err  # hardened: run() checks the coverage bound into the new set
    assert "RECOVERING" in err and state(host)["active"] and not marker(host).exists()


def interrupted(host):
    """An earlier run stopped the runtime and was SIGKILLed before restoring it: marker present, runtime down."""
    set_state(host, active=False)
    marker(host).write_text("2026-11-04T03:31:00Z\n")


def test_interrupted_and_recovered_the_runtime_is_proven_back_before_fresh_coverage_and_the_backup(host):
    interrupted(host)
    code, out, err = run(host)
    assert code == 0, err  # BACKUP = PASS with this run's coverage bound (checked by run())
    assert err.index("RECOVERING") < err.index("RECOVERED")
    assert [c for c in calls(host) if c.split()[0] in ("start", "stop")] == \
        ["start tlos-runtime.service", "stop tlos-runtime.service", "start tlos-runtime.service"]
    (stamp,) = sets(host)
    cov = record(host, stamp)["live_data_coverage"]
    # Containers exist only while the runtime runs, so a PASS observation was made after the recovery.
    assert cov["LIVE_DATA_COVERAGE"] == "PASS" and cov["observed"] == "before_runtime_stop"
    assert (host["evid"] / f"backup_coverage_{stamp}.json").is_file()
    assert state(host)["active"] and not marker(host).exists()


def test_interrupted_with_the_runtime_since_started_by_someone_else_is_proven_not_restarted(host):
    interrupted(host)
    set_state(host, active=True)
    code, _, err = run(host)
    assert code == 0, err
    assert "RECOVERED" in err
    assert [c for c in calls(host) if c.split()[0] in ("start", "stop")] == \
        ["stop tlos-runtime.service", "start tlos-runtime.service"]


@pytest.mark.parametrize("failure", ["start_fails", "running_but_not_answering"])
def test_interrupted_and_recovery_failed_refuses_any_backup_and_keeps_the_marker(host, failure):
    interrupted(host)
    if failure == "start_fails":
        set_state(host, fail_start=True)
    else:
        set_state(host, active=True, probe_fail=["prometheus"])
    code, out, err = run(host)
    assert code == 6, err
    assert "RUNTIME_RECOVERY_FAILED" in err and "no backup is attempted" in err
    assert "BACKUP = PASS" not in out and "ARCHIVE_INTEGRITY" not in out
    assert sets(host) == [] and not list(host["evid"].glob("backup_coverage_*.json"))
    assert "stop tlos-runtime.service" not in calls(host)
    assert marker(host).exists(), "the next run must try the recovery again"
    assert not (host["mirror"] / "current").exists()


def test_a_second_run_is_refused_while_one_holds_the_lock(host):
    set_state(host, slow_export_s=3)
    first = run(host, wait=False)
    wait_for_stop(host, first)
    second = run(host)
    assert second[0] == 75 and "another backup run holds" in second[2]
    out, err = first.communicate(timeout=120)
    assert first.returncode == 0, err
    assert_no_unhardened_pass(host, first.returncode, out, err)
    assert calls(host).count("stop tlos-runtime.service") == 1
    assert calls(host).count("start tlos-runtime.service") == 1
    assert len(sets(host)) == 1


def test_the_governed_wrapper_is_the_baseline_plus_this_patch_only():
    text = WRAPPER.read_text(encoding="utf-8")
    assert "sha256 561c44d2" in text
    for gone in ("--volume tlos_runtime_", "|| true; }", "sort | tail -1", 'rm -rf "$MIRROR/previous"'):
        assert gone not in text, gone
    assert subprocess.run(["bash", "-n", str(WRAPPER)]).returncode == 0
