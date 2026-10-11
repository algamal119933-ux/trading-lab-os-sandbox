"""Load the Dataset V3 engine data into the generators' Market and the replay's Prices.

The feather files are the exact Freqtrade inputs written by
``dataset_v3.py engine`` (each 4h series checked against the lock's sha256);
membership, candidate rankings, delisting bars and funding come from the
committed lock tables. Nothing here derives anything from a result.

PAPER / RESEARCH ONLY.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from auth2 import replay as RP
from auth2 import signals as S

FOUR_H_MS = 14_400_000
TABLES = "research/datasets/dataset_v3"
GRID_START = int(datetime(2018, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
GRID_END = int(datetime(2026, 9, 1, tzinfo=timezone.utc).timestamp() * 1000)
A3_SYMBOLS = ("BTCUSDT", "ETHUSDT")
KIND_TABLE = {"U6": "membership_u6.json", "U12": "membership_u12.json", "U8": "membership_u8.json"}
FAMILY_KIND = {"A1": "U6", "A2": "U12"}


def _ms(s: str) -> int:
    return int(datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp() * 1000)


def tables(repo: Path) -> dict:
    t = repo / TABLES
    return {name: json.loads((t / f).read_text()) for name, f in
            (("candidates", "candidates.json"), ("engine", "engine_data.json"), ("U6", KIND_TABLE["U6"]),
             ("U12", KIND_TABLE["U12"]), ("U8", KIND_TABLE["U8"]))}


def family_symbols(fam: str, tb: dict) -> list[str]:
    if fam == "A3":
        return list(A3_SYMBOLS)
    kind = FAMILY_KIND[fam]
    syms = {m["symbol"] for p in tb[kind] for m in p["members"]}
    if fam == "A2":
        syms |= {p["eligible"][12][0] for p in tb["U12"] if len(p["eligible"]) > 12}
    return sorted(syms)


def read_bars(engine_dir: Path, pair: str) -> np.ndarray:
    import pandas as pd

    df = pd.read_feather(engine_dir / f"{pair.replace('/', '_')}-4h.feather")
    t = df["date"].dt.as_unit("ms").astype("int64").to_numpy()
    return np.column_stack([t, df[["open", "high", "low", "close", "volume"]].to_numpy(dtype=float)])


def terminal_bars(sym: str, tb: dict) -> set[int]:
    out = set()
    for seg in tb["candidates"]["symbols"][sym]["segments"]:
        if seg["ended_before_dataset_end"] and seg["terminal_trustworthy"]:
            last = _ms(seg["last_utc"])
            if last >= GRID_START:
                out.add(last - last % FOUR_H_MS + FOUR_H_MS)
    return out


def load(fam: str, engine_dir: Path, repo: Path, funding_dir: Path | None = None
         ) -> tuple[S.Market, RP.Prices, dict[str, np.ndarray]]:
    """(Market, Prices, bars) for a family on Dataset V3."""
    tb = tables(repo)
    syms = family_symbols(fam, tb)
    pairs = [tb["engine"]["symbols"][s]["pair"] for s in syms]
    bars = {p: read_bars(engine_dir, p) for p in pairs}
    times = np.arange(GRID_START, GRID_END, FOUR_H_MS, dtype=np.int64)
    prices = RP.fill_like_freqtrade(times, {p: b[:, :5] for p, b in bars.items()}, pairs)
    real = np.zeros((len(times), len(pairs)), dtype=bool)
    for j, p in enumerate(pairs):
        idx = (bars[p][:, 0].astype(np.int64) - GRID_START) // FOUR_H_MS
        idx = idx[(idx >= 0) & (idx < len(times))]
        real[idx, j] = True
    terminal = {j: terminal_bars(s, tb) for j, s in enumerate(syms) if terminal_bars(s, tb)}
    col = {s: j for j, s in enumerate(syms)}
    periods, candidates = [], []
    if fam == "A3":
        periods = [(GRID_START, GRID_END, [0, 1], [1, 2])]
        candidates = [[0, 1]]
    else:
        for p in tb[FAMILY_KIND[fam]]:
            members = [col[m["symbol"]] for m in p["members"]]
            ranks = [m["rank"] for m in p["members"]]
            periods.append((_ms(p["period_start_utc"]), _ms(p["period_end_utc"]), members, ranks))
            cands = []
            for sym, _stat in p["eligible"]:
                if sym not in col:
                    break  # ranked candidates are usable only while every earlier one has data
                cands.append(col[sym])
            candidates.append(cands)
    funding = {}
    if fam == "A3":
        if funding_dir is None:
            raise ValueError("A3 needs the funding series")
        for j, s in enumerate(syms):
            rows = np.loadtxt(funding_dir / f"{s}-funding.csv", delimiter=",", skiprows=1, ndmin=2)
            funding[j] = (rows[:, 0].astype(np.int64), rows[:, 1].astype(float))
    m = S.Market(times, pairs, prices.close, real, terminal, periods, funding, candidates)
    return m, prices, bars


def u8_market(m: S.Market, repo: Path) -> S.Market:
    """A2-3 market: the lock's U8 membership on the A2 pair set."""
    tb = tables(repo)
    col = {p: j for j, p in enumerate(m.pairs)}
    sym_pair = {s: e["pair"] for s, e in tb["engine"]["symbols"].items()}
    periods = []
    for p in tb["U8"]:
        members = [col[sym_pair[x["symbol"]]] for x in p["members"]]
        periods.append((_ms(p["period_start_utc"]), _ms(p["period_end_utc"]), members, [x["rank"] for x in p["members"]]))
    return S.Market(m.times, m.pairs, m.close, m.real, m.terminal, periods, m.funding, [q[2] for q in periods])
