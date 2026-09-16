"""Registry invariants the JSON schema cannot express, checked in one place.

The schema already enforces a great deal: a RUNNING row must carry a T0, a
cohort id and a 40-hex source commit; a NOT_STARTED row must carry none of
them; an outcome belongs only to a CLOSED row. What a per-row schema cannot say
is how rows relate to each other and to the registry header:

* ``fp_run_active`` is a registry-level flag and every row is a separate object,
  so the schema can never notice a registry that says no run is active while a
  row says RUNNING. That flag is what a reader consults to answer "is a cohort
  live right now?", and a flag that can disagree with the rows it summarises is
  worse than no flag at all.
* ``cohort_id`` is *derived* from role and T0 by a stated rule. The schema can
  require a non-empty string; it cannot require the right one, so a cohort id
  that names a different instant than the T0 beside it would validate.
* At most one row may be RUNNING. Two live cohorts would share one lane path,
  because the role enum is closed and each role declares one ``evidence_dir``.

So the correspondence between RUNNING, T0, the cohort id, the source commit and
``fp_run_active`` lives here, as executable law rather than as prose. The freeze
tool checks it against what it is about to write, the CI freeze-candidate gate
checks it against the candidate, and the test suite checks it against the
committed registry — one rule, three consumers, no restatement.

Every function returns a list of violations. Empty means lawful. Nothing here
repairs anything: a registry that has to be corrected to pass is a registry
whose correction is the evidence.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
COHORT_REGISTRY = REPO_ROOT / "research" / "fp" / "records" / "forward_paper_cohort_registry.json"

T0_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")

STARTED_STATUSES = ("RUNNING", "PAUSED", "CLOSED")


def cohort_id_for(role: str, t0_utc: str) -> str:
    """The one lawful cohort id for a (role, T0) pair.

    ``role + "-" + t0_utc`` with ``:`` and ``-`` removed. The precedent is
    FP-CONTROL-1's own frozen id — ``2026-09-08T12:15:13Z`` became
    ``FP-CONTROL-1-20260908T121513Z`` — and it is already an executable
    expectation in tests/test_fp_admission.py. Stated as a function so the
    freeze writes what the gate checks, rather than two hand-written strings
    that agree until one of them is edited.
    """
    return f"{role}-{t0_utc.replace(':', '').replace('-', '')}"


def check_row(row: dict) -> list[str]:
    """Correspondence between one row's status, T0, cohort id and commit."""
    problems: list[str] = []
    role = row.get("role")
    status = row.get("status")
    t0 = row.get("t0_utc")
    cohort = row.get("cohort_id")
    identity = row.get("runtime_identity") or {}
    commit = identity.get("source_commit")

    if status in STARTED_STATUSES:
        if not isinstance(t0, str) or not T0_PATTERN.match(t0):
            problems.append(f"{role} is {status} but carries t0_utc {t0!r}, which is not a frozen instant")
            # Without a well-formed T0 there is no lawful cohort id to derive,
            # so the derivation is not attempted: a second complaint computed
            # from the first one's bad input is noise, not a finding.
            return problems
        if not isinstance(cohort, str) or not cohort:
            problems.append(f"{role} is {status} but carries no cohort_id")
        else:
            expected = cohort_id_for(role, t0)
            if cohort != expected:
                problems.append(
                    f"{role}.cohort_id is {cohort!r} but its t0_utc {t0} derives {expected!r}; "
                    "a cohort id that names a different instant than its own T0 makes the two "
                    "unfalsifiable against each other"
                )
        if not isinstance(commit, str) or not COMMIT_PATTERN.match(commit or ""):
            problems.append(
                f"{role} is {status} but its runtime_identity.source_commit is {commit!r}, "
                "not a 40-hex commit id"
            )
    elif status == "NOT_STARTED":
        for field, value in (("t0_utc", t0), ("cohort_id", cohort), ("source_commit", commit)):
            if value is not None:
                problems.append(
                    f"{role} is NOT_STARTED but carries {field}={value!r}; a row that has started "
                    "nothing may not hold the identity of a run that never happened"
                )
    else:
        problems.append(f"{role} declares status {status!r}, which is not a status the registry admits")
    return problems


def check_registry(registry: dict) -> list[str]:
    """Every cross-row and header invariant. Empty list means lawful."""
    problems: list[str] = []
    instances = registry.get("instances")
    if not isinstance(instances, list):
        return ["the registry declares no instances array"]

    roles = [row.get("role") for row in instances]
    duplicates = sorted({role for role in roles if roles.count(role) > 1})
    if duplicates:
        problems.append(f"roles declared more than once: {duplicates}")

    for row in instances:
        problems.extend(check_row(row))

    running = [row.get("role") for row in instances if row.get("status") == "RUNNING"]
    if len(running) > 1:
        problems.append(
            f"{len(running)} rows are RUNNING ({running}); the role enum is closed and each role "
            "declares one evidence_dir, so two live cohorts would share one lane"
        )

    active = registry.get("fp_run_active")
    if not isinstance(active, bool):
        problems.append(f"fp_run_active is {active!r}, not a boolean")
    elif active and not running:
        problems.append(
            "fp_run_active is true but no row is RUNNING; the flag a reader consults to ask "
            "whether a cohort is live disagrees with the rows it summarises"
        )
    elif running and not active:
        problems.append(
            f"{running[0]} is RUNNING but fp_run_active is false; the same disagreement, the other way"
        )

    if registry.get("real_money_authorized") is not False:
        problems.append(
            f"real_money_authorized is {registry.get('real_money_authorized')!r}; this project is "
            "PAPER / RESEARCH ONLY and the value is false, always"
        )

    # Lane paths must not be shared between rows. resolve_lane refuses a path
    # outside canonical user_data, and path exclusivity refuses a runtime about
    # to write into another instance's paths — but neither is consulted when a
    # registry is merely being read, and two rows declaring one evidence_dir is
    # a commingling hazard that should be visible in the registry itself.
    declared: dict[str, list[str]] = {}
    for row in instances:
        identity = row.get("runtime_identity") or {}
        for field in ("db_path", "log_path", "evidence_dir"):
            value = identity.get(field)
            if value:
                declared.setdefault(str(value), []).append(f"{row.get('role')}.{field}")
    for path, owners in sorted(declared.items()):
        if len(owners) > 1:
            problems.append(f"{path} is declared by more than one row: {owners}")

    return problems


def load_registry(path: Path | None = None) -> dict:
    return json.loads(Path(path or COHORT_REGISTRY).read_text(encoding="utf-8"))
