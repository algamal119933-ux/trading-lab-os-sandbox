#!/usr/bin/env python3
"""Regime / session diagnostics over an exported trade list (OPENING-1 §6.4).

DIAGNOSTIC_ONLY. Reads one Freqtrade backtest export (the trade list the
Cycle-2 driver exports on every run) plus the OHLCV it ran on, and reports per
bucket — preregistered regime label, UTC session, UTC weekday — how many trades
fell there, what they returned and how much time they spent in the market.

It never selects, filters or gates a configuration, and its output carries no
PASS/FAIL. A regime- or session-gated variant is a separately preregistered
configuration (§2.3), not something read off this report.

No lookahead: the label at time t is computed from candles that had fully
CLOSED by t (open_time + timeframe <= t) and nothing else. The regime rule and
the session table come only from a preregistered spec; nothing here has a
default.

Spec (JSON):
  {"regime": {"rule": "close_vs_trailing_sma", "lookback": <int>}
           | {"rule": "trailing_volatility_band", "lookback": <int>, "boundaries": [<float>, ...]},
   "sessions": [{"name": <str>, "start_hour": <int>, "end_hour": <int>}, ...]}   # UTC, covers 0..24
"""

from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

_RESEARCH_DIR = Path(__file__).resolve().parents[1]
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from summarize_backtest import load_result, load_strategy_block, parse_time  # noqa: E402

CLASSIFICATION = "DIAGNOSTIC_ONLY"
NOTICE = ("Diagnostic only. Never selects, filters or gates a configuration; no PASS/FAIL. "
          "Labels use trailing, fully closed candles only.")
WARMUP = "WARMUP"
NO_DATA = "NO_DATA"
WEEKDAYS = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")
TIMEFRAMES_MS = {"5m": 300_000, "15m": 900_000, "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}


class SpecError(ValueError):
    """The diagnostic spec is missing, malformed or not preregistrable."""


# -- spec -------------------------------------------------------------------------


def validate_spec(spec: dict) -> dict:
    if not isinstance(spec, dict) or set(spec) != {"regime", "sessions"}:
        raise SpecError("spec must have exactly the keys 'regime' and 'sessions'")
    regime = spec["regime"]
    rule = regime.get("rule") if isinstance(regime, dict) else None
    lookback = regime.get("lookback") if isinstance(regime, dict) else None
    if isinstance(lookback, bool) or not isinstance(lookback, int) or lookback < 2:
        raise SpecError("regime.lookback must be an integer >= 2")
    if rule == "close_vs_trailing_sma":
        if set(regime) != {"rule", "lookback"}:
            raise SpecError("close_vs_trailing_sma takes exactly rule and lookback")
    elif rule == "trailing_volatility_band":
        bounds = regime.get("boundaries")
        if set(regime) != {"rule", "lookback", "boundaries"} or not isinstance(bounds, list) or not bounds:
            raise SpecError("trailing_volatility_band takes rule, lookback and a non-empty boundaries list")
        if not all(isinstance(b, (int, float)) and not isinstance(b, bool) and math.isfinite(b) and b > 0
                   for b in bounds) or sorted(set(bounds)) != bounds:
            raise SpecError("boundaries must be strictly increasing positive numbers")
    else:
        raise SpecError(f"unknown regime rule {rule!r}")

    sessions = spec["sessions"]
    if not isinstance(sessions, list) or not sessions:
        raise SpecError("sessions must be a non-empty list")
    covered: list[int] = []
    names = set()
    for s in sessions:
        if not isinstance(s, dict) or set(s) != {"name", "start_hour", "end_hour"}:
            raise SpecError("each session has exactly name, start_hour, end_hour")
        a, b = s["start_hour"], s["end_hour"]
        if not (isinstance(a, int) and isinstance(b, int) and 0 <= a < b <= 24):
            raise SpecError(f"session {s.get('name')!r}: need 0 <= start_hour < end_hour <= 24")
        if not isinstance(s["name"], str) or not s["name"] or s["name"] in names:
            raise SpecError("session names must be unique non-empty strings")
        names.add(s["name"])
        covered.extend(range(a, b))
    if sorted(covered) != list(range(24)):
        raise SpecError("sessions must cover every UTC hour exactly once")
    return spec


# -- labels (trailing only) -------------------------------------------------------


def closed_candles(candles: list[list[float]], open_times: list[int], t_ms: int, tf_ms: int) -> list[list[float]]:
    """Candles whose close (open + timeframe) is at or before ``t_ms``. Nothing later."""
    return candles[:bisect.bisect_right(open_times, t_ms - tf_ms)]


def regime_label(history: list[list[float]], regime: dict) -> str:
    """Label from closed candles only. ``history`` rows are [open_ms, o, h, l, c, v]."""
    n = regime["lookback"]
    if regime["rule"] == "close_vs_trailing_sma":
        if len(history) < n:
            return WARMUP
        closes = [row[4] for row in history[-n:]]
        return "ABOVE_SMA" if closes[-1] > sum(closes) / n else "AT_OR_BELOW_SMA"
    # trailing_volatility_band: stdev of the last n close-to-close log returns
    if len(history) < n + 1:
        return WARMUP
    closes = [row[4] for row in history[-(n + 1):]]
    rets = [math.log(b / a) for a, b in zip(closes, closes[1:])]
    mean = sum(rets) / n
    vol = math.sqrt(sum((r - mean) ** 2 for r in rets) / (n - 1))
    return f"VOL_BAND_{bisect.bisect_right(regime['boundaries'], vol)}"


def label_at(candles: list[list[float]], open_times: list[int], t_ms: int, tf_ms: int, regime: dict) -> str:
    return regime_label(closed_candles(candles, open_times, t_ms, tf_ms), regime)


def session_of(when: datetime, sessions: list[dict]) -> str:
    hour = when.astimezone(timezone.utc).hour
    return next(s["name"] for s in sessions if s["start_hour"] <= hour < s["end_hour"])


def weekday_of(when: datetime) -> str:
    return WEEKDAYS[when.astimezone(timezone.utc).weekday()]


# -- diagnostics ------------------------------------------------------------------


def _bucket() -> dict:
    return {"trades": 0, "wins": 0, "sum_profit_ratio": 0.0, "exposure_hours": 0.0}


def diagnostics(trades: list[dict], ohlcv: dict[str, list[list[float]]], timeframe: str, spec: dict) -> dict:
    """Per-bucket counts, return and exposure. Trades are labelled at their open time."""
    validate_spec(spec)
    if timeframe not in TIMEFRAMES_MS:
        raise SpecError(f"unsupported timeframe {timeframe!r}")
    tf_ms = TIMEFRAMES_MS[timeframe]
    series = {}
    for pair, rows in ohlcv.items():
        rows = sorted(rows, key=lambda r: r[0])
        series[pair] = (rows, [int(r[0]) for r in rows])

    readable = []
    for trade in trades:
        opened = parse_time(trade.get("open_date") or trade.get("open_timestamp"))
        closed = parse_time(trade.get("close_date") or trade.get("close_timestamp"))
        ratio = trade.get("profit_ratio")
        if opened is None or closed is None or not isinstance(ratio, (int, float)) or not math.isfinite(ratio):
            continue
        readable.append((opened, closed, str(trade.get("pair")), float(ratio)))
    # A canonical order, so float sums never depend on how the export listed trades.
    readable.sort()
    skipped = len(trades) - len(readable)

    buckets: dict[str, dict[str, dict]] = {"regime": {}, "session": {}, "weekday": {}}
    total_hours = 0.0
    for opened, closed, pair, ratio in readable:
        hours = max(0.0, (closed - opened).total_seconds() / 3600.0)
        total_hours += hours
        if pair in series:
            rows, times = series[pair]
            regime = label_at(rows, times, int(opened.timestamp() * 1000), tf_ms, spec["regime"])
        else:
            regime = NO_DATA
        for dim, key in (("regime", regime), ("session", session_of(opened, spec["sessions"])),
                         ("weekday", weekday_of(opened))):
            b = buckets[dim].setdefault(key, _bucket())
            b["trades"] += 1
            b["wins"] += ratio > 0
            b["sum_profit_ratio"] += ratio
            b["exposure_hours"] += hours

    for dim in buckets:
        for b in buckets[dim].values():
            b["mean_profit_ratio"] = b["sum_profit_ratio"] / b["trades"]
            b["exposure_share"] = b["exposure_hours"] / total_hours if total_hours else None
        buckets[dim] = dict(sorted(buckets[dim].items()))
    return {
        "classification": CLASSIFICATION,
        "notice": NOTICE,
        "timeframe": timeframe,
        "spec": spec,
        "trades_total": len(trades),
        "trades_unreadable": skipped,
        "buckets": buckets,
    }


# -- I/O --------------------------------------------------------------------------


def load_ohlcv(path: Path) -> list[list[float]]:
    """Freqtrade JSON ([[open_ms, o, h, l, c, v], ...]) or feather (pandas, optional)."""
    if path.suffix == ".json":
        return [list(r) for r in json.loads(path.read_text(encoding="utf-8"))]
    if path.suffix == ".feather":
        import pandas as pd

        frame = pd.read_feather(path)
        stamps = pd.to_datetime(frame["date"], utc=True).astype("int64") // 1_000_000
        return [[int(t), float(o), float(h), float(lo), float(c), float(v)] for t, o, h, lo, c, v in
                zip(stamps, frame["open"], frame["high"], frame["low"], frame["close"], frame["volume"])]
    raise SpecError(f"unsupported OHLCV file {path.name}")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--result", required=True, type=Path, help="Freqtrade backtest export (zip or json)")
    parser.add_argument("--ohlcv", action="append", required=True, metavar="PAIR=PATH")
    parser.add_argument("--timeframe", required=True)
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)

    _, block = load_strategy_block(load_result(args.result))
    trades = list(block.get("trades") or [])
    ohlcv, inputs = {}, {"result": {"path": args.result.name, "sha256": _sha(args.result)},
                         "spec": {"path": args.spec.name, "sha256": _sha(args.spec)}, "ohlcv": {}}
    for item in args.ohlcv:
        pair, _, raw = item.partition("=")
        path = Path(raw)
        ohlcv[pair] = load_ohlcv(path)
        inputs["ohlcv"][pair] = {"path": path.name, "sha256": _sha(path)}
    report = diagnostics(trades, ohlcv, args.timeframe, json.loads(args.spec.read_text(encoding="utf-8")))
    report["inputs"] = inputs
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{CLASSIFICATION}: {report['trades_total']} trades -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
