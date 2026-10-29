"""P3 backup storage location (research/p3/storage.py) and every consumer of it.

The store is configured once. An unusable configuration is never replaced by a default; the health
check reports it CRITICAL, the backup wrapper refuses to run, and the reboot snapshot errors.
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


def test_the_default_applies_only_when_nothing_is_configured(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DEFAULT_CONFIG", tmp_path / "absent.json")
    s = storage.load(env={})
    assert (s.backup_mount, s.backup_target, s.mount_uuid, s.source) == (
        "/mnt/tlos-wdc", "/mnt/tlos-wdc/tlos-backups", None, "default")


def test_a_config_file_moves_every_path_together(tmp_path):
    p = _cfg(tmp_path, backup_mount="/srv/project-data", backup_target="/srv/project-data/tlos-backups",
             mount_uuid=UUID)
    s = storage.load(env={}, config_path=p)
    assert (s.backup_mount, s.backup_target, s.mount_uuid, s.source) == (
        "/srv/project-data", "/srv/project-data/tlos-backups", UUID, str(p))
    assert s.target == Path("/srv/project-data/tlos-backups")


def test_the_config_env_variable_names_the_file(tmp_path):
    p = _cfg(tmp_path, backup_mount="/srv/x", backup_target="/srv/x/b")
    assert storage.load(env={"TLOS_STORAGE_CONFIG": str(p)}).backup_mount == "/srv/x"


def test_env_overrides_the_file_and_needs_both_paths(tmp_path):
    p = _cfg(tmp_path, backup_mount="/srv/x", backup_target="/srv/x/b")
    s = storage.load(env={"TLOS_BACKUP_MOUNT": "/srv/y", "TLOS_BACKUP_TARGET": "/srv/y/b"}, config_path=p)
    assert (s.backup_mount, s.source) == ("/srv/y", "env")
    for one in ({"TLOS_BACKUP_MOUNT": "/srv/y"}, {"TLOS_BACKUP_TARGET": "/srv/y/b"}):
        with pytest.raises(storage.StorageConfigError):
            storage.load(env=one, config_path=p)


@pytest.mark.parametrize("data, why", [
    ({"backup_mount": "/", "backup_target": "/tlos-backups"}, "system disk"),
    ({"backup_mount": "/srv/x", "backup_target": "/srv/other/b"}, "not inside"),
    ({"backup_mount": "srv/x", "backup_target": "srv/x/b"}, "absolute"),
    ({"backup_mount": "/srv/x", "backup_target": "/srv/x/../etc"}, "'..'"),
    ({"backup_mount": "/srv/x", "backup_target": "/srv/x/b", "mount_uuid": "x; rm -rf /"}, "UUID"),
    ({"backup_mount": "/srv/x", "backup_target": "/srv/x/b", "extra": 1}, "unknown keys"),
    ({"backup_mount": 5, "backup_target": "/srv/x/b"}, "strings"),
])
def test_an_invalid_file_is_refused_never_defaulted(tmp_path, data, why):
    with pytest.raises(storage.StorageConfigError, match=why):
        storage.load(env={}, config_path=_cfg(tmp_path, **data))


def test_an_unreadable_or_named_but_missing_file_is_refused(tmp_path):
    bad = tmp_path / "storage.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(storage.StorageConfigError, match="unreadable"):
        storage.load(env={}, config_path=bad)
    with pytest.raises(storage.StorageConfigError, match="does not exist"):
        storage.load(env={"TLOS_STORAGE_CONFIG": str(tmp_path / "missing.json")})
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


def test_a_quote_in_a_value_cannot_reach_the_shell():
    with pytest.raises(storage.StorageConfigError):
        storage.shell_exports(storage.Storage("/srv/a'b", "/srv/a'b/c", None, "x"))


def test_the_cli_exits_3_on_an_unusable_configuration(tmp_path):
    bad = _cfg(tmp_path, backup_mount="/", backup_target="/b")
    r = subprocess.run([sys.executable, str(REPO / "research" / "p3" / "storage.py"), "--shell"],
                       env={**os.environ, "TLOS_STORAGE_CONFIG": str(bad)}, capture_output=True, text=True)
    assert r.returncode == 3 and "STORAGE_CONFIG_ERROR" in r.stderr and r.stdout == ""


# ---------------------------------------------------------------- health


def _store(uuid=None, mount="/srv/project-data"):
    return storage.Storage(mount, f"{mount}/tlos-backups", uuid, "test")


def test_health_reports_the_resolved_store_and_its_mount(monkeypatch):
    monkeypatch.setattr(health.os.path, "ismount", lambda p: p == "/srv/project-data")
    f = health.storage_findings(R(), _store())
    assert [x["check"] for x in f] == ["backup_storage", "mount:/srv/project-data"]
    assert [x["severity"] for x in f] == [health.INFO, health.INFO]
    monkeypatch.setattr(health.os.path, "ismount", lambda p: False)
    assert health.storage_findings(R(), _store())[1]["severity"] == health.CRITICAL


def test_a_configured_uuid_must_match_and_unknown_is_unproven(monkeypatch):
    monkeypatch.setattr(health.os.path, "ismount", lambda p: True)
    ok = health.storage_findings(R(UUID.upper() + "\n"), _store(UUID))[-1]
    assert ok["check"] == "mount_uuid:/srv/project-data" and ok["severity"] == health.INFO
    other = health.storage_findings(R("1111-2222"), _store(UUID))[-1]
    assert other["severity"] == health.CRITICAL and "another filesystem" in other["detail"]
    for runner in (R(""), R(exc=FileNotFoundError("findmnt"))):
        f = health.storage_findings(runner, _store(UUID))[-1]
        assert f["severity"] == health.WARNING and "UNPROVEN" in f["detail"]


def test_an_unusable_configuration_is_critical_in_the_standard_set(tmp_path, monkeypatch):
    monkeypatch.setenv("TLOS_STORAGE_CONFIG", str(_cfg(tmp_path, backup_mount="/", backup_target="/b")))
    run = lambda cmd: R("enabled")  # noqa: E731
    checks = {f["check"]: f for f in health.standard_findings(
        {"instances": []}, runner=run, verifier=None, lane=tmp_path, fp_lane_root=tmp_path)}
    assert checks["backup_storage"]["severity"] == health.CRITICAL
    assert checks["backup_recency"]["severity"] == health.CRITICAL
    assert not any(k.startswith("mount:/mnt/tlos-wdc") for k in checks)


def test_recency_is_read_from_the_configured_target(tmp_path, monkeypatch):
    store = tmp_path / "store"
    (store / "tlos-backups" / "20261029T220229Z").mkdir(parents=True)
    (store / "tlos-backups" / "20261029T220229Z" / "BACKUP_RECORD.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("TLOS_BACKUP_MOUNT", str(store))
    monkeypatch.setenv("TLOS_BACKUP_TARGET", str(store / "tlos-backups"))
    seen = []

    def verifier(path):
        seen.append(Path(path))
        return {"BACKUP_VERIFY": "PASS"}

    findings = health.standard_findings({"instances": []}, runner=lambda cmd: R("enabled"), verifier=verifier,
                                        lane=tmp_path, fp_lane_root=tmp_path)
    assert seen and seen[0].parent == store / "tlos-backups"
    assert any(f["check"] == f"mount:{store}" for f in findings)


# ---------------------------------------------------------------- backup wrapper, unit, snapshot


def _wrapper(env_extra: dict) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items()
           if k not in ("TLOS_BACKUP_MOUNT", "TLOS_BACKUP_TARGET", "TLOS_BACKUP_MOUNT_UUID", "TLOS_STORAGE_CONFIG")}
    env.update({"TLOS_PYTHON": sys.executable, **env_extra})
    return subprocess.run(["bash", str(REPO / "scripts" / "p3" / "scheduled_backup.sh")], env=env,
                          capture_output=True, text=True, timeout=60)


def test_the_wrapper_refuses_an_unusable_configuration(tmp_path):
    r = _wrapper({"TLOS_STORAGE_CONFIG": str(_cfg(tmp_path, backup_mount="/", backup_target="/b"))})
    assert r.returncode == 3 and "BACKUP_REFUSED: backup storage configuration is unusable" in r.stderr


def test_the_wrapper_refuses_an_unmounted_configured_store(tmp_path):
    store = tmp_path / "not-a-mount"
    store.mkdir()
    r = _wrapper({"TLOS_BACKUP_MOUNT": str(store), "TLOS_BACKUP_TARGET": str(store / "b")})
    assert r.returncode == 3 and f"BACKUP_REFUSED: {store} is not mounted" in r.stderr
    assert not (store / "b").exists()


def test_the_wrapper_refuses_a_different_filesystem_uuid():
    # /proc is a mountpoint in every Linux test environment; its UUID is never the configured one.
    if subprocess.run(["mountpoint", "-q", "/proc"]).returncode != 0:
        pytest.skip("/proc is not a mountpoint here")
    r = _wrapper({"TLOS_BACKUP_MOUNT": "/proc", "TLOS_BACKUP_TARGET": "/proc/tlos-backups",
                  "TLOS_BACKUP_MOUNT_UUID": UUID})
    assert r.returncode == 3 and "not the configured" in r.stderr


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
    assert mod._mounts() == ("/", "/srv/project-data")
    monkeypatch.setenv("TLOS_BACKUP_MOUNT", "/")
    monkeypatch.setenv("TLOS_BACKUP_TARGET", "/b")
    with pytest.raises(storage.StorageConfigError):
        mod._mounts()
