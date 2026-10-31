"""P3-PLN-07 data-truth audits over recorded evidence (master plan §13; contract §4).

Two read-only verifiers that close named gaps of docs/p3/PLN_07_DATA_TRUTH_COVERAGE.md:

G-1  ``audit_input_ledger``  — the missing-bar audit of a captured input ledger. For each frozen pair it
     reports missing, duplicate, out-of-order and off-grid bars on the frozen timeframe, plus records of a
     foreign pair or timeframe. Each missing bar is classified against what the lane itself recorded, in
     the categories the P2 closure audit used by hand (P2_CLOSURE §4): ``EXPLAINED_INPUT_REJECTED``,
     ``EXPLAINED_FETCH_FAILURE``, ``EXPLAINED_DOWNTIME_THEN_RESTART`` or ``UNEXPLAINED``. Contract §4:
     a missing candle is *recorded, never filled*, so a gap with an incident behind it is compliant and an
     unexplained gap is a finding.
G-2  ``compare_feeds``  — a pure comparator of two recorded bar sequences of one pair, the captured live
     input (L) and the engine's feed (F), per bar timestamp. The contract states no tolerance, so the
     comparison is exact. A value mismatch, a bar on one side only, a duplicate or an off-grid bar is a
     finding. It never fetches anything: both sides are recordings handed to it.

Reuse (contract §2 priority 2): ledger reading and chain verification are ``fp.ledger``; the market
event identity and the timeframe table are ``fp.market``; the live-side candle extraction is
``fp.replay.candles_from_input_ledger``; gap clustering and UTC parsing are ``audit_data.gap_clusters``
and ``audit_data.to_ms``. ``research/fp`` is the frozen FP runtime tree and is not changed.

Fail-closed: every finding the law names is always emitted, and a finding that could not be
established is ``UNPROVEN``, which withholds PASS exactly as FAIL does. Read-only: nothing here
writes, repairs, fills or fetches. PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import math
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for _extra in (str(REPO_ROOT / "research"), str(REPO_ROOT / "scripts")):
    if _extra not in sys.path:
        sys.path.insert(0, _extra)

import audit_data  # noqa: E402
from fp import ledger as fp_ledger  # noqa: E402
from fp import market as fp_market  # noqa: E402
from fp import replay as fp_replay  # noqa: E402

AUDIT_VERSION = "P3_DATA_TRUTH_V1"
PASS, FAIL, UNPROVEN = "PASS", "FAIL", "UNPROVEN"
MAX_EXAMPLES = 10
OHLCV = ("open", "high", "low", "close", "volume")

# The findings each audit always emits, named once so the set is a law (as reconcile.EXPECTED_FINDINGS).
LEDGER_FINDINGS = (
    "ledger_readable",
    "ledger_chain_integrity",
    "record_shape",
    "timeframe_conformance",
    "universe_conformance",
    "bar_alignment",
    "bar_ordering",
    "bar_uniqueness",
    "missing_bars",
)
FEED_FINDINGS = (
    "rows_readable",
    "bar_alignment",
    "bar_uniqueness",
    "bar_coverage",
    "value_equality",
)

# Missing-bar classes, in precedence order (P2_CLOSURE §4 used the last three by hand).
INPUT_REJECTED = "EXPLAINED_INPUT_REJECTED"
FETCH_FAILURE = "EXPLAINED_FETCH_FAILURE"
DOWNTIME_THEN_RESTART = "EXPLAINED_DOWNTIME_THEN_RESTART"
UNEXPLAINED = "UNEXPLAINED"
GAP_CLASSES = (INPUT_REJECTED, FETCH_FAILURE, DOWNTIME_THEN_RESTART, UNEXPLAINED)


class DataTruthError(RuntimeError):
    """Recorded evidence could not be read; the caller reports UNPROVEN, never PASS."""


def _finding(check: str, result: str, detail: str, count: int = 0) -> dict:
    return {"check": check, "result": result, "detail": detail, "count": count}


def overall(findings: list[dict], expected: tuple[str, ...]) -> str:
    """FAIL beats UNPROVEN beats PASS; a missing or extra finding is FAIL (a check that stopped running)."""
    if sorted(f["check"] for f in findings) != sorted(expected):
        return FAIL
    results = {f["result"] for f in findings}
    if FAIL in results:
        return FAIL
    if results != {PASS}:
        return UNPROVEN
    return PASS


def _step_ms(timeframe: str) -> int:
    if timeframe not in fp_market.TIMEFRAME_MS:
        raise DataTruthError(f"unsupported timeframe {timeframe!r}; known: {sorted(fp_market.TIMEFRAME_MS)}")
    return fp_market.TIMEFRAME_MS[timeframe]


def _int_ts(value) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _incident_ms(record) -> int | None:
    for stamp in (record.payload.get("observed_utc"), record.recorded_utc):
        if isinstance(stamp, str):
            try:
                return audit_data.to_ms(stamp)
            except ValueError:
                continue
    return None


def _read_ledger(ledgers: dict, kind: str) -> list:
    try:
        return ledgers[kind].records()
    except fp_ledger.LedgerError as exc:
        raise DataTruthError(f"{kind} ledger unreadable: {exc}") from exc


# --------------------------------------------------------------------------------------------------
# G-1: missing-bar audit of a captured input ledger
# --------------------------------------------------------------------------------------------------

def audit_input_ledger(
    evidence_dir: Path,
    *,
    pairs: list[str],
    timeframe: str,
    start_ms: int | None = None,
    end_ms: int | None = None,
) -> dict:
    """Audit one lane's input ledger against the frozen pairs and timeframe. Read-only.

    The expected grid per pair runs from ``start_ms`` (else the pair's first captured bar) to ``end_ms``
    (else its last), both snapped inward to the timeframe grid; the audit cannot know about bars before
    the first capture unless the caller names the window, so the cohort window should be passed.

    A missing bar's *opportunity* runs from its close until the lane demonstrably moved past it: the
    receipt of the next bar captured for that pair (the capture loop never writes an older bar after a
    newer one). An incident recorded inside that opportunity explains the miss.
    """
    step = _step_ms(timeframe)
    report = {
        "audit_version": AUDIT_VERSION,
        "audit": "captured_input_ledger_bars",
        "evidence_dir": str(evidence_dir),
        "pairs": list(pairs),
        "timeframe": timeframe,
        "window": {"start_ms": start_ms, "end_ms": end_ms},
        "per_pair": {},
        "findings": [],
        "result": UNPROVEN,
        "real_money_authorized": False,
    }

    def finish(findings: list[dict]) -> dict:
        report["findings"] = findings
        report["result"] = overall(findings, LEDGER_FINDINGS)
        return report

    def not_evaluated(reason: str) -> list[dict]:
        return [_finding(name, UNPROVEN, f"not evaluated: {reason}") for name in LEDGER_FINDINGS[1:]]

    if not pairs:
        return finish([_finding("ledger_readable", UNPROVEN, "no frozen pair was named")]
                      + not_evaluated("no frozen pair was named"))
    directory = Path(evidence_dir)
    if not directory.is_dir():
        reason = f"{directory} is not a readable evidence directory"
        return finish([_finding("ledger_readable", UNPROVEN, reason)] + not_evaluated(reason))
    try:
        ledgers = fp_ledger.open_ledgers(directory)
        inputs = _read_ledger(ledgers, "input")
        incidents = _read_ledger(ledgers, "incident")
    except DataTruthError as exc:
        return finish([_finding("ledger_readable", UNPROVEN, str(exc))] + not_evaluated(str(exc)))
    live_inputs = [r for r in inputs if not r.payload.get("erratum")]
    if not live_inputs:
        reason = "the input ledger holds no live record, so no bar can be audited"
        return finish([_finding("ledger_readable", UNPROVEN, reason)] + not_evaluated(reason))
    findings = [_finding("ledger_readable", PASS,
                         f"{len(live_inputs)} live input record(s), {len(incidents)} incident record(s)",
                         len(live_inputs))]

    chain = [f"input: {p}" for p in ledgers["input"].verify()] + \
            [f"incident: {p}" for p in ledgers["incident"].verify()]
    findings.append(_finding(
        "ledger_chain_integrity", FAIL if chain else PASS,
        "; ".join(chain[:3]) if chain else "the input and incident chains verify from genesis",
        len(chain)))

    # Shape, timeframe and universe, record by record, in ledger order.
    malformed, wrong_tf, foreign = [], [], []
    by_pair: dict[str, list[tuple[int, int, int | None]]] = {pair: [] for pair in pairs}
    for record in live_inputs:
        payload = record.payload
        candle = payload.get("candle") if isinstance(payload.get("candle"), dict) else {}
        ts = _int_ts(candle.get("ts"))
        pair = payload.get("pair")
        if ts is None or not isinstance(pair, str):
            malformed.append(record.seq)
            continue
        if payload.get("timeframe") != timeframe:
            wrong_tf.append({"seq": record.seq, "timeframe": payload.get("timeframe")})
            continue
        if pair not in by_pair:
            foreign.append({"seq": record.seq, "pair": pair})
            continue
        by_pair[pair].append((record.seq, ts, _int_ts(payload.get("receive_ts_ms"))))

    findings.append(_finding(
        "record_shape", FAIL if malformed else PASS,
        f"input records with no integer candle ts or no pair: seq {malformed[:MAX_EXAMPLES]}" if malformed
        else "every live input record carries a pair and an integer candle ts", len(malformed)))
    findings.append(_finding(
        "timeframe_conformance", FAIL if wrong_tf else PASS,
        f"records on a timeframe other than {timeframe}: {wrong_tf[:MAX_EXAMPLES]}" if wrong_tf
        else f"every live input record is on the frozen timeframe {timeframe}", len(wrong_tf)))
    absent = [pair for pair, rows in by_pair.items() if not rows]
    if foreign:
        universe = _finding("universe_conformance", FAIL,
                            f"records of a pair outside the frozen universe {list(pairs)}: {foreign[:MAX_EXAMPLES]}",
                            len(foreign))
    elif absent:
        universe = _finding("universe_conformance", UNPROVEN,
                            f"frozen pair(s) {absent} have no captured bar, so their coverage cannot be shown",
                            len(absent))
    else:
        universe = _finding("universe_conformance", PASS,
                            f"every record is a frozen pair, and each of {list(pairs)} has captured bars")
    findings.append(universe)

    rejected_events = {r.payload.get("market_event_id") for r in incidents
                       if r.payload.get("category") == "input_rejected" and r.payload.get("market_event_id")}
    fetch_failures: dict[str | None, list[int]] = {}
    restarts: list[int] = []
    for record in incidents:
        category = record.payload.get("category")
        when = _incident_ms(record)
        if when is None:
            continue  # an incident with no readable time explains nothing (fail-closed: the bar stays UNEXPLAINED)
        if category == "market_fetch_failed":
            fetch_failures.setdefault(record.payload.get("pair"), []).append(when)
        elif category == "run_started":
            restarts.append(when)

    off_grid, out_of_order, duplicates = [], [], []
    total_missing = 0
    unexplained_total = 0
    for pair, rows in by_pair.items():
        if not rows:
            report["per_pair"][pair] = {"captured": 0, "expected": None, "missing": None}
            continue
        newest = None
        seen = Counter()
        for seq, ts, _ in rows:
            if ts % step:
                off_grid.append({"pair": pair, "seq": seq, "ts_utc": audit_data.iso(ts)})
            seen[ts] += 1
            if newest is not None and ts < newest:
                out_of_order.append({"pair": pair, "seq": seq, "ts_utc": audit_data.iso(ts)})
            newest = ts if newest is None else max(newest, ts)
        duplicates.extend({"pair": pair, "ts_utc": audit_data.iso(ts), "copies": n}
                          for ts, n in sorted(seen.items()) if n > 1)

        aligned = sorted({ts for _, ts, _ in rows if ts % step == 0})
        if not aligned:
            report["per_pair"][pair] = {"captured": len(rows), "expected": None, "missing": None}
            continue
        first = aligned[0] if start_ms is None else -(-start_ms // step) * step
        last = aligned[-1] if end_ms is None else (end_ms // step) * step
        present = {ts for ts in aligned if first <= ts <= last}
        expected = (last - first) // step + 1 if last >= first else 0
        missing = [ts for ts in range(first, last + 1, step) if ts not in present] if expected else []
        receipts = sorted((ts, rcv) for _, ts, rcv in rows)
        pair_failures = sorted(fetch_failures.get(pair, []) + fetch_failures.get(None, []))

        classes = Counter()
        unexplained = []
        for ts in missing:
            close = ts + step
            horizon = next((rcv if rcv is not None else captured_ts + step
                            for captured_ts, rcv in receipts if captured_ts > ts), math.inf)
            if fp_market.market_event_id(pair, timeframe, ts) in rejected_events:
                cls = INPUT_REJECTED
            elif any(close <= when <= horizon for when in pair_failures):
                cls = FETCH_FAILURE
            elif any(close <= when <= horizon for when in restarts):
                cls = DOWNTIME_THEN_RESTART
            else:
                cls = UNEXPLAINED
                unexplained.append(audit_data.iso(ts))
            classes[cls] += 1
        total_missing += len(missing)
        unexplained_total += len(unexplained)
        report["per_pair"][pair] = {
            "captured": len(present),
            "expected": expected,
            "missing": len(missing),
            "window_utc": [audit_data.iso(first), audit_data.iso(last)] if expected else None,
            "gap_clusters": audit_data.gap_clusters(present, first, last, step)[:audit_data.MAX_GAP_CLUSTERS]
            if expected else [],
            "classification": {cls: classes.get(cls, 0) for cls in GAP_CLASSES},
            "unexplained_bars_utc": unexplained[:MAX_EXAMPLES],
        }

    findings.append(_finding(
        "bar_alignment", FAIL if off_grid else PASS,
        f"bars off the {timeframe} grid: {off_grid[:MAX_EXAMPLES]}" if off_grid
        else f"every captured bar opens on the {timeframe} grid", len(off_grid)))
    findings.append(_finding(
        "bar_ordering", FAIL if out_of_order else PASS,
        f"bars recorded after a newer bar of the same pair: {out_of_order[:MAX_EXAMPLES]}" if out_of_order
        else "each pair's bars were recorded in event-time order", len(out_of_order)))
    findings.append(_finding(
        "bar_uniqueness", FAIL if duplicates else PASS,
        f"bars captured more than once: {duplicates[:MAX_EXAMPLES]}" if duplicates
        else "every (pair, bar) is captured at most once", len(duplicates)))
    if absent or any(v.get("expected") is None for v in report["per_pair"].values()):
        gaps = _finding("missing_bars", UNPROVEN,
                        "at least one frozen pair has no on-grid captured bar, so its grid is unknown",
                        total_missing)
    elif unexplained_total:
        gaps = _finding("missing_bars", FAIL,
                        f"{unexplained_total} of {total_missing} missing bar(s) have no recorded incident "
                        "(input_rejected, market_fetch_failed or run_started) inside their capture opportunity",
                        unexplained_total)
    else:
        gaps = _finding("missing_bars", PASS,
                        f"{total_missing} missing bar(s), each with a recorded incident; none was filled"
                        if total_missing else "no bar is missing inside the window", total_missing)
    findings.append(gaps)
    return finish(findings)


# --------------------------------------------------------------------------------------------------
# G-2: live-feed vs engine-feed per-bar comparator
# --------------------------------------------------------------------------------------------------

def _bars(rows, side: str, step: int) -> tuple[dict[int, tuple], list[dict], list[dict], list[dict]]:
    """(bars by ts, unreadable rows, off-grid rows, duplicate ts) for one recorded side."""
    bars: dict[int, tuple] = {}
    unreadable, off_grid, duplicates = [], [], []
    counts = Counter()
    for index, row in enumerate(rows if isinstance(rows, list) else []):
        ts = _int_ts(row.get("ts")) if isinstance(row, dict) else None
        try:
            values = tuple(float(row[field]) for field in OHLCV) if ts is not None else None
        except (KeyError, TypeError, ValueError):
            values = None
        if ts is None or values is None or any(math.isnan(v) or math.isinf(v) for v in values):
            unreadable.append({"side": side, "index": index})
            continue
        if ts % step:
            off_grid.append({"side": side, "ts_utc": audit_data.iso(ts)})
            continue
        counts[ts] += 1
        if ts in bars and bars[ts] != values:
            bars[ts] = None  # conflicting copies: the side does not say what this bar was
        elif ts not in bars:
            bars[ts] = values
    if not isinstance(rows, list):
        unreadable.append({"side": side, "index": None, "reason": "not a list of rows"})
    duplicates = [{"side": side, "ts_utc": audit_data.iso(ts), "copies": n} for ts, n in sorted(counts.items()) if n > 1]
    return bars, unreadable, off_grid, duplicates


def compare_feeds(
    live_rows: list[dict],
    engine_rows: list[dict],
    *,
    pair: str,
    timeframe: str,
    start_ms: int | None = None,
    end_ms: int | None = None,
) -> dict:
    """Compare two recorded bar sequences of one pair, bar by bar, exactly. Pure; nothing is fetched.

    Each row is ``{"ts": <open time, int UTC ms>, "open", "high", "low", "close", "volume"}``, the shape
    of the ``candle`` object of an input-ledger record. ``start_ms``/``end_ms`` bound both sides by the
    same explicit window; without them every recorded bar on either side is in scope.
    """
    step = _step_ms(timeframe)
    live, l_bad, l_off, l_dup = _bars(live_rows, "live", step)
    engine, e_bad, e_off, e_dup = _bars(engine_rows, "engine", step)

    def in_window(ts: int) -> bool:
        return (start_ms is None or ts >= start_ms) and (end_ms is None or ts <= end_ms)

    live = {ts: v for ts, v in live.items() if in_window(ts)}
    engine = {ts: v for ts, v in engine.items() if in_window(ts)}
    only_live = sorted(set(live) - set(engine))
    only_engine = sorted(set(engine) - set(live))
    common = sorted(set(live) & set(engine))

    mismatches = []
    ambiguous = []
    for ts in common:
        if live[ts] is None or engine[ts] is None:
            ambiguous.append(audit_data.iso(ts))
            continue
        for field, a, b in zip(OHLCV, live[ts], engine[ts]):
            if a != b:
                mismatches.append({"ts_utc": audit_data.iso(ts), "field": field, "live": a, "engine": b})

    findings = []
    bad = l_bad + e_bad
    findings.append(_finding(
        "rows_readable", UNPROVEN if bad else PASS,
        f"rows with no integer ts or no finite OHLCV: {bad[:MAX_EXAMPLES]}" if bad
        else f"{len(live_rows or [])} live and {len(engine_rows or [])} engine rows read", len(bad)))
    off = l_off + e_off
    findings.append(_finding(
        "bar_alignment", FAIL if off else PASS,
        f"bars off the {timeframe} grid: {off[:MAX_EXAMPLES]}" if off else f"every bar opens on the {timeframe} grid",
        len(off)))
    dup = l_dup + e_dup
    findings.append(_finding(
        "bar_uniqueness", FAIL if dup else PASS,
        f"bars recorded more than once on one side: {dup[:MAX_EXAMPLES]}" if dup
        else "each side records each bar at most once", len(dup)))
    if only_live or only_engine:
        coverage = _finding(
            "bar_coverage", FAIL,
            f"live-only bars {[audit_data.iso(t) for t in only_live[:MAX_EXAMPLES]]}; "
            f"engine-only bars {[audit_data.iso(t) for t in only_engine[:MAX_EXAMPLES]]}",
            len(only_live) + len(only_engine))
    elif not common:
        coverage = _finding("bar_coverage", UNPROVEN, "neither side holds a bar in scope; nothing was compared")
    else:
        coverage = _finding("bar_coverage", PASS, f"both sides hold the same {len(common)} bar(s)", len(common))
    findings.append(coverage)
    if mismatches or ambiguous:
        equality = _finding(
            "value_equality", FAIL,
            f"value mismatches {mismatches[:MAX_EXAMPLES]}; bars with conflicting copies {ambiguous[:MAX_EXAMPLES]}",
            len(mismatches) + len(ambiguous))
    elif not common:
        equality = _finding("value_equality", UNPROVEN, "no common bar, so no value was compared")
    else:
        equality = _finding("value_equality", PASS,
                            f"OHLCV identical on all {len(common)} common bar(s) (exact; the contract states "
                            "no tolerance)", len(common))
    findings.append(equality)
    return {
        "audit_version": AUDIT_VERSION,
        "audit": "live_vs_engine_feed",
        "pair": pair,
        "timeframe": timeframe,
        "tolerance": "exact",
        "window": {"start_ms": start_ms, "end_ms": end_ms},
        "bars": {"live": len(live), "engine": len(engine), "common": len(common)},
        "findings": findings,
        "result": overall(findings, FEED_FINDINGS),
        "real_money_authorized": False,
    }


def live_rows_from_input_ledger(evidence_dir: Path, pair: str) -> list[dict]:
    """The captured live bars of ``pair``, read through ``fp.ledger`` and ``fp.replay``. Read-only."""
    directory = Path(evidence_dir)
    if not directory.is_dir():
        raise DataTruthError(f"{directory} is not a readable evidence directory")
    ledgers = fp_ledger.open_ledgers(directory)
    records = _read_ledger(ledgers, "input")
    problems = ledgers["input"].verify()
    if problems:
        raise DataTruthError(f"input ledger chain does not verify: {problems[:3]}")
    try:
        return fp_replay.candles_from_input_ledger(records, pair)
    except fp_replay.ReplayError as exc:
        raise DataTruthError(str(exc)) from exc
