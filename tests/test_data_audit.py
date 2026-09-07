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


def test_gap_clusters_group_contiguous_holes(tmp_path):
    """Five scattered examples cannot distinguish one outage from ten thousand."""
    keep = [i for i in range(48) if i not in (10, 11, 12, 30)]
    rows = [candle(START + i * HOUR_MS) for i in keep]
    path = tmp_path / "BTC_USDT-1h.json"
    write_json(path, rows)
    report = audit_data.audit_file("BTC/USDT", "1h", path)
    assert report["missing_intervals"] == 4
    assert report["gap_cluster_count"] == 2
    assert report["largest_gap_candles"] == 3
    assert report["gap_clusters"][0]["missing_candles"] == 3


def test_coverage_assertions_flag_a_short_dataset(tmp_path):
    rows = [candle(START + i * HOUR_MS) for i in range(48)]
    path = tmp_path / "BTC_USDT-1h.json"
    write_json(path, rows)
    good = audit_data.audit_file(
        "BTC/USDT", "1h", path,
        expect_start="2025-09-01T00:00:00Z", expect_end="2025-09-03T00:00:00Z",
    )
    assert good["start_matches_expected"] is True
    assert good["end_matches_expected"] is True
    assert good["pass"] is True

    short = audit_data.audit_file(
        "BTC/USDT", "1h", path,
        expect_start="2025-09-01T00:00:00Z", expect_end="2025-10-01T00:00:00Z",
    )
    assert short["end_matches_expected"] is False
    assert short["pass"] is False


def test_a_partial_live_candle_is_rejected(tmp_path):
    """The final candle must be closed, or the last bar is a half-formed one."""
    import time as _time

    now_ms = int(_time.time() * 1000)
    aligned = (now_ms // HOUR_MS) * HOUR_MS  # the currently forming hour
    rows = [candle(aligned - i * HOUR_MS) for i in range(5, -1, -1)]
    path = tmp_path / "BTC_USDT-1h.json"
    write_json(path, rows)
    report = audit_data.audit_file("BTC/USDT", "1h", path)
    assert report["last_candle_is_complete"] is False
    assert report["pass"] is False


def test_a_gap_is_a_continuity_finding_not_a_structural_one(tmp_path):
    """An exchange halt is a fact about the market, not a corrupt file."""
    rows = [candle(START + i * HOUR_MS) for i in range(48) if i != 20]
    path = tmp_path / "BTC_USDT-1h.json"
    write_json(path, rows)

    strict = audit_data.audit_file("BTC/USDT", "1h", path)
    assert strict["structural_pass"] is True, "a gap must not look like corruption"
    assert strict["continuity_pass"] is False
    assert strict["pass"] is False, "the default tolerance is zero"

    tolerant = audit_data.audit_file("BTC/USDT", "1h", path, max_missing_ratio=0.05)
    assert tolerant["pass"] is True
    assert tolerant["continuity_pass"] is False, "the gap is still reported, not erased"
    assert tolerant["missing_ratio"] == pytest.approx(1 / 48, rel=1e-3)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda rows: rows.insert(5, rows[5]),                       # duplicate
        lambda rows: rows[7].__setitem__(2, rows[7][3] - 5.0),      # high below low
        lambda rows: rows[9].__setitem__(5, -3.0),                  # negative volume
        lambda rows: rows[30].__setitem__(0, rows[30][0] + 90_000),  # off grid
    ],
)
def test_tolerance_never_excuses_a_structural_defect(tmp_path, mutate):
    rows = [candle(START + i * HOUR_MS) for i in range(48)]
    mutate(rows)
    path = tmp_path / "BTC_USDT-1h.json"
    write_json(path, rows)
    report = audit_data.audit_file("BTC/USDT", "1h", path, max_missing_ratio=1.0)
    assert report["structural_pass"] is False
    assert report["pass"] is False, "a generous gap tolerance must not hide corruption"


def test_reconciliation_reports_the_worst_deviation(tmp_path):
    fine, coarse = build_consistent_pair(tmp_path, "BTC/USDT")
    rows = json.loads(coarse.read_text())
    rows[5][5] *= 1.000001  # a volume that is off by one part in a million
    write_json(coarse, rows)

    strict = audit_data.reconcile("BTC/USDT", fine, "5m", coarse, "1h")
    assert strict["mismatched_bars"]["volume"] == 1
    assert strict["price_reconciliation_exact"] is True
    assert strict["worst_relative_deviation"]["volume"] == pytest.approx(1e-6, rel=1e-2)
    assert "aggregated" in strict["worst_deviation_examples"]["volume"]

    loose = audit_data.reconcile("BTC/USDT", fine, "5m", coarse, "1h", reconcile_rel_tol=1e-5)
    assert loose["pass"] is True


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


def test_dataset_v2_lock_is_frozen_with_every_fingerprint(repo_root):
    """A lock missing half its fingerprints is not a drift gate.

    Dataset V2 spent several runs in `frozen_pending_hash_transcription` with
    only the ETH series recorded, which meant a BTC file could have changed
    without the lock check noticing. Pin the closed state.
    """
    lock = json.loads((repo_root / "research/datasets/dataset_v2.lock.json").read_text())
    assert lock["status"] == "frozen"
    assert "hashes_pending" not in lock
    expected = {f"{pair} {tf}" for pair in ("BTC/USDT", "ETH/USDT") for tf in ("5m", "1h")}
    assert set(lock["raw_file_hashes"]) == expected
    assert set(lock["canonical_hashes"]) == expected
    for series in (lock["raw_file_hashes"], lock["canonical_hashes"]):
        for name, digest in series.items():
            assert len(digest) == 64 and set(digest) <= set("0123456789abcdef"), name
    # Raw and canonical fingerprints answer different questions; they must not
    # be the same value copied twice.
    assert set(lock["raw_file_hashes"].values()).isdisjoint(lock["canonical_hashes"].values())


def test_dataset_v1_lock_is_untouched_by_dataset_v2(repo_root):
    """V2 must not rewrite V1. These are the hashes CLAUDE.md records."""
    lock = json.loads((repo_root / "research/datasets/dataset_v1.lock.json").read_text())
    assert lock["dataset_hashes"]["BTC/USDT 1h"] == (
        "b29689f5d0c0e86c95b5ec15e63e6bcfbcb8ad4596408dcc0f9040b3bbdfb4f9"
    )
    assert lock["dataset_hashes"]["BTC/USDT 5m"] == (
        "2ab332f23d2376677b61d5a02492b5a4b67f2d37ac68f89a925697252cc7b908"
    )
    assert lock["dataset_hashes"]["ETH/USDT 1h"] == (
        "a5de3ae5e9c3c73439eb8aec8ff496f9e9d5ebc7cec83842b2b2827880201ccf"
    )
    assert lock["dataset_hashes"]["ETH/USDT 5m"] == (
        "4fa5ca782864ee84aff0e02786be3ca663de159288a7fb4baf12398fcdcca5c4"
    )
