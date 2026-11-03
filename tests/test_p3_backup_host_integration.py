"""P3-PLN-03 host integration support: bound pre-stop coverage, exclusive runs, the SSD mirror, runtime recovery.

The host stops its runtime with ``docker compose down``, which removes the containers, so coverage is observed
**before** the stop and the report is bound into the set by ``create --coverage-report``. A report that is not
PASS, describes other sources or roots, or is stale or from the future is refused, and nothing is written.

- Two runs never overlap: create and mirror hold exclusive flocks. A holder killed by SIGKILL releases its lock.
- The mirror never destroys the last verified full generation while publishing. It is interrupted at every
  step here, including mid-copy, and each interruption is shown to keep that invariant; a re-run then completes.
  Legacy partial copies (``latest``/``previous``/``.incoming``) are never touched.
- ``runtime_check`` judges Grafana, Prometheus and MLflow individually. An incomplete recovery is a FAIL, and a
  timeout returns FAIL rather than hanging.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "research"))
sys.path.insert(0, str(REPO / "scripts" / "p3"))

from p3 import backup  # noqa: E402
from test_p3_backup_live_data import PROJECT, FakeDocker, container, live, sources  # noqa: E402,F401

SERVICES = ("grafana", "prometheus", "mlflow")


def roots_of(live: dict) -> dict:
    return {"trading": live["trading"]}


def report_file(tmp_path: Path, live: dict, monkeypatch, *, data=None, name="cov.json") -> Path:
    monkeypatch.setattr(backup.subprocess, "run", FakeDocker(live["containers"]))
    report = backup.coverage_report(PROJECT, data=sources(live) if data is None else data, roots=roots_of(live))
    path = tmp_path / name
    backup.write_coverage_report(report, path)
    return path


def rewrite(path: Path, **changes) -> Path:
    report = json.loads(path.read_text())
    report.update(changes)
    path.chmod(0o600)
    path.write_text(json.dumps(report))
    return path


# ------------------------------------------------------------------------------------------------------------
# B-bound: coverage observed before the stop, bound into the record
# ------------------------------------------------------------------------------------------------------------

def test_a_pre_stop_report_binds_into_the_set_after_compose_down(tmp_path, live, monkeypatch):
    cov = report_file(tmp_path, live, monkeypatch)
    assert stat.S_IMODE(cov.stat().st_mode) == 0o600
    # compose down: the project's containers are gone
    monkeypatch.setattr(backup.subprocess, "run", FakeDocker([c for c in live["containers"]
                                                              if c["Name"] == "/other-project"]))
    with pytest.raises(backup.BackupError, match="no container of compose project"):
        backup.create_backup(tmp_path / "b", roots=roots_of(live), repos={}, data=sources(live),
                             compose_project=PROJECT, stamp="s0")
    record = backup.create_backup(tmp_path / "b", roots=roots_of(live), repos={}, data=sources(live),
                                  coverage_report=cov, stamp="s1")
    ldc = record["live_data_coverage"]
    assert ldc["LIVE_DATA_COVERAGE"] == "PASS" and ldc["observed"] == "before_runtime_stop"
    assert ldc["report_sha256"] == backup.sha256_file(cov) and ldc["compose_project"] == PROJECT
    assert set(record["data_sources"]) == set(SERVICES)
    assert backup.restore_drill(tmp_path / "b" / "s1", tmp_path / "scratch")["PLN_03_RESTORE_DRILL"] == "PASS"


@pytest.mark.parametrize("mutate,why", [
    (lambda live, d: {**d, "LIVE_DATA_COVERAGE": "FAIL"}, "LIVE_DATA_COVERAGE = FAIL"),
    (lambda live, d: {**d, "report_version": "OTHER"}, "report_version"),
    (lambda live, d: {**d, "compose_project": ""}, "no compose_project"),
    (lambda live, d: {**d, "data": {k: v for k, v in d["data"].items() if k != "mlflow"}}, "data sources"),
    (lambda live, d: {**d, "data": {**d["data"], "grafana": "tlos_runtime_grafana_data"}}, "data sources"),
    (lambda live, d: {**d, "roots": {"other": "/tmp"}}, "roots"),
    (lambda live, d: {**d, "generated_epoch": time.time() - backup.COVERAGE_MAX_AGE_S - 5}, "observed"),
    (lambda live, d: {**d, "generated_epoch": time.time() + backup.COVERAGE_FUTURE_SKEW_S + 60}, "observed"),
])
def test_a_report_that_does_not_describe_this_backup_is_refused_and_nothing_is_written(tmp_path, live, monkeypatch,
                                                                                       mutate, why):
    cov = report_file(tmp_path, live, monkeypatch)
    original = json.loads(cov.read_text())
    rewrite(cov, **mutate(live, original))
    with pytest.raises(backup.BackupError, match=why):
        backup.create_backup(tmp_path / "b", roots=roots_of(live), repos={}, data=sources(live),
                             coverage_report=cov, stamp="s")
    assert not (tmp_path / "b").exists()


def test_create_data_must_equal_the_report_both_ways(tmp_path, live, monkeypatch):
    cov = report_file(tmp_path, live, monkeypatch)
    fewer = {k: v for k, v in sources(live).items() if k != "prometheus"}
    with pytest.raises(backup.BackupError, match="data sources"):
        backup.create_backup(tmp_path / "b", roots=roots_of(live), repos={}, data=fewer, coverage_report=cov)
    with pytest.raises(backup.BackupError, match="roots"):
        backup.create_backup(tmp_path / "b", roots={**roots_of(live), "x": tmp_path}, repos={}, data=sources(live),
                             coverage_report=cov)


def test_unreadable_report_and_both_modes_are_refused(tmp_path, live, monkeypatch):
    with pytest.raises(backup.BackupError, match="unreadable"):
        backup.create_backup(tmp_path / "b", roots={}, repos={}, data=sources(live),
                             coverage_report=tmp_path / "missing.json")
    cov = report_file(tmp_path, live, monkeypatch)
    with pytest.raises(backup.BackupError, match="not both"):
        backup.create_backup(tmp_path / "b", roots=roots_of(live), repos={}, data=sources(live),
                             coverage_report=cov, compose_project=PROJECT)
    assert not (tmp_path / "b").exists()


def test_cli_coverage_report_then_create_and_the_report_is_never_overwritten(tmp_path, live, monkeypatch, capsys):
    import backup as cli
    monkeypatch.setattr(backup.subprocess, "run", FakeDocker(live["containers"]))
    cov = tmp_path / "cov.json"
    base = ["--root", f"trading={live['trading']}"] + [f"--data={k}={v}" for k, v in sources(live).items()]
    assert cli.main(["coverage", "--compose-project", PROJECT, "--json", str(cov)] + base) == 0
    assert stat.S_IMODE(cov.stat().st_mode) == 0o600 and json.loads(cov.read_text())["data"] == sources(live)
    assert cli.main(["coverage", "--compose-project", PROJECT, "--json", str(cov)] + base) == 2  # exists: refused
    assert cli.main(["create", "--target", str(tmp_path / "b"), "--stamp", "s", "--coverage-report", str(cov)]
                    + base) == 0
    record = json.loads((tmp_path / "b" / "s" / backup.RECORD).read_text())
    assert record["live_data_coverage"]["observed"] == "before_runtime_stop"
    capsys.readouterr()


def test_without_coverage_the_set_says_unproven(tmp_path, live, monkeypatch):
    # The runtime was intentionally inactive: no containers to observe; the data is still backed up.
    monkeypatch.setattr(backup.subprocess, "run", FakeDocker(live["containers"]))
    record = backup.create_backup(tmp_path / "b", roots=roots_of(live), repos={}, data=sources(live), stamp="s")
    assert record["live_data_coverage"] is None and set(record["data_sources"]) == set(SERVICES)


# ------------------------------------------------------------------------------------------------------------
# Concurrency: exclusive runs, released even on SIGKILL
# ------------------------------------------------------------------------------------------------------------

def hold_lock(path: Path) -> subprocess.Popen:
    code = ("import fcntl,os,sys,time; fd=os.open(sys.argv[1], os.O_RDWR|os.O_CREAT, 0o600); "
            "fcntl.flock(fd, fcntl.LOCK_EX); print('held', flush=True); time.sleep(60)")
    proc = subprocess.Popen([sys.executable, "-c", code, str(path)], stdout=subprocess.PIPE, text=True)
    assert proc.stdout.readline().strip() == "held"
    return proc


def make_plain_set(tmp_path: Path, live: dict, monkeypatch, stamp: str) -> Path:
    monkeypatch.setattr(backup.subprocess, "run", FakeDocker(live["containers"]))
    backup.create_backup(tmp_path / "b", roots=roots_of(live), repos={}, data=sources(live), stamp=stamp)
    return tmp_path / "b" / stamp


def test_two_creates_never_overlap_and_a_killed_holder_releases(tmp_path, live, monkeypatch):
    target = tmp_path / "b"
    target.mkdir()
    holder = hold_lock(target / backup.LOCK_NAME)
    try:
        monkeypatch.setattr(backup.subprocess, "run", FakeDocker(live["containers"]))
        with pytest.raises(backup.BackupError, match="held by another run"):
            backup.create_backup(target, roots=roots_of(live), repos={}, data=sources(live), stamp="s1")
        assert sorted(p.name for p in target.iterdir()) == [backup.LOCK_NAME], "the refused run wrote nothing"
    finally:
        holder.send_signal(signal.SIGKILL)
        holder.wait()
    backup.create_backup(target, roots=roots_of(live), repos={}, data=sources(live), stamp="s1")
    assert backup.verify_backup(target / "s1")["status"] == "PASS"


def test_two_mirror_publishes_never_overlap(tmp_path, live, monkeypatch):
    set_dir = make_plain_set(tmp_path, live, monkeypatch, "20261104T010000Z")
    mirror = tmp_path / "ssd"
    mirror.mkdir()
    holder = hold_lock(mirror / backup.MIRROR_LOCK)
    try:
        with pytest.raises(backup.BackupError, match="held by another run"):
            backup.publish_mirror(set_dir, mirror, margin_bytes=0)
        assert not (mirror / backup.MIRROR_CURRENT).exists()
    finally:
        holder.kill()
        holder.wait()
    assert backup.publish_mirror(set_dir, mirror, margin_bytes=0)["SSD_MIRROR"] == "PASS"


# ------------------------------------------------------------------------------------------------------------
# SSD mirror: verified full generations; the last verified one survives every interruption
# ------------------------------------------------------------------------------------------------------------

@pytest.fixture
def legacy_mirror(tmp_path) -> Path:
    """The host mirror today: partial volumes-only copies under latest/ and previous/, maybe a stale .incoming."""
    mirror = tmp_path / "ssd"
    for gen in ("latest", "previous", ".incoming"):
        (mirror / gen / "volumes").mkdir(parents=True)
        (mirror / gen / "volumes" / "tlos_runtime_grafana_data.tar").write_bytes(b"old volume " + gen.encode())
        (mirror / gen / "SOURCE_SET").write_text("20261103T183447Z\n")
    return mirror


def snapshot(path: Path) -> dict:
    return {p.relative_to(path).as_posix(): (p.read_bytes() if p.is_file() else None)
            for p in sorted(path.rglob("*")) if not p.relative_to(path).as_posix().startswith(("sets", "current"))
            and p.name not in (backup.MIRROR_LOCK,)}


def current_verifies(mirror: Path) -> str | None:
    cur = mirror / backup.MIRROR_CURRENT
    if not cur.is_symlink():
        return None
    assert backup.verify_backup(cur)["status"] == "PASS"
    return os.readlink(cur)


def test_publish_is_a_verified_full_copy_that_drills_and_leaves_legacy_untouched(tmp_path, live, monkeypatch,
                                                                                legacy_mirror):
    before = snapshot(legacy_mirror)
    set_dir = make_plain_set(tmp_path, live, monkeypatch, "20261104T010000Z")
    report = backup.publish_mirror(set_dir, legacy_mirror, margin_bytes=0)
    assert report["SSD_MIRROR"] == "PASS" and report["generations"] == ["20261104T010000Z"]
    assert report["legacy_untouched"] == [".incoming", "latest", "previous"]
    assert snapshot(legacy_mirror) == before, "legacy partial copies are never touched"
    assert current_verifies(legacy_mirror) == "sets/20261104T010000Z"
    copy = legacy_mirror / backup.MIRROR_CURRENT
    assert backup.group_or_other_accessible(legacy_mirror / "sets" / "20261104T010000Z") == []
    drill = backup.restore_drill(copy, tmp_path / "scratch-from-ssd")
    assert drill["PLN_03_RESTORE_DRILL"] == "PASS" and drill["checks"]["data:grafana"]["status"] == "PASS"


def test_retention_keeps_the_newest_generations_and_never_the_current_one(tmp_path, live, monkeypatch, legacy_mirror):
    stamps = ["20261104T010000Z", "20261105T010000Z", "20261106T010000Z"]
    for stamp in stamps:
        report = backup.publish_mirror(make_plain_set(tmp_path, live, monkeypatch, stamp), legacy_mirror,
                                       keep=2, margin_bytes=0)
    assert report["generations"] == stamps[1:] and report["retired"] == [stamps[0]]
    assert current_verifies(legacy_mirror) == f"sets/{stamps[2]}"
    with pytest.raises(backup.BackupError, match="keep must be at least 1"):
        backup.publish_mirror(tmp_path / "b" / stamps[2], legacy_mirror, keep=0)


class Interrupt(Exception):
    pass


@pytest.mark.parametrize("keep", [1, 2])
@pytest.mark.parametrize("step", ["copy", "verify", "publish", "pointer", "retire", "delete"])
def test_an_interruption_at_any_step_never_destroys_the_last_verified_generation(tmp_path, live, monkeypatch,
                                                                                 legacy_mirror, step, keep):
    # `keep` generations already published, so publishing one more always retires the oldest
    olds = [f"2026110{4 + i}T010000Z" for i in range(keep)]
    for stamp in olds:
        backup.publish_mirror(make_plain_set(tmp_path, live, monkeypatch, stamp), legacy_mirror, keep=keep,
                              margin_bytes=0)
    new = make_plain_set(tmp_path, live, monkeypatch, "20261109T010000Z")
    legacy = snapshot(legacy_mirror)

    def boom(at):
        if at == step:
            raise Interrupt(at)
    with pytest.raises(Interrupt):
        backup.publish_mirror(new, legacy_mirror, keep=keep, margin_bytes=0, _step=boom)
    # invariant: a verified full generation remains, and current points at a verified one
    published = backup.mirror_generations(legacy_mirror)
    assert published, "no verified generation left"
    for name in published:
        assert backup.verify_backup(legacy_mirror / "sets" / name)["status"] == "PASS"
    assert current_verifies(legacy_mirror) in {f"sets/{name}" for name in published}
    if step in ("copy", "verify", "publish"):
        assert published == olds and current_verifies(legacy_mirror) == f"sets/{olds[-1]}"
    else:  # the new generation was verified and published before anything older was touched
        assert "20261109T010000Z" in published
    assert snapshot(legacy_mirror) == legacy
    # a re-run completes the publish and cleans the dot-name leftovers
    report = backup.publish_mirror(new, legacy_mirror, keep=keep, margin_bytes=0)
    assert current_verifies(legacy_mirror) == "sets/20261109T010000Z"
    assert report["generations"] == (olds + ["20261109T010000Z"])[-keep:]
    assert not [p for p in (legacy_mirror / "sets").iterdir() if p.name.startswith(".")]


def test_an_interruption_in_the_middle_of_the_copy_keeps_the_previous_generation(tmp_path, live, monkeypatch,
                                                                                legacy_mirror):
    a = make_plain_set(tmp_path, live, monkeypatch, "20261104T010000Z")
    b = make_plain_set(tmp_path, live, monkeypatch, "20261105T010000Z")
    backup.publish_mirror(a, legacy_mirror, keep=1, margin_bytes=0)
    real_copy2, copied = shutil.copy2, []

    def dying_copy2(src, dst, *args, **kwargs):
        if len(copied) == 3:
            raise Interrupt("power cut mid-copy")
        copied.append(src)
        return real_copy2(src, dst, *args, **kwargs)
    monkeypatch.setattr(backup.shutil, "copy2", dying_copy2)
    with pytest.raises(Exception):
        backup.publish_mirror(b, legacy_mirror, keep=1, margin_bytes=0)
    monkeypatch.setattr(backup.shutil, "copy2", real_copy2)
    assert backup.mirror_generations(legacy_mirror) == ["20261104T010000Z"]
    assert current_verifies(legacy_mirror) == "sets/20261104T010000Z"
    assert (legacy_mirror / "sets" / ".incoming-20261105T010000Z").exists(), "the partial copy is never published"
    backup.publish_mirror(b, legacy_mirror, keep=1, margin_bytes=0)
    assert backup.mirror_generations(legacy_mirror) == ["20261105T010000Z"]


def test_a_copy_that_does_not_verify_is_not_published(tmp_path, live, monkeypatch, legacy_mirror):
    a = make_plain_set(tmp_path, live, monkeypatch, "20261104T010000Z")
    b = make_plain_set(tmp_path, live, monkeypatch, "20261105T010000Z")
    backup.publish_mirror(a, legacy_mirror, keep=1, margin_bytes=0)
    real_privatize = backup._privatize

    def corrupt(path):
        real_privatize(path)
        (path / "data" / "grafana.tar").write_bytes(b"bit rot on the way")
    monkeypatch.setattr(backup, "_privatize", corrupt)
    with pytest.raises(backup.BackupError, match="not published: verify FAIL"):
        backup.publish_mirror(b, legacy_mirror, keep=1, margin_bytes=0)
    assert backup.mirror_generations(legacy_mirror) == ["20261104T010000Z"]
    assert current_verifies(legacy_mirror) == "sets/20261104T010000Z"


def test_no_space_refuses_and_deletes_nothing(tmp_path, live, monkeypatch, legacy_mirror):
    a = make_plain_set(tmp_path, live, monkeypatch, "20261104T010000Z")
    b = make_plain_set(tmp_path, live, monkeypatch, "20261105T010000Z")
    backup.publish_mirror(a, legacy_mirror, keep=1, margin_bytes=0)
    with pytest.raises(backup.BackupError, match="nothing is deleted to make room"):
        backup.publish_mirror(b, legacy_mirror, keep=1, margin_bytes=1 << 60)
    assert backup.mirror_generations(legacy_mirror) == ["20261104T010000Z"]


def test_an_unverified_source_or_a_corrupt_existing_generation_is_refused(tmp_path, live, monkeypatch, legacy_mirror):
    a = make_plain_set(tmp_path, live, monkeypatch, "20261104T010000Z")
    backup.publish_mirror(a, legacy_mirror, margin_bytes=0)
    target = legacy_mirror / "sets" / "20261104T010000Z" / "data" / "mlflow.tar"
    target.write_bytes(b"x")
    with pytest.raises(backup.BackupError, match="exists and does not verify; it is not overwritten"):
        backup.publish_mirror(a, legacy_mirror, margin_bytes=0)
    (a / "data" / "grafana.tar").chmod(0o600)
    (a / "data" / "grafana.tar").write_bytes(b"y")
    with pytest.raises(backup.BackupError, match="does not verify; nothing is mirrored"):
        backup.publish_mirror(a, legacy_mirror, margin_bytes=0)


def test_cli_mirror(tmp_path, live, monkeypatch, legacy_mirror, capsys):
    import backup as cli
    a = make_plain_set(tmp_path, live, monkeypatch, "20261104T010000Z")
    assert cli.main(["mirror", "--set", str(a), "--mirror", str(legacy_mirror), "--margin-gib", "0",
                     "--json", str(tmp_path / "m.json")]) == 0
    assert "SSD_MIRROR = PASS" in capsys.readouterr().out
    assert json.loads((tmp_path / "m.json").read_text())["published"] == "20261104T010000Z"
    assert cli.main(["mirror", "--set", str(a), "--mirror", str(legacy_mirror), "--margin-gib", "1e12"]) in (0, 2)


# ------------------------------------------------------------------------------------------------------------
# Runtime recovery: each service individually; incomplete = FAIL; never hangs
# ------------------------------------------------------------------------------------------------------------

def state(status="running", started="2026-11-04T01:00:05.123Z", health=None, restarting=False) -> dict:
    st = {"Status": status, "Restarting": restarting, "StartedAt": started}
    if health:
        st["Health"] = {"Status": health}
    return {"State": st}


T0 = backup._started_epoch("2026-11-04T01:00:00")


def test_all_three_back_is_pass():
    report = backup.runtime_check(PROJECT, SERVICES, started_after=T0, state_of=lambda p, s: [state()])
    assert report["RUNTIME_RECOVERY"] == "PASS" and set(report["services"]) == set(SERVICES)


@pytest.mark.parametrize("bad,problem", [
    ([], "0 containers"),
    ([state(), state()], "2 containers"),
    ([state(status="exited")], "status exited"),
    ([state(restarting=True)], "restarting"),
    ([state(health="unhealthy")], "health unhealthy"),
    ([state(started="2026-11-04T00:30:00Z")], "before this restoration"),
])
def test_one_service_not_back_fails_the_recovery_and_is_named(bad, problem):
    report = backup.runtime_check(PROJECT, SERVICES, started_after=T0,
                                  state_of=lambda p, s: bad if s == "prometheus" else [state()])
    assert report["RUNTIME_RECOVERY"] == "FAIL"
    assert report["services"]["prometheus"]["status"] == "FAIL"
    assert any(problem in x for x in report["services"]["prometheus"]["problems"])
    assert report["services"]["grafana"]["status"] == report["services"]["mlflow"]["status"] == "PASS"


def test_waits_for_a_starting_service_then_passes_and_a_timeout_is_fail_not_a_hang():
    clock = {"t": 0.0}
    seen = {"n": 0}

    def state_of(p, s):
        if s == "grafana":
            seen["n"] += 1
            return [state(health="healthy" if seen["n"] >= 3 else "starting")]
        return [state()]
    tick = lambda: clock["t"]  # noqa: E731
    sleep = lambda d: clock.__setitem__("t", clock["t"] + d)  # noqa: E731
    report = backup.runtime_check(PROJECT, SERVICES, wait_s=10, state_of=state_of, sleep=sleep, clock=tick)
    assert report["RUNTIME_RECOVERY"] == "PASS" and seen["n"] == 3
    clock["t"] = 0.0
    report = backup.runtime_check(PROJECT, SERVICES, wait_s=10, state_of=lambda p, s: [state(status="created")],
                                  sleep=sleep, clock=tick)
    assert report["RUNTIME_RECOVERY"] == "FAIL" and clock["t"] >= 10


def test_cli_runtime_check_uses_compose_labels(monkeypatch, capsys):
    import backup as cli
    calls = []

    def fake_run(cmd, *args, **kwargs):
        calls.append(cmd)
        if cmd[1] == "ps":
            service = cmd[-1].rsplit("=", 1)[1]
            return subprocess.CompletedProcess(cmd, 0, f"id-{service}\n", "")
        return subprocess.CompletedProcess(cmd, 0, json.dumps([state() if cmd[2] != "id-mlflow"
                                                               else state(status="exited")]), "")
    monkeypatch.setattr(backup.subprocess, "run", fake_run)
    assert cli.main(["runtime-check", "--compose-project", PROJECT] + sum((["--service", s] for s in SERVICES), [])) == 1
    out = capsys.readouterr().out
    assert "mlflow       FAIL status exited" in out and "RUNTIME_RECOVERY = FAIL" in out
    assert ["--filter", f"label=com.docker.compose.project={PROJECT}"] == calls[0][4:6]
