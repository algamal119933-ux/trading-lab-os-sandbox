"""Funding acquisition gate — verified against synthetic archives.

This module can never be integration-tested from the research sandbox:
data.binance.vision answers 403 to CONNECT here, so the first real run happens on a
CI runner. That makes the unit tests the only place the verification logic is proven
before it is trusted, so they cover the failure paths rather than just the happy one.

The rule these encode: every check fails closed. A funding series that cannot be shown
to be a settlement grid, or cannot be shown to agree with the upstream API, is not
usable evidence - and "unreachable" must never read as "fine".
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timezone

import pytest

import fetch_binance_funding as ff

HOUR_MS = 3600 * 1000
SLOT_MS = 8 * HOUR_MS
BASE = int(datetime(2023, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)


def grid(count: int, start: int = BASE) -> list[tuple[int, float]]:
    """A well-formed settlement series: one row every 8 hours, on the grid."""
    return [(start + i * SLOT_MS, 0.0001 * (i % 7 - 3)) for i in range(count)]


def make_archive(rows: list[tuple[int, float]], header=("calc_time", "funding_interval_hours", "last_funding_rate")) -> bytes:
    lines = [",".join(header)]
    lines += [f"{ts},8,{rate}" for ts, rate in rows] if len(header) == 3 else [f"{ts},{rate}" for ts, rate in rows]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("BTCUSDT-fundingRate-2023-01.csv", "\n".join(lines))
    return buffer.getvalue()


def span(rows):
    return rows[0][0], rows[-1][0] + SLOT_MS


# --- schema ----------------------------------------------------------------------

def test_canonical_archive_schema_parses():
    rows = grid(90)
    assert ff.parse_archive(make_archive(rows), "test") == rows


def test_api_shaped_schema_also_parses():
    rows = grid(10)
    assert ff.parse_archive(make_archive(rows, ("fundingTime", "fundingRate")), "test") == rows


def test_unknown_schema_fails_closed_rather_than_guessing():
    """A wrong column guess shifts every value by up to eight hours."""
    payload = make_archive(grid(5), ("mystery_time", "mystery_rate"))
    with pytest.raises(SystemExit, match="unrecognised columns"):
        ff.parse_archive(payload, "test")


def test_multiple_csvs_in_one_archive_fail_closed():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("a.csv", "calc_time,funding_interval_hours,last_funding_rate\n")
        archive.writestr("b.csv", "calc_time,funding_interval_hours,last_funding_rate\n")
    with pytest.raises(SystemExit, match="expected one CSV"):
        ff.parse_archive(buffer.getvalue(), "test")


# --- integrity -------------------------------------------------------------------

def test_clean_series_passes_every_integrity_check():
    rows = grid(120)
    result = ff.verify_series(rows, *span(rows))
    assert result["pass"], result["problems"]
    assert result["duplicates"] == 0 and result["off_grid"] == 0 and result["continuity_breaks"] == 0


def test_off_grid_timestamp_fails_because_it_breaks_the_knowability_argument():
    rows = grid(30)
    rows[10] = (rows[10][0] + HOUR_MS, rows[10][1])   # 09:00 is not a settlement hour
    result = ff.verify_series(rows, *span(rows))
    assert not result["pass"]
    assert result["off_grid"] == 1
    assert any("settlement grid" in p for p in result["problems"])


def test_duplicate_settlement_is_caught():
    rows = grid(20)
    rows.append(rows[5])
    result = ff.verify_series(rows, *span(sorted(rows)))
    assert not result["pass"] and result["duplicates"] == 1


def test_missing_settlement_breaks_continuity():
    rows = grid(20)
    del rows[7]
    result = ff.verify_series(rows, *span(rows))
    assert not result["pass"] and result["continuity_breaks"] >= 1


def test_unsorted_input_is_reported():
    rows = grid(20)
    rows[3], rows[9] = rows[9], rows[3]
    result = ff.verify_series(rows, *span(sorted(rows)))
    assert not result["pass"]
    assert any("sorted" in p for p in result["problems"])


# --- API equivalence -------------------------------------------------------------

def test_unreachable_api_is_unestablished_never_pass(monkeypatch):
    """The whole point of the gate: 'could not check' must not read as 'checked'."""
    monkeypatch.setattr(ff, "fetch", lambda url: (_ for _ in ()).throw(RuntimeError("451")))
    result = ff.check_api_equivalence(grid(50))
    assert result["status"] == "UNESTABLISHED"
    assert result["status"] != "PASS"


def test_matching_api_sample_establishes_the_timestamp_mapping(monkeypatch):
    rows = grid(50)
    payload = json.dumps([
        {"symbol": "BTCUSDT", "fundingTime": ts, "fundingRate": str(rate), "markPrice": "0"}
        for ts, rate in rows
    ]).encode()
    monkeypatch.setattr(ff, "fetch", lambda url: payload)
    result = ff.check_api_equivalence(rows)
    assert result["status"] == "PASS"
    assert result["compared"] > 0 and result["mismatches"] == 0


def test_disagreeing_rate_fails_equivalence(monkeypatch):
    rows = grid(50)
    payload = json.dumps([
        {"fundingTime": ts, "fundingRate": str(rate + (0.5 if i == 3 else 0.0))}
        for i, (ts, rate) in enumerate(rows)
    ]).encode()
    monkeypatch.setattr(ff, "fetch", lambda url: payload)
    result = ff.check_api_equivalence(rows)
    assert result["status"] == "FAIL" and result["mismatches"] == 1


def test_non_overlapping_timestamps_are_unestablished_not_pass(monkeypatch):
    """If the two columns never line up, that is evidence they may not mean the same thing."""
    rows = grid(50)
    shifted = json.dumps([
        {"fundingTime": ts + HOUR_MS, "fundingRate": str(rate)} for ts, rate in rows
    ]).encode()
    monkeypatch.setattr(ff, "fetch", lambda url: shifted)
    result = ff.check_api_equivalence(rows)
    assert result["status"] == "UNESTABLISHED"
    assert "overlap" in result["reason"]


# --- checksum --------------------------------------------------------------------

def test_published_checksum_is_parsed_in_binance_s_format():
    body = b"a3f5  BTCUSDT-fundingRate-2023-01.zip\n"
    assert ff.expected_sha256(body) == "a3f5"


def test_month_range_is_inclusive_and_crosses_years():
    from datetime import date
    assert ff.months(date(2023, 11, 1), date(2024, 2, 15)) == ["2023-11", "2023-12", "2024-01", "2024-02"]


# --- verdict model (sprint v1.3 section 12.2) -------------------------------------
#
# An unreachable API blocks the equivalence *claim*, not the experiment. Collapsing
# that into a single FAIL would stall H2 on a network condition rather than on
# anything about the strategy. What must stay fatal is a measured disagreement.

CLEAN = {"pass": True, "problems": []}
BROKEN = {"pass": False, "problems": ["3 breaks in 8-hour continuity"]}


def test_reachable_and_agreeing_api_gives_the_top_reproduction_grade():
    v = ff.classify(CLEAN, {"status": "PASS", "compared": 200, "mismatches": 0}, [])
    assert v["admissible"] is True
    assert v["REPRODUCTION_GRADE"] == "EXACT_API_NATIVE"
    assert v["MEASUREMENT_VALIDITY"] == "PASS"


def test_unreachable_api_downgrades_but_does_not_block_h2():
    """The correction that matters: H2 is not globally unmeasurable."""
    v = ff.classify(CLEAN, {"status": "UNESTABLISHED", "reason": "upstream API unreachable: 451"}, [])
    assert v["admissible"] is True
    assert v["H2_NATIVE_API_REPRODUCTION"] == "BLOCKED_SOURCE_EQUIVALENCE"
    assert v["H2_OFFICIAL_ARCHIVE_SURROGATE"] == "MEASURABLE"
    assert v["REPRODUCTION_GRADE"] == "OFFICIAL_ARCHIVE_SURROGATE"
    assert v["MEASUREMENT_VALIDITY"] == "PASS"


def test_surrogate_grade_is_strictly_lower_than_native():
    native = ff.classify(CLEAN, {"status": "PASS"}, [])
    surrogate = ff.classify(CLEAN, {"status": "UNESTABLISHED", "reason": "blocked"}, [])
    assert native["REPRODUCTION_GRADE"] == "EXACT_API_NATIVE"
    assert surrogate["REPRODUCTION_GRADE"] == "OFFICIAL_ARCHIVE_SURROGATE"
    assert native["admissible"] and surrogate["admissible"]


def test_measured_disagreement_stays_fatal_and_is_not_downgraded():
    """'Could not check' and 'checked and they disagree' must never collapse."""
    v = ff.classify(CLEAN, {"status": "FAIL", "mismatches": 4}, [])
    assert v["admissible"] is False
    assert v["MEASUREMENT_VALIDITY"] == "FAIL"
    assert v["H2_NATIVE_API_REPRODUCTION"] == "CONTRADICTED"
    assert "contradiction" in v["reason"]


def test_invalid_archive_is_fatal_whatever_the_api_says():
    for equivalence in ({"status": "PASS"}, {"status": "UNESTABLISHED", "reason": "blocked"}):
        v = ff.classify(BROKEN, equivalence, [])
        assert v["admissible"] is False
        assert v["MEASUREMENT_VALIDITY"] == "FAIL"
        assert v["H2_OFFICIAL_ARCHIVE_SURROGATE"] == "NOT_MEASURABLE"


def test_missing_months_are_fatal_even_with_a_clean_integrity_report():
    v = ff.classify(CLEAN, {"status": "PASS"}, ["2021-03"])
    assert v["admissible"] is False
    assert "2021-03" in v["reason"]
