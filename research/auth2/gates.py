"""FUNNEL-LAW-2 gate evaluation for one family (FUNNEL_LAW_2.md §COMMON_GATES, family gates,
§MULTIPLE_TESTING_LAW, §CALIBRATION_DAG).

``evaluate`` turns an ``Evidence`` (the daily return series a family's gates
need, computed lazily) into a gate table and a pre-Holm verdict. The same
function judges a calibration world, PC-Ax, N-Ax and the market-data node Ax;
only the source of the series differs:

  * engine-judged series (primary, benchmark, perturbations, stresses, U8,
    secondary) come from Freqtrade runs whenever the node has them
    (``Evidence.engine``), and from the replay evaluator in calibration worlds;
  * nulls, leave-one-out variants, sleeves, weekday offsets and PBO always come
    from the replay evaluator (REPLAY_EVALUATOR_CONTRACT).

Verdict precedence (IMPLEMENTATION_NOTES.md §Verdicts): any evaluable gate that
FAILS => REJECTED; otherwise any gate NOT_EVALUABLE or short coverage (C8) =>
INCONCLUSIVE; otherwise PRE_HOLM_PASS. C1 integrity is checked by the node
before this function is called (a failure there is INVALID_RUN).

In a calibration world (``early_exit=True``) evaluation stops at the first gate
that prevents acceptance, cheapest gates first; acceptance additionally needs
the Holm first step p <= 0.05 / 3 (the other two families enter with p = 1).
The order never changes an outcome: acceptance is the conjunction.

PAPER / RESEARCH ONLY.
"""

from __future__ import annotations

import math

import numpy as np

from auth2 import families as F
from auth2 import replay as RP
from auth2 import signals as S
from auth2 import stats as ST
from auth2.universe import DELISTING_HAIRCUT as U_HAIRCUT
from auth2.universe import DIAGNOSTIC_HAIRCUTS as U_DIAGNOSTIC_HAIRCUTS

DAY_MS = 86_400_000

BASE_FEE = 0.0015  # 0.10%/side fee + 0.05%/side slippage
STRESS_FEES = {"x2": 0.0030, "x3": 0.0045}
SEEDS = {"C3": 20261010, "C7": 20261011, "SPA": 20261012}
ALPHA_HOLM = 0.05
HOLM_M = 3
ALPHA_PERTURBATION = 0.10
C4_ALPHA = 0.05
DSR_THRESHOLD = 0.95
SPA_ALPHA = 0.05
PBO_BLOCKS = 16
COVERAGE_MIN = {"A1": 100, "A2": 250, "A3": 6}
A1_MIN_SLEEVE_DAYS = 730  # >= 2 years of scored membership
A1_SLEEVES_POSITIVE = 4
A2_YEARS = list(range(2019, 2025))
A2_YEARS_POSITIVE = 4
A3_CVAR_LEVEL = 0.05

PASS, FAIL, NE, INC, REP = "PASS", "FAIL", "NOT_EVALUABLE", "INCONCLUSIVE", "REPORTED"


def daily_returns(marks: np.ndarray) -> np.ndarray:
    return marks[..., 1:] / marks[..., :-1] - 1.0


class Evidence:
    """Daily return series for one family on one market and window, computed on demand."""

    def __init__(self, fam: str, m: S.Market, prices: RP.Prices, start: int, end: int,
                 sec: tuple[int, int] | None = None, engine: dict[str, np.ndarray] | None = None,
                 primary_override: tuple[str, int] | None = None):
        self.fam, self.m, self.prices, self.start, self.end, self.sec = fam, m, prices, start, end, sec
        self.engine = dict(engine or {})
        self.override = primary_override
        self._cache: dict[str, np.ndarray] = {}
        self._order = list(np.argsort(m.pairs))
        self.replay_calls = 0
        self.names = ["primary", "bench", *F.PERTURBATIONS[fam]]

    # -- replay plumbing -------------------------------------------------------
    def _replay(self, b: F.Bundle, fee: float, start: int, end: int) -> dict[str, np.ndarray]:
        sched = RP.Schedule(b.exec_times, b.weights, S._forced(self.m, start, end), b.extra_slippage, b.exempt)
        marks = RP.run(self.prices, sched, fee, start, end, whitelist_order=self._order)
        self.replay_calls += 1
        r = daily_returns(marks)
        return {n: r[i] for i, n in enumerate(b.names)}

    def _group(self, key: str) -> None:
        fam, m, s, e = self.fam, self.m, self.start, self.end
        if key == "base":
            got = self._replay(F.bundle(fam, m, s, e, self.names, 0, self.override), BASE_FEE, s, e)
        elif key in STRESS_FEES:
            names = ["primary", "bench"] if key == "x2" else ["primary"]
            got = self._replay(F.bundle(fam, m, s, e, names, 0, self.override), STRESS_FEES[key], s, e)
        elif key == "lat":
            got = self._replay(F.bundle(fam, m, s, e, ["primary", "bench"], 1, self.override), BASE_FEE, s, e)
        elif key == "sec":
            a, b = self.sec
            got = self._replay(F.bundle(fam, m, a, b, ["primary", "bench"], 0, self.override), BASE_FEE, a, b)
        elif key == "u8":
            mu = F.u8_market(m)
            got = self._replay(F.bundle(fam, mu, s, e, ["primary", "bench"], 0, self.override), BASE_FEE, s, e)
        else:
            raise KeyError(key)
        suffix = {"base": "", "x2": "@x2", "x3": "@x3", "lat": "@lat", "sec": "@sec", "u8": "@u8"}[key]
        for n, r in got.items():
            self._cache.setdefault(n + suffix, r)

    def r(self, name: str) -> np.ndarray:
        if name in self.engine:
            return self.engine[name]
        if name not in self._cache:
            key = {"@x2": "x2", "@x3": "x3", "@lat": "lat", "@sec": "sec", "@u8": "u8"}.get(
                name[name.find("@"):] if "@" in name else "", "base")
            self._group(key)
        return self._cache[name]

    def nulls(self, seeds: list[int]) -> np.ndarray:
        b = F.null_bundle(self.fam, self.m, self.start, self.end, seeds)
        got = self._replay(b, BASE_FEE, self.start, self.end)
        return np.stack([got[f"null:{s}"] for s in seeds])

    def variants(self, named: dict[str, np.ndarray], base: F.Bundle, m: S.Market | None = None,
                 start: int | None = None, end: int | None = None) -> dict[str, np.ndarray]:
        """Replay arbitrary weight matrices on ``base``'s grid (one call)."""
        names = list(named)
        W = np.stack([named[n] for n in names], axis=1)
        b = F.Bundle(base.exec_times, names, W, base.extra_slippage, base.exempt, base.meta)
        mm = m or self.m
        s, e = start or self.start, end or self.end
        sched = RP.Schedule(b.exec_times, b.weights, S._forced(mm, s, e), b.extra_slippage, b.exempt)
        marks = RP.run(self.prices, sched, BASE_FEE, s, e, whitelist_order=self._order)
        self.replay_calls += 1
        r = daily_returns(marks)
        return {n: r[i] for i, n in enumerate(names)}


def dsr_of(a: np.ndarray, b: np.ndarray) -> float:
    return ST.sharpe(a) - ST.sharpe(b)


def _gate(status: str, **kw) -> dict:
    return {"status": status, **kw}


def evaluate(ev: Evidence, early_exit: bool = False, report: bool = True) -> dict:
    """Gate table and verdict. ``early_exit``: calibration-world mode (stop at the first
    gate that prevents acceptance; skip report-only statistics)."""
    fam = ev.fam
    G: dict[str, dict] = {}
    stop = False

    def done() -> bool:
        if not early_exit:
            return False
        return any(g["status"] in (FAIL, NE, INC) for g in G.values())

    def finish() -> dict:
        return _verdict(fam, G, early_exit)

    # C2 absolute net economics
    p = ev.r("primary")
    G["C2"] = _gate(PASS if ST.total_return(p) > 0 and ST.sharpe(p) > 0 else FAIL,
                    total_return=ST.total_return(p), sharpe=ST.sharpe(p))
    if done():
        return finish()

    # C3 matched-benchmark inference (A3-1 is C3 as a paired ablation)
    bm = ev.r("bench")
    bl = ST.block_length(p - bm)
    if bl["status"] != "OK":
        G["C3"] = _gate(NE, block=bl, reason="block length not evaluable")
    else:
        t = ST.delta_sr_test(p, bm, bl["b"], "greater", SEEDS["C3"])
        st = NE if t["status"] != "OK" else (PASS if t["delta_sr"] > 0 else FAIL)
        G["C3"] = _gate(st, block=bl, test=t, p_value=t.get("p_value"))
        if report and t["status"] == "OK":
            G["C3"]["sensitivity"] = {str(b): ST.delta_sr_test(p, bm, b, "greater", SEEDS["C3"]).get("p_value")
                                      for b in ST.SENSITIVITY_BLOCKS}
    if early_exit and G["C3"]["status"] == PASS and not (G["C3"]["p_value"] <= ALPHA_HOLM / HOLM_M):
        G["HOLM_FIRST_STEP"] = _gate(FAIL, p_value=G["C3"]["p_value"], level=ALPHA_HOLM / HOLM_M)
    if done():
        return finish()

    # C8 coverage
    cov = F.coverage_count(fam, ev.m, ev.start, ev.end) if ev.override is None else _null_coverage(ev)
    G["C8"] = _gate(PASS if cov >= COVERAGE_MIN[fam] else INC, count=cov, minimum=COVERAGE_MIN[fam])
    if done():
        return finish()

    # C5 cost stress (2x gates; 3x reported)
    p2, b2 = ev.r("primary@x2"), ev.r("bench@x2")
    d2 = dsr_of(p2, b2)
    G["C5"] = _gate(PASS if d2 > 0 and ST.total_return(p2) > 0 else FAIL, delta_sr_x2=d2,
                    total_return_x2=ST.total_return(p2))
    if report:
        p3 = ev.r("primary@x3")
        G["C5"]["report_x3"] = {"total_return": ST.total_return(p3), "sharpe": ST.sharpe(p3)}
    if done():
        return finish()

    # C6 latency stress
    dl = dsr_of(ev.r("primary@lat"), ev.r("bench@lat"))
    G["C6"] = _gate(PASS if dl > 0 else FAIL, delta_sr_latency=dl)
    if done():
        return finish()

    # family mechanism gates
    {"A1": _a1_gates, "A2": _a2_gates, "A3": _a3_gates}[fam](ev, G, report)
    if done():
        return finish()

    # C7 robustness perturbations
    _c7(ev, G)
    if done():
        return finish()

    # C9 DSR and SPA (Holm is the HOLM node)
    _c9(ev, G)
    if done():
        return finish()

    # C4 family-matched null
    _c4(ev, G, early_exit)
    if done():
        return finish()

    if report:
        _reports(ev, G)
    return finish()


def _null_coverage(ev: Evidence) -> int:
    # N-Ax: coverage of the null fixture's own schedule, counted like the primary's
    fam, m, s, e = ev.fam, ev.m, ev.start, ev.end
    t, W = F.null_weights(fam, m, s, e, [ev.override[1]])
    W = W[:, 0, :]
    if fam == "A1":
        return int(np.abs(np.diff((W > 0).astype(int), axis=0)).sum())
    if fam == "A2":
        return int((W > 0).any(axis=1).sum())
    _t, Wb = F.weights(fam, m, s, e, "bench")
    cut = (W < Wb - 1e-15) & (Wb > 0)
    n = 0
    for j in sorted(m.funding):
        n += len(S.episodes(cut[:, j]))
    return n


def _c7(ev: Evidence, G: dict) -> None:
    fam = ev.fam
    bm = ev.r("bench")
    deltas, pvals, tests = {}, {}, {}
    for name in F.PERTURBATIONS[fam]:
        x = ev.r(name)
        deltas[name] = dsr_of(x, bm)
        bl = ST.block_length(x - bm)
        if bl["status"] != "OK":
            tests[name] = {"status": NE, "block": bl}
            continue
        t = ST.delta_sr_test(x, bm, bl["b"], "less", SEEDS["C7"])
        tests[name] = {**t, "block": bl}
        if t["status"] == "OK":
            pvals[name] = t["p_value"]
    positive = sum(1 for d in deltas.values() if d > 0)
    if len(pvals) < len(F.PERTURBATIONS[fam]):
        neg = {"status": NE, "reason": "a perturbation's negative-direction test is not evaluable"}
        rejected = {}
    else:
        rejected = ST.holm(pvals, ALPHA_PERTURBATION)
        neg = {"status": FAIL if any(rejected.values()) else PASS, "holm_rejections": rejected}
    pos_ok = positive >= F.MIN_POSITIVE[fam]
    if not pos_ok or neg["status"] == FAIL:
        st = FAIL
    elif neg["status"] == NE:
        st = NE
    else:
        st = PASS
    G["C7"] = _gate(st, delta_sr=deltas, positive=positive, required_positive=F.MIN_POSITIVE[fam],
                    negative_tests={k: {kk: v.get(kk) for kk in ("status", "p_value", "delta_sr", "b")}
                                    for k, v in tests.items()}, negative_holm=neg)


def _c9(ev: Evidence, G: dict) -> None:
    fam = ev.fam
    p, bm = ev.r("primary"), ev.r("bench")
    srs = [ST.sharpe(ev.r(n)) for n in ["primary", *F.PERTURBATIONS[fam]]]
    d = ST.dsr(p, srs, F.FAMILY_N[fam], DSR_THRESHOLD)
    dsr_status = {"PASS": PASS, "FAIL": FAIL}.get(d["status"], NE)
    bl = G.get("C3", {}).get("block") or ST.block_length(p - bm)
    if bl["status"] != "OK":
        spa = {"status": NE, "reason": "block length not evaluable"}
        spa_status = NE
    else:
        models = np.column_stack([ev.r(n) for n in ["primary", *F.PERTURBATIONS[fam]]])
        spa = ST.spa_pvalue(bm, models, bl["b"], SEEDS["SPA"])
        spa_status = NE if spa["status"] != "OK" else (PASS if spa["p_value"] <= SPA_ALPHA else FAIL)
    st = FAIL if FAIL in (dsr_status, spa_status) else (NE if NE in (dsr_status, spa_status) else PASS)
    G["C9"] = _gate(st, dsr=d, dsr_status=dsr_status, spa=spa, spa_status=spa_status,
                    holm="evaluated in the HOLM node (m = 3, FWER 0.05)")


def _c4(ev: Evidence, G: dict, early_exit: bool) -> None:
    obs = dsr_of(ev.r("primary"), ev.r("bench"))
    bm = ev.r("bench")
    seeds = F.C4_SEEDS
    exceed_limit = math.floor(C4_ALPHA * (len(seeds) + 1) - 1 + 1e-12)  # p <= 0.05 <=> exceed <= 49
    exceed, seen, deltas = 0, 0, []
    batch = 100 if early_exit else len(seeds)
    sr_b = ST.sharpe(bm)
    for i in range(0, len(seeds), batch):
        R = ev.nulls(seeds[i:i + batch])
        ds = np.array([ST.sharpe(x) - sr_b for x in R])
        deltas += list(ds)
        exceed += int((ds >= obs).sum())
        seen += len(ds)
        if early_exit and exceed > exceed_limit:
            G["C4"] = _gate(FAIL, observed_delta_sr=obs, draws_evaluated=seen, exceed=exceed, early_stop=True)
            return
    deltas = np.array(deltas)
    pval = (1 + exceed) / (1 + len(seeds))
    q95 = float(np.quantile(deltas, 0.95))
    st = PASS if (obs > q95 and pval <= C4_ALPHA) else FAIL
    G["C4"] = _gate(st, observed_delta_sr=obs, null_q95=q95, p_value=pval, draws=len(seeds),
                    null_mean=float(deltas.mean()))


# -- family gates ------------------------------------------------------------------


def _drop(x: np.ndarray, a: int, b: int) -> np.ndarray:
    return np.concatenate([x[:a], x[b + 1:]])


def _a1_gates(ev: Evidence, G: dict, report: bool) -> None:
    m, s, e = ev.m, ev.start, ev.end
    p, bm = ev.r("primary"), ev.r("bench")
    eps = F.a1_trend_episodes(m, s, e)
    ups = sum(1 for g, _a, _b in eps if g > 0)
    downs = sum(1 for g, _a, _b in eps if g < 0)
    loo = {f"{'up' if g > 0 else 'down'}:{a}-{b}": dsr_of(_drop(p, a, b), _drop(bm, a, b)) for g, a, b in eps}
    if ups < 2 or downs < 2:
        st = INC
    else:
        st = PASS if all(v > 0 for v in loo.values()) else FAIL
    G["A1-1"] = _gate(st, up_episodes=ups, down_episodes=downs, leave_one_episode_out=loo)

    if ev.override is not None:
        tp, Wp = F.null_weights("A1", m, s, e, [ev.override[1]])
        Wp = Wp[:, 0, :]
    else:
        tp, Wp = F.weights("A1", m, s, e, "primary")
    _tb, Wb = F.weights("A1", m, s, e, "bench")
    base = F.bundle("A1", m, s, e, ["bench"])
    held = sorted(set(F.ever_held(Wp)) | set(F.ever_held(Wb)))
    named = {}
    for j in held:
        named[f"sleeve:{j}:primary"] = F.only_pair(Wp, j)
        named[f"sleeve:{j}:bench"] = F.only_pair(Wb, j)
        named[f"loo:{j}:primary"] = F.zero_pair(Wp, j)
        named[f"loo:{j}:bench"] = F.zero_pair(Wb, j)
    got = ev.variants(named, base) if named else {}
    member_days = _member_days(m, s, e)
    sleeves, loo_assets = {}, {}
    for j in held:
        pair = m.pairs[j]
        loo_assets[pair] = dsr_of(got[f"loo:{j}:primary"], got[f"loo:{j}:bench"])
        if member_days.get(j, 0) >= A1_MIN_SLEEVE_DAYS:
            sleeves[pair] = dsr_of(got[f"sleeve:{j}:primary"], got[f"sleeve:{j}:bench"])
    pos = sum(1 for v in sleeves.values() if v > 0 and math.isfinite(v))
    loo_ok = all(math.isfinite(v) and v > 0 for v in loo_assets.values())
    G["A1-2"] = _gate(PASS if pos >= A1_SLEEVES_POSITIVE and loo_ok else FAIL, sleeves_2y=sleeves,
                      sleeves_positive=pos, required=A1_SLEEVES_POSITIVE, leave_one_asset_out=loo_assets)
    G["A1-3"] = _gate(REP, max_drawdown_primary=ST.max_drawdown(p), max_drawdown_bench=ST.max_drawdown(bm))


def _member_days(m: S.Market, s: int, e: int) -> dict[int, int]:
    out: dict[int, int] = {}
    for a, b, members, _rk in m.periods:
        lo, hi = max(a, s), min(b, e)
        if hi <= lo:
            continue
        for j in members:
            out[j] = out.get(j, 0) + (hi - lo) // DAY_MS
    return out


def _years(ev: Evidence, x: np.ndarray, y: np.ndarray) -> dict[int, float]:
    out = {}
    days = ev.start + np.arange(len(x)) * DAY_MS  # return i covers [start + i d, start + (i+1) d)
    for yr in A2_YEARS:
        from datetime import datetime, timezone
        a = int(datetime(yr, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
        b = int(datetime(yr + 1, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
        k = (days >= a) & (days < b)
        if k.sum() >= 30:
            out[yr] = dsr_of(x[k], y[k])
    return out


def _a2_gates(ev: Evidence, G: dict, report: bool) -> None:
    m, s, e = ev.m, ev.start, ev.end
    p, bm = ev.r("primary"), ev.r("bench")
    # A2-2 fold breadth (calendar years)
    yrs = _years(ev, p, bm)
    pos = sum(1 for v in yrs.values() if v > 0)
    G["A2-2"] = _gate(PASS if pos >= A2_YEARS_POSITIVE else FAIL, by_year=yrs, positive=pos,
                      required=A2_YEARS_POSITIVE)
    # A2-3 universe breadth (U8; engine in market nodes)
    d8 = dsr_of(ev.r("primary@u8"), ev.r("bench@u8"))
    G["A2-3"] = _gate(PASS if d8 > 0 else FAIL, delta_sr_u8=d8)
    if G["A2-2"]["status"] == FAIL or G["A2-3"]["status"] == FAIL:
        if not report:
            return
    # A2-1 leave-one-coin-out (replay; U12 rebuilt without the coin)
    if ev.override is not None:
        _t, Wp = F.null_weights("A2", m, s, e, [ev.override[1]])
        Wp = Wp[:, 0, :]
    else:
        _t, Wp = F.weights("A2", m, s, e, "primary")
    loo = {}
    for j in F.ever_held(Wp):
        mj = F.without_coin(m, j, 12)
        bj = F.bundle("A2", mj, s, e, ["primary", "bench"], 0, ev.override)
        got = ev.variants({"primary": bj.weights[:, 0, :], "bench": bj.weights[:, 1, :]}, bj, m=mj)
        loo[m.pairs[j]] = dsr_of(got["primary"], got["bench"])
    G["A2-1"] = _gate(PASS if all(math.isfinite(v) and v > 0 for v in loo.values()) else FAIL,
                      leave_one_coin_out=loo)
    # A2-4 schedule breadth (weekday offsets, replay)
    offs = {}
    for wd in range(7):
        named = {}
        for n in ("primary", "bench"):
            if ev.override is not None and n == "primary":
                p_ = F.params_for("A2", "primary") | {"weekday": wd}
                prim = S.a2_weights(m, s, e, p_, mode="primary")
                out = S.a2_weights(m, s, e, p_, mode="null", seeds=[ev.override[1]], k_eff_from=prim["k_eff"])
                t, W = out["exec_times"], out["weights"][:, 0, :]
            else:
                t, W = F._a2(m, s, e, n, 0, weekday=wd)
            named[n] = (t, W)
        slip, exempt = F.slippage("A2", m, s, e)
        base = F.Bundle(named["primary"][0], ["x"], named["primary"][1][:, None, :], slip, exempt, {})
        got = ev.variants({"primary": named["primary"][1], "bench": named["bench"][1]}, base)
        offs[wd] = dsr_of(got["primary"], got["bench"])
    med = float(np.median(list(offs.values())))
    G["A2-4"] = _gate(PASS if med > 0 else FAIL, by_weekday=offs, median=med)


def _a3_gates(ev: Evidence, G: dict, report: bool) -> None:
    m, s, e = ev.m, ev.start, ev.end
    p, bm = ev.r("primary"), ev.r("bench")
    mdd_p, mdd_b = ST.max_drawdown(p), ST.max_drawdown(bm)
    cv_p, cv_b = ST.cvar(p, A3_CVAR_LEVEL), ST.cvar(bm, A3_CVAR_LEVEL)
    G["A3-2"] = _gate(PASS if (mdd_p < mdd_b and cv_p > cv_b) else FAIL, max_drawdown_overlay=mdd_p,
                      max_drawdown_base=mdd_b, cvar5_overlay=cv_p, cvar5_base=cv_b)
    # A3-3 episodes (coverage is C8) and leave-one-episode-out
    if ev.override is None:
        eps = F.a3_episodes(m, s, e, F.params_for("A3", "primary"))
    else:
        eps = _null_episodes(ev)
    loo = {f"{m.pairs[j]}:{a}-{b}": dsr_of(_drop(p, a, b), _drop(bm, a, b)) for j, a, b in eps}
    if len(eps) < COVERAGE_MIN["A3"]:
        st = INC
    else:
        st = PASS if all(math.isfinite(v) and v > 0 for v in loo.values()) else FAIL
    G["A3-3"] = _gate(st, episodes=len(eps), leave_one_episode_out=loo)
    # A3-4 asset breadth
    if ev.override is not None:
        _t, Wp = F.null_weights("A3", m, s, e, [ev.override[1]])
        Wp = Wp[:, 0, :]
    else:
        _t, Wp = F.weights("A3", m, s, e, "primary")
    _t, Wb = F.weights("A3", m, s, e, "bench")
    base = F.bundle("A3", m, s, e, ["bench"])
    named = {}
    for j in sorted(m.funding):
        named[f"{j}:primary"] = F.only_pair(Wp, j)
        named[f"{j}:bench"] = F.only_pair(Wb, j)
    got = ev.variants(named, base)
    per = {m.pairs[j]: dsr_of(got[f"{j}:primary"], got[f"{j}:bench"]) for j in sorted(m.funding)}
    G["A3-4"] = _gate(PASS if all(math.isfinite(v) and v > 0 for v in per.values()) else FAIL, by_asset=per)
    G["A3-5"] = _gate(REP, forgone_return=ST.total_return(bm) - ST.total_return(p))


def _null_episodes(ev: Evidence) -> list[tuple[int, int, int]]:
    m, s, e = ev.m, ev.start, ev.end
    _t, W = F.null_weights("A3", m, s, e, [ev.override[1]])
    _t, Wb = F.weights("A3", m, s, e, "bench")
    cut = (W[:, 0, :] < Wb - 1e-15) & (Wb > 0)
    out = []
    for j in sorted(m.funding):
        out += [(j, a, b) for a, b in S.episodes(cut[:, j])]
    return out


def _reports(ev: Evidence, G: dict) -> None:
    names = ["primary", *F.PERTURBATIONS[ev.fam]]
    mat = np.column_stack([ev.r(n) for n in names])
    G["C11"] = _gate(REP, pbo=ST.pbo(mat, PBO_BLOCKS), configurations=names)
    G["DELISTING_DIAGNOSTICS"] = _gate(REP, **delisting_diagnostics(ev))


def delisting_diagnostics(ev: Evidence) -> dict:
    """POINT_IN_TIME_UNIVERSE_LAW DIAGNOSTICS: the primary and its benchmark replayed with the
    delisting exit at 1.00x and 0.60x of the last archived close instead of the primary 0.80x
    (the terminal bar's prices rescaled). Reported only; never a gate, never a rescue."""
    hits = [(j, t) for j, ts in ev.m.terminal.items() for t in ts if ev.start <= t <= ev.end]
    if not hits:
        return {"delistings_in_window": 0}
    out = {"delistings_in_window": len(hits), "primary_haircut": U_HAIRCUT}
    for h in U_DIAGNOSTIC_HAIRCUTS:
        pr = RP.Prices(ev.prices.times, ev.prices.pairs, ev.prices.open.copy(), ev.prices.high.copy(),
                       ev.prices.low.copy(), ev.prices.close.copy())
        for j, t in hits:
            i = pr.index(t)
            for a in (pr.open, pr.high, pr.low, pr.close):
                a[i, j] *= h / U_HAIRCUT
        alt = Evidence(ev.fam, ev.m, pr, ev.start, ev.end, primary_override=ev.override)
        got = alt._replay(F.bundle(ev.fam, ev.m, ev.start, ev.end, ["primary", "bench"], 0, ev.override),
                          BASE_FEE, ev.start, ev.end)
        ev.replay_calls += 1
        out[f"{h:.2f}x"] = {"total_return_primary": ST.total_return(got["primary"]),
                            "total_return_bench": ST.total_return(got["bench"]),
                            "delta_sr": dsr_of(got["primary"], got["bench"])}
    return out


def _verdict(fam: str, G: dict, early_exit: bool) -> dict:
    statuses = {k: g["status"] for k, g in G.items()}
    if any(v == FAIL for v in statuses.values()):
        verdict = "REJECTED"
    elif any(v in (NE, INC) for v in statuses.values()):
        verdict = "INCONCLUSIVE"
    else:
        verdict = "PRE_HOLM_PASS"
    p = G.get("C3", {}).get("p_value")
    accepted = verdict == "PRE_HOLM_PASS" and p is not None and p <= ALPHA_HOLM / HOLM_M
    return {"family": fam, "verdict": verdict, "gate_status": statuses, "gates": G, "primary_p_value": p,
            "accepted_with_holm_m3": accepted, "complete": not early_exit or verdict == "PRE_HOLM_PASS"}


def holm_node(pvalues: dict[str, float | None]) -> dict:
    """HOLM node: m = 3 fixed; a family not tested enters with p = 1."""
    full = {f: (1.0 if pvalues.get(f) is None else float(pvalues[f])) for f in F.FAMILIES}
    rej = ST.holm(full, ALPHA_HOLM)
    return {"m": HOLM_M, "alpha": ALPHA_HOLM, "p_values": full, "rejected": rej}


def secondary(ev: Evidence) -> dict:
    """C10: secondary-window dSR point estimate > 0 (reject-only)."""
    d = dsr_of(ev.r("primary@sec"), ev.r("bench@sec"))
    return {"status": PASS if d > 0 else FAIL, "delta_sr": d}
