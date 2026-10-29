"""P3 backup storage location: one governed source for the backup mount and target.

PLN-03 wrote its sets to a WDC store mounted at ``/mnt/tlos-wdc``. That path was hard-coded in the
scheduled backup, the health check, the Control Room, the reboot snapshot and the backup unit. When
the host's backup store moves (the Owner-reported 2026-10-29 migration put it on an internal HDD),
every one of those places must move together, or health reports a store that no longer exists while
backups land somewhere unchecked.

Resolution order, first match wins:
1. environment: ``TLOS_BACKUP_MOUNT`` and ``TLOS_BACKUP_TARGET`` (both, or neither), optional
   ``TLOS_BACKUP_MOUNT_UUID``;
2. a host-local JSON file: ``$TLOS_STORAGE_CONFIG`` or ``~/.config/tlos-p3/storage.json``
   ``{"backup_mount": "...", "backup_target": "...", "mount_uuid": "..."}`` (``mount_uuid`` optional);
There is no implicit default. The historical PLN-03 store (``/mnt/tlos-wdc``) is only a documented
legacy value: falling back to it silently would let a stale or re-mounted legacy disk receive backups.
Nothing configured, or a configuration that cannot be read or is invalid, raises ``StorageConfigError``;
the health check turns that into a CRITICAL finding and the backup wrapper refuses to run.

Rules: absolute, normalised paths (no ``..``, no ``.``, no ``//``); the mount is never ``/`` (a backup on
the system disk is not a separate store); the target lies inside the mount; a UUID, when given, is a
plain filesystem UUID string.

``preflight`` checks the live host before anything is written: the mount is a real mountpoint and not a
symlink; the filesystem UUID matches when configured; and the target (or its deepest existing parent)
resolves inside the mount on the mount's own device, so a symlink or a nested mount cannot redirect a
backup set to another disk.

Read-only. PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import json
import os
import posixpath
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

LEGACY_MOUNT = "/mnt/tlos-wdc"  # documented PLN-03 history only; never resolved implicitly
LEGACY_TARGET = "/mnt/tlos-wdc/tlos-backups"
DEFAULT_TARGET = LEGACY_TARGET  # import-time placeholder for static consumers (see control_room)
CONFIG_ENV = "TLOS_STORAGE_CONFIG"
DEFAULT_CONFIG = Path.home() / ".config" / "tlos-p3" / "storage.json"
_UUID = re.compile(r"^[0-9A-Fa-f][0-9A-Fa-f-]{3,63}$")


class StorageConfigError(ValueError):
    """The backup storage location is configured but unusable. Never silently defaulted."""


@dataclass(frozen=True)
class Storage:
    backup_mount: str
    backup_target: str
    mount_uuid: str | None
    source: str  # "env" or the config file path

    @property
    def target(self) -> Path:
        return Path(self.backup_target)


def _validate(mount: object, target: object, uuid: object, source: str) -> Storage:
    if not isinstance(mount, str) or not isinstance(target, str):
        raise StorageConfigError(f"{source}: backup_mount and backup_target must be strings")
    for v in (mount, target):
        if not v.startswith("/"):
            raise StorageConfigError(f"{source}: backup_mount and backup_target must be absolute paths")
        if ".." in v.split("/"):
            raise StorageConfigError(f"{source}: '..' is not allowed in storage paths")
        if v.startswith("//") or posixpath.normpath(v) != (v.rstrip("/") or "/"):
            raise StorageConfigError(f"{source}: {v!r} is not a normalised path")
        if any(c in v for c in "\n\r\t\0'\"$`\\"):
            raise StorageConfigError(f"{source}: storage paths must not contain quotes, '$', '`', '\\' or control characters")
    m, t = PurePosixPath(mount), PurePosixPath(target)
    if str(m) == "/":
        raise StorageConfigError(f"{source}: backup_mount '/' is the system disk, not a separate store")
    if t != m and m not in t.parents:
        raise StorageConfigError(f"{source}: backup_target {t} is not inside backup_mount {m}")
    if uuid is not None and (not isinstance(uuid, str) or not _UUID.match(uuid)):
        raise StorageConfigError(f"{source}: mount_uuid must be a filesystem UUID string")
    return Storage(str(m), str(t), uuid or None, source)


def load(env: dict | None = None, config_path: Path | None = None) -> Storage:
    """Resolve the backup storage location (see the module docstring for the order and rules)."""
    env = os.environ if env is None else env
    em, et = env.get("TLOS_BACKUP_MOUNT"), env.get("TLOS_BACKUP_TARGET")
    if em or et:
        if not (em and et):
            raise StorageConfigError("env: TLOS_BACKUP_MOUNT and TLOS_BACKUP_TARGET must be set together")
        return _validate(em, et, env.get("TLOS_BACKUP_MOUNT_UUID") or None, "env")
    path = Path(config_path) if config_path is not None else Path(env.get(CONFIG_ENV) or DEFAULT_CONFIG)
    if not path.exists():
        raise StorageConfigError(f"no backup store configured: {path} does not exist and TLOS_BACKUP_MOUNT/"
                                 f"TLOS_BACKUP_TARGET are unset (see docs/p3/PLN_03_BACKUP_RESTORE.md)")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StorageConfigError(f"{path}: unreadable ({type(exc).__name__})") from exc
    if not isinstance(data, dict):
        raise StorageConfigError(f"{path}: must be a JSON object")
    unknown = set(data) - {"backup_mount", "backup_target", "mount_uuid"}
    if unknown:
        raise StorageConfigError(f"{path}: unknown keys {sorted(unknown)}")
    return _validate(data.get("backup_mount"), data.get("backup_target"), data.get("mount_uuid"), str(path))


def _deepest_existing(path: str) -> str:
    p = path
    while not os.path.lexists(p):
        p = posixpath.dirname(p)
    return p


def preflight(store: Storage, runner=None) -> list[str]:
    """Live checks before a backup is written or a store is trusted. Returns problems; empty means OK.

    ``runner(cmd) -> stdout`` reads the filesystem UUID (default: ``findmnt``). Read-only."""
    m = store.backup_mount
    if os.path.islink(m):
        return [f"{m} is a symlink, not the store's mountpoint"]
    if not os.path.ismount(m):
        return [f"{m} is not mounted"]
    if store.mount_uuid:
        try:
            got = (runner or _findmnt_uuid)(["findmnt", "-no", "UUID", "--mountpoint", m]).strip()
        except Exception as exc:  # noqa: BLE001 - an identity that cannot be read is not proven
            return [f"UUID of {m} cannot be read ({type(exc).__name__})"]
        if got.lower() != store.mount_uuid.lower():
            return [f"{m} has UUID {got or '(none)'!r}, not the configured {store.mount_uuid}"]
    return target_problems(store)


def target_problems(store: Storage) -> list[str]:
    """The target, or its deepest existing parent, must resolve inside the mount on the mount's device,
    and an existing target must be a plain directory (not a symlink, not a file). Read-only."""
    problems: list[str] = []
    m = store.backup_mount
    probe = _deepest_existing(store.backup_target)
    real_m, real_p = os.path.realpath(m), os.path.realpath(probe)
    if real_p != real_m and not real_p.startswith(real_m.rstrip("/") + "/"):
        problems.append(f"{store.backup_target} resolves outside the store ({probe} -> {real_p})")
    elif os.stat(real_p).st_dev != os.stat(real_m).st_dev:
        problems.append(f"{store.backup_target} is on another filesystem than {m} (nested mount at or above {probe})")
    if os.path.lexists(store.backup_target) and (os.path.islink(store.backup_target)
                                                 or not os.path.isdir(store.backup_target)):
        problems.append(f"{store.backup_target} exists but is not a plain directory")
    return problems


def _findmnt_uuid(cmd: list[str]) -> str:
    import subprocess
    return subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False).stdout


def shell_exports(storage: Storage) -> str:
    """Lines a shell wrapper can ``eval``; values are single-quoted (validated paths hold no quote)."""
    def q(v: str) -> str:
        if "'" in v or "\n" in v:
            raise StorageConfigError("storage values must not contain quotes or newlines")
        return f"'{v}'"
    return "\n".join([f"TLOS_STORAGE_MOUNT={q(storage.backup_mount)}",
                      f"TLOS_STORAGE_TARGET={q(storage.backup_target)}",
                      f"TLOS_STORAGE_UUID={q(storage.mount_uuid or '')}",
                      f"TLOS_STORAGE_SOURCE={q(storage.source)}"]) + "\n"


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Print the resolved P3 backup storage location.")
    parser.add_argument("--shell", action="store_true", help="print shell assignments for a wrapper to eval")
    parser.add_argument("--preflight", action="store_true",
                        help="also check the live store (mounted, UUID, target on the store); exit 3 on any problem")
    args = parser.parse_args(argv)
    import sys
    try:
        s = load()
    except StorageConfigError as exc:
        print(f"STORAGE_CONFIG_ERROR: {exc}", file=sys.stderr)
        return 3
    if args.preflight:
        problems = preflight(s)
        if problems:
            for p in problems:
                print(f"STORAGE_PREFLIGHT_FAIL: {p}", file=sys.stderr)
            return 3
    if args.shell:
        print(shell_exports(s), end="")
    else:
        print(json.dumps({"backup_mount": s.backup_mount, "backup_target": s.backup_target,
                          "mount_uuid": s.mount_uuid, "source": s.source}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
