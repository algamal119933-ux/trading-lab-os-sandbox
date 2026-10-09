#!/usr/bin/env python3
"""The CEA-1 merge law: may this PR be merged by the platform without the Owner?

docs/governance/CONTINUOUS_EXECUTION_AUTHORITY_1.md §4. The verdict is one of

    AUTO_ELIGIBLE         every condition holds; the platform may merge it
    OWNER_MERGE_REQUIRED  lawful work, but not auto-mergeable (protected path,
                          auto-merge inactive, outside a charter, not current...)
    REFUSED               an integrity condition failed (SUSPENDED, a ledger
                          rewrite, a non-merge-commit method); fix it first

THE PR NEVER JUDGES ITSELF. Policy — the protected list, AUTONOMY_STATE,
ACTIVATION, the charters, and the trial-ledger verifier — is read from the
BASE revision only. From the HEAD this reads data: which paths changed, the
ledger bytes, and dependency files. It never imports or runs HEAD code; the
HEAD's own tests run in ci.yml. The workflow that calls it
(.github/workflows/merge-law.yml) runs on pull_request_target, so the copy of
this file that judges a PR is main's copy.

Exit codes: 0 AUTO_ELIGIBLE · 1 OWNER_MERGE_REQUIRED · 2 REFUSED.
While auto-merge is INACTIVE (CEA-1 §5) no PR can exit 0, by design.

PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cea_policy as cp  # noqa: E402

LEDGER = "research/records/trial_ledger.jsonl"
LEDGER_CODE = "research/trial_ledger.py"
_REQ_LINE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


@dataclass
class Policy:
    """Everything the law reads from BASE."""
    protected: list[tuple[str, bool]]
    autonomy: dict
    activation: dict
    charters: dict[str, dict]


@dataclass
class PullRequest:
    """Everything the law reads about the PR. All of it is data."""
    branch: str
    author: str | None
    changed_paths: list[str]
    base_is_current: bool
    merge_method: str = "merge"
    unresolved_threads: int = 0
    ledger_append_only: bool = True
    ledger_verifies: bool = True
    new_dependencies: list[str] = field(default_factory=list)


HARD = {"AUTONOMY_SUSPENDED", "LEDGER_NOT_APPEND_ONLY", "LEDGER_DOES_NOT_VERIFY", "MERGE_METHOD_NOT_MERGE_COMMIT"}


def evaluate(policy: Policy, pr: PullRequest) -> dict:
    """Pure: the verdict and every reason, in a stable order."""
    reasons: list[str] = []

    if policy.autonomy.get("state") != "ACTIVE":
        reasons.append("AUTONOMY_SUSPENDED")
    if pr.merge_method != "merge":
        reasons.append("MERGE_METHOD_NOT_MERGE_COMMIT")
    if not pr.ledger_append_only:
        reasons.append("LEDGER_NOT_APPEND_ONLY")
    if not pr.ledger_verifies:
        reasons.append("LEDGER_DOES_NOT_VERIFY")

    active, missing = cp.auto_merge_active(policy.activation, policy.autonomy)
    for flag in missing:
        if flag != "AUTONOMY_STATE":
            reasons.append(f"AUTO_MERGE_INACTIVE:{flag}")

    protected = sorted(p for p in pr.changed_paths if cp.is_protected(p, policy.protected))
    for path in protected:
        reasons.append(f"PROTECTED_PATH:{path}")

    executor = policy.activation.get("executor_identity")
    if not executor or pr.author != executor:
        reasons.append("AUTHOR_NOT_EXECUTOR")

    match = cp.CHARTER_BRANCH.match(pr.branch or "")
    charter = policy.charters.get(match["charter"]) if match else None
    if match is None:
        reasons.append("BRANCH_NOT_A_CHARTER_UNIT")
    elif charter is None:
        reasons.append(f"CHARTER_UNKNOWN:{match['charter']}")
    else:
        if charter.get("status") != "ACTIVE" or charter["id"] in policy.autonomy.get("revoked_programs", []):
            reasons.append(f"CHARTER_NOT_ACTIVE:{charter['id']}")
        unit = next((u for u in charter.get("units", []) if u["id"] == match["unit"]), None)
        if unit is None:
            reasons.append(f"UNIT_UNKNOWN:{match['unit']}")
        elif unit.get("merge_class") != "AUTO":
            reasons.append(f"UNIT_MERGE_CLASS_OWNER:{unit['id']}")
        scope = charter.get("scope", {}).get("paths", [])
        for path in pr.changed_paths:
            if path in cp.ALWAYS_ALLOWED or path in protected:
                continue
            if not any(cp.glob_match(g, path) for g in scope):
                reasons.append(f"OUTSIDE_CHARTER_SCOPE:{path}")
        allow = set(charter.get("deps", {}).get("allowlist", []))
        for dep in sorted(set(pr.new_dependencies) - allow):
            reasons.append(f"DEPENDENCY_NOT_ALLOWLISTED:{dep}")

    if not pr.base_is_current:
        reasons.append("BASE_NOT_CURRENT")
    if pr.unresolved_threads:
        reasons.append(f"UNRESOLVED_REVIEW_THREADS:{pr.unresolved_threads}")

    if any(r.split(":", 1)[0] in HARD for r in reasons):
        verdict = "REFUSED"
    elif reasons:
        verdict = "OWNER_MERGE_REQUIRED"
    else:
        verdict = "AUTO_ELIGIBLE"
    return {"verdict": verdict, "reasons": reasons, "auto_merge_active": active}


# -- reading the inputs from git ---------------------------------------------


def policy_at(repo: Path, base: str) -> Policy:
    return Policy(
        protected=cp.protected_at(repo, base),
        autonomy=cp.json_at(repo, base, cp.AUTONOMY_STATE) or {"state": "SUSPENDED"},
        activation=cp.json_at(repo, base, cp.ACTIVATION) or {},
        charters=cp.charters_at(repo, base),
    )


def _requirement_names(text: str | None) -> set[str]:
    names = set()
    for line in (text or "").splitlines():
        if line.lstrip().startswith(("#", "-")):
            continue
        m = _REQ_LINE.match(line)
        if m:
            names.add(m.group(1).lower().replace("_", "-"))
    return names


def new_dependencies(repo: Path, base: str, head: str, changed: list[str]) -> list[str]:
    added: set[str] = set()
    for path in changed:
        if re.search(r"(^|/)requirements[^/]*\.txt$", path):
            added |= _requirement_names(cp.read_at(repo, head, path)) - _requirement_names(cp.read_at(repo, base, path))
    return sorted(added)


def ledger_checks(repo: Path, base: str, head: str) -> tuple[bool, bool]:
    """(append_only, verifies): HEAD ledger bytes, BASE ledger code."""
    before = cp.read_at(repo, base, LEDGER) or ""
    after = cp.read_at(repo, head, LEDGER) or ""
    if before == after:
        return True, True
    if not after.startswith(before):
        return False, False
    code = cp.read_at(repo, base, LEDGER_CODE)
    if code is None:
        return True, False
    with tempfile.TemporaryDirectory() as tmp:
        mod_path = Path(tmp) / "base_trial_ledger.py"
        mod_path.write_text(code, encoding="utf-8")
        ledger_path = Path(tmp) / "trial_ledger.jsonl"
        ledger_path.write_text(after, encoding="utf-8")
        spec = importlib.util.spec_from_file_location("base_trial_ledger", mod_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules["base_trial_ledger"] = module
        spec.loader.exec_module(module)
        try:
            return True, module.TrialLedger(ledger_path).verify() == []
        finally:
            sys.modules.pop("base_trial_ledger", None)


def pull_request_at(repo: Path, base: str, head: str, branch: str, author: str | None,
                    main: str | None, merge_method: str, unresolved_threads: int) -> PullRequest:
    merge_base = cp.git(repo, "merge-base", base, head).strip()
    changed = sorted(p for p in cp.git(repo, "diff", "--name-only", merge_base, head).splitlines() if p.strip())
    current = subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", main or base, head])
    append_only, verifies = ledger_checks(repo, merge_base, head)
    return PullRequest(
        branch=branch, author=author, changed_paths=changed, base_is_current=current.returncode == 0,
        merge_method=merge_method, unresolved_threads=unresolved_threads,
        ledger_append_only=append_only, ledger_verifies=verifies,
        new_dependencies=new_dependencies(repo, merge_base, head, changed),
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=".", help="repository checkout (default: .)")
    ap.add_argument("--base", required=True, help="BASE revision: policy is read from here only")
    ap.add_argument("--head", required=True, help="HEAD revision: read as data only")
    ap.add_argument("--main", help="current main (default: --base) for the up-to-date check")
    ap.add_argument("--branch", help="PR head branch name (default: the current branch)")
    ap.add_argument("--author", help="PR author login")
    ap.add_argument("--merge-method", default="merge", choices=("merge", "squash", "rebase"))
    ap.add_argument("--unresolved-threads", type=int, default=0)
    ap.add_argument("--json", action="store_true", help="print JSON only")
    args = ap.parse_args(argv)

    repo = Path(args.repo).resolve()
    branch = args.branch or cp.git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()
    try:
        policy = policy_at(repo, args.base)
    except FileNotFoundError as exc:
        # No law on the base (the bootstrap PR that installs it): fail closed.
        print(f"MERGE_LAW_VERDICT = OWNER_MERGE_REQUIRED\n  - BASE_POLICY_ABSENT: {exc}")
        return 1
    pr = pull_request_at(repo, args.base, args.head, branch, args.author, args.main,
                         args.merge_method, args.unresolved_threads)
    result = evaluate(policy, pr)
    result.update({"base": args.base, "head": args.head, "branch": branch, "changed_paths": pr.changed_paths})
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"MERGE_LAW_VERDICT = {result['verdict']}")
        for reason in result["reasons"]:
            print(f"  - {reason}")
    return {"AUTO_ELIGIBLE": 0, "OWNER_MERGE_REQUIRED": 1, "REFUSED": 2}[result["verdict"]]


if __name__ == "__main__":
    sys.exit(main())
