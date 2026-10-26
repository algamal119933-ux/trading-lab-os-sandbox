"""The prepared H1 launch authorization record cannot be mistaken for a grant.

research/paper/h1/launch/OWNER_H1_LAUNCH_AUTHORIZATION_1.md is prepared NOT GRANTED
(Owner directive 2026-10-26, PRIORITY 4). These tests hold:

* the machine block declares every field exactly once;
* the fixed identities equal the frozen package (digest, cohort, 24 h card age, no real money);
* while H1_LAUNCH_AUTHORIZED = NO, the not-a-grant clause is present;
* a YES is only well-formed with a concrete card path, a 64-hex card sha256, a concrete
  second store and a concrete EXPIRES_UTC (exercised on synthetic text, never on the record);
* no launch tool reads the record, so its presence changes no verdict.

PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
RECORD = REPO / "research" / "paper" / "h1" / "launch" / "OWNER_H1_LAUNCH_AUTHORIZATION_1.md"
LAUNCH_DIR = REPO / "research" / "paper" / "h1" / "launch"
PACKAGE_DIR = REPO / "research" / "paper" / "h1" / "package"
PACKAGE_DIGEST = "ef9a3d0c5b5b9abe122faaa1bd4ef67feb0c3ec4437bed56cd6ef33d910bc43c"

FIELDS = (
    "AUTHORIZATION", "H1_LAUNCH_AUTHORIZED", "PACKAGE", "PACKAGE_MANIFEST_SHA256", "COHORT_ID",
    "CANDIDATE", "MODE", "HOST", "PLACEMENT", "LANE_DIR", "SECOND_EVIDENCE_STORE", "LAUNCH_CARD_JSON",
    "LAUNCH_CARD_SHA256", "CARD_MAX_AGE_HOURS", "T0_RULE", "WINDOW", "EDGE_EVIDENCE", "EXPIRES_UTC",
    "REAL_MONEY_AUTHORIZED",
)
NOT_A_GRANT = "Merging this record does NOT authorize launch."
PLACEHOLDER = re.compile(r"<[^>]*>")


def machine_block(text: str) -> str:
    match = re.search(r"## The record\s+```text\n(.*?)```", text, re.S)
    assert match, "the record's fenced machine block is missing"
    return match.group(1)


def parse(block: str) -> dict[str, list[str]]:
    fields: dict[str, list[str]] = {}
    for line in block.splitlines():
        if not line.strip():
            continue
        key, sep, value = line.partition("=")
        assert sep, f"not a KEY = VALUE line: {line!r}"
        fields.setdefault(key.strip(), []).append(value.strip())
    return fields


def grant_problems(text: str) -> list[str]:
    """Why this text is not a well-formed record. Applies to NO and YES alike."""
    problems: list[str] = []
    fields = parse(machine_block(text))
    for key in FIELDS:
        count = len(fields.get(key, []))
        if count != 1:
            problems.append(f"{key} appears {count} times")
    for key in fields:
        if key not in FIELDS:
            problems.append(f"unknown field {key}")
    if problems:
        return problems
    value = {k: v[0] for k, v in fields.items()}
    if value["PACKAGE_MANIFEST_SHA256"] != PACKAGE_DIGEST:
        problems.append("package digest differs from the frozen package")
    if value["COHORT_ID"] != "H1-PAPER-COHORT-1":
        problems.append("cohort id differs")
    if value["REAL_MONEY_AUTHORIZED"] != "NO":
        problems.append("REAL_MONEY_AUTHORIZED must be NO")
    if value["CARD_MAX_AGE_HOURS"] != "24":
        problems.append("CARD_MAX_AGE_HOURS must be 24")
    granted = value["H1_LAUNCH_AUTHORIZED"]
    if granted == "NO":
        if NOT_A_GRANT not in text:
            problems.append("a NOT-GRANTED record must carry the not-a-grant clause")
    elif granted == "YES":
        for key in ("SECOND_EVIDENCE_STORE", "LAUNCH_CARD_JSON", "LAUNCH_CARD_SHA256", "EXPIRES_UTC"):
            if PLACEHOLDER.search(value[key]) or not value[key]:
                problems.append(f"a grant must set {key}")
        if not re.fullmatch(r"[0-9a-f]{64}", value["LAUNCH_CARD_SHA256"]):
            problems.append("a grant must name the card's sha256 (64 hex)")
        if not value["LAUNCH_CARD_JSON"].endswith(".json"):
            problems.append("a grant must name the card's JSON file")
        if not value["SECOND_EVIDENCE_STORE"].startswith("/"):
            problems.append("a grant must name an absolute second evidence store")
        try:
            datetime.strptime(value["EXPIRES_UTC"], "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            problems.append("a grant must set EXPIRES_UTC as YYYY-MM-DDTHH:MM:SSZ")
    else:
        problems.append(f"H1_LAUNCH_AUTHORIZED must be NO or YES, not {granted!r}")
    return problems


def test_record_is_well_formed():
    assert grant_problems(RECORD.read_text(encoding="utf-8")) == []


def test_record_is_prepared_not_granted():
    text = RECORD.read_text(encoding="utf-8")
    fields = parse(machine_block(text))
    assert fields["H1_LAUNCH_AUTHORIZED"] == ["NO"]
    assert NOT_A_GRANT in text
    assert "PREPARED, NOT GRANTED" in text


def _as_yes(text: str, **overrides: str) -> str:
    text = text.replace("H1_LAUNCH_AUTHORIZED     = NO", "H1_LAUNCH_AUTHORIZED     = YES")
    for key, value in overrides.items():
        text = re.sub(rf"^({key}\s+= ).*$", lambda m: m.group(1) + value, text, flags=re.M)
    return text


def test_a_yes_with_placeholders_is_refused():
    problems = grant_problems(_as_yes(RECORD.read_text(encoding="utf-8")))
    assert any("LAUNCH_CARD_SHA256" in p for p in problems)
    assert any("EXPIRES_UTC" in p for p in problems)
    assert any("SECOND_EVIDENCE_STORE" in p for p in problems)


def test_a_complete_yes_is_well_formed_only_with_a_card_digest():
    base = RECORD.read_text(encoding="utf-8")
    complete = dict(SECOND_EVIDENCE_STORE="/mnt/tlos-wdc/tlos-h1-evidence",
                    LAUNCH_CARD_JSON="/home/hamza/tlos-paper/h1-card-checks/20261027T000000Z/h1_launch_card.json",
                    LAUNCH_CARD_SHA256="a" * 64, EXPIRES_UTC="2026-11-30T23:59:59Z")
    assert grant_problems(_as_yes(base, **complete)) == []
    assert grant_problems(_as_yes(base, **{**complete, "LAUNCH_CARD_SHA256": "not-a-digest"}))


@pytest.mark.parametrize("mutation", [
    lambda t: t.replace("REAL_MONEY_AUTHORIZED    = NO", "REAL_MONEY_AUTHORIZED    = YES"),
    lambda t: t.replace(PACKAGE_DIGEST, "0" * 64, 1),
    lambda t: t.replace("H1_LAUNCH_AUTHORIZED     = NO", "H1_LAUNCH_AUTHORIZED     = NO\nH1_LAUNCH_AUTHORIZED     = YES"),
    lambda t: t.replace(NOT_A_GRANT, ""),
    lambda t: t.replace("H1_LAUNCH_AUTHORIZED     = NO", "H1_LAUNCH_AUTHORIZED     = MAYBE"),
])
def test_mutations_are_refused(mutation):
    assert grant_problems(mutation(RECORD.read_text(encoding="utf-8")))


def test_no_launch_tool_reads_the_record():
    """Its presence cannot turn a DENY into a launch: no tool parses it."""
    for directory in (LAUNCH_DIR, PACKAGE_DIR):
        for path in directory.glob("*.py"):
            text = path.read_text(encoding="utf-8")
            assert "OWNER_H1_LAUNCH_AUTHORIZATION" not in text, path
            assert "H1_LAUNCH_AUTHORIZED" not in text, path


# -- coordination with the merged §19 health check (PR #85; research/p3/health.py is Lane B's) ----------
# The hourly health run reports `unauthorized_execution` CRITICAL for any running paper container that no
# RUNNING registry cohort backs. H1 has no registry row, so today a running H1 container is CRITICAL. A
# grant PR that flips H1_LAUNCH_AUTHORIZED to YES must, in the same change, give the health check a way to
# recognise the granted H1 cohort (e.g. a RUNNING H1 row the check reads). Otherwise a lawful launch would
# page as unauthorized execution. This test fails if the record says YES before that is true.

H1_CONTAINER = "tlos-h1-paper-cohort-1-freqtrade"


def _h1_is_unauthorized_today() -> bool:
    import json
    import sys
    for extra in (str(REPO / "research"), str(REPO / "scripts")):
        if extra not in sys.path:
            sys.path.insert(0, extra)
    from p3 import health  # noqa: PLC0415
    registry = json.loads((REPO / "research" / "fp" / "records" / "forward_paper_cohort_registry.json")
                          .read_text(encoding="utf-8"))
    findings = health.paper_runtime_vs_registry(registry, {H1_CONTAINER: "running"})
    sev = {f["check"]: f["severity"] for f in findings}
    return sev.get("unauthorized_execution") == health.CRITICAL


def test_the_health_check_and_the_record_agree_about_h1():
    granted = {k: v[0] for k, v in parse(machine_block(RECORD.read_text(encoding="utf-8"))).items()}[
        "H1_LAUNCH_AUTHORIZED"]
    if granted == "YES":
        assert not _h1_is_unauthorized_today(), (
            "H1_LAUNCH_AUTHORIZED = YES, but research/p3/health.py would still page a running H1 container as "
            "unauthorized execution: the grant PR must also teach the health check the granted cohort")
    else:
        assert granted == "NO"
        assert _h1_is_unauthorized_today(), "while NOT granted, a running H1 container must be CRITICAL"
