"""Research-selection accounting (COMPRESSED RESEARCH FOUNDATION, Unit A).

The ledger's whole value is that a winning configuration cannot be the only
one anyone ever wrote down. These tests attack that property directly:
attempts that lose, abort, or arrive without a preregistration.
"""

from __future__ import annotations

import pytest

from trial_ledger import (
    IDENTITY_FIELDS,
    PREREGISTERED,
    TrialLedger,
    TrialLedgerError,
)


def _identity(**overrides) -> dict:
    base = {
        "schema_version": "1.0.0",
        "family_id": "TEST_FAMILY",
        "lineage_id": "TEST_FAMILY/L1",
        "candidate_id": "TEST_CANDIDATE",
        "config_id": "TEST_CANDIDATE/CFG1",
        "experiment_id": "EXP-TEST-1",
        "run_id": "RUN-TEST-1",
        "trial_id": "TRIAL-TEST-1",
        "state": PREREGISTERED,
        "purpose": "unit test fixture",
    }
    base.update(overrides)
    return base


@pytest.fixture
def ledger(tmp_path) -> TrialLedger:
    return TrialLedger(tmp_path / "trial_ledger.jsonl")


# -- 1. two attempted configs remain two attempts ---------------------------


def test_two_configs_under_one_lineage_are_two_attempts(ledger):
    ledger.append(_identity(config_id="TEST_CANDIDATE/CFG1", trial_id="T1"))
    ledger.append(_identity(config_id="TEST_CANDIDATE/CFG2", trial_id="T2"))
    records = ledger.records()
    assert len(records) == 2
    assert {r.payload["config_id"] for r in records} == {"TEST_CANDIDATE/CFG1", "TEST_CANDIDATE/CFG2"}
    assert {r.payload["trial_id"] for r in records} == {"T1", "T2"}


# -- 2 & 3. failed / aborted attempts remain recorded ------------------------


def test_a_failed_attempt_remains_recorded(ledger):
    ledger.append(_identity(trial_id="T1", purpose="p"))
    ledger.append(_identity(trial_id="T1", state="FAILED", purpose="p",
                             outcome={"reason": "measurement invalid"}))
    states = [r.payload["state"] for r in ledger.records()]
    assert states == [PREREGISTERED, "FAILED"]


def test_an_aborted_attempt_remains_recorded(ledger):
    ledger.append(_identity(trial_id="T1", purpose="p"))
    ledger.append(_identity(trial_id="T1", state="ABORTED", purpose="p",
                             outcome={"reason": "technical failure, not a research outcome"}))
    states = [r.payload["state"] for r in ledger.records()]
    assert states == [PREREGISTERED, "ABORTED"]


# -- 4. negative results cannot silently disappear --------------------------


def test_a_rejected_trial_survives_a_later_survivor_being_recorded(ledger):
    """One winning config must not erase the losing attempts before it."""
    ledger.append(_identity(trial_id="LOSER", config_id="CFG_A", purpose="p"))
    ledger.append(_identity(trial_id="LOSER", config_id="CFG_A", state="REJECTED", purpose="p",
                             outcome={"reason": "dominated on drawdown"}))
    ledger.append(_identity(trial_id="WINNER", config_id="CFG_B", purpose="p"))
    ledger.append(_identity(trial_id="WINNER", config_id="CFG_B", state="SURVIVED", purpose="p",
                             outcome={"reason": "best on the Pareto frontier"}))
    records = ledger.records()
    assert len(records) == 4
    loser_states = [r.payload["state"] for r in records if r.payload["trial_id"] == "LOSER"]
    assert loser_states == [PREREGISTERED, "REJECTED"]
    problems = ledger.verify()
    assert problems == []


def test_the_ledger_file_cannot_be_edited_without_detection(ledger):
    ledger.append(_identity(trial_id="T1", purpose="p"))
    ledger.append(_identity(trial_id="T1", state="FAILED", purpose="p",
                             outcome={"reason": "x"}))
    text = ledger.path.read_text(encoding="utf-8")
    tampered = text.replace('"FAILED"', '"SURVIVED"')
    ledger.path.write_text(tampered, encoding="utf-8")
    problems = ledger.verify()
    assert any("digest mismatch" in p for p in problems)


# -- 5. identity levels cannot accidentally collapse -------------------------


def test_one_lineage_can_hold_many_configs_without_collapsing_counts(ledger):
    for i in range(5):
        ledger.append(_identity(config_id=f"CFG_{i}", trial_id=f"T{i}",
                                 lineage_id="SHARED_LINEAGE"))
    records = ledger.records_for(lineage_id="SHARED_LINEAGE")
    distinct_configs = {r.payload["config_id"] for r in records}
    distinct_lineages = {r.payload["lineage_id"] for r in records}
    assert len(distinct_configs) == 5, "five config attempts must not collapse into one"
    assert len(distinct_lineages) == 1, "they are still one lineage, not five"


def test_every_identity_field_is_required(ledger):
    for field in IDENTITY_FIELDS:
        payload = _identity(trial_id=f"missing-{field}")
        del payload[field]
        with pytest.raises(TrialLedgerError):
            ledger.append(payload)


# -- 6. malformed records fail existing validation ---------------------------


def test_an_unknown_state_is_rejected(ledger):
    with pytest.raises(TrialLedgerError):
        ledger.append(_identity(state="WINNING"))


def test_a_preregistered_record_may_not_carry_an_outcome(ledger):
    with pytest.raises(TrialLedgerError):
        ledger.append(_identity(state=PREREGISTERED, outcome={"reason": "too early"}))


def test_a_terminal_record_must_carry_an_outcome(ledger):
    ledger.append(_identity(trial_id="T1", purpose="p"))
    with pytest.raises(TrialLedgerError):
        ledger.append(_identity(trial_id="T1", state="FAILED", purpose="p"))


# -- 7. result-only retroactive registration cannot masquerade as valid -----
# -- preregistration ---------------------------------------------------------


def test_a_terminal_record_with_no_prior_preregistration_is_refused(ledger):
    with pytest.raises(TrialLedgerError, match="no PREREGISTERED record"):
        ledger.append(_identity(trial_id="NEVER_PREREGISTERED", state="SURVIVED",
                                 outcome={"reason": "looks good after the fact"}))
    assert ledger.records() == []


def test_a_trial_id_cannot_be_preregistered_twice(ledger):
    ledger.append(_identity(trial_id="T1", purpose="p"))
    with pytest.raises(TrialLedgerError, match="already preregistered"):
        ledger.append(_identity(trial_id="T1", purpose="p"))


def test_the_declared_purpose_cannot_change_between_preregistration_and_outcome(ledger):
    ledger.append(_identity(trial_id="T1", purpose="the original stated purpose"))
    with pytest.raises(TrialLedgerError, match="purpose"):
        ledger.append(_identity(trial_id="T1", state="SURVIVED",
                                 purpose="a purpose rewritten after seeing the result",
                                 outcome={"reason": "great result"}))


def test_verify_flags_a_terminal_record_smuggled_in_without_a_preregistration(ledger):
    """Even a chain that is internally hash-consistent must still fail ``verify``
    if a terminal record's trial_id has no preregistration — proving the
    integrity check does not rely solely on ``append`` having been used."""
    ledger.append(_identity(trial_id="T1", purpose="p"))
    ledger.append(_identity(trial_id="T1", state="FAILED", purpose="p",
                             outcome={"reason": "x"}))
    # Hand-append a well-formed, correctly-chained record for a trial_id that
    # was never preregistered — bypassing TrialLedger.append entirely.
    import json

    from fp.ledger import record_digest

    seq, prev = ledger.head()
    payload = _identity(trial_id="SMUGGLED", state="SURVIVED", purpose="p",
                         outcome={"reason": "never preregistered"})
    stamp = "2026-09-29T00:00:00.000Z"
    digest = record_digest(seq, "trial", stamp, prev, payload)
    line = json.dumps({"seq": seq, "kind": "trial", "recorded_utc": stamp,
                        "prev_digest": prev, "digest": digest, "payload": payload},
                       sort_keys=True) + "\n"
    with open(ledger.path, "a", encoding="utf-8") as fh:
        fh.write(line)
    problems = ledger.verify()
    assert any("retroactive registration" in p for p in problems)
