#!/usr/bin/env python3
"""P3-PLN-07 data-truth audits over recorded evidence (research/p3/data_truth.py).

    scripts/p3/data_truth.py ledger-bars  --evidence-dir <lane or sealed archive>/evidence \
        --pair BTC/USDT --pair ETH/USDT --timeframe 1h [--start ISO --end ISO] [--json out.json]
    scripts/p3/data_truth.py feed-compare --evidence-dir <...>/evidence --pair BTC/USDT --timeframe 1h \
        --engine-bars engine_bars.json [--start ISO --end ISO] [--json out.json]

``--engine-bars`` is a JSON list of ``{"ts", "open", "high", "low", "close", "volume"}`` rows recorded
from the engine's feed; this tool never fetches one. Read-only: a ``--json`` path inside the evidence
directory is refused. Exit codes: 0 PASS · 1 FAIL · 2 UNPROVEN or error.
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

import audit_data  # noqa: E402
from p3 import data_truth  # noqa: E402

EXIT = {data_truth.PASS: 0, data_truth.FAIL: 1, data_truth.UNPROVEN: 2}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("audit", choices=("ledger-bars", "feed-compare"))
    parser.add_argument("--evidence-dir", required=True, type=Path)
    parser.add_argument("--pair", action="append", dest="pairs", required=True)
    parser.add_argument("--timeframe", required=True)
    parser.add_argument("--start", help="window start, ISO-8601 UTC")
    parser.add_argument("--end", help="window end, ISO-8601 UTC")
    parser.add_argument("--engine-bars", type=Path)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args(argv)

    if args.json is not None:
        target, lane = args.json.resolve(), args.evidence_dir.resolve()
        if target == lane or lane in target.parents:
            print(f"P3_DATA_TRUTH_REFUSED: {args.json} is inside the evidence directory", file=sys.stderr)
            return 2
    try:
        start = audit_data.to_ms(args.start) if args.start else None
        end = audit_data.to_ms(args.end) if args.end else None
        if args.audit == "ledger-bars":
            report = data_truth.audit_input_ledger(args.evidence_dir, pairs=args.pairs, timeframe=args.timeframe,
                                                   start_ms=start, end_ms=end)
        else:
            if args.engine_bars is None or len(args.pairs) != 1:
                print("P3_DATA_TRUTH_ERROR: feed-compare needs exactly one --pair and --engine-bars", file=sys.stderr)
                return 2
            live = data_truth.live_rows_from_input_ledger(args.evidence_dir, args.pairs[0])
            engine = json.loads(args.engine_bars.read_text(encoding="utf-8"))
            report = data_truth.compare_feeds(live, engine, pair=args.pairs[0], timeframe=args.timeframe,
                                              start_ms=start, end_ms=end)
    except (data_truth.DataTruthError, OSError, ValueError) as exc:
        print(f"P3_DATA_TRUTH_UNPROVEN: {exc}", file=sys.stderr)
        return 2

    if args.json is not None:
        args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for item in report["findings"]:
        print(f"  [{item['result']:>8}] {item['check']}: {item['detail']}")
    print(f"P3_DATA_TRUTH {report['audit']} = {report['result']}")
    return EXIT[report["result"]]


if __name__ == "__main__":
    raise SystemExit(main())
