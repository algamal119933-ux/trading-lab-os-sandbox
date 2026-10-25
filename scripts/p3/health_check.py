#!/usr/bin/env python3
"""P3-PLN-06 operational health check (master plan §19 severities). Read-only.

    scripts/p3/health_check.py [--root-min-gib 20] [--lane /home/hamza/tlos-paper/h1-paper-cohort-1]
        [--backup-target /mnt/tlos-wdc/tlos-backups] [--rpo-hours 26] [--json out.json]

Exit codes: 0 all INFO · 1 any WARNING · 2 any CRITICAL.
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

from p3 import backup, health  # noqa: E402

REGISTRY = REPO_ROOT / "research" / "fp" / "records" / "forward_paper_cohort_registry.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root-min-gib", type=float, default=20.0)
    parser.add_argument("--lane", type=Path, default=Path("/home/hamza/tlos-paper/h1-paper-cohort-1"))
    parser.add_argument("--lane-min-gib", type=float, default=20.0)
    parser.add_argument("--backup-target", type=Path, default=Path("/mnt/tlos-wdc/tlos-backups"))
    parser.add_argument("--rpo-hours", type=float, default=26.0)
    parser.add_argument("--fp-lane-root", type=Path,
                        default=Path("/home/hamza/projects/trading/trading_lab_os_final/freqtrade/user_data"))
    parser.add_argument("--json", type=Path)
    parser.add_argument("--prom-textfile", type=Path, help="also write Prometheus text exposition, atomically")
    args = parser.parse_args(argv)
    run = health.default_runner
    findings = [
        health.free_space(Path("/"), args.root_min_gib, "root"),
        health.free_space(args.lane, args.lane_min_gib, "h1_lane"),
        health.mounted("/mnt/tlos-wdc"),
        health.backup_recency(args.backup_target, args.rpo_hours, verifier=backup.verify_backup),
        health.timer_expected("tlos-p3-backup.timer", want_active=True, runner=run),
        health.timer_expected("tlos-p2-window-fp-control-3.timer", want_active=False, runner=run),
        *health.normal_end_due(json.loads(REGISTRY.read_text(encoding="utf-8")), args.fp_lane_root),
    ]
    verdict = health.overall(findings)
    if args.json:
        args.json.write_text(json.dumps({"findings": findings, "HEALTH": verdict}, indent=2) + "\n", encoding="utf-8")
    if args.prom_textfile:
        health.write_textfile(findings, args.prom_textfile)
    for f in findings:
        print(f"  {f['severity']:8} {f['check']:42} {f['detail']}")
    print(f"HEALTH = {verdict}")
    return {health.INFO: 0, health.WARNING: 1, health.CRITICAL: 2}[verdict]


if __name__ == "__main__":
    raise SystemExit(main())
