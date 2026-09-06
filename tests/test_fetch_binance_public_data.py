"""Binance public-archive acquisition.

Binance answers 451 to both this sandbox and GitHub runners on its trading API,
so real market data is pulled from Binance's own public archive instead. These
tests exercise the parsing, checksum verification and framing against synthetic
archives, so the pieces that turn a ZIP into a Freqtrade feather file are proven
without needing the network.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from datetime import date

import pytest

import fetch_binance_public_data as fetcher

HOUR_MS = 3_600_000
START_MS = 1_609_459_200_000  # 2021-01-01T00:00:00Z


def make_zip(rows: list[list], name: str = "data.csv", header: bool = False) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    if header:
        writer.writerow(["open_time", "open", "high", "low", "close", "volume",
                         "close_time", "quote_volume", "count", "tb_base", "tb_quote", "ignore"])
    writer.writerows(rows)
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr(name, buffer.getvalue())
    return payload.getvalue()


def kline(ts: int, base: float = 100.0) -> list:
    return [ts, base, base + 1, base - 1, base + 0.5, 3.5,
            ts + HOUR_MS - 1, 350.0, 10, 1.0, 100.0, 0]


def test_month_range_is_inclusive_and_crosses_years():
    assert fetcher.month_range(date(2020, 12, 1), date(2021, 2, 28)) == ["2020-12", "2021-01", "2021-02"]
    assert fetcher.month_range(date(2021, 5, 3), date(2021, 5, 20)) == ["2021-05"]


def test_day_range_is_inclusive():
    days = fetcher.day_range(date(2021, 1, 30), date(2021, 2, 2))
    assert days == ["2021-01-30", "2021-01-31", "2021-02-01", "2021-02-02"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1609459200000", 1609459200000),        # milliseconds
        ("1609459200000000", 1609459200000),     # microseconds (newer archives)
        ("1609459200", 1609459200000),           # seconds
        ("1609459200000.0", 1609459200000),
    ],
)
def test_timestamps_are_normalised_to_milliseconds(raw, expected):
    assert fetcher.normalise_timestamp(raw) == expected


def test_parse_klines_reads_a_plain_archive():
    payload = make_zip([kline(START_MS + i * HOUR_MS, 100.0 + i) for i in range(3)])
    rows = fetcher.parse_klines(payload)
    assert len(rows) == 3
    assert rows[0][0] == START_MS
    assert rows[0][1] == 100.0 and rows[0][5] == 3.5


def test_parse_klines_skips_a_header_row():
    payload = make_zip([kline(START_MS)], header=True)
    rows = fetcher.parse_klines(payload)
    assert len(rows) == 1


def test_parse_klines_rejects_an_ambiguous_archive():
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("a.csv", "1,2,3,4,5,6\n")
        archive.writestr("b.csv", "1,2,3,4,5,6\n")
    with pytest.raises(SystemExit):
        fetcher.parse_klines(payload.getvalue())


def test_expected_sha256_reads_binances_checksum_format():
    body = b"9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08  BTCUSDT-1h-2021-01.zip\n"
    assert fetcher.expected_sha256(body) == "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"


def test_to_pair_splits_on_the_quote():
    assert fetcher.to_pair("BTCUSDT") == "BTC/USDT"
    assert fetcher.to_pair("ETHUSDT") == "ETH/USDT"
    with pytest.raises(SystemExit):
        fetcher.to_pair("BTCEUR")


def install_fake_network(monkeypatch, archives: dict[str, bytes], verify: bool = True):
    """Serve synthetic archives and matching .CHECKSUM bodies."""

    def fake_fetch(url: str):
        if url.endswith(".CHECKSUM"):
            base = url[: -len(".CHECKSUM")]
            if base not in archives:
                return None
            digest = hashlib.sha256(archives[base]).hexdigest()
            return f"{digest}  {base.rsplit('/', 1)[-1]}\n".encode()
        return archives.get(url)

    monkeypatch.setattr(fetcher, "fetch", fake_fetch)


def test_download_series_verifies_checksums_and_records_a_manifest(monkeypatch):
    base = "https://data.binance.vision"
    url = f"{base}/data/spot/monthly/klines/BTCUSDT/1h/BTCUSDT-1h-2021-01.zip"
    payload = make_zip([kline(START_MS + i * HOUR_MS) for i in range(24)])
    install_fake_network(monkeypatch, {url: payload})

    manifest: list[dict] = []
    rows = fetcher.download_series(base, "BTCUSDT", "1h", date(2021, 1, 1), date(2021, 1, 31), manifest)
    assert len(rows) == 24
    assert len(manifest) == 1
    assert manifest[0]["checksum_verified"] is True
    assert manifest[0]["granularity"] == "monthly"


def test_a_bad_checksum_aborts_rather_than_using_the_data(monkeypatch):
    base = "https://data.binance.vision"
    url = f"{base}/data/spot/monthly/klines/BTCUSDT/1h/BTCUSDT-1h-2021-01.zip"
    payload = make_zip([kline(START_MS)])

    def fake_fetch(u: str):
        if u.endswith(".CHECKSUM"):
            return b"0000000000000000000000000000000000000000000000000000000000000000  x.zip\n"
        return payload if u == url else None

    monkeypatch.setattr(fetcher, "fetch", fake_fetch)
    with pytest.raises(SystemExit, match="checksum mismatch"):
        fetcher.download_series(base, "BTCUSDT", "1h", date(2021, 1, 1), date(2021, 1, 31), [])


def test_an_unpublished_month_falls_back_to_daily_archives(monkeypatch):
    base = "https://data.binance.vision"
    archives = {}
    for day in range(1, 4):
        ts = START_MS + (day - 1) * 24 * HOUR_MS
        url = f"{base}/data/spot/daily/klines/BTCUSDT/1h/BTCUSDT-1h-2021-01-{day:02d}.zip"
        archives[url] = make_zip([kline(ts + i * HOUR_MS) for i in range(24)])
    install_fake_network(monkeypatch, archives)

    manifest: list[dict] = []
    rows = fetcher.download_series(base, "BTCUSDT", "1h", date(2021, 1, 1), date(2021, 1, 3), manifest)
    assert len(rows) == 72
    assert {entry["granularity"] for entry in manifest} == {"daily"}


def test_write_feather_frames_sorts_dedupes_and_clips(tmp_path):
    pytest.importorskip("pandas")
    pytest.importorskip("pyarrow")
    import pandas as pd

    rows = [
        (START_MS + 2 * HOUR_MS, 3.0, 4.0, 2.0, 3.5, 1.0),
        (START_MS, 1.0, 2.0, 0.5, 1.5, 1.0),
        (START_MS, 1.0, 2.0, 0.5, 1.5, 1.0),          # duplicate
        (START_MS + HOUR_MS, 2.0, 3.0, 1.5, 2.5, 1.0),
        (START_MS - HOUR_MS, 9.0, 9.0, 9.0, 9.0, 1.0),  # before the window
        (START_MS + 99 * HOUR_MS, 8.0, 8.0, 8.0, 8.0, 1.0),  # after the window
    ]
    path = fetcher.write_feather(
        rows, tmp_path, "BTC/USDT", "1h", START_MS, START_MS + 3 * HOUR_MS
    )
    assert path.name == "BTC_USDT-1h.feather"

    frame = pd.read_feather(path)
    assert list(frame.columns) == ["date", "open", "high", "low", "close", "volume"]
    assert len(frame) == 3
    assert frame["date"].is_monotonic_increasing
    assert str(frame["date"].dt.tz) == "UTC"
    assert frame["open"].tolist() == [1.0, 2.0, 3.0]


def test_written_feather_is_readable_by_the_auditor(tmp_path):
    """The acquisition output must be exactly what the audit path consumes."""
    pytest.importorskip("pandas")
    pytest.importorskip("pyarrow")
    import audit_data

    rows = [(START_MS + i * HOUR_MS, 100.0 + i, 101.0 + i, 99.0 + i, 100.5 + i, 2.0) for i in range(48)]
    fetcher.write_feather(rows, tmp_path, "BTC/USDT", "1h", START_MS, START_MS + 48 * HOUR_MS)
    report = audit_data.audit_file("BTC/USDT", "1h", tmp_path / "BTC_USDT-1h.feather")
    assert report["pass"] is True
    assert report["rows"] == 48
    assert len(report["canonical_candle_content_sha256"]) == 64


def test_manifest_is_written_with_every_archive(tmp_path, monkeypatch):
    pytest.importorskip("pandas")
    base = "https://data.binance.vision"
    url = f"{base}/data/spot/monthly/klines/BTCUSDT/1h/BTCUSDT-1h-2021-01.zip"
    install_fake_network(monkeypatch, {url: make_zip([kline(START_MS + i * HOUR_MS) for i in range(24)])})

    manifest_path = tmp_path / "manifest.json"
    code = fetcher.main([
        "--symbol", "BTCUSDT", "--timeframe", "1h",
        "--start", "2021-01-01", "--end", "2021-01-31",
        "--out-dir", str(tmp_path / "data"),
        "--manifest", str(manifest_path),
        "--base-url", base,
    ])
    assert code == 0
    manifest = json.loads(manifest_path.read_text())
    assert manifest["checksum_verification"] is True
    assert manifest["files_written"][0]["pair"] == "BTC/USDT"
    assert manifest["archives"][0]["sha256"]
