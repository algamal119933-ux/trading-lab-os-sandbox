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
    parser.add_argument("--no-s19", action="store_true",
                        help="omit the master plan §19 CRITICAL checks (paper guard, real-money state, evidence chains, "
                             "paper runtime vs registry); for diagnosis only")
    args = parser.parse_args(argv)
    run = health.default_runner
    s19, s19_error = None, None
    if not args.no_s19:
        try:
            s19 = health.default_s19_inputs(REPO_ROOT)
        except Exception as exc:  # noqa: BLE001 - a §19 set that cannot be built is a failure, not an absence
            s19_error = f"§19 checks could not be prepared ({type(exc).__name__}: {str(exc)[:120]})"
    findings = health.standard_findings(
        json.loads(REGISTRY.read_text(encoding="utf-8")), runner=run, verifier=backup.verify_backup,
        root_min_gib=args.root_min_gib, lane=args.lane, lane_min_gib=args.lane_min_gib,
        backup_target=args.backup_target, rpo_hours=args.rpo_hours, fp_lane_root=args.fp_lane_root,
        s19=s19)
    if args.no_s19:
        findings.append({"check": "s19_checks", "severity": health.WARNING,
                         "detail": "§19 checks disabled by --no-s19 (diagnosis only); safety state UNPROVEN"})
    elif s19_error:
        findings.append({"check": "s19_checks", "severity": health.CRITICAL, "detail": s19_error})
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
