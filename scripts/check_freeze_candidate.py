#!/usr/bin/env python3
"""The CI gate a T0 freeze candidate must pass before the Owner may merge it.

    scripts/check_freeze_candidate.py --base origin/main --head HEAD

Contract section 6. A freeze candidate may change EXACTLY TWO FILES and EXACTLY
SEVEN REGISTRY VALUES. That is not a stylistic preference: it is what makes the
equivalence proof total and reviewable in one line, because ``git diff
--name-only M1 M2`` must equal exactly that pair. A freeze that also touched a
test, a doc or a line of code would be a cohort whose declared source commit and
whose actual runtime differ in ways no diff of two files could show.

This gate is a **no-op on every branch that does not touch the registry**, and
that matters: a gate that fired on ordinary work would be disabled within a
week. It wakes up only when ``forward_paper_cohort_registry.json`` moved, and
then it insists on the whole transaction at once.

It also runs on a registry change that is NOT a freeze — a closure, a class-O
binding — and says so rather than failing. What it refuses is a change that
*half* looks like a freeze, because a partially applied T0 is the one state from
which nothing can be unwound.

Exit codes: 0 the diff is lawful (or irrelevant); 2 it is not.

PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for _extra in (str(REPO_ROOT / "research"), str(REPO_ROOT / "scripts")):
    if _extra not in sys.path:
        sys.path.insert(0, _extra)

from fp import registry_law as fp_law  # noqa: E402
from fp import semantic_identity as fp_semantic  # noqa: E402

REGISTRY_PATH = "research/fp/records/forward_paper_cohort_registry.json"
MANIFEST_PATH = "MANIFEST.txt"

NOT_A_FREEZE = "NOT_A_FREEZE"
FREEZE_CANDIDATE = "FREEZE_CANDIDATE"

# The seven values, and nothing else, contract section 6.
FROZEN_ROW_FIELDS = ("t0_utc", "cohort_id", "status", "change_log")
FROZEN_IDENTITY_FIELDS = ("source_commit",)
FROZEN_REGISTRY_FIELDS = ("fp_run_active", "registry_updated_utc")


class CandidateRefused(Exception):
    pass


def _git(args: list[str], *, check: bool = True, repo_root: Path | None = None) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_root or REPO_ROOT), *args],
        capture_output=True, text=True, timeout=300,
    )
    if check and result.returncode != 0:
        raise CandidateRefused(f"git {' '.join(args)} failed: {result.stderr.strip()[:300]}")
    return result.stdout


def _registry_at(rev: str, repo_root: Path | None = None) -> dict:
    return json.loads(_git(["show", f"{rev}:{REGISTRY_PATH}"], repo_root=repo_root))


def _row(registry: dict, role: str) -> dict | None:
    return next((item for item in registry.get("instances") or [] if item.get("role") == role), None)


def _diff_object(before, after, prefix: str = "") -> list[str]:
    """Every leaf that moved between two JSON values, as dotted paths."""
    moved: list[str] = []
    if isinstance(before, dict) and isinstance(after, dict):
        for key in sorted(set(before) | set(after)):
            moved.extend(_diff_object(before.get(key), after.get(key), f"{prefix}{key}."))
        return moved
    if before != after:
        moved.append(prefix.rstrip("."))
    return moved


def check(base: str, head: str, *, repo_root: Path | None = None) -> dict:
    """Classify the diff and, if it is a freeze, insist on the whole transaction.

    ``repo_root`` exists so this gate can be run against a scratch repository in
    which a freeze — lawful and unlawful — can actually be committed. A gate
    whose only test is "it passed on a branch that changed nothing" is a gate
    nobody has exercised.
    """
    merge_base = _git(["merge-base", base, head], repo_root=repo_root).strip()
    changed = sorted(
        line for line in _git(["diff", "--name-only", merge_base, head],
                              repo_root=repo_root).splitlines() if line.strip()
    )

    if REGISTRY_PATH not in changed:
        return {
            "classification": NOT_A_FREEZE,
            "result": "PASS",
            "changed_files": changed,
            "detail": (
                f"{REGISTRY_PATH} is unchanged between {merge_base[:8]} and {head[:8]}; this branch "
                "is not a freeze candidate and this gate has nothing to say about it"
            ),
            "problems": [],
        }

    before = _registry_at(merge_base, repo_root)
    after = _registry_at(head, repo_root)
    problems: list[str] = []

    role_before = {item.get("role") for item in before.get("instances") or []}
    role_after = {item.get("role") for item in after.get("instances") or []}
    if role_before != role_after:
        problems.append(
            f"the set of declared roles changed from {sorted(role_before)} to {sorted(role_after)}"
        )

    # Which rows moved, and how?
    moved_rows: dict[str, list[str]] = {}
    for role in sorted(role_before & role_after):
        leaves = _diff_object(_row(before, role), _row(after, role))
        if leaves:
            moved_rows[role] = leaves
    header_leaves = [
        key for key in sorted(set(before) | set(after))
        if key != "instances" and before.get(key) != after.get(key)
    ]

    freezing = [
        role for role, leaves in moved_rows.items()
        if _row(before, role).get("status") == "NOT_STARTED"
        and _row(after, role).get("status") == "RUNNING"
    ]

    if not freezing:
        return {
            "classification": NOT_A_FREEZE,
            "result": "PASS",
            "changed_files": changed,
            "detail": (
                f"{REGISTRY_PATH} changed but no row went NOT_STARTED -> RUNNING, so this is not a "
                f"T0 freeze. Rows touched: {sorted(moved_rows)}; header fields: {header_leaves}. "
                "This gate governs the freeze transaction only; the schema, the registry-law tests "
                "and review govern everything else a registry change may do"
            ),
            "problems": [],
        }

    if len(freezing) > 1:
        problems.append(f"{len(freezing)} rows freeze at once: {freezing}; a T0 freezes one cohort")
    role = freezing[0]

    # -- exactly two files -------------------------------------------------
    if changed != sorted([MANIFEST_PATH, REGISTRY_PATH]):
        extra = [f for f in changed if f not in (MANIFEST_PATH, REGISTRY_PATH)]
        problems.append(
            f"a freeze candidate changes exactly [{MANIFEST_PATH}, {REGISTRY_PATH}]; this one also "
            f"changes {extra}. Two files is what makes the equivalence proof reviewable in one line"
        )

    # -- the other rows must be byte-identical ------------------------------
    for other in sorted(role_before & role_after):
        if other != role and other in moved_rows:
            problems.append(
                f"the {other} row is not byte-identical: {moved_rows[other][:5]}. A freeze touches "
                "one row; a closed cohort's record is history and never moves"
            )

    # -- exactly the seven values ------------------------------------------
    row_before, row_after = _row(before, role), _row(after, role)
    permitted_row = set(FROZEN_ROW_FIELDS) | {f"runtime_identity.{f}" for f in FROZEN_IDENTITY_FIELDS}
    actual_row = set()
    for leaf in moved_rows.get(role, []):
        if leaf.startswith("runtime_identity."):
            actual_row.add("runtime_identity." + leaf.split(".")[1])
        elif leaf.startswith("change_log"):
            actual_row.add("change_log")
        else:
            actual_row.add(leaf.split(".")[0])
    forbidden = sorted(actual_row - permitted_row)
    if forbidden:
        problems.append(
            f"{role} changed fields a freeze may not touch: {forbidden}. The seven values are "
            f"{sorted(permitted_row)} plus {list(FROZEN_REGISTRY_FIELDS)}"
        )
    missing = sorted(permitted_row - actual_row)
    if missing:
        problems.append(
            f"{role} did not change {missing}; a freeze writes all seven values or none. A "
            "partially applied T0 is the one state from which nothing can be unwound"
        )

    forbidden_header = sorted(set(header_leaves) - set(FROZEN_REGISTRY_FIELDS))
    if forbidden_header:
        problems.append(f"the registry header changed {forbidden_header}, which a freeze may not touch")
    missing_header = sorted(set(FROZEN_REGISTRY_FIELDS) - set(header_leaves))
    if missing_header:
        problems.append(f"the registry header did not change {missing_header}")

    # -- the values themselves ---------------------------------------------
    if row_before.get("t0_utc") is not None or row_after.get("t0_utc") is None:
        problems.append(
            f"t0_utc went {row_before.get('t0_utc')!r} -> {row_after.get('t0_utc')!r}; a freeze "
            "writes a T0 onto a row that had none"
        )
    elif row_after.get("cohort_id") != fp_law.cohort_id_for(role, row_after["t0_utc"]):
        problems.append(
            f"cohort_id {row_after.get('cohort_id')!r} is not what t0_utc {row_after['t0_utc']} "
            f"derives ({fp_law.cohort_id_for(role, row_after['t0_utc'])})"
        )
    if after.get("fp_run_active") is not True or before.get("fp_run_active") is not False:
        problems.append(
            f"fp_run_active went {before.get('fp_run_active')!r} -> {after.get('fp_run_active')!r}"
        )
    change_log = row_after.get("change_log") or []
    if row_before.get("change_log") != []:
        problems.append("the change_log was not empty before the freeze")
    elif len(change_log) != 1 or change_log[0].get("class") != "O":
        problems.append(
            f"the freeze wrote {len(change_log)} change_log entr(y/ies) of class "
            f"{[e.get('class') for e in change_log]}; it writes exactly one, class O"
        )

    problems.extend(fp_law.check_registry(after))

    # -- M1 and M2 must run the same system --------------------------------
    declared = (row_after.get("runtime_identity") or {}).get("source_commit")
    if not declared:
        problems.append(f"{role} declares no source_commit after the freeze")
    else:
        equivalence = fp_semantic.compare(declared, head, role, repo_root=repo_root)
        if equivalence["result"] != fp_semantic.EQUIVALENT:
            problems.append(
                f"SEMANTIC_IDENTITY({declared[:8]}) is not SEMANTIC_IDENTITY({head[:8]}): "
                f"{equivalence['result']} — {equivalence['detail']}"
            )

    return {
        "classification": FREEZE_CANDIDATE,
        "result": "PASS" if not problems else "FAIL",
        "role": role,
        "changed_files": changed,
        "t0_utc": row_after.get("t0_utc"),
        "cohort_id": row_after.get("cohort_id"),
        "declared_source_commit": declared,
        "detail": (
            f"{role} freezes T0 at {row_after.get('t0_utc')} as cohort {row_after.get('cohort_id')}"
        ),
        "problems": problems,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        report = check(args.base, args.head)
    except CandidateRefused as exc:
        print(f"FREEZE_CANDIDATE_REFUSED: {exc}", file=sys.stderr)
        return 2

    if args.json:
        sys.stdout.write(json.dumps(report, indent=2) + "\n")
    else:
        print(f"FREEZE_CANDIDATE_GATE — {report['classification']}")
        print(f"  {report['detail']}")
        for problem in report["problems"]:
            print(f"  [FAIL] {problem}")
        print()
        print(f"FREEZE_CANDIDATE = {report['result']}")

    return 0 if report["result"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
