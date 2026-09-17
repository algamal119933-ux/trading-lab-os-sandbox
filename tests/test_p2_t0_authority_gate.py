"""scripts/check_t0_authority.py — the boundary, in both lawful states.

This gate exists because its predecessor lived as inline Python in
``.github/workflows/ci.yml``, where no test could reach it. It asserted that the
registry at HEAD carries no T0 — true every day until the Owner lawfully froze
one, and false on the very commit P2 exists to produce. The first real freeze
candidate failed CI on it, and the repair could not travel with the freeze
because contract section 6 fixes that transaction at exactly two files.

So the gate is a script now, and these tests are the reason. Each one commits a
real state into a disposable clone and runs the real decision function: absent,
granted, a lawful freeze, and the state that must always fail — a T0 sitting in
the registry that no audited freeze transaction wrote.

PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import check_t0_authority as gate
import conftest
import freeze_t0
from fp import registry_law as fp_law

ROLE = "FP-CONTROL-2"


def _run(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args],
                          capture_output=True, text=True, check=True).stdout.strip()


def _commit(root: Path, message: str) -> str:
    subprocess.run(["git", "-C", str(root), "-c", "user.email=t@example.invalid",
                    "-c", "user.name=t", "commit", "--quiet", "--allow-empty", "-m", message],
                   check=True)
    return _run(root, "rev-parse", "HEAD")


def _write_registry(root: Path, registry: dict) -> None:
    (root / freeze_t0.REGISTRY_PATH).write_text(
        json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "--", freeze_t0.REGISTRY_PATH], check=True)


def _frozen_registry(t0: str = "2026-12-01T12:00:00Z") -> dict:
    """A registry carrying a lawfully shaped frozen row."""
    registry = conftest.pre_t0_registry(ROLE)
    registry["fp_run_active"] = True
    row = next(r for r in registry["instances"] if r["role"] == ROLE)
    row["status"] = "RUNNING"
    row["t0_utc"] = t0
    row["cohort_id"] = fp_law.cohort_id_for(ROLE, t0)
    row["runtime_identity"]["source_commit"] = "a" * 40
    row["change_log"] = [{"utc": t0, "class": "O", "description": "T0 frozen.",
                          "replay_parity_before_after": None}]
    return registry


@pytest.fixture
def clone(tmp_path):
    from conftest import clone_at_head

    destination, _ = clone_at_head(tmp_path / "clone")
    subprocess.run(["git", "-C", str(destination), "checkout", "--quiet", "-B", "base"], check=True)
    # A pre-T0 base every test can measure against, whatever this checkout holds.
    _write_registry(destination, conftest.pre_t0_registry(ROLE))
    base = _commit(destination, "the state before a T0 was frozen")
    subprocess.run(["git", "-C", str(destination), "checkout", "--quiet", "-b", "work"], check=True)
    return destination, base


def _authorization(**overrides) -> str:
    values = {
        "ROLE": ROLE,
        "QUALIFICATION_COMMIT": None,          # filled in per clone
        "QUALIFICATION_CERTIFICATE_SHA256": None,
        "REAL_MONEY_AUTHORIZED": "NO",
        "EXPIRES_UTC": (datetime.now(timezone.utc) + timedelta(days=3)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"),
    }
    values.update(overrides)
    return "\n".join(["# Owner T0 authorization", "", "```text",
                      *(f"{k} = {v}" for k, v in values.items()), "```", ""])


def _binding_values(root: Path) -> tuple[str, str]:
    binding = json.loads((root / freeze_t0.BINDING_PATH).read_text(encoding="utf-8"))
    return binding["qualification_commit"], binding["certificate_sha256"]


def _grant(root: Path, **overrides) -> str:
    mq, cert = _binding_values(root)
    overrides.setdefault("QUALIFICATION_COMMIT", mq)
    overrides.setdefault("QUALIFICATION_CERTIFICATE_SHA256", cert)
    path = root / freeze_t0.AUTHORIZATION_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_authorization(**overrides), encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "--", freeze_t0.AUTHORIZATION_PATH], check=True)
    return _commit(root, "Owner: authorize T0")


def _revoke(root: Path) -> str:
    if (root / freeze_t0.AUTHORIZATION_PATH).exists():
        subprocess.run(["git", "-C", str(root), "rm", "--quiet", "--",
                        freeze_t0.AUTHORIZATION_PATH], check=True)
    return _commit(root, "the state before authority was granted")


# -- the two lawful states -------------------------------------------------


def test_an_absent_authorization_is_lawful_and_reports_absent(clone):
    root, base = clone
    head = _revoke(root)
    report = gate.check(head, base=base, repo_root=root)
    assert report["authority"] == gate.ABSENT
    assert report["result"] == "PASS"
    assert report["t0_frozen_at_head"] is False


def test_a_granted_authorization_over_a_pre_t0_registry_passes(clone):
    root, base = clone
    head = _grant(root)
    report = gate.check(head, base=base, repo_root=root)
    assert report["authority"] == gate.GRANTED
    assert report["result"] == "PASS", report["problems"]
    assert report["t0_frozen_at_head"] is False


def test_a_lawful_freeze_candidate_passes_and_defers_to_the_freeze_gate(clone):
    """The case the predecessor could not express, and failed CI on."""
    root, base = clone
    _grant(root)
    _write_registry(root, _frozen_registry())
    head = _commit(root, "Freeze T0")

    report = gate.check(head, base=base, repo_root=root)
    assert report["is_freeze_candidate"] is True
    assert report["t0_frozen_at_head"] is True
    assert report["result"] == "PASS", report["problems"]
    assert any("defers" in note for note in report["notes"])


# -- the state that must never pass ---------------------------------------


def test_a_t0_that_no_freeze_transaction_wrote_fails(clone):
    """Deferring to the freeze gate must not become a way past it.

    Here the registry carries a T0 and the branch is NOT a freeze candidate —
    the row was already RUNNING at the base, so nothing went NOT_STARTED ->
    RUNNING. That is a cohort nobody reviewed, and it is the whole reason this
    gate still looks at the registry at all.
    """
    root, _ = clone
    _write_registry(root, _frozen_registry())
    base = _commit(root, "a T0 nobody audited")
    _grant(root)
    head = _commit(root, "later work")

    report = gate.check(head, base=base, repo_root=root)
    assert report["is_freeze_candidate"] is False
    assert report["result"] == "FAIL"
    assert any("outside the audited freeze transaction" in p for p in report["problems"])


def test_without_a_base_a_frozen_registry_still_fails_closed(clone):
    """No base means no freeze gate, and an unexplained T0 is then a failure."""
    root, _ = clone
    _write_registry(root, _frozen_registry())
    head = _commit(root, "Freeze T0")
    report = gate.check(head, base=None, repo_root=root)
    assert report["is_freeze_candidate"] is False
    assert report["result"] == "FAIL"


# -- the authorization must agree with the merged binding ------------------


def test_an_authorization_naming_another_certificate_fails(clone):
    root, base = clone
    head = _grant(root, QUALIFICATION_CERTIFICATE_SHA256="0" * 64)
    report = gate.check(head, base=base, repo_root=root)
    assert report["result"] == "FAIL"
    assert any("does not pin" in p for p in report["problems"])


def test_an_authorization_naming_another_qualification_commit_fails(clone):
    root, base = clone
    head = _grant(root, QUALIFICATION_COMMIT="b" * 40)
    report = gate.check(head, base=base, repo_root=root)
    assert report["result"] == "FAIL"
    assert any("does not record" in p or "not an ancestor" in p for p in report["problems"])


def test_an_authorization_for_another_role_fails(clone):
    root, base = clone
    head = _grant(root, ROLE="FP-CANDIDATE-A")
    report = gate.check(head, base=base, repo_root=root)
    assert report["result"] == "FAIL"
    assert any("names role" in p for p in report["problems"])


def test_real_money_yes_fails(clone):
    root, base = clone
    head = _grant(root, REAL_MONEY_AUTHORIZED="YES")
    report = gate.check(head, base=base, repo_root=root)
    assert report["result"] == "FAIL"
    assert any("REAL_MONEY_AUTHORIZED = NO" in p for p in report["problems"])


def test_a_malformed_expiry_fails(clone):
    root, base = clone
    head = _grant(root, EXPIRES_UTC="whenever")
    report = gate.check(head, base=base, repo_root=root)
    assert report["result"] == "FAIL"
    assert any("EXPIRES_UTC" in p for p in report["problems"])


# -- and against this repository as it actually stands --------------------


def test_the_gate_passes_against_this_repository():
    report = gate.check("HEAD", base="origin/main")
    assert report["result"] == "PASS", report["problems"]
