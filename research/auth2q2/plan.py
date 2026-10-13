#!/usr/bin/env python3
"""The readiness plan: RT-1 to RT-11 as jobs, their timeouts and the 300-minute readiness ledger (Owner decisions
OD-S4, OD-S7 and OD-S8; review section 4).

One table, read by the readiness gate (.github/gates/auth2q2_readiness.py), the readiness record (record.py) and
the tests that hold the two workflows to it (tests/test_auth2q2_workflows.py): which workflow runs each test, the
name and timeout of every job it can run, and which job's record is the test's verdict. A job's planned maximum is
its timeout + 1, the most a job can bill (RT-10 measures it); a run's is the sum over its jobs, the gate job
included. RT-0 is not a run: it is the offline suite in CI at the readiness commit.

PAPER / RESEARCH ONLY. Nothing here dispatches or reads market data.
"""

from __future__ import annotations

PREPARE_WORKFLOW = "auth2q2-prepare.yml"
READINESS_WORKFLOW = "auth2q2-readiness.yml"
WORKFLOWS = (PREPARE_WORKFLOW, READINESS_WORKFLOW)
CONCURRENCY_GROUP = "auth2q2-readiness"
TITLE = "AUTH2Q2-READINESS {test}"

READINESS_CAP = 300          # OD-S4: the readiness ledger, separate from the program's 4,000 (OD-S7)
GATE_JOB = "Readiness gate"
GATE_TIMEOUT = 10
NEXT_GATE_RESERVE = GATE_TIMEOUT + 1   # room for one more gate run, so a refusal cannot pass the cap
STORAGE_INTERVAL_HOURS = 6   # RT-8: the two billing readings are at least this far apart

# Every job each workflow can run: name -> timeout-minutes (the workflow files are tested against this).
JOBS = {
    PREPARE_WORKFLOW: {
        GATE_JOB: GATE_TIMEOUT,
        "Cold preparation": 90,
        "Snapshot release (contents: write)": 15,
        "Read-only probe": 10,
    },
    READINESS_WORKFLOW: {
        GATE_JOB: GATE_TIMEOUT,
        "RT-4 cold restore and D0 data path": 60,
        "RT-5 restore without a cache entry": 20,
        "RT-5 restore from the warm cache": 20,
        "RT-6 corrupted restored file": 15,
        "RT-6 asset with the wrong digest": 15,
        "RT-6 classify": 10,
        "RT-7 probe infra": 10,
        "RT-7 probe science": 10,
        "RT-7 classify": 10,
        "RT-8 storage, retention and billing": 10,
        "RT-9 billing guard": 10,
        "RT-10 probe": 2,
        "RT-10 classify": 10,
        "RT-11 engine data path": 60,
    },
}

# test -> (workflow, the jobs a run of it runs, the jobs whose published record is its verdict)
TESTS = {
    "RT-1": (PREPARE_WORKFLOW, ("Cold preparation", "Snapshot release (contents: write)"),
             ("Snapshot release (contents: write)",)),
    "RT-2": (PREPARE_WORKFLOW, ("Cold preparation",), ("Cold preparation",)),
    "RT-3": (PREPARE_WORKFLOW, ("Snapshot release (contents: write)", "Read-only probe"),
             ("Snapshot release (contents: write)", "Read-only probe")),
    "RT-4": (READINESS_WORKFLOW, ("RT-4 cold restore and D0 data path",), ("RT-4 cold restore and D0 data path",)),
    "RT-5": (READINESS_WORKFLOW, ("RT-5 restore without a cache entry", "RT-5 restore from the warm cache"),
             ("RT-5 restore from the warm cache",)),
    "RT-6": (READINESS_WORKFLOW, ("RT-6 corrupted restored file", "RT-6 asset with the wrong digest",
                                  "RT-6 classify"), ("RT-6 classify",)),
    "RT-7": (READINESS_WORKFLOW, ("RT-7 probe infra", "RT-7 probe science", "RT-7 classify"), ("RT-7 classify",)),
    "RT-8": (READINESS_WORKFLOW, ("RT-8 storage, retention and billing",), ("RT-8 storage, retention and billing",)),
    "RT-9": (READINESS_WORKFLOW, ("RT-9 billing guard",), ("RT-9 billing guard",)),
    "RT-10": (READINESS_WORKFLOW, ("RT-10 probe", "RT-10 classify"), ("RT-10 classify",)),
    "RT-11": (READINESS_WORKFLOW, ("RT-11 engine data path",), ("RT-11 engine data path",)),
}
RUN_TESTS = tuple(TESTS)
ALL_TESTS = ("RT-0", *RUN_TESTS)

# The order the Owner is asked to dispatch them in: RT-1 publishes the snapshot every later test reads, RT-8's
# second billing reading comes after RT-7 (review section 4), and RT-9 checks a ledger that already holds runs.
DISPATCH_ORDER = ("RT-1", "RT-2", "RT-3", "RT-4", "RT-5", "RT-6", "RT-7", "RT-10", "RT-11", "RT-9", "RT-8")
NEEDS_SNAPSHOT = frozenset(RUN_TESTS) - {"RT-1", "RT-9", "RT-10"}

# Expected billed minutes per run (review section 4, refined per job: every job bills at least one minute).
EXPECTED = {"RT-1": 38, "RT-2": 30, "RT-3": 4, "RT-4": 22, "RT-5": 9, "RT-6": 6, "RT-7": 5, "RT-8": 2,
            "RT-9": 2, "RT-10": 5, "RT-11": 24}

RT10_TIMEOUT = JOBS[READINESS_WORKFLOW]["RT-10 probe"]

# How a job ends when it works as designed. The probes exist to fail or to run out of time; every other job,
# the gate and each verdict job included, succeeds.
DESIGNED_END = {"RT-6 corrupted restored file": "failure", "RT-6 asset with the wrong digest": "failure",
                "RT-7 probe infra": "failure", "RT-7 probe science": "failure", "RT-10 probe": "cancelled"}


def workflow_of(test: str) -> str:
    return TESTS[test][0]


def timeout_of(workflow: str, job: str) -> int | None:
    return JOBS.get(workflow, {}).get(job)


def designed_end(job: str) -> str:
    return DESIGNED_END.get(job, "success")


def planned_max(test: str) -> int:
    """The most a run of ``test`` can bill: every job it runs, the gate included, at timeout + 1."""
    wf, jobs, _verdict = TESTS[test]
    return sum(JOBS[wf][j] + 1 for j in (GATE_JOB, *jobs))


def table() -> list[dict]:
    return [{"test": t, "workflow": wf, "jobs": {j: JOBS[wf][j] for j in (GATE_JOB, *jobs)},
             "verdict": list(verdict), "planned_max": planned_max(t), "expected": EXPECTED[t]}
            for t, (wf, jobs, verdict) in TESTS.items()]


def totals() -> dict:
    return {"planned_max": sum(planned_max(t) for t in RUN_TESTS), "expected": sum(EXPECTED.values()),
            "cap": READINESS_CAP}
