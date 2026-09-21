#!/usr/bin/env python3
"""The T0 authority boundary, in whichever state it is in.

T0 authority is a merged record, not a token. This gate proves the boundary
holds in both of its lawful states, and it fails closed on the one state that is
not lawful: a T0 in the registry that no audited freeze transaction wrote.

    ABSENT   no docs/p2/OWNER_T0_AUTHORIZATION.md at HEAD. The default, and the
             default is refusal — freeze_t0 cannot run at all.
    GRANTED  the file is there, and must then be what freeze_t0 will read: it
             parses, names this role, and names the same qualification run the
             merged S3b binding pins, forbids real money, carries an unexpired
             expiry, and its Mq is in this history.

WHY THIS IS A SCRIPT, AND WHY IT LIVES HERE. It began as inline Python in
.github/workflows/ci.yml, where nothing could import it and the test suite could
not reach it. It then did exactly what it was written to prevent someone else
doing: it asserted that the registry at HEAD carries no T0 — true every day
until the Owner lawfully froze one, and false on the very commit the whole stage
exists to produce. A lawful freeze could not pass CI. As a module it is covered
by tests/test_p2_t0_authority_gate.py like every other authority-bearing
mechanism here, and a freeze rehearsal exercises it automatically.

It is NOT under scripts/. Contract section 5 puts ``scripts/*.py`` inside
RUNTIME_TREE, so a new module there changes SEMANTIC_IDENTITY and breaks the
required SEMANTIC_IDENTITY(Mq) == SEMANTIC_IDENTITY(M1) — freeze_t0 refuses, and
rightly: between the qualification run and the freeze, nothing that can change
what the runtime does may move. This gate cannot change what the runtime does.
It reads git and answers a question about authority, runs only in CI and in the
suite, and is never imported by the runtime. Living beside the workflow that
calls it states that, and keeps the equivalence proof exactly as strict as it
was rather than widening the model to fit a convenience.

AUTHORITY PERMITS A FREEZE; IT IS NEVER ITSELF A FREEZE. That claim still holds
and is still checked — but "is this branch the freeze?" is a question with an
existing answer, and it is asked of scripts/check_freeze_candidate.py rather
than re-derived here. Where that gate classifies the branch a FREEZE_CANDIDATE,
the registry's T0 is the audited transaction and this gate defers to it. Two
checkers disagreeing about what a freeze looks like would be worse than one.

Exit codes: 0 the boundary holds; 2 it does not.

PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for _extra in (REPO_ROOT / "scripts", REPO_ROOT / "research"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

import check_freeze_candidate as freeze_gate  # noqa: E402
import freeze_t0  # noqa: E402

ROLE = "FP-CONTROL-2"
ABSENT, GRANTED = "ABSENT", "GRANTED"


def _git(args: list[str], *, repo_root: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo_root or REPO_ROOT), *args],
        capture_output=True, text=True, timeout=300,
    )


def _registry_at(rev: str, repo_root: Path | None = None) -> dict:
    result = _git(["show", f"{rev}:{freeze_t0.REGISTRY_PATH}"], repo_root=repo_root)
    if result.returncode != 0:
        raise RuntimeError(f"{freeze_t0.REGISTRY_PATH} is not readable at {rev}")
    return json.loads(result.stdout)


def _is_freeze_candidate(base: str | None, head: str, repo_root: Path | None) -> tuple[bool, str]:
    """Ask the freeze gate whether this branch is the freeze transaction."""
    if not base:
        return False, "no base reference, so the freeze gate has nothing to compare against"
    try:
        report = freeze_gate.check(base, head, repo_root=repo_root)
    except Exception as exc:  # a gate that cannot answer has not answered favourably
        return False, f"the freeze gate could not classify this branch: {exc}"
    return (
        report["classification"] == freeze_gate.FREEZE_CANDIDATE,
        report["detail"],
    )


def check(head: str = "HEAD", *, base: str | None = None,
          repo_root: Path | None = None, role: str = ROLE) -> dict:
    """The boundary, as it stands at ``head``."""
    root = repo_root or REPO_ROOT
    resolved = _git(["rev-parse", head], repo_root=root).stdout.strip() or head
    problems: list[str] = []
    notes: list[str] = []

    # -- the authorization itself -----------------------------------------
    previous_root = freeze_t0.REPO_ROOT
    freeze_t0.REPO_ROOT = root
    try:
        granted = freeze_t0.read_authorization(resolved)
        state = GRANTED
    except freeze_t0.FreezeRefused as exc:
        granted, state = None, ABSENT
        notes.append(str(exc))
    finally:
        freeze_t0.REPO_ROOT = previous_root

    if granted is not None:
        try:
            binding = json.loads(
                _git(["show", f"{resolved}:{freeze_t0.BINDING_PATH}"], repo_root=root).stdout
            )
        except json.JSONDecodeError:
            binding = {}
            problems.append(f"{freeze_t0.BINDING_PATH} is not readable at {resolved[:8]}; an "
                            "authorization naming a certificate with nothing to check it against "
                            "is a hash compared to nothing")
        if binding:
            if granted["ROLE"] != binding.get("role"):
                problems.append(f"the authorization names role {granted['ROLE']!r} but the merged "
                                f"binding is for {binding.get('role')!r}")
            if granted["QUALIFICATION_COMMIT"] != binding.get("qualification_commit"):
                problems.append("the authorization names a qualification commit the merged binding "
                                "does not record")
            if granted["QUALIFICATION_CERTIFICATE_SHA256"] != binding.get("certificate_sha256"):
                problems.append("the authorization names a certificate the merged binding does not "
                                "pin; the Owner authorized a different qualification run")
        if granted["REAL_MONEY_AUTHORIZED"].strip().upper() != "NO":
            problems.append("the authorization does not declare REAL_MONEY_AUTHORIZED = NO")
        try:
            freeze_t0._parse_utc(granted["EXPIRES_UTC"], "EXPIRES_UTC")
        except freeze_t0.FreezeRefused as exc:
            problems.append(str(exc))
        if _git(["merge-base", "--is-ancestor", granted["QUALIFICATION_COMMIT"], resolved],
                repo_root=root).returncode != 0:
            problems.append("the qualification commit the authorization names is not an ancestor "
                            "of this head")

    # -- authority permits a freeze; it is never itself a freeze ----------
    #
    # The claim is about what THIS BRANCH DID, not about what the registry
    # happens to hold. Once the Owner has merged a freeze, every later branch
    # carries that T0 — it is history, and it was audited when it was written.
    # An earlier version of this gate failed on "carries a T0 and is not a
    # freeze candidate", which is every commit after the freeze forever: the
    # same mistake, one level along, of reading a state as an act.
    registry = _registry_at(resolved, root)
    row = next((r for r in registry["instances"] if r.get("role") == role), None)
    if row is None:
        problems.append(f"the registry declares no {role} row")
        row = {}
    frozen_here, detail = _is_freeze_candidate(base, resolved, root)
    carries_t0 = bool(row.get("t0_utc") or row.get("cohort_id")) or row.get("status") == "RUNNING"

    # A T0 is written by t0_utc and cohort_id appearing, and by a row entering
    # RUNNING. A row LEAVING RUNNING for CLOSED is a lawful cohort closure -
    # FP-CONTROL-1's own closure was exactly that - and refusing it would make
    # this gate forbid the disposition contract section 11 class B requires.
    FROZEN_FIELDS = ("t0_utc", "cohort_id")
    if base:
        try:
            base_registry = _registry_at(
                _git(["merge-base", base, resolved], repo_root=root).stdout.strip() or base, root)
            base_row = next(
                (r for r in base_registry["instances"] if r.get("role") == role), {})
        except Exception as exc:
            base_row = None
            problems.append(f"the registry at {base} could not be read ({exc}); whether this "
                            "branch introduced a T0 cannot be established, and a question that "
                            "could not be answered has not been answered favourably")
    else:
        base_row = None

    if base_row is None and carries_t0 and not problems:
        problems.append(
            f"{role} carries t0={row.get('t0_utc')!r} and there is no base to compare against, "
            "so whether this branch introduced it cannot be established. Fail closed"
        )
    elif base_row is not None:
        introduced = {f: (base_row.get(f), row.get(f))
                      for f in FROZEN_FIELDS if base_row.get(f) != row.get(f)}
        if row.get("status") == "RUNNING" and base_row.get("status") != "RUNNING":
            introduced["status"] = (base_row.get("status"), row.get("status"))
        before_sc = (base_row.get("runtime_identity") or {}).get("source_commit")
        after_sc = (row.get("runtime_identity") or {}).get("source_commit")
        if before_sc != after_sc:
            introduced["source_commit"] = (before_sc, after_sc)
        if introduced and not frozen_here:
            problems.append(
                f"{role} moves {sorted(introduced)} on this branch "
                f"({introduced}), and this branch is not a freeze candidate: {detail}. A T0 "
                "written outside the audited freeze transaction is a cohort nobody reviewed"
            )
        elif introduced:
            notes.append("the registry's T0 is this branch's own freeze transaction, which "
                         "scripts/check_freeze_candidate.py audits; this gate defers to it")
        elif carries_t0:
            notes.append(f"{role} carries t0={row.get('t0_utc')} from history, unchanged by this "
                         "branch; the transaction that wrote it was audited when it was written")

    return {
        "authority": state,
        "head": resolved,
        "role": role,
        "authorization": granted,
        "t0_frozen_at_head": carries_t0,
        "is_freeze_candidate": frozen_here,
        "notes": notes,
        "problems": problems,
        "result": "PASS" if not problems else "FAIL",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--head", default="HEAD")
    parser.add_argument(
        "--base", default=None,
        help="the reference this branch is measured against, so a lawful freeze can be "
             "recognised as one. Omitted, no branch is treated as a freeze candidate, which "
             "is the conservative reading",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = check(args.head, base=args.base)

    if args.json:
        sys.stdout.write(json.dumps(report, indent=2) + "\n")
        return 0 if report["result"] == "PASS" else 2

    if report["authority"] == GRANTED:
        granted = report["authorization"]
        print(f"T0_AUTHORITY = GRANTED — role {granted['ROLE']}, qualification "
              f"{granted['QUALIFICATION_COMMIT'][:8]}, certificate "
              f"{granted['QUALIFICATION_CERTIFICATE_SHA256'][:12]}, expires "
              f"{granted['EXPIRES_UTC']}")
    else:
        print(f"T0_AUTHORITY = ABSENT — {report['notes'][0] if report['notes'] else ''}")
    for note in report["notes"][1:] if report["authority"] == ABSENT else report["notes"]:
        print(f"  {note}")
    if not report["t0_frozen_at_head"]:
        state = "NO"
    elif report["is_freeze_candidate"]:
        state = "YES (this branch's own freeze candidate)"
    else:
        state = "YES (from history, unchanged by this branch)"
    print(f"T0_FROZEN_AT_HEAD = {state}")
    for problem in report["problems"]:
        print(f"::error::{problem}")
    print(f"T0_AUTHORITY_GATE = {report['result']}")
    return 0 if report["result"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
