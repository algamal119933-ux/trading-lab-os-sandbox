#!/usr/bin/env python3
"""Normalise a Freqtrade backtest result into the CLOUD-0 metrics vocabulary.

Freqtrade's result JSON is rich but its key names drift between releases, and it
does not report the exposure figures this protocol needs. This script therefore:

* reads whatever the engine did report, trying several key spellings;
* derives time and capital exposure from the trade list itself;
* computes return per unit of exposure and a realised-exposure-matched passive
  comparison, which is the only fair yardstick for a long-only strategy that
  spends much of its life in cash.

Usage:
    python3 research/summarize_backtest.py --result backtest_results/x.zip \\
        --window-start 2021-01-01T00:00:00Z --window-end 2024-12-31T23:59:59Z \\
        --wallet 100 --fee 0.001 --passive passive_development.json \\
        --out metrics.json --md summary.md
    python3 research/summarize_backtest.py --result x.json --dump-schema
"""

from __future__ import annotations

import argparse
import json
import math
import zipfile
from datetime import datetime, timezone
from pathlib import Path


def parse_time(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        # Freqtrade exports milliseconds in some places, seconds in others.
        seconds = float(value) / 1000.0 if float(value) > 1e11 else float(value)
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    if isinstance(value, str):
        text = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def pick(source: dict, *names: str, default: object = None) -> object:
    for name in names:
        if name in source and source[name] is not None:
            return source[name]
    return default


def first_not_none(*values: object) -> object:
    """Explicit precedence, so a legitimate 0.0 is not treated as 'missing'."""
    for value in values:
        if value is not None:
            return value
    return None


def as_float(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return None if math.isnan(float(value)) or math.isinf(float(value)) else float(value)
    return None


def load_result(path: Path) -> dict:
    """Read a Freqtrade backtest result from either a plain JSON or a zip export.

    Freqtrade 2026.7 writes `backtest-result-<ts>.zip` next to a small
    `.meta.json`; the substantive result is a JSON member inside the archive.
    Older releases wrote the JSON directly. Accept both so the protocol does not
    depend on the engine's packaging choice.
    """
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            members = [
                name
                for name in archive.namelist()
                if name.endswith(".json") and not name.endswith(".meta.json")
            ]
            if not members:
                raise SystemExit(f"{path}: zip export contains no result JSON member")
            # A multi-strategy export can hold several; the largest is the result.
            member = max(members, key=lambda name: archive.getinfo(name).file_size)
            return json.loads(archive.read(member).decode("utf-8"))
    return json.loads(path.read_text(encoding="utf-8"))


def load_strategy_block(result: dict) -> tuple[str, dict]:
    strategies = result.get("strategy")
    if isinstance(strategies, dict) and strategies:
        name = sorted(strategies)[0]
        return name, strategies[name]
    # Some exports are already the single-strategy block.
    return str(result.get("strategy_name", "unknown")), result


def find_trades(block: dict, result: dict, explicit: Path | None) -> list[dict]:
    if explicit is not None:
        payload = json.loads(explicit.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload = payload.get("trades", payload.get("data", []))
        return list(payload or [])
    for candidate in (block.get("trades"), result.get("trades")):
        if isinstance(candidate, list):
            return candidate
    return []


def exposure_profile(
    trades: list[dict], window_start: datetime, window_end: datetime, wallet: float
) -> dict:
    """Time-weighted capital exposure derived from the trade list.

    Returns time in market, average and peak capital exposure. Average capital
    exposure is the fraction of the wallet that was actually at risk, integrated
    over the whole window - the number that makes a cash-heavy long-only result
    comparable with a passive one.
    """
    total_seconds = (window_end - window_start).total_seconds()
    empty = {
        "time_exposure_pct": 0.0,
        "avg_capital_exposure_pct": 0.0,
        "peak_capital_exposure_pct": 0.0,
        "peak_concurrent_trades": 0,
        "trades_with_usable_timestamps": 0,
    }
    if total_seconds <= 0 or not trades:
        return empty

    events: list[tuple[datetime, float, int]] = []
    usable = 0
    for trade in trades:
        opened = parse_time(pick(trade, "open_date", "open_timestamp", "open_date_utc"))
        closed = parse_time(pick(trade, "close_date", "close_timestamp", "close_date_utc"))
        stake = as_float(pick(trade, "stake_amount", "amount_stake", default=0.0)) or 0.0
        if opened is None:
            continue
        if closed is None or closed < opened:
            closed = window_end
        usable += 1
        events.append((max(opened, window_start), stake, 1))
        events.append((min(closed, window_end), -stake, -1))

    if not events:
        return empty

    events.sort(key=lambda item: item[0])
    open_stake = 0.0
    open_count = 0
    peak_stake = 0.0
    peak_count = 0
    stake_seconds = 0.0
    in_market_seconds = 0.0
    cursor = events[0][0]

    for moment, stake_delta, count_delta in events:
        span = (moment - cursor).total_seconds()
        if span > 0:
            stake_seconds += open_stake * span
            if open_count > 0:
                in_market_seconds += span
        cursor = moment
        open_stake += stake_delta
        open_count += count_delta
        peak_stake = max(peak_stake, open_stake)
        peak_count = max(peak_count, open_count)

    return {
        "time_exposure_pct": 100.0 * in_market_seconds / total_seconds,
        "avg_capital_exposure_pct": 100.0 * (stake_seconds / total_seconds) / wallet,
        "peak_capital_exposure_pct": 100.0 * peak_stake / wallet,
        "peak_concurrent_trades": peak_count,
        "trades_with_usable_timestamps": usable,
    }


def trade_derived_stats(trades: list[dict], fee: float) -> dict:
    """Figures Freqtrade does not always report, computed from the trades."""
    profits = [as_float(pick(t, "profit_abs", "profit_absolute")) for t in trades]
    profits = [p for p in profits if p is not None]
    stakes = [as_float(pick(t, "stake_amount", default=0.0)) or 0.0 for t in trades]

    wins = [p for p in profits if p > 0]
    losses = [p for p in profits if p < 0]

    streak = 0
    worst_streak = 0
    for profit in profits:
        if profit < 0:
            streak += 1
            worst_streak = max(worst_streak, streak)
        else:
            streak = 0

    # Every closed trade pays the fee twice: once in, once out.
    entry_notional = sum(stakes)
    fees_paid = None
    explicit_fees = [
        as_float(pick(t, "fee_open_cost", default=None)) for t in trades
    ] + [as_float(pick(t, "fee_close_cost", default=None)) for t in trades]
    explicit_fees = [f for f in explicit_fees if f is not None]
    if explicit_fees:
        fees_paid = sum(explicit_fees)
    elif entry_notional:
        fees_paid = 2.0 * fee * entry_notional

    return {
        "trade_count": len(trades),
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "win_rate_pct": (100.0 * len(wins) / len(profits)) if profits else None,
        "profit_factor": (sum(wins) / abs(sum(losses))) if losses and sum(losses) else None,
        "max_consecutive_losses": worst_streak,
        "turnover_stake": 2.0 * entry_notional,
        "turnover_note": "entry notional plus exit notional, approximated as 2x total stake",
        "total_fees_stake": fees_paid,
        "fees_note": (
            "summed from per-trade fee fields"
            if explicit_fees
            else f"derived as 2 x fee({fee}) x total stake; the engine reported no per-trade fee fields"
        ),
    }


def per_pair_returns(block: dict, trades: list[dict], wallet: float) -> tuple[dict, str]:
    """Per-pair attribution, preferring the engine's own table.

    Returns the attribution and a note saying where it came from, because a
    figure the engine reported and one derived here are not equally strong
    evidence and the record should not blur them.
    """
    out: dict[str, float] = {}
    rows = pick(block, "results_per_pair", "pair_results", default=[]) or []
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = row.get("key") or row.get("pair")
        if not key or key in ("TOTAL", "Total"):
            continue
        value = as_float(pick(row, "profit_total_pct", "profit_sum_pct", "profit_mean_pct"))
        if value is not None:
            out[str(key)] = value
    if out:
        return out, "reported by the engine (results_per_pair.profit_total_pct)"

    # Fall back to the trade list so the protocol still gets attribution if a
    # future release drops or renames that table.
    if not trades or not wallet:
        return {}, "unavailable: the engine reported no per-pair table and no usable trades"
    totals: dict[str, float] = {}
    for row in trades:
        pair = row.get("pair")
        profit = as_float(row.get("profit_abs"))
        if pair is None or profit is None:
            continue
        totals[str(pair)] = totals.get(str(pair), 0.0) + profit
    if not totals:
        return {}, "unavailable: no trade carried both a pair and an absolute profit"
    return (
        {pair: round(100.0 * value / wallet, 6) for pair, value in sorted(totals.items())},
        "derived here: sum of per-trade profit_abs by pair, as a percentage of the "
        "starting wallet; the engine reported no per-pair table",
    )


def build(args) -> dict:
    result = load_result(Path(args.result))
    name, block = load_strategy_block(result)
    trades = find_trades(block, result, Path(args.trades) if args.trades else None)

    window_start = parse_time(args.window_start)
    window_end = parse_time(args.window_end)
    if window_start is None or window_end is None:
        raise SystemExit("--window-start and --window-end must be ISO-8601 UTC timestamps")

    total_return_ratio = as_float(pick(block, "profit_total", "profit_total_ratio"))
    total_return_pct = as_float(pick(block, "profit_total_pct"))
    if total_return_pct is None and total_return_ratio is not None:
        total_return_pct = 100.0 * total_return_ratio

    drawdown_ratio = as_float(pick(block, "max_drawdown_account", "max_drawdown", "max_relative_drawdown"))
    drawdown_pct = 100.0 * drawdown_ratio if drawdown_ratio is not None else None

    exposure = exposure_profile(trades, window_start, window_end, float(args.wallet))
    derived = trade_derived_stats(trades, float(args.fee))
    per_pair, per_pair_note = per_pair_returns(block, trades, float(args.wallet))

    engine_trade_count = as_float(pick(block, "total_trades", "trade_count"))
    if not derived["trade_count"] and engine_trade_count is not None:
        derived["trade_count"] = int(engine_trade_count)

    engine_winrate = as_float(pick(block, "winrate"))
    engine_win_rate_pct = 100.0 * engine_winrate if engine_winrate is not None else None

    avg_exposure_fraction = exposure["avg_capital_exposure_pct"] / 100.0
    return_per_exposure = (
        total_return_pct / avg_exposure_fraction
        if total_return_pct is not None and avg_exposure_fraction > 0
        else None
    )

    passive: dict = {}
    realised_matched = None
    if args.passive:
        passive_report = json.loads(Path(args.passive).read_text(encoding="utf-8"))
        passive = passive_report.get("result", passive_report)
        full_5050 = as_float(passive.get("full_50_50_return"))
        if full_5050 is not None and avg_exposure_fraction > 0:
            # Same average capital in the market, held passively 50/50 for the
            # whole window. An approximation: it ignores *when* the exposure fell.
            realised_matched = 100.0 * full_5050 * avg_exposure_fraction

    metrics: dict = {
        "strategy": name,
        "window_start_utc": window_start.isoformat(),
        "window_end_utc": window_end.isoformat(),
        "wallet": float(args.wallet),
        "fee_per_side": float(args.fee),
        "total_return_pct": total_return_pct,
        "total_return_abs": as_float(pick(block, "profit_total_abs")),
        "max_drawdown_pct": drawdown_pct,
        "sharpe": as_float(pick(block, "sharpe", "sharpe_ratio")),
        "sortino": as_float(pick(block, "sortino", "sortino_ratio")),
        "calmar": as_float(pick(block, "calmar", "calmar_ratio")),
        "profit_factor": first_not_none(as_float(pick(block, "profit_factor")), derived["profit_factor"]),
        "win_rate_pct": first_not_none(engine_win_rate_pct, derived["win_rate_pct"]),
        "trade_count": derived["trade_count"],
        "winning_trades": first_not_none(as_float(pick(block, "wins")), derived["winning_trades"]),
        "losing_trades": first_not_none(as_float(pick(block, "losses")), derived["losing_trades"]),
        "max_consecutive_losses": int(
            first_not_none(
                as_float(pick(block, "max_consecutive_losses")), derived["max_consecutive_losses"], 0
            )
        ),
        "total_fees_stake": derived["total_fees_stake"],
        "fees_note": derived["fees_note"],
        "turnover_stake": derived["turnover_stake"],
        "turnover_note": derived["turnover_note"],
        "market_change_pct": (
            100.0 * as_float(pick(block, "market_change"))
            if as_float(pick(block, "market_change")) is not None
            else None
        ),
        "per_pair_return_pct": per_pair,
        "per_pair_return_note": per_pair_note,
        "backtest_days": as_float(pick(block, "backtest_days")),
        **exposure,
        "return_per_exposure_unit": return_per_exposure,
        "return_per_exposure_note": (
            "total_return_pct divided by the average capital-exposure fraction; "
            "how much return each unit of capital-at-risk produced"
        ),
        "passive_full_50_50_return_pct": (
            100.0 * as_float(passive.get("full_50_50_return"))
            if passive.get("full_50_50_return") is not None
            else None
        ),
        "passive_max_exposure_matched_return_pct": (
            100.0 * as_float(passive.get("exposure_matched_return"))
            if passive.get("exposure_matched_return") is not None
            else None
        ),
        "passive_realised_exposure_matched_return_pct": realised_matched,
        "passive_realised_exposure_matched_note": (
            "50/50 passive return scaled to the strategy's realised average capital "
            "exposure; an approximation that ignores when that exposure occurred"
        ),
    }
    return metrics


def to_markdown(metrics: dict) -> str:
    lines = [f"# Backtest summary — {metrics['strategy']}", ""]
    lines.append(f"Window: {metrics['window_start_utc']} → {metrics['window_end_utc']}")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("| --- | --- |")
    for key in sorted(metrics):
        if key in ("strategy", "window_start_utc", "window_end_utc"):
            continue
        value = metrics[key]
        if isinstance(value, float):
            value = f"{value:.6g}"
        elif isinstance(value, dict):
            value = ", ".join(f"{k}={v:.4g}" for k, v in sorted(value.items())) or "—"
        lines.append(f"| {key} | {value if value is not None else '—'} |")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--result", required=True)
    parser.add_argument("--trades", default=None, help="Separate trades JSON, when the engine exported one.")
    parser.add_argument("--window-start", default=None)
    parser.add_argument("--window-end", default=None)
    parser.add_argument("--wallet", type=float, default=100.0)
    parser.add_argument("--fee", type=float, default=0.001)
    parser.add_argument("--passive", default=None)
    parser.add_argument("--out", default=None)
    parser.add_argument("--md", default=None)
    parser.add_argument("--dump-schema", action="store_true", help="Print the result JSON's key structure and exit.")
    args = parser.parse_args(argv)

    if args.dump_schema:
        result = load_result(Path(args.result))
        name, block = load_strategy_block(result)
        print("top-level keys:", sorted(result)[:60])
        print("strategy name:", name)
        print("strategy block keys:", sorted(k for k in block if k != "trades")[:200])
        trades = find_trades(block, result, None)
        print("trade count:", len(trades))
        if trades:
            print("trade keys:", sorted(trades[0]))
        return 0

    metrics = build(args)
    if args.out:
        Path(args.out).write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    if args.md:
        Path(args.md).write_text(to_markdown(metrics), encoding="utf-8")
    if not args.out and not args.md:
        print(json.dumps(metrics, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
