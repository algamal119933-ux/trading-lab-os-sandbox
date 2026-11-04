"""H7 / G8 application checks on a restored copy (scripts/p3/ops/restore_app_checks.sh).

Real SQLite files; `docker` is stubbed: it emulates the throwaway Prometheus container (readiness after N polls,
an early exit, its log, its query API) and the MLflow client run, and records every container it creates and
removes.

Proved here:
- every check has one PASS condition and FAILs otherwise, with no dependence on a sleep;
- WAL recovery needs the replay message, no repair/corruption line, and data queryable at the set stamp;
- the throwaway Prometheus container is removed on every path: pass, each failure, and SIGTERM mid-wait;
- the evidence JSON names the checks, and file hashes are never reported as application consistency.

Synthetic tests are not host acceptance.
"""

from __future__ import annotations

import json
import os
import signal
import sqlite3
import subprocess
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "p3" / "ops" / "restore_app_checks.sh"
STAMP = "20261104T010203Z"
AT = "1793754123"  # STAMP as epoch seconds

DOCKER = r'''#!/usr/bin/env python3
import json, os, sys, time
sp = os.environ["TLOS_TEST_STATE"]
s = json.load(open(sp))
def save():
    json.dump(s, open(sp + ".tmp", "w")); os.replace(sp + ".tmp", sp)
a = sys.argv[1:]
with open(os.environ["TLOS_TEST_LOG"], "a") as log:
    log.write(" ".join(a) + "\n")
v = a[0]
if v == "run" and "-d" in a:
    name = a[a.index("--name") + 1]
    assert "--network" in a and a[a.index("--network") + 1] == "none"
    s["containers"][name] = {"running": True, "polls": 0}; s["created"].append(name); save()
    print("cid"); sys.exit(0)
if v == "run":
    assert "--rm" in a and a[a.index("--network") + 1] == "none"
    if s["mlflow"] is None:
        print("Traceback: schema mismatch", file=sys.stderr); sys.exit(1)
    print(json.dumps({"experiments": s["mlflow"]})); sys.exit(0)
if v == "inspect":
    name = a[-1]
    if name not in s["containers"]:
        sys.exit(1)
    c = s["containers"][name]
    if s["exit_after_polls"] is not None and c["polls"] >= s["exit_after_polls"]:
        c["running"] = False; save()
    print("true" if c["running"] else "false"); sys.exit(0)
if v == "exec":
    name, url = a[1], a[-1]
    c = s["containers"][name]
    if url.endswith("/-/ready"):
        c["polls"] += 1; save()
        sys.exit(0 if s["ready_after"] is not None and c["polls"] >= s["ready_after"] else 1)
    assert "time=" + os.environ["TLOS_TEST_AT"] in url, url
    assert "count_over_time" in __import__("urllib.parse").parse.unquote(url)
    res = [] if not s["series"] else [{"metric": {}, "value": [0, str(s["series"])]}]
    print(json.dumps({"status": "success", "data": {"resultType": "vector", "result": res}})); sys.exit(0)
if v == "logs":
    print(s["logs"]); sys.exit(0)
if v == "rm":
    name = a[-1]
    if name in s["containers"]:
        del s["containers"][name]; s["removed"].append(name); save()
    sys.exit(0)
sys.exit(3)
'''

GOOD_LOGS = ('time=... level=INFO msg="Replaying WAL, this may take a while"\n'
             'time=... level=INFO msg="WAL replay completed" checkpoint_replay_duration=1ms\n'
             'time=... level=INFO msg="Server is ready to receive web requests."')


def sqlite_db(path: Path, corrupt: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(path)
    c.execute("create table t (a)")
    c.executemany("insert into t values (?)", [("x" * 500,)] * 200)
    c.commit()
    c.close()
    if corrupt:
        b = bytearray(path.read_bytes())
        b[4096 * 2: 4096 * 2 + 12] = b"\x0d" + b"\xff" * 11  # a leaf page's header: cell count and offsets
        path.write_bytes(bytes(b))


@pytest.fixture
def env(tmp_path):
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "docker").write_text(DOCKER)
    (bin_ / "docker").chmod(0o755)
    data = tmp_path / "X" / "data"
    sqlite_db(data / "grafana" / "grafana.db")
    sqlite_db(data / "mlflow" / "mlflow.db")
    (data / "prometheus" / "wal").mkdir(parents=True)
    state = tmp_path / "state.json"
    e = {**os.environ, "PATH": f"{bin_}:{os.environ['PATH']}", "TLOS_TEST_STATE": str(state),
         "TLOS_TEST_LOG": str(tmp_path / "docker.log"), "TLOS_TEST_AT": AT,
         "TLOS_PROM_READY_TIMEOUT_S": "3", "TLOS_PROM_POLL_S": "0.1"}
    h = {"env": e, "data": data, "state": state, "out": tmp_path / "ev" / "h7_app.json"}
    h["out"].parent.mkdir()
    set_state(h)
    return h


def set_state(h, **kw):
    s = {"containers": {}, "created": [], "removed": [], "ready_after": 3, "exit_after_polls": None,
         "series": 42, "logs": GOOD_LOGS, "mlflow": 2}
    s.update(kw)
    h["state"].write_text(json.dumps(s))


def run(h, wait=True):
    args = [str(SCRIPT), str(h["data"]), STAMP, str(h["out"])]
    if not wait:
        return subprocess.Popen(args, env=h["env"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                start_new_session=True)
    p = subprocess.run(args, env=h["env"], capture_output=True, text=True, timeout=60)
    return p.returncode, p.stdout, p.stderr


def st(h):
    return json.loads(h["state"].read_text())


def checks(h):
    r = json.loads(h["out"].read_text())
    return r["RESTORE_APP_CHECKS"], {(c["name"], c["check"]): c["result"] for c in r["checks"]}


def assert_cleaned(h):
    s = st(h)
    assert s["containers"] == {} and s["created"] == s["removed"] and len(s["created"]) == 1


def test_the_stamp_constant_is_right():
    assert subprocess.run(["date", "-u", "-d", "2026-11-04T01:02:03Z", "+%s"], capture_output=True,
                          text=True).stdout.strip() == AT


def test_all_checks_pass_and_the_container_is_removed(env):
    code, out, err = run(env)
    assert code == 0, out + err
    status, c = checks(env)
    assert status == "PASS" and set(c.values()) == {"PASS"}
    assert set(c) == {("grafana_db", "SQLITE_INTEGRITY"), ("mlflow", "APPLICATION_READ"),
                      ("prometheus", "APPLICATION_READY"), ("prometheus", "WAL_RECOVERY")}
    assert "RESTORE_APP_CHECKS = PASS" in out and "series_before_stamp=42" in out
    assert_cleaned(env)
    note = json.loads(env["out"].read_text())["note"]
    assert "separate gate" in note


@pytest.mark.parametrize("kw,check,needle", [
    ({"ready_after": None}, ("prometheus", "APPLICATION_READY"), "not ready within 3s"),
    ({"exit_after_polls": 1}, ("prometheus", "APPLICATION_READY"), "container exited"),
    ({"logs": GOOD_LOGS.replace("WAL replay completed", "WAL replay started")}, ("prometheus", "WAL_RECOVERY"),
     "no 'WAL replay completed'"),
    ({"logs": GOOD_LOGS + '\nlevel=WARN msg="Encountered WAL read error, attempting repair"'},
     ("prometheus", "WAL_RECOVERY"), "repair or corruption"),
    ({"logs": GOOD_LOGS + '\nlevel=ERROR msg="Corrupted block"'}, ("prometheus", "WAL_RECOVERY"),
     "repair or corruption"),
    ({"series": 0}, ("prometheus", "WAL_RECOVERY"), "no series with samples"),
    ({"mlflow": 0}, ("mlflow", "APPLICATION_READ"), "experiments=0"),
    ({"mlflow": None}, ("mlflow", "APPLICATION_READ"), "exit=1"),
])
def test_each_failure_fails_the_gate_and_still_removes_the_container(env, kw, check, needle):
    set_state(env, **kw)
    code, out, _ = run(env)
    assert code == 1
    status, c = checks(env)
    assert status == "FAIL" and c[check] == "FAIL" and needle in out
    assert "RESTORE_APP_CHECKS = FAIL" in out
    assert_cleaned(env)


def test_a_server_that_is_never_ready_leaves_wal_recovery_unproven(env):
    set_state(env, ready_after=None)
    run(env)
    _, c = checks(env)
    assert c[("prometheus", "WAL_RECOVERY")] == "FAIL"


def test_a_corrupt_grafana_database_fails(env):
    p = env["data"] / "grafana" / "grafana.db"
    p.unlink()
    sqlite_db(p, corrupt=True)
    code, out, _ = run(env)
    assert code == 1
    _, c = checks(env)
    assert c[("grafana_db", "SQLITE_INTEGRITY")] == "FAIL"
    assert_cleaned(env)


def test_sigterm_while_waiting_for_readiness_still_removes_the_container(env):
    env["env"]["TLOS_PROM_READY_TIMEOUT_S"] = "60"
    set_state(env, ready_after=None)
    proc = run(env, wait=False)
    for _ in range(200):
        if st(env)["created"]:
            break
        time.sleep(0.05)
    time.sleep(0.3)
    os.killpg(proc.pid, signal.SIGTERM)
    proc.communicate(timeout=30)
    assert proc.returncode == 143
    assert_cleaned(env)
    assert not env["out"].exists()


def test_usage_errors_change_nothing(env):
    assert subprocess.run([str(SCRIPT), str(env["data"]), "2026-11-04", str(env["out"])], env=env["env"],
                          capture_output=True).returncode == 2
    env["out"].write_text("{}")
    assert run(env)[0] == 2
    assert st(env)["created"] == []
