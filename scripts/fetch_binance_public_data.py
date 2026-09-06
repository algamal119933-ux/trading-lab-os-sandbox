#!/usr/bin/env python3
"""Acquire real Binance spot klines from Binance's official public data archive.

Why this exists: Binance's trading API (``api.binance.com``) answers HTTP 451,
"Service unavailable from a restricted location", to both this project's cloud
sandbox and GitHub-hosted runners, so ``freqtrade download-data`` cannot load
markets. Binance publishes the *same* spot klines at
https://data.binance.vision as monthly and daily ZIP archives with published
SHA256 checksums, and that path carries no eligibility check.

This is real market data from the exchange itself, not a synthetic substitute
and not a different venue.

Each archive is verified against its ``.CHECKSUM`` file before use, and every
verified checksum is written to an acquisition manifest so the download is
auditable after the fact.

Usage:
    python3 scripts/fetch_binance_public_data.py \\
        --symbol BTCUSDT --symbol ETHUSDT \\
        --timeframe 1h --timeframe 5m \\
        --start 2020-12-01 --end 2026-08-31 \\
        --out-dir freqtrade/user_data/data/binance \\
        --manifest artifacts/acquisition_manifest.json
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
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

DEFAULT_BASE_URL = "https://data.binance.vision"
MARKET = "spot"
RETRIES = 4
TIMEOUT = 120
# Archives are independent, so fetching them concurrently turns a ~50-minute
# sequential download into a few minutes. Kept modest to stay polite to the CDN.
MAX_WORKERS = 8

# Binance kline CSV layout. Only the first six columns matter here.
OPEN_TIME, OPEN, HIGH, LOW, CLOSE, VOLUME = range(6)


def month_range(start: date, end: date) -> list[str]:
    months: list[str] = []
    cursor = date(start.year, start.month, 1)
    last = date(end.year, end.month, 1)
    while cursor <= last:
        months.append(f"{cursor.year:04d}-{cursor.month:02d}")
        cursor = date(cursor.year + (cursor.month // 12), (cursor.month % 12) + 1, 1)
    return months


def day_range(start: date, end: date) -> list[str]:
    days: list[str] = []
    cursor = start
    while cursor <= end:
        days.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return days


_OPENER = urllib.request.build_opener()
_OPENER.addheaders = [("User-Agent", "trading-lab-os-sandbox/1.0 (research)"),
                      ("Connection", "keep-alive")]


def fetch(url: str) -> bytes | None:
    """Return the body, or None for a 404 (archive not published for that period)."""
    last_error: Exception | None = None
    for attempt in range(RETRIES):
        try:
            with _OPENER.open(url, timeout=TIMEOUT) as response:  # noqa: S310
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            last_error = exc
        except Exception as exc:  # noqa: BLE001 - network flakiness is retried
            last_error = exc
        if attempt < RETRIES - 1:
            import time

            time.sleep(2**attempt)
    raise SystemExit(f"failed to fetch {url}: {last_error}")


def expected_sha256(checksum_body: bytes) -> str:
    """Binance publishes '<sha256>  <filename>' in the .CHECKSUM file."""
    text = checksum_body.decode("utf-8", errors="replace").strip()
    return text.split()[0].lower()


def normalise_timestamp(raw: str) -> int:
    """Binance archives switched some series from milliseconds to microseconds."""
    value = int(float(raw))
    if value > 1_000_000_000_000_000:  # microseconds
        return value // 1000
    if value > 1_000_000_000_000:  # milliseconds
        return value
    return value * 1000  # seconds


def parse_klines(payload: bytes) -> list[tuple[int, float, float, float, float, float]]:
    rows: list[tuple[int, float, float, float, float, float]] = []
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = [n for n in archive.namelist() if n.lower().endswith(".csv")]
        if len(names) != 1:
            raise SystemExit(f"expected exactly one CSV in the archive, found {names}")
        with archive.open(names[0]) as handle:
            text = io.TextIOWrapper(handle, encoding="utf-8")
            for record in csv.reader(text):
                if not record or len(record) < 6:
                    continue
                if not record[OPEN_TIME].strip().replace(".", "").isdigit():
                    continue  # header row present in newer archives
                rows.append(
                    (
                        normalise_timestamp(record[OPEN_TIME]),
                        float(record[OPEN]),
                        float(record[HIGH]),
                        float(record[LOW]),
                        float(record[CLOSE]),
                        float(record[VOLUME]),
                    )
                )
    return rows


def archive_urls(base_url: str, symbol: str, timeframe: str, start: date, end: date) -> list[tuple[str, str]]:
    """Monthly archives, with daily archives filling any month not yet published."""
    urls: list[tuple[str, str]] = []
    for month in month_range(start, end):
        name = f"{symbol}-{timeframe}-{month}.zip"
        urls.append((month, f"{base_url}/data/{MARKET}/monthly/klines/{symbol}/{timeframe}/{name}"))
    return urls


def daily_urls(base_url: str, symbol: str, timeframe: str, days: list[str]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for day in days:
        name = f"{symbol}-{timeframe}-{day}.zip"
        out.append((day, f"{base_url}/data/{MARKET}/daily/klines/{symbol}/{timeframe}/{name}"))
    return out


def _fetch_verified(url: str, verify: bool) -> tuple[str, bytes | None, dict | None]:
    """Fetch one archive and, when asked, verify it against its published checksum."""
    payload = fetch(url)
    if payload is None:
        return url, None, None
    digest = hashlib.sha256(payload).hexdigest()
    entry: dict = {"url": url, "sha256": digest}
    if verify:
        checksum = fetch(url + ".CHECKSUM")
        if checksum is None:
            entry["checksum_verified"] = False
            entry["checksum_note"] = "no .CHECKSUM published"
        else:
            want = expected_sha256(checksum)
            if want != digest:
                raise SystemExit(f"checksum mismatch for {url}: published {want}, got {digest}")
            entry["checksum_verified"] = True
    return url, payload, entry


def _fetch_many(urls: list[tuple[str, str]], verify: bool) -> dict[str, tuple[bytes | None, dict | None]]:
    results: dict[str, tuple[bytes | None, dict | None]] = {}
    if not urls:
        return results
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        for url, payload, entry in pool.map(lambda item: _fetch_verified(item[1], verify), urls):
            results[url] = (payload, entry)
    return results


def download_series(
    base_url: str,
    symbol: str,
    timeframe: str,
    start: date,
    end: date,
    manifest: list[dict],
    verify: bool = True,
) -> list[tuple[int, float, float, float, float, float]]:
    rows: list[tuple[int, float, float, float, float, float]] = []
    missing_months: list[str] = []

    monthly = archive_urls(base_url, symbol, timeframe, start, end)
    fetched = _fetch_many(monthly, verify)
    for month, url in monthly:
        payload, entry = fetched[url]
        if payload is None:
            missing_months.append(month)
            continue
        entry.update({"symbol": symbol, "timeframe": timeframe, "period": month, "granularity": "monthly"})
        manifest.append(entry)
        rows.extend(parse_klines(payload))

    # A month with no monthly archive is usually the current, still-open month;
    # Binance publishes those day by day.
    daily: list[tuple[str, str]] = []
    for month in missing_months:
        year, mon = (int(part) for part in month.split("-"))
        first = date(year, mon, 1)
        last = date(year + (mon // 12), (mon % 12) + 1, 1) - timedelta(days=1)
        window = day_range(max(first, start), min(last, end))
        daily.extend(daily_urls(base_url, symbol, timeframe, window))

    fetched = _fetch_many(daily, verify)
    for day, url in daily:
        payload, entry = fetched[url]
        if payload is None:
            continue
        entry.update({"symbol": symbol, "timeframe": timeframe, "period": day, "granularity": "daily"})
        manifest.append(entry)
        rows.extend(parse_klines(payload))

    return rows


def to_pair(symbol: str, quote: str = "USDT") -> str:
    if not symbol.endswith(quote):
        raise SystemExit(f"cannot split {symbol!r} on quote {quote!r}")
    return f"{symbol[: -len(quote)]}/{quote}"


def write_feather(rows, out_dir: Path, pair: str, timeframe: str, start_ms: int, end_ms: int) -> Path:
    import pandas as pd  # noqa: PLC0415 - only needed when actually writing

    frame = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
    frame = frame[(frame["date"] >= start_ms) & (frame["date"] < end_ms)]
    frame = frame.drop_duplicates(subset="date", keep="first").sort_values("date")
    frame["date"] = pd.to_datetime(frame["date"], unit="ms", utc=True)
    frame = frame.reset_index(drop=True)

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{pair.replace('/', '_')}-{timeframe}.feather"
    frame.to_feather(path, compression="lz4")
    return path


def to_ms(value: str) -> int:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--symbol", action="append", required=True, help="e.g. BTCUSDT (repeatable)")
    parser.add_argument("--timeframe", action="append", required=True, help="e.g. 1h (repeatable)")
    parser.add_argument("--start", required=True, help="inclusive UTC date, YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="inclusive UTC date, YYYY-MM-DD")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--manifest", default=None)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--no-verify", action="store_true", help="Skip .CHECKSUM verification (not for evidence runs).")
    args = parser.parse_args(argv)

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    start_ms = to_ms(f"{args.start}T00:00:00+00:00")
    end_ms = to_ms(f"{(end + timedelta(days=1)).isoformat()}T00:00:00+00:00")

    manifest: list[dict] = []
    written: list[dict] = []
    for symbol in args.symbol:
        for timeframe in args.timeframe:
            print(f"fetching {symbol} {timeframe} {args.start}..{args.end}", flush=True)
            rows = download_series(
                args.base_url, symbol, timeframe, start, end, manifest, verify=not args.no_verify
            )
            if not rows:
                raise SystemExit(f"no data returned for {symbol} {timeframe}")
            pair = to_pair(symbol)
            path = write_feather(rows, Path(args.out_dir), pair, timeframe, start_ms, end_ms)
            print(f"  wrote {path} from {len(rows)} raw candles", flush=True)
            written.append({"pair": pair, "timeframe": timeframe, "file": path.name, "raw_candles": len(rows)})

    if args.manifest:
        Path(args.manifest).parent.mkdir(parents=True, exist_ok=True)
        Path(args.manifest).write_text(
            json.dumps(
                {
                    "source": args.base_url,
                    "market": MARKET,
                    "requested_start_utc": args.start,
                    "requested_end_utc": args.end,
                    "checksum_verification": not args.no_verify,
                    "files_written": written,
                    "archives": sorted(
                        manifest, key=lambda e: (e["symbol"], e["timeframe"], e["period"])
                    ),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"acquisition manifest: {args.manifest} ({len(manifest)} archives)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
