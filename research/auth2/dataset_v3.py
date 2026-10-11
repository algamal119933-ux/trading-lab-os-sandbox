#!/usr/bin/env python3
"""Dataset V3: build, lock and verify (FUNNEL_LAW_2.md §DATA, §POINT_IN_TIME_UNIVERSE_LAW, §A3_VALID_WINDOW).

    build   acquire the archive (checksum-verified, cached), then write the lock
            research/datasets/dataset_v3.lock.json and its tables under
            research/datasets/dataset_v3/ (classification, selections, coverage,
            A3 window, engine data identity)
    verify  rebuild everything from the archive and require every committed
            lock file to be byte-identical (the D0 DATA_LOCK node)
    engine  write the 4h engine data (Freqtrade feather) and funding series for
            a set of symbols, each checked against the lock's content sha256

Market data is never committed (CLAUDE.md); the lock pins its identity. The
same code builds the lock in any environment, so a rebuild on a GitHub runner
is the reproducibility proof.

PAPER / RESEARCH ONLY. No key, no private endpoint, no order.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from auth2 import archive as A  # noqa: E402
from auth2 import universe as U  # noqa: E402

DATASET_ID = "dataset_v3"
SPOT_PREFIX = "data/spot/monthly/klines/"
FUNDING_PREFIX = "data/futures/um/monthly/fundingRate/"
TIMEFRAME = "1h"
LAST_MONTH = "2026-08"
END_MS = U.ms(datetime(2026, 9, 1))  # exclusive
ENGINE_START_MS = U.ms(datetime(2018, 1, 1))
A3_ASSETS = ("BTCUSDT", "ETHUSDT")
FOUR_H_MS = 4 * U.HOUR_MS
COVERAGE_WINDOWS = {
    "scored_2019_2024": (U.ms(datetime(2019, 1, 1)), U.ms(datetime(2025, 1, 1))),
    "secondary_2025_2026_08": (U.ms(datetime(2025, 1, 1)), END_MS),
}
LOCK_REL = "research/datasets/dataset_v3.lock.json"
TABLE_DIR_REL = "research/datasets/dataset_v3"

# Tokenised equities / ETF trackers in the archive (design: track an external
# equity price). Classified as externally-pegged with the commodity-pegged class.
EQUITY_PEGGED = frozenset({
    "AAOIB", "AAPLB", "ADBEB", "AGPUB", "ALABB", "AMATB", "AMCB", "AMDB", "AMZNB", "ARMB", "ASMLB", "ASTSB",
    "AVGOB", "AXTIB", "BABAB", "BMNRB", "BNCB", "CBRSB", "COHRB", "COINB", "CRCLB", "CRDOB", "CRMB", "CRWDB",
    "CRWVB", "CYPHB", "DELLB", "DJTB", "DRAMB", "EWYB", "FLNCB", "FWDIB", "GLWB", "GMEB", "GOOGLB", "GPROB",
    "HIMSB", "HOODB", "HPEB", "IBMB", "INTCB", "INTWB", "IRENB", "KORUB", "LITEB", "METAB", "MRNAB", "MRVLB",
    "MSFTB", "MSTRB", "MUB", "MUUB", "MVLLB", "NBISB", "NFLXB", "NOKB", "NVDAB", "ORCLB", "PDDB", "PLTRB",
    "PYPLB", "QCOMB", "QNTB", "QQQB", "RDDTB", "RKLBB", "SHAZB", "SKHYB", "SMCIB", "SMHB", "SNDKB", "SNXXB",
    "SOXLB", "SOXSB", "SPCXB", "SPYB", "SQQQB", "STXB", "TQQQB", "TSLAB", "TSMB", "USARB", "WDCB", "WENB",
})


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def dumps(obj) -> str:
    return json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def code_sha256() -> dict:
    return {p.name: sha256_bytes(p.read_bytes()) for p in
            (_HERE / "archive.py", _HERE / "universe.py", _HERE / "dataset_v3.py")}


# -- acquisition ---------------------------------------------------------------


def discover(base: str) -> tuple[list[str], dict[str, list[str]], dict[str, list[str]]]:
    """(USDT symbols, kline keys per symbol, funding keys per asset), months <= LAST_MONTH."""
    symbols = sorted(p.split("/")[-2] for p in A.list_bucket(SPOT_PREFIX, True))
    usdt = [s for s in symbols if s.endswith("USDT")]
    from concurrent.futures import ThreadPoolExecutor

    def keys_for(sym: str) -> list[str]:
        ks = A.list_bucket(f"{SPOT_PREFIX}{sym}/{TIMEFRAME}/", False)
        return sorted(k for k in ks if k.endswith(".zip") and k[-11:-4] <= LAST_MONTH)

    with ThreadPoolExecutor(16) as pool:
        kline_keys = dict(zip(usdt, pool.map(keys_for, usdt)))
    kline_keys = {s: k for s, k in kline_keys.items() if k}
    funding_keys = {}
    for s in A3_ASSETS:
        ks = A.list_bucket(f"{FUNDING_PREFIX}{s}/", False)
        funding_keys[s] = sorted(k for k in ks if k.endswith(".zip") and k[-11:-4] <= LAST_MONTH)
    return sorted(kline_keys), kline_keys, funding_keys


def canonical_1h(rows: list[tuple]) -> bytes:
    lines = ["open_ms,open,high,low,close,volume,quote_volume,trades"]
    lines += [f"{r[0]},{r[1]!r},{r[2]!r},{r[3]!r},{r[4]!r},{r[5]!r},{r[6]!r},{r[7]}" for r in rows]
    return ("\n".join(lines) + "\n").encode()


def load_symbol(keys: list[str], cache_dir: Path, base: str) -> tuple[list[tuple], str, dict]:
    """(on-the-hour rows, archive identity sha256, anomalies).

    Exact duplicate rows (every field equal; the archive repeats some, e.g.
    JUVUSDT 2022-03) collapse to one and are counted; duplicates that disagree
    in any field fail DATA_TRUTH.

    The archive holds a few klines whose open time is not on the hour (in
    Dataset V3: 43 rows of each of the six USDT symbols then listed, opening
    about 28 minutes past the hour right after Binance's 2018-02-08/09 outage).
    They are never shifted onto the grid: they are dropped, the hours stay
    missing, and every dropped open time is recorded in the lock.
    anomalies = {"offgrid": [dropped open times], "duplicates": collapsed count}.
    """
    rows: list[tuple] = []
    archive_lines = []
    for k in keys:
        payload = A.fetch_verified(k, cache_dir, base)
        archive_lines.append(f"{Path(k).name} {sha256_bytes(payload)}")
        rows += A.parse_klines(payload, k)
    rows.sort(key=lambda r: r[0])
    rows = [r for r in rows if r[0] < END_MS]
    unique: list[tuple] = []
    duplicates = 0
    for r in rows:
        if unique and unique[-1][0] == r[0]:
            if unique[-1] != r:
                raise SystemExit(f"DATA_TRUTH FAIL: conflicting duplicate kline {r[0]} in {keys[0]}")
            duplicates += 1
            continue
        unique.append(r)
    offgrid = [r[0] for r in unique if r[0] % U.HOUR_MS]
    rows = [r for r in unique if not r[0] % U.HOUR_MS]
    return rows, sha256_bytes(("\n".join(archive_lines) + "\n").encode()), {"offgrid": offgrid, "duplicates": duplicates}


def load_funding(keys: list[str], cache_dir: Path, base: str) -> tuple[list[tuple[int, float]], str]:
    rows: list[tuple[int, float]] = []
    lines = []
    for k in keys:
        payload = A.fetch_verified(k, cache_dir, base)
        lines.append(f"{Path(k).name} {sha256_bytes(payload)}")
        rows += A.parse_funding(payload, k)
    rows.sort()
    rows = [r for r in rows if r[0] < END_MS]
    if len({r[0] for r in rows}) != len(rows):
        raise SystemExit("DATA_TRUTH FAIL: duplicate funding timestamps")
    return rows, sha256_bytes(("\n".join(lines) + "\n").encode())


def canonical_funding(rows: list[tuple[int, float]]) -> bytes:
    return ("calc_ms,rate\n" + "".join(f"{t},{r!r}\n" for t, r in rows)).encode()


# -- derived series -------------------------------------------------------------


def to_4h(rows: list[tuple], segments: list[U.Segment], trust: dict[int, bool]) -> list[tuple]:
    """4h bars from 1h klines, plus one delisting terminal bar per trustworthy ended segment.

    A 4h bar [t, t + 4h) aggregates the 1h klines opening inside it: open of the
    first, max high, min low, close of the last, summed volume. A segment that
    ends before the dataset end with a trustworthy terminal price gets a bar at
    the next 4h boundary with open = high = low = close = 0.80 x the last 1h
    close and zero volume: the frozen delisting exit (FUNNEL_LAW_2 OD-10).
    """
    bars: dict[int, list] = {}
    for r in rows:
        t = r[0] - r[0] % FOUR_H_MS
        b = bars.get(t)
        if b is None:
            bars[t] = [t, r[1], r[2], r[3], r[4], 0.0 + r[5]]
        else:
            b[2] = max(b[2], r[2])
            b[3] = min(b[3], r[3])
            b[4] = r[4]
            b[5] += r[5]
    for seg in segments:
        if (seg.last_ms >= END_MS - U.HOUR_MS or seg.last_ms < ENGINE_START_MS
                or not trust.get(seg.last_ms, False)):
            continue
        last_close = next(r[4] for r in rows if r[0] == seg.last_ms)
        t = seg.last_ms - seg.last_ms % FOUR_H_MS + FOUR_H_MS
        p = U.DELISTING_HAIRCUT * last_close
        bars[t] = [t, p, p, p, p, 0.0]
    return [tuple(bars[t]) for t in sorted(bars)]


def canonical_4h(bars: list[tuple]) -> bytes:
    return ("date_ms,open,high,low,close,volume\n" +
            "".join(f"{b[0]},{b[1]!r},{b[2]!r},{b[3]!r},{b[4]!r},{b[5]!r}\n" for b in bars)).encode()


def reconcile_4h(rows: list[tuple], bars: list[tuple]) -> None:
    """C1 DATA_TRUTH: every non-terminal 4h bar equals the aggregate of its 1h klines."""
    by_bar: dict[int, list[tuple]] = {}
    for r in rows:
        by_bar.setdefault(r[0] - r[0] % FOUR_H_MS, []).append(r)
    for b in bars:
        group = by_bar.get(b[0])
        if group is None:
            if not (b[1] == b[2] == b[3] == b[4] and b[5] == 0.0):
                raise SystemExit(f"RECONCILIATION FAIL: 4h bar {b[0]} has no 1h klines")
            continue
        vol = 0.0
        for g in group:  # left-to-right, as to_4h; never sum(): Python >= 3.12 compensates float sums
            vol += g[5]
        want = (group[0][1], max(g[2] for g in group), min(g[3] for g in group), group[-1][4], vol)
        if tuple(b[1:]) != want:
            raise SystemExit(f"RECONCILIATION FAIL: 4h bar {b[0]} does not equal its 1h aggregate")


def summarise(sym: str, rows: list[tuple]) -> tuple[U.SymbolSummary, dict]:
    open_ms = [r[0] for r in rows]
    vol = [r[5] for r in rows]
    segs = U.segments(open_ms)
    idx = {t: i for i, t in enumerate(open_ms)}
    trust = {s.last_ms: U.terminal_trustworthy(open_ms, vol, idx[s.last_ms]) for s in segs}
    prefix = [0.0]
    for r in rows:
        prefix.append(prefix[-1] + r[6])
    cls, reason = U.classify(sym, EQUITY_PEGGED)
    summary = U.SymbolSummary(sym, cls, tuple(segs), tuple(open_ms), tuple(prefix))
    entry = {
        "class": cls, "class_reason": reason, "rows": len(rows),
        "first_kline_utc": U.iso(open_ms[0]), "last_kline_utc": U.iso(open_ms[-1]),
        "segments": [{"first_utc": U.iso(s.first_ms), "last_utc": U.iso(s.last_ms),
                      "ended_before_dataset_end": s.last_ms < END_MS - U.HOUR_MS,
                      "terminal_trustworthy": trust[s.last_ms]} for s in segs],
    }
    return summary, entry


def day_price_flags(rows: list[tuple]) -> set[int]:
    """Days (ms at 00:00) whose 23:00 kline exists: the daily close is known."""
    return {r[0] - 23 * U.HOUR_MS for r in rows if r[0] % U.DAY_MS == 23 * U.HOUR_MS}


def coverage(membership: list[dict], priced: dict[str, set[int]], seg_info: dict[str, list[dict]]) -> dict:
    """Member-days with and without price data, per window (FUNNEL_LAW_2 A2-5 and its A1 analogue)."""
    out = {}
    for wname, (w0, w1) in COVERAGE_WINDOWS.items():
        covered = convention = missing = 0
        missing_detail: dict[str, int] = {}
        for period in membership:
            p0 = max(_parse(period["period_start_utc"]), w0)
            p1 = min(_parse(period["period_end_utc"]), w1)
            for m in period["members"]:
                seg = next(s for s in seg_info[m["symbol"]] if s["first_utc"] == m["segment_first_utc"])
                seg_last = _parse(seg["last_utc"])
                day = p0
                while day < p1:
                    if day in priced[m["symbol"]] and day <= seg_last:
                        covered += 1
                    elif seg["ended_before_dataset_end"] and day >= seg_last - seg_last % U.DAY_MS:
                        if seg["terminal_trustworthy"]:
                            convention += 1
                        else:
                            missing += 1
                            missing_detail[m["symbol"]] = missing_detail.get(m["symbol"], 0) + 1
                    else:
                        missing += 1
                        missing_detail[m["symbol"]] = missing_detail.get(m["symbol"], 0) + 1
                    day += U.DAY_MS
        total = covered + convention + missing
        out[wname] = {"member_days": total, "with_price": covered, "after_trustworthy_delisting": convention,
                      "without_price": missing, "missing_fraction": (missing / total) if total else None,
                      "missing_by_symbol": dict(sorted(missing_detail.items()))}
    total = sum(v["member_days"] for v in out.values())
    miss = sum(v["without_price"] for v in out.values())
    frac = miss / total if total else None
    out["all_windows"] = {"member_days": total, "without_price": miss, "missing_fraction": frac,
                          "data_limited": bool(frac is None or frac > U.DATA_LIMITED_THRESHOLD),
                          "rule": "DATA_LIMITED iff member-days without price data > 1.0% of all member-days"}
    return out


def _parse(s: str) -> int:
    return U.ms(datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ"))


def a3_window(funding: dict[str, list[tuple[int, float]]]) -> dict:
    f0 = {s: rows[0][0] for s, rows in funding.items()}
    ready = {s: t + (365 + 7) * U.DAY_MS for s, t in f0.items()}
    r = max(ready.values())
    d = datetime.fromtimestamp(r / 1000, tz=timezone.utc)
    start = datetime(d.year, d.month, 1, tzinfo=timezone.utc)
    if start.timestamp() * 1000 < r:
        start = datetime(d.year + (d.month == 12), d.month % 12 + 1, 1, tzinfo=timezone.utc)
    folds = []
    cur = start
    while cur.year <= 2024:
        folds.append({"start_utc": cur.strftime("%Y-%m-%d"), "end_utc": f"{cur.year}-12-31"})
        cur = datetime(cur.year + 1, 1, 1, tzinfo=timezone.utc)
    first_len = (datetime(start.year + 1, 1, 1, tzinfo=timezone.utc) - start).days
    merged = False
    if folds and first_len < 183 and len(folds) > 1:
        folds[1]["start_utc"] = folds[0]["start_utc"]
        folds = folds[1:]
        merged = True
    complete = len(folds)
    return {
        "f0_utc": {s: U.iso(t) for s, t in f0.items()},
        "ready_utc": {s: U.iso(t) for s, t in ready.items()},
        "a3_start_utc": start.strftime("%Y-%m-%dT%H:%M:%SZ"), "a3_end_utc": "2024-12-31T23:59:59Z",
        "first_stub_days": first_len, "first_stub_merged": merged, "folds": folds,
        "complete_folds": complete, "data_limited": complete < 3,
        "rule": "READY = f0 + 365 + 7 days; A3_START = first 00:00 UTC month start >= max READY; calendar-year "
                "folds; a first segment < 183 days merges into the next year; >= 3 folds else DATA_LIMITED",
    }


# -- build / verify -----------------------------------------------------------------


def build(cache_dir: Path, base: str, out_root: Path) -> dict[str, bytes]:
    """Every lock file as bytes, keyed by repository-relative path."""
    symbols, kline_keys, funding_keys = discover(base)
    summaries, entries, priced, rows_by = [], {}, {}, {}
    archive_files = 0
    for i, sym in enumerate(symbols):
        rows, archive_sha, anomalies = load_symbol(kline_keys[sym], cache_dir, base)
        archive_files += len(kline_keys[sym])
        if not rows:
            continue
        s, e = summarise(sym, rows)
        e["archive_months"] = [kline_keys[sym][0][-11:-4], kline_keys[sym][-1][-11:-4], len(kline_keys[sym])]
        e["archive_sha256"] = archive_sha
        e["normalized_1h_sha256"] = sha256_bytes(canonical_1h(rows))
        if anomalies["offgrid"]:
            e["offgrid_rows_dropped_open_ms"] = anomalies["offgrid"]
        if anomalies["duplicates"]:
            e["exact_duplicate_rows_collapsed"] = anomalies["duplicates"]
        summaries.append(s)
        entries[sym] = e
        priced[sym] = day_price_flags(rows)
        rows_by[sym] = rows
        if i % 100 == 0:
            print(f"  {i}/{len(symbols)} {sym}", flush=True)

    memberships = {k: U.build_membership(summaries, k, END_MS) for k in ("U6", "U12", "U8")}
    seg_info = {s: e["segments"] for s, e in entries.items()}
    cov = {"A1_U6": coverage(memberships["U6"], priced, seg_info),
           "A2_U12": coverage(memberships["U12"], priced, seg_info),
           "A2_U8": coverage(memberships["U8"], priced, seg_info)}

    # Engine data: every member of U6/U12/U8, the A3 assets, and each U12 period's
    # 13th eligible coin, which replaces a removed coin in the A2-1 leave-one-coin-out
    # rebuild (replay evaluator; FUNNEL_LAW_2.md §A2_SPECIFIC_GATES).
    engine_symbols = sorted({m["symbol"] for k in memberships for p in memberships[k] for m in p["members"]}
                            | {p["eligible"][12][0] for p in memberships["U12"] if len(p["eligible"]) > 12}
                            | set(A3_ASSETS))
    engine = {}
    for sym in engine_symbols:
        rows = [r for r in rows_by[sym] if r[0] >= ENGINE_START_MS]
        segs = [g for g in summaries if g.symbol == sym][0].segments
        idx = {r[0]: i for i, r in enumerate(rows_by[sym])}
        vol = [r[5] for r in rows_by[sym]]
        om = [r[0] for r in rows_by[sym]]
        trust = {g.last_ms: U.terminal_trustworthy(om, vol, idx[g.last_ms]) for g in segs}
        bars = to_4h(rows, list(segs), trust)
        reconcile_4h(rows, bars)
        engine[sym] = {"pair": f"{sym[:-4]}/USDT", "bars_4h": len(bars),
                       "content_sha256_4h": sha256_bytes(canonical_4h(bars)),
                       "first_utc": U.iso(bars[0][0]), "last_utc": U.iso(bars[-1][0])}

    funding, funding_entries = {}, {}
    for s in A3_ASSETS:
        rows, archive_sha = load_funding(funding_keys[s], cache_dir, base)
        funding[s] = rows
        funding_entries[s] = {"rows": len(rows), "first_utc": U.iso(rows[0][0]), "last_utc": U.iso(rows[-1][0]),
                              "archive_files": len(funding_keys[s]), "archive_sha256": archive_sha,
                              "content_sha256": sha256_bytes(canonical_funding(rows))}
    a3 = a3_window(funding)

    tables = {
        "candidates.json": {"symbols": entries},
        "membership_u6.json": memberships["U6"],
        "membership_u12.json": memberships["U12"],
        "membership_u8.json": memberships["U8"],
        "coverage.json": cov,
        "a3_window.json": a3,
        "engine_data.json": {"symbols": engine, "funding": funding_entries},
    }
    files = {f"{TABLE_DIR_REL}/{name}": dumps(obj).encode() for name, obj in tables.items()}
    lock = {
        "dataset_id": DATASET_ID,
        "status": "frozen",
        "program": "AUTH-2-DISCOVERY-QUALIFICATION-1",
        "law": "research/auth2/FUNNEL_LAW_2.md §DATA, §POINT_IN_TIME_UNIVERSE_LAW, §A3_VALID_WINDOW",
        "exchange": "binance", "market_type": "spot", "quote": "USDT", "timeframe": TIMEFRAME,
        "engine_timeframe": "4h (derived from 1h; reconciliation gate in research/auth2/dataset_v3.py)",
        "window_utc": {"klines": ["archive start", "2026-08-31T23:59:59Z"], "engine_data_from": "2018-01-01T00:00:00Z"},
        "source": {"archive": "https://data.binance.vision (bucket data.binance.vision)",
                   "kline_prefix": SPOT_PREFIX, "funding_prefix": FUNDING_PREFIX,
                   "last_month": LAST_MONTH, "checksum": "every zip verified against its published .CHECKSUM"},
        "counts": {"usdt_symbols_with_klines": len(entries), "kline_archive_files": archive_files,
                   "funding_archive_files": sum(len(v) for v in funding_keys.values()),
                   "engine_symbols": len(engine_symbols)},
        "classification_counts": _counts(entries),
        "data_limited": {"A1": cov["A1_U6"]["all_windows"]["data_limited"],
                         "A2": cov["A2_U12"]["all_windows"]["data_limited"],
                         "A3": a3["data_limited"]},
        "a3_start_utc": a3["a3_start_utc"],
        "tables_sha256": {p: sha256_bytes(b) for p, b in sorted(files.items())},
        "generator_code_sha256": code_sha256(),
        "market_data_committed": False,
        "real_money_authorized": False,
    }
    files[LOCK_REL] = dumps(lock).encode()
    return files


def _counts(entries: dict) -> dict:
    out: dict[str, int] = {}
    for e in entries.values():
        out[e["class"]] = out.get(e["class"], 0) + 1
    return dict(sorted(out.items()))


def engine_data(symbols: list[str], cache_dir: Path, base: str, out_dir: Path, repo: Path) -> dict:
    """Write Freqtrade 4h feather files + funding CSVs for ``symbols``, each sha256-checked against the lock."""
    import pandas as pd

    lock_engine = json.loads((repo / TABLE_DIR_REL / "engine_data.json").read_text())
    cands = json.loads((repo / TABLE_DIR_REL / "candidates.json").read_text())["symbols"]
    _, kline_keys, funding_keys = discover(base)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = {}
    for sym in symbols:
        rows_all, _, _ = load_symbol(kline_keys[sym], cache_dir, base)
        if sha256_bytes(canonical_1h(rows_all)) != cands[sym]["normalized_1h_sha256"]:
            raise SystemExit(f"DATA_TRUTH FAIL: {sym} 1h content differs from the lock")
        s, _e = summarise(sym, rows_all)
        idx = {r[0]: i for i, r in enumerate(rows_all)}
        om, vol = [r[0] for r in rows_all], [r[5] for r in rows_all]
        trust = {g.last_ms: U.terminal_trustworthy(om, vol, idx[g.last_ms]) for g in s.segments}
        rows = [r for r in rows_all if r[0] >= ENGINE_START_MS]
        bars = to_4h(rows, list(s.segments), trust)
        reconcile_4h(rows, bars)
        sha = sha256_bytes(canonical_4h(bars))
        if sha != lock_engine["symbols"][sym]["content_sha256_4h"]:
            raise SystemExit(f"DATA_TRUTH FAIL: {sym} 4h content differs from the lock")
        df = pd.DataFrame(bars, columns=["date", "open", "high", "low", "close", "volume"])
        df["date"] = pd.to_datetime(df["date"], unit="ms", utc=True)
        pair = lock_engine["symbols"][sym]["pair"]
        df.to_feather(out_dir / f"{pair.replace('/', '_')}-4h.feather")
        written[sym] = sha
    for s in A3_ASSETS:
        rows, _ = load_funding(funding_keys[s], cache_dir, base)
        body = canonical_funding(rows)
        if sha256_bytes(body) != lock_engine["funding"][s]["content_sha256"]:
            raise SystemExit(f"DATA_TRUTH FAIL: {s} funding content differs from the lock")
        (out_dir / f"{s}-funding.csv").write_bytes(body)
    return written


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=("build", "verify", "engine"))
    ap.add_argument("--cache-dir", required=True)
    ap.add_argument("--base", default=A.DEFAULT_BASE)
    ap.add_argument("--repo", default=".")
    ap.add_argument("--out-dir", help="engine: where the feather files go")
    ap.add_argument("--symbols", nargs="*", help="engine: symbols (default: every engine symbol in the lock)")
    args = ap.parse_args(argv)
    repo = Path(args.repo).resolve()
    cache = Path(args.cache_dir)
    if args.command == "engine":
        syms = args.symbols or sorted(json.loads((repo / TABLE_DIR_REL / "engine_data.json").read_text())["symbols"])
        written = engine_data(syms, cache, args.base, Path(args.out_dir), repo)
        print(f"ENGINE_DATA = PASS ({len(written)} symbols, every 4h and funding sha256 equals the lock)")
        return 0
    files = build(cache, args.base, repo)
    if args.command == "build":
        for rel, body in files.items():
            (repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (repo / rel).write_bytes(body)
            print(f"wrote {rel} sha256={sha256_bytes(body)}")
        return 0
    bad = [rel for rel, body in files.items() if not (repo / rel).is_file() or (repo / rel).read_bytes() != body]
    for rel in bad:
        print(f"FAIL  {rel} is not byte-identical to the rebuild")
    print("DATASET_V3_LOCK = " + ("FAIL" if bad else "PASS"))
    return 2 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
