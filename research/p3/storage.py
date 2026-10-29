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
3. the historical PLN-03 default (``/mnt/tlos-wdc``, ``/mnt/tlos-wdc/tlos-backups``).

Fail-closed: a config that exists but cannot be read or is invalid raises ``StorageConfigError``; it
never falls back to the default. The health check turns that into a CRITICAL finding.

Rules: absolute paths; the mount is never ``/`` (a backup on the system disk is not a separate store);
the target lies inside the mount; a UUID, when given, is a plain filesystem UUID string.

Read-only. PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

DEFAULT_MOUNT = "/mnt/tlos-wdc"
DEFAULT_TARGET = "/mnt/tlos-wdc/tlos-backups"
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
    source: str  # "default", "env", or the config file path

    @property
    def target(self) -> Path:
        return Path(self.backup_target)


def _validate(mount: object, target: object, uuid: object, source: str) -> Storage:
    if not isinstance(mount, str) or not isinstance(target, str):
        raise StorageConfigError(f"{source}: backup_mount and backup_target must be strings")
    m, t = PurePosixPath(mount), PurePosixPath(target)
    if not m.is_absolute() or not t.is_absolute():
        raise StorageConfigError(f"{source}: backup_mount and backup_target must be absolute paths")
    if ".." in m.parts or ".." in t.parts:
        raise StorageConfigError(f"{source}: '..' is not allowed in storage paths")
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
    explicit = config_path is not None or bool(env.get(CONFIG_ENV))
    if not path.exists():
        if explicit:
            raise StorageConfigError(f"{path}: configured storage file does not exist")
        return Storage(DEFAULT_MOUNT, DEFAULT_TARGET, None, "default")
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
    args = parser.parse_args(argv)
    try:
        s = load()
    except StorageConfigError as exc:
        print(f"STORAGE_CONFIG_ERROR: {exc}", file=__import__("sys").stderr)
        return 3
    if args.shell:
        print(shell_exports(s), end="")
    else:
        print(json.dumps({"backup_mount": s.backup_mount, "backup_target": s.backup_target,
                          "mount_uuid": s.mount_uuid, "source": s.source}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
