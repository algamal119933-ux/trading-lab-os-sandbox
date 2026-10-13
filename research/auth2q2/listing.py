#!/usr/bin/env python3
"""The archive listing: recorded once at preparation, replayed offline in the science phase (review section 3).

research/auth2/dataset_v3.discover lists the live bucket through research/auth2/archive.py, and neither file
may change (the lock pins both). So the science phase gets the listing the way VCR.py's replay mode gets HTTP:
``replay`` swaps archive._OPENER, the one object every archive request goes through, for an opener that serves
the snapshot's listing pages and refuses every other URL, logging it. A refusal is final: it is raised as a
BaseException, which archive._get's retry loop (``except Exception``) cannot swallow.

What is recorded is what discover keeps, not the raw S3 responses: the USDT symbols that have 1h klines up to
LAST_MONTH, each symbol's 1h zip keys up to LAST_MONTH, and the funding keys of the A3 assets. The raw responses
carry volatile metadata (LastModified, ETag) and keep growing (new months, new symbols), so two cold preparations
on different days would record different bytes for the same Dataset V3 archive. The replayed pages are minimal
S3 ListBucketResult pages, one per (prefix, delimiter) request discover makes, never truncated, and archive's own
list_bucket parses them. Preparation proves the result: discover under ``replay`` returns exactly the tuple the
live bucket gave (prepare.py).

PAPER / RESEARCH ONLY. Nothing here opens a connection.
"""

from __future__ import annotations

import io
import json
import sys
import threading
import urllib.parse
from contextlib import contextmanager
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from auth2 import archive as A  # noqa: E402
from auth2 import dataset_v3 as D  # noqa: E402
from auth2q2 import snapshot as SN  # noqa: E402

LISTING_SCHEMA = "AUTH2Q2_ARCHIVE_LISTING_1"
FIELDS = {"schema", "list_base", "last_month", "delimited", "keys"}


class ReplayRefused(BaseException):
    """A request the snapshot cannot answer. BaseException, so archive._get cannot retry it: it is final."""


def from_discover(found: tuple) -> dict:
    """The listing that makes dataset_v3.discover return ``found`` (its own (symbols, kline keys, funding keys))."""
    symbols, kline_keys, funding_keys = found
    keys = {f"{D.SPOT_PREFIX}{s}/{D.TIMEFRAME}/": list(kline_keys[s]) for s in symbols}
    keys.update({f"{D.FUNDING_PREFIX}{s}/": list(funding_keys[s]) for s in D.A3_ASSETS})
    return {"schema": LISTING_SCHEMA, "list_base": A.LIST_BASE, "last_month": D.LAST_MONTH,
            "delimited": {D.SPOT_PREFIX: [f"{D.SPOT_PREFIX}{s}/" for s in symbols]}, "keys": keys}


def dumps(listing: dict) -> bytes:
    return SN.dumps(listing)


def listing_problems(listing) -> list[str]:
    """Why ``listing`` is not a well-formed snapshot listing ([] when it is)."""
    if not isinstance(listing, dict) or set(listing) != FIELDS:
        return [f"listing fields are not {sorted(FIELDS)}"]
    p = []
    if (listing["schema"], listing["list_base"], listing["last_month"]) != (LISTING_SCHEMA, A.LIST_BASE,
                                                                           D.LAST_MONTH):
        p.append("schema, list base or last month differ from this code's")
    delimited = listing["delimited"]
    if not isinstance(delimited, dict) or list(delimited) != [D.SPOT_PREFIX] \
            or not isinstance(delimited[D.SPOT_PREFIX], list):
        return p + [f"delimited must hold exactly the {D.SPOT_PREFIX} symbol listing"]
    prefixes = delimited[D.SPOT_PREFIX]
    symbols = []
    for item in prefixes:
        sym = item[len(D.SPOT_PREFIX):-1] if isinstance(item, str) and item.startswith(D.SPOT_PREFIX) else ""
        if not item.endswith("/") or not sym or not sym.endswith("USDT") or not SN.valid_path(
                f"{D.SPOT_PREFIX}{sym}/1h/{sym}-1h-2000-01.zip"):
            return p + [f"{str(item)[:120]!r} is not a USDT symbol prefix"]
        symbols.append(sym)
    if symbols != sorted(set(symbols)):
        p.append("symbol prefixes are not sorted and unique")
    keys = listing["keys"]
    want = {f"{D.SPOT_PREFIX}{s}/{D.TIMEFRAME}/" for s in symbols} | {f"{D.FUNDING_PREFIX}{s}/" for s in D.A3_ASSETS}
    if not isinstance(keys, dict) or set(keys) != want:
        return p + ["keys must hold exactly one listing per symbol prefix and per A3 funding asset"]
    for prefix, items in keys.items():
        if not isinstance(items, list) or items != sorted(set(items)):
            p.append(f"{prefix}: keys are not a sorted, unique list")
            continue
        if prefix.startswith(D.SPOT_PREFIX) and not items:
            p.append(f"{prefix}: a symbol without keys is not a symbol discover keeps")
        for k in items:
            kind = SN.data_kind(k) if isinstance(k, str) else None
            if kind not in ("kline", "funding") or not k.startswith(prefix) or k.count("/") != prefix.count("/"):
                p.append(f"{str(k)[:160]!r} is not an archive zip under {prefix}")
                break
            if SN.month_of(k) > D.LAST_MONTH:
                p.append(f"{k} is after LAST_MONTH {D.LAST_MONTH}")
                break
    return p


def load(raw: bytes) -> dict:
    try:
        listing = json.loads(raw.decode("utf-8"), object_pairs_hook=SN._unique)
    except (UnicodeDecodeError, ValueError) as exc:
        raise SN.SnapshotError(f"the listing is not JSON ({str(exc)[:120]})") from exc
    problems = listing_problems(listing)
    if problems:
        raise SN.SnapshotError("the listing is malformed: " + "; ".join(problems[:5]))
    if dumps(listing) != raw:
        raise SN.SnapshotError("the listing is not in its canonical form")
    return listing


def data_keys(listing: dict) -> list[str]:
    """Every archive zip the build reads, in the order it reads them."""
    out = []
    for prefix in listing["delimited"][D.SPOT_PREFIX]:
        out += listing["keys"][f"{prefix}{D.TIMEFRAME}/"]
    for s in D.A3_ASSETS:
        out += listing["keys"][f"{D.FUNDING_PREFIX}{s}/"]
    return out


def page_url(prefix: str, delimiter: bool) -> str:
    """The URL archive.list_bucket requests for the first page of (prefix, delimiter)."""
    q = {"prefix": prefix}
    if delimiter:
        q["delimiter"] = "/"
    return f"{A.LIST_BASE}?{urllib.parse.urlencode(q)}"


def page(prefix: str, items: list[str], delimiter: bool) -> bytes:
    """One complete, untruncated S3 ListBucketResult page holding ``items``."""
    if any("<" in x or "&" in x for x in [prefix, *items]):
        raise SN.SnapshotError("a listing item cannot be written into a page verbatim")
    head = ('<?xml version="1.0" encoding="UTF-8"?>\n<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
            f"<Name>data.binance.vision</Name><Prefix>{prefix}</Prefix><Marker></Marker>"
            f"<MaxKeys>1000</MaxKeys>{'<Delimiter>/</Delimiter>' if delimiter else ''}<IsTruncated>false</IsTruncated>")
    if delimiter:
        body = "".join(f"<CommonPrefixes><Prefix>{x}</Prefix></CommonPrefixes>" for x in items)
    else:
        body = "".join(f"<Contents><Key>{x}</Key></Contents>" for x in items)
    return (head + body + "</ListBucketResult>").encode("utf-8")


class ReplayOpener:
    """Stands in for archive._OPENER: the snapshot's listing pages by exact URL; every other URL refused."""

    def __init__(self, listing: dict) -> None:
        self.pages = {page_url(p, True): page(p, items, True) for p, items in listing["delimited"].items()}
        self.pages.update({page_url(p, False): page(p, items, False) for p, items in listing["keys"].items()})
        self.served: list[str] = []
        self.refused: list[str] = []
        self._lock = threading.Lock()

    def open(self, url, timeout=None):  # noqa: ARG002 - archive._get passes its timeout
        body = self.pages.get(url) if isinstance(url, str) else None
        with self._lock:
            (self.served if body is not None else self.refused).append(str(url))
        if body is None:
            raise ReplayRefused(f"{str(url)[:300]}: not in the snapshot; the science phase has no network")
        return io.BytesIO(body)


@contextmanager
def replay(listing: dict):
    """archive's every request answered by the snapshot listing (and nothing else) while the context is open."""
    opener = ReplayOpener(listing)
    saved = A._OPENER
    A._OPENER = opener
    try:
        yield opener
    finally:
        A._OPENER = saved
