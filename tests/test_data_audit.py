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
    assert len(report["sha256"]) == 64


def test_fingerprint_changes_when_a_single_candle_changes(tmp_path, clean_1h):
    first = audit_data.audit_file("BTC/USDT", "1h", clean_1h)["sha256"]
    rows = json.loads(clean_1h.read_text())
    rows[10][4] += 0.01
    write_json(clean_1h, rows)
    assert audit_data.audit_file("BTC/USDT", "1h", clean_1h)["sha256"] != first


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


def test_dataset_lock_detects_fingerprint_drift(tmp_path):
    build_consistent_pair(tmp_path, "BTC/USDT")
    report = audit_data.build_report(tmp_path, ["BTC/USDT"], ["5m", "1h"])
    real = {f"{f['pair']} {f['timeframe']}": f["sha256"] for f in report["files"]}

    lock = tmp_path / "lock.json"
    lock.write_text(json.dumps({"dataset_hashes": real}), encoding="utf-8")
    assert audit_data.check_lock(report, lock) == []

    drifted = dict(real)
    drifted["BTC/USDT 1h"] = "0" * 64
    lock.write_text(json.dumps({"dataset_hashes": drifted}), encoding="utf-8")
    problems = audit_data.check_lock(report, lock)
    assert any("drift" in p for p in problems)


def test_dataset_lock_detects_a_missing_file(tmp_path):
    build_consistent_pair(tmp_path, "BTC/USDT")
    report = audit_data.build_report(tmp_path, ["BTC/USDT"], ["5m", "1h"])
    lock = tmp_path / "lock.json"
    lock.write_text(
        json.dumps({"dataset_hashes": {"ETH/USDT 1h": "0" * 64}}), encoding="utf-8"
    )
    problems = audit_data.check_lock(report, lock)
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
    assert lock["dataset_hashes"] == from_audit
    assert audit["overall_pass"] is True
