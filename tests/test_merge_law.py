"""CEA-1 §4/§5: the merge law, one test per refusal, and the inactive default.

PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import cea_policy as cp
import merge_law as ml

REPO_ROOT = Path(__file__).resolve().parents[1]
CHARTER = "COMMERCIAL-VERIFICATION-LANE-1"
EXECUTOR = "tlos-executor"


def policy(**over) -> ml.Policy:
    p = ml.Policy(
        protected=cp.parse_protected((REPO_ROOT / cp.PROTECTED_PATHS).read_text(encoding="utf-8")),
        autonomy={"state": "ACTIVE", "revoked_programs": []},
        activation={"platform_enforcement": True, "executor_identity": EXECUTOR,
                    "executor_proven": True, "p2_closed": True},
        charters=cp.charters_at(REPO_ROOT, None),
    )
    for k, v in over.items():
        setattr(p, k, v)
    return p


def pr(**over) -> ml.PullRequest:
    base = dict(branch=f"auto/{CHARTER}/CV-01", author=EXECUTOR,
                changed_paths=["verification/sample/report.md", "tests/test_verification_sample.py",
                               "MANIFEST.txt"],
                base_is_current=True)
    base.update(over)
    return ml.PullRequest(**base)


def test_a_clean_routine_pr_is_auto_eligible_when_every_condition_holds():
    result = ml.evaluate(policy(), pr())
    assert result == {"verdict": "AUTO_ELIGIBLE", "reasons": [], "auto_merge_active": True}


def test_todays_activation_record_never_allows_auto_merge():
    activation = json.loads((REPO_ROOT / cp.ACTIVATION).read_text(encoding="utf-8"))
    autonomy = json.loads((REPO_ROOT / cp.AUTONOMY_STATE).read_text(encoding="utf-8"))
    assert activation == {"platform_enforcement": False, "executor_identity": None,
                          "executor_proven": False, "p2_closed": False}
    result = ml.evaluate(policy(activation=activation, autonomy=autonomy), pr())
    assert result["verdict"] == "OWNER_MERGE_REQUIRED"
    assert result["auto_merge_active"] is False
    for flag in cp.ACTIVATION_FLAGS:
        assert f"AUTO_MERGE_INACTIVE:{flag}" in result["reasons"]


@pytest.mark.parametrize("flag", cp.ACTIVATION_FLAGS)
def test_each_activation_flag_alone_blocks_auto_merge(flag):
    p = policy()
    p.activation = dict(p.activation, **{flag: False if flag != "executor_identity" else None})
    result = ml.evaluate(p, pr(author=None if flag == "executor_identity" else EXECUTOR))
    assert result["verdict"] == "OWNER_MERGE_REQUIRED"
    assert f"AUTO_MERGE_INACTIVE:{flag}" in result["reasons"]


@pytest.mark.parametrize("path", [
    "CLAUDE.md", ".github/gates/protected_paths.txt", ".github/gates/AUTONOMY_STATE.json",
    ".github/workflows/ci.yml", "pytest.ini", "tests/conftest.py", "research/cycle2/funnel.py",
    "research/trial_ledger.py", "charters/COMMERCIAL-VERIFICATION-LANE-1.json",
    "docs/governance/CONTINUOUS_EXECUTION_AUTHORITY_1.md", "tests/test_p2_scope_audit.py",
])
def test_a_protected_path_requires_the_owner(path):
    result = ml.evaluate(policy(), pr(changed_paths=["verification/x.py", path]))
    assert result["verdict"] == "OWNER_MERGE_REQUIRED"
    assert f"PROTECTED_PATH:{path}" in result["reasons"]


def test_suspended_refuses():
    result = ml.evaluate(policy(autonomy={"state": "SUSPENDED", "revoked_programs": []}), pr())
    assert result["verdict"] == "REFUSED"
    assert "AUTONOMY_SUSPENDED" in result["reasons"]


def test_a_revoked_charter_is_not_auto():
    result = ml.evaluate(policy(autonomy={"state": "ACTIVE", "revoked_programs": [CHARTER]}), pr())
    assert result["verdict"] == "OWNER_MERGE_REQUIRED"
    assert f"CHARTER_NOT_ACTIVE:{CHARTER}" in result["reasons"]


def test_a_path_outside_the_charter_scope_is_not_auto():
    result = ml.evaluate(policy(), pr(changed_paths=["verification/a.py", "research/summarize_backtest.py"]))
    assert result["verdict"] == "OWNER_MERGE_REQUIRED"
    assert "OUTSIDE_CHARTER_SCOPE:research/summarize_backtest.py" in result["reasons"]


def test_a_stale_base_is_not_auto():
    result = ml.evaluate(policy(), pr(base_is_current=False))
    assert "BASE_NOT_CURRENT" in result["reasons"] and result["verdict"] == "OWNER_MERGE_REQUIRED"


def test_a_non_executor_author_is_not_auto():
    result = ml.evaluate(policy(), pr(author="someone-else"))
    assert "AUTHOR_NOT_EXECUTOR" in result["reasons"] and result["verdict"] == "OWNER_MERGE_REQUIRED"


def test_a_branch_that_is_not_a_charter_unit_is_not_auto():
    result = ml.evaluate(policy(), pr(branch="claude/some-work"))
    assert "BRANCH_NOT_A_CHARTER_UNIT" in result["reasons"]


def test_an_owner_class_unit_is_never_auto():
    result = ml.evaluate(policy(), pr(branch=f"auto/{CHARTER}/CV-03P"))
    assert "UNIT_MERGE_CLASS_OWNER:CV-03P" in result["reasons"]
    assert result["verdict"] == "OWNER_MERGE_REQUIRED"


def test_a_ledger_rewrite_is_refused():
    result = ml.evaluate(policy(), pr(ledger_append_only=False, ledger_verifies=False))
    assert result["verdict"] == "REFUSED"
    assert "LEDGER_NOT_APPEND_ONLY" in result["reasons"]


def test_a_ledger_that_does_not_verify_is_refused():
    result = ml.evaluate(policy(), pr(ledger_verifies=False))
    assert result["verdict"] == "REFUSED"
    assert "LEDGER_DOES_NOT_VERIFY" in result["reasons"]


def test_a_new_dependency_outside_the_allowlist_is_not_auto():
    result = ml.evaluate(policy(), pr(new_dependencies=["leftpad"]))
    assert "DEPENDENCY_NOT_ALLOWLISTED:leftpad" in result["reasons"]


def test_unresolved_review_threads_are_not_auto():
    result = ml.evaluate(policy(), pr(unresolved_threads=2))
    assert "UNRESOLVED_REVIEW_THREADS:2" in result["reasons"]


@pytest.mark.parametrize("method", ["squash", "rebase"])
def test_squash_and_rebase_are_refused(method):
    result = ml.evaluate(policy(), pr(merge_method=method))
    assert result["verdict"] == "REFUSED"
    assert "MERGE_METHOD_NOT_MERGE_COMMIT" in result["reasons"]


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    subprocess.run(["git", "clone", "-q", "--no-hardlinks", str(REPO_ROOT), str(repo)], check=True)
    for k, v in (("user.email", "t@example.invalid"), ("user.name", "test")):
        subprocess.run(["git", "-C", str(repo), "config", k, v], check=True)
    return repo


def _commit(repo: Path, message: str) -> str:
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", message], check=True)
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True,
                          check=True).stdout.strip()


def test_a_pr_editing_the_protected_list_is_judged_by_the_base_list(tmp_path):
    """The PR removes CLAUDE.md from protection and edits CLAUDE.md. The BASE list still protects both."""
    repo = _repo(tmp_path)
    base = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True,
                          check=True).stdout.strip()
    lst = repo / cp.PROTECTED_PATHS
    lst.write_text(lst.read_text(encoding="utf-8").replace("\nCLAUDE.md\n", "\n"), encoding="utf-8")
    (repo / "CLAUDE.md").write_text("weakened\n", encoding="utf-8")
    head = _commit(repo, "self-judging attempt")
    policy_base = ml.policy_at(repo, base)
    p = ml.pull_request_at(repo, base, head, f"auto/{CHARTER}/CV-01", EXECUTOR, base, "merge", 0)
    result = ml.evaluate(policy_base, p)
    assert "PROTECTED_PATH:CLAUDE.md" in result["reasons"]
    assert f"PROTECTED_PATH:{cp.PROTECTED_PATHS}" in result["reasons"]
    assert result["verdict"] == "OWNER_MERGE_REQUIRED"


def test_a_rewritten_ledger_line_is_detected_from_git(tmp_path):
    repo = _repo(tmp_path)
    base = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True,
                          check=True).stdout.strip()
    ledger = repo / ml.LEDGER
    lines = ledger.read_text(encoding="utf-8").splitlines(keepends=True)
    ledger.write_text("".join(lines[:-1]), encoding="utf-8")
    head = _commit(repo, "drop the last ledger record")
    assert ml.ledger_checks(repo, base, head) == (False, False)


def test_an_unchanged_ledger_passes_from_git(tmp_path):
    repo = _repo(tmp_path)
    base = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True,
                          check=True).stdout.strip()
    (repo / "verification").mkdir()
    (repo / "verification" / "x.md").write_text("x\n", encoding="utf-8")
    head = _commit(repo, "routine")
    assert ml.ledger_checks(repo, base, head) == (True, True)
    assert ml.new_dependencies(repo, base, head, ["verification/x.md"]) == []
