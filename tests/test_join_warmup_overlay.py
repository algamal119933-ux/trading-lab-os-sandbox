"""Warm-up overlay join gates (sprint v1.3 §8.2).

The overlay exists so EmaCross's 1300 startup candles are satisfied without
touching Dataset V2. These tests attack the three properties that make that
claim checkable: disjointness, canonical identity, and *valid* candle count.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from audit_data import canonical_digest  # noqa: E402
from join_warmup_overlay import join_series, parse_utc, valid_completed  # noqa: E402

HOUR = 3_600_000
V2_START = parse_utc("2020-12-01T00:00:00Z")
FIRST_SCORED = parse_utc("2021-01-01T00:00:00Z")


def series(start_ms: int, count: int, base: float = 20000.0) -> list[tuple]:
    return [
        (start_ms + i * HOUR, base + i, base + i + 5, base + i - 5, base + i + 1, 10.0)
        for i in range(count)
    ]


@pytest.fixture
def dataset() -> list[tuple]:
    return series(V2_START, 744)


@pytest.fixture
def overlay() -> list[tuple]:
    return series(parse_utc("2020-10-01T00:00:00Z"), 1464, base = 19000.0)


def test_a_clean_join_passes_every_gate(dataset, overlay):
    report = join_series(dataset, overlay, canonical_digest(dataset), FIRST_SCORED, 1300)
    assert report["problems"] == []
    assert report["disjoint"] is True
    assert report["canonical_identity_preserved"] is True
    assert report["warmup_sufficient"] is True
    assert report["valid_completed_before_first_scored"] == 1464 + 744


def test_canonical_identity_fails_if_a_dataset_candle_moves(dataset, overlay):
    """The gate that makes 'overlay, not mutation' checkable."""
    frozen = canonical_digest(dataset)
    tampered = list(dataset)
    ts, o, h, low, c, v = tampered[400]
    tampered[400] = (ts, o, h, low, c + 1.0, v)

    report = join_series(tampered, overlay, frozen, FIRST_SCORED, 1300)
    assert report["canonical_identity_preserved"] is False
    assert any("CANONICAL IDENTITY FAILED" in p for p in report["problems"])
    assert "joined" not in report, "a failed identity gate must not hand back a series to write"


def test_an_overlapping_overlay_candle_never_overwrites_dataset_v2(dataset, overlay):
    """overlap_policy.on_overlap: the Dataset V2 candle wins unconditionally."""
    colliding = overlay + [(V2_START, 1.0, 1.0, 1.0, 1.0, 1.0)]
    report = join_series(dataset, colliding, canonical_digest(dataset), FIRST_SCORED, 1300)

    assert report["disjoint"] is False
    assert report["collisions"] == 1
    # The dataset candle survived: identity still holds despite the collision.
    assert report["canonical_identity_preserved"] is True
    assert any("Dataset V2 wins unconditionally" in p for p in report["problems"])


def test_insufficient_warmup_fails(dataset):
    short = series(parse_utc("2020-11-01T00:00:00Z"), 100, base=19000.0)
    report = join_series(dataset, short, canonical_digest(dataset), FIRST_SCORED, 1300)
    assert report["warmup_sufficient"] is False
    assert report["valid_completed_before_first_scored"] == 844
    assert any("need 1300" in p for p in report["problems"])


def test_the_gate_counts_valid_candles_not_rows(dataset, overlay):
    """1300 rows of garbage must not satisfy a 1300 valid-candle requirement."""
    broken = list(overlay)
    for index in range(0, 600):
        ts, o, h, low, c, v = broken[index]
        broken[index] = (ts, o, h, low, o + 999.0, v)  # close above high: invalid OHLC

    report = join_series(dataset, broken, canonical_digest(dataset), FIRST_SCORED, 1300)
    assert report["valid_completed_before_first_scored"] == 1464 + 744 - 600
    assert report["warmup_sufficient"] is True  # 1608 still clears 1300
    assert len(report["invalid_warmup_candles"]) > 0


def test_duplicate_and_off_grid_candles_do_not_count():
    candles = series(V2_START, 10)
    candles.append(candles[0])                      # duplicate
    candles.append((V2_START + 90_000, 1.0, 2.0, 0.5, 1.5, 1.0))  # off-grid
    count, problems = valid_completed(sorted(candles), FIRST_SCORED)
    assert count == 10
    assert any("duplicate" in p for p in problems)
    assert any("off-grid" in p for p in problems)


def test_non_finite_and_non_positive_cells_do_not_count():
    candles = series(V2_START, 5)
    candles[1] = (candles[1][0], float("nan"), 1.0, 0.5, 0.9, 1.0)
    candles[2] = (candles[2][0], -1.0, 1.0, 0.5, 0.9, 1.0)
    count, problems = valid_completed(candles, FIRST_SCORED)
    assert count == 3
    assert len(problems) == 2


def test_warmup_after_the_first_scored_bar_is_not_warmup(dataset, overlay):
    """Candles at or after the first scored bar contribute nothing to warm-up."""
    early = parse_utc("2020-12-01T00:00:00Z")
    report = join_series(dataset, overlay, canonical_digest(dataset), early, 1300)
    assert report["valid_completed_before_first_scored"] == 1464
