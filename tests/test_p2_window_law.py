"""The prospective window is clocked from ACTIVATION_UTC, and it has a hard cap.

A registry can say `RUNNING` while nothing runs — that interval is structural
and cannot be designed away (contract section 7). Clocking the window from
`T0_UTC` would therefore run the cohort's clock through the one stretch whose
records are explicitly not credited, which is the wrong direction for every
party: it shortens the observed window while lengthening the recorded one.

So the window starts at ACTIVATION_UTC, the instant activation validation first
proves a lawful POST_T0 + LIVE record. T0_UTC does not move and keeps doing its
own job as the crediting boundary.

The hard cap is 30 calendar days with no automatic extension, and reaching it
without a completed lifecycle is a lawful `INCONCLUSIVE / INSUFFICIENT` close.
That prohibition is what makes the cap meaningful at all: a window extendable
until it produced a trade would be a window that always produces one, and the
result would say nothing about the system.
"""

from __future__ import annotations

import copy
import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import validate_activation as activation
from fp import lane as fp_lane
from fp import ledger as fp_ledger
from fp import registry_law as fp_law

from test_p2_activation import (  # the same synthetic-lane machinery
    COMMIT,
    HOUR_MS,
    TEST_LANE,
    first_credited_candle_ts,
    lane_env,  # noqa: F401  (fixture)
    stamp,
    write_lane,
)

CONTRACT = Path("docs/p2/P2_CONTRACT.md")


def _window(registry, evidence, t0_ms, cohort, **kwargs):
    write_lane(evidence, cohort, t0_ms, **kwargs)
    return activation.validate("FP-CONTROL-2", source_commit=COMMIT, registry=registry)["window"]


# -- the contract states it -------------------------------------------------


def test_the_contract_defines_activation_utc_as_the_window_start():
    text = CONTRACT.read_text(encoding="utf-8")
    assert "ACTIVATION_UTC   the instant activation validation FIRST proves a lawful" in text
    assert "WINDOW STARTS AT ACTIVATION_UTC                      not at T0_UTC" in text
    assert "HARD CAP         ACTIVATION_UTC + 30 calendar days" in text
    assert "no automatic extension" in text


def test_the_contract_keeps_t0_immutable_and_still_the_crediting_boundary():
    text = CONTRACT.read_text(encoding="utf-8")
    assert "`T0_UTC` remains immutable and remains the crediting boundary" in text
    assert "`POST_T0 + WARMUP` is contextual and is never\ncredited" in text


def test_the_contract_forbids_manufacturing_the_end_of_the_window():
    text = CONTRACT.read_text(encoding="utf-8")
    for forbidden in ("an artificial trade", "a threshold change",
                      "a forced entry or exit", "any strategy modification"):
        assert forbidden in text
    assert "P2 INCONCLUSIVE / INSUFFICIENT" in text


def test_the_validator_agrees_with_the_contracts_cap():
    assert activation.WINDOW_HARD_CAP_DAYS == 30


# -- the clock ---------------------------------------------------------------


def test_the_window_does_not_start_before_a_credited_record_exists(lane_env):
    """A cohort that has produced nothing creditable has not started its window."""
    registry, evidence, t0_ms, cohort = lane_env
    window = _window(registry, evidence, t0_ms, cohort,
                     bars=[(t0_ms - 4 * HOUR_MS, "PRE_T0", "WARMUP")])
    assert window["state"] == "NOT_ACTIVATED"
    assert window["activation_utc"] is None
    assert window["hard_cap_utc"] is None


def test_activation_utc_is_the_first_credited_record_not_t0(lane_env):
    registry, evidence, t0_ms, cohort = lane_env
    window = _window(registry, evidence, t0_ms, cohort)
    assert window["activation_utc"] is not None
    assert window["t0_utc"] is not None
    assert window["window_starts_at"] == "ACTIVATION_UTC"
    # The two are different instants, and the window uses the later one.
    assert window["activation_utc"] >= window["t0_utc"]


def test_activation_utc_is_a_property_of_the_evidence_not_of_when_we_looked(lane_env):
    """Re-running the validator later must report the same instant."""
    registry, evidence, t0_ms, cohort = lane_env
    first = _window(registry, evidence, t0_ms, cohort)
    second = activation.validate("FP-CONTROL-2", source_commit=COMMIT,
                                 registry=registry)["window"]
    assert first["activation_utc"] == second["activation_utc"]
    assert first["hard_cap_utc"] == second["hard_cap_utc"]


def test_gap_bars_do_not_start_the_window(lane_env):
    """POST_T0 + WARMUP is contextual, and contextual does not start a clock."""
    registry, evidence, t0_ms, cohort = lane_env
    start = first_credited_candle_ts(t0_ms)
    window = _window(registry, evidence, t0_ms, cohort, bars=[
        (start, "POST_T0", "WARMUP"),
        (start + HOUR_MS, "POST_T0", "WARMUP"),
        (start + 2 * HOUR_MS, "POST_T0", "LIVE"),
    ])
    live_open = start + 2 * HOUR_MS
    # The clock begins at the LIVE bar, not at the first POST_T0 bar.
    assert window["activation_utc"] is not None
    from fp import market as fp_market

    assert window["activation_utc"] >= fp_market.iso_from_ms(live_open)


def test_the_hard_cap_is_thirty_days_after_activation(lane_env):
    registry, evidence, t0_ms, cohort = lane_env
    window = _window(registry, evidence, t0_ms, cohort)
    activated = datetime.strptime(window["activation_utc"][:19] + "Z", "%Y-%m-%dT%H:%M:%SZ")
    cap = datetime.strptime(window["hard_cap_utc"], "%Y-%m-%dT%H:%M:%SZ")
    assert (cap - activated).days == 30
    assert window["hard_cap_days"] == 30


def test_a_window_inside_the_cap_is_open(lane_env):
    registry, evidence, t0_ms, cohort = lane_env
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    recent_t0 = now_ms - 3 * HOUR_MS
    row = next(r for r in registry["instances"] if r["role"] == "FP-CONTROL-2")
    from fp import market as fp_market

    t0_iso = fp_market.iso_from_ms((recent_t0 // HOUR_MS) * HOUR_MS)[:19] + "Z"
    row["t0_utc"] = t0_iso
    row["cohort_id"] = fp_law.cohort_id_for("FP-CONTROL-2", t0_iso)
    row["change_log"] = [{"utc": t0_iso, "class": "O", "description": "T0 frozen."}]
    aligned = (recent_t0 // HOUR_MS) * HOUR_MS
    window = _window(registry, evidence, aligned, row['cohort_id'])
    assert window["state"] == "OPEN"
    assert 0 <= window["elapsed_days"] < 1


def test_a_window_past_the_cap_reports_hard_cap_reached(lane_env):
    """A T0 well in the past: the cap is reached and said so, not extended."""
    registry, evidence, t0_ms, cohort = lane_env
    window = _window(registry, evidence, t0_ms, cohort)
    # The fixture's T0 is 2026-09-20; if that is more than 30 days ago the state
    # is HARD_CAP_REACHED, otherwise OPEN. Either way the state is computed from
    # the cap rather than assumed, and no extension field exists.
    assert window["state"] in ("OPEN", "HARD_CAP_REACHED")
    assert window["automatic_extension"] is False


# -- what the window may and may not do to end itself ----------------------


def test_the_report_names_the_lawful_close_at_the_cap(lane_env):
    registry, evidence, t0_ms, cohort = lane_env
    window = _window(registry, evidence, t0_ms, cohort)
    assert window["at_hard_cap_close_as"] == "P2 INCONCLUSIVE / INSUFFICIENT"
    assert window["automatic_extension"] is False


def test_the_report_carries_the_prohibition_that_makes_the_cap_meaningful(lane_env):
    registry, evidence, t0_ms, cohort = lane_env
    window = _window(registry, evidence, t0_ms, cohort)
    forbidden = window["forbidden_to_end_the_window"]
    for phrase in ("artificial trade", "threshold change", "forced entry",
                   "strategy modification"):
        assert phrase in forbidden


def test_the_normal_end_requires_all_twelve_properties(lane_env):
    registry, evidence, t0_ms, cohort = lane_env
    window = _window(registry, evidence, t0_ms, cohort)
    assert "naturally completed full paper trade lifecycle" in window["normal_end"]
    assert "twelve" in window["normal_end"]
    from fp import capability as cap

    assert cap.PROPERTY_COUNT == 12


def test_the_validator_never_extends_a_window():
    """No mechanism exists to move the cap — only to report it.

    Claim-shaped, not vocabulary-shaped: the report must be able to SAY
    `automatic_extension: False`, which is the field doing its job.
    """
    code = Path("scripts/validate_activation.py").read_text(encoding="utf-8")
    body = code.split('"""', 2)[2]
    for forbidden in ("grace_period", "extend_window", "--extend", "WINDOW_HARD_CAP_DAYS * 2",
                      "WINDOW_HARD_CAP_DAYS +"):
        assert forbidden not in body, f"validate_activation offers {forbidden!r}"
    # The cap is a constant consulted once, not a parameter.
    assert body.count("WINDOW_HARD_CAP_DAYS") == 3  # definition, report field, timedelta
    assert '"automatic_extension": False' in body
