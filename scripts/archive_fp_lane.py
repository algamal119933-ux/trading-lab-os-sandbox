#!/usr/bin/env python3
"""Archive a whole forward-paper lane out of container reach, and seal it.

    scripts/archive_fp_lane.py FP-CONTROL-2 --reason "L0 retained P1 qualification lane"
    scripts/archive_fp_lane.py FP-CONTROL-2 --name fp-control-2-L1-qualification
    scripts/archive_fp_lane.py FP-CONTROL-2 --check-empty

The whole lane moves — evidence, logs, ``tradesv3.sqlite``,
``capture_runtime.json``, the lock file and anything else in there. Archiving
only ``evidence/`` would carry pre-T0 wallet and position state into a post-T0
cohort through the database, which is precisely the cross-lane crediting the
contract forbids.

This is TIER 1, same-host archival. It may claim that lanes cannot be commingled
or cross-credited and that no running container can reach the archive. It may
not claim survival of host loss, disk failure, or this machine being
decommissioned — only a Tier-3 independent-host snapshot may claim that.

Exit codes: 0 archived (or the lane is empty, under ``--check-empty``);
2 refused.

PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for _extra in (str(REPO_ROOT / "research"), str(REPO_ROOT / "scripts")):
    if _extra not in sys.path:
        sys.path.insert(0, _extra)

from fp import archive as fp_archive  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("role", help="the registry role whose lane is to be archived")
    parser.add_argument("--name", default=None, help="archive directory name under artifacts/")
    parser.add_argument("--archive-root", default=None)
    parser.add_argument("--reason", default="", help="why this lane is being sealed")
    parser.add_argument(
        "--check-empty",
        action="store_true",
        help="report whether the lane is empty and change nothing; exit 2 if it is not",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.check_empty:
        empty, detail = fp_archive.lane_is_empty(args.role)
        print(f"LANE_EMPTY = {'YES' if empty else 'NO'} — {detail}")
        return 0 if empty else 2

    try:
        manifest = fp_archive.archive_lane(
            args.role,
            name=args.name,
            archive_root=Path(args.archive_root) if args.archive_root else None,
            reason=args.reason,
        )
    except fp_archive.ArchiveError as exc:
        print(f"ARCHIVE_REFUSED: {exc}", file=sys.stderr)
        return 2

    if args.json:
        sys.stdout.write(json.dumps(manifest, indent=2) + "\n")
    else:
        print(f"ARCHIVED {manifest['role']} → {manifest['archive_dir']}")
        print(f"  files          {manifest['file_count']} ({manifest['total_bytes']} bytes), each re-read and hashed")
        evidence = manifest["evidence"]
        if evidence["present"]:
            print(f"  counts         {evidence['counts']}")
            print(f"  pack digest    {evidence['daily_pack_digest']}")
            if evidence["chain_problems"]:
                print(f"  CHAIN PROBLEMS {evidence['chain_problems'][:3]}")
        else:
            print("  counts         no evidence directory in this lane")
        print(f"  lane           {manifest['source_lane']} is now empty")
        print()
        print(f"DURABILITY_TIER = 1")
        print(f"  {fp_archive.TIER1_DISCLAIMER}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
