#!/usr/bin/env python3
"""P3-PLN-04: terminal-state restart guard (F-5) and the reboot check.

    scripts/p3/recovery.py may-restart --role FP-CONTROL-3
    scripts/p3/recovery.py authorize-resume --role R --operator NAME --reason "<why>"
    scripts/p3/recovery.py snapshot --out pre_reboot.json
    scripts/p3/recovery.py verify-boot --before pre_reboot.json [--json out.json]

`may-restart` exits 0 if allowed and 3 if refused, so automation can gate on it. `snapshot` and
`verify-boot` are read-only. `authorize-resume` appends one attributable operator-ledger record.
PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for _extra in (str(REPO_ROOT / "research"), str(REPO_ROOT / "scripts")):
    if _extra not in sys.path:
        sys.path.insert(0, _extra)

from p3 import kill_switch, recovery, storage  # noqa: E402

REGISTRY = REPO_ROOT / "research" / "fp" / "records" / "forward_paper_cohort_registry.json"
LEDGER = Path(os.environ.get("TLOS_OPERATOR_LEDGER", "/home/hamza/tlos-paper/operator-ledger/operator_ledger.jsonl"))
def _mounts() -> tuple[str, ...]:
    """The root filesystem and the configured backup store (p3.storage). An unusable storage
    configuration is an error here, not a silent default: a snapshot must record the real store."""
    return ("/", storage.load().backup_mount)
UNITS = ("tlos-p3-backup.timer", "tlos-p2-window-fp-control-3.timer")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    mr = sub.add_parser("may-restart")
    mr.add_argument("--role", required=True)
    ar = sub.add_parser("authorize-resume")
    ar.add_argument("--role", required=True)
    ar.add_argument("--operator", required=True)
    ar.add_argument("--reason", required=True)
    sn = sub.add_parser("snapshot")
    sn.add_argument("--out", required=True, type=Path)
    vb = sub.add_parser("verify-boot")
    vb.add_argument("--before", required=True, type=Path)
    vb.add_argument("--json", type=Path)
    for p in (mr, ar):
        p.add_argument("--ledger", type=Path, default=LEDGER)
    args = parser.parse_args(argv)
    try:
        if args.command == "may-restart":
            ok, why = recovery.may_restart(args.role, json.loads(REGISTRY.read_text(encoding="utf-8")), args.ledger)
            print(f"MAY_RESTART = {'YES' if ok else 'NO'} — {why}")
            return 0 if ok else 3
        if args.command == "authorize-resume":
            record = recovery.authorize_resume(args.role, reason=args.reason, operator=args.operator, ledger=args.ledger)
            print(f"RESUME_AUTHORIZED {args.role} seq {record['seq']} digest {record['digest'][:16]}")
            return 0
        if args.command == "snapshot":
            snap = recovery.snapshot(_mounts(), UNITS)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(snap, indent=2) + "\n", encoding="utf-8")
            print(f"SNAPSHOT boot_id {snap['boot_id'][:8]} · {len(snap['containers'])} containers → {args.out}")
            return 0
        before = json.loads(args.before.read_text(encoding="utf-8"))
        report = recovery.verify_after_boot(before, recovery.snapshot(_mounts(), UNITS))
    except (kill_switch.KillSwitchError, storage.StorageConfigError, OSError, json.JSONDecodeError) as exc:
        print(f"P3_RECOVERY_ERROR: {exc}", file=sys.stderr)
        return 2
    if args.json:
        args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for name, check in report["checks"].items():
        print(f"  {name:48} {check['status']}  {check['detail']}")
    print(f"PLN_04_REBOOT_CHECK = {report['PLN_04_REBOOT_CHECK']}")
    return 0 if report["PLN_04_REBOOT_CHECK"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
