#!/usr/bin/env python3
"""P3-PLN-07: audit that every paper execution is backed by an admitted decision (P2 finding F-2).

    scripts/p3/execution_audit.py --evidence-dir <lane or sealed archive>/evidence [--json out.json]

Read-only. Exit codes: 0 PASS · 1 FAIL (an unbacked execution) · 2 error.
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

from p3 import execution_audit  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--evidence-dir", required=True, type=Path)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args(argv)
    try:
        report = execution_audit.audit(args.evidence_dir)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"P3_EXECUTION_AUDIT_ERROR: {exc}", file=sys.stderr)
        return 2
    if args.json:
        args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for e in report["executions"]:
        print(f"  trade {e['trade_id']} {e['pair']:9} {e['event']:16} {e['fill_utc']}  "
              f"{'BACKED' if e['backed'] else 'UNBACKED'}")
    print(f"EXECUTION_BACKED_BY_ADMITTED_DECISION = {report['EXECUTION_BACKED_BY_ADMITTED_DECISION']}")
    return 0 if report["EXECUTION_BACKED_BY_ADMITTED_DECISION"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
