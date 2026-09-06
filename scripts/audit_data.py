#!/usr/bin/env python3
"""Deterministic OHLCV dataset audit and fingerprinting.

CLOUD-0 / C0.7 — data-reproduction plan.

Market data is deliberately not committed to this repository, so the only way a
result stays reproducible is to fingerprint the exact files a run consumed and to
prove they are structurally sound. This script does both, and can additionally
assert that the files still match a frozen dataset lock so a re-download cannot
silently change a dataset mid-experiment.

Supported inputs (Freqtrade ``user_data/data/<exchange>`` layout):
    <PAIR>-<TIMEFRAME>.feather / .parquet   (needs pandas; imported lazily)
    <PAIR>-<TIMEFRAME>.json / .json.gz      (stdlib only)

Usage
-----
    python3 scripts/audit_data.py --data-dir freqtrade/user_data/data/binance \
        --pair BTC/USDT --pair ETH/USDT --timeframe 1h --timeframe 5m \
        --out freqtrade/user_data/baseline_v1_data_audit.json

    python3 scripts/audit_data.py --data-dir ... --lock research/datasets/dataset_v1.lock.json

Exit codes
----------
    0  audit passed (and matched the lock, when one was given)
    2  audit failed, or a fingerprint drifted from the lock
    3  no data files found
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

TIMEFRAME_SECONDS = {"m": 60, "h": 3600, "d": 86400, "w": 604800}
# Version tag baked into the canonical digest so the digest describes its own
# normalisation rules. Changing the rules must change this string.
CANONICAL_DIGEST_VERSION = "CANONICAL_CANDLE_V1"
MAX_MISSING_EXAMPLES = 5
MAX_GAP_CLUSTERS = 25
SUPPORTED_SUFFIXES = (".feather", ".parquet", ".json", ".json.gz")


def timeframe_seconds(timeframe: str) -> int:
    unit = timeframe[-1]
    if unit not in TIMEFRAME_SECONDS or not timeframe[:-1].isdigit():
        raise SystemExit(f"unsupported timeframe: {timeframe!r}")
    return int(timeframe[:-1]) * TIMEFRAME_SECONDS[unit]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_digest(candles: list[tuple[int, float, float, float, float, float]]) -> str:
    """Serialization-independent digest of candle *content*.

    A Feather/PyArrow version bump, a different compression codec or changed file
    metadata all move the raw file hash while the market data is byte-for-byte the
    same numbers. This digest is computed from sorted, normalised candle content
    only, so a change here means the data really changed.

    Normalisation: candles sorted by timestamp; each row rendered as
    ``ts|open|high|low|close|volume`` with integer milliseconds and Python's
    shortest round-tripping float repr; rows joined by newlines under a version
    tag.
    """
    digest = hashlib.sha256()
    digest.update(f"{CANONICAL_DIGEST_VERSION}\n".encode("utf-8"))
    for ts, o, h, low, c, v in sorted(candles, key=lambda row: row[0]):
        row = f"{int(ts)}|{float(o)!r}|{float(h)!r}|{float(low)!r}|{float(c)!r}|{float(v)!r}\n"
        digest.update(row.encode("utf-8"))
    return digest.hexdigest()


def iso(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat()


def to_ms(value: str) -> int:
    """Parse an ISO-8601 UTC timestamp into epoch milliseconds."""
    text = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def find_file(data_dir: Path, pair: str, timeframe: str) -> Path | None:
    token = pair.replace("/", "_")
    for suffix in SUPPORTED_SUFFIXES:
        candidate = data_dir / f"{token}-{timeframe}{suffix}"
        if candidate.exists():
            return candidate
    matches = sorted(
        p for p in data_dir.glob(f"{token}-{timeframe}*")
        if "".join(p.suffixes[-2:]) in SUPPORTED_SUFFIXES or p.suffix in SUPPORTED_SUFFIXES
    )
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise SystemExit(
            f"cannot uniquely resolve {pair} {timeframe} in {data_dir}: {[m.name for m in matches]}"
        )
    return None


def load_candles(path: Path) -> list[tuple[int, float, float, float, float, float]]:
    """Return candles as (timestamp_ms, open, high, low, close, volume), file order preserved."""
    name = path.name
    if name.endswith(".json") or name.endswith(".json.gz"):
        opener = gzip.open if name.endswith(".gz") else open
        with opener(path, "rt", encoding="utf-8") as handle:  # type: ignore[operator]
            raw = json.load(handle)
        return [
            (int(row[0]), float(row[1]), float(row[2]), float(row[3]), float(row[4]), float(row[5]))
            for row in raw
        ]

    import pandas as pd  # noqa: PLC0415 - heavy dependency, only needed for binary formats

    frame = pd.read_feather(path) if path.suffix == ".feather" else pd.read_parquet(path)
    missing = {"date", "open", "high", "low", "close", "volume"} - set(frame.columns)
    if missing:
        raise SystemExit(f"{path.name} is missing columns: {sorted(missing)}")
    dates = pd.to_datetime(frame["date"], utc=True).astype("int64") // 1_000_000
    return [
        (int(ts), float(o), float(h), float(low), float(c), float(v))
        for ts, o, h, low, c, v in zip(
            dates, frame["open"], frame["high"], frame["low"], frame["close"], frame["volume"]
        )
    ]


def gap_clusters(timestamps: set[int], start: int, end: int, step_ms: int) -> list[dict]:
    """Group missing candles into contiguous runs.

    Five scattered example timestamps cannot tell you whether a dataset has one
    exchange outage or ten thousand holes, and that is exactly the judgement a
    date adjustment has to be based on.
    """
    clusters: list[dict] = []
    cursor = start
    run_start: int | None = None
    previous: int | None = None
    while cursor <= end:
        if cursor not in timestamps:
            if run_start is None:
                run_start = cursor
            previous = cursor
        elif run_start is not None:
            clusters.append(
                {
                    "start": iso(run_start),
                    "end": iso(previous),
                    "missing_candles": (previous - run_start) // step_ms + 1,
                }
            )
            run_start = None
        cursor += step_ms
    if run_start is not None and previous is not None:
        clusters.append(
            {
                "start": iso(run_start),
                "end": iso(previous),
                "missing_candles": (previous - run_start) // step_ms + 1,
            }
        )
    clusters.sort(key=lambda c: c["missing_candles"], reverse=True)
    return clusters


def audit_file(
    pair: str,
    timeframe: str,
    path: Path,
    expect_start: str | None = None,
    expect_end: str | None = None,
    max_missing_ratio: float = 0.0,
) -> dict:
    step_ms = timeframe_seconds(timeframe) * 1000
    candles = load_candles(path)

    report: dict = {
        "pair": pair,
        "timeframe": timeframe,
        "file": path.name,
        "raw_file_sha256": sha256_file(path),
        "canonical_candle_content_sha256": canonical_digest(candles),
        "rows": len(candles),
    }
    if not candles:
        report.update({"pass": False, "error": "file contains no candles"})
        return report

    timestamps = [c[0] for c in candles]
    start, end = timestamps[0], timestamps[-1]
    expected_rows = (end - start) // step_ms + 1 if end >= start else 0

    seen: set[int] = set()
    duplicates = 0
    for ts in timestamps:
        if ts in seen:
            duplicates += 1
        seen.add(ts)

    off_grid = sum(1 for ts in timestamps if (ts - start) % step_ms != 0)

    missing_examples: list[str] = []
    missing = 0
    cursor = start
    while cursor <= end:
        if cursor not in seen:
            missing += 1
            if len(missing_examples) < MAX_MISSING_EXAMPLES:
                missing_examples.append(iso(cursor))
        cursor += step_ms
    clusters = gap_clusters(seen, start, end, step_ms) if missing else []

    nan_cells = 0
    bad_ohlc = 0
    prices_positive = True
    volume_nonnegative = True
    for _ts, o, h, low, c, v in candles:
        values = (o, h, low, c, v)
        if any(math.isnan(x) or math.isinf(x) for x in values):
            nan_cells += 1
            continue
        if h < low or h < max(o, c) or low > min(o, c):
            bad_ohlc += 1
        if min(o, h, low, c) <= 0:
            prices_positive = False
        if v < 0:
            volume_nonnegative = False

    monotonic = all(b > a for a, b in zip(timestamps, timestamps[1:]))

    report.update(
        {
            "start": iso(start),
            "end": iso(end),
            "expected_rows_from_range": int(expected_rows),
            "duplicate_timestamps": duplicates,
            "missing_intervals": missing,
            "missing_examples": missing_examples,
            "gap_clusters": clusters[:MAX_GAP_CLUSTERS],
            "gap_cluster_count": len(clusters),
            "largest_gap_candles": clusters[0]["missing_candles"] if clusters else 0,
            "unexpected_timestamps": off_grid,
            "nan_cells": nan_cells,
            "nonfinite_numeric_cells": nan_cells,
            "bad_ohlc_rows": bad_ohlc,
            "prices_positive": prices_positive,
            "volume_nonnegative": volume_nonnegative,
            "monotonic_time": monotonic,
            "last_candle_is_complete": end + step_ms <= int(time.time() * 1000),
        }
    )
    if expect_start is not None:
        report["expected_start"] = expect_start
        report["start_matches_expected"] = iso(start) == iso(to_ms(expect_start))
    if expect_end is not None:
        # The last *completed* candle strictly inside the requested end bound.
        bound = to_ms(expect_end)
        report["expected_end_exclusive"] = expect_end
        report["end_matches_expected"] = bound - step_ms <= end < bound
    coverage_ok = bool(
        report.get("start_matches_expected", True) and report.get("end_matches_expected", True)
    )
    # Two different kinds of problem, deliberately kept apart.
    #
    # Structural integrity is about whether the data is *sound*: duplicates,
    # off-grid timestamps, NaN, impossible OHLC, non-monotonic time, wrong
    # coverage, a half-formed final candle. Any of these means the acquisition or
    # the file is broken, and none is ever tolerable.
    #
    # Continuity is about whether the *exchange* was up. Binance really did halt
    # trading on some days, and those candles do not exist in Binance's own
    # authoritative archive either. Treating an exchange outage as data
    # corruption would be wrong, and silently folding it into a single pass/fail
    # would hide it. So gaps are measured, located, and reported separately.
    report["structural_pass"] = bool(
        coverage_ok
        and report["last_candle_is_complete"]
        and duplicates == 0
        and off_grid == 0
        and nan_cells == 0
        and bad_ohlc == 0
        and prices_positive
        and volume_nonnegative
        and monotonic
    )
    expected_rows = int(expected_rows) or 1
    report["missing_ratio"] = missing / expected_rows
    report["continuity_pass"] = missing == 0
    report["continuity_within_tolerance"] = report["missing_ratio"] <= max_missing_ratio
    report["max_missing_ratio_allowed"] = max_missing_ratio
    report["pass"] = bool(report["structural_pass"] and report["continuity_within_tolerance"])
    return report


def reconcile(
    pair: str,
    fine: Path,
    fine_tf: str,
    coarse: Path,
    coarse_tf: str,
    reconcile_rel_tol: float = 1e-9,
) -> dict:
    """Verify that the fine timeframe aggregates exactly into the coarse timeframe."""
    fine_step = timeframe_seconds(fine_tf) * 1000
    coarse_step = timeframe_seconds(coarse_tf) * 1000
    if coarse_step % fine_step != 0:
        raise SystemExit(f"{coarse_tf} is not a whole multiple of {fine_tf}")
    per_bucket = coarse_step // fine_step

    buckets: dict[int, list[tuple[int, float, float, float, float, float]]] = {}
    for candle in load_candles(fine):
        buckets.setdefault((candle[0] // coarse_step) * coarse_step, []).append(candle)

    coarse_candles = {c[0]: c for c in load_candles(coarse)}

    incomplete = 0
    compared = 0
    mismatches = {"open": 0, "high": 0, "low": 0, "close": 0, "volume": 0}
    worst: dict[str, float] = {"open": 0.0, "high": 0.0, "low": 0.0, "close": 0.0, "volume": 0.0}
    worst_examples: dict[str, str] = {}
    for bucket_start, rows in buckets.items():
        if len(rows) != per_bucket:
            incomplete += 1
            continue
        if bucket_start not in coarse_candles:
            continue
        rows.sort(key=lambda r: r[0])
        expected = (
            rows[0][1],
            max(r[2] for r in rows),
            min(r[3] for r in rows),
            rows[-1][4],
            sum(r[5] for r in rows),
        )
        _ts, o, h, low, c, v = coarse_candles[bucket_start]
        compared += 1
        for name, want, got in zip(
            ("open", "high", "low", "close", "volume"), expected, (o, h, low, c, v)
        ):
            deviation = abs(want - got) / abs(want) if want else abs(want - got)
            if deviation > worst[name]:
                worst[name] = deviation
                worst_examples[name] = (
                    f"{iso(bucket_start)}: aggregated {want!r} vs stored {got!r}"
                )
            if not math.isclose(want, got, rel_tol=reconcile_rel_tol, abs_tol=1e-8):
                mismatches[name] += 1

    return {
        "pair": pair,
        "fine_timeframe": fine_tf,
        "coarse_timeframe": coarse_tf,
        "common_complete_buckets": compared,
        "incomplete_fine_buckets_in_downloaded_range": incomplete,
        "mismatched_bars": mismatches,
        "relative_tolerance": reconcile_rel_tol,
        "worst_relative_deviation": worst,
        "worst_deviation_examples": worst_examples,
        "price_reconciliation_exact": all(
            mismatches[field] == 0 for field in ("open", "high", "low", "close")
        ),
        "pass": compared > 0 and all(v == 0 for v in mismatches.values()),
    }


def range_alignment(files: list[dict]) -> dict:
    out: dict = {}
    by_tf: dict[str, list[dict]] = {}
    for entry in files:
        by_tf.setdefault(entry["timeframe"], []).append(entry)
    for timeframe, entries in sorted(by_tf.items()):
        if len(entries) < 2:
            continue
        same_start = len({e.get("start") for e in entries}) == 1
        same_end = len({e.get("end") for e in entries}) == 1
        same_rows = len({e.get("rows") for e in entries}) == 1
        out[timeframe] = {
            "same_start": same_start,
            "same_end": same_end,
            "same_rows": same_rows,
            "pass": same_start and same_end and same_rows,
        }
    return out


def build_report(
    data_dir: Path,
    pairs: list[str],
    timeframes: list[str],
    expect_start: str | None = None,
    expect_end: str | None = None,
    max_missing_ratio: float = 0.0,
    reconcile_rel_tol: float = 1e-9,
) -> dict:
    files: list[dict] = []
    resolved: dict[tuple[str, str], Path] = {}
    for pair in pairs:
        for timeframe in timeframes:
            path = find_file(data_dir, pair, timeframe)
            if path is None:
                continue
            resolved[(pair, timeframe)] = path
            files.append(
                audit_file(pair, timeframe, path, expect_start, expect_end, max_missing_ratio)
            )

    aggregation: list[dict] = []
    if len(timeframes) >= 2:
        ordered = sorted(timeframes, key=timeframe_seconds)
        fine_tf, coarse_tf = ordered[0], ordered[-1]
        for pair in pairs:
            fine = resolved.get((pair, fine_tf))
            coarse = resolved.get((pair, coarse_tf))
            if fine and coarse:
                aggregation.append(
                    reconcile(pair, fine, fine_tf, coarse, coarse_tf, reconcile_rel_tol)
                )

    alignment = range_alignment(files)
    overall = bool(
        files
        and all(f.get("pass") for f in files)
        and all(a.get("pass") for a in aggregation)
        and all(a.get("pass") for a in alignment.values())
    )
    return {
        "base_directory": data_dir.as_posix(),
        "pairs": pairs,
        "timeframes": timeframes,
        "expected_start": expect_start,
        "expected_end_exclusive": expect_end,
        "max_missing_ratio_allowed": max_missing_ratio,
        "reconcile_relative_tolerance": reconcile_rel_tol,
        "structural_pass": all(f.get("structural_pass") for f in files) if files else False,
        "files": files,
        "aggregation_checks": aggregation,
        "range_alignment": alignment,
        "overall_pass": overall,
    }


def check_lock(report: dict, lock_path: Path) -> tuple[list[str], list[str]]:
    """Compare a dataset against its frozen lock.

    Returns (problems, notes). Content drift is a problem. A raw-file hash that
    moved while the canonical content digest still matches is a *note*: that is a
    serialization difference (PyArrow version, compression, file metadata), not
    market-data drift, and treating it as drift would block every re-download.
    Locks that predate canonical digests carry raw hashes only, so for those a
    raw mismatch stays a hard failure.
    """
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    expected_raw: dict[str, str] = lock.get("raw_file_hashes") or lock.get("dataset_hashes") or {}
    expected_canonical: dict[str, str] = lock.get("canonical_hashes") or {}

    problems: list[str] = []
    notes: list[str] = []
    seen: set[str] = set()

    for entry in report["files"]:
        key = f"{entry['pair']} {entry['timeframe']}"
        seen.add(key)
        raw = entry["raw_file_sha256"]
        canonical = entry["canonical_candle_content_sha256"]

        if key not in expected_raw and key not in expected_canonical:
            problems.append(f"{key}: present on disk but absent from the lock")
            continue

        canonical_known = key in expected_canonical
        if canonical_known and expected_canonical[key] != canonical:
            problems.append(
                f"{key}: CONTENT DRIFT — lock canonical {expected_canonical[key]} "
                f"!= on-disk {canonical}"
            )
            continue

        if key in expected_raw and expected_raw[key] != raw:
            message = (
                f"{key}: raw file hash differs — lock {expected_raw[key]} != on-disk {raw}"
            )
            if canonical_known:
                notes.append(message + " (canonical content identical: serialization only)")
            else:
                problems.append(message + " (lock has no canonical digest to distinguish)")

    for key in sorted((set(expected_raw) | set(expected_canonical)) - seen):
        problems.append(f"{key}: named in the lock but not found on disk")
    return problems, notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit and fingerprint OHLCV datasets.")
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--pair", action="append", default=[], metavar="BASE/QUOTE")
    parser.add_argument("--timeframe", action="append", default=[], metavar="TF")
    parser.add_argument("--out", default=None, help="Write the audit report JSON here.")
    parser.add_argument("--lock", default=None, help="Frozen dataset lock to assert against.")
    parser.add_argument("--expect-start", default=None, metavar="ISO8601",
                        help="Assert the first candle sits exactly here.")
    parser.add_argument("--expect-end", default=None, metavar="ISO8601",
                        help="Exclusive upper bound; the last candle must be the one just below it.")
    parser.add_argument("--max-missing-ratio", type=float, default=0.0, metavar="RATIO",
                        help="Fraction of candles allowed to be absent because the exchange was "
                             "halted. Structural defects are never tolerated by this. Default 0.")
    parser.add_argument("--reconcile-rel-tol", type=float, default=1e-9, metavar="TOL",
                        help="Relative tolerance for 5m -> 1h reconciliation. Default 1e-9.")
    args = parser.parse_args(argv)

    pairs = args.pair or ["BTC/USDT", "ETH/USDT"]
    timeframes = args.timeframe or ["5m", "1h"]

    data_dir = Path(args.data_dir)
    if not data_dir.is_dir():
        print(f"DATA_AUDIT_FAIL: data directory not found: {data_dir}", file=sys.stderr)
        return 3

    report = build_report(
        data_dir, pairs, timeframes, args.expect_start, args.expect_end,
        args.max_missing_ratio, args.reconcile_rel_tol,
    )
    if not report["files"]:
        print(f"DATA_AUDIT_FAIL: no dataset files found in {data_dir}", file=sys.stderr)
        return 3

    lock_problems: list[str] = []
    lock_notes: list[str] = []
    if args.lock:
        lock_problems, lock_notes = check_lock(report, Path(args.lock))
        report["dataset_lock"] = {
            "file": args.lock,
            "problems": lock_problems,
            "notes": lock_notes,
            "pass": not lock_problems,
        }
        report["overall_pass"] = report["overall_pass"] and not lock_problems

    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    for entry in report["files"]:
        print(f"{entry['pair']:>10} {entry['timeframe']:>4}  rows={entry['rows']:<8} "
              f"{'PASS' if entry.get('pass') else 'FAIL'}")
        print(f"{'':>10} raw       {entry['raw_file_sha256']}")
        print(f"{'':>10} canonical {entry['canonical_candle_content_sha256']}")
    for entry in report["aggregation_checks"]:
        print(f"{entry['pair']:>10} {entry['fine_timeframe']}->{entry['coarse_timeframe']} "
              f"reconciliation: {'PASS' if entry['pass'] else 'FAIL'}")
    for note in lock_notes:
        print(f"DATA_LOCK_NOTE: {note}")
    for problem in lock_problems:
        print(f"DATA_LOCK_FAIL: {problem}", file=sys.stderr)

    if report["overall_pass"]:
        print("DATA_INTEGRITY_GATE = PASS")
        return 0
    print("DATA_INTEGRITY_GATE = FAIL", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
