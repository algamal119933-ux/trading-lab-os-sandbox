"""Trade-history statistics and red flags from a closed-trade list.

A trade list cannot show look-ahead, overfitting or data errors: those need the
strategy code and the data. So this module describes the distribution of the
trades it is given and flags patterns that commonly mean a misleading record. Its
verdict is RED_FLAGS or NO_RED_FLAGS_FOUND, never PASS.

Input contract: a CSV with a header row and, per closed trade, a close time and a
return. Accepted column names (first match wins, case-insensitive):

  close time   close_date, close_time, exit_time, exit_date, date
  return       profit_ratio (fraction), return_pct / profit_pct / profit_percent (percent)
  optional     pair, symbol, open_date, open_time

Returns are per trade, on the capital the trade used. The equity curve applies
each return to a fixed fraction of current equity (``fraction``), in close-time
order. ``fraction = 1`` means every trade used the whole account.
"""

from __future__ import annotations

import csv
import math
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

CLOSE_COLUMNS = ("close_date", "close_time", "exit_time", "exit_date", "date")
RATIO_COLUMNS = ("profit_ratio",)
PERCENT_COLUMNS = ("return_pct", "profit_pct", "profit_percent")
PAIR_COLUMNS = ("pair", "symbol")

# Red-flag thresholds. They describe common shapes of misleading records; none is
# a pass mark.
MIN_TRADES = 30
TOP_TRADE_SHARE = 0.5
TOP_5PCT_SHARE = 0.8
HIGH_PF_LOW_N = (3.0, 100)
MARTINGALE_SHAPE = (0.9, 3.0)
FLAWLESS_MONTHS = 12


class TradeFileError(ValueError):
    """The file does not satisfy the input contract."""


@dataclass(frozen=True)
class Trade:
    close_time: datetime
    ret: float  # fraction, e.g. 0.012 = +1.2 %
    pair: str = ""


def _pick(header: dict[str, str], names: tuple[str, ...]) -> str | None:
    for name in names:
        if name in header:
            return header[name]
    return None


def _parse_time(value: str) -> datetime:
    value = value.strip()
    try:
        number = float(value)
    except ValueError:
        number = None
    if number is not None:
        if number > 1e11:  # milliseconds
            number /= 1000.0
        return datetime.fromtimestamp(number, tz=timezone.utc)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def load_trades(path: Path) -> list[Trade]:
    with Path(path).open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            raise TradeFileError("no header row")
        header = {name.strip().lower(): name for name in reader.fieldnames}
        close_col = _pick(header, CLOSE_COLUMNS)
        ratio_col = _pick(header, RATIO_COLUMNS)
        pct_col = _pick(header, PERCENT_COLUMNS)
        pair_col = _pick(header, PAIR_COLUMNS)
        if close_col is None:
            raise TradeFileError(f"no close-time column (one of {', '.join(CLOSE_COLUMNS)})")
        if ratio_col is None and pct_col is None:
            raise TradeFileError("no return column (profit_ratio, or a percent column)")
        trades = []
        for line, row in enumerate(reader, start=2):
            raw = row[ratio_col] if ratio_col else row[pct_col]
            try:
                ret = float(raw) if ratio_col else float(raw) / 100.0
                when = _parse_time(row[close_col])
            except (TypeError, ValueError) as exc:
                raise TradeFileError(f"line {line}: {exc}") from exc
            if not math.isfinite(ret) or ret <= -1.0:
                raise TradeFileError(f"line {line}: return {ret} is not a possible trade return")
            trades.append(Trade(when, ret, row[pair_col].strip() if pair_col else ""))
    if not trades:
        raise TradeFileError("no trades")
    return sorted(trades, key=lambda t: t.close_time)


def equity_curve(returns: list[float], fraction: float) -> list[float]:
    equity = [1.0]
    for r in returns:
        equity.append(equity[-1] * (1.0 + fraction * r))
    return equity


def max_drawdown(equity: list[float]) -> float:
    peak, worst = equity[0], 0.0
    for value in equity:
        peak = max(peak, value)
        worst = max(worst, 1.0 - value / peak)
    return worst


def _streaks(returns: list[float]) -> tuple[int, int]:
    best_win = best_loss = win = loss = 0
    for r in returns:
        win, loss = (win + 1, 0) if r > 0 else (0, loss + 1)
        best_win, best_loss = max(best_win, win), max(best_loss, loss)
    return best_win, best_loss


def _monthly(trades: list[Trade], fraction: float) -> "OrderedDict[str, float]":
    months: OrderedDict[str, float] = OrderedDict()
    for t in trades:
        key = t.close_time.strftime("%Y-%m")
        months[key] = months.get(key, 1.0) * (1.0 + fraction * t.ret)
    return OrderedDict((k, v - 1.0) for k, v in months.items())


def summarize(trades: list[Trade], fraction: float = 1.0) -> dict:
    if not 0 < fraction <= 1:
        raise ValueError("fraction must be in (0, 1]")
    returns = [t.ret for t in trades]
    n = len(returns)
    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r <= 0]
    gross_win, gross_loss = sum(wins), -sum(losses)
    equity = equity_curve(returns, fraction)
    mean = sum(returns) / n
    std = math.sqrt(sum((r - mean) ** 2 for r in returns) / (n - 1)) if n > 1 else 0.0
    span_days = (trades[-1].close_time - trades[0].close_time).total_seconds() / 86400
    years = span_days / 365.25
    per_year = n / years if years > 0 else None
    sharpe = mean / std * math.sqrt(per_year) if std > 0 and per_year else None
    best_win, best_loss = _streaks(returns)
    months = _monthly(trades, fraction)

    net = sum(returns)
    ranked = sorted(returns, reverse=True)
    top_n = max(1, math.ceil(0.05 * n))
    top_share = ranked[0] / net if net > 0 else None
    top5_share = sum(ranked[:top_n]) / net if net > 0 else None

    stats = {
        "trades": n,
        "first_close": trades[0].close_time.isoformat(),
        "last_close": trades[-1].close_time.isoformat(),
        "span_days": round(span_days, 2),
        "fraction": fraction,
        "win_rate": len(wins) / n,
        "avg_win": gross_win / len(wins) if wins else 0.0,
        "avg_loss": -gross_loss / len(losses) if losses else 0.0,
        "expectancy_per_trade": mean,
        "profit_factor": gross_win / gross_loss if gross_loss > 0 else None,
        "total_return": equity[-1] - 1.0,
        "max_drawdown": max_drawdown(equity),
        "sharpe_annualised": sharpe,
        "trades_per_year": per_year,
        "longest_win_streak": best_win,
        "longest_loss_streak": best_loss,
        "top_trade_share_of_net": top_share,
        "top_5pct_trades_share_of_net": top5_share,
        "months": len(months),
        "positive_month_share": sum(1 for v in months.values() if v > 0) / len(months),
        "worst_month": min(months.values()),
        "best_month": max(months.values()),
        "monthly_returns": dict(months),
    }
    stats["red_flags"] = red_flags(stats)
    stats["verdict"] = "RED_FLAGS" if stats["red_flags"] else "NO_RED_FLAGS_FOUND"
    return stats


def red_flags(s: dict) -> list[str]:
    flags = []
    if s["trades"] < MIN_TRADES:
        flags.append(f"FEW_TRADES: {s['trades']} < {MIN_TRADES}; any statistic here is noise-dominated")
    if s["expectancy_per_trade"] <= 0:
        flags.append("NON_POSITIVE_EXPECTANCY: the average trade loses money")
    if s["top_trade_share_of_net"] is not None and s["top_trade_share_of_net"] > TOP_TRADE_SHARE:
        flags.append(f"CONCENTRATION: one trade is {s['top_trade_share_of_net']:.0%} of net profit")
    if s["top_5pct_trades_share_of_net"] is not None and s["top_5pct_trades_share_of_net"] > TOP_5PCT_SHARE:
        flags.append(f"CONCENTRATION: the top 5% of trades are {s['top_5pct_trades_share_of_net']:.0%} of net profit")
    pf_cap, pf_n = HIGH_PF_LOW_N
    if s["profit_factor"] is not None and s["profit_factor"] > pf_cap and s["trades"] < pf_n:
        flags.append(f"TOO_GOOD: profit factor {s['profit_factor']:.2f} on {s['trades']} trades "
                     "is typical of an overfit or selected record")
    if s["profit_factor"] is None and s["trades"] >= 1:
        flags.append("NO_LOSING_TRADES: a record without a single loss is almost never real or complete")
    wr_cap, ratio_cap = MARTINGALE_SHAPE
    if s["win_rate"] > wr_cap and s["avg_win"] > 0 and -s["avg_loss"] > ratio_cap * s["avg_win"]:
        flags.append("MARTINGALE_SHAPE: many small wins with rare losses several times larger "
                     "(averaging down, no stop, or hidden tail risk)")
    if s["months"] >= FLAWLESS_MONTHS and s["positive_month_share"] == 1.0:
        flags.append(f"FLAWLESS_MONTHS: {s['months']} months without a losing month")
    return flags
