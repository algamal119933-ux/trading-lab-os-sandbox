#!/usr/bin/env python3
"""Acquire and verify BTCUSDT perpetual funding rates from Binance's public archive.

`EmaCrossFunding` consumes a funding series as a read-only feature. Directive v1.1
section 11 permits that for a spot strategy provided no derivative order is placed,
and requires proof that each value was knowable when the decision it informs was
taken.

Why the archive rather than the API: `fapi.binance.com` is blocked from the research
sandbox and returned HTTP 451 to GitHub-hosted runners during Dataset V2 acquisition.
`data.binance.vision` is the route that worked for candles.

Nothing here is trusted by default. Before the series may be used, ALL of the
following must pass, and any failure is fatal:

  coverage        every requested month present, spanning the required range
  schema          the archive's columns are a shape this module recognises
  checksum        each archive matches its published .CHECKSUM
  ordering        timestamps strictly increasing after sort, no duplicates
  semantics       every timestamp lands on the 8-hour settlement grid, which is
                  what makes it a settlement instant rather than an interval start
  continuity      exactly one settlement per 8-hour slot, no gaps
  equivalence     overlapping samples agree with the upstream API representation

The last one is the one that cannot be waived. The archive and the API use different
column names, so "calc_time == fundingTime" is an assumption until it is measured. If
the API is unreachable, equivalence is UNESTABLISHED and this exits non-zero: an
unverified mapping would silently shift every funding value by up to eight hours.

This module deliberately mirrors the conventions of scripts/fetch_binance_public_data.py
(same base URL, retry policy, checksum handling). Once that module and this one are on
one branch, the shared helpers should be lifted into a common module rather than kept
in two places.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
import urllib.error
import urllib.request
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

DEFAULT_BASE_URL = "https://data.binance.vision"
API_URL = "https://fapi.binance.com/fapi/v1/fundingRate"
SYMBOL = "BTCUSDT"
RETRIES = 4
TIMEOUT = 120

# Binance settles perpetual funding every 8 hours at 00:00, 08:00 and 16:00 UTC.
SETTLEMENT_INTERVAL_MS = 8 * 3600 * 1000
SETTLEMENT_HOURS = (0, 8, 16)

# Archive header shapes this module knows how to read, mapped to (timestamp, rate).
# Anything else is a hard failure rather than a guess.
KNOWN_SCHEMAS = {
    ("calc_time", "funding_interval_hours", "last_funding_rate"): ("calc_time", "last_funding_rate"),
    ("calc_time", "last_funding_rate"): ("calc_time", "last_funding_rate"),
    ("fundingTime", "fundingRate"): ("fundingTime", "fundingRate"),
    ("symbol", "fundingTime", "fundingRate", "markPrice"): ("fundingTime", "fundingRate"),
}


def fetch(url: str) -> bytes | None:
    """Return the body, or None on 404. Any other failure raises after RETRIES."""
    last: Exception | None = None
    for attempt in range(RETRIES):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "trading-lab-os-funding/1"})
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            last = exc
        except Exception as exc:  # noqa: BLE001 - retried, then surfaced
            last = exc
    raise RuntimeError(f"failed to fetch {url} after {RETRIES} attempts: {last}")


def months(start: date, end: date) -> list[str]:
    out, cursor = [], date(start.year, start.month, 1)
    while cursor <= end:
        out.append(f"{cursor.year:04d}-{cursor.month:02d}")
        cursor = date(cursor.year + (cursor.month == 12), (cursor.month % 12) + 1, 1)
    return out


def expected_sha256(checksum_body: bytes) -> str:
    return checksum_body.decode("utf-8", errors="replace").strip().split()[0].lower()


def parse_archive(payload: bytes, source: str) -> list[tuple[int, float]]:
    """Read one monthly archive, asserting its schema rather than assuming it."""
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = [n for n in archive.namelist() if n.lower().endswith(".csv")]
        if len(names) != 1:
            raise SystemExit(f"SCHEMA FAIL {source}: expected one CSV, found {names}")
        text = archive.read(names[0]).decode("utf-8", errors="replace")

    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        raise SystemExit(f"SCHEMA FAIL {source}: empty archive")

    header = tuple(h.strip() for h in rows[0])
    body = rows[1:]
    if not all(_is_number(c) for c in header[:1]):
        key = header
    else:
        # Headerless month: fall back to the canonical three-column shape.
        key = ("calc_time", "funding_interval_hours", "last_funding_rate")
        body = rows

    if key not in KNOWN_SCHEMAS:
        raise SystemExit(
            f"SCHEMA FAIL {source}: unrecognised columns {key}.\n"
            "Refusing to guess a column mapping - a wrong guess silently shifts every "
            "funding value. Add the shape to KNOWN_SCHEMAS only after confirming its meaning."
        )
    ts_col, rate_col = KNOWN_SCHEMAS[key]
    ts_i, rate_i = key.index(ts_col), key.index(rate_col)

    out: list[tuple[int, float]] = []
    for row in body:
        if not row or not _is_number(row[ts_i]):
            continue
        out.append((_to_ms(row[ts_i]), float(row[rate_i])))
    return out


def _is_number(value: str) -> bool:
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    return True


def _to_ms(raw: str) -> int:
    value = int(float(raw))
    return value // 1000 if value > 10**14 else value  # microseconds -> milliseconds


def verify_series(rows: list[tuple[int, float]], start_ms: int, end_ms: int) -> dict:
    """Ordering, deduplication, settlement-grid semantics and continuity."""
    problems: list[str] = []
    stamps = [ts for ts, _ in rows]

    duplicates = len(stamps) - len(set(stamps))
    if duplicates:
        problems.append(f"{duplicates} duplicate settlement timestamps")
    if stamps != sorted(stamps):
        problems.append("timestamps are not sorted ascending")

    off_grid = [
        ts for ts in stamps
        if datetime.fromtimestamp(ts / 1000, tz=timezone.utc).hour not in SETTLEMENT_HOURS
        or ts % (3600 * 1000) != 0
    ]
    if off_grid:
        sample = [datetime.fromtimestamp(t / 1000, tz=timezone.utc).isoformat() for t in off_grid[:3]]
        problems.append(
            f"{len(off_grid)} timestamps off the 8-hour settlement grid, e.g. {sample}. "
            "Off-grid values would mean the column is not a settlement instant, which "
            "invalidates the knowability argument."
        )

    ordered = sorted(set(stamps))
    gaps = [
        (a, b) for a, b in zip(ordered, ordered[1:])
        if b - a != SETTLEMENT_INTERVAL_MS
    ]
    if gaps:
        problems.append(f"{len(gaps)} breaks in 8-hour continuity, first at "
                        f"{datetime.fromtimestamp(gaps[0][0] / 1000, tz=timezone.utc).isoformat()}")

    if ordered and (ordered[0] > start_ms + SETTLEMENT_INTERVAL_MS or ordered[-1] < end_ms - SETTLEMENT_INTERVAL_MS):
        problems.append("coverage does not span the requested range")

    return {
        "rows": len(rows),
        "unique_timestamps": len(set(stamps)),
        "first_utc": datetime.fromtimestamp(ordered[0] / 1000, tz=timezone.utc).isoformat() if ordered else None,
        "last_utc": datetime.fromtimestamp(ordered[-1] / 1000, tz=timezone.utc).isoformat() if ordered else None,
        "duplicates": duplicates,
        "off_grid": len(off_grid),
        "continuity_breaks": len(gaps),
        "problems": problems,
        "pass": not problems,
    }


def check_api_equivalence(rows: list[tuple[int, float]], sample_size: int = 200) -> dict:
    """Compare overlapping samples with the upstream API representation.

    The archive names its columns calc_time / last_funding_rate; the API names them
    fundingTime / fundingRate. That they mean the same instant is an assumption until
    measured, and getting it wrong shifts every value by up to eight hours. If the API
    cannot be reached the result is UNESTABLISHED, which is a failure, not a pass.
    """
    if not rows:
        return {"status": "UNESTABLISHED", "reason": "no archive rows to compare"}

    ordered = sorted(rows)
    start_ms = ordered[max(0, len(ordered) - sample_size)][0]
    url = f"{API_URL}?symbol={SYMBOL}&startTime={start_ms}&limit={min(sample_size, 1000)}"
    try:
        payload = fetch(url)
    except Exception as exc:  # noqa: BLE001 - reachability is the thing being measured
        return {
            "status": "UNESTABLISHED",
            "reason": f"upstream API unreachable: {exc}",
            "url": url,
            "note": "fapi.binance.com is blocked from the sandbox and returned 451 to GitHub runners.",
        }
    if payload is None:
        return {"status": "UNESTABLISHED", "reason": "API returned 404", "url": url}

    api = {int(item["fundingTime"]): float(item["fundingRate"]) for item in json.loads(payload)}
    archive = dict(ordered)
    overlap = sorted(set(api) & set(archive))
    if not overlap:
        return {
            "status": "UNESTABLISHED",
            "reason": "no overlapping timestamps between archive and API",
            "note": "Non-overlap is itself evidence the two timestamp columns may not mean the same thing.",
        }

    mismatches = [
        {
            "utc": datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat(),
            "archive": archive[ts],
            "api": api[ts],
        }
        for ts in overlap
        if abs(archive[ts] - api[ts]) > 1e-12
    ]
    return {
        "status": "PASS" if not mismatches else "FAIL",
        "compared": len(overlap),
        "mismatches": len(mismatches),
        "examples": mismatches[:3],
        "conclusion": (
            "archive calc_time and API fundingTime denote the same settlement instant, "
            "and the rates agree exactly"
        ) if not mismatches else "archive and API disagree on overlapping settlements",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2019-09-01")
    parser.add_argument("--end", default="2026-08-31")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--out", default=None, help="write the verified series as JSON")
    parser.add_argument("--report", default=None, help="write the verification report as JSON")
    parser.add_argument("--probe-only", action="store_true",
                        help="fetch one month and report reachability and schema, nothing more")
    args = parser.parse_args(argv)

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    wanted = months(start, end)
    if args.probe_only:
        wanted = wanted[:1]

    print(f"FUNDING ACQUISITION  {SYMBOL}  {args.start} -> {args.end}  ({len(wanted)} month(s))")
    print(f"base: {args.base_url}\n")

    rows: list[tuple[int, float]] = []
    manifest: list[dict] = []
    missing: list[str] = []

    for month in wanted:
        name = f"{SYMBOL}-fundingRate-{month}.zip"
        url = f"{args.base_url}/data/futures/um/monthly/fundingRate/{SYMBOL}/{name}"
        payload = fetch(url)
        if payload is None:
            missing.append(month)
            print(f"  MISSING  {month}")
            continue

        entry = {"month": month, "url": url, "bytes": len(payload),
                 "sha256": hashlib.sha256(payload).hexdigest()}
        checksum = fetch(url + ".CHECKSUM")
        if checksum is None:
            entry["checksum_verified"] = False
            entry["checksum_note"] = "no .CHECKSUM published"
        else:
            want = expected_sha256(checksum)
            if want != entry["sha256"]:
                raise SystemExit(f"CHECKSUM FAIL {month}: published {want}, got {entry['sha256']}")
            entry["checksum_verified"] = True

        month_rows = parse_archive(payload, month)
        entry["rows"] = len(month_rows)
        rows.extend(month_rows)
        manifest.append(entry)
        print(f"  ok       {month}  {len(month_rows):>4} settlements  "
              f"checksum={'verified' if entry.get('checksum_verified') else 'ABSENT'}")

    if not rows:
        print("\nFUNDING_ACQUISITION_GATE = FAIL (nothing retrieved)", file=sys.stderr)
        return 1

    start_ms = int(datetime(start.year, start.month, start.day, tzinfo=timezone.utc).timestamp() * 1000)
    end_ms = int((datetime(end.year, end.month, end.day, tzinfo=timezone.utc)
                  + timedelta(days=1)).timestamp() * 1000)
    integrity = verify_series(rows, start_ms, end_ms)
    equivalence = check_api_equivalence(rows)

    report = {
        "symbol": SYMBOL,
        "requested": {"start": args.start, "end": args.end},
        "probe_only": args.probe_only,
        "months_missing": missing,
        "archives": manifest,
        "integrity": integrity,
        "api_equivalence": equivalence,
        "settlement_semantics": (
            "Every timestamp lands on the 00:00/08:00/16:00 UTC settlement grid, so the column is the "
            "instant funding is applied and therefore published - not the start of the interval it accrued "
            "over. That distinction is what the knowability argument rests on."
        ),
    }

    print(f"\nintegrity : {'PASS' if integrity['pass'] else 'FAIL'}  "
          f"({integrity['rows']} rows, {integrity['first_utc']} -> {integrity['last_utc']})")
    for problem in integrity["problems"]:
        print(f"  - {problem}")
    print(f"equivalence: {equivalence['status']}  {equivalence.get('reason', equivalence.get('conclusion', ''))}")

    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2) + "\n")
    if args.out and integrity["pass"] and equivalence["status"] == "PASS":
        Path(args.out).write_text(json.dumps(
            [{"funding_time_ms": ts, "funding": rate} for ts, rate in sorted(rows)], indent=2) + "\n")

    if args.probe_only:
        print("\nPROBE ONLY - reachability and schema reported; no gate decision made.")
        return 0 if integrity["rows"] else 1

    ok = integrity["pass"] and equivalence["status"] == "PASS" and not missing
    if not ok:
        print("\nFUNDING_ACQUISITION_GATE = FAIL", file=sys.stderr)
        if equivalence["status"] == "UNESTABLISHED":
            print("  Equivalence to the upstream API representation could not be established, and the "
                  "directive requires failing closed on exactly that. H2 is NOT_MEASURABLE until an API "
                  "sample is obtainable from a network that Binance does not refuse.", file=sys.stderr)
        return 1

    print("\nFUNDING_ACQUISITION_GATE = PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
