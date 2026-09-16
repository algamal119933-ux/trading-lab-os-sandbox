"""Activation validation, and the gap that cannot be designed away.

The capture loop reads T0 **once**, at construction. A loop already running when
T0 is frozen will never see it, so a cohort requires a fresh process start after
the merge — and that is a property of the code, not a preference. These tests
drive the validator over lanes built to look like each way that start can go
wrong.

The activation gap gets its own attention because it is structural. The registry
has four statuses; a cohort whose T0 is frozen but whose runtime has not started
cannot be NOT_STARTED (the schema forbids a T0 on it) and cannot be PAUSED (a
paused row is not executable), so it must be RUNNING. An interval in which the
registry says RUNNING and nothing runs therefore exists by construction. It can
only be bounded, made visible, and kept out of the credited evidence — and a
silently absent hour and a recorded one are different evidentiary objects, which
is what check 9 is for.
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

REGISTRY_PATH = Path("research/fp/records/forward_paper_cohort_registry.json")
ROLE = "FP-CONTROL-2"
TEST_LANE = "fp-testlane-s2activation"
HOUR_MS = 3_600_000
COMMIT = "a" * 40


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def lane_env(tmp_path, monkeypatch):
    """A registry whose successor row is RUNNING over a disposable real lane.

    The synthetic registry is written to a file and every consumer is pointed at
    it, rather than injected into the one call that accepts a dict. Injection
    was not enough and the difference is instructive: ``validate_activation``
    takes a registry for lane resolution, but the preflight and reconciliation
    legs it runs read the registry from disk through their own module constants.
    A fixture that patched only the argument would have tested a validator whose
    two halves disagreed about which cohort they were looking at.
    """
    registry = copy.deepcopy(json.loads(REGISTRY_PATH.read_text(encoding="utf-8")))
    row = next(item for item in registry["instances"] if item["role"] == ROLE)
    identity = row["runtime_identity"]
    for field in ("db_path", "log_path", "evidence_dir"):
        identity[field] = identity[field].replace("/fp-control-2/", f"/{TEST_LANE}/")

    # T0 on an exact hour boundary, so "the first boundary at or after T0" is
    # unambiguous and the expected first credited bar can be named exactly.
    t0_ms = (int(datetime(2026, 9, 20, 14, 0, 0, tzinfo=timezone.utc).timestamp())) * 1000
    t0 = _iso(t0_ms)
    row["status"] = "RUNNING"
    row["t0_utc"] = t0
    row["cohort_id"] = fp_law.cohort_id_for(ROLE, t0)
    identity["source_commit"] = "b" * 40
    row["change_log"] = [{"utc": t0, "class": "O", "description": "T0 frozen."}]
    registry["fp_run_active"] = True
    assert fp_law.check_registry(registry) == []

    registry_file = tmp_path / "forward_paper_cohort_registry.json"
    registry_file.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    for module in (fp_lane, fp_law, activation.fp_reconcile.fp_lane,
                   activation.fp_preflight, activation.fp_preflight.fp_capture):
        if hasattr(module, "COHORT_REGISTRY"):
            monkeypatch.setattr(module, "COHORT_REGISTRY", registry_file)

    root = fp_lane.HOST_USER_DATA / TEST_LANE
    if root.exists():
        shutil.rmtree(root)
    evidence = root / "evidence"
    evidence.mkdir(parents=True)
    try:
        yield registry, evidence, t0_ms, row["cohort_id"]
    finally:
        if root.exists():
            shutil.rmtree(root)


def stamp(cohort_id: str, *, commit: str = COMMIT, restart: int = 0) -> dict:
    return {
        "runtime_id": f"{ROLE}:fp-control-2",
        "run_id": "run-" + str(restart),
        "role": ROLE,
        "cohort_id": cohort_id,
        "restart_counter": restart,
        "source_commit": commit,
        "strategy_sha256": "c" * 64,
        "config_sha256": "d" * 64,
        "capture_engine_version": "FP_CAPTURE_LOOP_V1",
    }


def write_lane(
    evidence: Path,
    cohort_id: str,
    t0_ms: int,
    *,
    bars: list[tuple[int, str, str]] | None = None,
    starts: int = 1,
    started_offset_s: int = 60,
    gap_incidents: int | None = None,
    commit: str = COMMIT,
):
    """A lane shaped exactly as the test needs, written through the real ledgers.

    ``bars`` is a list of (candle_ts, t0_relation, bar_class). Written through
    ``fp_ledger`` rather than as raw lines so the hash chains are genuine: a
    validator tested against hand-written JSON would never exercise the chain
    verification it depends on.
    """
    ledgers = fp_ledger.open_ledgers(evidence, create=True)
    identity = stamp(cohort_id, commit=commit)
    for index in range(starts):
        ledgers["incident"].append({
            "category": "run_started",
            "detail": f"start {index}",
            "observed_utc": _iso(t0_ms + started_offset_s * 1000),
            "full_identity": {**identity, "restart_counter": index},
            "identity": stamp(cohort_id, commit=commit, restart=index),
        })
    if bars is None:
        bars = [(first_credited_candle_ts(t0_ms), "POST_T0", "LIVE")]
    gaps = 0
    for candle_ts, relation, bar_class in bars:
        ledgers["input"].append({
            "pair": "BTC/USDT",
            "timeframe": "1h",
            "candle_ts": candle_ts,
            "market_event_id": f"BTC/USDT|1h|{candle_ts}",
            "identity": identity,
        })
        ledgers["decision"].append({
            "pair": "BTC/USDT",
            "timeframe": "1h",
            "candle_ts": candle_ts,
            "market_event_id": f"BTC/USDT|1h|{candle_ts}",
            "intended_action": "hold",
            "signal_state": "flat",
            "t0_relation": relation,
            "bar_class": bar_class,
            "identity": identity,
        })
        if relation == "POST_T0" and bar_class == "WARMUP":
            gaps += 1
    for index in range(gaps if gap_incidents is None else gap_incidents):
        ledgers["incident"].append({
            "category": "activation_gap",
            "detail": f"gap bar {index}",
            "observed_utc": _iso(t0_ms),
            "identity": identity,
        })
    return ledgers


def first_credited_candle_ts(t0_ms: int, timeframe_ms: int = HOUR_MS) -> int:
    """The bar a cohort's first credited decision must be on.

    ``capture.t0_relation`` calls a bar POST_T0 when its **close** is at or
    after T0, so the first credited bar is the first one that CLOSES at or after
    T0 — which opens one period earlier. When T0 sits exactly on a boundary that
    bar covers the hour immediately before T0, and by the frozen definition it
    is still prospective: the decision it produced was taken after T0, from a
    candle that closed at T0.
    """
    first_close = ((t0_ms + timeframe_ms - 1) // timeframe_ms) * timeframe_ms
    return first_close - timeframe_ms


def result_of(report: dict, number: int) -> str:
    return next(c["result"] for c in report["checks"] if c["check"] == number)


# -- the shape a clean activation has --------------------------------------


def test_a_clean_activation_passes_every_ledger_check(lane_env):
    registry, evidence, t0_ms, cohort = lane_env
    write_lane(evidence, cohort, t0_ms)
    report = activation.validate(ROLE, source_commit=COMMIT, registry=registry)
    for number in (1, 2, 3, 4, 5, 6, 9, 10):
        assert result_of(report, number) == activation.PASS, report["checks"]
    assert report["activation_gap"]["post_t0_warmup_decisions"] == 0
    assert report["prospective_paper_edge"] == "NOT_EVALUATED"


def test_the_first_credited_bar_is_the_first_boundary_after_t0(lane_env):
    registry, evidence, t0_ms, cohort = lane_env
    write_lane(evidence, cohort, t0_ms,
               bars=[(first_credited_candle_ts(t0_ms), "POST_T0", "LIVE")])
    report = activation.validate(ROLE, source_commit=COMMIT, registry=registry)
    assert result_of(report, 6) == activation.PASS


def test_the_first_credited_bar_is_derived_from_the_close_not_the_open():
    """Pin the arithmetic, for a T0 on a boundary and a T0 between two."""
    boundary = 1_789_912_800_000  # exactly 14:00:00Z
    assert boundary % HOUR_MS == 0
    # On a boundary: the bar closing exactly at T0 opens one hour before it.
    assert first_credited_candle_ts(boundary) == boundary - HOUR_MS
    # Between boundaries: the next close is the following hour, so the bar opens
    # at the boundary T0 fell just after.
    assert first_credited_candle_ts(boundary + 1) == boundary
    assert first_credited_candle_ts(boundary + HOUR_MS - 1) == boundary


def test_a_later_first_credited_bar_fails(lane_env):
    """Bars between T0 and the first credited one were not observed live."""
    registry, evidence, t0_ms, cohort = lane_env
    write_lane(evidence, cohort, t0_ms, bars=[(t0_ms + 3 * HOUR_MS, "POST_T0", "LIVE")])
    report = activation.validate(ROLE, source_commit=COMMIT, registry=registry)
    assert result_of(report, 6) == activation.FAIL


def test_no_credited_bar_at_all_fails(lane_env):
    registry, evidence, t0_ms, cohort = lane_env
    write_lane(evidence, cohort, t0_ms, bars=[(t0_ms - 4 * HOUR_MS, "PRE_T0", "WARMUP")])
    report = activation.validate(ROLE, source_commit=COMMIT, registry=registry)
    assert result_of(report, 6) == activation.FAIL


# -- the five identity checks ----------------------------------------------


def test_a_restarted_lane_is_not_a_fresh_activation(lane_env):
    registry, evidence, t0_ms, cohort = lane_env
    write_lane(evidence, cohort, t0_ms, starts=2)
    report = activation.validate(ROLE, source_commit=COMMIT, registry=registry)
    assert result_of(report, 1) == activation.FAIL


def test_a_broken_chain_fails(lane_env):
    registry, evidence, t0_ms, cohort = lane_env
    write_lane(evidence, cohort, t0_ms)
    path = evidence / "paper_decision_ledger.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[0])
    record["payload"]["intended_action"] = "enter_long"
    lines[0] = json.dumps(record, sort_keys=True, ensure_ascii=False)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    report = activation.validate(ROLE, source_commit=COMMIT, registry=registry)
    assert result_of(report, 2) == activation.FAIL


def test_a_foreign_cohort_id_fails(lane_env):
    registry, evidence, t0_ms, cohort = lane_env
    write_lane(evidence, "FP-CONTROL-1-20260908T121513Z", t0_ms)
    report = activation.validate(ROLE, source_commit=COMMIT, registry=registry)
    assert result_of(report, 3) == activation.FAIL


def test_a_second_source_commit_fails(lane_env):
    registry, evidence, t0_ms, cohort = lane_env
    ledgers = write_lane(evidence, cohort, t0_ms)
    ledgers["input"].append({
        "pair": "ETH/USDT", "timeframe": "1h", "candle_ts": t0_ms + HOUR_MS,
        "market_event_id": f"ETH/USDT|1h|{t0_ms + HOUR_MS}",
        "identity": stamp(cohort, commit="f" * 40),
    })
    report = activation.validate(ROLE, source_commit=COMMIT, registry=registry)
    assert result_of(report, 3) == activation.FAIL


def test_a_record_reading_t0_not_frozen_proves_the_lane_was_not_fresh(lane_env):
    registry, evidence, t0_ms, cohort = lane_env
    write_lane(evidence, cohort, t0_ms, bars=[
        (t0_ms - 4 * HOUR_MS, "T0_NOT_FROZEN", "LIVE"),
        (first_credited_candle_ts(t0_ms), "POST_T0", "LIVE"),
    ])
    report = activation.validate(ROLE, source_commit=COMMIT, registry=registry)
    assert result_of(report, 4) == activation.FAIL


def test_a_pre_t0_live_record_is_impossible_on_a_fresh_lane(lane_env):
    registry, evidence, t0_ms, cohort = lane_env
    write_lane(evidence, cohort, t0_ms, bars=[
        (t0_ms - 4 * HOUR_MS, "PRE_T0", "LIVE"),
        (first_credited_candle_ts(t0_ms), "POST_T0", "LIVE"),
    ])
    report = activation.validate(ROLE, source_commit=COMMIT, registry=registry)
    assert result_of(report, 5) == activation.FAIL


# -- the gap ---------------------------------------------------------------


def test_gap_bars_are_counted_named_and_never_credited(lane_env):
    registry, evidence, t0_ms, cohort = lane_env
    write_lane(evidence, cohort, t0_ms, bars=[
        (first_credited_candle_ts(t0_ms), "POST_T0", "WARMUP"),
        (first_credited_candle_ts(t0_ms) + HOUR_MS, "POST_T0", "WARMUP"),
        (first_credited_candle_ts(t0_ms) + 2 * HOUR_MS, "POST_T0", "LIVE"),
    ])
    report = activation.validate(ROLE, source_commit=COMMIT, registry=registry)
    gap = report["activation_gap"]
    assert gap["post_t0_warmup_decisions"] == 2
    assert len(gap["candles_covered"]) == 2
    assert "NEVER CREDITED" in gap["disposition"]
    # Recorded where it happened, not only in this report.
    assert result_of(report, 9) == activation.PASS


def test_a_gap_with_no_incident_recorded_fails(lane_env):
    """A gap visible only in a report written afterwards is not in the evidence."""
    registry, evidence, t0_ms, cohort = lane_env
    write_lane(evidence, cohort, t0_ms, gap_incidents=0, bars=[
        (first_credited_candle_ts(t0_ms), "POST_T0", "WARMUP"),
        (first_credited_candle_ts(t0_ms) + HOUR_MS, "POST_T0", "LIVE"),
    ])
    report = activation.validate(ROLE, source_commit=COMMIT, registry=registry)
    assert result_of(report, 9) == activation.FAIL


def test_no_gap_means_no_incident_is_expected(lane_env):
    registry, evidence, t0_ms, cohort = lane_env
    write_lane(evidence, cohort, t0_ms)
    report = activation.validate(ROLE, source_commit=COMMIT, registry=registry)
    assert result_of(report, 9) == activation.PASS
    assert report["activation_gap"]["post_t0_warmup_decisions"] == 0


def test_starting_beyond_one_candle_period_after_t0_fails(lane_env):
    registry, evidence, t0_ms, cohort = lane_env
    write_lane(evidence, cohort, t0_ms, started_offset_s=2 * 3600 + 1)
    report = activation.validate(ROLE, source_commit=COMMIT, registry=registry)
    assert result_of(report, 10) == activation.FAIL
    assert report["activation_gap"]["max_elapsed_seconds"] == 3600


def test_starting_before_t0_is_within_bound(lane_env):
    registry, evidence, t0_ms, cohort = lane_env
    write_lane(evidence, cohort, t0_ms, started_offset_s=-600)
    report = activation.validate(ROLE, source_commit=COMMIT, registry=registry)
    assert result_of(report, 10) == activation.PASS


# -- the row must actually be frozen ---------------------------------------


def test_a_not_started_row_has_no_activation_to_validate():
    report = activation.validate(ROLE)
    assert report["activation"] == activation.FAIL
    assert "no activation to validate" in report["checks"][0]["detail"]
