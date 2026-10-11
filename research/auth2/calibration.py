"""AUTH-2 statistical calibration (FUNNEL_LAW_2.md §CALIBRATION_DAG, §CALIBRATION_POWER_PROOF).

    edge_for_delta   the planted-edge strength whose TRUE effect equals the Owner's
                     delta, measured once on a 200-year world of the frozen generator
                     (fixed seed) through the replay evaluator at base cost; computed
                     before the program is frozen and recorded in the preregistration
    size_power       CAL-Ax-STAT: 200 no-edge and 200 planted-edge worlds through the
                     family's full gate stack (C2-C9 + family gates, Holm with m = 3 and
                     the other two families at p = 1); PASS iff accepted <= 10 / 200
                     (size) and >= 160 / 200 (power); exact Clopper-Pearson 95%
                     intervals reported
    pc_world         the single planted-edge world PC-Ax runs in the engine

A count stops early only once its outcome is mathematically decided (more than
10 accepted no-edge worlds, or more than 40 rejected planted-edge worlds); the
record then says so. Worlds are independent and deterministic in their seed, so
running them in parallel processes changes no number.

PAPER / RESEARCH ONLY. Synthetic data only; nothing here reads market data or a result.
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone

import numpy as np

from auth2 import families as F
from auth2 import gates as GT
from auth2 import replay as RP
from auth2 import stats as ST
from auth2 import synthetic as SY

DAY_MS = 86_400_000

DELTA = {"A1": 0.40, "A2": 0.40, "A3": 0.30}
WORLDS = 200
SIZE_MAX_ACCEPTED = 10
POWER_MIN_ACCEPTED = 160
SIZE_SEEDS = list(range(1, WORLDS + 1))
POWER_SEEDS = list(range(10_001, 10_001 + WORLDS))
PC_SEED = 777
TRUE_DELTA_SEED = 500_000  # disjoint from SIZE, POWER and PC seeds
TRUE_DELTA_YEARS = 200
EDGE_BRACKET = {"A1": (0.0, 0.004), "A2": (0.0, 0.004), "A3": (0.0, 0.6)}
EDGE_TOLERANCE = 0.005  # |true dSR - delta| at the calibrated edge


def _ms(y: int, mo: int = 1, d: int = 1) -> int:
    return int(datetime(y, mo, d, tzinfo=timezone.utc).timestamp() * 1000)


SCORED_END = _ms(2025)
SECONDARY = (_ms(2025), _ms(2026, 9))


def scored_start(fam: str, a3_start_ms: int) -> int:
    return a3_start_ms if fam == "A3" else _ms(2019)


def world_evidence(fam: str, seed: int, edge: float, a3_start_ms: int) -> GT.Evidence:
    w = SY.generate(fam, seed=seed, edge=edge)
    m = w.market
    prices = RP.fill_like_freqtrade(m.times, {p: w.bars[p][:, :5] for p in m.pairs}, m.pairs)
    return GT.Evidence(fam, m, prices, scored_start(fam, a3_start_ms), SCORED_END, sec=SECONDARY)


def true_delta(fam: str, edge: float, a3_start_ms: int, years: int = TRUE_DELTA_YEARS) -> float:
    """True dSR(primary vs matched benchmark) at base cost over a 200-year simulation of the
    same design: consecutive independent worlds of the frozen generator (seeds
    TRUE_DELTA_SEED, TRUE_DELTA_SEED + 1, ...), each priced over the family's scored window,
    pooled until the scored days reach ``years`` x 365. One long path would not be the same
    design: over two centuries a 70%-vol price leaves floating-point range."""
    need = years * 365
    prim, bench = [], []
    seed = TRUE_DELTA_SEED
    while sum(len(x) for x in prim) < need:
        ev = world_evidence(fam, seed, edge, a3_start_ms)
        got = ev._replay(F.bundle(fam, ev.m, ev.start, ev.end, ["primary", "bench"]), GT.BASE_FEE, ev.start, ev.end)
        prim.append(got["primary"])
        bench.append(got["bench"])
        seed += 1
    p, b = np.concatenate(prim)[:need], np.concatenate(bench)[:need]
    return float(ST.sharpe(p) - ST.sharpe(b))


def edge_for_delta(fam: str, a3_start_ms: int, iterations: int = 14) -> dict:
    """Bisection on the edge strength for true dSR = delta (monotone by construction)."""
    lo, hi = EDGE_BRACKET[fam]
    d_lo, d_hi = true_delta(fam, lo, a3_start_ms), true_delta(fam, hi, a3_start_ms)
    trace = [(lo, d_lo), (hi, d_hi)]
    target = DELTA[fam]
    if not (d_lo < target < d_hi):
        return {"status": "FAIL", "reason": "delta outside the bracket", "trace": trace}
    for _ in range(iterations):
        mid = (lo + hi) / 2
        d = true_delta(fam, mid, a3_start_ms)
        trace.append((mid, d))
        if d < target:
            lo = mid
        else:
            hi = mid
    edge = (lo + hi) / 2
    d = true_delta(fam, edge, a3_start_ms)
    trace.append((edge, d))
    ok = abs(d - target) <= EDGE_TOLERANCE
    return {"status": "OK" if ok else "FAIL", "family": fam, "delta": target, "edge": edge, "true_delta": d,
            "first_seed": TRUE_DELTA_SEED, "years": TRUE_DELTA_YEARS, "trace": trace}


def _one(args: tuple) -> dict:
    fam, seed, edge, a3_start_ms = args
    ev = world_evidence(fam, seed, edge, a3_start_ms)
    res = GT.evaluate(ev, early_exit=True, report=False)
    first_fail = next((k for k, v in res["gate_status"].items() if v != "PASS"), None)
    return {"seed": seed, "accepted": bool(res["accepted_with_holm_m3"]), "verdict": res["verdict"],
            "stopped_at": first_fail, "p_value": res["primary_p_value"], "replay_calls": ev.replay_calls}


def _count(fam: str, seeds: list[int], edge: float, a3_start_ms: int, stop, workers: int) -> dict:
    results: list[dict] = []
    batch = max(1, workers) * 4
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for i in range(0, len(seeds), batch):
            chunk = [(fam, s, edge, a3_start_ms) for s in seeds[i:i + batch]]
            results += list(pool.map(_one, chunk))
            if stop(results):
                break
    accepted = sum(r["accepted"] for r in results)
    return {"evaluated": len(results), "accepted": accepted, "worlds": results,
            "stopped_early": len(results) < len(seeds)}


def size_power(fam: str, edge: float, a3_start_ms: int, workers: int = 2) -> dict:
    size = _count(fam, SIZE_SEEDS, 0.0, a3_start_ms,
                  lambda rs: sum(r["accepted"] for r in rs) > SIZE_MAX_ACCEPTED, workers)
    size_pass = size["accepted"] <= SIZE_MAX_ACCEPTED and not size["stopped_early"]
    out = {"family": fam, "edge": edge, "delta": DELTA[fam], "size": size,
           "size_status": "PASS" if size_pass else "FAIL"}
    if not size_pass:
        out["power_status"] = "NOT_RUN"
        out["status"] = "FAIL_SIZE"
        return out
    power = _count(fam, POWER_SEEDS, edge, a3_start_ms,
                   lambda rs: sum(not r["accepted"] for r in rs) > WORLDS - POWER_MIN_ACCEPTED, workers)
    power_pass = power["accepted"] >= POWER_MIN_ACCEPTED and not power["stopped_early"]
    out["power"] = power
    out["power_status"] = "PASS" if power_pass else "FAIL"
    out["status"] = "PASS" if power_pass else "FAIL_POWER"
    if not size["stopped_early"]:
        out["size_clopper_pearson_95"] = ST.clopper_pearson(size["accepted"], WORLDS)
    if not power["stopped_early"]:
        out["power_clopper_pearson_95"] = ST.clopper_pearson(power["accepted"], WORLDS)
    return out


def outcome(cal: dict) -> str:
    """CAL-Ax-STAT terminal mapping (§CALIBRATION_DAG Outcomes)."""
    if cal["status"] == "FAIL_SIZE":
        return "LAW_INVALID"
    if cal["status"] == "FAIL_POWER":
        return "INCONCLUSIVE_UNDERPOWERED"
    return "PASS"


def clopper_pearson_at_thresholds() -> dict:
    return {"size_10_of_200": ST.clopper_pearson(SIZE_MAX_ACCEPTED, WORLDS),
            "power_160_of_200": ST.clopper_pearson(POWER_MIN_ACCEPTED, WORLDS)}
