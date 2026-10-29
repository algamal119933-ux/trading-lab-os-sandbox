"""P3 backup storage location (research/p3/storage.py) and every consumer of it.

The store is configured once and there is no implicit default. A missing or unusable configuration is
never replaced by another location; the health check reports it CRITICAL, the backup wrapper refuses to
run, and the reboot snapshot errors. The live preflight refuses a symlinked mountpoint, another
filesystem UUID, and a target that resolves off the store.
Synthetic paths only; nothing here touches a real mount.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "research"))

from p3 import health, storage  # noqa: E402

UUID = "0f3c5a2e-9b1d-4c7e-8a6f-2d4b1e9c7a10"


def _cfg(tmp_path, **data) -> Path:
    p = tmp_path / "storage.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


class R:
    def __init__(self, out="", exc=None):
        self.stdout, self.exc = out, exc

    def __call__(self, cmd):
        if self.exc:
            raise self.exc
        return self


# ---------------------------------------------------------------- resolution


def test_nothing_configured_is_refused_not_defaulted(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DEFAULT_CONFIG", tmp_path / "absent.json")
    with pytest.raises(storage.StorageConfigError, match="no backup store configured"):
        storage.load(env={})
    with pytest.raises(storage.StorageConfigError, match="no backup store configured"):
        storage.load(env={"TLOS_STORAGE_CONFIG": str(tmp_path / "missing.json")})


def test_a_config_file_moves_every_path_together(tmp_path):
    p = _cfg(tmp_path, backup_mount="/srv/project-data", backup_target="/srv/project-data/tlos-backups",
             mount_uuid=UUID)
    s = storage.load(env={}, config_path=p)
    assert (s.backup_mount, s.backup_target, s.mount_uuid, s.source) == (
        "/srv/project-data", "/srv/project-data/tlos-backups", UUID, str(p))
    assert s.target == Path("/srv/project-data/tlos-backups")


def test_the_config_env_variable_names_the_file(tmp_path):
    p = _cfg(tmp_path, backup_mount="/srv/x", backup_target="/srv/x/b", mount_uuid=UUID)
    assert storage.load(env={"TLOS_STORAGE_CONFIG": str(p)}).backup_mount == "/srv/x"


def test_env_overrides_the_file_and_needs_all_three_values(tmp_path):
    p = _cfg(tmp_path, backup_mount="/srv/x", backup_target="/srv/x/b", mount_uuid=UUID)
    full = {"TLOS_BACKUP_MOUNT": "/srv/y", "TLOS_BACKUP_TARGET": "/srv/y/b", "TLOS_BACKUP_MOUNT_UUID": UUID}
    s = storage.load(env=full, config_path=p)
    assert (s.backup_mount, s.mount_uuid, s.source) == ("/srv/y", UUID, "env")
    for drop in full:
        partial = {k: v for k, v in full.items() if k != drop}
        with pytest.raises(storage.StorageConfigError, match="set together"):
            storage.load(env=partial, config_path=p)


def test_a_configuration_without_a_uuid_is_refused(tmp_path):
    # Without the UUID any filesystem mounted at the path (a tmpfs, another disk) would pass as the store.
    with pytest.raises(storage.StorageConfigError, match="mount_uuid is required"):
        storage.load(env={}, config_path=_cfg(tmp_path, backup_mount="/srv/x", backup_target="/srv/x/b"))
    with pytest.raises(storage.StorageConfigError, match="mount_uuid is required"):
        storage.load(env={}, config_path=_cfg(tmp_path, backup_mount="/srv/x", backup_target="/srv/x/b",
                                              mount_uuid=UUID + "\n"))


def test_a_config_that_is_not_a_regular_file_is_refused_without_blocking(tmp_path):
    fifo = tmp_path / "storage.json"
    os.mkfifo(fifo)
    with pytest.raises(storage.StorageConfigError, match="not a regular file"):
        storage.load(env={}, config_path=fifo)
    d = tmp_path / "dir.json"
    d.mkdir()
    with pytest.raises(storage.StorageConfigError, match="not a regular file"):
        storage.load(env={}, config_path=d)


@pytest.mark.parametrize("data, why", [
    ({"backup_mount": "/", "backup_target": "/tlos-backups", "mount_uuid": UUID}, "system disk"),
    ({"backup_mount": "/srv/x", "backup_target": "/srv/other/b", "mount_uuid": UUID}, "not inside"),
    ({"backup_mount": "srv/x", "backup_target": "srv/x/b", "mount_uuid": UUID}, "absolute"),
    ({"backup_mount": "/srv/x", "backup_target": "/srv/x/../etc", "mount_uuid": UUID}, "'..'"),
    ({"backup_mount": "/srv/x", "backup_target": "/srv/x/b", "mount_uuid": "x; rm -rf /"}, "UUID"),
    ({"backup_mount": "/srv/x", "backup_target": "/srv/x/b", "extra": 1, "mount_uuid": UUID}, "unknown keys"),
    ({"backup_mount": 5, "backup_target": "/srv/x/b", "mount_uuid": UUID}, "strings"),
    ({"backup_mount": "//srv/x", "backup_target": "//srv/x/b", "mount_uuid": UUID}, "normalised"),
    ({"backup_mount": "/srv/x", "backup_target": "/srv/x/./b", "mount_uuid": UUID}, "normalised"),
    ({"backup_mount": "/srv//x", "backup_target": "/srv//x/b", "mount_uuid": UUID}, "normalised"),
    ({"backup_mount": "/srv/x", "backup_target": "/srv/x/$(id)", "mount_uuid": UUID}, "quotes"),
    ({"backup_mount": "/srv/x", "backup_target": "/srv/x/`id`", "mount_uuid": UUID}, "quotes"),
    ({"backup_mount": "/srv/x", "backup_target": "/srv/x/b\nTLOS_STORAGE_TARGET=/", "mount_uuid": UUID}, "quotes"),
])
def test_an_invalid_file_is_refused_never_defaulted(tmp_path, data, why):
    with pytest.raises(storage.StorageConfigError, match=why):
        storage.load(env={}, config_path=_cfg(tmp_path, **data))


def test_an_unreadable_or_named_but_missing_file_is_refused(tmp_path):
    bad = tmp_path / "storage.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(storage.StorageConfigError, match="unreadable"):
        storage.load(env={}, config_path=bad)
    lst = tmp_path / "list.json"
    lst.write_text("[]", encoding="utf-8")
    with pytest.raises(storage.StorageConfigError, match="JSON object"):
        storage.load(env={}, config_path=lst)


def test_shell_exports_round_trip_through_bash(tmp_path):
    s = storage.load(env={}, config_path=_cfg(tmp_path, backup_mount="/srv/project data",
                                                backup_target="/srv/project data/b", mount_uuid=UUID))
    out = subprocess.run(["bash", "-c", 'eval "$1"; printf "%s|%s|%s|%s" "$TLOS_STORAGE_MOUNT" '
                          '"$TLOS_STORAGE_TARGET" "$TLOS_STORAGE_UUID" "$TLOS_STORAGE_SOURCE"', "_",
                          storage.shell_exports(s)], capture_output=True, text=True, check=True).stdout
    assert out == f"/srv/project data|/srv/project data/b|{UUID}|{s.source}"


def test_a_quote_in_a_value_cannot_reach_the_shell(tmp_path):
    with pytest.raises(storage.StorageConfigError):
        storage.shell_exports(storage.Storage("/srv/a'b", "/srv/a'b/c", None, "x"))
    with pytest.raises(storage.StorageConfigError):
        storage.load(env={}, config_path=_cfg(tmp_path, backup_mount="/srv/a'b", backup_target="/srv/a'b/c"))


# ---------------------------------------------------------------- live preflight (synthetic filesystems)


def _is_mount(p: str) -> bool:
    return subprocess.run(["mountpoint", "-q", p]).returncode == 0


needs_proc = pytest.mark.skipif(not _is_mount("/proc"), reason="/proc is not a mountpoint here")


def test_a_target_symlinked_off_the_store_is_refused(tmp_path):
    m, elsewhere = tmp_path / "store", tmp_path / "elsewhere"
    m.mkdir()
    elsewhere.mkdir()
    (m / "b").symlink_to(elsewhere)
    probs = storage.target_problems(storage.Storage(str(m), str(m / "b"), None, "t"))
    assert any("resolves outside the store" in p for p in probs)
    (m / "c").symlink_to(m)  # a link that stays inside is still not a plain directory
    probs = storage.target_problems(storage.Storage(str(m), str(m / "c"), None, "t"))
    assert any("not a plain directory" in p for p in probs)
    (m / "f").write_text("x", encoding="utf-8")
    assert any("not a plain directory" in p
               for p in storage.target_problems(storage.Storage(str(m), str(m / "f"), None, "t")))


def test_a_parent_symlinked_off_the_store_is_refused_before_anything_is_created(tmp_path):
    m, elsewhere = tmp_path / "store", tmp_path / "elsewhere"
    m.mkdir()
    elsewhere.mkdir()
    (m / "sub").symlink_to(elsewhere)
    target = m / "sub" / "deep" / "tlos-backups"
    probs = storage.target_problems(storage.Storage(str(m), str(target), None, "t"))
    assert any("resolves outside the store" in p for p in probs) and not target.exists()


def test_a_nested_mount_under_the_store_is_refused(tmp_path, monkeypatch):
    m = tmp_path / "store"
    (m / "nested").mkdir(parents=True)
    real_stat = os.stat

    def fake_stat(p, *a, **k):
        st = real_stat(p, *a, **k)
        if str(p).endswith("/nested"):
            return os.stat_result((st.st_mode, st.st_ino, st.st_dev + 1) + tuple(st)[3:])
        return st
    monkeypatch.setattr(storage.os, "stat", fake_stat)
    probs = storage.target_problems(storage.Storage(str(m), str(m / "nested" / "b"), None, "t"))
    assert any("another filesystem" in p for p in probs)


def test_a_plain_target_inside_the_store_passes(tmp_path):
    m = tmp_path / "store"
    (m / "tlos-backups").mkdir(parents=True)
    assert storage.target_problems(storage.Storage(str(m), str(m / "tlos-backups"), None, "t")) == []
    assert storage.target_problems(storage.Storage(str(m), str(m / "not-yet" / "b"), None, "t")) == []


def test_preflight_refuses_an_unmounted_or_symlinked_mountpoint(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    assert storage.preflight(storage.Storage(str(plain), str(plain / "b"), None, "t")) == [f"{plain} is not mounted"]
    link = tmp_path / "link"
    link.symlink_to("/proc")
    assert "is a symlink" in storage.preflight(storage.Storage(str(link), str(link / "b"), None, "t"))[0]


@needs_proc
def test_preflight_checks_the_uuid_of_a_real_mountpoint():
    s = storage.Storage("/proc", "/proc/tlos-not-here/b", UUID, "t")
    assert "not the configured" in storage.preflight(s, runner=lambda cmd: "1111-2222\n")[0]
    assert "cannot be read" in storage.preflight(s, runner=lambda cmd: (_ for _ in ()).throw(OSError()))[0]
    assert storage.preflight(s, runner=lambda cmd: UUID + "\n") == []
    assert "identity is unproven" in storage.preflight(storage.Storage("/proc", "/proc/tlos-not-here/b", None, "t"))[0]


def test_the_cli_preflight_exits_3_with_reasons(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    r = subprocess.run([sys.executable, str(REPO / "research" / "p3" / "storage.py"), "--preflight"],
                       env={**os.environ, "TLOS_BACKUP_MOUNT": str(plain), "TLOS_BACKUP_TARGET": str(plain / "b"),
                            "TLOS_BACKUP_MOUNT_UUID": UUID},
                       capture_output=True, text=True)
    assert r.returncode == 3 and "STORAGE_PREFLIGHT_FAIL" in r.stderr and "not mounted" in r.stderr


def test_the_cli_exits_3_on_an_unusable_configuration(tmp_path):
    bad = _cfg(tmp_path, backup_mount="/", backup_target="/b")
    r = subprocess.run([sys.executable, str(REPO / "research" / "p3" / "storage.py"), "--shell"],
                       env={**os.environ, "TLOS_STORAGE_CONFIG": str(bad)}, capture_output=True, text=True)
    assert r.returncode == 3 and "STORAGE_CONFIG_ERROR" in r.stderr and r.stdout == ""


# ---------------------------------------------------------------- health


def _store(uuid=None, mount="/srv/project-data"):
    return storage.Storage(mount, f"{mount}/tlos-backups", uuid, "test")


def _by_check(findings):
    return {f["check"]: f for f in findings}


def test_health_reports_the_resolved_store_its_mount_its_uuid_and_its_target(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "device_problems", lambda store, root="/": [])  # tmp_path stands in for a separate disk
    m = tmp_path / "store"
    (m / "tlos-backups").mkdir(parents=True, mode=0o700)
    store = storage.Storage(str(m), str(m / "tlos-backups"), UUID, "t")
    monkeypatch.setattr(health.os.path, "ismount", lambda p: p == str(m))
    f = health.storage_findings(R(UUID), store)
    assert [x["check"] for x in f] == ["backup_storage", f"mount:{m}", f"mount_uuid:{m}", "backup_target_on_store"]
    assert {x["severity"] for x in f} == {health.INFO}
    monkeypatch.setattr(health.os.path, "ismount", lambda p: False)
    f = _by_check(health.storage_findings(R(UUID), store))
    assert f[f"mount:{m}"]["severity"] == health.CRITICAL and "backup_target_on_store" not in f


def test_a_store_without_a_uuid_is_critical_not_a_warning(tmp_path, monkeypatch):
    monkeypatch.setattr(health.os.path, "ismount", lambda p: True)
    m = tmp_path / "store"
    m.mkdir()
    f = _by_check(health.storage_findings(R(), storage.Storage(str(m), str(m / "b"), None, "t")))
    assert f[f"mount_uuid:{m}"]["severity"] == health.CRITICAL and "UNPROVEN" in f[f"mount_uuid:{m}"]["detail"]
    assert "backup_target_on_store" not in f


def test_a_configured_uuid_must_match_and_unknown_is_unproven(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "device_problems", lambda store, root="/": [])  # tmp_path stands in for a separate disk
    m = tmp_path / "store"
    m.mkdir()
    store = storage.Storage(str(m), str(m / "b"), UUID, "t")
    key = f"mount_uuid:{m}"
    monkeypatch.setattr(health.os.path, "ismount", lambda p: True)
    ok = _by_check(health.storage_findings(R(UUID.upper() + "\n"), store))
    assert ok[key]["severity"] == health.INFO and ok["backup_target_on_store"]["severity"] == health.INFO
    other = _by_check(health.storage_findings(R("1111-2222"), store))
    assert other[key]["severity"] == health.CRITICAL and "another filesystem" in other[key]["detail"]
    assert "backup_target_on_store" not in other
    for runner in (R(""), R(exc=FileNotFoundError("findmnt"))):
        f = _by_check(health.storage_findings(runner, store))
        assert f[key]["severity"] == health.CRITICAL and "UNPROVEN" in f[key]["detail"]
        assert "backup_target_on_store" not in f


def test_health_reports_a_target_off_the_store_as_critical(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "device_problems", lambda store, root="/": [])  # tmp_path stands in for a separate disk
    m, elsewhere = tmp_path / "store", tmp_path / "elsewhere"
    m.mkdir()
    elsewhere.mkdir()
    (m / "tlos-backups").symlink_to(elsewhere)
    monkeypatch.setattr(health.os.path, "ismount", lambda p: p == str(m))
    f = {x["check"]: x for x in health.storage_findings(R(UUID), storage.Storage(str(m), str(m / "tlos-backups"), UUID, "t"))}
    assert f["backup_target_on_store"]["severity"] == health.CRITICAL
    (m / "tlos-backups").unlink()
    (m / "tlos-backups").mkdir()
    f = {x["check"]: x for x in health.storage_findings(R(UUID), storage.Storage(str(m), str(m / "tlos-backups"), UUID, "t"))}
    assert f["backup_target_on_store"]["severity"] == health.INFO


def test_an_unusable_configuration_is_critical_in_the_standard_set(tmp_path, monkeypatch):
    monkeypatch.setenv("TLOS_STORAGE_CONFIG", str(_cfg(tmp_path, backup_mount="/", backup_target="/b")))
    run = lambda cmd: R("enabled")  # noqa: E731
    checks = {f["check"]: f for f in health.standard_findings(
        {"instances": []}, runner=run, verifier=None, lane=tmp_path, fp_lane_root=tmp_path)}
    assert checks["backup_storage"]["severity"] == health.CRITICAL
    assert checks["backup_recency"]["severity"] == health.CRITICAL
    assert not any(k.startswith("mount:/mnt/tlos-wdc") for k in checks)


def _store_env(monkeypatch, store: Path):
    monkeypatch.setenv("TLOS_BACKUP_MOUNT", str(store))
    monkeypatch.setenv("TLOS_BACKUP_TARGET", str(store / "tlos-backups"))
    monkeypatch.setenv("TLOS_BACKUP_MOUNT_UUID", UUID)


def test_recency_is_read_from_the_configured_target_only_when_the_store_is_proven(tmp_path, monkeypatch):
    store = tmp_path / "store"
    (store / "tlos-backups" / "20261029T220229Z").mkdir(parents=True)
    os.chmod(store / "tlos-backups", 0o700)
    (store / "tlos-backups" / "20261029T220229Z" / "BACKUP_RECORD.json").write_text("{}", encoding="utf-8")
    _store_env(monkeypatch, store)
    monkeypatch.setattr(storage, "device_problems", lambda s, root="/": [])
    monkeypatch.setattr(health.os.path, "ismount", lambda p: p == str(store))
    seen = []

    def verifier(path):
        seen.append(Path(path))
        return {"BACKUP_VERIFY": "PASS"}

    def run(cmd):
        return R(UUID) if cmd[0] == "findmnt" else R("enabled")
    findings = _by_check(health.standard_findings({"instances": []}, runner=run, verifier=verifier,
                                                  lane=tmp_path, fp_lane_root=tmp_path))
    assert seen and seen[0].parent == store / "tlos-backups"
    assert findings[f"mount:{store}"]["severity"] == health.INFO
    # The same sets on an unproven store (wrong UUID) are not measured at all.
    seen.clear()
    findings = _by_check(health.standard_findings({"instances": []}, runner=lambda cmd: R("ffff-0000"),
                                                  verifier=verifier, lane=tmp_path, fp_lane_root=tmp_path))
    assert not seen and findings["backup_recency"]["severity"] == health.CRITICAL
    assert "not measured" in findings["backup_recency"]["detail"]


# ---------------------------------------------------------------- backup wrapper, unit, snapshot


def _wrapper(env_extra: dict) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items()
           if k not in ("TLOS_BACKUP_MOUNT", "TLOS_BACKUP_TARGET", "TLOS_BACKUP_MOUNT_UUID", "TLOS_STORAGE_CONFIG")}
    env.update({"TLOS_PYTHON": sys.executable, **env_extra})
    return subprocess.run(["bash", str(REPO / "scripts" / "p3" / "scheduled_backup.sh")], env=env,
                          capture_output=True, text=True, timeout=60)


def test_the_wrapper_refuses_an_unusable_configuration(tmp_path):
    r = _wrapper({"TLOS_STORAGE_CONFIG": str(_cfg(tmp_path, backup_mount="/", backup_target="/b"))})
    assert r.returncode == 3 and "STORAGE_CONFIG_ERROR" in r.stderr and "BACKUP_REFUSED" in r.stderr
    r = _wrapper({"TLOS_STORAGE_CONFIG": str(tmp_path / "missing.json")})
    assert r.returncode == 3 and "no backup store configured" in r.stderr


def test_the_wrapper_refuses_an_unmounted_configured_store(tmp_path):
    store = tmp_path / "not-a-mount"
    store.mkdir()
    r = _wrapper({"TLOS_BACKUP_MOUNT": str(store), "TLOS_BACKUP_TARGET": str(store / "b"),
                  "TLOS_BACKUP_MOUNT_UUID": UUID, "TLOS_STORE_WAIT_S": "0"})
    assert r.returncode == 3 and f"STORAGE_PREFLIGHT_FAIL: {store} is not mounted" in r.stderr
    assert not (store / "b").exists()


def test_the_wrapper_refuses_a_different_filesystem_uuid():
    # /proc is a mountpoint in every Linux test environment; its UUID is never the configured one.
    if subprocess.run(["mountpoint", "-q", "/proc"]).returncode != 0:
        pytest.skip("/proc is not a mountpoint here")
    r = _wrapper({"TLOS_BACKUP_MOUNT": "/proc", "TLOS_BACKUP_TARGET": "/proc/tlos-backups",
                  "TLOS_BACKUP_MOUNT_UUID": UUID, "TLOS_STORE_WAIT_S": "0"})
    assert r.returncode == 3 and "not the configured" in r.stderr and "BACKUP_REFUSED" in r.stderr


def test_no_consumer_hard_codes_the_old_store():
    for rel in ("research/p3/health.py", "research/p3/control_room.py", "scripts/p3/recovery.py",
                "scripts/p3/scheduled_backup.sh", "scripts/p3/health_check.py",
                "scripts/p3/units/tlos-p3-backup.service"):
        assert "/mnt/tlos-wdc" not in (REPO / rel).read_text(encoding="utf-8"), rel


def test_the_reboot_snapshot_records_the_configured_store(tmp_path, monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location("p3_recovery_cli", REPO / "scripts" / "p3" / "recovery.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setenv("TLOS_BACKUP_MOUNT", "/srv/project-data")
    monkeypatch.setenv("TLOS_BACKUP_TARGET", "/srv/project-data/tlos-backups")
    monkeypatch.setenv("TLOS_BACKUP_MOUNT_UUID", UUID)
    assert mod._mounts() == ("/", "/srv/project-data")
    monkeypatch.setenv("TLOS_BACKUP_MOUNT", "/")
    monkeypatch.setenv("TLOS_BACKUP_TARGET", "/b")
    with pytest.raises(storage.StorageConfigError):
        mod._mounts()


def test_the_control_room_has_no_fallback_store(tmp_path, monkeypatch):
    from p3 import control_room as cr
    monkeypatch.setenv("TLOS_STORAGE_CONFIG", str(_cfg(tmp_path, backup_mount="/", backup_target="/b", mount_uuid=UUID)))
    assert cr._store_target() is None
    _store_env(monkeypatch, tmp_path / "store")
    assert cr._store_target() == tmp_path / "store" / "tlos-backups"


def test_a_store_on_the_system_disk_is_refused(tmp_path):
    m = tmp_path / "store"
    m.mkdir()
    store = storage.Storage(str(m), str(m / "b"), None, "t")
    assert "same filesystem" in storage.device_problems(store, root=str(tmp_path))[0]


@needs_proc
def test_a_separate_filesystem_is_not_the_system_disk():
    assert storage.device_problems(storage.Storage("/proc", "/proc/x/b", None, "t")) == []


def test_a_store_reachable_by_others_is_a_warning(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "device_problems", lambda store, root="/": [])
    monkeypatch.setattr(health.os.path, "ismount", lambda p: True)
    m = tmp_path / "store"
    (m / "b").mkdir(parents=True)
    os.chmod(m / "b", 0o755)
    store = storage.Storage(str(m), str(m / "b"), UUID, "t")
    f = _by_check(health.storage_findings(R(UUID), store))
    assert f["backup_store_permissions"]["severity"] == health.WARNING and "0o755" in f["backup_store_permissions"]["detail"]
    os.chmod(m / "b", 0o700)
    assert "backup_store_permissions" not in _by_check(health.storage_findings(R(UUID), store))


def test_the_backup_wrapper_and_unit_create_owner_only_files():
    assert "\numask 077" in (REPO / "scripts/p3/scheduled_backup.sh").read_text(encoding="utf-8")
    assert "\nUMask=0077\n" in (REPO / "scripts/p3/units/tlos-p3-backup.service").read_text(encoding="utf-8")


def test_the_wrapper_waits_for_a_late_mount_but_not_for_other_failures(tmp_path):
    store = tmp_path / "late"
    store.mkdir()
    env = {"TLOS_BACKUP_MOUNT": str(store), "TLOS_BACKUP_TARGET": str(store / "b"), "TLOS_BACKUP_MOUNT_UUID": UUID,
           "TLOS_STORE_WAIT_S": "12"}
    import time
    t0 = time.time()
    r = _wrapper(env)
    assert r.returncode == 3 and r.stderr.count("is not mounted") >= 2 and time.time() - t0 >= 10
    t0 = time.time()
    r = _wrapper({**env, "TLOS_BACKUP_MOUNT_UUID": "not a uuid"})
    assert r.returncode == 3 and "STORAGE_CONFIG_ERROR" in r.stderr and time.time() - t0 < 10
