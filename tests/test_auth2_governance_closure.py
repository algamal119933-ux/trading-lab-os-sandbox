"""AUTH2-GOVERNANCE-CLOSURE-1 (docs/governance/records/AUTH2-GOVERNANCE-CLOSURE-1/): AUTH-2 closes by an
Owner-approved governance record outside the trial ledger (Owner decision 2026-10-12T23:14:33Z, OD-C1 to
OD-C7). The record files are the approved bundle byte for byte and never change, the charter is CLOSED and
otherwise as run, the trial ledger keeps every record the closure saw and gains no AUTH-2 terminal, and the
generator rebuilds the record from its evidence at the commit the evidence names.

PAPER / RESEARCH ONLY.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

import cea_policy as cp

REPO = Path(__file__).resolve().parents[1]
RECORD_DIR = "docs/governance/records/AUTH2-GOVERNANCE-CLOSURE-1"
CHARTER = "charters/programs/AUTH-2-DISCOVERY-QUALIFICATION-1.json"
LEDGER = "research/records/trial_ledger.jsonl"
EVIDENCE_COMMIT = "8013e216075fcdfdf1068ef1b43b52aea5747d78"

# Append-only (OD-C1): no file here changes after the Owner's merge. A correction is a new ERRATA file.
PINNED = {
    "evidence.json": "bbece74c7757c4c8030293b34c1c7e74615997d7d3bbd13b2cd0c1dc98394c3f",
    "governance_closure.proposed.json": "accc6ed0f9f3ce248b8227d4774fe1ce8da93e88e8227a61719a18008f0c71c2",
    "trial_ledger_option.check.json": "ab501540c200ef283960eac5234cad25b4719a397a5b4f3baf88b688f37047d5",
    "SHA256SUMS": "fee39e08980907b156cce6d33c5c30a073e921892cd8283b8df78ff8d81cc89c",
    "closure_proposal.py": "0c7cb7c1ca286d5279e69d0c17737c709b490190b104ec9eaae7cb8dc9a4608a",
    "README.md": "18a00882c574eb5999ad07ff56954387d7b7fea12ec8ccafe04e777fedf678ef",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dumps(obj) -> str:
    return json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def record() -> dict:
    return json.loads((REPO / RECORD_DIR / "governance_closure.proposed.json").read_text())


@pytest.mark.parametrize("name", sorted(PINNED))
def test_every_record_file_is_the_one_the_owner_approved(name):
    assert sha(REPO / RECORD_DIR / name) == PINNED[name], name


def test_sha256sums_binds_the_evidence_and_both_outputs():
    listed = {name: digest for digest, name in
              (line.split("  ", 1) for line in (REPO / RECORD_DIR / "SHA256SUMS").read_text().splitlines())}
    assert sorted(listed) == ["evidence.json", "governance_closure.proposed.json", "trial_ledger_option.check.json"]
    for name, digest in listed.items():
        assert sha(REPO / RECORD_DIR / name) == digest, name
    assert record()["evidence"]["evidence_sha256"] == listed["evidence.json"]


def test_the_record_closes_auth2_by_operational_exhaustion_with_no_scientific_outcome():
    rec = record()
    assert (rec["record_id"], rec["record_type"]) == ("AUTH2-GOVERNANCE-CLOSURE-1", "PROGRAM_CLOSURE")
    cls = rec["classification"]
    assert (cls["terminal"], cls["scientific_outcome"]) == ("OPERATIONAL_EXHAUSTION", "NONE")
    assert (cls["hypotheses_evaluated"], cls["node_results"], cls["engine_invocations"]) == (0, 0, 0)
    assert (rec["dry_run"], rec["real_money_authorized"]) == (True, False)
    trials = {n["trial_id"] for n in json.loads((REPO / CHARTER).read_text())["dag"]["nodes"]}
    assert len(trials) == 14 and set(rec["trials"]) == trials
    status = {t: v["governance_status"] for t, v in rec["trials"].items()}
    assert status.pop("TRIAL-AUTH2-D0") == "CLOSED_NOT_EVALUATED"
    assert len(status) == 13 and set(status.values()) == {"CLOSED_NOT_RUN"}


def test_the_charter_is_closed_and_the_record_keeps_its_as_run_hash():
    """OD-C3: only the status changed. The committed file is the canonical dump of its content, and the same
    content with status ACTIVE hashes to the charter the record names, so no other byte can differ."""
    text = (REPO / CHARTER).read_text()
    program = json.loads(text)
    assert program["status"] == "CLOSED" and text == dumps(program)
    rec = record()["program"]
    assert (rec["id"], rec["charter_path"], rec["main_sha"]) == (program["program_id"], CHARTER, EVIDENCE_COMMIT)
    as_run = dumps({**program, "status": "ACTIVE"}).encode()
    assert hashlib.sha256(as_run).hexdigest() == rec["charter_sha256"]
    assert sha(REPO / "research/auth2/FUNNEL_LAW_2.md") == rec["funnel_law_sha256"]


def test_the_trial_ledger_keeps_what_the_closure_saw_and_gains_no_auth2_terminal():
    """OD-C1: nothing is appended for AUTH-2. Every record the closure saw is still there byte for byte; later
    records may follow (the ledger is append-only), but none for an AUTH-2 trial ID."""
    from trial_ledger import TrialLedger

    anchor = record()["trial_ledger_anchor"]
    assert anchor["path"] == LEDGER
    lines = (REPO / LEDGER).read_bytes().splitlines(keepends=True)
    assert hashlib.sha256(b"".join(lines[:anchor["records"]])).hexdigest() == anchor["sha256"]
    led = TrialLedger(REPO / LEDGER)
    assert led.verify() == []
    recs = led.records()
    assert recs[anchor["records"] - 1].digest == anchor["tip_digest"]
    auth2 = [r for r in recs if r.payload["trial_id"] in record()["trials"]]
    assert len(auth2) == anchor["auth2_preregistered"] == 14
    assert {r.payload["state"] for r in auth2} == {"PREREGISTERED"}
    assert anchor["auth2_terminal"] == 0


def test_the_record_folder_is_protected():
    globs = cp.protected_at(REPO, None)
    for path in sorted((REPO / RECORD_DIR).iterdir()):
        assert cp.is_protected(f"{RECORD_DIR}/{path.name}", globs), path.name


def test_the_generator_sits_outside_the_pinned_code_and_every_pin_holds():
    pytest.importorskip("numpy")
    from auth2 import run_node as RN

    now = RN.code_sha256()
    assert not any("closure_proposal" in rel for rel in now)
    for node in RN.NODES:
        prereg = json.loads((REPO / f"research/auth2/prereg/{node}.json").read_text())
        assert prereg["code_sha256"] == now, node


def test_the_generator_rebuilds_the_record_from_its_evidence_at_the_commit_it_names(tmp_path):
    """The README's `verify`: a clone at main 8013e216, the commit evidence.json names, rebuilds every output
    byte for byte with the trial ledger and worktree unchanged. A later commit is refused by design (this
    record's own commit changes the charter), so the clone is taken at that commit."""
    pytest.importorskip("numpy")

    def git(*args: str, cwd: Path = REPO) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, timeout=600)

    if git("cat-file", "-e", f"{EVIDENCE_COMMIT}^{{commit}}").returncode != 0:
        pytest.skip("this checkout does not hold the evidence commit (shallow history)")
    clone = tmp_path / "at-evidence"
    assert git("clone", "--quiet", "--no-hardlinks", str(REPO), str(clone), cwd=tmp_path).returncode == 0
    checkout = git("checkout", "--quiet", "--detach", EVIDENCE_COMMIT, cwd=clone)
    assert checkout.returncode == 0, checkout.stderr
    folder = REPO / RECORD_DIR
    out = subprocess.run([sys.executable, "-I", str(folder / "closure_proposal.py"), "verify", "--repo", str(clone),
                          "--evidence", str(folder / "evidence.json"), "--out-dir", str(folder)],
                         capture_output=True, text=True, timeout=600)
    assert out.returncode == 0, out.stdout + out.stderr
    assert "CLOSURE_PROPOSAL_VERIFY = PASS" in out.stdout
