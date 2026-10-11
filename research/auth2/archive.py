"""Checksum-verified reader for Binance's public data archive (Dataset V3).

The archive bucket is listed through its S3 endpoint (the only endpoint that
serves listings) and files are fetched from ``base`` (``data.binance.vision``
or the same bucket's S3 endpoint; both serve identical bytes). Every zip is
verified against its published ``.CHECKSUM`` before use and cached under
``cache_dir/<key>`` together with that checksum, so a rebuild from cache is
byte-identical to a rebuild from the network. Nothing here touches a trading
endpoint, a key, or a private API.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

LIST_BASE = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
DEFAULT_BASE = LIST_BASE
RETRIES = 5
TIMEOUT = 120

_OPENER = urllib.request.build_opener()
_OPENER.addheaders = [("User-Agent", "trading-lab-os-sandbox/auth2 (research)")]


class ArchiveError(RuntimeError):
    pass


def _get(url: str) -> bytes | None:
    """Body, or None on 404. Network errors are retried, then raised."""
    last: Exception | None = None
    for attempt in range(RETRIES):
        try:
            with _OPENER.open(url, timeout=TIMEOUT) as resp:  # noqa: S310 - public archive
                return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            last = exc
        except Exception as exc:  # noqa: BLE001 - transient network failure
            last = exc
        time.sleep(2 ** attempt)
    raise ArchiveError(f"failed to fetch {url}: {last}")


def list_bucket(prefix: str, delimiter: bool) -> list[str]:
    """Common prefixes (delimiter=True) or keys under ``prefix``, in bucket order."""
    out: list[str] = []
    marker = ""
    while True:
        q = {"prefix": prefix}
        if delimiter:
            q["delimiter"] = "/"
        if marker:
            q["marker"] = marker
        body = _get(f"{LIST_BASE}?{urllib.parse.urlencode(q)}")
        if body is None:
            raise ArchiveError(f"listing {prefix} returned 404")
        text = body.decode("utf-8")
        tag = "Prefix" if delimiter else "Key"
        items = re.findall(rf"<{tag}>([^<]+)</{tag}>", text)
        if delimiter:
            items = [i for i in items if i != prefix]
        out += items
        if "<IsTruncated>true</IsTruncated>" not in text:
            return out
        nxt = re.findall(r"<NextMarker>([^<]+)</NextMarker>", text)
        marker = nxt[0] if nxt else items[-1]


def fetch_verified(key: str, cache_dir: Path, base: str = DEFAULT_BASE) -> bytes:
    """The zip at ``key``, verified against its published checksum (cached)."""
    path = cache_dir / key
    sum_path = cache_dir / (key + ".CHECKSUM")
    if path.is_file() and sum_path.is_file():
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() == sum_path.read_text().split()[0].lower():
            return payload
    url = f"{base}/{urllib.parse.quote(key)}"  # some symbols are not ASCII
    payload = _get(url)
    checksum = _get(url + ".CHECKSUM")
    if payload is None or checksum is None:
        raise ArchiveError(f"{key}: archive or checksum not published")
    want = checksum.decode("utf-8", errors="replace").split()[0].lower()
    got = hashlib.sha256(payload).hexdigest()
    if want != got:
        raise ArchiveError(f"{key}: checksum mismatch (published {want}, got {got})")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    sum_path.write_text(f"{want}  {Path(key).name}\n")
    return payload


def fetch_many(keys: list[str], cache_dir: Path, base: str = DEFAULT_BASE, workers: int = 16) -> dict[str, bytes]:
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return dict(zip(keys, pool.map(lambda k: fetch_verified(k, cache_dir, base), keys)))


def _csv_rows(payload: bytes, key: str) -> list[list[str]]:
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        names = [n for n in z.namelist() if n.lower().endswith(".csv")]
        if len(names) != 1:
            raise ArchiveError(f"{key}: expected one CSV, found {names}")
        return list(csv.reader(io.StringIO(z.read(names[0]).decode("utf-8"))))


def _ms(raw: str) -> int:
    v = int(raw)
    if v > 10 ** 15:  # microseconds (Binance spot archives from 2025-01)
        return v // 1000
    if v < 10 ** 11:  # seconds
        return v * 1000
    return v


def parse_klines(payload: bytes, key: str) -> list[tuple]:
    """(open_ms, open, high, low, close, volume, quote_volume, trades) per row."""
    out = []
    for r in _csv_rows(payload, key):
        if len(r) < 9 or not r[0].strip().isdigit():
            continue  # header row of newer archives
        out.append((_ms(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4]),
                    float(r[5]), float(r[7]), int(r[8])))
    return out


FUNDING_SCHEMAS = {
    ("calc_time", "funding_interval_hours", "last_funding_rate"): (0, 2),
    ("calc_time", "last_funding_rate"): (0, 1),
}


def parse_funding(payload: bytes, key: str) -> list[tuple[int, float]]:
    rows = _csv_rows(payload, key)
    if not rows:
        return []
    head = tuple(c.strip() for c in rows[0])
    if head[0].isdigit():
        ts_i, rate_i = FUNDING_SCHEMAS[("calc_time", "funding_interval_hours", "last_funding_rate")]
        body = rows
    elif head in FUNDING_SCHEMAS:
        ts_i, rate_i = FUNDING_SCHEMAS[head]
        body = rows[1:]
    else:
        raise ArchiveError(f"{key}: unrecognised funding columns {head}")
    return [(_ms(r[ts_i]), float(r[rate_i])) for r in body if r and r[ts_i].strip().isdigit()]
