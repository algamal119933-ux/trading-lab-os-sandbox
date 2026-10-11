"""CEA-1 §2/§6/§8/§9: the resolver is deterministic, leases by branch name,
serializes main, honours the kill state, and parks only the blocked lane.

PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

import resolve_next_unit as rnu

REPO_ROOT = Path(__file__).resolve().parents[1]
CHARTER = "COMMERCIAL-VERIFICATION-LANE-1"
EMPTY = {"open_prs": [], "merged_heads": [], "branches": []}


def lane(result: dict, name: str) -> dict:
    return next(l for l in result["lanes"] if l.get("charter") == name or l["lane"] == name)


def eligible(result: dict) -> list[str]:
    return [u["unit"] for u in lane(result, CHARTER)["eligible_units"]]


@pytest.fixture
def policy_copy(tmp_path: Path) -> Path:
    """A copy of only the policy files, so a test can change them without touching the repo."""
    root = tmp_path / "main"
    for rel in (".github/gates", "charters"):
        shutil.copytree(REPO_ROOT / rel, root / rel)
    (root / "docs/governance").mkdir(parents=True)
    shutil.copy(REPO_ROOT / "docs/governance/CONTINUOUS_EXECUTION_AUTHORITY_1.md", root / "docs/governance")
    return root


def test_the_state_on_this_tree_is_the_designed_c6():
    result = rnu.resolve(REPO_ROOT, EMPTY)
    assert eligible(result) == ["CV-01", "CV-02", "CV-03"]
    research = lane(result, "RESEARCH")
    # AUTH-2 adds the first program. Its nodes are never selected here: the lane names the
    # program's own runner and dispatch guard, and next_action is unchanged by it.
    assert research["status"] == "PROGRAMS_PRESENT"
    assert research["programs"] == ["AUTH-2-DISCOVERY-QUALIFICATION-1"]
    assert [b["class"] for b in research["blockers"]] == ["EXTERNAL"]
    assert result["auto_merge"] == "INACTIVE"
    assert result["next_action"] == f"START auto/{CHARTER}/CV-01"


def test_cv_03p_is_not_opened_pre_paid():
    blocked = {b["unit"]: b["unmet"] for b in lane(rnu.resolve(REPO_ROOT, EMPTY), CHARTER)["blocked_units"]}
    assert "CV-03P" in blocked and "CV-03P" not in eligible(rnu.resolve(REPO_ROOT, EMPTY))


def test_the_output_is_byte_identical_for_the_same_inputs():
    a = json.dumps(rnu.resolve(REPO_ROOT, EMPTY), sort_keys=True)
    b = json.dumps(rnu.resolve(REPO_ROOT, json.loads(json.dumps(EMPTY))), sort_keys=True)
    assert a == b


def test_an_existing_branch_is_resumed_never_duplicated():
    gh = dict(EMPTY, branches=[f"auto/{CHARTER}/CV-01"])
    result = rnu.resolve(REPO_ROOT, gh)
    assert "CV-01" not in eligible(result)
    assert [f["unit"] for f in lane(result, CHARTER)["in_flight"]] == ["CV-01"]
    assert result["next_action"] == f"RESUME auto/{CHARTER}/CV-01"


def test_a_merged_unit_is_done():
    result = rnu.resolve(REPO_ROOT, dict(EMPTY, merged_heads=[f"auto/{CHARTER}/CV-01"]))
    assert lane(result, CHARTER)["done"] == ["CV-01"]
    assert eligible(result) == ["CV-02", "CV-03"]


def test_an_open_pr_needs_the_owner_while_auto_merge_is_inactive():
    gh = dict(EMPTY, open_prs=[{"number": 7, "head_ref": f"auto/{CHARTER}/CV-02", "auto_merge": False}])
    owner = lane(rnu.resolve(REPO_ROOT, gh), CHARTER)["owner_required"]
    assert owner == [{"unit": "CV-02", "pr": 7, "action": "OWNER_MERGE"}]


def test_more_than_one_armed_pr_is_a_safety_stop():
    gh = dict(EMPTY, open_prs=[{"number": 1, "head_ref": f"auto/{CHARTER}/CV-01", "auto_merge": True},
                               {"number": 2, "head_ref": f"auto/{CHARTER}/CV-02", "auto_merge": True}])
    result = rnu.resolve(REPO_ROOT, gh)
    assert result["blockers"][0]["class"] == "SAFETY"
    assert result["next_action"].startswith("EXIT")


def test_suspended_yields_nothing(policy_copy):
    (policy_copy / ".github/gates/AUTONOMY_STATE.json").write_text(
        json.dumps({"state": "SUSPENDED", "revoked_programs": []}), encoding="utf-8")
    result = rnu.resolve(policy_copy, EMPTY)
    assert eligible(result) == []
    assert result["next_action"] == "EXIT: AUTONOMY_SUSPENDED"


def test_a_blocked_lane_leaves_the_other_lanes_eligible(policy_copy):
    other = json.loads((policy_copy / f"charters/{CHARTER}.json").read_text(encoding="utf-8"))
    other.update(id="ENGINEERING-LANE-T", lane="ENGINEERING", priority=2, status="SUSPENDED")
    (policy_copy / "charters/ENGINEERING-LANE-T.json").write_text(json.dumps(other), encoding="utf-8")
    result = rnu.resolve(policy_copy, EMPTY)
    assert lane(result, "ENGINEERING-LANE-T")["blockers"][0]["class"] == "AUTHORITY"
    assert eligible(result) == ["CV-01", "CV-02", "CV-03"]


def test_evidence_tickets_open_cv_03p(policy_copy):
    tickets = policy_copy / "charters/tickets" / CHARTER
    tickets.mkdir(parents=True)
    (tickets / "T-1.json").write_text(json.dumps({
        "id": "T-1", "charter": CHARTER, "kind": "existing_interface_blocker", "date": "2026-10-09",
        "summary": "runner cannot pass fee levels through the existing interface"}), encoding="utf-8")
    assert "CV-03P" in eligible(rnu.resolve(policy_copy, EMPTY))


def test_only_dry_run_exists(capsys):
    assert rnu.main(["--repo", str(REPO_ROOT)]) == 2
    assert "only --dry-run" in capsys.readouterr().err
