"""AUTH-2 family specifications: every schedule a gate needs, by name (FUNNEL_LAW_2.md
§PRIMARY_CONFIGS, §ROBUSTNESS_PERTURBATIONS, §Matched benchmarks, family gates, §CALIBRATION_DAG).

A *bundle* is a set of named target-weight matrices that share one execution
grid, so the replay evaluator can price all of them in one vectorised call
(each name is one draw). Every weight comes from a generator in signals.py;
nothing here decides a position.

Names used throughout:
    primary, bench              the primary configuration and its matched benchmark
    P1 ... P5                   precommitted robustness perturbations (reject-only)
    null:<seed>                 the family null (C4 distribution and N-Ax)
    loo:<pair>:primary|bench    A1 leave-one-asset-out / A2 leave-one-coin-out
    sleeve:<pair>:primary|bench A1 per-sleeve and A3 per-asset decomposition
    wd<k>:primary|bench         A2 rebalance weekday offset k (0 = Monday)
    u8:primary|bench            A2 U8 universe

PAPER / RESEARCH ONLY: long or cash.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass

import numpy as np

from auth2 import signals as S

FAMILIES = ("A1", "A2", "A3")

PRIMARY = {"A1": S.A1_PRIMARY, "A2": S.A2_PRIMARY, "A3": S.A3_PRIMARY}

PERTURBATIONS = {
    "A1": {"P1": {"lookbacks": [10, 20, 40]}, "P2": {"lookbacks": [40, 120, 250]}, "P3": {"target_vol": 0.15},
           "P4": {"target_vol": 0.40}, "P5": {"vol_window": 60}},
    "A2": {"P1": {"lookback": 14}, "P2": {"lookback": 56}, "P3": {"k": 2}, "P4": {"k": 5}, "P5": {"skip": 0}},
    "A3": {"P1": {"z_threshold": 1.5}, "P2": {"z_threshold": 2.5}, "P3": {"cut_to": 0.0}},
}

# Cumulative family configuration N for DSR (MULTIPLE_TESTING_LAW): A1 inherits 15.
FAMILY_N = {"A1": 21, "A2": 6, "A3": 4}
# Positive-count rule (C7): at least this many perturbations with dSR > 0.
MIN_POSITIVE = {"A1": 4, "A2": 4, "A3": 2}

A2_EXTRA_SLIPPAGE = 0.0005  # +0.05%/side for U12 members ranked 7-12
A2_EXEMPT_RANKS = 6

# Null seeds: the C4 distribution uses 1..1000; the N-Ax fixture is seed 0 and its
# "perturbations" are seeds 1001.. (5 for A1/A2, 3 for A3), all disjoint.
NULL_DRAWS = 1000
C4_SEEDS = list(range(1, NULL_DRAWS + 1))
N_FIXTURE_SEED = 0
N_PERTURBATION_SEEDS = {"A1": [1001, 1002, 1003, 1004, 1005], "A2": [1001, 1002, 1003, 1004, 1005],
                        "A3": [1001, 1002, 1003]}


def params_for(fam: str, name: str) -> dict:
    p = copy.deepcopy(PRIMARY[fam])
    if name in PERTURBATIONS[fam]:
        p.update(PERTURBATIONS[fam][name])
    return p


@dataclass
class Bundle:
    exec_times: np.ndarray
    names: list[str]
    weights: np.ndarray  # (R, D, P)
    extra_slippage: float
    exempt: list
    meta: dict

    def index(self, name: str) -> int:
        return self.names.index(name)


def _stack(t, named: dict[str, np.ndarray], P: int) -> tuple[list[str], np.ndarray]:
    names = list(named)
    W = np.zeros((len(t), len(names), P))
    for d, n in enumerate(names):
        W[:, d, :] = named[n]
    return names, W


# -- per-family generators -------------------------------------------------------


def _a1(m: S.Market, start: int, end: int, name: str, off: int) -> tuple[np.ndarray, np.ndarray]:
    t, W, _ = S.a1_weights(m, start, end, params_for("A1", "primary" if name == "bench" else name),
                           timing=name != "bench", exec_offset_bars=off)
    return t, W


def _a2(m: S.Market, start: int, end: int, name: str, off: int, weekday: int = 0) -> tuple[np.ndarray, np.ndarray]:
    p = params_for("A2", "primary" if name == "bench" else name)
    p["weekday"] = weekday
    if name == "bench":
        prim = S.a2_weights(m, start, end, params_for("A2", "primary") | {"weekday": weekday}, mode="primary",
                            exec_offset_bars=off)
        out = S.a2_weights(m, start, end, p, mode="bench", k_eff_from=prim["k_eff"], exec_offset_bars=off)
    else:
        out = S.a2_weights(m, start, end, p, mode="primary", exec_offset_bars=off)
    return out["exec_times"], out["weights"][:, 0, :]


def _a3(m: S.Market, start: int, end: int, name: str, off: int) -> tuple[np.ndarray, np.ndarray]:
    t, W, _ = S.a3_weights(m, start, end, params_for("A3", "primary" if name == "bench" else name),
                           overlay=name != "bench", exec_offset_bars=off)
    return t, W


def weights(fam: str, m: S.Market, start: int, end: int, name: str, off: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """(exec_times, W (R, P)) of a configuration: primary, bench or a perturbation."""
    return {"A1": _a1, "A2": _a2, "A3": _a3}[fam](m, start, end, name, off)


def null_weights(fam: str, m: S.Market, start: int, end: int, seeds: list[int], off: int = 0):
    """(exec_times, W (R, D, P)) of the family null for ``seeds``."""
    if fam == "A1":
        return S.a1_null_weights(m, start, end, params_for("A1", "primary"), seeds, exec_offset_bars=off)
    if fam == "A2":
        p = params_for("A2", "primary")
        prim = S.a2_weights(m, start, end, p, mode="primary", exec_offset_bars=off)
        out = S.a2_weights(m, start, end, p, mode="null", seeds=seeds, k_eff_from=prim["k_eff"], exec_offset_bars=off)
        return out["exec_times"], out["weights"]
    return S.a3_null_weights(m, start, end, params_for("A3", "primary"), seeds, exec_offset_bars=off)


def slippage(fam: str, m: S.Market, start: int, end: int) -> tuple[float, list]:
    if fam != "A2":
        return 0.0, []
    return A2_EXTRA_SLIPPAGE, S.a2_slippage_exempt(m, start, end, A2_EXEMPT_RANKS)


def bundle(fam: str, m: S.Market, start: int, end: int, names: list[str], off: int = 0,
           primary_override: tuple[str, int] | None = None) -> Bundle:
    """Configurations ``names`` (primary, bench, P1..) on one grid.

    ``primary_override = ("null", seed)`` makes "primary" the null fixture of that seed
    (N-Ax) and each "P<i>" the i-th N perturbation seed."""
    named: dict[str, np.ndarray] = {}
    t_ref = None
    for n in names:
        if primary_override is not None and (n == "primary" or n.startswith("P")):
            seed = primary_override[1] if n == "primary" else N_PERTURBATION_SEEDS[fam][int(n[1:]) - 1]
            t, Wn = null_weights(fam, m, start, end, [seed], off)
            W = Wn[:, 0, :]
        else:
            t, W = weights(fam, m, start, end, n, off)
        if t_ref is None:
            t_ref = t
        elif not np.array_equal(t, t_ref):
            raise ValueError(f"{fam} {n}: execution grid differs within a bundle")
        named[n] = W
    names_, W = _stack(t_ref, named, len(m.pairs))
    slip, exempt = slippage(fam, m, start, end)
    return Bundle(t_ref, names_, W, slip, exempt, {"family": fam, "offset_bars": off})


def null_bundle(fam: str, m: S.Market, start: int, end: int, seeds: list[int], off: int = 0) -> Bundle:
    t, W = null_weights(fam, m, start, end, seeds, off)
    slip, exempt = slippage(fam, m, start, end)
    return Bundle(t, [f"null:{s}" for s in seeds], W, slip, exempt, {"family": fam, "offset_bars": off})


def zero_pair(W: np.ndarray, j: int) -> np.ndarray:
    out = W.copy()
    out[..., j] = 0.0
    return out


def only_pair(W: np.ndarray, j: int) -> np.ndarray:
    out = np.zeros_like(W)
    out[..., j] = W[..., j]
    return out


def ever_held(W: np.ndarray) -> list[int]:
    return [int(j) for j in np.nonzero((W > 0).any(axis=0))[0]]


def without_coin(m: S.Market, coin: int, top: int) -> S.Market:
    """The market with U-membership rebuilt point-in-time without ``coin``: each period's
    members are its ranked eligible candidates minus the coin, first ``top`` (A2-1)."""
    periods = []
    for (a, b, members, ranks), cands in zip(m.periods, m.candidates):
        rest = [c for c in cands if c != coin][:top]
        periods.append((a, b, rest, list(range(1, len(rest) + 1))))
    return S.Market(m.times, m.pairs, m.close, m.real, m.terminal, periods, m.funding, m.candidates)


def u8_market(m: S.Market) -> S.Market:
    """A2-3: the same point-in-time ranking, top 8 (from the ranked candidates)."""
    periods = [(a, b, cands[:8], list(range(1, min(8, len(cands)) + 1)))
               for (a, b, _mem, _rk), cands in zip(m.periods, m.candidates)]
    return S.Market(m.times, m.pairs, m.close, m.real, m.terminal, periods, m.funding, m.candidates)


def coverage_count(fam: str, m: S.Market, start: int, end: int) -> int:
    """C8 operational coverage of the primary in [start, end)."""
    p = params_for(fam, "primary")
    if fam == "A1":
        _t, _W, sig = S.a1_weights(m, start, end, p)
        return int(np.abs(np.diff(sig, axis=0)).sum())
    if fam == "A2":
        out = S.a2_weights(m, start, end, p, mode="primary")
        return int(((out["weights"][:, 0, :] > 0).any(axis=1)).sum())
    return len(a3_episodes(m, start, end, p))


A3_EPISODE_MERGE_DAYS = 30


def a3_episodes(m: S.Market, start: int, end: int, p: dict) -> list[tuple[int, int, int]]:
    """(asset index, first day index, last day index) of overlay episodes in [start, end):
    maximal runs of z > threshold; runs of one asset separated by < 30 days merge (A3-3)."""
    _t, _W, cut = S.a3_weights(m, start, end, p, overlay=True)
    out = []
    for j in sorted(m.funding):
        eps = S.episodes(cut[:, j])
        merged: list[list[int]] = []
        for a, b in eps:
            if merged and a - merged[-1][1] - 1 < A3_EPISODE_MERGE_DAYS:
                merged[-1][1] = b
            else:
                merged.append([a, b])
        out += [(j, a, b) for a, b in merged]
    return out


A1_EPISODE_LOOKBACK = 120
A1_EPISODE_MIN_DAYS = 60


def a1_trend_episodes(m: S.Market, start: int, end: int) -> list[tuple[int, int, int]]:
    """(sign, first day index, last day index) of A1-1 trend episodes in the scored days [start, end).

    Index = U6 equal-weight always-long: its daily return is the mean of the members'
    daily close-to-close returns (members of the period containing the day). The
    episode sign is the sign of the index's trailing 120-day return; an episode is a
    maximal run of constant sign lasting >= 60 days."""
    days = np.arange(start - A1_EPISODE_LOOKBACK * S.DAY_MS, end, S.DAY_MS, dtype=np.int64)
    C = m.daily_close(np.concatenate([[days[0] - S.DAY_MS], days]))
    level = [1.0]
    for i, d in enumerate(days):
        members, _rk, _a, _b = m.members_at(int(d) - S.DAY_MS)
        r = C[i + 1, members] / C[i, members] - 1.0 if members else np.array([])
        r = r[np.isfinite(r)]
        level.append(level[-1] * (1.0 + (r.mean() if r.size else 0.0)))
    level = np.array(level[1:])
    k0 = A1_EPISODE_LOOKBACK
    sign = np.sign(level[k0:] / level[:-k0] - 1.0)  # aligned with scored days [start, end)
    out, a = [], 0
    for i in range(1, len(sign) + 1):
        if i == len(sign) or sign[i] != sign[a]:
            if i - a >= A1_EPISODE_MIN_DAYS and sign[a] != 0:
                out.append((int(sign[a]), a, i - 1))
            a = i
    return out
