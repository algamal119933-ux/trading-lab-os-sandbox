"""AUTH-2-DISCOVERY-QUALIFICATION-2 readiness (RT-0): attempt classes, bounded retries, TECHNICAL_EXHAUSTION
(research/auth2q2/attempts.py) and the guarded compute proof (research/auth2q2/compute.py).

The classifier reads the Actions jobs API only. Its fixtures are the API's own records of AUTH-2's two D0 runs
(tests/fixtures/auth2q2_jobs_api.json), read as AUTH-2 counted them and re-shaped into a successor node job. The
TECHNICAL_EXHAUSTION terminal goes through the real trial-ledger code and schema on a temporary copy of the
ledger, with fixture trial IDs; the committed ledger is checked unchanged.

PAPER / RESEARCH ONLY. Nothing here dispatches or calls GitHub.
"""

from __future__ import annotations

import copy
import hashlib
import itertools
import json
import shutil
from pathlib import Path

import pytest

from auth2q2 import attempts as AT
from auth2q2 import compute as C

REPO = Path(__file__).resolve().parents[1]
JOBS = json.loads((REPO / "tests" / "fixtures" / "auth2q2_jobs_api.json").read_text())["runs"]
AUTH2_NODE_STEP = "Run the node (refuses unless the program, ledger and DAG allow it)"
LEDGER = REPO / "research" / "records" / "trial_ledger.jsonl"


def d0(run: str) -> dict:
    (job,) = JOBS[run]
    return copy.deepcopy(job)


def successor_shape(job: dict, fail_at: str, how: str = "failure") -> dict:
    """The AUTH-2 D0 job's timestamps on a successor node job's steps: in-job admission, restore, verify, then
    the science step. ``fail_at`` names the step that ends the job (``how``); later steps are skipped, with
    timestamps, as the API reports them."""
    names = ["Set up job", "Run actions/checkout@v4", "Run actions/setup-python@v5", "Install pinned dependencies",
             "Gate: in-job admission (program, preregistrations, ledger, DAG, snapshot digest)",
             "Restore the snapshot (cache, else the release), every file verified",
             "Verify the restored tree against the manifest", AT.SCIENCE_STEP, "Publish the result summary",
             "Complete job"]
    t0, t1 = job["started_at"], job["completed_at"]
    steps, ended = [], False
    for i, name in enumerate(names, 1):
        if name == "Complete job":
            steps.append({"number": i, "name": name, "status": "completed", "conclusion": "success",
                          "started_at": t1, "completed_at": t1})
        elif ended and name != "Publish the result summary":
            steps.append({"number": i, "name": name, "status": "completed", "conclusion": "skipped",
                          "started_at": t1, "completed_at": t1})
        elif name == fail_at:
            steps.append({"number": i, "name": name, "status": "completed", "conclusion": how,
                          "started_at": t0, "completed_at": t1})
            ended = True
        else:
            steps.append({"number": i, "name": name, "status": "completed",
                          "conclusion": "success" if not ended else "success", "started_at": t0, "completed_at": t0})
    return {**job, "name": "node", "conclusion": how, "steps": steps}


# -- billed minutes ----------------------------------------------------------------------------------

def test_billed_minutes_are_the_run_time_rounded_up():
    assert AT.billed_minutes(d0("38273417548"), 150) == 1  # 43 s
    assert AT.billed_minutes(d0("38286502721"), 150) == 151  # cancelled at the 150-minute timeout: 151 billed
    running = {**d0("38286502721"), "status": "in_progress", "completed_at": None}
    assert AT.billed_minutes(running, 150) == 151
    garbled = {**d0("38273417548"), "completed_at": "yesterday"}
    assert AT.billed_minutes(garbled, 30) == 31
    backwards = {**d0("38273417548"), "completed_at": "2026-10-12T15:52:49Z"}
    assert AT.billed_minutes(backwards, 30) == 31


def test_a_job_github_skipped_bills_nothing_and_nothing_else_passes_for_skipped():
    skipped = {"status": "completed", "conclusion": "skipped", "started_at": None, "completed_at": None,
               "steps": [], "runner_id": None, "runner_name": None}
    assert AT.billed_minutes(skipped, 90) == 0
    assert AT.billed_minutes({**skipped, "runner_id": 0, "started_at": "2026-10-13T10:00:00Z",
                              "completed_at": "2026-10-13T10:00:00Z"}, 90) == 0
    # anything that ran, or might have, is billed as usual or as timeout + 1
    assert AT.billed_minutes({**skipped, "runner_id": 1000001033}, 90) == 91
    assert AT.billed_minutes({**skipped, "runner_name": "GitHub Actions 7"}, 90) == 91
    assert AT.billed_minutes({**skipped, "steps": [{"name": "Set up job"}]}, 90) == 91
    assert AT.billed_minutes({**skipped, "conclusion": "cancelled"}, 90) == 91
    assert AT.billed_minutes({**skipped, "status": "queued"}, 90) == 91


# -- classification ------------------------------------------------------------------------------------

def test_auth2s_two_d0_runs_each_used_an_attempt_as_auth2_counted_them():
    for run in ("38273417548", "38286502721"):
        got = AT.classify_job(d0(run), science_step=AUTH2_NODE_STEP)
        assert got["class"] == AT.SCIENCE, (run, got)


def test_shaped_like_run_38273417548_a_harness_refusal_before_science_is_infra_not_an_attempt():
    job = successor_shape(d0("38273417548"), "Gate: in-job admission (program, preregistrations, ledger, DAG, "
                                              "snapshot digest)")
    assert AT.classify_job(job)["class"] == AT.INFRA
    assert AT.classify_job(job, result=True)["class"] == AT.INCONSISTENT


def test_shaped_like_run_38286502721_a_timeout_in_the_restore_is_infra_and_in_science_is_an_attempt():
    job = d0("38286502721")
    restore = successor_shape(job, "Restore the snapshot (cache, else the release), every file verified", "cancelled")
    assert AT.classify_job(restore)["class"] == AT.INFRA
    science = successor_shape(job, AT.SCIENCE_STEP, "cancelled")
    assert AT.classify_job(science)["class"] == AT.SCIENCE
    assert AT.billed_minutes(science, 150) == 151


def test_a_written_result_is_never_re_run_even_if_a_later_step_failed():
    job = successor_shape(d0("38273417548"), "Publish the result summary")
    assert AT.classify_job(job, result=True)["class"] == AT.RESULT
    assert AT.classify_job(job, result=False)["class"] == AT.SCIENCE


def test_a_job_cancelled_with_its_later_steps_skipped_is_read_from_the_skipped_marks():
    (job,) = JOBS["34064311322"]  # a real cancelled job: every step after the cancelled one is "skipped"
    assert AT.classify_job(job, science_step="Acquire Binance spot klines from the public data archive")["class"] \
        == AT.INFRA
    assert AT.classify_job(job, science_step="Probe public Binance data endpoints")["class"] == AT.SCIENCE


@pytest.mark.parametrize("edit,why", [
    (lambda steps: [s for s in steps if s["name"] != AT.SCIENCE_STEP], "not one"),
    (lambda steps: steps + [dict(next(s for s in steps if s["name"] == AT.SCIENCE_STEP))], "not one"),
    (lambda steps: [dict(s, status="completed", conclusion="failure", started_at=None)
                    if s["name"] == AT.SCIENCE_STEP else s for s in steps], "unclear"),
    (lambda steps: "not a list", "no step list"),
    (lambda steps: [dict(s, status="in_progress") if s["name"] == AT.SCIENCE_STEP else s for s in steps],
     "science step ran"),
    (lambda steps: [dict(s, status=None) if s["name"] == AT.SCIENCE_STEP else s for s in steps], "unclear"),
])
def test_an_unreadable_science_step_fails_closed_as_an_attempt(edit, why):
    job = successor_shape(d0("38273417548"), "Verify the restored tree against the manifest")
    job["steps"] = edit(job["steps"])
    got = AT.classify_job(job)
    assert got["class"] == AT.SCIENCE and why in got["why"]


def test_a_job_that_never_had_a_runner_or_a_step_is_infra_not_an_attempt():
    base = {"name": "x", "status": "completed", "steps": [], "runner_id": None, "runner_name": None,
            "started_at": None, "completed_at": None}
    for conclusion in ("skipped", "cancelled", "failure"):
        got = AT.classify_job({**base, "conclusion": conclusion})
        assert got["class"] == AT.INFRA and "never had a runner" in got["why"]
    assert AT.classify_job({**base, "conclusion": "cancelled"}, result=True)["class"] == AT.INCONSISTENT
    with_runner = {**base, "conclusion": "failure", "runner_id": 7}  # it had a runner: fail closed
    assert AT.classify_job(with_runner)["class"] == AT.SCIENCE


def test_billing_never_reads_low_at_a_whole_minute_or_at_zero():
    ran = {"status": "completed", "conclusion": "success", "steps": [{"name": "Set up job"}], "runner_id": 7,
           "started_at": "2026-10-13T10:00:00Z"}
    for end, billed in (("10:00:00", 1), ("10:00:59", 1), ("10:01:00", 2), ("10:02:00", 3), ("10:02:59", 3)):
        assert AT.billed_minutes({**ran, "completed_at": f"2026-10-13T{end}Z"}, 2) == billed, end


def test_a_science_step_that_is_queued_and_never_started_is_infra():
    job = successor_shape(d0("38273417548"), "Verify the restored tree against the manifest")
    for s in job["steps"]:
        if s["name"] == AT.SCIENCE_STEP:
            s.update(status="queued", conclusion=None, started_at=None, completed_at=None)
    assert AT.classify_job(job)["class"] == AT.INFRA


def test_an_active_job_or_run_is_not_classified():
    job = {**d0("38273417548"), "status": "in_progress", "conclusion": None}
    assert AT.classify_job(job)["class"] == AT.ACTIVE_RUN
    assert AT.classify_run([job], "AUTH-2 D0 part 1")["class"] == AT.ACTIVE_RUN
    assert AT.classify_run([d0("38273417548")], "another job")["class"] == AT.SCIENCE
    assert AT.classify_run([d0("38273417548")] * 2, "AUTH-2 D0 part 1")["class"] == AT.SCIENCE


# -- retries and exhaustion --------------------------------------------------------------------------

@pytest.mark.parametrize("history,next_,extra", [
    ([], AT.DISPATCH, {"first_science_attempt": True, "retry_of": None}),
    ([AT.INFRA], AT.DISPATCH, {"first_science_attempt": True, "retry_of": AT.INFRA}),
    ([AT.INFRA, AT.INFRA], AT.DISPATCH, {"infra_retries_used": 2}),
    ([AT.INFRA, AT.INFRA, AT.INFRA], AT.EXHAUSTED, {"reason": AT.INFRA_RETRIES_SPENT}),
    ([AT.SCIENCE], AT.DISPATCH, {"first_science_attempt": False, "retry_of": AT.SCIENCE}),
    ([AT.SCIENCE, AT.SCIENCE], AT.EXHAUSTED, {"reason": AT.ATTEMPTS_SPENT}),
    ([AT.INFRA, AT.INFRA, AT.SCIENCE, AT.SCIENCE], AT.EXHAUSTED, {"reason": AT.ATTEMPTS_SPENT}),
    ([AT.SCIENCE, AT.INFRA, AT.INFRA, AT.INFRA], AT.EXHAUSTED, {"reason": AT.INFRA_RETRIES_SPENT}),
    ([AT.INFRA, AT.SCIENCE, AT.RESULT], AT.DONE, {"terminal": AT.RESULT}),
])
def test_a_node_part_gets_two_infra_retries_and_two_science_attempts(history, next_, extra):
    got = AT.part_state(history)
    assert got["next"] == next_
    assert {k: got[k] for k in extra} == extra


@pytest.mark.parametrize("history", [
    [AT.RESULT, AT.INFRA], [AT.SCIENCE, AT.SCIENCE, AT.INFRA], [AT.INFRA] * 4, [AT.ADMISSION], [AT.INCONSISTENT],
    ["ACTIVE"], ["result"],
])
def test_no_run_after_a_terminal_and_no_unknown_class_is_accepted(history):
    with pytest.raises(ValueError):
        AT.part_state(history)


def test_every_possible_history_ends_within_four_runs():
    seen_terminal = 0
    for n in range(0, 7):
        for h in itertools.product((AT.INFRA, AT.SCIENCE, AT.RESULT), repeat=n):
            try:
                st = AT.part_state(list(h))
            except ValueError:
                continue
            assert len(h) <= AT.max_runs_per_part() == 4
            if st["next"] != AT.DISPATCH:
                seen_terminal += 1
            else:
                assert len(h) < 4
    assert seen_terminal > 0


# -- TECHNICAL_EXHAUSTION through the real ledger code and schema --------------------------------------

def test_technical_exhaustion_is_a_valid_terminal_record_on_a_copy_of_the_ledger(tmp_path):
    pytest.importorskip("jsonschema")
    from trial_ledger import TrialLedger, TrialLedgerError

    before = hashlib.sha256(LEDGER.read_bytes()).hexdigest()
    copy_path = tmp_path / "trial_ledger.jsonl"
    shutil.copyfile(LEDGER, copy_path)
    led = TrialLedger(copy_path)
    n0 = len(led.records())
    base = json.loads(LEDGER.read_text().splitlines()[26])["payload"]  # TRIAL-AUTH2-D0's preregistration
    for reason in AT.EXHAUSTION_REASONS:
        trial = f"TRIAL-FIXTURE-AUTH2Q2-{reason}"
        prereg = {**base, "trial_id": trial, "run_id": f"RUN-FIXTURE-{reason}", "experiment_id": "EXP-FIXTURE",
                  "family_id": "FIXTURE_AUTH2Q2", "lineage_id": "FIXTURE_AUTH2Q2/L1",
                  "candidate_id": "FIXTURE_AUTH2Q2/X", "config_id": "FIXTURE_AUTH2Q2/X",
                  "notes": "test fixture on a temporary copy; never appended to the committed ledger"}
        led.append(prereg, recorded_utc="2026-10-13T00:00:00Z")
        term = AT.terminal_payload(prereg, reason, "a" * 64, "FIXTURE")
        assert term["state"] == "ABORTED" and term["purpose"] == prereg["purpose"] and "notes" not in term
        assert {k: term["outcome"][k] for k in ("terminal", "technical_reason", "outcome", "measurement_validity")} \
            == {"terminal": "TECHNICAL_EXHAUSTION", "technical_reason": reason, "outcome": "NOT_RUN",
                "measurement_validity": "NOT_APPLICABLE"}
        led.append(term, recorded_utc="2026-10-13T00:00:01Z")
    assert led.verify() == [] and len(led.records()) == n0 + 6
    with pytest.raises(TrialLedgerError):  # the ledger still refuses a terminal record nothing preregistered
        led.append(AT.terminal_payload({**base, "trial_id": "TRIAL-FIXTURE-NEVER"}, AT.CAP_REACHED, "a" * 64, "X"))
    with pytest.raises(ValueError):
        AT.terminal_payload(base, "TIMEOUT", "a" * 64, "D0")
    assert hashlib.sha256(LEDGER.read_bytes()).hexdigest() == before


# -- the compute proof ---------------------------------------------------------------------------------

def test_auth2s_frozen_plan_proves_3960_on_node_jobs_but_bills_up_to_4448_with_every_job():
    assert C.law_proof() == C.AUTH2_LAW_PROOF == 3960
    assert C.worst_case(C.stage_rows()) == C.AUTH2_WORST_CASE == 4448
    assert C.RESERVE == 32


def test_r1_dispatches_only_with_the_job_its_retry_and_the_reserve_inside_the_cap():
    part = {"node": "D0", "part": 1, "timeout": 150, "first_science_attempt": True}
    need = C.need(150, True)
    assert need == {"this_guard": 11, "node": 151, "retry": 162, "reserve": 32, "total": 356}
    assert C.decide(4000 - 356, part)["decision"] == C.DISPATCH
    got = C.decide(4000 - 355, part)
    assert got["decision"] == C.CLOSE and got["reason"] == AT.CAP_REACHED
    retry = {**part, "first_science_attempt": False}
    assert C.need(150, False)["total"] == 194
    assert C.decide(4000 - 194, retry)["decision"] == C.DISPATCH
    assert C.decide(4000 - 193, retry)["reason"] == AT.CAP_REACHED


def test_r2_r3_a_refusal_never_eats_the_reserve_and_the_cap_closes_whatever_else_holds():
    part = {"node": "HOLM", "part": 1, "timeout": 15, "first_science_attempt": False}
    edge = 4000 - C.need(15, False)["total"]
    got = C.decide(edge, part, refusals=["SERIAL: x"])
    assert got["decision"] == C.NO_DISPATCH and "R3" in got["why"]
    assert edge + 11 + C.RESERVE <= 4000  # the refused guard run's minutes leave the reserve whole
    got = C.decide(edge + 1, part, refusals=["FAIL_CLOSED: billing"])
    assert got["decision"] == C.CLOSE and got["reason"] == AT.CAP_REACHED and "R2" in got["why"]
    assert C.decide(3999, None)["reason"] is None  # nothing left to run: an ordinary closure


def _invariants(sim: dict) -> None:
    assert sim["within_cap"] and sim["peak"] <= C.CAP and not sim["unended"]
    assert sum(1 for t in sim["trace"] if t.get("closure")) == 1 and sim["trace"][-1].get("closure")
    for t in sim["trace"][:-2]:  # until the closing guard, the reserve is never touched
        value = t.get("ledger", t.get("ledger_after_guard"))
        assert value + C.RESERVE <= C.CAP, t


def test_the_expected_plan_runs_at_about_1150_minutes_and_nothing_is_exhausted():
    sim = C.simulate(C.parts_in_order(), C.expected_outcomes(), guard_minutes=lambda _i: 1, closure_minutes=2)
    _invariants(sim)
    assert sim["node_runs"] == 19 and set(sim["terminal"].values()) == {AT.RESULT}
    assert 1100 <= sim["ledger"] <= 1200


def test_the_heaviest_runs_stop_at_the_cap_and_still_close():
    sim = C.simulate(C.parts_in_order(), C.worst_outcomes(C.HEAVIEST))
    _invariants(sim)
    assert any(v.endswith(AT.CAP_REACHED) for v in sim["terminal"].values())


@pytest.mark.parametrize("pattern", [p for n in range(0, 5) for p in itertools.product(
    (AT.INFRA, AT.SCIENCE, AT.RESULT), repeat=n)])
def test_every_uniform_outcome_pattern_ends_inside_the_cap(pattern):
    _invariants(C.simulate(C.parts_in_order(), C.worst_outcomes(pattern)))


@pytest.mark.parametrize("seed", range(150))
def test_random_outcomes_refusals_and_guard_times_never_pass_the_cap(seed):
    import random
    rng = random.Random(10_000 + seed)
    p_refuse = rng.choice([0.0, 0.1, 0.5])
    sim = C.simulate(C.parts_in_order(), C.random_outcomes(seed, rng.random() * 0.5, rng.random() * 0.4),
                     guard_minutes=lambda _i: rng.randint(0, 40),
                     refuse=lambda _i, _l: ["FAIL_CLOSED: billing"] if rng.random() < p_refuse else [],
                     closure_minutes=rng.randint(0, 60))
    _invariants(sim)


def test_the_report_cli_passes(tmp_path, capsys):
    assert C.main(["report", "--out", str(tmp_path / "r.json")]) == 0
    rec = json.loads((tmp_path / "r.json").read_text())
    assert rec["auth2_worst_case_all_jobs"] == 4448 and rec["adversarial"]["within_cap"]
    assert "COMPUTE_PROOF = PASS" in capsys.readouterr().out
