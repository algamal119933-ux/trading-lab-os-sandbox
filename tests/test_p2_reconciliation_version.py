"""The reconciliation finding count is a law, and P1's history is not rewritten.

P1 closed on **thirteen** findings and `docs/p1/P1_CLOSURE.md` records that. P2
adds `registry_source_commit_equivalence` — the check that compares the
registry's declared source commit against the one stamped on the evidence — so
the current and future law is **fourteen**.

Both statements are true, about different things, and the distinction is the
point of this file. A closure record describes what was observed at the commit
it was written for; it is evidence and is never edited to agree with a later
system. An expectation, by contrast, must track the system it is asserted
against — a P2 closure that asserted 13/13 would either be counting a check that
no longer exists or silently accepting a report with one missing.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from fp import reconcile as fp_reconcile

P1_CLOSURE = Path("docs/p1/P1_CLOSURE.md")


# -- the law ---------------------------------------------------------------


def test_the_law_is_fourteen_findings():
    assert fp_reconcile.RECONCILE_FINDING_COUNT == 14
    assert len(fp_reconcile.EXPECTED_FINDINGS) == 14
    assert len(set(fp_reconcile.EXPECTED_FINDINGS)) == 14


def test_the_new_p2_finding_is_one_of_them():
    assert "registry_source_commit_equivalence" in fp_reconcile.EXPECTED_FINDINGS
    assert "registry_source_commit_equivalence" in fp_reconcile.FINDINGS_ALWAYS


def test_the_law_is_exactly_p1s_thirteen_plus_the_p2_finding():
    """The delta is one named check, not a renumbering."""
    p2_only = {"registry_source_commit_equivalence"}
    p1_era = set(fp_reconcile.EXPECTED_FINDINGS) - p2_only
    assert len(p1_era) == 13


def test_the_buckets_partition_the_law():
    always = set(fp_reconcile.FINDINGS_ALWAYS)
    role_bound = set(fp_reconcile.FINDINGS_WHEN_ROLE_BOUND)
    assert always & role_bound == set()
    assert always | role_bound == set(fp_reconcile.EXPECTED_FINDINGS)


# -- the report is checked against the law, every time ---------------------


def test_a_role_bound_reconciliation_emits_all_fourteen(tmp_path):
    from fp import ledger as fp_ledger

    evidence = tmp_path / "evidence"
    fp_ledger.open_ledgers(evidence, create=True)
    report = fp_reconcile.reconcile(evidence, expected_role="FP-CONTROL-2")
    assert report["findings_complete"] is True
    assert report["missing_findings"] == []
    assert report["unexpected_findings"] == []
    assert len(report["findings"]) == 14
    assert sorted(f["check"] for f in report["findings"]) == list(fp_reconcile.EXPECTED_FINDINGS)


def test_an_unbound_reconciliation_emits_thirteen_and_says_so(tmp_path):
    """Without a role there is no role to bind records to, and that is stated."""
    from fp import ledger as fp_ledger

    evidence = tmp_path / "evidence"
    fp_ledger.open_ledgers(evidence, create=True)
    report = fp_reconcile.reconcile(evidence)
    assert report["findings_complete"] is True
    assert len(report["findings"]) == 13
    assert "record_role_binding" not in report["expected_findings"]


def test_a_missing_finding_fails_the_reconciliation(tmp_path, monkeypatch):
    """A check that stopped running looks exactly like a check that passed."""
    from fp import ledger as fp_ledger

    evidence = tmp_path / "evidence"
    fp_ledger.open_ledgers(evidence, create=True)
    monkeypatch.setattr(
        fp_reconcile, "FINDINGS_ALWAYS",
        fp_reconcile.FINDINGS_ALWAYS + ("a_check_that_is_never_emitted",),
    )
    report = fp_reconcile.reconcile(evidence, expected_role="FP-CONTROL-2")
    assert report["findings_complete"] is False
    assert report["missing_findings"] == ["a_check_that_is_never_emitted"]
    assert report["reconciliation"] == fp_reconcile.FAIL
    assert any("findings_incomplete" in item for item in report["failing_checks"])


# -- P1's history is preserved exactly ------------------------------------


def test_p1s_closure_record_still_states_thirteen():
    """It describes P1. It is evidence, and evidence is not edited to agree."""
    text = P1_CLOSURE.read_text(encoding="utf-8")
    assert "13/13 findings, exit 0" in text
    assert "**13/13 PASS**" in text


def test_p1s_closure_record_is_unchanged_on_this_branch():
    import subprocess

    from test_p2_scope_audit import BASE_REF

    if BASE_REF is None:
        pytest.skip("no baseline in this checkout; covered wherever one exists")
    base = BASE_REF
    diff = subprocess.run(["git", "diff", "--name-only", base, "HEAD", "--", str(P1_CLOSURE)],
                          capture_output=True, text=True, check=True).stdout.strip()
    assert diff == "", "P1's closure record was modified; it is history, not an expectation"


# -- no P2 surface may assert the superseded count ------------------------


P2_SURFACES = [
    "docs/p2/P2_CONTRACT.md",
    "docs/p2/S2_PRE_T0_IMPLEMENTATION.md",
    "research/fp/reconcile.py",
    "scripts/validate_activation.py",
    "scripts/seal_pre_t0_qualification.py",
]


STALE_COUNTS = ("13/13", "13 findings", "thirteen findings")

# Words that mark a passage as describing P1 rather than stating a rule. A
# correction has to be able to say what it corrected, so citing the old number
# is legitimate exactly where the citation is labelled as history.
HISTORY_MARKERS = (
    "p1", "observed", "describes", "history", "superseded", "never rewritten",
    "closure record", "was written for",
)


def _paragraphs(text: str) -> list[str]:
    return re.split(r"\n\s*\n", text)


@pytest.mark.parametrize("path", P2_SURFACES)
def test_no_p2_surface_asserts_the_old_thirteen_finding_expectation(path):
    """The guard against a future P2 closure inheriting a stale number.

    A quotation of P1's own line, inside a passage that says it describes P1, is
    allowed — that is how a correction explains itself. A bare occurrence is not,
    because in a P2 document a bare count reads as the rule.
    """
    text = Path(path).read_text(encoding="utf-8")
    for paragraph in _paragraphs(text):
        for stale in STALE_COUNTS:
            if stale not in paragraph:
                continue
            lowered = paragraph.lower()
            assert any(marker in lowered for marker in HISTORY_MARKERS), (
                f"{path} mentions {stale!r} in a passage that does not mark it as history:\n"
                f"{paragraph.strip()[:300]}"
            )
            assert "14" in paragraph or "fourteen" in lowered or "`" in paragraph, (
                f"{path} cites {stale!r} without either quoting it or naming the current law"
            )


@pytest.mark.parametrize("path", [p for p in P2_SURFACES if p.endswith(".py")])
def test_no_p2_surface_hard_codes_the_old_count_in_code(path):
    """In executable surfaces the number may not appear as a literal at all.

    Parametrised over the code surfaces only rather than skipping the prose
    ones: a skip that is always expected is noise, and noise is what an audit
    step has to be able to distinguish a real skip from.
    """
    code = Path(path).read_text(encoding="utf-8")
    for stale in ("== 13", "!= 13", "len(findings) == 13", "FINDING_COUNT = 13"):
        assert stale not in code, f"{path} hard-codes the superseded count: {stale!r}"


def test_the_stage_record_states_the_current_law():
    text = Path("docs/p2/S2_PRE_T0_IMPLEMENTATION.md").read_text(encoding="utf-8")
    assert "fourteen" in text.lower()
    assert "registry_source_commit_equivalence" in text


def test_a_p2_closure_cannot_assert_a_count_the_code_does_not_produce():
    """Whatever a future P2 record claims must be derivable from the law here.

    Stated as an executable relationship rather than a number in prose, so a
    closure record that hard-codes a count can be checked against the module
    that produces it instead of against someone's memory.
    """
    assert fp_reconcile.RECONCILE_FINDING_COUNT == len(fp_reconcile.EXPECTED_FINDINGS)
    # And the count is discoverable from the report itself, so a record can cite
    # the report rather than a literal.
    from fp import ledger as fp_ledger
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        evidence = Path(tmp) / "evidence"
        fp_ledger.open_ledgers(evidence, create=True)
        report = fp_reconcile.reconcile(evidence, expected_role="FP-CONTROL-2")
    assert len(report["expected_findings"]) == fp_reconcile.RECONCILE_FINDING_COUNT
