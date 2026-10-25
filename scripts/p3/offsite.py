#!/usr/bin/env python3
"""P3-PLN-05: push a verified backup set to an independent target and verify it on the destination.

    scripts/p3/offsite.py --set /mnt/tlos-wdc/tlos-backups/<stamp> --dest user@host:/srv/tlos-offsite
    scripts/p3/offsite.py --set <set> --dest /path/on/another/device      (local path: NOT host-loss redundancy)

Append-only; it re-verifies an existing copy and never overwrites one. Exit codes: 0 PASS · 1 FAIL · 2 error.
PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for _extra in (str(REPO_ROOT / "research"), str(REPO_ROOT / "scripts")):
    if _extra not in sys.path:
        sys.path.insert(0, _extra)

from p3 import backup, offsite  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--set", required=True, type=Path, dest="set_dir")
    parser.add_argument("--dest", required=True)
    args = parser.parse_args(argv)
    try:
        report = offsite.push(args.set_dir, args.dest)
    except (offsite.OffsiteError, backup.BackupError, OSError, json.JSONDecodeError) as exc:
        print(f"P3_OFFSITE_ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return 0 if report["destination_verify"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
