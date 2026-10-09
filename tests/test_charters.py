"""CEA-1 §1/§13: charters and evidence tickets.

PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

import cea_policy as cp
import check_charters as cc

REPO_ROOT = Path(__file__).resolve().parents[1]
CHARTER = "COMMERCIAL-VERIFICATION-LANE-1"


@pytest.fixture
def copy(tmp_path: Path) -> Path:
    root = tmp_path / "main"
    for rel in (".github/gates", "charters"):
        shutil.copytree(REPO_ROOT / rel, root / rel)
    return root


def write_ticket(root: Path, ticket: dict) -> None:
    d = root / "charters/tickets" / ticket["charter"]
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{ticket['id']}.json").write_text(json.dumps(ticket), encoding="utf-8")


def test_the_committed_charters_pass():
    assert cc.check(REPO_ROOT) == []


def test_the_commercial_charter_is_the_one_active_charter():
    charters = cp.charters_at(REPO_ROOT, None)
    assert sorted(charters) == [CHARTER]
    c = charters[CHARTER]
    assert c["status"] == "ACTIVE" and c["title"] == "Freqtrade Strategy Verification"
    units = {u["id"]: u for u in c["units"]}
    assert [units[u]["merge_class"] for u in ("CV-01", "CV-02", "CV-03")] == ["AUTO"] * 3
    assert units["CV-03P"]["merge_class"] == "OWNER"


def test_cv_03_never_depends_on_cv_03p_and_never_touches_the_judge():
    units = {u["id"]: u for u in cp.charters_at(REPO_ROOT, None)[CHARTER]["units"]}
    assert all(p["kind"] == "file_exists" for p in units["CV-03"]["prerequisites"])
    assert any("research/cycle2/**" in a and "NOT" in a for a in units["CV-03"]["acceptance"])
    kinds = json.dumps(units["CV-03P"]["prerequisites"])
    assert "existing_interface_blocker" in kinds and "manual_minutes" in kinds


def test_the_scope_never_reaches_a_protected_path():
    protected = cp.protected_at(REPO_ROOT, None)
    scope = cp.charters_at(REPO_ROOT, None)[CHARTER]["scope"]["paths"]
    assert not [(s, g) for s in scope for g, _ in protected if cp.globs_may_overlap(s, g)]


def test_a_scope_reaching_a_protected_path_is_refused(copy):
    path = copy / f"charters/{CHARTER}.json"
    c = json.loads(path.read_text(encoding="utf-8"))
    c["scope"]["paths"].append("research/cycle2/**")
    path.write_text(json.dumps(c), encoding="utf-8")
    assert any("can reach protected path" in p for p in cc.check(copy))


@pytest.mark.parametrize("field", ["customer_name", "email", "contact", "code", "data"])
def test_a_ticket_has_no_field_for_customer_data(copy, field):
    write_ticket(copy, {"id": "T-1", "charter": CHARTER, "kind": "failing_case", "date": "2026-10-09",
                        "summary": "x", field: "anything"})
    assert any("schema" in p for p in cc.check(copy))


def test_a_manual_minutes_ticket_must_name_a_paid_case(copy):
    write_ticket(copy, {"id": "T-2", "charter": CHARTER, "kind": "manual_minutes", "case_id": "C-9",
                        "minutes": 40, "date": "2026-10-09", "summary": "manual report assembly"})
    assert any("must name the case_id of a paid ticket" in p for p in cc.check(copy))
    write_ticket(copy, {"id": "T-1", "charter": CHARTER, "kind": "paid", "case_id": "C-9",
                        "date": "2026-10-09", "summary": "first paid case"})
    assert cc.check(copy) == []


def test_the_market_test_numbers_are_frozen_in_the_charter():
    stop = cp.charters_at(REPO_ROOT, None)[CHARTER]["stop_law"]
    assert stop["market_test_window_days"] == 14
    assert stop["market_test_min_logged_contacts"] == 25
    assert "STOP" in stop["zero_paid_outcome"]
