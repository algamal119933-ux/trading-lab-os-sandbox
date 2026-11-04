"""H7 / G8 application checks on a restored copy (scripts/p3/ops/restore_app_checks.sh).

Real SQLite files. `docker` is stubbed: it emulates the throwaway Prometheus container (readiness after N polls, an
early exit, its log) and the MLflow client run, and it runs the script's own HTTP helper code for real against a
local server that answers like Prometheus v3.14.0:
- /metrics carries prometheus_tsdb_wal_corruptions_total and _mmap_chunk_corruptions_total;
- /api/v1/query applies the engine rule the original G8 query broke: a range function other than
  last_over_time/first_over_time drops the metric name, so over several metric names the result has duplicate
  label sets and the query fails with HTTP 422 "vector cannot contain metrics with the same labelset"
  (promql/engine.go, v3.14.0).

Proved here:
- source=repair.go:54 msg="Found healthy block" (seven such lines in the 2026-11-04 H7 run) is not an event;
- genuine WAL repair, corrupted segments, mmap corruption, ERROR lines and non-zero counters each FAIL;
- failed HTTP (status, transport, helper) and unreadable counters FAIL with the reason, never PASS;
- the historical-sample query at the stamp: corrected query PASSes on multi-metric data; zero series FAILs;
- the complete log and raw HTTP evidence are kept on PASS and FAIL; the throwaway is removed on every path.

Synthetic tests are not host acceptance.
"""

from __future__ import annotations

import json
import os
import re
import signal
import sqlite3
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "p3" / "ops" / "restore_app_checks.sh"
STAMP = "20261104T010203Z"
AT = "1793754123"  # STAMP as epoch seconds
ORIGINAL_G8_QUERY = 'count(count_over_time({__name__=~".+"}[15m]))'

DOCKER = r'''#!/usr/bin/env python3
import json, os, subprocess, sys
sp = os.environ["TLOS_TEST_STATE"]
s = json.load(open(sp))
def save():
    json.dump(s, open(sp + ".tmp", "w")); os.replace(sp + ".tmp", sp)
a = sys.argv[1:]
with open(os.environ["TLOS_TEST_LOG"], "a") as log:
    log.write(" ".join(a) + "\n")
v = a[0]
if v == "image":
    print(a[2] + " id=sha256:stub digests=[]"); sys.exit(0)
if v == "run":
    assert a[a.index("--pull") + 1] == "never", a
    net = a[a.index("--network") + 1]
    if "-d" in a:
        assert net == "none"
        name = a[a.index("--name") + 1]
        s["containers"][name] = {"running": True, "polls": 0}; s["created"].append(name); save()
        print("cid"); sys.exit(0)
    if net.startswith("container:"):  # the HTTP helper: run its own code against the emulated server
        assert net[len("container:"):] in s["containers"], "helper must join the throwaway's namespace"
        if s.get("helper_fail"):
            sys.exit(125)
        env = {k: v for k, v in (x.split("=", 1) for x in [a[i + 1] for i, t in enumerate(a) if t == "-e"])}
        out = [x for x in a if x.endswith(":/out")][0].rsplit(":", 1)[0]
        env.update(OUT=out, PROM_URL=os.environ["TLOS_TEST_PROM_URL"], PATH=os.environ["PATH"])
        sys.exit(subprocess.run([sys.executable, "-c", a[a.index("-c") + 1]], env=env).returncode)
    assert net == "none"
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
    assert url.endswith("/-/ready"), url
    c["polls"] += 1; save()
    sys.exit(0 if s["ready_after"] is not None and c["polls"] >= s["ready_after"] else 1)
if v == "logs":
    assert a[-1] in s["containers"], "logs are read before the container is removed"
    for line in s["logs"].splitlines():
        print("2026-11-04T14:50:12.000000000Z " + line)
    sys.exit(0)
if v == "rm":
    name = a[-1]
    if name in s["containers"]:
        del s["containers"][name]; s["removed"].append(name); save()
    sys.exit(0)
sys.exit(3)
'''

HEALTHY_BLOCKS = "\n".join(
    f'time=2026-11-04T14:50:1{i}Z level=INFO source=repair.go:54 msg="Found healthy block" component=tsdb '
    f'mint=1793000000000 maxt=1793007200000 ulid=01K9ABC{i}' for i in range(7))
GOOD_LOGS = ('time=2026-11-04T14:50:10Z level=INFO source=main.go:1 msg="Starting Prometheus Server" mode=server\n'
             + HEALTHY_BLOCKS + "\n"
             'time=2026-11-04T14:50:11Z level=INFO source=head.go:832 msg="Replaying WAL, this may take a while" component=tsdb\n'
             'time=2026-11-04T14:50:11Z level=INFO source=head.go:965 msg="WAL replay completed" component=tsdb checkpoint_replay_duration=1ms\n'
             'time=2026-11-04T14:50:12Z level=INFO source=main.go:2 msg="Server is ready to receive web requests."')


class _Prometheus(BaseHTTPRequestHandler):
    """Answers like Prometheus v3.14.0 from the test state."""

    def do_GET(self):  # noqa: N802
        s = json.loads(Path(self.server.state_path).read_text())
        url = urllib.parse.urlparse(self.path)
        if url.path == "/metrics":
            if s["metrics_status"] != 200:
                return self._send(s["metrics_status"], b"internal error")
            lines = [] if s.get("omit_counters") else [
                f"prometheus_tsdb_wal_corruptions_total {s['wal_corruptions']}",
                f"prometheus_tsdb_mmap_chunk_corruptions_total {s['mmap_corruptions']}"]
            return self._send(200, ("\n".join(lines + ["prometheus_tsdb_head_series 120"]) + "\n").encode())
        if url.path == "/api/v1/query":
            q = urllib.parse.parse_qs(url.query)
            s.setdefault("queries", []).append({"query": q["query"][0], "time": q["time"][0]})
            Path(self.server.state_path).write_text(json.dumps(s))
            if s.get("query_transport_fail"):
                self.connection.close()
                return
            if s["query_status"] != 200:
                return self._json(s["query_status"], {"status": "error", "errorType": "unavailable",
                                                      "error": "injected failure"})
            m = re.fullmatch(r'count\((\w+)\(\{__name__=~"\.\+"\}\[\w+\]\)\)', q["query"][0])
            if m and m.group(1) not in ("last_over_time", "first_over_time") and s["metric_names"] >= 2:
                return self._json(422, {"status": "error", "errorType": "execution",
                                        "error": "vector cannot contain metrics with the same labelset"})
            res = [] if not s["series"] else [{"metric": {}, "value": [int(q["time"][0]), str(s["series"])]}]
            return self._json(200, {"status": "success", "data": {"resultType": "vector", "result": res}})
        self._send(404, b"not found")

    def _json(self, code, obj):
        self._send(code, json.dumps(obj).encode(), "application/json")

    def _send(self, code, body, ctype="text/plain"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


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
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Prometheus)
    srv.state_path = str(state)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    e = {**os.environ, "PATH": f"{bin_}:{os.environ['PATH']}", "TLOS_TEST_STATE": str(state),
         "TLOS_TEST_LOG": str(tmp_path / "docker.log"), "TLOS_TEST_PROM_URL": f"http://127.0.0.1:{srv.server_address[1]}",
         "TLOS_PROM_READY_TIMEOUT_S": "3", "TLOS_PROM_POLL_S": "0.1"}
    h = {"env": e, "data": data, "state": state, "out": tmp_path / "ev" / "h7_app.json",
         "log": tmp_path / "ev" / "h7_app.prometheus.log", "http": tmp_path / "ev" / "h7_app.http",
         "url": e["TLOS_TEST_PROM_URL"]}
    h["out"].parent.mkdir()
    set_state(h)
    yield h
    srv.shutdown()


def set_state(h, **kw):
    s = {"containers": {}, "created": [], "removed": [], "ready_after": 3, "exit_after_polls": None,
         "series": 42, "metric_names": 30, "logs": GOOD_LOGS, "mlflow": 2, "wal_corruptions": 0,
         "mmap_corruptions": 0, "metrics_status": 200, "query_status": 200}
    s.update(kw)
    h["state"].write_text(json.dumps(s))


def run(h, wait=True):
    args = [str(SCRIPT), str(h["data"]), STAMP, str(h["out"])]
    if not wait:
        return subprocess.Popen(args, env=h["env"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                start_new_session=True)
    p = subprocess.run(args, env=h["env"], capture_output=True, text=True, timeout=90)
    return p.returncode, p.stdout, p.stderr


def st(h):
    return json.loads(h["state"].read_text())


def checks(h):
    r = json.loads(h["out"].read_text())
    return r["RESTORE_APP_CHECKS"], {(c["name"], c["check"]): c["result"] for c in r["checks"]}


def wal_detail(h):
    return [c["detail"] for c in json.loads(h["out"].read_text())["checks"] if c["check"] == "WAL_RECOVERY"][0]


def assert_cleaned(h):
    s = st(h)
    assert s["containers"] == {} and s["created"] == s["removed"] and len(s["created"]) == 1


def test_the_stamp_constant_is_right():
    assert subprocess.run(["date", "-u", "-d", "2026-11-04T01:02:03Z", "+%s"], capture_output=True,
                          text=True).stdout.strip() == AT


def test_healthy_block_lines_are_not_events_and_all_checks_pass_with_evidence_kept(env):
    # The 2026-11-04 H7 run failed on exactly these seven lines: "repair" was the source file name.
    code, out, err = run(env)
    assert code == 0, out + err
    status, c = checks(env)
    assert status == "PASS" and set(c.values()) == {"PASS"}
    assert set(c) == {("grafana_db", "SQLITE_INTEGRITY"), ("mlflow", "APPLICATION_READ"),
                      ("prometheus", "APPLICATION_READY"), ("prometheus", "WAL_RECOVERY")}
    assert "series_before_stamp=42" in out and "wal_corruptions_total=0" in out
    assert_cleaned(env)
    # Evidence: the complete log, raw HTTP for /metrics and the query, image identities, all named in the JSON.
    assert env["log"].read_text().count('msg="Found healthy block"') == 7
    for n in ("metrics", "query"):
        assert json.loads((env["http"] / f"{n}.meta.json").read_text())["status"] == 200
    assert "prometheus_tsdb_wal_corruptions_total 0" in (env["http"] / "metrics.body").read_text()
    assert "prom/prometheus:v3.14.0" in (env["http"] / "images.txt").read_text()
    ev = json.loads(env["out"].read_text())["evidence"]
    assert ev == {"prometheus_log": str(env["log"]), "http": str(env["http"])}


def test_the_original_g8_query_fails_on_multi_metric_data_and_the_corrected_one_is_used_at_the_stamp(env):
    q = urllib.parse.quote(ORIGINAL_G8_QUERY)
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(f"{env['url']}/api/v1/query?query={q}&time={AT}")
    assert e.value.code == 422 and "same labelset" in json.loads(e.value.read())["error"]
    set_state(env)
    assert run(env)[0] == 0
    (asked,) = st(env)["queries"]
    assert asked == {"query": 'count(last_over_time({__name__=~".+"}[15m]))', "time": AT}


@pytest.mark.parametrize("line,needle", [
    ('level=WARN source=db.go:1218 msg="Encountered WAL read error, attempting repair" component=tsdb '
     'err="corruption in segment /prometheus/wal/00000003 at 41: unexpected full record"', "repair/corruption event"),
    ('level=WARN source=wlog.go:413 msg="Starting corruption repair" component=tsdb segment=3 offset=41',
     "repair/corruption event"),
    ('level=WARN source=wlog.go:443 msg="Rewrite corrupted segment" component=tsdb segment=3', "repair/corruption event"),
    ('level=INFO source=db.go:1222 msg="Successfully repaired WAL" component=tsdb', "repair/corruption event"),
    ('level=INFO source=head.go:1099 msg="Deletion of corrupted mmap chunk files failed, discarding chunk files '
     'completely" component=tsdb err="x"', "repair/corruption event"),
    ('level=ERROR source=head.go:807 msg="Loading on-disk chunks failed" component=tsdb err="unexpected EOF"',
     "level=ERROR"),
    ("panic: corrupt record header", "repair/corruption event"),
])
def test_each_genuine_event_fails_wal_recovery_and_the_log_is_kept(env, line, needle):
    set_state(env, logs=GOOD_LOGS + "\n" + line)
    code, _, _ = run(env)
    assert code == 1
    _, c = checks(env)
    assert c[("prometheus", "WAL_RECOVERY")] == "FAIL" and needle in wal_detail(env)
    assert line.split(" msg=")[0][:20] in env["log"].read_text()
    assert_cleaned(env)


@pytest.mark.parametrize("kw,needle", [
    ({"wal_corruptions": 1}, "wal_corruptions_total=1"),
    ({"mmap_corruptions": 2}, "mmap_chunk_corruptions_total=2"),
    ({"omit_counters": True}, "wal_corruptions_total not captured"),
    ({"metrics_status": 500}, "not captured (metrics HTTP status 500)"),
    ({"logs": GOOD_LOGS.replace('msg="WAL replay completed"', 'msg="WAL replay started"')}, "WAL replay completed"),
])
def test_counters_and_the_replay_line_are_required(env, kw, needle):
    set_state(env, **kw)
    assert run(env)[0] == 1
    assert checks(env)[1][("prometheus", "WAL_RECOVERY")] == "FAIL" and needle in wal_detail(env)
    assert_cleaned(env)


@pytest.mark.parametrize("kw,needle,status", [
    ({"query_status": 503}, "QUERY_FAILED: HTTP 503 injected failure", 503),
    ({"query_transport_fail": True}, "QUERY_FAILED: HTTP None", None),
    ({"helper_fail": True}, "QUERY_FAILED: no response captured", "absent"),
])
def test_a_failed_http_request_fails_with_its_reason_and_its_evidence(env, kw, needle, status):
    set_state(env, **kw)
    assert run(env)[0] == 1
    assert checks(env)[1][("prometheus", "WAL_RECOVERY")] == "FAIL" and needle in wal_detail(env)
    meta = env["http"] / "query.meta.json"
    if status == "absent":
        assert not meta.exists() and "helper_exit=125" in (env["http"] / "helper.txt").read_text()
    else:
        m = json.loads(meta.read_text())
        assert m["status"] == status
        if status is None:
            assert m["transport_error"]
        else:
            assert json.loads((env["http"] / "query.body").read_text())["error"] == "injected failure"
    assert env["log"].exists()
    assert_cleaned(env)


def test_no_series_before_the_stamp_fails(env):
    set_state(env, series=0)
    assert run(env)[0] == 1
    assert "no series with samples in the 15m before" in wal_detail(env)
    assert json.loads((env["http"] / "query.meta.json").read_text())["status"] == 200


@pytest.mark.parametrize("kw,detail", [
    ({"ready_after": None}, "not ready within 3s"),
    ({"exit_after_polls": 1}, "container exited"),
])
def test_a_server_that_never_gets_ready_fails_both_checks_and_its_log_is_kept(env, kw, detail):
    set_state(env, **kw)
    code, out, _ = run(env)
    assert code == 1 and detail in out
    _, c = checks(env)
    assert c[("prometheus", "APPLICATION_READY")] == "FAIL" and c[("prometheus", "WAL_RECOVERY")] == "FAIL"
    assert "Found healthy block" in env["log"].read_text()
    assert not (env["http"] / "query.meta.json").exists()
    assert_cleaned(env)


@pytest.mark.parametrize("kw,needle", [({"mlflow": 0}, "experiments=0"), ({"mlflow": None}, "exit=1")])
def test_mlflow_failures_fail_and_still_remove_the_container(env, kw, needle):
    set_state(env, **kw)
    code, out, _ = run(env)
    assert code == 1 and needle in out
    assert checks(env)[1][("mlflow", "APPLICATION_READ")] == "FAIL"
    assert_cleaned(env)


def test_a_corrupt_grafana_database_fails(env):
    p = env["data"] / "grafana" / "grafana.db"
    p.unlink()
    sqlite_db(p, corrupt=True)
    assert run(env)[0] == 1
    assert checks(env)[1][("grafana_db", "SQLITE_INTEGRITY")] == "FAIL"
    assert_cleaned(env)


def test_sigterm_while_waiting_for_readiness_saves_the_log_and_removes_the_container(env):
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
    assert "Found healthy block" in env["log"].read_text()
    assert not env["out"].exists()


def test_usage_errors_change_nothing(env):
    assert subprocess.run([str(SCRIPT), str(env["data"]), "2026-11-04", str(env["out"])], env=env["env"],
                          capture_output=True).returncode == 2
    env["log"].write_text("earlier evidence")
    assert run(env)[0] == 2
    env["log"].unlink()
    env["out"].write_text("{}")
    assert run(env)[0] == 2
    assert st(env)["created"] == []
