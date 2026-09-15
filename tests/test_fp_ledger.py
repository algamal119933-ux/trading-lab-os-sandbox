"""Append-only evidence ledgers (FP-BOOT-1 sections 8, 16, 26).

The ledger's whole value is that a record cannot be changed after it is written.
These tests attack that property directly rather than checking that writing and
reading round-trip.
"""

from __future__ import annotations

import json

import pytest

from fp.ledger import (
    GENESIS_DIGEST,
    LEDGER_KINDS,
    Ledger,
    LedgerError,
    canonical_payload,
    daily_pack_digest,
    open_ledgers,
    record_digest,
)


@pytest.fixture
def decision_ledger(tmp_path) -> Ledger:
    return Ledger(tmp_path / "paper_decision_ledger.jsonl", "decision")


def test_unknown_kind_is_rejected(tmp_path):
    """A typo'd kind would silently create a second, invisible ledger."""
    with pytest.raises(LedgerError):
        Ledger(tmp_path / "x.jsonl", "decisions")


def test_kinds_are_the_specification_ledgers():
    assert LEDGER_KINDS == ("input", "decision", "trade", "incident")


def test_empty_ledger_reads_as_empty(decision_ledger):
    assert decision_ledger.records() == []
    assert decision_ledger.head() == (0, GENESIS_DIGEST)
    assert decision_ledger.verify() == []


def test_appends_chain_and_verify(decision_ledger):
    first = decision_ledger.append({"candle_ts": 1, "intended_action": "hold"})
    second = decision_ledger.append({"candle_ts": 2, "intended_action": "enter_long"})

    assert first.seq == 0 and second.seq == 1
    assert first.prev_digest == GENESIS_DIGEST
    assert second.prev_digest == first.digest
    assert decision_ledger.verify() == []
    assert decision_ledger.tip_digest() == second.digest


def test_altered_payload_is_detected(decision_ledger):
    decision_ledger.append({"candle_ts": 1, "intended_action": "enter_long"})
    decision_ledger.append({"candle_ts": 2, "intended_action": "hold"})

    lines = decision_ledger.path.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[0])
    record["payload"]["intended_action"] = "exit_long"
    lines[0] = json.dumps(record, sort_keys=True)
    decision_ledger.path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    problems = decision_ledger.verify()
    assert any("digest mismatch" in p for p in problems)


def test_deleted_record_is_detected(decision_ledger):
    """Removing a middle record must not leave a chain that still verifies."""
    for ts in (1, 2, 3):
        decision_ledger.append({"candle_ts": ts})

    lines = decision_ledger.path.read_text(encoding="utf-8").splitlines()
    del lines[1]
    decision_ledger.path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    problems = decision_ledger.verify()
    assert any("out-of-order sequence" in p for p in problems)
    assert any("broken chain" in p for p in problems)


def test_reordered_records_are_detected(decision_ledger):
    for ts in (1, 2):
        decision_ledger.append({"candle_ts": ts})
    lines = decision_ledger.path.read_text(encoding="utf-8").splitlines()
    decision_ledger.path.write_text("\n".join(reversed(lines)) + "\n", encoding="utf-8")

    assert decision_ledger.verify() != []


def test_erratum_appends_and_does_not_rewrite(decision_ledger):
    """Section 26: corrections are appended as errata, not silently rewritten."""
    original = decision_ledger.append({"candle_ts": 1, "fee": 0.01})
    erratum = decision_ledger.append_erratum(original.seq, "fee misreported", {"fee": 0.02})

    assert decision_ledger.verify() == []
    assert erratum.payload["erratum"] is True
    assert erratum.payload["corrects_seq"] == original.seq
    # The corrected record is untouched and still valid.
    assert decision_ledger.records()[0].digest == original.digest
    assert decision_ledger.records()[0].payload == {"candle_ts": 1, "fee": 0.01}


def test_erratum_for_unknown_sequence_is_refused(decision_ledger):
    decision_ledger.append({"candle_ts": 1})
    with pytest.raises(LedgerError):
        decision_ledger.append_erratum(99, "typo", {})


def test_non_utc_timestamp_is_refused(decision_ledger):
    with pytest.raises(LedgerError):
        decision_ledger.append({"a": 1}, recorded_utc="2026-09-07 10:00:00")


def test_non_dict_payload_is_refused(decision_ledger):
    with pytest.raises(LedgerError):
        decision_ledger.append(["not", "a", "dict"])


def test_canonical_payload_is_key_order_independent():
    """A formatting change must not move the digest; a content change must."""
    a = canonical_payload({"b": 2, "a": 1})
    b = canonical_payload({"a": 1, "b": 2})
    assert a == b
    assert canonical_payload({"a": 1, "b": 3}) != a


def test_digest_covers_every_envelope_field():
    base = dict(seq=0, kind="decision", recorded_utc="2026-09-07T00:00:00Z", prev_digest="0" * 64, payload={"a": 1})
    reference = record_digest(**base)
    assert record_digest(**{**base, "seq": 1}) != reference
    assert record_digest(**{**base, "kind": "trade"}) != reference
    assert record_digest(**{**base, "recorded_utc": "2026-09-07T00:00:01Z"}) != reference
    assert record_digest(**{**base, "prev_digest": "1" * 64}) != reference
    assert record_digest(**{**base, "payload": {"a": 2}}) != reference


def test_open_ledgers_creates_the_four_specification_ledgers(tmp_path):
    ledgers = open_ledgers(tmp_path, create=True)
    assert set(ledgers) == set(LEDGER_KINDS)
    assert ledgers["incident"].path.name == "paper_incident_ledger.jsonl"


def test_daily_pack_digest_tracks_ledger_tips(tmp_path):
    """Section 26: the daily pack has its own digest, bound to what it covers."""
    ledgers = open_ledgers(tmp_path, create=True)
    before = daily_pack_digest(ledgers.values())
    ledgers["trade"].append({"trade_id": 1})
    after = daily_pack_digest(ledgers.values())
    assert before != after
    assert daily_pack_digest(ledgers.values()) == after


def test_appends_survive_reopening(tmp_path):
    """A restart must continue the chain, not start a second one."""
    path = tmp_path / "paper_input_ledger.jsonl"
    Ledger(path, "input").append({"candle_ts": 1})
    reopened = Ledger(path, "input")
    second = reopened.append({"candle_ts": 2})
    assert second.seq == 1
    assert reopened.verify() == []


def test_extend_produces_the_same_chain_as_repeated_appends(tmp_path):
    """The batch form is a durability optimisation, not a different ledger."""
    payloads = [{"candle_ts": ts} for ts in range(1, 6)]

    one_at_a_time = Ledger(tmp_path / "a.jsonl", "input")
    for payload in payloads:
        one_at_a_time.append(payload, recorded_utc="2026-09-07T00:00:00.000Z")

    batched = Ledger(tmp_path / "b.jsonl", "input")
    batched.extend(payloads, recorded_utc="2026-09-07T00:00:00.000Z")

    assert [r.digest for r in batched] == [r.digest for r in one_at_a_time]
    assert batched.verify() == []


def test_extend_continues_an_existing_chain(tmp_path):
    ledger = Ledger(tmp_path / "c.jsonl", "input")
    first = ledger.append({"candle_ts": 1})
    written = ledger.extend([{"candle_ts": 2}, {"candle_ts": 3}])
    assert [r.seq for r in written] == [1, 2]
    assert written[0].prev_digest == first.digest
    assert ledger.verify() == []


def test_extend_rejects_a_non_dict_payload_before_writing_anything(tmp_path):
    ledger = Ledger(tmp_path / "d.jsonl", "input")
    with pytest.raises(LedgerError):
        ledger.extend([{"ok": True}, "not a dict"])
    assert ledger.records() == [], "a rejected batch must not leave a partial write"


def test_extend_of_nothing_is_a_no_op(tmp_path):
    ledger = Ledger(tmp_path / "e.jsonl", "input")
    assert ledger.extend([]) == []
    assert ledger.verify() == []
