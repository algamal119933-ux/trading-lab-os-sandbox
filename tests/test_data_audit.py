"""CLOUD-0 / C0.7 — the dataset audit must actually catch broken data.

Market data is not committed, so these tests build synthetic Freqtrade-format
JSON OHLCV files and verify each defect class is detected. The same code path
serves the real feather datasets.
"""

from __future__ import annotations

import json

import pytest

import audit_data


HOUR_MS = 3_600_000
FIVE_MIN_MS = 300_000
START = 1_756_684_800_000  # 2025-09-01T00:00:00Z


def candle(ts: int, base: float = 100.0, vol: float = 1.0) -> list:
    # open, high, low, close chosen so high/low always bracket open/close.
    return [ts, base, base + 1.0, base - 1.0, base + 0.5, vol]


def write_json(path, candles) -> None:
    path.write_text(json.dumps(candles), encoding="utf-8")


@pytest.fixture
def clean_1h(tmp_path):
    rows = [candle(START + i * HOUR_MS, 100.0 + i) for i in range(48)]
    path = tmp_path / "BTC_USDT-1h.json"
    write_json(path, rows)
    return path


def test_timeframe_seconds():
    assert audit_data.timeframe_seconds("5m") == 300
    assert audit_data.timeframe_seconds("1h") == 3600
    assert audit_data.timeframe_seconds("1d") == 86400
    with pytest.raises(SystemExit):
        audit_data.timeframe_seconds("1x")


def test_clean_dataset_passes(clean_1h):
    report = audit_data.audit_file("BTC/USDT", "1h", clean_1h)
    assert report["pass"] is True
    assert report["rows"] == 48
    assert report["missing_intervals"] == 0
    assert report["duplicate_timestamps"] == 0
    assert len(report["raw_file_sha256"]) == 64
    assert len(report["canonical_candle_content_sha256"]) == 64


def test_both_fingerprints_change_when_a_single_candle_changes(tmp_path, clean_1h):
    before = audit_data.audit_file("BTC/USDT", "1h", clean_1h)
    rows = json.loads(clean_1h.read_text())
    rows[10][4] += 0.01
    write_json(clean_1h, rows)
    after = audit_data.audit_file("BTC/USDT", "1h", clean_1h)
    assert after["raw_file_sha256"] != before["raw_file_sha256"]
    assert after["canonical_candle_content_sha256"] != before["canonical_candle_content_sha256"]


def test_canonical_digest_survives_a_serialization_change(tmp_path, clean_1h):
    """A re-serialized file is a different file but the same market data."""
    before = audit_data.audit_file("BTC/USDT", "1h", clean_1h)
    rows = json.loads(clean_1h.read_text())
    # Same numbers, different bytes on disk: whitespace and row order.
    reserialized = tmp_path / "BTC_USDT-1h-reserialized.json"
    reserialized.write_text(json.dumps(list(reversed(rows)), indent=4), encoding="utf-8")
    after = audit_data.audit_file("BTC/USDT", "1h", reserialized)
    assert after["raw_file_sha256"] != before["raw_file_sha256"]
    assert after["canonical_candle_content_sha256"] == before["canonical_candle_content_sha256"]


def test_canonical_digest_is_order_independent_and_versioned():
    rows = [(START + i * HOUR_MS, 1.0 + i, 2.0 + i, 0.5 + i, 1.5 + i, 10.0 + i) for i in range(5)]
    assert audit_data.canonical_digest(rows) == audit_data.canonical_digest(list(reversed(rows)))
    assert audit_data.CANONICAL_DIGEST_VERSION == "CANONICAL_CANDLE_V1"


def test_gap_is_detected(tmp_path):
    rows = [candle(START + i * HOUR_MS) for i in range(48) if i != 20]
    path = tmp_path / "BTC_USDT-1h.json"
    write_json(path, rows)
    report = audit_data.audit_file("BTC/USDT", "1h", path)
    assert report["pass"] is False
    assert report["missing_intervals"] == 1
    assert report["missing_examples"]


def test_duplicate_timestamp_is_detected(tmp_path):
    rows = [candle(START + i * HOUR_MS) for i in range(48)]
    rows.insert(5, rows[5])
    path = tmp_path / "BTC_USDT-1h.json"
    write_json(path, rows)
    report = audit_data.audit_file("BTC/USDT", "1h", path)
    assert report["pass"] is False
    assert report["duplicate_timestamps"] == 1
    assert report["monotonic_time"] is False


def test_off_grid_timestamp_is_detected(tmp_path):
    rows = [candle(START + i * HOUR_MS) for i in range(48)]
    rows[30][0] += 90_000
    path = tmp_path / "BTC_USDT-1h.json"
    write_json(path, rows)
    report = audit_data.audit_file("BTC/USDT", "1h", path)
    assert report["pass"] is False
    assert report["unexpected_timestamps"] == 1


def test_invalid_ohlc_is_detected(tmp_path):
    rows = [candle(START + i * HOUR_MS) for i in range(48)]
    rows[7][2] = rows[7][3] - 5.0  # high below low
    path = tmp_path / "BTC_USDT-1h.json"
    write_json(path, rows)
    report = audit_data.audit_file("BTC/USDT", "1h", path)
    assert report["pass"] is False
    assert report["bad_ohlc_rows"] >= 1


def test_nan_and_nonpositive_prices_are_detected(tmp_path):
    rows = [candle(START + i * HOUR_MS) for i in range(48)]
    rows[3][1] = float("nan")
    rows[4][3] = -1.0
    path = tmp_path / "BTC_USDT-1h.json"
    path.write_text(json.dumps(rows).replace("NaN", "NaN"), encoding="utf-8")
    report = audit_data.audit_file("BTC/USDT", "1h", path)
    assert report["pass"] is False
    assert report["nan_cells"] == 1
    assert report["prices_positive"] is False


def test_negative_volume_is_detected(tmp_path):
    rows = [candle(START + i * HOUR_MS) for i in range(48)]
    rows[9][5] = -3.0
    path = tmp_path / "BTC_USDT-1h.json"
    write_json(path, rows)
    report = audit_data.audit_file("BTC/USDT", "1h", path)
    assert report["pass"] is False
    assert report["volume_nonnegative"] is False


def build_consistent_pair(tmp_path, pair: str, hours: int = 24):
    """Write 5m and 1h files where the 1h bars are the exact 5m aggregation."""
    token = pair.replace("/", "_")
    fine_rows = []
    coarse_rows = []
    for hour in range(hours):
        bucket = START + hour * HOUR_MS
        bars = []
        for step in range(12):
            base = 100.0 + hour + step * 0.1
            bars.append([bucket + step * FIVE_MIN_MS, base, base + 0.5, base - 0.5, base + 0.2, 1.0])
        fine_rows.extend(bars)
        coarse_rows.append(
            [
                bucket,
                bars[0][1],
                max(b[2] for b in bars),
                min(b[3] for b in bars),
                bars[-1][4],
                sum(b[5] for b in bars),
            ]
        )
    fine = tmp_path / f"{token}-5m.json"
    coarse = tmp_path / f"{token}-1h.json"
    write_json(fine, fine_rows)
    write_json(coarse, coarse_rows)
    return fine, coarse


def test_reconciliation_passes_for_consistent_files(tmp_path):
    fine, coarse = build_consistent_pair(tmp_path, "BTC/USDT")
    result = audit_data.reconcile("BTC/USDT", fine, "5m", coarse, "1h")
    assert result["pass"] is True
    assert result["common_complete_buckets"] == 24
    assert all(v == 0 for v in result["mismatched_bars"].values())


def test_reconciliation_catches_a_corrupted_hourly_bar(tmp_path):
    fine, coarse = build_consistent_pair(tmp_path, "BTC/USDT")
    rows = json.loads(coarse.read_text())
    rows[5][4] += 10.0  # close no longer matches the 5m aggregation
    write_json(coarse, rows)
    result = audit_data.reconcile("BTC/USDT", fine, "5m", coarse, "1h")
    assert result["pass"] is False
    assert result["mismatched_bars"]["close"] == 1


def test_full_report_and_range_alignment(tmp_path):
    build_consistent_pair(tmp_path, "BTC/USDT")
    build_consistent_pair(tmp_path, "ETH/USDT")
    report = audit_data.build_report(tmp_path, ["BTC/USDT", "ETH/USDT"], ["5m", "1h"])
    assert report["overall_pass"] is True
    assert len(report["files"]) == 4
    assert report["range_alignment"]["1h"]["pass"] is True


def test_misaligned_pairs_fail_range_alignment(tmp_path):
    build_consistent_pair(tmp_path, "BTC/USDT", hours=24)
    build_consistent_pair(tmp_path, "ETH/USDT", hours=20)
    report = audit_data.build_report(tmp_path, ["BTC/USDT", "ETH/USDT"], ["5m", "1h"])
    assert report["overall_pass"] is False
    assert report["range_alignment"]["1h"]["pass"] is False


def hashes(report, field):
    return {f"{f['pair']} {f['timeframe']}": f[field] for f in report["files"]}


def test_dataset_lock_accepts_an_unchanged_dataset(tmp_path):
    build_consistent_pair(tmp_path, "BTC/USDT")
    report = audit_data.build_report(tmp_path, ["BTC/USDT"], ["5m", "1h"])
    lock = tmp_path / "lock.json"
    lock.write_text(
        json.dumps(
            {
                "raw_file_hashes": hashes(report, "raw_file_sha256"),
                "canonical_hashes": hashes(report, "canonical_candle_content_sha256"),
            }
        ),
        encoding="utf-8",
    )
    problems, notes = audit_data.check_lock(report, lock)
    assert problems == [] and notes == []


def test_dataset_lock_reports_content_drift_as_a_failure(tmp_path):
    build_consistent_pair(tmp_path, "BTC/USDT")
    report = audit_data.build_report(tmp_path, ["BTC/USDT"], ["5m", "1h"])
    canonical = hashes(report, "canonical_candle_content_sha256")
    canonical["BTC/USDT 1h"] = "0" * 64
    lock = tmp_path / "lock.json"
    lock.write_text(
        json.dumps(
            {"raw_file_hashes": hashes(report, "raw_file_sha256"), "canonical_hashes": canonical}
        ),
        encoding="utf-8",
    )
    problems, _notes = audit_data.check_lock(report, lock)
    assert any("CONTENT DRIFT" in p for p in problems)


def test_serialization_difference_is_a_note_not_a_failure(tmp_path):
    """Re-downloading with a different PyArrow build must not read as drift."""
    build_consistent_pair(tmp_path, "BTC/USDT")
    report = audit_data.build_report(tmp_path, ["BTC/USDT"], ["5m", "1h"])
    raw = hashes(report, "raw_file_sha256")
    raw["BTC/USDT 1h"] = "0" * 64  # file bytes moved
    lock = tmp_path / "lock.json"
    lock.write_text(
        json.dumps(
            {
                "raw_file_hashes": raw,
                "canonical_hashes": hashes(report, "canonical_candle_content_sha256"),
            }
        ),
        encoding="utf-8",
    )
    problems, notes = audit_data.check_lock(report, lock)
    assert problems == []
    assert any("serialization only" in n for n in notes)


def test_raw_drift_without_a_canonical_digest_stays_a_failure(tmp_path):
    """Dataset V1's lock predates canonical digests; it must not get looser."""
    build_consistent_pair(tmp_path, "BTC/USDT")
    report = audit_data.build_report(tmp_path, ["BTC/USDT"], ["5m", "1h"])
    raw = hashes(report, "raw_file_sha256")
    raw["BTC/USDT 1h"] = "0" * 64
    lock = tmp_path / "lock.json"
    lock.write_text(json.dumps({"dataset_hashes": raw}), encoding="utf-8")
    problems, _notes = audit_data.check_lock(report, lock)
    assert any("no canonical digest" in p for p in problems)


def test_dataset_lock_detects_a_missing_file(tmp_path):
    build_consistent_pair(tmp_path, "BTC/USDT")
    report = audit_data.build_report(tmp_path, ["BTC/USDT"], ["5m", "1h"])
    lock = tmp_path / "lock.json"
    lock.write_text(
        json.dumps({"dataset_hashes": {"ETH/USDT 1h": "0" * 64}}), encoding="utf-8"
    )
    problems, _notes = audit_data.check_lock(report, lock)
    assert any("not found on disk" in p for p in problems)


def test_cli_exits_3_when_no_data_is_present(tmp_path):
    assert audit_data.main(["--data-dir", str(tmp_path)]) == 3
    assert audit_data.main(["--data-dir", str(tmp_path / "absent")]) == 3


def test_cli_passes_and_writes_a_report(tmp_path, capsys):
    build_consistent_pair(tmp_path, "BTC/USDT")
    out = tmp_path / "audit.json"
    code = audit_data.main(
        ["--data-dir", str(tmp_path), "--pair", "BTC/USDT", "--timeframe", "5m",
         "--timeframe", "1h", "--out", str(out)]
    )
    assert code == 0
    assert "DATA_INTEGRITY_GATE = PASS" in capsys.readouterr().out
    assert json.loads(out.read_text())["overall_pass"] is True


def test_committed_dataset_lock_matches_the_recorded_audit(repo_root):
    """The frozen lock and the historical audit evidence must not disagree."""
    lock = json.loads((repo_root / "research/datasets/dataset_v1.lock.json").read_text())
    audit = json.loads((repo_root / "freqtrade/user_data/baseline_v1_data_audit.json").read_text())
    from_audit = {f"{f['pair']} {f['timeframe']}": f["sha256"] for f in audit["files"]}
    # Dataset V1 is immutable historical evidence: raw-file hashes only.
    assert lock["dataset_hashes"] == from_audit
    assert audit["overall_pass"] is True
