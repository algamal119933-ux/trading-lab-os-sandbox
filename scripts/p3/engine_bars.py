#!/usr/bin/env python3
"""P3-PLN-07 G-3: record the engine's closed bars through the read-only Freqtrade API (research/p3/engine_bars.py).

    scripts/p3/engine_bars.py --api http://127.0.0.1:8080 --pair BTC/USDT --pair ETH/USDT --timeframe 1h \\
        --out ~/tlos-paper/p3-evidence/engine-bars/<run_id>.jsonl

One cycle per call (schedule it only inside an authorized window). Credentials, if the API needs them, are read from
the environment variables named by --user-env / --password-env and never printed. Only GET on pair_candles is
issued. The output must lie outside every evidence lane and runtime tree. Exit codes: 0 recorded (PASS) · 2 UNPROVEN
or error (nothing written). Compare with: scripts/p3/data_truth.py feed-compare --engine-recording <out>.
PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for _extra in (str(REPO_ROOT / "research"), str(REPO_ROOT / "scripts")):
    if _extra not in sys.path:
        sys.path.insert(0, _extra)

from p3 import engine_bars  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api", required=True, help="Freqtrade API base, e.g. http://127.0.0.1:8080")
    parser.add_argument("--pair", action="append", dest="pairs", required=True)
    parser.add_argument("--timeframe", required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--user-env", default="FREQTRADE__API_SERVER__USERNAME")
    parser.add_argument("--password-env", default="FREQTRADE__API_SERVER__PASSWORD")
    args = parser.parse_args(argv)
    fetch = engine_bars.http_fetch(os.environ.get(args.user_env), os.environ.get(args.password_env))
    try:
        report = engine_bars.record_cycle(args.api, pairs=args.pairs, timeframe=args.timeframe, out=args.out,
                                          fetch=fetch, limit=args.limit)
    except engine_bars.RecorderError as exc:
        print(f"P3_ENGINE_BARS_REFUSED: {exc}", file=sys.stderr)
        return 2
    print(f"P3_ENGINE_BARS = {report['result']} · {report['detail']}")
    return 0 if report["result"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
