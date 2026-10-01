"""CYCLE-2 UNIT 7.1 — the §6.4 regime/session diagnostic, on synthetic fixtures only.

The central property is no lookahead: changing any candle that had not closed
by time t never changes the label at t. The rest proves the script is
diagnostic only — it labels and counts, and has nothing that selects, filters
or gates.
"""

from __future__ import annotations

import inspect
import json
import random
from datetime import datetime, timezone

import pytest

from cycle2 import regime_session as rs

H = 3_600_000
T0 = int(datetime(2022, 1, 3, tzinfo=timezone.utc).timestamp() * 1000)  # a Monday

SESSIONS = [{"name": "S_A", "start_hour": 0, "end_hour": 8},
            {"name": "S_B", "start_hour": 8, "end_hour": 16},
            {"name": "S_C", "start_hour": 16, "end_hour": 24}]
# Fixture rules: the numbers exercise code paths; none is a research choice.
SMA_SPEC = {"regime": {"rule": "close_vs_trailing_sma", "lookback": 5}, "sessions": SESSIONS}
VOL_SPEC = {"regime": {"rule": "trailing_volatility_band", "lookback": 6, "boundaries": [0.005, 0.02]},
            "sessions": SESSIONS}


def candles(seed: int, n: int = 300) -> list[list[float]]:
    rng = random.Random(seed)
    price, rows = 100.0, []
    for i in range(n):
        o = price
        price *= 1 + rng.gauss(0, 0.012)
        rows.append([T0 + i * H, o, max(o, price) * 1.001, min(o, price) * 0.999, price, 1.0])
    return rows


def iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


@pytest.mark.parametrize("spec", [SMA_SPEC, VOL_SPEC], ids=["sma", "vol"])
@pytest.mark.parametrize("seed", range(4))
def test_changing_any_candle_after_t_never_changes_the_label_at_t(spec, seed):
    rows = candles(seed)
    times = [r[0] for r in rows]
    rng = random.Random(1000 + seed)
    probes = sorted({T0 + rng.randrange(0, 300 * H, 60_000) for _ in range(60)}) + [T0 + 40 * H]
    for t in probes:
        before = rs.label_at(rows, times, t, H, spec["regime"])
        mutated = [list(r) for r in rows]
        for r in mutated:
            if r[0] + H > t:  # not yet closed at t: rewrite it arbitrarily
                scale = rng.choice([0.2, 5.0, 50.0])
                r[1:5] = [v * scale for v in r[1:5]]
        assert rs.label_at(mutated, times, t, H, spec["regime"]) == before, (t, spec["regime"])


def test_the_candle_closing_exactly_at_t_is_used_and_the_one_still_open_is_not():
    rows = candles(5)
    times = [r[0] for r in rows]
    t = T0 + 50 * H  # candle 49 closes exactly at t; candle 50 opens at t
    assert len(rs.closed_candles(rows, times, t, H)) == 50
    assert len(rs.closed_candles(rows, times, t - 1, H)) == 49


def test_a_lookahead_labeller_would_be_caught_by_the_same_check():
    # Guard on the guard: a labeller that also reads the candle still open at t
    # does change under the mutation; label_at, for the same t, does not.
    rows = candles(6)
    times = [r[0] for r in rows]
    regime = SMA_SPEC["regime"]
    caught = 0
    for i in range(10, 200):
        t = T0 + i * H + 1  # candle i opened at t-1 and is still open
        leaky, leaky_mutated = rows[:i + 1], [list(r) for r in rows[:i + 1]]
        leaky_mutated[-1][4] *= 0.2 if rows[i][4] > rows[i - 1][4] else 5.0
        caught += rs.regime_label(leaky, regime) != rs.regime_label(leaky_mutated, regime)
        mutated = [list(r) for r in rows]
        mutated[i] = leaky_mutated[-1]
        assert rs.label_at(mutated, times, t, H, regime) == rs.label_at(rows, times, t, H, regime)
    assert caught > 0


def test_warmup_is_labelled_not_guessed():
    rows = candles(7)
    times = [r[0] for r in rows]
    assert rs.label_at(rows, times, T0 + 3 * H, H, SMA_SPEC["regime"]) == rs.WARMUP
    assert rs.label_at(rows, times, T0 + 6 * H, H, VOL_SPEC["regime"]) == rs.WARMUP
    assert rs.label_at(rows, times, T0 + 7 * H, H, VOL_SPEC["regime"]).startswith("VOL_BAND_")


def _trades(rows):
    out = []
    for k, (start, hours, ratio) in enumerate([(20, 5, 0.02), (30, 10, -0.01), (45, 3, 0.005),
                                               (60, 24, 0.03), (90, 2, -0.02), (130, 8, 0.0)]):
        out.append({"pair": "BTC/USDT", "open_date": iso(T0 + start * H), "close_date": iso(T0 + (start + hours) * H),
                    "profit_ratio": ratio})
    out.append({"pair": "ETH/USDT", "open_date": iso(T0 + 70 * H), "close_date": iso(T0 + 75 * H),
                "profit_ratio": 0.01})
    out.append({"pair": "BTC/USDT", "open_date": None, "close_date": None, "profit_ratio": 0.5})
    return out


def test_diagnostics_count_return_and_exposure_per_bucket():
    rows = candles(8)
    report = rs.diagnostics(_trades(rows), {"BTC/USDT": rows}, "1h", SMA_SPEC)
    assert report["classification"] == "DIAGNOSTIC_ONLY"
    assert report["trades_total"] == 8 and report["trades_unreadable"] == 1
    for dim in ("regime", "session", "weekday"):
        buckets = report["buckets"][dim]
        assert sum(b["trades"] for b in buckets.values()) == 7
        assert abs(sum(b["sum_profit_ratio"] for b in buckets.values()) - 0.035) < 1e-12
        assert abs(sum(b["exposure_share"] for b in buckets.values()) - 1.0) < 1e-12
        assert abs(sum(b["exposure_hours"] for b in buckets.values()) - 57.0) < 1e-12
    assert report["buckets"]["regime"]["NO_DATA"]["trades"] == 1  # ETH without OHLCV
    # T0 is Monday 00:00 UTC; +20h = Monday 20:00 → S_C; +30h = Tuesday 06:00 → S_A
    assert report["buckets"]["weekday"]["MON"]["trades"] == 1
    assert report["buckets"]["session"]["S_A"]["trades"] >= 1


def test_the_report_is_deterministic_and_order_independent():
    rows = candles(9)
    trades = _trades(rows)
    a = rs.diagnostics(trades, {"BTC/USDT": rows}, "1h", VOL_SPEC)
    b = rs.diagnostics(list(reversed(trades)), {"BTC/USDT": list(reversed(rows))}, "1h", VOL_SPEC)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


@pytest.mark.parametrize("spec", [
    {},
    {"regime": {"rule": "close_vs_trailing_sma"}, "sessions": SESSIONS},
    {"regime": {"rule": "close_vs_trailing_sma", "lookback": 5, "threshold": 0.1}, "sessions": SESSIONS},
    {"regime": {"rule": "future_return_sign", "lookback": 5}, "sessions": SESSIONS},
    {"regime": {"rule": "trailing_volatility_band", "lookback": 5, "boundaries": [0.02, 0.01]},
     "sessions": SESSIONS},
    {"regime": SMA_SPEC["regime"], "sessions": SESSIONS[:2]},
    {"regime": SMA_SPEC["regime"], "sessions": SESSIONS + [{"name": "X", "start_hour": 3, "end_hour": 4}]},
    {"regime": SMA_SPEC["regime"], "sessions": SESSIONS, "select": True},
])
def test_a_spec_without_every_preregistered_value_is_refused(spec):
    with pytest.raises(rs.SpecError):
        rs.validate_spec(spec)


def test_it_exposes_nothing_that_selects_filters_or_gates():
    public = [n for n, _ in inspect.getmembers(rs) if not n.startswith("_")
              and getattr(getattr(rs, n), "__module__", rs.__name__) == rs.__name__]
    for name in public:
        for word in ("select", "filter", "gate", "admit", "promote", "rank", "best", "choose"):
            assert word not in name.lower(), name
    rows = candles(10)
    report = rs.diagnostics(_trades(rows), {"BTC/USDT": rows}, "1h", SMA_SPEC)
    flat = json.dumps(report)
    for verdict in ('"PASS"', '"FAIL"', '"status"', '"selected"'):
        assert verdict not in flat


def test_the_cli_reads_an_export_and_writes_a_diagnostic(tmp_path):
    rows = candles(11)
    result = tmp_path / "backtest-result.json"
    result.write_text(json.dumps({"strategy": {"Fixture": {"trades": _trades(rows)}}}), encoding="utf-8")
    ohlcv = tmp_path / "BTC_USDT-1h.json"
    ohlcv.write_text(json.dumps(rows), encoding="utf-8")
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps(SMA_SPEC), encoding="utf-8")
    out = tmp_path / "out.json"
    assert rs.main(["--result", str(result), "--ohlcv", f"BTC/USDT={ohlcv}", "--timeframe", "1h",
                    "--spec", str(spec), "--out", str(out)]) == 0
    report = json.loads(out.read_text())
    assert report["classification"] == "DIAGNOSTIC_ONLY"
    assert report["inputs"]["ohlcv"]["BTC/USDT"]["path"] == "BTC_USDT-1h.json"
