#!/usr/bin/env python3
"""Passive benchmarks for Trading Lab OS — OOS-safe version.

Default behavior exposes DEVELOPMENT only.

Copy to:
C:/trading_lab_os_v1/freqtrade/user_data/baseline_benchmarks.py

Development:
docker compose run --rm --entrypoint python freqtrade /freqtrade/user_data/baseline_benchmarks.py

Validation, only after active-strategy logic is frozen:
docker compose run --rm --entrypoint python freqtrade /freqtrade/user_data/baseline_benchmarks.py --period validation

Locked OOS, only at the final OOS gate:
docker compose run --rm --entrypoint python freqtrade /freqtrade/user_data/baseline_benchmarks.py --period oos --unlock-oos

Benchmarks:
1) BTC buy-and-hold.
2) ETH buy-and-hold.
3) Fully-invested 50/50 BTC+ETH on a 100 USDT wallet.
4) Exposure-matched passive: 10 USDT BTC + 10 USDT ETH + 80 USDT cash.

Default fee assumption: 0.1% per side, explicitly reported.
"""

from __future__ import annotations

from pathlib import Path
import argparse
import json
import sys
import pandas as pd

BASE = Path("/freqtrade/user_data/data/binance")
OUT = Path("/freqtrade/user_data/baseline_v1_passive_benchmarks.json")

PERIODS = {
    "development": ("2025-09-01T00:00:00Z", "2026-04-30T23:59:59Z"),
    "validation": ("2026-05-01T00:00:00Z", "2026-06-30T23:59:59Z"),
    "oos": ("2026-07-01T00:00:00Z", "2026-09-06T17:00:00Z"),
}


def find_1h(pair: str) -> Path:
    token = pair.replace("/", "_")
    exact = BASE / f"{token}-1h.feather"
    if exact.exists():
        return exact
    candidates = list(BASE.glob(f"{token}-1h*.feather"))
    if len(candidates) != 1:
        raise RuntimeError(
            f"Cannot uniquely resolve 1h file for {pair}: "
            f"{[p.name for p in candidates]}"
        )
    return candidates[0]


def load(pair: str) -> pd.DataFrame:
    df = pd.read_feather(find_1h(pair))
    df["date"] = pd.to_datetime(df["date"], utc=True)
    return df.sort_values("date")


def period_return(df: pd.DataFrame, start: str, end: str, fee: float) -> dict:
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    x = df[(df["date"] >= start_ts) & (df["date"] <= end_ts)]
    if x.empty:
        raise RuntimeError(f"No rows in period {start} -> {end}")

    p0 = float(x.iloc[0]["close"])
    p1 = float(x.iloc[-1]["close"])

    gross_return = p1 / p0 - 1.0
    net_factor = (1.0 - fee) * (p1 / p0) * (1.0 - fee)
    net_return = net_factor - 1.0

    return {
        "start_candle": x.iloc[0]["date"].isoformat(),
        "end_candle": x.iloc[-1]["date"].isoformat(),
        "start_close": p0,
        "end_close": p1,
        "gross_return": gross_return,
        "net_return_after_entry_and_exit_fee": net_return,
    }


def compute_period(name: str, btc: pd.DataFrame, eth: pd.DataFrame, fee: float) -> dict:
    start, end = PERIODS[name]
    btc_r = period_return(btc, start, end, fee)
    eth_r = period_return(eth, start, end, fee)

    full_final = (
        50.0 * (1.0 + btc_r["net_return_after_entry_and_exit_fee"])
        + 50.0 * (1.0 + eth_r["net_return_after_entry_and_exit_fee"])
    )
    exposure_final = (
        80.0
        + 10.0 * (1.0 + btc_r["net_return_after_entry_and_exit_fee"])
        + 10.0 * (1.0 + eth_r["net_return_after_entry_and_exit_fee"])
    )

    return {
        "period": name,
        "BTC": btc_r,
        "ETH": eth_r,
        "full_50_50_wallet_start": 100.0,
        "full_50_50_wallet_end": full_final,
        "full_50_50_return": full_final / 100.0 - 1.0,
        "exposure_matched_wallet_start": 100.0,
        "exposure_matched_wallet_end": exposure_final,
        "exposure_matched_return": exposure_final / 100.0 - 1.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--period",
        choices=["development", "validation", "oos"],
        default="development",
    )
    parser.add_argument(
        "--unlock-oos",
        action="store_true",
        help="Required to expose locked OOS benchmark results.",
    )
    parser.add_argument(
        "--fee",
        type=float,
        default=0.001,
        help="Fee ratio per side. Default 0.001 = 0.1%%.",
    )
    args = parser.parse_args()

    if args.period == "oos" and not args.unlock_oos:
        print("OOS_LOCKED: refusing to expose locked OOS benchmark.")
        print("Use --period oos --unlock-oos only at the final OOS gate.")
        return 3

    btc = load("BTC/USDT")
    eth = load("ETH/USDT")
    result = compute_period(args.period, btc, eth, args.fee)

    # Preserve only the explicitly requested period in this run's report.
    report = {
        "fee_per_side": args.fee,
        "requested_period": args.period,
        "result": result,
    }
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("=" * 76)
    print("TRADING LAB OS - PASSIVE BENCHMARK")
    print(f"Period: {args.period.upper()}")
    print(f"Fee assumption per side: {args.fee:.4%}")
    print("=" * 76)
    print(
        "BTC net B&H:      "
        f"{result['BTC']['net_return_after_entry_and_exit_fee']:.2%}"
    )
    print(
        "ETH net B&H:      "
        f"{result['ETH']['net_return_after_entry_and_exit_fee']:.2%}"
    )
    print(f"Full 50/50:       {result['full_50_50_return']:.2%}")
    print(f"Exposure-matched: {result['exposure_matched_return']:.2%}")
    print("Report:", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
