#!/usr/bin/env python3
"""H1_P2_ENTRY_GATE: may H1 enter, given how P2 ended? Read from a git ref, never inferred.

    python3 research/paper/h1/launch/h1_p2_entry_gate.py [--ref origin/main] [--json out.json]

It prints exactly one verdict, and its exit code matches:

    H1_ENTRY_ELIGIBLE   0   P2 has an Owner-merged closure that admits H1 under
                            H1-P2-CONDITION-AMENDMENT-1
    H1_ENTRY_WAITING    10  P2 has no Owner-merged terminal closure yet
    H1_ENTRY_BLOCKED    20  anything else: CLOSED / FAIL, invalid evidence, a broken chain,
                            failed reconciliation, an unresolved defect, a safety failure,
                            an identity or hash mismatch, or a record it cannot read

Every input is read from the ref with ``git show``; nothing in the working tree counts:

- ``research/fp/records/forward_paper_cohort_registry.json``: the P2 rows;
- ``docs/p2/P2_CLOSURE.md``: the P2 stage closure record. Its machine block is
  described under CLOSURE_FIELDS. The record is "Owner-merged" only if a two-parent
  merge commit on the ref's first-parent history brought it in;
- ``research/fp/records/evidence_digest_publication.json``: the closed cohort's sealed
  archive must be published;
- ``research/paper/h1/package/PACKAGE_MANIFEST.sha256``: the frozen H1 package digest;
- ``research/paper/h1/amendments/H1_AMENDMENTS_G6.md``: G.2-a. Branch B (INCONCLUSIVE)
  is lawful only when this record, at its pinned sha256, reached the ref's first-parent
  history BEFORE the P2 closure record did.

It is fail-closed. A field that is missing, unknown or unparsable is BLOCKED, never
WAITING and never ELIGIBLE. It starts nothing and writes nothing except ``--json``.
PAPER / RESEARCH ONLY.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]

REGISTRY = "research/fp/records/forward_paper_cohort_registry.json"
CLOSURE = "docs/p2/P2_CLOSURE.md"
DIGESTS = "research/fp/records/evidence_digest_publication.json"
PACKAGE_MANIFEST = "research/paper/h1/package/PACKAGE_MANIFEST.sha256"
AMENDMENTS = "research/paper/h1/amendments/H1_AMENDMENTS_G6.md"

H1_PACKAGE_DIGEST = "ef9a3d0c5b5b9abe122faaa1bd4ef67feb0c3ec4437bed56cd6ef33d910bc43c"
G6_AMENDMENTS_SHA256 = "0575c3a2d780892ceaee28f703d7d73caa675a8a53d8409c0f084feb669252fd"

ELIGIBLE, WAITING, BLOCKED = "H1_ENTRY_ELIGIBLE", "H1_ENTRY_WAITING", "H1_ENTRY_BLOCKED"
EXIT = {ELIGIBLE: 0, WAITING: 10, BLOCKED: 20}

PASS_STATUS = "CLOSED / PASS"
FAIL_STATUS = "CLOSED / FAIL"
INCONCLUSIVE_STATUS = "INCONCLUSIVE / INSUFFICIENT"

# The machine block the P2 closure record must carry: one ``KEY = VALUE`` line per field,
# inside a fenced block. The value each field needs for H1 entry follows the colon. Both
# admitting branches need every one of them. CLOSED / PASS asks at least this much
# (P2_CONTRACT §12), and branch B of G.2-a asks exactly this.
CLOSURE_FIELDS = {
    "P2_TERMINAL_STATUS": (PASS_STATUS, INCONCLUSIVE_STATUS, FAIL_STATUS),
    "COHORT_ID": None,
    "EVIDENCE_VALID": ("YES",),
    "EVIDENCE_CHAINS": ("INTACT",),
    "RECONCILIATION": ("PASS",),
    "UNRESOLVED_INTEGRITY_DEFECTS": ("NONE",),
    "UNRESOLVED_TECHNICAL_DEFECTS": ("NONE",),
    "SAFETY_FAILURES": ("NONE",),
    "REAL_MONEY_AUTHORIZED": ("NO",),
}
FIELD_LINE = re.compile(r"^\s*([A-Z0-9_]+)\s*=\s*(.+?)\s*$")


def git(*args: str, repo: Path = REPO) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def show(ref: str, path: str, repo: Path = REPO) -> bytes | None:
    result = subprocess.run(["git", "-C", str(repo), "show", f"{ref}:{path}"], capture_output=True)
    return result.stdout if result.returncode == 0 else None


def first_parent_merge_introducing(ref: str, path: str, repo: Path = REPO) -> str | None:
    """The oldest two-parent merge on ref's first-parent line whose first-parent diff adds or changes path."""
    out = git("log", "--first-parent", "--merges", "--format=%H", "--reverse", ref, "--", path, repo=repo)
    if out.returncode != 0:
        return None
    for commit in out.stdout.split():
        parents = git("rev-list", "--parents", "-n", "1", commit, repo=repo).stdout.split()
        if len(parents) == 3:
            return commit
    return None


def last_first_parent_change(ref: str, path: str, repo: Path = REPO) -> str | None:
    out = git("log", "--first-parent", "-n", "1", "--format=%H", ref, "--", path, repo=repo)
    return out.stdout.strip() or None


def is_ancestor(a: str, b: str, repo: Path = REPO) -> bool:
    return git("merge-base", "--is-ancestor", a, b, repo=repo).returncode == 0


def parse_closure(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    in_fence = False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        match = FIELD_LINE.match(line) if in_fence else None
        if match and match.group(1) in CLOSURE_FIELDS:
            if match.group(1) in fields and fields[match.group(1)] != match.group(2):
                fields[match.group(1)] = "<CONFLICTING>"
            else:
                fields[match.group(1)] = match.group(2)
    return fields


def evaluate(ref: str = "origin/main", repo: Path = REPO) -> dict:
    reasons: list[str] = []
    out = {"gate": "H1_P2_ENTRY_GATE", "ref": ref, "reasons": reasons}
    resolved = git("rev-parse", "--verify", f"{ref}^{{commit}}", repo=repo)
    if resolved.returncode != 0:
        reasons.append(f"ref {ref} does not resolve")
        return {**out, "verdict": BLOCKED}
    out["ref_commit"] = resolved.stdout.strip()

    # Identity first: a moved package or a moved amendment blocks whatever P2 did.
    manifest = show(ref, PACKAGE_MANIFEST, repo)
    out["h1_package_digest"] = hashlib.sha256(manifest).hexdigest() if manifest else None
    if out["h1_package_digest"] != H1_PACKAGE_DIGEST:
        reasons.append(f"H1 package digest {out['h1_package_digest']} != frozen {H1_PACKAGE_DIGEST}")

    raw_registry = show(ref, REGISTRY, repo)
    try:
        registry = json.loads(raw_registry) if raw_registry else None
    except json.JSONDecodeError:
        registry = None
    if registry is None:
        reasons.append("the cohort registry is missing or unreadable at the ref")
        return {**out, "verdict": BLOCKED}
    p2_rows = [r for r in registry.get("instances", []) if str(r.get("role", "")).startswith("FP-CONTROL-")]
    out["p2_rows"] = [{"role": r.get("role"), "cohort_id": r.get("cohort_id"), "status": r.get("status"),
                       "closed_utc": r.get("closed_utc")} for r in p2_rows]
    running = [r["cohort_id"] for r in p2_rows if r.get("status") != "CLOSED"]

    closure_raw = show(ref, CLOSURE, repo)
    if closure_raw is None:
        out["p2_terminal_status"] = "NOT_CLOSED"
        if reasons:
            return {**out, "verdict": BLOCKED}
        reasons.append(f"no P2 closure record at {CLOSURE}; P2 rows not closed: {running or 'none'}")
        return {**out, "verdict": WAITING}

    closure_merge = first_parent_merge_introducing(ref, CLOSURE, repo)
    out["p2_closure_sha256"] = hashlib.sha256(closure_raw).hexdigest()
    out["p2_closure_merge"] = closure_merge
    if closure_merge is None:
        reasons.append("the P2 closure record did not reach the ref through a two-parent merge (not Owner-merged)")
    elif last_first_parent_change(ref, CLOSURE, repo) != closure_merge:
        reasons.append("the P2 closure record changed after the merge that introduced it")

    fields = parse_closure(closure_raw.decode("utf-8", errors="replace"))
    out["closure_fields"] = fields
    for key, allowed in CLOSURE_FIELDS.items():
        value = fields.get(key)
        if value is None:
            reasons.append(f"closure field {key} is missing")
        elif value == "<CONFLICTING>":
            reasons.append(f"closure field {key} is given twice with different values")
        elif key == "P2_TERMINAL_STATUS" and value not in allowed:
            reasons.append(f"P2_TERMINAL_STATUS {value!r} is not a P2 terminal state")
        elif key != "P2_TERMINAL_STATUS" and allowed is not None and value not in allowed:
            reasons.append(f"closure field {key} = {value!r} (needs {allowed[0]})")
    status = fields.get("P2_TERMINAL_STATUS")
    out["p2_terminal_status"] = status
    if status == FAIL_STATUS:
        reasons.append("P2 CLOSED / FAIL blocks H1 (H1-P2-CONDITION-AMENDMENT-1)")

    cohort = fields.get("COHORT_ID")
    row = next((r for r in p2_rows if r.get("cohort_id") == cohort), None)
    if row is None:
        reasons.append(f"closure COHORT_ID {cohort!r} is not a P2 row in the registry")
    elif row.get("status") != "CLOSED" or not row.get("closed_utc"):
        reasons.append(f"registry row {cohort} is {row.get('status')}, not CLOSED with a closed_utc")
    if running:
        reasons.append(f"registry still shows P2 rows not closed: {running}")
    if registry.get("fp_run_active") is not False:
        reasons.append("registry fp_run_active is not false")
    if registry.get("real_money_authorized") is not False:
        reasons.append("registry real_money_authorized is not false")

    digests_raw = show(ref, DIGESTS, repo)
    try:
        archives = json.loads(digests_raw).get("archives", []) if digests_raw else []
    except json.JSONDecodeError:
        archives = []
    if not any(a.get("cohort_id") == cohort for a in archives):
        reasons.append(f"no published sealed archive for {cohort!r} in {DIGESTS}")

    if status == INCONCLUSIVE_STATUS:
        amendment = show(ref, AMENDMENTS, repo)
        amendment_sha = hashlib.sha256(amendment).hexdigest() if amendment else None
        out["g6_amendments_sha256"] = amendment_sha
        amendment_merge = first_parent_merge_introducing(ref, AMENDMENTS, repo)
        if amendment_sha != G6_AMENDMENTS_SHA256:
            reasons.append("branch B needs H1-P2-CONDITION-AMENDMENT-1 at its pinned sha256; it is absent or moved")
        elif amendment_merge is None:
            reasons.append("H1-P2-CONDITION-AMENDMENT-1 did not reach the ref through a two-parent merge")
        elif closure_merge is not None and (amendment_merge == closure_merge
                                            or not is_ancestor(amendment_merge, closure_merge, repo)):
            reasons.append("H1-P2-CONDITION-AMENDMENT-1 was not merged before the P2 closure record")

    return {**out, "verdict": BLOCKED if reasons else ELIGIBLE}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ref", default="origin/main")
    ap.add_argument("--json", type=Path)
    args = ap.parse_args(argv)
    result = evaluate(args.ref)
    if args.json:
        args.json.write_text(json.dumps(result, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    for reason in result["reasons"]:
        print(f"  - {reason}", file=sys.stderr)
    print(f"P2_TERMINAL_STATUS = {result.get('p2_terminal_status')}")
    print(result["verdict"])
    return EXIT[result["verdict"]]


if __name__ == "__main__":
    sys.exit(main())
