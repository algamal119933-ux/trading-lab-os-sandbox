#!/usr/bin/env python3
"""Passive benchmarks for Trading Lab OS — OOS-safe.

Default behaviour exposes DEVELOPMENT only. The development window is strongly
bearish, so an active long-only strategy can look strong merely by sitting in
cash. Compare against the exposure-matched line, not only against buy-and-hold.

Run inside the Freqtrade container (paths default to the container layout):
  docker compose run --rm --entrypoint python freqtrade \
      /freqtrade/user_data/baseline_benchmarks.py

Run on a host checkout by pointing at the data directory:
  python3 freqtrade/user_data/baseline_benchmarks.py \
      --data-dir freqtrade/user_data/data/binance \
      --out freqtrade/user_data/baseline_v1_passive_benchmarks.json

Validation, only after the active-strategy logic is frozen:
  ... --period validation

Locked OOS, only at the final OOS gate:
  ... --period oos --unlock-oos

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
import pandas as pd

DEFAULT_DATA_DIR = Path("/freqtrade/user_data/data/binance")
DEFAULT_OUT = Path("/freqtrade/user_data/baseline_v1_passive_benchmarks.json")

# Dataset V1 windows, kept so V1 results stay reproducible without a lock file.
PERIODS_V1 = {
    "development": ("2025-09-01T00:00:00Z", "2026-04-30T23:59:59Z"),
    "validation": ("2026-05-01T00:00:00Z", "2026-06-30T23:59:59Z"),
    "oos": ("2026-07-01T00:00:00Z", "2026-09-06T17:00:00Z"),
}


def periods_from_lock(lock_path: Path) -> dict[str, tuple[str, str]]:
    """Read protocol windows from a dataset lock so the benchmark and the
    backtest can never disagree about which dates a window covers."""
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    windows = lock.get("protocol_windows") or {}
    out: dict[str, tuple[str, str]] = {}
    for name, spec in windows.items():
        if name == "warmup":
            continue  # never scored
        out[name] = (spec["start_utc"], spec["end_utc"])
    if not out:
        raise SystemExit(f"{lock_path} declares no scorable protocol windows")
    return out


def find_1h(pair: str, base: Path) -> Path:
    token = pair.replace("/", "_")
    exact = base / f"{token}-1h.feather"
    if exact.exists():
        return exact
    candidates = list(base.glob(f"{token}-1h*.feather"))
    if len(candidates) != 1:
        raise RuntimeError(
            f"Cannot uniquely resolve 1h file for {pair}: "
            f"{[p.name for p in candidates]}"
        )
    return candidates[0]


def load(pair: str, base: Path) -> pd.DataFrame:
    df = pd.read_feather(find_1h(pair, base))
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


def compute_period(
    name: str,
    btc: pd.DataFrame,
    eth: pd.DataFrame | None,
    fee: float,
    periods: dict[str, tuple[str, str]],
    wallet: float = 100.0,
    stake: float = 10.0,
    max_open_trades: int = 2,
) -> dict:
    """Passive controls for one protocol window.

    ``eth`` may be ``None`` for a single-asset universe. A BTC-specialist
    candidate must be compared against BTC's own buy-and-hold and BTC's own
    exposure-matched passive line: the frozen sprint is explicit that a combined
    BTC+ETH control is not a fair sole opponent for it. The two-asset path is
    untouched, so BASELINE-1's recorded numbers are reproduced bit-for-bit by the
    same code that produced them.
    """
    start, end = periods[name]
    btc_r = period_return(btc, start, end, fee)
    eth_r = period_return(eth, start, end, fee) if eth is not None else None

    legs = [btc_r] if eth_r is None else [btc_r, eth_r]
    share = wallet / len(legs)
    full_final = sum(share * (1.0 + leg["net_return_after_entry_and_exit_fee"]) for leg in legs)

    # Structural max-exposure-matched passive: the most capital the sizing rules
    # can ever have in the market (max_open_trades x stake), split evenly across
    # the pairs, with the remainder in cash. This is an upper bound on the
    # strategy's exposure, not its realised exposure -- the realised-exposure
    # comparison needs the backtest and is computed after it.
    invested = min(float(stake) * int(max_open_trades), wallet)
    per_pair = invested / len(legs)
    cash = wallet - invested
    exposure_final = cash + sum(
        per_pair * (1.0 + leg["net_return_after_entry_and_exit_fee"]) for leg in legs
    )

    return {
        "period": name,
        "window_start": start,
        "window_end": end,
        "universe": [leg["pair"] for leg in legs] if all("pair" in leg for leg in legs) else (
            ["BTC/USDT"] if eth_r is None else ["BTC/USDT", "ETH/USDT"]
        ),
        "BTC": btc_r,
        "ETH": eth_r,
        "full_50_50_wallet_start": wallet,
        "full_50_50_wallet_end": full_final,
        "full_50_50_return": full_final / wallet - 1.0,
        "max_exposure_matched_methodology": (
            f"{invested:.2f} of a {wallet:.2f} wallet invested for the whole window "
            f"({per_pair:.2f} each across {len(legs)} leg(s)), {cash:.2f} held in cash; "
            f"invested fraction {invested / wallet:.4f} = max_open_trades({max_open_trades}) "
            f"x stake({stake}) capped at the wallet"
        ),
        "max_exposure_invested_fraction": invested / wallet,
        "exposure_matched_wallet_start": wallet,
        "exposure_matched_wallet_end": exposure_final,
        "exposure_matched_return": exposure_final / wallet - 1.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--period",
        default="development",
        help="Protocol window to score. Names come from --lock when given.",
    )
    parser.add_argument(
        "--lock",
        default=None,
        help="Dataset lock defining the protocol windows. Defaults to the Dataset V1 windows.",
    )
    parser.add_argument(
        "--universe",
        choices=("btc-eth", "btc"),
        default="btc-eth",
        help=(
            "Which passive controls to compute. 'btc-eth' (default) is the two-asset "
            "line BASELINE-1 was scored against and is unchanged. 'btc' gives a "
            "BTC-specialist candidate its own buy-and-hold and exposure-matched "
            "passive, which the frozen sprint requires as a fair control."
        ),
    )
    parser.add_argument("--wallet", type=float, default=100.0)
    parser.add_argument("--stake", type=float, default=10.0)
    parser.add_argument("--max-open-trades", type=int, default=2)
    parser.add_argument(
        "--unlock-oos",
        action="store_true",
        help="Required to expose locked OOS benchmark results.",
    )
    parser.add_argument(
        "--data-dir",
        default=str(DEFAULT_DATA_DIR),
        help="Directory holding <PAIR>-1h.feather files. Defaults to the container path.",
    )
    parser.add_argument(
        "--out",
        default=str(DEFAULT_OUT),
        help="Where to write the JSON report.",
    )
    parser.add_argument(
        "--fee",
        type=float,
        default=0.001,
        help="Fee ratio per side. Default 0.001 = 0.1%%.",
    )
    args = parser.parse_args()

    periods = periods_from_lock(Path(args.lock)) if args.lock else dict(PERIODS_V1)
    if args.period not in periods:
        raise SystemExit(
            f"unknown period {args.period!r}; available: {', '.join(sorted(periods))}"
        )

    if args.period == "oos" and not args.unlock_oos:
        print("OOS_LOCKED: refusing to expose locked OOS benchmark.")
        print("Use --period oos --unlock-oos only at the final OOS gate.")
        return 3

    base = Path(args.data_dir)
    out = Path(args.out)
    btc = load("BTC/USDT", base)
    # A single-pair universe is a deliberate request, not a missing file: the
    # BTC-specialist lanes need BTC's own controls, and an ETH file that happens
    # to be absent must still be an error rather than a silent universe change.
    eth = None if args.universe == "btc" else load("ETH/USDT", base)
    result = compute_period(
        args.period,
        btc,
        eth,
        args.fee,
        periods,
        wallet=args.wallet,
        stake=args.stake,
        max_open_trades=args.max_open_trades,
    )

    # Preserve only the explicitly requested period in this run's report.
    report = {
        "fee_per_side": args.fee,
        "requested_period": args.period,
        "windows_source": args.lock or "built-in Dataset V1 windows",
        "result": result,
    }
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("=" * 76)
    print("TRADING LAB OS - PASSIVE BENCHMARK")
    print(f"Period: {args.period.upper()}")
    print(f"Fee assumption per side: {args.fee:.4%}")
    print("=" * 76)
    print(
        "BTC net B&H:      "
        f"{result['BTC']['net_return_after_entry_and_exit_fee']:.2%}"
    )
    if result["ETH"] is not None:
        print(
            "ETH net B&H:      "
            f"{result['ETH']['net_return_after_entry_and_exit_fee']:.2%}"
        )
    else:
        print("ETH net B&H:      n/a (single-asset universe)")
    label = "Full 50/50:      " if result["ETH"] is not None else "Fully invested:  "
    print(f"{label} {result['full_50_50_return']:.2%}")
    print(
        f"Max-exposure-matched ({result['max_exposure_invested_fraction']:.0%} invested): "
        f"{result['exposure_matched_return']:.2%}"
    )
    print("Report:", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
