#!/usr/bin/env python3
"""Attempt classes, bounded retries and the TECHNICAL_EXHAUSTION terminal (Owner decisions OD-S5 and OD-S6;
review section 3, "Attempt classes").

Every way a node run can end falls in exactly one class, read from the Actions jobs API alone:

  ADMISSION  the guard refused before dispatch: no node run exists        no attempt   minutes count
  INFRA      the node job ended before its science step started            no attempt   minutes count
             (checkout, dependencies, restore or verify, a lost runner)    at most MAX_INFRA_RETRIES retries
  SCIENCE    the science step started and the job ended without a result   an attempt   MAX_SCIENCE_ATTEMPTS
             (timeout, lost runner, a technical INVALID_RUN)
  RESULT     the node wrote its result                                     never re-run

"Started" is read from the science step's own record: a step that never ran either has no start time or (as the
jobs API reports every step after a failure or a cancellation) carries timestamps with conclusion "skipped". Only
a science step that is present exactly once and provably never started makes a run INFRA. A missing, repeated or
unreadable science step, or one with no start time but no "skipped" either, counts as SCIENCE: fail closed, so a
run whose science may have seen data never gets a free retry.

A node part ends RESULT, or TECHNICAL_EXHAUSTION (state ABORTED, outcome NOT_RUN, measurement_validity
NOT_APPLICABLE) with one reason: INFRA_RETRIES_SPENT, ATTEMPTS_SPENT, or CAP_REACHED when the compute guard
cannot admit its next run (compute.py). Nothing here dispatches, writes a ledger or reads market data.

PAPER / RESEARCH ONLY.
"""

from __future__ import annotations

from datetime import datetime

ADMISSION, INFRA, SCIENCE, RESULT = "ADMISSION", "INFRA", "SCIENCE", "RESULT"
ACTIVE_RUN, INCONSISTENT = "ACTIVE", "INCONSISTENT"
CLASSES = (ADMISSION, INFRA, SCIENCE, RESULT)
ACTIVE = ("queued", "in_progress", "waiting", "requested", "pending")
SCIENCE_STEP = "Science phase (network removed)"
MAX_SCIENCE_ATTEMPTS = 2
MAX_INFRA_RETRIES = 2

TECHNICAL_EXHAUSTION = "TECHNICAL_EXHAUSTION"
INFRA_RETRIES_SPENT, ATTEMPTS_SPENT, CAP_REACHED = "INFRA_RETRIES_SPENT", "ATTEMPTS_SPENT", "CAP_REACHED"
EXHAUSTION_REASONS = (INFRA_RETRIES_SPENT, ATTEMPTS_SPENT, CAP_REACHED)
TERMINAL_STATE, TERMINAL_OUTCOME, TERMINAL_VALIDITY = "ABORTED", "NOT_RUN", "NOT_APPLICABLE"

DISPATCH, DONE, EXHAUSTED = "DISPATCH", "DONE", TECHNICAL_EXHAUSTION


def _ts(raw) -> datetime | None:
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


def never_ran(job: dict) -> bool:
    """A job GitHub skipped (its ``if`` was false): it never had a runner or a step, so it bills nothing."""
    return job.get("status") == "completed" and job.get("conclusion") == "skipped" and not job.get("steps") \
        and not job.get("runner_id") and not job.get("runner_name")


def billed_minutes(job: dict, timeout: int) -> int:
    """Billed minutes of one job: every minute it started, at least one. A job that is not finished, or whose
    times are unreadable, counts timeout + 1, what a job GitHub stops at its timeout bills (readiness test
    RT-10 measures it). A job GitHub skipped never ran and bills 0."""
    if never_ran(job):
        return 0
    a, b = _ts(job.get("started_at")), _ts(job.get("completed_at"))
    if job.get("status") != "completed" or a is None or b is None or b < a:
        return timeout + 1
    # The API's times are whole seconds and GitHub rounds each job up to the next minute, so a reading of an
    # exact number of minutes (or of none) counts the next one: never low, at most one minute high.
    return int((b - a).total_seconds()) // 60 + 1


def science_started(steps, name: str = SCIENCE_STEP) -> tuple[bool, str]:
    """(started, why). False only with proof that the one science step never ran."""
    if not isinstance(steps, list):
        return True, "the job has no step list; fail closed"
    named = [s for s in steps if isinstance(s, dict) and s.get("name") == name]
    if len(named) != 1:
        return True, f"the job lists {len(named)} step(s) named {name!r}, not one; fail closed"
    s = named[0]
    status, conclusion = s.get("status"), s.get("conclusion")
    if status == "completed" and conclusion == "skipped":
        return False, "the science step was skipped: the job ended before it"
    if status in ("queued", "pending", "waiting") and not s.get("started_at") and conclusion is None:
        return False, f"the science step is {status} and never started"
    if s.get("started_at") and status in ("in_progress", "completed"):
        return True, f"the science step ran (status {status}, conclusion {conclusion})"
    return True, f"the science step's record (status {status!r}, conclusion {conclusion!r}) is unclear; fail closed"


def classify_job(job: dict, *, science_step: str = SCIENCE_STEP, result: bool = False) -> dict:
    """The class of one finished node job. ``result``: the job's result record was read (annotations or
    artifact) and is a node result, not a technical INVALID_RUN. A result, once written, is never re-run, even
    if a later step of the job failed; a result from a job whose science step never ran is INCONSISTENT, which
    no state machine accepts (the guard refuses until a person looks)."""
    if not isinstance(job, dict) or job.get("status") != "completed":
        return {"class": ACTIVE_RUN, "why": f"the job is {job.get('status') if isinstance(job, dict) else 'unread'}"}
    if not job.get("steps") and not job.get("runner_id") and not job.get("runner_name"):
        started, why = False, "the job never had a runner or a step: nothing in it can have read data"
    else:
        started, why = science_started(job.get("steps"), science_step)
    if not started:
        if result:
            return {"class": INCONSISTENT, "why": f"{why}, yet a node result is published"}
        return {"class": INFRA, "why": why}
    if result:
        return {"class": RESULT, "why": f"{why}; the node wrote its result"}
    return {"class": SCIENCE, "why": f"{why}; no node result (job conclusion {job.get('conclusion')})"}


def classify_run(jobs: list[dict], node_job: str, **kw) -> dict:
    """The class of one node run: its jobs as the API lists them (one attempt), the node job by name."""
    mine = [j for j in jobs if isinstance(j, dict) and j.get("name") == node_job]
    if len(mine) != 1:
        if any(isinstance(j, dict) and j.get("status") in ACTIVE for j in jobs):
            return {"class": ACTIVE_RUN, "why": "the run is still active"}
        return {"class": SCIENCE, "why": f"the run has {len(mine)} job(s) named {node_job!r}, not one; fail closed"}
    return classify_job(mine[0], **kw)


def part_state(history: list[str]) -> dict:
    """Where one node part stands, from the classes of its runs in dispatch order (ADMISSION refusals are not
    runs and are not in the history). Raises ValueError on a history no guard could have produced."""
    science = infra = 0
    for i, c in enumerate(history):
        if c not in (INFRA, SCIENCE, RESULT):
            raise ValueError(f"run {i + 1}: {c!r} is not a node run class")
        if i and _terminal(history[:i]):
            raise ValueError(f"run {i + 1} follows the part's terminal state: no guard admits it")
        if c == SCIENCE:
            science += 1
        elif c == INFRA:
            infra += 1
    out = {"runs": len(history), "science_attempts": science, "infra_failures": infra,
           "infra_retries_used": min(infra, MAX_INFRA_RETRIES)}
    end = _terminal(history)
    if end == RESULT:
        return {**out, "next": DONE, "terminal": RESULT}
    if end:
        return {**out, "next": EXHAUSTED, "terminal": TECHNICAL_EXHAUSTION, "reason": end}
    retry = (SCIENCE if history and history[-1] == SCIENCE else INFRA if history else None)
    return {**out, "next": DISPATCH, "retry_of": retry, "first_science_attempt": science == 0}


def _terminal(history: list[str]) -> str | None:
    if RESULT in history:
        return RESULT
    if history.count(SCIENCE) >= MAX_SCIENCE_ATTEMPTS:
        return ATTEMPTS_SPENT
    if history.count(INFRA) > MAX_INFRA_RETRIES:
        return INFRA_RETRIES_SPENT
    return None


def max_runs_per_part() -> int:
    """At most MAX_INFRA_RETRIES INFRA runs and MAX_SCIENCE_ATTEMPTS - 1 SCIENCE runs can be followed by another
    run; the run after them ends the part whatever it is."""
    return MAX_INFRA_RETRIES + (MAX_SCIENCE_ATTEMPTS - 1) + 1


def terminal_payload(prereg: dict, reason: str, program_sha256: str, node: str) -> dict:
    """The trial-ledger terminal record of a node part that ended TECHNICAL_EXHAUSTION: the preregistration's
    payload (its purpose verbatim, as the ledger requires) with state ABORTED and the exhaustion outcome."""
    if reason not in EXHAUSTION_REASONS:
        raise ValueError(f"{reason!r} is not a TECHNICAL_EXHAUSTION reason {EXHAUSTION_REASONS}")
    payload = {k: v for k, v in prereg.items() if k not in ("notes", "outcome")}
    payload["state"] = TERMINAL_STATE
    payload["outcome"] = {"reason": f"{TECHNICAL_EXHAUSTION}: {node} {reason}", "terminal": TECHNICAL_EXHAUSTION,
                          "technical_reason": reason, "outcome": TERMINAL_OUTCOME,
                          "measurement_validity": TERMINAL_VALIDITY, "program_sha256": program_sha256}
    return payload
