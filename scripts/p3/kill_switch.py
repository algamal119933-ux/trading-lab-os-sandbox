#!/usr/bin/env python3
"""P3-PLN-08 kill switch: stop every paper runtime (FP cohorts and H1) and record who did it, and why.

    scripts/p3/kill_switch.py --reason "<why>" [--operator NAME] [--dry-run] [--ledger PATH]
    scripts/p3/kill_switch.py --verify-ledger [--ledger PATH]

Matches only containers named tradinglab-fp-control-* or tlos-h1-paper-cohort-*. It uses
`docker stop` and nothing destructive, so lanes and evidence are untouched. Every invocation appends a
hash-chained record to the operator ledger (default $TLOS_OPERATOR_LEDGER, else
/home/hamza/tlos-paper/operator-ledger/operator_ledger.jsonl).
Exit codes: 0 stopped / nothing running / dry run · 1 stop incomplete · 2 error or refused.
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

from p3 import kill_switch  # noqa: E402

DEFAULT_LEDGER = Path(os.environ.get("TLOS_OPERATOR_LEDGER",
                                     "/home/hamza/tlos-paper/operator-ledger/operator_ledger.jsonl"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reason")
    parser.add_argument("--operator")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--timeout", type=int, default=kill_switch.DEFAULT_TIMEOUT_S)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--verify-ledger", action="store_true")
    args = parser.parse_args(argv)
    if args.verify_ledger:
        problems = kill_switch.verify_ledger(args.ledger)
        print("OPERATOR_LEDGER = " + ("PASS" if not problems else f"FAIL {problems}"))
        return 0 if not problems else 2
    try:
        record = kill_switch.engage(reason=args.reason or "", ledger=args.ledger, operator=args.operator,
                                    dry_run=args.dry_run, timeout_s=args.timeout)
    except kill_switch.KillSwitchError as exc:
        print(f"KILL_SWITCH_REFUSED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({k: record[k] for k in ("utc", "operator", "reason", "targets", "still_running",
                                             "elapsed_s", "outcome", "seq", "digest")}, indent=2))
    print(f"KILL_SWITCH = {record['outcome']}")
    return 1 if record["outcome"] == "STOP_INCOMPLETE" else 0


if __name__ == "__main__":
    raise SystemExit(main())
