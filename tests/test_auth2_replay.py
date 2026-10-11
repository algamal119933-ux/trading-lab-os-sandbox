"""AUTH-2 replay evaluator (FUNNEL_LAW_2.md §REPLAY_EVALUATOR_CONTRACT): parity against recorded
Freqtrade 2026.7 engine marks, the frozen tolerances, determinism, and the boundaries of what
it may do.

tests/fixtures/auth2_engine_marks.json holds the daily equity marks of two engine runs of the
pinned engine (research/auth2/engine_selftest.py worlds: synthetic, seed 4242, no edge). The
schedules are regenerated here from the frozen generators, so a change to a generator, the
schedule document or the replay accounting shows up as a hash or parity failure.

PAPER / RESEARCH ONLY. Synthetic data only.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")

from auth2 import engine_io as EIO  # noqa: E402
from auth2 import engine_selftest as ES  # noqa: E402
from auth2 import families as F  # noqa: E402
from auth2 import replay as RP  # noqa: E402
from auth2 import signals as S  # noqa: E402
from auth2 import synthetic as SY  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((REPO / "tests" / "fixtures" / "auth2_engine_marks.json").read_text())


def world_and_plan(fam: str):
    w = SY.generate(fam, seed=FIXTURE["seed"], edge=0.0, start_ms=ES._ms(2019), end_ms=ES._ms(2020))
    m = w.market
    start, end = ES._ms(2019, 3), ES._ms(2019, 7)
    b = F.bundle(fam, m, start, end, ["primary"], 0, None)
    plan = S.Plan(b.exec_times, b.weights, S._forced(m, start, end), b.extra_slippage, b.exempt,
                  {"node_run": "selftest", "family": fam})
    prices = RP.fill_like_freqtrade(m.times, {p: w.bars[p][:, :5] for p in m.pairs}, m.pairs)
    return w, m, plan, prices, start, end


def replay_marks(fam: str):
    w, m, plan, prices, start, end = world_and_plan(fam)
    sched = RP.Schedule(plan.exec_times, plan.weights, plan.forced_exits, plan.extra_slippage, plan.slippage_exempt)
    return RP.run(prices, sched, FIXTURE["fee"], start, end, whitelist_order=list(np.argsort(m.pairs)))[0]


def test_the_frozen_parity_tolerances():
    assert RP.PARITY_MIN_CORRELATION == 0.999
    assert RP.PARITY_MAX_TOTAL_RETURN_DIFF == 0.0025


@pytest.mark.parametrize("fam", ["A3", "A2"])
def test_the_regenerated_schedule_is_the_one_the_engine_ran(fam, tmp_path):
    w, m, plan, prices, start, end = world_and_plan(fam)
    doc = S.schedule_document(m, plan)
    held = sorted({p for r in doc["rows"] for p in r["w"]} | {f["pair"] for f in doc["forced_exits"]}) or [m.pairs[0]]
    spec = EIO.prepare_run(tmp_path, held, {p: w.bars[p] for p in held}, doc, FIXTURE["fee"], start, end)
    assert spec["schedule_sha256"] == FIXTURE["families"][fam]["schedule_sha256"]


@pytest.mark.parametrize("fam", ["A3", "A2"])
def test_replay_reproduces_the_recorded_engine_run(fam):
    engine = np.array(FIXTURE["families"][fam]["engine_marks"])
    par = RP.parity(engine, replay_marks(fam))
    assert par["status"] == "PASS", par
    assert par["total_return_difference"] < 1e-8  # far inside the 0.25 pp tolerance


def test_parity_fails_outside_either_tolerance():
    rng = np.random.default_rng(1)
    base = 1000 * np.cumprod(1 + rng.standard_normal(400) * 0.02)
    assert RP.parity(base, base)["status"] == "PASS"
    drift = base * np.linspace(1.0, 1.01, base.size)  # total return moved by ~1% of final equity
    par = RP.parity(base, drift)
    assert par["daily_return_correlation"] > 0.999 and par["total_return_difference"] > 0.0025
    assert par["status"] == "FAIL"
    noisy = base * (1 + rng.standard_normal(base.size) * 0.002)
    assert RP.parity(base, noisy)["status"] == "FAIL"  # correlation < 0.999
    flat = np.full(400, 1000.0)
    assert RP.parity(flat, flat)["status"] == "FAIL"  # not evaluable is never a pass


def test_replay_is_byte_identical_for_identical_inputs():
    a, b = replay_marks("A2"), replay_marks("A2")
    assert a.tobytes() == b.tobytes()


def test_a_null_distribution_is_one_deterministic_vectorised_call():
    w, m, _plan, prices, start, end = world_and_plan("A2")
    names = ["null:1", "null:2", "null:3"]
    b1 = F.bundle("A2", m, start, end, names, 0, None)
    b2 = F.bundle("A2", m, start, end, names, 0, None)
    assert b1.weights.tobytes() == b2.weights.tobytes()
    assert b1.weights.shape[1] == 3


def test_the_replay_evaluator_never_touches_the_ledger_or_the_engine():
    tree = ast.parse((REPO / "research" / "auth2" / "replay.py").read_text())
    imported = {n.names[0].name if isinstance(n, ast.Import) else n.module
                for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))}
    assert imported <= {"__future__", "hashlib", "json", "dataclasses", "pathlib", "numpy", "pandas"}
    # no ledger, engine, process or file-writing dependency: pure functions of the inputs
    src = (REPO / "research" / "auth2" / "replay.py").read_text()
    for forbidden in ("hyperopt", "minimize(", "write_text", "write_bytes", "subprocess"):
        assert forbidden not in src, forbidden


def _one_pair_prices(n_bars: int, t0: int):
    t = t0 + np.arange(n_bars, dtype=np.int64) * RP.FOUR_H_MS
    o = 100.0 + np.arange(n_bars, dtype=float)
    c = o + 0.5
    col = lambda a: a[:, None]  # noqa: E731
    return RP.Prices(t, ["AAA/USDT"], col(o), col(c + 1.0), col(o - 1.0), col(c))


def test_end_at_close_values_the_last_mark_at_the_last_close():
    # data ends exactly at end_ms (the secondary window on Dataset V3): no bar opens there
    t0 = ES._ms(2019, 3)
    prices = _one_pair_prices(12, t0)  # two days of 4h bars
    end = t0 + 2 * RP.DAY_MS
    assert int(prices.times[-1]) + RP.FOUR_H_MS == end
    sched = RP.Schedule(np.array([t0], dtype=np.int64), np.ones((1, 1, 1)), {}, 0.0, [])
    marks = RP.run(prices, sched, 0.0, t0, end)[0]
    units = 1.0 / prices.open[0, 0]
    assert marks.shape == (3,)
    assert marks[1] == pytest.approx(units * prices.open[6, 0])
    assert marks[2] == pytest.approx(units * prices.close[-1, 0])
    # one bar short of the window end is still refused, never extrapolated
    with pytest.raises(KeyError):
        RP.run(_one_pair_prices(11, t0), sched, 0.0, t0, end)


def test_engine_marks_end_at_close_use_the_last_bar_balances_at_its_close():
    import pandas as pd

    t0, day = ES._ms(2019, 3), RP.DAY_MS
    last = t0 + 2 * day - RP.FOUR_H_MS
    rows = [(t0, "USDT", 1.0, 1000.0), (t0 + day, "USDT", 1.0, 10.0), (t0 + day, "AAA", 100.0, 9.9),
            (last, "USDT", 1.0, 10.0), (last, "AAA", 110.0, 9.9)]
    wallet = pd.DataFrame(rows, columns=["date", "currency", "rate", "balance"])
    wallet["date"] = pd.to_datetime(wallet["date"], unit="ms", utc=True)
    with pytest.raises(ValueError, match="lacks 1 day marks"):
        RP.engine_daily_marks(wallet, t0, t0 + 2 * day)
    marks = RP.engine_daily_marks(wallet, t0, t0 + 2 * day, final_close={"AAA": 111.0})
    assert marks.tolist() == [1000.0, 10.0 + 990.0, 10.0 + 9.9 * 111.0]
    with pytest.raises(ValueError, match="no last-bar close"):
        RP.engine_daily_marks(wallet, t0, t0 + 2 * day, final_close={"BBB": 1.0})


def test_end_at_close_refuses_a_schedule_that_trades_in_the_last_bar(tmp_path):
    t0 = ES._ms(2019, 3)
    end = t0 + 2 * RP.DAY_MS
    p = _one_pair_prices(12, t0)
    bars = np.column_stack([p.times, p.open[:, 0], p.high[:, 0], p.low[:, 0], p.close[:, 0], np.full(12, 5.0)])
    EIO.write_feather(bars, tmp_path / "user_data/data/binance/AAA_USDT-4h.feather")
    doc = {"rows": [{"t": t0, "w": {"AAA/USDT": 1.0}}], "forced_exits": []}
    (tmp_path / "schedule.json").write_text(json.dumps(doc))
    assert EIO.final_closes(tmp_path, end) == {"AAA": float(p.close[-1, 0])}
    assert EIO.final_closes(tmp_path, end - RP.DAY_MS) is None  # a bar opens at that end: the normal capture
    doc["rows"].append({"t": end - RP.FOUR_H_MS, "w": {}})
    (tmp_path / "schedule.json").write_text(json.dumps(doc))
    with pytest.raises(SystemExit, match="END_AT_CLOSE"):
        EIO.final_closes(tmp_path, end)
