"""Null-control schedule semantics (RESEARCH-FOUNDATION-CLOSURE-1, Gate 3).

Proves the corrected exit mechanism's intended semantics at the schedule
level — entirely independent of any backtest result, before any Attempt-3
trial runs. This is not a search over outcomes: nothing here reads a
backtest result, a metric, or a PnL figure.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from null_controls import generate_schedules as gen


@pytest.fixture(params=["matched_frequency_random", "block_shuffled"])
def schedule(request) -> dict:
    return (gen.matched_frequency_schedule() if request.param == "matched_frequency_random"
            else gen.block_shuffled_schedule())


def _parse(stamp: str) -> datetime:
    return datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ")


def test_every_entry_has_exactly_one_matching_exit_hold_hours_later(schedule):
    entries, exits = schedule["entries_utc"], schedule["exits_utc"]
    assert len(entries) == len(exits) == schedule["target_n"]
    for entry, exit_ in zip(entries, exits):
        assert _parse(exit_) - _parse(entry) == timedelta(hours=schedule["hold_hours"])


def test_no_two_entries_share_an_open_position_window(schedule):
    """The exit mechanism only matters if positions genuinely don't overlap —
    otherwise Freqtrade's single-position-per-pair rule would still silently
    swallow entries, exit fix or not."""
    windows = sorted(
        (_parse(e), _parse(x)) for e, x in zip(schedule["entries_utc"], schedule["exits_utc"])
    )
    for (_, prev_exit), (next_entry, _) in zip(windows, windows[1:]):
        assert next_entry >= prev_exit, (
            f"entry {next_entry} opens before the prior position's exit {prev_exit} — "
            "would still be silently blocked"
        )


def test_no_entry_candle_is_also_an_exit_candle(schedule):
    """An entry and an exit signal both firing on the same candle for a
    strategy with no open position at that instant is not itself harmful
    here (windows don't overlap), but distinct candles keep the two signal
    columns independently checkable against the schedule."""
    assert set(schedule["entries_utc"]).isdisjoint(schedule["exits_utc"])


def test_schedules_regenerate_byte_identically():
    """The generator is the source of truth; the committed JSON files must
    always be exactly what it produces for the pinned seeds."""
    import json
    from pathlib import Path

    here = Path(gen.__file__).resolve().parent
    for name, builder in (
        ("null_matched_frequency_schedule.json", gen.matched_frequency_schedule),
        ("null_block_shuffled_schedule.json", gen.block_shuffled_schedule),
    ):
        committed = json.loads((here / name).read_text(encoding="utf-8"))
        assert committed == builder()


def test_exits_utc_present_for_both_committed_schedules():
    """Attempt 1/2's schedule files predate the exit fix and had no
    exits_utc at all — the absence itself was consistent with a design that
    left exit timing to a runtime callback. Guards against silently
    reintroducing that gap."""
    import json
    from pathlib import Path

    here = Path(gen.__file__).resolve().parent
    for name in ("null_matched_frequency_schedule.json", "null_block_shuffled_schedule.json"):
        data = json.loads((here / name).read_text(encoding="utf-8"))
        assert "exits_utc" in data and len(data["exits_utc"]) == data["target_n"]
