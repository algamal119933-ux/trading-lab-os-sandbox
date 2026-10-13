"""AUTH-2 operator gate (.github/gates/auth2_operator.py): the pre-dispatch guard in Actions only ever
adds refusals to research/auth2/dispatch_guard.decide, a dispatch needs a fresh, successful guard run's
DISPATCH record on the current main, and the published records survive the annotation channel byte-exact.

The Owner billing evidence bridge (AUTH2-OWNER-BILLING-EVIDENCE-BRIDGE-1): the two pacing-rule controls GitHub
does not expose for a personal account are the Owner's attestation in the guard run, authenticated by the run's
actor as the Actions API reports it; a node or closure run is bound to that guard record by its run id and
evidence digest; A_m is the month's first node run's. ``World`` is a synthetic GitHub that drives the whole
bridge end to end: the Owner's guard run, the executor's check, the node's in-job guard and the next month.

The program charter (Owner decision OD-C4): nothing dispatches unless the AUTH-2 charter says ACTIVE, at the
Owner's guard, the executor's check and the in-job guard alike. ``World`` reads the charter AUTH-2 ran under
(status ACTIVE) unless a test closes it; this checkout's own charter is CLOSED (AUTH2-GOVERNANCE-CLOSURE-1).

PAPER / RESEARCH ONLY. Nothing here calls GitHub: every function under test is pure or runs against ``World``.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import importlib.util
import io
import json
import math
import re
import subprocess
import sys
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

pytest.importorskip("numpy")
yaml = pytest.importorskip("yaml")

from auth2 import dispatch_guard as DG  # noqa: E402
from auth2 import run_node as RN  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
WF = REPO / ".github" / "workflows"
_spec = importlib.util.spec_from_file_location("auth2_operator", REPO / ".github" / "gates" / "auth2_operator.py")
OP = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(OP)

MAIN = "a" * 40
NOW = datetime(2026, 11, 3, 10, 0, tzinfo=timezone.utc)
OWNER = "algamal119933-ux"
OWNER_USER = {"login": OWNER, "id": 325778659}
OTHER_USER = {"login": "someone-else", "id": 4242}
SLUG = f"{OWNER}/trading-lab-os-sandbox"
USAGE_PATH = f"/users/{OWNER}/settings/billing/usage"
OCT = datetime(2026, 10, 12, 0, 5, tzinfo=timezone.utc)
TOKEN = "TESTONLY-billing-token-0123456789"  # not a token format: the hygiene gate scans for real ones

# The AUTH-2 charter: CLOSED in this checkout since AUTH2-GOVERNANCE-CLOSURE-1 (OD-C3); as run, it said ACTIVE.
CHARTER_CLOSED = (REPO / OP.CHARTER_REL).read_bytes()
CHARTER_AS_RUN = (json.dumps({**json.loads(CHARTER_CLOSED), "status": "ACTIVE"}, indent=1, sort_keys=True,
                             ensure_ascii=False) + "\n").encode()
ACTIVE = {"path": OP.CHARTER_REL, "rev": "working tree", "status": "ACTIVE",
          "sha256": hashlib.sha256(CHARTER_AS_RUN).hexdigest()}


def state(**kw) -> dict:
    s = {"now": "2026-11-03T10:00:00Z", "self_run_id": None,
         "billing": {"readable": True, "remaining_included_minutes": 2000, "budget_usd_zero": True},
         "runs": [], "charter": ACTIVE}
    s.update(kw)
    return s


def aux(i, workflow=OP.GUARD_WORKFLOW, status="completed", conclusion="success", minutes=2,
        created="2026-11-03T09:00:00Z"):
    return {"id": i, "workflow": workflow, "status": status, "conclusion": conclusion, "created_at": created,
            "minutes": minutes}


# -- the decision only adds refusals ---------------------------------------------------------------

@pytest.mark.parametrize("node,part", [("D0", 1), ("PC-A2", 2), ("HOLM", 1), ("SC-A3", 1)])
def test_with_no_guard_or_closure_runs_the_decision_is_dispatch_guards(node, part):
    for s in (state(), state(billing={"readable": False}),
              state(billing={"readable": True, "remaining_included_minutes": 700, "budget_usd_zero": True})):
        base = DG.decide(json.loads(json.dumps(s)), node, part)
        mine = OP.decide(s, [], node, part)
        assert mine["decision"] == base["decision"]
        assert mine["reasons"][:len(base["reasons"])] == base["reasons"]  # it only adds refusals
        added = mine["reasons"][len(base["reasons"]):]
        assert added == ([] if s["billing"].get("budget_usd_zero") else
                         ["FAIL_CLOSED: an Actions budget of USD 0 that stops usage is not verified"])


def test_unreadable_billing_never_dispatches():
    d = OP.decide(state(billing={"readable": False, "reason": "HTTP 403"}), [aux(1)], "D0", 1)
    assert d["decision"] == DG.NO_DISPATCH and any(r.startswith("FAIL_CLOSED") for r in d["reasons"])
    assert d["billing"]["readable"] is False


def test_an_active_guard_or_closure_run_blocks_dispatch():
    d = OP.decide(state(), [aux(5, status="in_progress", conclusion=None)], "D0", 1)
    assert d["decision"] == DG.NO_DISPATCH and any(r.startswith("SERIAL") for r in d["reasons"])


def test_guard_and_closure_minutes_count_toward_the_4000_cap():
    big = {"readable": True, "remaining_included_minutes": 100000, "budget_usd_zero": True}
    ok = OP.decide(state(billing=big), [aux(1, minutes=3000)], "PC-A2", 1)  # 3000 + 2 x 180 = 3360
    assert ok["decision"] == DG.DISPATCH and ok["total_minutes_ledger"] == 3000
    d = OP.decide(state(billing=big), [aux(1, minutes=3700)], "PC-A2", 1)  # 3700 + 360 > 4000
    assert d["decision"] == DG.NO_DISPATCH and any(r.startswith("CAP: minutes") for r in d["reasons"])


def test_closure_is_guarded_with_its_own_rerun_and_attempt_rules():
    holm_done = [{"id": 1, "node": "HOLM", "part": 1, "status": "completed", "conclusion": "success",
                  "created_at": "2026-11-01T00:00:00Z",
                  "jobs": [{"status": "completed", "started_at": "2026-11-01T00:00:00Z",
                            "completed_at": "2026-11-01T00:02:00Z"}],
                  "guard": {"month": "2026-11", "a_m": 2000}}]
    d = OP.decide(state(runs=holm_done), [], OP.CLOSURE, 1)
    assert d["decision"] == DG.DISPATCH and d["node"] == OP.CLOSURE  # HOLM succeeded: not a re-run of CLOSURE
    assert d["timeout_minutes"] == OP.CLOSURE_TIMEOUT
    done = OP.decide(state(runs=holm_done), [aux(2, OP.CLOSURE_WORKFLOW)], OP.CLOSURE, 1)
    assert any(r.startswith("NEVER_RERUN: CLOSURE") for r in done["reasons"])
    spent = OP.decide(state(runs=holm_done), [aux(2, OP.CLOSURE_WORKFLOW, conclusion="failure"),
                                              aux(3, OP.CLOSURE_WORKFLOW, conclusion="failure")], OP.CLOSURE, 1)
    assert any(r.startswith("ATTEMPTS") for r in spent["reasons"])
    low = OP.decide(state(billing={"readable": True, "remaining_included_minutes": 535, "budget_usd_zero": True}),
                    [], OP.CLOSURE, 1)  # 535 - 2 x 20 < 500, although 535 - 2 x 15 >= 500
    assert low["decision"] == DG.PARK


# -- the annotation channel ------------------------------------------------------------------------

def notes_from(lines: str) -> list[dict]:
    out = []
    for line in lines.splitlines():
        m = re.fullmatch(r"::notice title=([A-Z0-9_]+)::(.*)", line)
        assert m, line
        out.append({"title": m[1], "message": m[2], "annotation_level": "notice"})
    return out


@pytest.mark.parametrize("size", [0, 10, OP.CHUNK, 3 * OP.CHUNK + 7])
def test_published_bytes_round_trip_exactly(size):
    data = bytes(range(256)) * (size // 256) + bytes(size % 256)
    notes = notes_from(OP.annotation_lines(OP.CLOSURE_RECORD, data))
    assert OP.decode_annotations(notes, OP.CLOSURE_RECORD) == [data]
    assert OP.decode_annotations(notes, OP.RECORD) == []


def test_a_tampered_or_incomplete_publication_is_refused():
    data = b"x" * (2 * OP.CHUNK)
    notes = notes_from(OP.annotation_lines(OP.CLOSURE_RECORD, data))
    with pytest.raises(ValueError, match="incomplete"):
        OP.decode_annotations(notes[:-1], OP.CLOSURE_RECORD)
    sha, i, rest = notes[0]["message"].split(":", 2)
    forged = base64.b64encode(b"y" * 12000).decode()
    bad = [{**notes[0], "message": f"{sha}:{i}:{forged}"}] + notes[1:]
    with pytest.raises(ValueError, match="sha256"):
        OP.decode_annotations(bad, OP.CLOSURE_RECORD)
    with pytest.raises(SystemExit):
        OP.annotation_lines(OP.CLOSURE_RECORD, b"z" * (11 * OP.CHUNK))


def test_result_summaries_carry_what_the_frozen_dag_reads(tmp_path):
    (tmp_path / "D0.result.json").write_text(json.dumps(
        {"terminal_state": "PASS", "data_limited": {"A1": False, "A2": False, "A3": True}, "program_sha256": "p"}))
    lines = OP.annotate_results(tmp_path)
    [payload] = OP.decode_annotations(notes_from(lines), OP.RESULT)
    [s] = json.loads(payload)
    assert s["key"] == "D0" and s["terminal_state"] == "PASS"
    assert s["sha256"] == hashlib.sha256((tmp_path / "D0.result.json").read_bytes()).hexdigest()
    nxt = OP.next_nodes({"D0": s})
    assert nxt == RN.eligible({"D0": json.loads((tmp_path / "D0.result.json").read_text())})
    assert ("CAL-A1", 1) in nxt["next"] and not any(n.endswith("A3") for n, _ in nxt["next"])


# -- check-dispatch: a fresh, successful Owner guard record on main --------------------------------------

USAGE_OK = {"verified": True, "status": 200, "class": "USAGE_VERIFIED", "period": "2026-11", "endpoint": USAGE_PATH,
            "actions": {}}


def guard_run(i=100, node="D0", part=1, sha=MAIN, conclusion="success", created="2026-11-03T09:55:00Z", **kw):
    r = {"id": i, "path": f".github/workflows/{OP.GUARD_WORKFLOW}", "event": "workflow_dispatch",
         "head_branch": "main", "head_sha": sha, "status": "completed", "conclusion": conclusion,
         "display_title": f"AUTH2-GUARD {node} part {part}", "created_at": created, "run_attempt": 1,
         "actor": OWNER_USER, "triggering_actor": OWNER_USER, "repository": {"full_name": SLUG}}
    r.update(kw)
    return r


def evidence(run_id=100, node="D0", part=1, sha=MAIN, attested="2026-11-03T09:55:00Z", tamper=False, **kw) -> dict:
    """Valid Owner evidence of guard run ``run_id``. ``kw`` changes fields; the digest then covers the change,
    unless ``tamper`` (the object was edited after it was digested) or ``evidence_digest`` is given."""
    ev = {"schema": OP.EVIDENCE_SCHEMA, "repository": SLUG, "guard_run_id": run_id, "guard_run_attempt": 1,
          "main_sha": sha, "node": node, "part": part, "actor": OWNER, "actor_id": 325778659,
          "triggering_actor": OWNER, "triggering_actor_id": 325778659, "billing_month": attested[:7],
          "remaining_included_linux_minutes": 2400, "budget_usd_zero_confirmed": True, "stop_usage_confirmed": True,
          "attested_utc": attested, "usage_api_verified": True, "usage_endpoint": USAGE_PATH,
          "usage_period": attested[:7]}
    ev["evidence_digest"] = OP.evidence_digest(ev)
    ev.update(kw)
    if not tamper and "evidence_digest" not in kw:
        ev["evidence_digest"] = OP.evidence_digest(ev)
    return ev


def billing(ev, **kw) -> dict:
    b = {"readable": True, "remaining_included_minutes": ev["remaining_included_linux_minutes"],
         "budget_usd_zero": True, "usage_evidence": USAGE_OK, "owner_evidence": ev, "owner_evidence_problems": []}
    b.update(kw)
    return b


def record(node="D0", part=1, decision=DG.DISPATCH, checked="2026-11-03T09:55:30Z", run_id=100, sha=MAIN,
           ev=None, bill=None, **kw) -> list[dict]:
    """The annotations of a guard run's published record; ``kw`` replaces record fields."""
    ev = evidence(run_id=run_id, node=node, part=part, sha=sha) if ev is None else ev
    body = {"node": node, "part": part, "decision": decision, "mode": "pre-dispatch", "checked_utc": checked,
            "run_id": run_id, "sha": sha, "run_attempt": 1, "reasons": [] if decision == DG.DISPATCH else ["X"],
            "billing": billing(ev) if bill is None else bill, "charter": ACTIVE}
    body.update(kw)
    return notes_from(OP.annotation_lines(OP.RECORD, (json.dumps(body) + "\n").encode()))


def check(run, notes, later=(), node="D0", part=1, main=MAIN, now=NOW, **kw) -> dict:
    return OP.check_dispatch(run, OP.annotated_records(notes), list(later), node, part, main, now, slug=SLUG, **kw)


LATER = [{"id": 100, "status": "completed", "created_at": "2026-11-03T09:55:00Z"}]


def test_a_fresh_successful_dispatch_record_on_main_dispatches():
    d = check(guard_run(), record(), LATER)
    assert d["decision"] == DG.DISPATCH, d["reasons"]
    ev = evidence()
    assert d["owner_evidence"] == ev
    assert d["dispatch_inputs"] == {"node": "D0", "part": "1", "guard_run": "100",
                                    "evidence_digest": ev["evidence_digest"]}
    assert check(guard_run(), record(), LATER, digest=ev["evidence_digest"])["decision"] == DG.DISPATCH


@pytest.mark.parametrize("run,notes,later,why", [
    (guard_run(conclusion="failure"), record(), [], "did not succeed"),
    (guard_run(), record(decision=DG.NO_DISPATCH), [], "guard decided NO_DISPATCH"),
    (guard_run(sha="b" * 40), record(sha="b" * 40), [], "not main"),
    (guard_run(path=".github/workflows/ci.yml"), record(), [], "not a run of"),
    (guard_run(event="push"), record(), [], "not a workflow_dispatch run on main"),
    (guard_run(node="CAL-A1"), record(node="CAL-A1"), [], "titled"),
    (guard_run(), record(checked="2026-11-03T09:30:00Z"), [], "not fresh"),
    (guard_run(), record(run_id=99), [], "does not name this run"),
    (guard_run(), [], [], "unreadable"),
    (guard_run(), record() + record(), [], "unreadable"),
    (guard_run(), record(), [{"id": 101, "status": "completed", "created_at": "2026-11-03T09:56:00Z"}],
     "created after"),
    (guard_run(), record(), [{"id": 7, "status": "queued", "created_at": "2026-11-02T00:00:00Z"}], "SERIAL"),
    # who dispatched the guard run, at which attempt, in which repository: the Actions API's answer
    (guard_run(actor=OTHER_USER, triggering_actor=OTHER_USER), record(), [], "OWNER_EVIDENCE_ACTOR_MISMATCH"),
    (guard_run(triggering_actor=OTHER_USER), record(), [], "OWNER_EVIDENCE_ACTOR_MISMATCH"),
    (guard_run(actor=OTHER_USER), record(), [], "OWNER_EVIDENCE_ACTOR_MISMATCH"),
    (guard_run(actor={"login": OWNER, "id": 1}, triggering_actor={"login": OWNER, "id": 1}), record(), [],
     "OWNER_EVIDENCE_ACTOR_MISMATCH"),
    (guard_run(run_attempt=2), record(), [], "OWNER_EVIDENCE_REPLAYED"),
    (guard_run(repository={"full_name": "someone-else/fork"}), record(), [], f"is not a run of {SLUG}"),
    (guard_run(created="2026-11-03T09:54:00Z"), record(), [], "attestation time is not the guard run's dispatch"),
    (guard_run(), record(run_attempt=2), [], "does not name this run, its first attempt and main"),
    (guard_run(), record(mode="in-job"), [], "guard record is for"),
    # the record's Owner evidence
    (guard_run(), record(bill=billing(evidence(), owner_evidence=None)), [], "OWNER_EVIDENCE_MISSING"),
    (guard_run(), record(ev=evidence(tamper=True, remaining_included_linux_minutes=99999)), [],
     "OWNER_EVIDENCE_DIGEST_MISMATCH"),
    (guard_run(), record(ev=evidence(evidence_digest="sha256:" + "0" * 64)), [], "OWNER_EVIDENCE_DIGEST_MISMATCH"),
    (guard_run(), record(ev=evidence(evidence_digest="0" * 64)), [], "OWNER_EVIDENCE_DIGEST_MISMATCH"),
    (guard_run(), record(ev=evidence(actor="someone-else", triggering_actor="someone-else")), [],
     "OWNER_EVIDENCE_ACTOR_MISMATCH"),
    (guard_run(), record(ev=evidence(actor_id=1, triggering_actor_id=1)), [], "OWNER_EVIDENCE_ACTOR_MISMATCH"),
    (guard_run(), record(ev=evidence(actor="someone-else")), [], "OWNER_EVIDENCE_ACTOR_MISMATCH"),
    (guard_run(), record(ev=evidence(actor_id=1)), [], "OWNER_EVIDENCE_ACTOR_MISMATCH"),
    (guard_run(), record(ev=evidence(triggering_actor="someone-else")), [], "OWNER_EVIDENCE_ACTOR_MISMATCH"),
    (guard_run(), record(ev=evidence(triggering_actor_id=1)), [], "OWNER_EVIDENCE_ACTOR_MISMATCH"),
    (guard_run(), record(ev=evidence(guard_run_id=99)), [], "OWNER_EVIDENCE_WRONG_RUN"),
    (guard_run(), record(ev=evidence(guard_run_attempt=2)), [], "OWNER_EVIDENCE_REPLAYED"),
    (guard_run(), record(ev=evidence(main_sha="b" * 40)), [], "OWNER_EVIDENCE_WRONG_SHA"),
    (guard_run(), record(ev=evidence(node="CAL-A1")), [], "OWNER_EVIDENCE_WRONG_NODE"),
    (guard_run(), record(ev=evidence(part=2)), [], "OWNER_EVIDENCE_WRONG_NODE"),
    (guard_run(), record(ev=evidence(repository="someone-else/fork")), [], "OWNER_EVIDENCE_WRONG_REPOSITORY"),
    (guard_run(), record(ev=evidence(billing_month="2026-10")), [], "OWNER_EVIDENCE_WRONG_MONTH"),
    (guard_run(), record(ev=evidence(usage_period="2026-10")), [], "OWNER_EVIDENCE_WRONG_MONTH"),
    (guard_run(created="2026-10-31T23:59:00Z"), record(ev=evidence(attested="2026-10-31T23:59:00Z")), [],
     "OWNER_EVIDENCE_WRONG_MONTH"),
    (guard_run(), record(ev=evidence(remaining_included_linux_minutes=-1)), [], "OWNER_EVIDENCE_REMAINING_INVALID"),
    (guard_run(), record(ev=evidence(remaining_included_linux_minutes="2400")), [], "OWNER_EVIDENCE_MALFORMED"),
    (guard_run(), record(ev=evidence(remaining_included_linux_minutes=True)), [], "OWNER_EVIDENCE_MALFORMED"),
    (guard_run(), record(ev=evidence(budget_usd_zero_confirmed=False)), [], "OWNER_EVIDENCE_BUDGET_NOT_CONFIRMED"),
    (guard_run(), record(ev=evidence(stop_usage_confirmed=False)), [], "OWNER_EVIDENCE_STOP_USAGE_NOT_CONFIRMED"),
    (guard_run(), record(ev=evidence(usage_api_verified=False)), [], "OWNER_EVIDENCE_USAGE_NOT_VERIFIED"),
    (guard_run(), record(ev=evidence(usage_endpoint="/users/someone-else/settings/billing/usage")), [],
     "OWNER_EVIDENCE_USAGE_NOT_VERIFIED"),
    (guard_run(), record(ev=evidence(schema="AUTH2_OWNER_BILLING_EVIDENCE_0")), [], "OWNER_EVIDENCE_MALFORMED"),
    (guard_run(), record(ev=evidence(note="an extra field")), [], "OWNER_EVIDENCE_MALFORMED"),
    (guard_run(), record(ev=evidence(attested_utc="2026-11-03 09:55")), [], "OWNER_EVIDENCE_MALFORMED"),
    # the record's billing state rests on that evidence and on a verified usage report
    (guard_run(), record(bill=billing(evidence(), remaining_included_minutes=99999)), [],
     "does not rest on its Owner evidence"),
    (guard_run(), record(bill=billing(evidence(), budget_usd_zero=False)), [], "does not rest on its Owner evidence"),
    (guard_run(), record(bill=billing(evidence(), readable=False)), [], "does not rest on its Owner evidence"),
    (guard_run(), record(bill=billing(evidence(), usage_evidence={**USAGE_OK, "verified": False})), [],
     "usage report is not verified"),
    (guard_run(), record(bill=billing(evidence(), usage_evidence={**USAGE_OK, "period": "2026-10"})), [],
     "usage report is not verified"),
    (guard_run(), record(bill=billing(evidence(), usage_evidence={**USAGE_OK, "class": "TOKEN_MISSING"})), [],
     "usage report is not verified"),
    (guard_run(), record(bill=billing(evidence(), usage_evidence={**USAGE_OK, "endpoint": "/x"})), [],
     "usage report is not verified"),
    (guard_run(), record(bill=billing(evidence(), usage_evidence=None)), [], "usage report is not verified"),
    # the record shows the program charter ACTIVE (OD-C4)
    (guard_run(), record(charter={**ACTIVE, "status": "CLOSED"}), [], "CHARTER_NOT_ACTIVE"),
    (guard_run(), record(charter={**ACTIVE, "status": "active"}), [], "CHARTER_NOT_ACTIVE"),
    (guard_run(), record(charter={**ACTIVE, "error": "OSError: unreadable"}), [], "CHARTER_NOT_ACTIVE"),
    (guard_run(), record(charter={"path": OP.CHARTER_REL, "rev": "working tree", "error": "x"}), [],
     "CHARTER_NOT_ACTIVE"),
    (guard_run(), record(charter={**ACTIVE, "error": ""}), [], "CHARTER_NOT_ACTIVE"),
    (guard_run(), record(charter=None), [], "CHARTER_NOT_ACTIVE"),
    (guard_run(), record(charter="ACTIVE"), [], "CHARTER_NOT_ACTIVE"),
])
def test_anything_short_of_that_never_dispatches(run, notes, later, why):
    d = check(run, notes, later)
    assert d["decision"] == DG.NO_DISPATCH and d["dispatch_inputs"] is None and d["owner_evidence"] is None
    assert any(why in r for r in d["reasons"]), d["reasons"]


def test_a_record_from_the_future_is_not_fresh():
    d = check(guard_run(), record(checked=(NOW + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")))
    assert any("not fresh" in r for r in d["reasons"])


def test_a_dispatch_naming_another_digest_never_dispatches():
    d = check(guard_run(), record(), LATER, digest="sha256:" + "0" * 64)
    assert d["decision"] == DG.NO_DISPATCH and any("OWNER_EVIDENCE_DIGEST_MISMATCH" in r for r in d["reasons"])


# -- the Owner's inputs and the evidence object --------------------------------------------------------

INPUTS = {"remaining_included_linux_minutes": "2400", "actions_budget_usd_zero": "CONFIRMED",
          "stop_usage_enabled": "CONFIRMED"}


def test_the_owner_is_the_repository_owners_account():
    assert (OP.OWNER_LOGIN, OP.OWNER_ID) == (OWNER, 325778659) and SLUG.split("/")[0] == OP.OWNER_LOGIN
    assert OP.USAGE_ENDPOINT.format(owner=OP.OWNER_LOGIN) == USAGE_PATH


def test_the_owner_inputs_parse_strictly():
    assert OP.parse_owner_inputs(INPUTS) == ({"budget_usd_zero_confirmed": True, "stop_usage_confirmed": True,
                                              "remaining_included_linux_minutes": 2400}, [])
    assert OP.parse_owner_inputs({**INPUTS, "remaining_included_linux_minutes": "0"})[0][OP.MINUTES_INPUT] == 0
    values, problems = OP.parse_owner_inputs({**INPUTS, "actions_budget_usd_zero": "NOT_CONFIRMED"})
    assert problems == [] and values["budget_usd_zero_confirmed"] is False  # parsed, and refused as evidence


@pytest.mark.parametrize("raw", ["-5", "-0", "+5", "12.5", "2400.0", "1,000", "1 000", " 100", "100 ", "0100", "00",
                                 "2e3", "0x10", "١٢٣", "½", "1234567890", "None", "true", "∞", 2400])
def test_a_remaining_minutes_value_that_is_not_plain_digits_is_refused(raw):
    values, problems = OP.parse_owner_inputs({**INPUTS, "remaining_included_linux_minutes": raw})
    assert values is None and problems and problems[0].startswith("OWNER_EVIDENCE_REMAINING_INVALID")


@pytest.mark.parametrize("value", ["yes", "Yes", "true", "True", "1", "on", "y", "confirmed", "Confirmed",
                                   "CONFIRMED ", True])
def test_a_confirmation_is_only_the_choice_confirmed(value):
    for key in OP.CONFIRMATIONS:
        values, problems = OP.parse_owner_inputs({**INPUTS, key: value})
        assert values is None and any(p.startswith("OWNER_EVIDENCE_MALFORMED") for p in problems)


@pytest.mark.parametrize("key", list(INPUTS))
def test_a_missing_owner_input_is_refused(key):
    for given in ({k: v for k, v in INPUTS.items() if k != key}, {**INPUTS, key: ""}, {**INPUTS, key: None}):
        values, problems = OP.parse_owner_inputs(given)
        assert values is None and problems[0].startswith("OWNER_EVIDENCE_MISSING")
    for nothing in (None, [], "inputs"):
        assert OP.parse_owner_inputs(nothing)[1][0].startswith("OWNER_EVIDENCE_MISSING")


def test_the_evidence_digest_is_deterministic_and_covers_every_field():
    ev = evidence()
    assert set(ev) == set(OP.EVIDENCE_FIELDS)
    assert not OP.owner_evidence_problems(ev, slug=SLUG, guard_run_id=100, main_sha=MAIN, node="D0", part=1,
                                          month="2026-11")
    body = {k: v for k, v in ev.items() if k != "evidence_digest"}
    assert ev["evidence_digest"] == "sha256:" + hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert OP.evidence_digest(dict(reversed(list(ev.items())))) == ev["evidence_digest"]  # key order is irrelevant
    for k, v in body.items():
        changed = {**ev, k: (not v) if isinstance(v, bool) else v + 1 if isinstance(v, int) else v + "x"}
        assert OP.evidence_digest(changed) != ev["evidence_digest"], k
        problems = OP.owner_evidence_problems(changed, slug=SLUG, guard_run_id=100, main_sha=MAIN, node="D0",
                                              part=1, month="2026-11")
        assert any(p.startswith("OWNER_EVIDENCE_DIGEST_MISMATCH") for p in problems), k


# -- a synthetic GitHub: the bridge end to end ------------------------------------------------------------

def usage_item(**kw) -> dict:
    """One usage item in the live report's form: guard run 38220977904 read the repository name without its
    owner."""
    it = {"date": "2026-10-11", "product": "Actions", "sku": "Actions Linux", "quantity": 12.0, "unitType": "Minutes",
          "pricePerUnit": 0.008, "grossAmount": 0.096, "discountAmount": 0.096, "netAmount": 0.0,
          "repositoryName": "trading-lab-os-sandbox"}
    it.update(kw)
    return it


def at(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def iso(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def zipped(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


class World:
    """One repository's AUTH-2 runs as the Actions API reports them (jobs of every attempt, artifacts,
    annotations), the account's billing usage report and the AUTH-2 charter. The operator runs against it
    unchanged: only dispatch_guard's two readers, the billing reader, the charter file reader and the operator's
    clock are replaced."""

    def __init__(self, monkeypatch, capsys, tmp_path):
        self.mp, self.capsys, self.tmp = monkeypatch, capsys, tmp_path
        self.runs: dict[int, dict] = {}
        self.jobs: dict[int, list] = {}
        self.artifacts: dict[int, list] = {}
        self.notes: dict[int, list] = {}
        self.usage = None  # None: a well-formed report of this account for the clock's month
        self.billing_calls: list = []
        self.unexpected: list = []
        self.printed: list = []
        self.charter: dict = {None: CHARTER_AS_RUN}  # by checkout: None, a job's own; a sha, that main
        self.charter_reads: list = []
        self.clock = type("Clock", (datetime,), {"at": NOW, "now": classmethod(lambda cls, tz=None: cls.at)})
        monkeypatch.setattr(OP, "datetime", self.clock)
        monkeypatch.setattr(DG, "_api", self.api)
        monkeypatch.setattr(DG, "_api_bytes", self.api_bytes)
        monkeypatch.setattr(OP, "billing_get", self.billing)
        monkeypatch.setattr(OP, "charter_bytes", self.charter_bytes)
        monkeypatch.setenv("AUTH2_BILLING_TOKEN", TOKEN)
        monkeypatch.setenv("GH_TOKEN", "workflow-token")
        for k in ("GITHUB_EVENT_PATH", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_SHA", "GITHUB_ACTOR",
                  "GITHUB_TRIGGERING_ACTOR"):
            monkeypatch.delenv(k, raising=False)

    # GitHub's side
    def api(self, path, token_env=None):
        route, _, query = path.partition("?")
        if "/settings/billing" in route:
            self.unexpected.append(f"billing read with the workflow token: {path}")
        route = route.removeprefix(f"/repos/{SLUG}")
        if m := re.fullmatch(r"/actions/workflows/([\w.-]+)/runs", route):
            first_page = "page=1" in query.split("&")
            return {"workflow_runs": [copy.deepcopy(r) for r in self.runs.values()
                                      if first_page and r["path"] == f".github/workflows/{m[1]}"]}
        if m := re.fullmatch(r"/actions/runs/(\d+)", route):
            if int(m[1]) not in self.runs:
                raise RuntimeError("gh: Not Found (HTTP 404)")
            return copy.deepcopy(self.runs[int(m[1])])
        if m := re.fullmatch(r"/actions/runs/(\d+)/jobs", route):
            run = self.runs[int(m[1])]
            jobs = self.jobs[run["id"]] if "filter=all" in query else \
                [j for j in self.jobs[run["id"]] if j["run_attempt"] == run["run_attempt"]]
            return {"jobs": copy.deepcopy(jobs)}
        if m := re.fullmatch(r"/actions/runs/(\d+)/artifacts", route):
            return {"artifacts": [{k: a[k] for k in ("id", "name", "expired")}
                                  for a in self.artifacts.get(int(m[1]), [])]}
        if m := re.fullmatch(r"/check-runs/(\d+)/annotations", route):
            return copy.deepcopy(self.notes.get(int(m[1]), []))
        self.unexpected.append(path)
        raise RuntimeError(f"gh: Not Found (HTTP 404) {path}")

    def api_bytes(self, path):
        for a in (a for arts in self.artifacts.values() for a in arts):
            if path == f"/repos/{SLUG}/actions/artifacts/{a['id']}/zip":
                return a["zip"]
        self.unexpected.append(path)
        raise RuntimeError(f"gh: Not Found (HTTP 404) {path}")

    def billing(self, path, token):
        self.billing_calls.append((path, token))
        return self.usage or (200, {"usageItems": [usage_item(date=f"{self.clock.at:%Y-%m}-01")]})

    def charter_bytes(self, rev=None, repo=None):
        """The charter file in a job's checkout (``rev`` None) or at the main the executor checks; a main the
        test does not name holds the checkout's. An exception stored there is raised, as a failed read is."""
        self.charter_reads.append(rev)
        raw = self.charter.get(rev, self.charter[None])
        if isinstance(raw, Exception):
            raise raw
        return raw

    def add(self, rid, workflow, title, created, *, status="completed", conclusion="success", attempt=1,
            actor=OWNER_USER, sha=MAIN, minutes=1) -> dict:
        start = at(created)
        self.runs[rid] = {"id": rid, "path": f".github/workflows/{workflow}", "event": "workflow_dispatch",
                          "head_branch": "main", "head_sha": sha, "status": status, "conclusion": conclusion,
                          "display_title": title, "created_at": created, "run_attempt": attempt, "actor": actor,
                          "triggering_actor": actor, "repository": {"full_name": SLUG}}
        self.jobs[rid] = [{"id": rid * 10 + n, "run_attempt": n, "status": "completed", "started_at": iso(start),
                           "completed_at": iso(start + timedelta(minutes=minutes))} for n in range(1, attempt + 1)]
        if status != "completed":
            self.jobs[rid][-1].update(status="in_progress", completed_at=None)
        return self.runs[rid]

    def finish(self, rid, conclusion, minutes=1):
        self.runs[rid].update(status="completed", conclusion=conclusion)
        job = self.jobs[rid][-1]
        job.update(status="completed", completed_at=iso(at(job["started_at"]) + timedelta(minutes=minutes)))

    def publish(self, rid, name, files: dict[str, bytes]):
        aid = 9000 + sum(len(arts) for arts in self.artifacts.values())
        self.artifacts.setdefault(rid, []).append({"id": aid, "name": name, "expired": False, "zip": zipped(files)})

    # the jobs
    def job(self, rid, argv, event, env=None) -> tuple[dict, bytes, str]:
        """Run the operator as job ``rid``'s guard step does, with the environment GitHub gives it."""
        run, n = self.runs[rid], len(self.printed)
        (self.tmp / f"event-{n}.json").write_text(json.dumps(event))
        out = self.tmp / f"record-{n}.json"
        given = {"GITHUB_RUN_ID": str(rid), "GITHUB_RUN_ATTEMPT": str(run["run_attempt"]),
                 "GITHUB_SHA": run["head_sha"], "GITHUB_EVENT_PATH": str(self.tmp / f"event-{n}.json"), **(env or {})}
        for k, v in given.items():
            self.mp.delenv(k, raising=False) if v is None else self.mp.setenv(k, v)
        self.capsys.readouterr()
        code = OP.main([*argv, "--repo-slug", SLUG, "--self-run-id", str(rid), "--out", str(out)])
        printed = self.capsys.readouterr().out
        self.printed.append(printed)
        data = out.read_bytes()
        rec = json.loads(data)
        assert code == (0 if rec["decision"] == DG.DISPATCH else 3)
        assert printed.rstrip().endswith(f"AUTH2_DISPATCH_GUARD = {rec['decision']}")
        return rec, data, printed

    def owner_guard(self, rid, node="D0", part=1, *, created="2026-11-03T09:55:00Z", minutes="2400",
                    budget="CONFIRMED", stop="CONFIRMED", inputs=None, event=None, sender=None, run=None,
                    attempt=1, env=None) -> dict:
        """The Owner dispatches auth2-guard.yml with the billing page's figures; its job starts 40 s later and
        publishes its record as an annotation and an artifact."""
        self.add(rid, OP.GUARD_WORKFLOW, f"AUTH2-GUARD {node} part {part}", created, status="in_progress",
                 conclusion=None, attempt=attempt)
        self.runs[rid].update(run or {})
        given = {"node": node, "part": str(part), "remaining_included_linux_minutes": minutes,
                 "actions_budget_usd_zero": budget, "stop_usage_enabled": stop}
        for k, v in (inputs or {}).items():
            given.pop(k) if v is None else given.update({k: v})
        payload = {"inputs": given, "sender": sender or self.runs[rid]["triggering_actor"], "ref": "refs/heads/main",
                   "repository": {"full_name": SLUG}, **(event or {})}
        self.clock.at = at(created) + timedelta(seconds=40)
        rec, data, printed = self.job(rid, ["guard", "--node", node, "--part", str(part), "--annotate"], payload, env)
        self.notes[self.jobs[rid][-1]["id"]] = notes_from(
            "\n".join(line for line in printed.splitlines() if line.startswith("::notice ")))
        self.publish(rid, f"auth2guard-{node}-p{part}", {"guard.json": data})
        self.finish(rid, "success" if rec["decision"] == DG.DISPATCH else "failure")
        return rec

    def check(self, rid, node="D0", part=1, *, when="2026-11-03T09:57:00Z", main=MAIN) -> dict:
        """The executor's ``check-dispatch`` before dispatching (it reads the record from the annotation)."""
        self.clock.at = at(when)
        self.capsys.readouterr()
        code = OP.main(["check-dispatch", "--guard-run", str(rid), "--node", node, "--part", str(part),
                        "--repo-slug", SLUG, "--main-sha", main])
        body, _, decision = self.capsys.readouterr().out.rpartition("AUTH2_DISPATCH_CHECK = ")
        rec = json.loads(body)
        assert decision.strip() == rec["decision"] and code == (0 if rec["decision"] == DG.DISPATCH else 3)
        return rec

    def dispatch(self, rid, node="D0", part=1, *, guard_run, digest, created="2026-11-03T09:58:00Z", attempt=1,
                 sha=MAIN, env=None, inputs=None, run=None) -> dict:
        """auth2.yml (auth2-closure.yml for CLOSURE) dispatched naming a guard run and an evidence digest; the
        in-job guard runs a minute later and the run's artifact keeps its record."""
        closure = node == OP.CLOSURE
        workflow, title = (OP.CLOSURE_WORKFLOW, OP.CLOSURE_TITLE) if closure else \
            (DG.WORKFLOW_FILE, f"AUTH2 {node} part {part}")
        self.add(rid, workflow, title, created, status="in_progress", conclusion=None, attempt=attempt, sha=sha)
        self.runs[rid].update(run or {})
        argv = ["guard", "--node", node, "--part", str(part), "--in-job"]
        argv += ["--guard-run", str(guard_run)] if guard_run is not None else []
        argv += ["--evidence-digest", digest] if digest is not None else []
        given = {"guard_run": str(guard_run), "evidence_digest": str(digest), **(inputs or {})}
        self.clock.at = at(created) + timedelta(seconds=60)
        rec, data, _ = self.job(rid, argv, {"inputs": given, "sender": OWNER_USER}, env)
        self.finish(rid, "success" if rec["decision"] == DG.DISPATCH else "failure", minutes=30)
        self.publish(rid, "auth2closure" if closure else f"auth2-{node}-p{part}",
                     {"guard.json": data, f"{node}.result.json": b"{}"})
        return rec


@pytest.fixture
def world(monkeypatch, capsys, tmp_path):
    w = World(monkeypatch, capsys, tmp_path)
    yield w
    assert w.unexpected == []
    assert all(token == TOKEN for _path, token in w.billing_calls)  # the billing token, never another
    assert not any(TOKEN in printed for printed in w.printed)


def d0_flow(world, minutes="2400") -> tuple[dict, dict, dict]:
    """The Owner's guard run 100 for D0, the executor's check, and node run 200 dispatched on it."""
    pre = world.owner_guard(100, minutes=minutes)
    chk = world.check(100)
    digest = (chk["dispatch_inputs"] or {}).get("evidence_digest", "sha256:" + "0" * 64)
    return pre, chk, world.dispatch(200, guard_run=100, digest=digest)


def test_a_fully_valid_owner_evidence_state_dispatches_at_every_gate(world):
    pre, chk, job = d0_flow(world)
    assert (pre["decision"], chk["decision"], job["decision"]) == (DG.DISPATCH,) * 3, \
        (pre["reasons"], chk["reasons"], job["reasons"])
    ev = pre["billing"]["owner_evidence"]
    assert ev == {"schema": "AUTH2_OWNER_BILLING_EVIDENCE_1", "repository": SLUG, "guard_run_id": 100,
                  "guard_run_attempt": 1, "main_sha": MAIN, "node": "D0", "part": 1, "actor": OWNER,
                  "actor_id": 325778659, "triggering_actor": OWNER, "triggering_actor_id": 325778659,
                  "billing_month": "2026-11", "remaining_included_linux_minutes": 2400,
                  "budget_usd_zero_confirmed": True, "stop_usage_confirmed": True,
                  "attested_utc": "2026-11-03T09:55:00Z", "usage_api_verified": True, "usage_endpoint": USAGE_PATH,
                  "usage_period": "2026-11", "evidence_digest": OP.evidence_digest(ev)}
    assert (pre["billing"]["readable"], pre["billing"]["remaining_included_minutes"],
            pre["billing"]["budget_usd_zero"], pre["billing"]["owner_evidence_problems"]) == (True, 2400, True, [])
    assert chk["dispatch_inputs"] == {"node": "D0", "part": "1", "guard_run": "100",
                                      "evidence_digest": ev["evidence_digest"]}
    assert job["billing"]["owner_evidence"] == ev  # the node consumes the guard's evidence
    assert job["binding"] == {"guard_run": 100, "evidence_digest": ev["evidence_digest"]}
    assert (job["mode"], job["run_id"], job["sha"], job["run_attempt"]) == ("in-job", 200, MAIN, 1)
    # the guard and the job each verify the usage report themselves, with the billing token only
    assert world.billing_calls == [(f"{USAGE_PATH}?year=2026&month=11", TOKEN)] * 2


def test_the_node_workflows_own_inputs_never_become_billing_evidence(world):
    world.owner_guard(100)
    digest = world.check(100)["dispatch_inputs"]["evidence_digest"]
    job = world.dispatch(200, guard_run=100, digest=digest,
                         inputs={"remaining_included_linux_minutes": "999999", "actions_budget_usd_zero": "CONFIRMED",
                                 "stop_usage_enabled": "CONFIRMED"})
    assert job["decision"] == DG.DISPATCH
    assert job["billing"]["remaining_included_minutes"] == 2400 and job["a_m"] == 2400


def no_jobs(w):
    w.add(52, DG.WORKFLOW_FILE, "AUTH2 CAL-A1 part 1", "2026-10-01T00:00:00Z")
    w.jobs[52] = []


PRE_DISPATCH_BREAKS = [
    # the Owner's attestation
    ("OWNER_EVIDENCE_MISSING", dict(inputs={"remaining_included_linux_minutes": None})),
    ("OWNER_EVIDENCE_MISSING", dict(minutes="")),
    ("OWNER_EVIDENCE_REMAINING_INVALID", dict(minutes="-5")),
    ("OWNER_EVIDENCE_REMAINING_INVALID", dict(minutes="2400.0")),
    ("OWNER_EVIDENCE_REMAINING_INVALID", dict(minutes="2,400")),
    ("OWNER_EVIDENCE_REMAINING_INVALID", dict(minutes="٢٤٠٠")),
    ("OWNER_EVIDENCE_BUDGET_NOT_CONFIRMED", dict(budget="NOT_CONFIRMED")),
    ("OWNER_EVIDENCE_MALFORMED", dict(budget="yes")),
    ("OWNER_EVIDENCE_MISSING", dict(inputs={"actions_budget_usd_zero": None})),
    ("OWNER_EVIDENCE_STOP_USAGE_NOT_CONFIRMED", dict(stop="NOT_CONFIRMED")),
    ("OWNER_EVIDENCE_MALFORMED", dict(stop="true")),
    ("OWNER_EVIDENCE_MISSING", dict(inputs={"stop_usage_enabled": None})),
    ("OWNER_EVIDENCE_MISSING", dict(event={"inputs": None})),
    ("OWNER_EVIDENCE_WRONG_NODE", dict(inputs={"node": "CAL-A1"})),
    # who attests: the run's actor and triggering actor as the Actions API reports them, never the environment
    ("OWNER_EVIDENCE_ACTOR_MISMATCH", dict(run={"actor": OTHER_USER, "triggering_actor": OTHER_USER})),
    ("OWNER_EVIDENCE_ACTOR_MISMATCH", dict(run={"triggering_actor": OTHER_USER})),
    ("OWNER_EVIDENCE_ACTOR_MISMATCH", dict(run={"actor": OTHER_USER})),
    ("OWNER_EVIDENCE_ACTOR_MISMATCH", dict(run={"actor": {"login": OWNER, "id": 1},
                                                "triggering_actor": {"login": OWNER, "id": 1}})),
    ("OWNER_EVIDENCE_ACTOR_MISMATCH", dict(sender=OTHER_USER)),
    ("OWNER_EVIDENCE_ACTOR_MISMATCH", dict(run={"actor": OTHER_USER, "triggering_actor": OTHER_USER},
                                           env={"GITHUB_ACTOR": OWNER, "GITHUB_TRIGGERING_ACTOR": OWNER})),
    # where and when
    ("OWNER_EVIDENCE_REPLAYED", dict(attempt=2)),
    ("OWNER_EVIDENCE_PROVENANCE", dict(run={"head_branch": "owner-branch"})),
    ("OWNER_EVIDENCE_PROVENANCE", dict(run={"event": "push"})),
    ("OWNER_EVIDENCE_WRONG_REPOSITORY", dict(run={"repository": {"full_name": "someone-else/fork"}})),
    ("OWNER_EVIDENCE_WRONG_SHA", dict(env={"GITHUB_SHA": "b" * 40})),
    ("OWNER_EVIDENCE_MISSING", dict(env={"GITHUB_EVENT_PATH": None})),
    ("OWNER_EVIDENCE_WRONG_MONTH", dict(created="2026-10-31T23:59:50Z")),
    # the independent usage report: a valid attestation alone is not enough
    ("TOKEN_MISSING", dict(env={"AUTH2_BILLING_TOKEN": None})),
    ("TOKEN_INVALID", dict(usage=(401, "gh: Bad credentials (HTTP 401)"))),
    ("PERMISSION_DENIED", dict(usage=(403, "gh: Resource not accessible by personal access token (HTTP 403)"))),
    ("ENDPOINT_RETIRED", dict(usage=(410, "gh: This endpoint has been moved. (HTTP 410)"))),
    ("MALFORMED", dict(usage=(200, {"items": []}))),
    ("MISSING_FIELDS", dict(usage=(200, {"usageItems": [usage_item(date="2026-11-01", quantity="12")]}))),
    ("WRONG_ACCOUNT", dict(usage=(200, {"usageItems": [usage_item(date="2026-11-01",
                                                                  repositoryName="someone-else/repo")]}))),
    ("WRONG_PERIOD", dict(usage=(200, {"usageItems": [usage_item(date="2026-10-31")]}))),
    # nor beside a ledger that refuses
    ("CAP: minutes", dict(setup=lambda w: w.add(50, OP.GUARD_WORKFLOW, "AUTH2-GUARD D0 part 1",
                                                "2026-11-01T00:00:00Z", minutes=3800))),
    ("SERIAL", dict(setup=lambda w: w.add(51, OP.CLOSURE_WORKFLOW, OP.CLOSURE_TITLE, "2026-11-03T09:50:00Z",
                                          status="in_progress", conclusion=None))),
    ("cannot be reconciled", dict(setup=no_jobs)),
    ("run history not readable", dict(setup=lambda w: w.add(53, DG.WORKFLOW_FILE, "AUTH2 something",
                                                            "2026-11-01T00:00:00Z"))),
    # nor while the program charter is not ACTIVE in the guard's checkout (OD-C4)
    ("CHARTER_NOT_ACTIVE", dict(setup=lambda w: w.charter.update({None: CHARTER_CLOSED}))),
    ("CHARTER_NOT_ACTIVE", dict(setup=lambda w: w.charter.update({None: FileNotFoundError(2, "No such file")}))),
    ("CHARTER_NOT_ACTIVE", dict(setup=lambda w: w.charter.update({None: b"{"}))),
]


@pytest.mark.parametrize("why,kw", PRE_DISPATCH_BREAKS)
def test_removing_any_pre_dispatch_evidence_bit_never_dispatches(world, why, kw):
    kw = dict(kw)
    world.usage = kw.pop("usage", None)
    kw.pop("setup", lambda w: None)(world)
    pre = world.owner_guard(100, **kw)
    assert pre["decision"] == DG.NO_DISPATCH
    assert any(why in r for r in pre["reasons"]), pre["reasons"]
    if why.startswith("OWNER_EVIDENCE"):
        assert pre["billing"]["readable"] is False and pre["billing"]["budget_usd_zero"] is False
    assert world.check(100)["decision"] == DG.NO_DISPATCH


def test_without_the_billing_token_nothing_is_requested_and_nothing_dispatches(world):
    pre = world.owner_guard(100, env={"AUTH2_BILLING_TOKEN": None})
    assert world.billing_calls == [] and pre["decision"] == DG.NO_DISPATCH
    assert pre["billing"]["owner_evidence_problems"][0].startswith("OWNER_EVIDENCE_USAGE_NOT_VERIFIED")


def republish(world, rid, change):
    """Rewrite guard run ``rid``'s published record, annotation and artifact alike (a consistent forgery)."""
    art = world.artifacts[rid][0]
    with zipfile.ZipFile(io.BytesIO(art["zip"])) as z:
        rec = json.loads(z.read("guard.json"))
    change(rec)
    data = (json.dumps(rec, indent=1, sort_keys=True) + "\n").encode()
    art["zip"] = zipped({"guard.json": data})
    world.notes[world.jobs[rid][-1]["id"]] = notes_from(OP.annotation_lines(OP.RECORD, data))


CHECK_BREAKS = [
    ("not fresh", dict(when="2026-11-03T10:10:41Z")),  # 15 min 1 s after the guard's check at 09:55:40
    ("titled", dict(node="CAL-A1")),
    ("not main", dict(main="b" * 40)),
    ("created after the guard run", dict(setup=lambda w: w.add(150, OP.GUARD_WORKFLOW, "AUTH2-GUARD CAL-A1 part 1",
                                                               "2026-11-03T09:56:30Z"))),
    ("SERIAL", dict(setup=lambda w: w.add(151, DG.WORKFLOW_FILE, "AUTH2 CAL-A1 part 1", "2026-11-03T09:56:30Z",
                                          status="queued", conclusion=None))),
    ("OWNER_EVIDENCE_REPLAYED", dict(setup=lambda w: w.runs[100].update(run_attempt=2))),
    ("OWNER_EVIDENCE_ACTOR_MISMATCH", dict(setup=lambda w: w.runs[100].update(triggering_actor=OTHER_USER))),
    ("did not succeed", dict(setup=lambda w: w.runs[100].update(conclusion="cancelled"))),
    ("guard record unreadable", dict(setup=lambda w: w.notes.clear())),
    ("OWNER_EVIDENCE_DIGEST_MISMATCH", dict(setup=lambda w: republish(
        w, 100, lambda r: r["billing"]["owner_evidence"].update(remaining_included_linux_minutes=99999)))),
    ("does not rest on its Owner evidence", dict(setup=lambda w: republish(
        w, 100, lambda r: r["billing"].update(remaining_included_minutes=99999)))),
    ("usage report is not verified", dict(setup=lambda w: republish(
        w, 100, lambda r: r["billing"]["usage_evidence"].update(verified=False)))),
    ("guard decided PARK", dict(setup=lambda w: republish(w, 100, lambda r: r.update(decision=DG.PARK)))),
    # the charter at the main checked, and in the record (OD-C4)
    ("CHARTER_NOT_ACTIVE", dict(setup=lambda w: w.charter.update({MAIN: CHARTER_CLOSED}))),
    ("CHARTER_NOT_ACTIVE", dict(setup=lambda w: w.charter.update({MAIN: OSError("git cat-file: fatal: bad object")}))),
    ("CHARTER_NOT_ACTIVE", dict(setup=lambda w: republish(w, 100, lambda r: r.pop("charter")))),
    ("CHARTER_NOT_ACTIVE", dict(setup=lambda w: republish(w, 100, lambda r: r["charter"].update(status="CLOSED")))),
]


@pytest.mark.parametrize("why,kw", CHECK_BREAKS)
def test_the_executor_check_refuses_anything_short_of_the_owners_bound_record(world, why, kw):
    kw = dict(kw)
    assert world.owner_guard(100)["decision"] == DG.DISPATCH
    kw.pop("setup", lambda w: None)(world)
    chk = world.check(100, **kw)
    assert chk["decision"] == DG.NO_DISPATCH and chk["dispatch_inputs"] is None
    assert any(why in r for r in chk["reasons"]), chk["reasons"]


IN_JOB_BREAKS = [
    ("OWNER_EVIDENCE_BINDING_MISSING", dict(guard_run=None)),
    ("OWNER_EVIDENCE_BINDING_MISSING", dict(digest=None)),
    ("OWNER_EVIDENCE_BINDING_MISSING", dict(digest="sha256:" + "A" * 64)),
    ("OWNER_EVIDENCE_BINDING_MISSING", dict(guard_run="100 101")),
    ("OWNER_EVIDENCE_BINDING_MISSING", dict(guard_run="0100")),
    ("OWNER_EVIDENCE_DIGEST_MISMATCH", dict(digest="sha256:" + "0" * 64)),
    ("OWNER_EVIDENCE_BINDING_UNREADABLE", dict(guard_run="777")),
    ("not fresh", dict(created="2026-11-03T10:10:41Z")),  # dispatched 15 min 1 s after the guard's check
    ("titled", dict(node="CAL-A1")),  # a CAL-A1 run naming D0's guard run
    ("not main", dict(sha="b" * 40)),  # main moved between the guard run and the dispatch
    ("created after the guard run", dict(setup=lambda w: w.add(150, OP.GUARD_WORKFLOW, "AUTH2-GUARD CAL-A1 part 1",
                                                               "2026-11-03T09:57:30Z"))),
    ("OWNER_EVIDENCE_REPLAYED", dict(setup=lambda w: w.runs[100].update(run_attempt=2))),
    ("guard record unreadable", dict(setup=lambda w: w.artifacts.update({100: []}))),
    ("guard record unreadable", dict(setup=lambda w: w.artifacts[100].append({**w.artifacts[100][0], "id": 9999}))),
    ("OWNER_EVIDENCE_BINDING", dict(run={"head_branch": "owner-branch"})),
    ("TOKEN_MISSING", dict(env={"AUTH2_BILLING_TOKEN": None})),
    ("ENDPOINT_RETIRED", dict(setup=lambda w: setattr(w, "usage", (410, "gh: moved (HTTP 410)")))),
    ("RE_RUN", dict(attempt=2)),
]


@pytest.mark.parametrize("why,kw", IN_JOB_BREAKS)
def test_the_in_job_guard_refuses_anything_short_of_the_bound_owner_record(world, why, kw):
    kw = dict(kw)
    world.owner_guard(100)
    digest = world.check(100)["dispatch_inputs"]["evidence_digest"]
    kw.pop("setup", lambda w: None)(world)
    kw.setdefault("guard_run", 100)
    kw.setdefault("digest", digest)
    job = world.dispatch(200, kw.pop("node", "D0"), **kw)
    assert job["decision"] == DG.NO_DISPATCH
    assert any(why in r for r in job["reasons"]), job["reasons"]
    # the billing state is readable only through a verified binding and the job's own verified usage report
    assert job["billing"]["readable"] is (why == "RE_RUN")


def test_the_closure_dispatch_is_bound_the_same_way(world):
    pre = world.owner_guard(100, OP.CLOSURE)
    chk = world.check(100, OP.CLOSURE)
    assert pre["decision"] == chk["decision"] == DG.DISPATCH, (pre["reasons"], chk["reasons"])
    bad = world.dispatch(200, OP.CLOSURE, guard_run=100, digest="sha256:" + "0" * 64)
    assert bad["decision"] == DG.NO_DISPATCH and bad["billing"]["owner_evidence"] is None
    assert any("OWNER_EVIDENCE_DIGEST_MISMATCH" in r for r in bad["reasons"])
    world.owner_guard(101, OP.CLOSURE, created="2026-11-03T10:30:00Z")
    digest = world.check(101, OP.CLOSURE, when="2026-11-03T10:32:00Z")["dispatch_inputs"]["evidence_digest"]
    job = world.dispatch(201, OP.CLOSURE, guard_run=101, digest=digest, created="2026-11-03T10:33:00Z")
    assert job["decision"] == DG.DISPATCH, job["reasons"]
    assert job["node"] == OP.CLOSURE and job["binding"] == {"guard_run": 101, "evidence_digest": digest}


# -- A_m: fixed by the month's first node run, from the Owner's attestation at that dispatch ---------------

def test_the_first_node_run_of_a_month_fixes_a_m_and_later_attestations_never_change_it(world):
    pre, _chk, job = d0_flow(world, minutes="3001")
    assert (pre["month"], pre["a_m"], pre["r_m"]) == ("2026-11", 3001, 601)  # a candidate: a guard run fixes nothing
    assert job["decision"] == DG.DISPATCH
    assert (job["month"], job["a_m"], job["r_m"], job["remaining_included_minutes"]) == ("2026-11", 3001, 601, 3001)
    assert job["r_m"] == max(500, math.ceil(0.20 * 3001)) == DG.reserve(3001)
    for rid, created, minutes, decision in ((300, "2026-11-03T11:00:00Z", "9000", DG.DISPATCH),
                                            (301, "2026-11-03T12:00:00Z", "721", DG.DISPATCH),  # 721 - 120 = R_m
                                            (302, "2026-11-03T13:00:00Z", "720", DG.PARK)):  # 600 < 601
        later = world.owner_guard(rid, "CAL-A1", created=created, minutes=minutes)
        assert (later["a_m"], later["r_m"], later["remaining_included_minutes"]) == (3001, 601, int(minutes))
        assert later["decision"] == decision, later["reasons"]
    assert DG.reserve(2500) == 500 and DG.reserve(2501) == 501 and DG.reserve(0) == 500


def test_a_new_month_takes_a_new_a_m_at_its_own_first_node_run(world):
    d0_flow(world, minutes="3001")
    dec = world.owner_guard(400, "CAL-A1", created="2026-12-01T09:00:00Z", minutes="1500")
    assert (dec["decision"], dec["month"], dec["a_m"], dec["r_m"]) == (DG.DISPATCH, "2026-12", 1500, 500)
    digest = world.check(400, "CAL-A1", when="2026-12-01T09:02:00Z")["dispatch_inputs"]["evidence_digest"]
    job = world.dispatch(500, "CAL-A1", guard_run=400, digest=digest, created="2026-12-01T09:03:00Z")
    assert (job["decision"], job["month"], job["a_m"], job["r_m"]) == (DG.DISPATCH, "2026-12", 1500, 500)
    after = world.owner_guard(401, "CAL-A2", created="2026-12-02T09:00:00Z", minutes="900")
    assert (after["month"], after["a_m"], after["r_m"], after["remaining_included_minutes"]) == \
        ("2026-12", 1500, 500, 900)


def rewrite_first(world, rid, change):
    art = world.artifacts[rid][0]
    with zipfile.ZipFile(io.BytesIO(art["zip"])) as z:
        files = {n: z.read(n) for n in z.namelist()}
    rec = json.loads(files["guard.json"])
    change(rec)
    files["guard.json"] = (json.dumps(rec, indent=1, sort_keys=True) + "\n").encode()
    art["zip"] = zipped(files)


def second_record(world):
    """A second artifact of the first node run that states another A_m."""
    with zipfile.ZipFile(io.BytesIO(world.artifacts[200][0]["zip"])) as z:
        rec = json.loads(z.read("guard.json"))
    rec.update(a_m=5000, r_m=1000)
    world.publish(200, "auth2-D0-p1", {"guard.json": json.dumps(rec).encode()})


FIRST_RECORD_BREAKS = [
    ("has no in-job guard record stating A_m", lambda w: w.artifacts.update({200: []})),
    ("has no in-job guard record stating A_m", lambda w: w.artifacts[200][0].update(expired=True)),
    ("has no in-job guard record stating A_m", lambda w: rewrite_first(w, 200, lambda r: r.pop("a_m"))),
    ("has no in-job guard record stating A_m", lambda w: rewrite_first(w, 200, lambda r: r.update(run_id=201))),
    ("has no in-job guard record stating A_m",
     lambda w: rewrite_first(w, 200, lambda r: r.update(mode="pre-dispatch"))),
    ("is unreadable", lambda w: w.artifacts[200][0].update(zip=b"PK-not-a-zip")),
    ("conflicting A_m records", second_record),
    ("invalid A_m record", lambda w: rewrite_first(w, 200, lambda r: r.update(r_m=501))),
    ("invalid A_m record", lambda w: rewrite_first(w, 200, lambda r: r.update(month="2026-10"))),
    ("invalid A_m record", lambda w: rewrite_first(w, 200, lambda r: r.update(a_m=-1))),
    ("invalid A_m record", lambda w: rewrite_first(w, 200, lambda r: r.update(a_m="2400"))),
    ("does not rest on the Owner evidence", lambda w: rewrite_first(
        w, 200, lambda r: r.update(a_m=5000, r_m=1000, remaining_included_minutes=5000))),
    ("does not rest on the Owner evidence", lambda w: rewrite_first(
        w, 200, lambda r: r["billing"].update(owner_evidence=None))),
    ("does not rest on the Owner evidence", lambda w: rewrite_first(
        w, 200, lambda r: r["binding"].update(evidence_digest="sha256:" + "0" * 64))),
    ("does not rest on the Owner evidence", lambda w: rewrite_first(
        w, 200, lambda r: r["billing"]["owner_evidence"].update(remaining_included_linux_minutes=5000))),
]


@pytest.mark.parametrize("why,breaker", FIRST_RECORD_BREAKS)
def test_a_missing_unreadable_conflicting_or_unbound_first_node_record_never_dispatches(world, why, breaker):
    d0_flow(world)
    breaker(world)
    later = world.owner_guard(300, "CAL-A1", created="2026-11-03T11:00:00Z", minutes="2000")
    assert later["decision"] == DG.NO_DISPATCH
    assert any(why in r for r in later["reasons"]), later["reasons"]
    assert "a_m" not in later  # R_m is unknown, so no reserve is computed


def test_the_in_job_guard_reads_the_first_node_record_itself(world):
    d0_flow(world)
    world.owner_guard(300, "CAL-A1", created="2026-11-03T11:00:00Z", minutes="2000")
    digest = world.check(300, "CAL-A1", when="2026-11-03T11:02:00Z")["dispatch_inputs"]["evidence_digest"]
    world.artifacts[200] = []  # the first node run's record is gone by the dispatch
    job = world.dispatch(301, "CAL-A1", guard_run=300, digest=digest, created="2026-11-03T11:03:00Z")
    assert job["decision"] == DG.NO_DISPATCH
    assert any("has no in-job guard record stating A_m" in r for r in job["reasons"])


# -- caps, attempts and replay under valid Owner evidence ----------------------------------------------------

def owner_billing(minutes=100000) -> dict:
    return OP.billing_state(USAGE_OK, {"evidence": evidence(remaining_included_linux_minutes=minutes), "problems": []})


def test_valid_owner_evidence_never_lifts_the_4000_minute_or_240_invocation_cap():
    bill = owner_billing()
    assert (bill["readable"], bill["remaining_included_minutes"], bill["budget_usd_zero"]) == (True, 100000, True)
    assert OP.decide(state(billing=bill), [aux(1, minutes=3700)], "D0", 1)["decision"] == DG.DISPATCH  # 4000
    cap = OP.decide(state(billing=bill), [aux(1, minutes=3701)], "D0", 1)  # 3701 + 2 x 150 > 4000
    assert cap["decision"] == DG.NO_DISPATCH and any(r.startswith("CAP: minutes") for r in cap["reasons"])
    runs = [{"id": i, "node": "PC-A1", "part": 1, "status": "completed", "conclusion": "failure",
             "created_at": f"2026-11-01T{i:02d}:00:00Z",
             "jobs": [{"status": "completed", "started_at": "2026-11-01T00:00:00Z",
                       "completed_at": "2026-11-01T00:01:00Z"}],
             "guard": {"month": "2026-11", "a_m": 100000}} for i in range(17)]
    assert OP.decide(state(billing=bill, runs=runs), [], "SC-A1", 1)["decision"] == DG.DISPATCH  # 221 + 2 x 1
    inv = OP.decide(state(billing=bill, runs=runs), [], "PC-A3", 1)  # 17 x 13 + 2 x 11 = 243 > 240
    assert inv["decision"] == DG.NO_DISPATCH and any(r.startswith("CAP: invocation") for r in inv["reasons"])


def test_evidence_with_any_problem_leaves_billing_unreadable():
    ev = evidence()
    assert OP.billing_state(USAGE_OK, {"evidence": ev, "problems": []})["readable"] is True
    for usage, owner in ((USAGE_OK, {"evidence": ev, "problems": ["OWNER_EVIDENCE_X"]}),
                         (USAGE_OK, {"evidence": None, "problems": []}), (USAGE_OK, None),
                         ({**USAGE_OK, "verified": False, "class": "ENDPOINT_RETIRED"},
                          {"evidence": ev, "problems": []})):
        bill = OP.billing_state(usage, owner)
        assert (bill["readable"], bill["remaining_included_minutes"], bill["budget_usd_zero"]) == (False, None, False)
        assert OP.decide(state(billing=bill), [], "D0", 1)["decision"] == DG.NO_DISPATCH


def test_every_attempt_of_a_re_run_guard_counts_and_the_re_run_never_attests(world):
    replay = world.owner_guard(90, created="2026-11-03T09:00:00Z", attempt=2)
    assert replay["decision"] == DG.NO_DISPATCH
    assert any("OWNER_EVIDENCE_REPLAYED" in r for r in replay["reasons"])
    pre, chk, job = d0_flow(world)
    assert (pre["decision"], chk["decision"], job["decision"]) == (DG.DISPATCH,) * 3
    assert pre["aux_minutes_ledger"] == 2 and job["aux_minutes_ledger"] == 3  # run 90's two attempts, then run 100


def test_no_token_reaches_any_record_annotation_artifact_or_log(world):
    world.usage = (403, f"gh: token {TOKEN} lacks the Plan permission (HTTP 403)")
    pre = world.owner_guard(100)
    assert pre["decision"] == DG.NO_DISPATCH and "***" in pre["billing"]["usage_evidence"]["detail"]
    world.usage = None
    world.owner_guard(101, created="2026-11-03T09:56:00Z")
    digest = world.check(101, when="2026-11-03T09:58:00Z")["dispatch_inputs"]["evidence_digest"]
    world.usage = (401, f"gh: Bad credentials for {TOKEN} (HTTP 401)")
    job = world.dispatch(200, guard_run=101, digest=digest, created="2026-11-03T09:59:00Z")
    assert job["decision"] == DG.NO_DISPATCH and "***" in job["billing"]["usage_evidence"]["detail"]
    stored = [a["zip"] for arts in world.artifacts.values() for a in arts]
    stored += [json.dumps(n).encode() for n in world.notes.values()] + [p.encode() for p in world.printed]
    assert stored and not any(TOKEN.encode() in blob for blob in stored)


# -- the workflows ---------------------------------------------------------------------------------

def load(name: str) -> dict:
    return yaml.safe_load((WF / name).read_text())


def inputs_of(name: str) -> dict:
    wf = load(name)
    return wf.get("on", wf.get(True))["workflow_dispatch"]["inputs"]


@pytest.mark.parametrize("name,run_name", [
    ("auth2-guard.yml", "AUTH2-GUARD ${{ inputs.node }} part ${{ inputs.part }}"),
    ("auth2-closure.yml", "AUTH2-CLOSURE"),
])
def test_the_operator_workflows_are_manual_serial_read_only(name, run_name):
    wf = load(name)
    text = (WF / name).read_text()
    on = wf.get("on", wf.get(True))
    assert list(on) == ["workflow_dispatch"]
    assert wf["permissions"] == {"contents": "read", "actions": "read"}
    assert wf["concurrency"] == {"group": "auth2-program", "cancel-in-progress": False}
    assert wf["run-name"] == run_name
    [job] = wf["jobs"].values()
    assert job["timeout-minutes"] == (OP.GUARD_TIMEOUT if name == "auth2-guard.yml" else OP.CLOSURE_TIMEOUT)
    assert set(re.findall(r"secrets\.([A-Z0-9_]+)", text)) == {"AUTH2_BILLING_TOKEN"}
    for forbidden in ("git push", "git commit", "contents: write", "dry_run\": false", "docker",
                      "--append-ledger", "run_node"):
        assert forbidden not in text
    names = [s.get("name", s.get("uses", "")) for s in job["steps"]]
    guard = next(i for i, n in enumerate(names) if "dispatch guard" in n)
    assert all("uses" in s or "Install" in s.get("name", "") for s in job["steps"][:guard])


def test_the_guard_workflow_offers_every_node_and_closure():
    on = load("auth2-guard.yml").get("on")
    on = on if on is not None else load("auth2-guard.yml")[True]
    assert sorted(on["workflow_dispatch"]["inputs"]["node"]["options"]) == sorted([*RN.NODES, OP.CLOSURE])
    assert OP.GUARD_TITLE.match("AUTH2-GUARD PC-A2 part 2")


def test_the_owner_states_both_controls_only_in_typed_guard_inputs():
    inputs = inputs_of("auth2-guard.yml")
    assert set(inputs) == {"node", "part", OP.MINUTES_INPUT, *OP.CONFIRMATIONS}
    minutes = inputs[OP.MINUTES_INPUT]
    assert minutes["type"] == "string" and minutes["required"] is True and "default" not in minutes
    for key in OP.CONFIRMATIONS:
        assert inputs[key]["type"] == "choice" and inputs[key]["required"] is True
        assert inputs[key]["options"] == [OP.NOT_CONFIRMED, OP.CONFIRMED] and inputs[key]["default"] == OP.NOT_CONFIRMED
    # read from the event GitHub delivered: no step, environment value or expression carries them
    jobs = json.dumps(load("auth2-guard.yml")["jobs"])
    for key in (OP.MINUTES_INPUT, *OP.CONFIRMATIONS):
        assert key not in jobs
    assert "github.actor" not in jobs and "github.triggering_actor" not in jobs
    for name in ("auth2-guard.yml", "auth2.yml", "auth2-closure.yml"):
        assert "vars." not in (WF / name).read_text()


@pytest.mark.parametrize("name,job", [("auth2.yml", "node"), ("auth2-closure.yml", "closure")])
def test_node_and_closure_dispatches_name_the_guard_run_and_digest_only(name, job):
    inputs = inputs_of(name)
    for key in ("guard_run", "evidence_digest"):
        assert inputs[key]["type"] == "string" and inputs[key]["required"] is True
    assert not set(inputs) & {OP.MINUTES_INPUT, *OP.CONFIRMATIONS}  # billing figures are never a dispatch input
    guard = next(s for s in load(name)["jobs"][job]["steps"] if "dispatch guard" in s.get("name", ""))
    assert guard["env"]["GUARD_RUN"] == "${{ inputs.guard_run }}"
    assert guard["env"]["EVIDENCE_DIGEST"] == "${{ inputs.evidence_digest }}"
    assert '--guard-run "$GUARD_RUN" --evidence-digest "$EVIDENCE_DIGEST"' in guard["run"]
    assert "--in-job" in guard["run"] and "${{" not in guard["run"]  # inputs reach the shell as values only


def test_node_jobs_guard_through_the_operator_and_publish_their_results():
    steps = load("auth2.yml")["jobs"]["node"]["steps"]
    guard = next(s for s in steps if "dispatch guard" in s.get("name", ""))
    assert "auth2_operator.py guard" in guard["run"] and "--in-job" in guard["run"]
    pub = next(s for s in steps if s.get("name", "").startswith("Publish the result summary"))
    assert pub["if"] == "always()" and "annotate-results" in pub["run"]
    names = [s.get("name", s.get("uses", "")) for s in steps]
    assert names.index(pub["name"]) < names.index("actions/upload-artifact@v4")


def test_the_node_job_checks_out_the_history_its_program_check_reads():
    checkout = next(s for s in load("auth2.yml")["jobs"]["node"]["steps"]
                    if s.get("uses", "").startswith("actions/checkout"))
    assert checkout["with"]["fetch-depth"] == 0


def test_a_depth_one_checkout_refuses_every_node_and_full_history_passes(tmp_path):
    """D0 run 38273417548 (main 410418e): a depth-1 checkout holds only the dispatched commit, so the program
    check takes it for the commit that added the program and finds every node's PREREGISTERED record older than
    the program. A full clone of the same commit passes."""
    import check_research_program as crp

    def git(*args, cwd=REPO) -> str:
        return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True,
                              timeout=300).stdout.strip()

    if git("rev-parse", "--is-shallow-repository") != "false":
        pytest.skip("this checkout is shallow itself, so there is no full history to compare with")
    head = git("rev-parse", "HEAD")
    program = json.loads((REPO / "charters/programs/AUTH-2-DISCOVERY-QUALIFICATION-1.json").read_text())
    for depth, refused in ((["--depth", "1"], len(program["dag"]["nodes"])), ([], 0)):
        clone = tmp_path / ("shallow" if depth else "full")
        git("clone", "--quiet", "--no-checkout", *depth, f"file://{REPO}", str(clone), cwd=tmp_path)
        git("checkout", "--quiet", "--detach", head, cwd=clone)
        problems = crp.check(clone)
        assert len(problems) == refused, problems
        assert all("ledger record older than the program" in p for p in problems)


def test_guard_and_closure_artifacts_are_never_read_as_node_results():
    for name in ("auth2-guard.yml", "auth2-closure.yml"):
        upload = next(s for s in load(name)["jobs"][next(iter(load(name)["jobs"]))]["steps"]
                      if s.get("uses", "").startswith("actions/upload-artifact"))
        assert not upload["with"]["name"].startswith("auth2-")


def test_the_guard_artifact_is_the_one_the_in_job_binding_reads():
    steps = load("auth2-guard.yml")["jobs"]["guard"]["steps"]
    upload = next(s for s in steps if s.get("uses", "").startswith("actions/upload-artifact"))
    assert upload["with"]["name"] == "auth2guard-${{ inputs.node }}-p${{ inputs.part }}"
    assert upload["with"]["path"] == "out/guard.json" and upload["if"] == "always()"
    assert "--out out/guard.json" in next(s for s in steps if "dispatch guard" in s.get("name", ""))["run"]


def test_research_auth2_code_is_untouched_by_the_operator():
    """The gate lives outside research/auth2/, whose *.py files are pinned in every preregistration."""
    pins = json.loads((REPO / "research/auth2/prereg/D0.json").read_text())["code_sha256"]
    assert pins == RN.code_sha256()
    assert not any("operator" in k for k in pins)


# -- billing evidence: the endpoint dispatch_guard reads is closed; nothing unproven dispatches ----------------

def read_with(monkeypatch, response, token=TOKEN):
    calls = []
    if token is None:
        monkeypatch.delenv("AUTH2_BILLING_TOKEN", raising=False)
    else:
        monkeypatch.setenv("AUTH2_BILLING_TOKEN", token)

    def get(path, tok):
        calls.append((path, tok))
        return response

    return OP.read_billing(OWNER, "AUTH2_BILLING_TOKEN", OCT, get=get), calls


def decided(bill: dict, **kw) -> dict:
    return OP.decide(state(billing=bill), [], "D0", 1, **kw)


def test_a_410_from_the_closed_endpoint_never_dispatches(monkeypatch):
    bill, calls = read_with(monkeypatch, (410, "gh: This endpoint has been moved. (HTTP 410)"))
    assert calls == [(f"/users/{OWNER}/settings/billing/usage?year=2026&month=10", TOKEN)]
    assert bill["usage_evidence"]["class"] == "ENDPOINT_RETIRED"
    d = decided(bill)
    assert d["decision"] == DG.NO_DISPATCH and any("ENDPOINT_RETIRED" in r for r in d["reasons"])


def test_the_closed_endpoint_is_no_longer_called(monkeypatch):
    def closed(*_a, **_k):
        raise AssertionError("dispatch_guard.read_billing calls /settings/billing/actions, closed by GitHub (410)")

    monkeypatch.setattr(DG, "read_billing", closed)
    monkeypatch.setattr(DG, "_api", lambda path, token_env=None: {"workflow_runs": []})
    monkeypatch.setattr(OP, "billing_get", lambda path, tok: (410, "gh: This endpoint has been moved. (HTTP 410)"))
    monkeypatch.setenv("AUTH2_BILLING_TOKEN", TOKEN)
    st = OP.collect("o/r", OWNER, "AUTH2_BILLING_TOKEN", None)
    assert st["runs"] == [] and "runs_error" not in st and st["billing"]["readable"] is False
    assert st["billing"]["usage_evidence"]["class"] == "ENDPOINT_RETIRED"  # the patched reader answered, offline


def test_a_403_is_a_permission_failure_not_an_api_migration(monkeypatch):
    bill, _ = read_with(monkeypatch, (403, "gh: Resource not accessible by personal access token (HTTP 403)"))
    assert bill["usage_evidence"]["class"] == "PERMISSION_DENIED"
    assert decided(bill)["decision"] == DG.NO_DISPATCH


@pytest.mark.parametrize("token", [None, "", "   "])
def test_a_missing_token_never_falls_back_to_the_workflow_token(monkeypatch, token):
    bill, calls = read_with(monkeypatch, (200, {"usageItems": [usage_item()]}), token=token)
    assert calls == []  # no request at all, so the workflow's GITHUB_TOKEN can never answer for billing
    assert bill["usage_evidence"]["class"] == "TOKEN_MISSING"
    d = decided(bill)
    assert d["decision"] == DG.NO_DISPATCH and any("TOKEN_MISSING" in r for r in d["reasons"])


def test_an_invalid_token_is_classified(monkeypatch):
    bill, _ = read_with(monkeypatch, (401, "gh: Bad credentials (HTTP 401)"))
    assert bill["usage_evidence"]["class"] == "TOKEN_INVALID"
    assert decided(bill)["decision"] == DG.NO_DISPATCH


def test_billing_requests_carry_only_the_billing_token(monkeypatch):
    seen = {}

    def run(cmd, capture_output, text, env):
        seen.update(cmd=cmd, env=env)
        return OP.subprocess.CompletedProcess(cmd, 1, "", "gh: This endpoint has been moved. (HTTP 410)")

    monkeypatch.setenv("GITHUB_TOKEN", "workflow-token")
    monkeypatch.setenv("GH_TOKEN", "workflow-token")
    monkeypatch.setattr(OP.subprocess, "run", run)
    assert OP.billing_get("/users/x/settings/billing/usage", TOKEN) == \
        (410, "gh: This endpoint has been moved. (HTTP 410)")
    assert seen["env"]["GH_TOKEN"] == TOKEN and "GITHUB_TOKEN" not in seen["env"]
    assert TOKEN not in " ".join(seen["cmd"])


@pytest.mark.parametrize("item", [
    {k: v for k, v in usage_item().items() if k != "quantity"},
    usage_item(quantity="12"),
    usage_item(netAmount=True),
    usage_item(date=None),
    "not an object",
])
def test_missing_or_mistyped_billing_fields_never_dispatch(monkeypatch, item):
    bill, _ = read_with(monkeypatch, (200, {"usageItems": [usage_item(), item]}))
    assert bill["usage_evidence"]["class"] == "MISSING_FIELDS" and not bill["usage_evidence"]["verified"]
    assert decided(bill)["decision"] == DG.NO_DISPATCH


@pytest.mark.parametrize("body", [None, [], {"items": []}, {"usageItems": {"0": usage_item()}}, "html"])
def test_a_malformed_response_never_dispatches(monkeypatch, body):
    bill, _ = read_with(monkeypatch, (200, body))
    assert bill["usage_evidence"]["class"] == "MALFORMED"
    assert decided(bill)["decision"] == DG.NO_DISPATCH


@pytest.mark.parametrize("item,why", [
    (usage_item(repositoryName="someone-else/repo"), "WRONG_ACCOUNT"),
    (usage_item(repositoryName=7), "WRONG_ACCOUNT"),
    (usage_item(date="2026-09-30"), "WRONG_PERIOD"),
    (usage_item(date="2025-10-11"), "WRONG_PERIOD"),
])
def test_another_account_or_billing_period_never_dispatches(monkeypatch, item, why):
    bill, _ = read_with(monkeypatch, (200, {"usageItems": [usage_item(), item]}))
    assert bill["usage_evidence"]["class"] == why
    assert decided(bill)["decision"] == DG.NO_DISPATCH


def test_the_live_report_names_the_accounts_repositories_without_an_owner(monkeypatch):
    """Guard run 38220977904 (2026-10-12, main e2cb36e): GitHub's live report named the repository
    "trading-lab-os-sandbox", not the docs example's "user/example" form, and the account check refused it
    (WRONG_ACCOUNT), so no report could ever verify. The report is per user: a bare name is this account's, and a
    name qualified with any other owner is still refused."""
    live = usage_item(repositoryName="trading-lab-os-sandbox")
    for also in ([], [usage_item(repositoryName=f"{OWNER}/trading-lab-os-sandbox")],
                 [usage_item(repositoryName=f"{OWNER.upper()}/Trading-Lab-OS-Sandbox")],
                 [usage_item(repositoryName="")], [usage_item(repositoryName=None)],
                 [usage_item(product="Copilot", sku="Copilot Premium Request", unitType="requests")]):
        bill, _ = read_with(monkeypatch, (200, {"usageItems": [live, *also]}))
        assert bill["usage_evidence"]["class"] == "USAGE_VERIFIED", also
        assert bill["usage_evidence"]["verified"] is True
    for name in ("someone-else/trading-lab-os-sandbox", f"{OWNER}x/trading-lab-os-sandbox", "/trading-lab-os-sandbox",
                 f"someone-else/{OWNER}", 7, ["trading-lab-os-sandbox"]):
        for items in ([live, usage_item(repositoryName=name)], [usage_item(repositoryName=name), live]):
            bill, _ = read_with(monkeypatch, (200, {"usageItems": items}))
            assert bill["usage_evidence"]["class"] == "WRONG_ACCOUNT", name
            assert decided(bill)["decision"] == DG.NO_DISPATCH


# Guard run 38220977904's Owner evidence object as its record published it (usage_api_verified false).
LIVE_SHA = "e2cb36ed0840cc0f44f2572626db7b795340bfac"
LIVE_EVIDENCE = {"schema": "AUTH2_OWNER_BILLING_EVIDENCE_1", "repository": SLUG, "guard_run_id": 38220977904,
                 "guard_run_attempt": 1, "main_sha": LIVE_SHA, "node": "D0", "part": 1, "actor": OWNER,
                 "actor_id": 325778659, "triggering_actor": OWNER, "triggering_actor_id": 325778659,
                 "billing_month": "2026-10", "remaining_included_linux_minutes": 1495,
                 "budget_usd_zero_confirmed": True, "stop_usage_confirmed": True,
                 "attested_utc": "2026-10-12T08:00:28Z", "usage_api_verified": False, "usage_endpoint": USAGE_PATH,
                 "usage_period": "2026-10",
                 "evidence_digest": "sha256:102a2643892b76a22497802a1305e3efddabb4512bf6acf48606e53c323929c4"}


def replay_38220977904(world, items) -> dict:
    """The Owner's guard run 38220977904 again (main e2cb36e, 1495 minutes, both confirmations) over ``items``."""
    world.usage = (200, {"usageItems": items})
    return world.owner_guard(38220977904, created="2026-10-12T08:00:28Z", minutes="1495", run={"head_sha": LIVE_SHA})


def test_guard_run_38220977904_replayed_over_the_live_report_form_dispatches_at_every_gate(world):
    """Its evidence differs from the published one only in usage_api_verified, and the reserve law, not the
    account check, decides: 1495 - 2 x 150 >= R_m 500."""
    assert OP.evidence_digest(LIVE_EVIDENCE) == LIVE_EVIDENCE["evidence_digest"]  # the copy above is exact
    pre = replay_38220977904(world, [usage_item(date="2026-10-01"), usage_item(date="2026-10-12", quantity=3.0)])
    assert pre["decision"] == DG.DISPATCH, pre["reasons"]
    ev = pre["billing"]["owner_evidence"]
    assert ev == {**LIVE_EVIDENCE, "usage_api_verified": True, "evidence_digest": ev["evidence_digest"]}
    assert ev["evidence_digest"] == OP.evidence_digest(ev) != LIVE_EVIDENCE["evidence_digest"]
    assert (pre["month"], pre["a_m"], pre["r_m"], pre["remaining_included_minutes"], pre["timeout_minutes"]) == \
        ("2026-10", 1495, 500, 1495, 150)
    assert pre["billing"]["usage_evidence"]["class"] == "USAGE_VERIFIED"
    chk = world.check(38220977904, when="2026-10-12T08:05:00Z", main=LIVE_SHA)
    assert chk["decision"] == DG.DISPATCH, chk["reasons"]
    assert chk["dispatch_inputs"] == {"node": "D0", "part": "1", "guard_run": "38220977904",
                                      "evidence_digest": ev["evidence_digest"]}
    job = world.dispatch(38220978000, guard_run=38220977904, digest=ev["evidence_digest"],
                         created="2026-10-12T08:06:00Z", sha=LIVE_SHA)
    assert job["decision"] == DG.DISPATCH, job["reasons"]
    assert job["billing"]["owner_evidence"] == ev


def test_guard_run_38220977904_replayed_with_another_owners_repository_still_refuses(world):
    other = usage_item(date="2026-10-12", repositoryName="someone-else/trading-lab-os-sandbox")
    pre = replay_38220977904(world, [usage_item(date="2026-10-01"), other])
    assert pre["decision"] == DG.NO_DISPATCH and pre["billing"]["usage_evidence"]["class"] == "WRONG_ACCOUNT"
    assert pre["billing"]["owner_evidence"] == LIVE_EVIDENCE  # the published refusal, byte for byte
    assert world.check(38220977904, when="2026-10-12T08:05:00Z", main=LIVE_SHA)["decision"] == DG.NO_DISPATCH


@pytest.mark.parametrize("status", [None, 404, 500, 503])
def test_any_other_api_failure_never_dispatches(monkeypatch, status):
    bill, _ = read_with(monkeypatch, (status, "gh: Internal Error"))
    assert bill["usage_evidence"]["class"] in ("API_ERROR", "NOT_FOUND")
    assert decided(bill)["decision"] == DG.NO_DISPATCH


def test_valid_usage_evidence_is_recorded_but_cannot_prove_remaining_included_minutes(monkeypatch):
    items = [usage_item(), usage_item(date="2026-10-01", quantity=3.0, grossAmount=0.024, discountAmount=0.024),
             usage_item(product="Copilot", sku="Copilot Premium Request", unitType="requests", repositoryName=None)]
    bill, _ = read_with(monkeypatch, (200, {"usageItems": items}))
    ev = bill["usage_evidence"]
    assert ev["verified"] and ev["class"] == "USAGE_VERIFIED" and ev["period"] == "2026-10"
    assert ev["endpoint"] == f"/users/{OWNER}/settings/billing/usage"
    assert ev["actions"] == {"Actions Linux": {"unitType": "Minutes", "quantity": 15.0, "grossAmount": 0.12,
                                               "discountAmount": 0.12, "netAmount": 0.0}}
    assert bill["readable"] is False and bill["remaining_included_minutes"] is None
    d = decided(bill)
    assert d["decision"] == DG.NO_DISPATCH
    assert any(r.startswith("FAIL_CLOSED: remaining included Actions minutes not readable (NOT_EXPOSED")
               for r in d["reasons"])
    assert d["billing"]["usage_evidence"]["verified"] is True


def test_the_usd_0_budget_is_never_assumed(monkeypatch):
    for response in [(200, {"usageItems": [usage_item()]}), (410, "gh: moved (HTTP 410)")]:
        bill, _ = read_with(monkeypatch, response)
        assert bill["budget_usd_zero"] is False
        assert any(r.startswith("FAIL_CLOSED: an Actions budget of USD 0 that stops usage is not verified "
                                "(NOT_EXPOSED: GitHub's budgets API is organization-only")
                   for r in decided(bill)["reasons"])


def test_only_proven_billing_controls_open_the_gate():
    proven = {"readable": True, "remaining_included_minutes": 2000, "budget_usd_zero": True}
    assert decided(proven)["decision"] == DG.DISPATCH
    for missing in ({**proven, "budget_usd_zero": False}, {**proven, "readable": False},
                    {"readable": True, "remaining_included_minutes": 2000}, {}):
        assert decided(missing)["decision"] == DG.NO_DISPATCH


def test_no_token_ever_reaches_the_record(monkeypatch):
    bill, _ = read_with(monkeypatch, (403, f"gh: token {TOKEN} lacks Plan (HTTP 403)"))
    rec = decided(bill)
    assert TOKEN not in json.dumps(rec) and TOKEN not in json.dumps(bill)
    assert "***" in bill["usage_evidence"]["detail"]


# -- caps and replay -------------------------------------------------------------------------------------

PROVEN = {"readable": True, "remaining_included_minutes": 100000, "budget_usd_zero": True}


def test_a_re_run_attempt_of_a_node_or_closure_job_never_runs_again():
    assert decided(PROVEN, attempt=1)["decision"] == DG.DISPATCH
    d = decided(PROVEN, attempt=2)
    assert d["decision"] == DG.NO_DISPATCH and any(r.startswith("RE_RUN") for r in d["reasons"])


def test_earlier_attempts_count_toward_the_4000_minute_cap():
    ok = OP.decide(state(billing=PROVEN), [aux(1, minutes=100)], "PC-A2", 1, earlier_minutes=3000)
    assert ok["decision"] == DG.DISPATCH and ok["total_minutes_ledger"] == 3100  # + 2 x 180 = 3460
    d = OP.decide(state(billing=PROVEN), [aux(1, minutes=100)], "PC-A2", 1, earlier_minutes=3600)
    assert d["decision"] == DG.NO_DISPATCH and any(r.startswith("CAP: minutes") for r in d["reasons"])


def fake_api(runs_by_workflow: dict, jobs_by_run: dict, seen: list):
    def api(path, token_env=None):
        seen.append(path)
        for wf, runs in runs_by_workflow.items():
            if f"/workflows/{wf}/runs" in path:
                return {"workflow_runs": runs}
        rid = int(path.split("/runs/")[1].split("/")[0])
        return {"jobs": jobs_by_run[rid]}
    return api


def job(attempt, start, end):
    return {"status": "completed", "run_attempt": attempt, "started_at": f"2026-10-12T{start}:00Z",
            "completed_at": f"2026-10-12T{end}:00Z"}


def test_guard_and_closure_minutes_count_every_attempt(monkeypatch):
    seen = []
    runs = {OP.GUARD_WORKFLOW: [{"id": 5, "status": "completed", "conclusion": "failure", "run_attempt": 2,
                                 "created_at": "2026-10-11T23:36:08Z"}], OP.CLOSURE_WORKFLOW: []}
    monkeypatch.setattr(DG, "_api", fake_api(runs, {5: [job(1, "00:00", "00:01"), job(2, "00:02", "00:03")]}, seen))
    [r] = OP.read_aux_runs("o/r", None)
    assert r["minutes"] == 2 and any("/runs/5/jobs" in p and "filter=all" in p for p in seen)


def test_earlier_attempts_of_a_re_run_node_run_are_counted(monkeypatch):
    seen = []
    runs = {DG.WORKFLOW_FILE: [{"id": 9, "run_attempt": 2, "display_title": "AUTH2 PC-A1 part 1"},
                               {"id": 8, "run_attempt": 1, "display_title": "AUTH2 D0 part 1"}]}
    jobs = {9: [job(1, "00:00", "01:00"), job(2, "02:00", "02:01")]}
    monkeypatch.setattr(DG, "_api", fake_api(runs, jobs, seen))
    assert OP.earlier_attempt_minutes("o/r") == 60  # the latest attempt is dispatch_guard's; run 8 has none
    assert not any("/runs/8/" in p for p in seen)
    runs[DG.WORKFLOW_FILE][0]["display_title"] = "something else"
    with pytest.raises(RuntimeError):
        OP.earlier_attempt_minutes("o/r")


# -- the program charter: nothing dispatches unless it is ACTIVE (Owner decision OD-C4) ------------------------

AS_RUN_SHA256 = "d6c057789fd8410aba39bebdacd2053c7893e14f4ed97fc38427b7ba65387a40"  # AUTH2-GOVERNANCE-CLOSURE-1
CLOSED_SHA256 = "1472916afc5101ccf5e7c8d161684e4bd5a98e6f18aa275fab5cfc6b70d84ba6"
EVIDENCE_COMMIT = "8013e216075fcdfdf1068ef1b43b52aea5747d78"  # the last main with the charter ACTIVE
OD_C4_BASE = "f5c6bc332288c5968926ce536db0f1d4cb710f64"  # PR #64's merge: the charter CLOSED, no refusal yet
DROP = object()
HOLM_DONE = [{"id": 1, "node": "HOLM", "part": 1, "status": "completed", "conclusion": "success",
              "created_at": "2026-11-01T00:00:00Z",
              "jobs": [{"status": "completed", "started_at": "2026-11-01T00:00:00Z",
                        "completed_at": "2026-11-01T00:02:00Z"}],
              "guard": {"month": "2026-11", "a_m": 2000}}]


def charter_with(**kw) -> bytes:
    """The as-run charter with ``kw`` replacing fields (DROP removes one), written as the repository writes it."""
    c = json.loads(CHARTER_AS_RUN)
    for k, v in kw.items():
        c.pop(k) if v is DROP else c.update({k: v})
    return (json.dumps(c, indent=1, sort_keys=True, ensure_ascii=False) + "\n").encode()


def reads(monkeypatch, raw):
    """``read_charter`` over the file ``raw`` (bytes, or an exception the read raises)."""
    def charter_bytes(rev=None, repo=None):
        if isinstance(raw, Exception):
            raise raw
        return raw
    monkeypatch.setattr(OP, "charter_bytes", charter_bytes)
    return OP.read_charter()


def refusal(status, rev="working tree") -> str:
    return (f"CHARTER_NOT_ACTIVE: {OP.PROGRAM_ID} is {repr(status)[:60]} ({OP.CHARTER_REL} at {rev}), not "
            "'ACTIVE'; no AUTH-2 node or closure may run")


def test_the_charters_here_are_the_one_auth2_ran_under_and_the_closed_one():
    assert hashlib.sha256(CHARTER_AS_RUN).hexdigest() == AS_RUN_SHA256 == ACTIVE["sha256"]
    assert hashlib.sha256(CHARTER_CLOSED).hexdigest() == CLOSED_SHA256
    assert json.loads(CHARTER_CLOSED)["status"] == "CLOSED"


@pytest.mark.parametrize("node,part", [*((n, p) for n, plan in RN.NODES.items() for p in range(1, plan["parts"] + 1)),
                                       (OP.CLOSURE, 1)])
def test_auth2_is_closed_here_so_every_node_part_and_the_closure_are_refused(node, part):
    """This checkout's charter, read as the guard reads its own checkout in Actions, refuses every node part and
    the closure in a state that otherwise decides exactly as before, the refusal added last."""
    charter = OP.read_charter()
    assert charter == {"path": OP.CHARTER_REL, "rev": "working tree", "status": "CLOSED", "sha256": CLOSED_SHA256}
    s = state(runs=HOLM_DONE) if node == OP.CLOSURE else state()
    active = OP.decide(copy.deepcopy(s), [], node, part)
    closed = OP.decide({**copy.deepcopy(s), "charter": charter}, [], node, part)
    assert closed["decision"] == DG.NO_DISPATCH and closed["charter"] == charter
    assert closed["reasons"] == active["reasons"] + [refusal("CLOSED")]


def test_only_the_status_active_dispatches(monkeypatch):
    assert reads(monkeypatch, CHARTER_AS_RUN) == ACTIVE
    assert OP.decide(state(charter=OP.read_charter()), [], "D0", 1)["decision"] == DG.DISPATCH


@pytest.mark.parametrize("status", ["CLOSED", "SUSPENDED", "DRAFT", "REVOKED", "PAUSED", "active", "Active",
                                    " ACTIVE", "ACTIVE ", "ACTIVE\n", "АCTIVE", "", None, 0, 1, True,
                                    ["ACTIVE"], {"status": "ACTIVE"}])
def test_any_status_but_exactly_active_is_refused(monkeypatch, status):
    charter = reads(monkeypatch, charter_with(status=status))
    assert charter["status"] == status
    d = OP.decide(state(charter=charter), [], "D0", 1)
    assert d["decision"] == DG.NO_DISPATCH and d["reasons"] == [refusal(status)]


@pytest.mark.parametrize("raw,why", [
    (FileNotFoundError(2, "No such file or directory"), "FileNotFoundError"),
    (OSError("git cat-file: fatal: invalid object name"), "OSError: git cat-file"),
    (subprocess.TimeoutExpired(["git"], 60), "TimeoutExpired"),
    (b"", "JSONDecodeError"),
    (b'{"program_id": "AUTH-2-DISCOVERY-QUALIFICATION-1", "status": "ACTIVE"', "JSONDecodeError"),
    (b"\xff\xfe\xfd", "Error"),
    (b"[" * 200000 + b"]" * 200000, "RecursionError"),
    (b'["ACTIVE"]', "not the AUTH-2-DISCOVERY-QUALIFICATION-1 charter"),
    (b'"ACTIVE"', "not the AUTH-2-DISCOVERY-QUALIFICATION-1 charter"),
    (charter_with(program_id="AUTH-2-DISCOVERY-QUALIFICATION-2"), "not the AUTH-2-DISCOVERY-QUALIFICATION-1 charter"),
    (charter_with(program_id=DROP), "not the AUTH-2-DISCOVERY-QUALIFICATION-1 charter"),
    (charter_with(status=DROP), "or it has no status"),
    (b'{"program_id": "AUTH-2-DISCOVERY-QUALIFICATION-1", "status": "CLOSED", "status": "ACTIVE"}',
     "duplicate keys ['status']"),
    (b'{"program_id": "x", "program_id": "AUTH-2-DISCOVERY-QUALIFICATION-1", "status": "ACTIVE"}',
     "duplicate keys ['program_id']"),
    (CHARTER_AS_RUN.replace(b'"status": "ACTIVE"', b'"status": "CLOSED", "status": "ACTIVE"'),
     "duplicate keys ['status']"),
], ids=["missing", "git", "timeout", "empty", "truncated", "not-utf8", "deep", "array", "string", "other-program",
        "no-program", "no-status", "status-twice", "program-twice", "status-twice-in-charter"])
def test_a_charter_that_cannot_be_read_as_this_programs_is_refused(monkeypatch, raw, why):
    charter = reads(monkeypatch, raw)
    assert set(charter) == {"path", "rev", "error"} and why in charter["error"], charter
    d = OP.decide(state(charter=charter), [], "D0", 1)
    assert d["decision"] == DG.NO_DISPATCH and len(d["reasons"]) == 1
    assert d["reasons"][0].startswith(f"CHARTER_NOT_ACTIVE: the {OP.PROGRAM_ID} charter is unreadable (")


@pytest.mark.parametrize("charter", [DROP, None, {}, {"path": OP.CHARTER_REL}, "ACTIVE", ["ACTIVE"],
                                     {**ACTIVE, "error": "x"}, {**ACTIVE, "error": ""}, {**ACTIVE, "error": None}])
def test_a_decision_without_a_readable_charter_never_dispatches(charter):
    s = state()
    s.pop("charter") if charter is DROP else s.update(charter=charter)
    d = OP.decide(s, [], "D0", 1)
    assert d["decision"] == DG.NO_DISPATCH and len(d["reasons"]) == 1
    assert d["reasons"][0].startswith(f"CHARTER_NOT_ACTIVE: the {OP.PROGRAM_ID} charter is unreadable (")


@pytest.mark.parametrize("rev", ["8013e216", "--output=/tmp/x", "-p", "", "A" * 40, "a" * 39, "a" * 41, "HEAD",
                                 "main", "origin/main", "a" * 40 + "\n", f"{'a' * 40}:x"])
def test_check_dispatch_reads_the_charter_only_at_a_full_commit_sha(monkeypatch, rev):
    """``check-dispatch --main-sha`` reaches git only as a full lowercase sha, so no option or ref name can."""
    got = []
    monkeypatch.setattr(OP, "charter_bytes", lambda rev=None, repo=None: got.append(rev) or CHARTER_AS_RUN)
    charter = OP.read_charter(rev)
    assert got == [] and "is not a full commit sha" in charter["error"]
    assert OP.charter_refusals(charter)[0].startswith("CHARTER_NOT_ACTIVE")


def test_the_charter_is_read_from_the_commit_named_not_the_working_tree(tmp_path):
    def git(*args) -> str:
        return subprocess.run(["git", "-C", str(tmp_path), "-c", "user.email=t@example.invalid", "-c", "user.name=t",
                               "-c", "commit.gpgsign=false", *args], capture_output=True, text=True, check=True,
                              timeout=60).stdout.strip()

    git("init", "--quiet")
    (tmp_path / "README").write_text("no charter yet\n")
    git("add", "-A")
    git("commit", "--quiet", "--no-verify", "-m", "before")
    before = git("rev-parse", "HEAD")
    path = tmp_path / OP.CHARTER_REL
    path.parent.mkdir(parents=True)
    commits = {}
    for status, raw in (("ACTIVE", CHARTER_AS_RUN), ("CLOSED", CHARTER_CLOSED)):
        path.write_bytes(raw)
        git("add", "-A")
        git("commit", "--quiet", "--no-verify", "-m", status)
        commits[status] = git("rev-parse", "HEAD")
    path.write_bytes(CHARTER_AS_RUN)  # the working tree says ACTIVE; at a commit, the commit decides
    assert OP.read_charter(commits["ACTIVE"], tmp_path) == {**ACTIVE, "rev": commits["ACTIVE"]}
    assert OP.read_charter(commits["CLOSED"], tmp_path) == {"path": OP.CHARTER_REL, "rev": commits["CLOSED"],
                                                            "status": "CLOSED", "sha256": CLOSED_SHA256}
    assert OP.read_charter(None, tmp_path) == ACTIVE
    for missing in (before, "f" * 40):
        error = OP.read_charter(missing, tmp_path)["error"]
        assert error.startswith("OSError: git cat-file: fatal:") and error.endswith("(is main fetched here?)")


def test_a_symlink_never_stands_in_for_the_charter(tmp_path):
    """In the checkout, a symlinked charter or charter directory is refused, even when it points at a file that
    says ACTIVE. At a commit, git stores a symlink as its target path, which is not JSON."""
    decoy = tmp_path / "decoy"
    decoy.mkdir()
    (decoy / f"{OP.PROGRAM_ID}.json").write_bytes(CHARTER_AS_RUN)
    as_file = tmp_path / "file-link"
    (as_file / "charters/programs").mkdir(parents=True)
    (as_file / OP.CHARTER_REL).symlink_to(decoy / f"{OP.PROGRAM_ID}.json")
    as_dir = tmp_path / "dir-link"
    (as_dir / "charters").mkdir(parents=True)
    (as_dir / "charters/programs").symlink_to(decoy, target_is_directory=True)
    for repo in (as_file, as_dir):
        assert (repo / OP.CHARTER_REL).read_bytes() == CHARTER_AS_RUN  # the link itself resolves to ACTIVE
        charter = OP.read_charter(None, repo)
        assert charter["error"] == f"OSError: {OP.CHARTER_REL} is reached through a symlink"
        assert OP.decide(state(charter=charter), [], "D0", 1)["decision"] == DG.NO_DISPATCH

    def git(*args) -> str:
        return subprocess.run(["git", "-C", str(as_file), "-c", "user.email=t@example.invalid", "-c", "user.name=t",
                               "-c", "commit.gpgsign=false", *args], capture_output=True, text=True, check=True,
                              timeout=60).stdout.strip()

    git("init", "--quiet")
    git("add", "-A")
    git("commit", "--quiet", "--no-verify", "-m", "a symlinked charter")
    assert git("ls-files", "-s", OP.CHARTER_REL).startswith("120000 ")
    assert OP.read_charter(git("rev-parse", "HEAD"), as_file)["error"].startswith("JSONDecodeError")


def test_a_local_replace_ref_cannot_reopen_the_charter_at_a_commit(tmp_path):
    """``git replace`` can make a clone show other bytes for an object; the charter is read without it."""
    def git(*args) -> str:
        return subprocess.run(["git", "-C", str(tmp_path), "-c", "user.email=t@example.invalid", "-c", "user.name=t",
                               "-c", "commit.gpgsign=false", *args], capture_output=True, text=True, check=True,
                              timeout=60).stdout.strip()

    git("init", "--quiet")
    path = tmp_path / OP.CHARTER_REL
    path.parent.mkdir(parents=True)
    blobs = {}
    for status, raw in (("ACTIVE", CHARTER_AS_RUN), ("CLOSED", CHARTER_CLOSED)):
        path.write_bytes(raw)
        git("add", "-A")
        git("commit", "--quiet", "--no-verify", "-m", status)
        blobs[status] = git("rev-parse", f"HEAD:{OP.CHARTER_REL}")
    closed = git("rev-parse", "HEAD")
    git("replace", blobs["CLOSED"], blobs["ACTIVE"])
    assert json.loads(git("show", f"{closed}:{OP.CHARTER_REL}"))["status"] == "ACTIVE"  # what git shows by default
    assert OP.read_charter(closed, tmp_path)["status"] == "CLOSED"


def test_the_charter_was_active_through_auth2s_last_main_and_is_closed_since():
    for rev in (EVIDENCE_COMMIT, OD_C4_BASE):
        if subprocess.run(["git", "-C", str(REPO), "cat-file", "-e", f"{rev}^{{commit}}"],
                          capture_output=True, timeout=60).returncode != 0:
            pytest.skip("this checkout does not hold AUTH-2's history (shallow)")
    assert OP.read_charter(EVIDENCE_COMMIT) == {**ACTIVE, "rev": EVIDENCE_COMMIT}
    assert OP.read_charter(OD_C4_BASE) == {"path": OP.CHARTER_REL, "rev": OD_C4_BASE, "status": "CLOSED",
                                           "sha256": CLOSED_SHA256}


@pytest.fixture(scope="module")
def base_operator(tmp_path_factory):
    """The operator as main had it before this refusal (PR #64's merge), loaded beside today's."""
    got = subprocess.run(["git", "-C", str(REPO), "cat-file", "blob", f"{OD_C4_BASE}:.github/gates/auth2_operator.py"],
                         capture_output=True, timeout=60)
    if got.returncode != 0:
        pytest.skip("this checkout does not hold the base commit (shallow history)")
    path = tmp_path_factory.mktemp("base") / "auth2_operator_base.py"
    path.write_bytes(got.stdout)
    saved = list(sys.path)
    spec = importlib.util.spec_from_file_location("auth2_operator_base", path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.path[:] = saved
    assert mod.DG is DG and not hasattr(mod, "charter_refusals")
    return mod


BIG = {"readable": True, "remaining_included_minutes": 100000, "budget_usd_zero": True}
LOW = {"readable": True, "remaining_included_minutes": 535, "budget_usd_zero": True}
ONLY_ADDS = [  # (state, aux, node, part, attempt, earlier minutes): decisions of every kind before OD-C4
    (state(), [], "D0", 1, 1, 0),
    (state(), [aux(1, minutes=40)], "PC-A2", 2, 1, 0),
    (state(billing={"readable": False, "reason": "HTTP 403"}), [aux(1)], "D0", 1, 1, 0),
    (state(billing={"readable": True, "remaining_included_minutes": 700, "budget_usd_zero": True}), [], "A2", 1, 1, 0),
    (state(), [aux(5, status="in_progress", conclusion=None)], "D0", 1, 1, 0),
    (state(billing=BIG), [aux(1, minutes=3700)], "PC-A2", 1, 1, 0),
    (state(billing=BIG), [], "N-A2", 1, 1, 3900),
    (state(), [], "CAL-A1", 1, 2, 0),
    (state(first_record_problems=["FAIL_CLOSED: the month's first record is unreadable"]), [], "A1", 1, 1, 0),
    (state(runs=HOLM_DONE), [], OP.CLOSURE, 1, 1, 0),
    (state(runs=HOLM_DONE), [aux(2, OP.CLOSURE_WORKFLOW)], OP.CLOSURE, 1, 1, 0),
    (state(runs=HOLM_DONE), [aux(2, OP.CLOSURE_WORKFLOW, conclusion="failure"),
                             aux(3, OP.CLOSURE_WORKFLOW, conclusion="failure")], OP.CLOSURE, 1, 1, 0),
    (state(billing=LOW), [], OP.CLOSURE, 1, 1, 0),
    (state(billing=LOW), [], "D0", 1, 1, 0),
]


def test_the_refusal_only_adds_to_the_decision_before_it(base_operator):
    """OD-C4 "only adds a refusal": with the charter ACTIVE every decision is the base operator's, field for
    field; with it CLOSED, missing or unreadable the reasons are the base's plus CHARTER_NOT_ACTIVE, last, and
    the decision is NO_DISPATCH, whatever it was (PARK included)."""
    seen = set()
    closed = {**ACTIVE, "status": "CLOSED"}
    for s, ax, node, part, attempt, earlier in ONLY_ADDS:
        before = base_operator.decide(copy.deepcopy(s), copy.deepcopy(ax), node, part, attempt, earlier)
        seen.add(before["decision"])
        active = OP.decide(copy.deepcopy(s), copy.deepcopy(ax), node, part, attempt, earlier)
        assert active.pop("charter") == ACTIVE and active == before
        for charter in (closed, None, DROP, {"path": OP.CHARTER_REL, "rev": "working tree", "error": "x"}):
            s2 = copy.deepcopy(s)
            s2.pop("charter") if charter is DROP else s2.update(charter=charter)
            after = OP.decide(s2, copy.deepcopy(ax), node, part, attempt, earlier)
            assert after.pop("charter") == (None if charter is DROP else charter)
            assert after.pop("decision") == DG.NO_DISPATCH
            refused = after.pop("reasons")
            assert refused == before["reasons"] + OP.charter_refusals(None if charter is DROP else charter)
            assert after == {k: v for k, v in before.items() if k not in ("decision", "reasons")}
    assert seen == {DG.DISPATCH, DG.PARK, DG.NO_DISPATCH}


# end to end, through World: the Owner's guard run, the executor's check and the node's or closure's own guard

def test_each_gate_reads_the_charter_where_it_runs(world):
    """The Owner's guard and the node's in-job guard read their own checkout; the executor's check reads main."""
    pre, chk, job = d0_flow(world)
    assert (pre["decision"], chk["decision"], job["decision"]) == (DG.DISPATCH,) * 3
    assert world.charter_reads == [None, MAIN, None]
    assert pre["charter"] == job["charter"] == ACTIVE and chk["charter"] == {**ACTIVE, "rev": MAIN}


@pytest.mark.parametrize("node", ["D0", OP.CLOSURE])
def test_a_closed_charter_refuses_at_every_gate_even_with_valid_owner_evidence(world, node):
    world.charter[None] = CHARTER_CLOSED
    pre = world.owner_guard(100, node)
    assert pre["decision"] == DG.NO_DISPATCH and pre["reasons"] == [refusal("CLOSED")]
    assert pre["billing"]["owner_evidence_problems"] == []  # the evidence is valid; the charter alone refuses
    chk = world.check(100, node)
    assert chk["decision"] == DG.NO_DISPATCH and chk["dispatch_inputs"] is None and chk["owner_evidence"] is None
    assert refusal("CLOSED", MAIN) in chk["reasons"]
    assert any(r.startswith("CHARTER_NOT_ACTIVE: the guard record shows") for r in chk["reasons"])
    job = world.dispatch(200, node, guard_run=100, digest=pre["billing"]["owner_evidence"]["evidence_digest"])
    assert job["decision"] == DG.NO_DISPATCH and refusal("CLOSED") in job["reasons"]
    assert job["charter"]["status"] == "CLOSED"


@pytest.mark.parametrize("node", ["D0", OP.CLOSURE])
def test_the_charter_alone_refuses_the_executors_check(world, node):
    """The Owner's guard read ACTIVE and decided DISPATCH; at the main the executor checks, the charter reads
    CLOSED. Nothing else is wrong, and the check refuses."""
    assert world.owner_guard(100, node)["decision"] == DG.DISPATCH
    world.charter[MAIN] = CHARTER_CLOSED
    chk = world.check(100, node)
    assert (chk["decision"], chk["dispatch_inputs"], chk["owner_evidence"]) == (DG.NO_DISPATCH, None, None)
    assert chk["reasons"] == [refusal("CLOSED", MAIN)] and chk["charter"]["rev"] == MAIN


@pytest.mark.parametrize("node", ["D0", OP.CLOSURE])
def test_the_charter_alone_refuses_the_in_job_guard(world, node):
    """The guard and the check passed; the dispatched run's own checkout says CLOSED. It refuses before the node
    or the closure runs, for that reason alone."""
    world.owner_guard(100, node)
    chk = world.check(100, node)
    assert chk["decision"] == DG.DISPATCH
    world.charter[None] = CHARTER_CLOSED
    job = world.dispatch(200, node, guard_run=100, digest=chk["dispatch_inputs"]["evidence_digest"])
    assert job["decision"] == DG.NO_DISPATCH and job["reasons"] == [refusal("CLOSED")]
    assert job["billing"]["readable"] is True  # the binding held; only the charter refused


def test_a_closed_charter_is_named_even_when_the_run_history_is_unreadable(world):
    world.charter[None] = CHARTER_CLOSED
    world.add(53, DG.WORKFLOW_FILE, "AUTH2 something", "2026-11-01T00:00:00Z")  # a title no node run has
    pre = world.owner_guard(100)
    assert pre["decision"] == DG.NO_DISPATCH and pre["charter"]["status"] == "CLOSED"
    assert pre["reasons"][0].startswith("FAIL_CLOSED: AUTH-2 run history not readable")
    assert pre["reasons"][1:] == [refusal("CLOSED")]


@pytest.mark.parametrize("name", ["auth2-guard.yml", "auth2.yml", "auth2-closure.yml"])
def test_every_auth2_job_guards_on_its_own_commits_checkout(name):
    """The guard reads the charter from the checkout, so every AUTH-2 job checks out the commit it was dispatched
    at (no other ref or repository) before its guard step runs the operator."""
    [job] = load(name)["jobs"].values()
    steps = job["steps"]
    checkout = next(i for i, s in enumerate(steps) if s.get("uses", "").startswith("actions/checkout"))
    guard = next(i for i, s in enumerate(steps) if "dispatch guard" in s.get("name", ""))
    assert checkout < guard and not {"ref", "repository", "path"} & set(steps[checkout].get("with") or {})
    assert "python .github/gates/auth2_operator.py guard " in steps[guard]["run"]
