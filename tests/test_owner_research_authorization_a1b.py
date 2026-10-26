"""OWNER RESEARCH AUTHORIZATION A1B-1: every field exactly once, and the boundary fields are NO.

Reads one committed file. PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import re
from pathlib import Path

RECORD = Path(__file__).resolve().parents[1] / "research" / "OWNER_RESEARCH_AUTHORIZATION_A1B_1.md"
FIELDS = ("AUTHORIZED_SCOPE", "EVALUATION_EXECUTION", "EXECUTION_LIMITS", "TRIALS_COUNTED", "GOVERNING_LAW", "DATASET",
          "REAL_MONEY_AUTHORIZED", "H1_LAUNCH_AUTHORIZED", "PAPER_LAUNCH_AUTHORIZED", "P3_RELATION", "EXPIRES_UTC")


def _block() -> str:
    text = RECORD.read_text(encoding="utf-8")
    m = re.search(r"## The authorization\s+```text\n(.*?)```", text, re.S)
    assert m, "the authorization block is missing"
    return m.group(1)


def _fields() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for line in _block().splitlines():
        if " = " in line:
            key, value = line.split(" = ", 1)
            out.setdefault(key.strip(), []).append(value.strip())
    return out


def test_every_field_appears_exactly_once():
    fields = _fields()
    assert sorted(fields) == sorted(FIELDS)
    assert all(len(v) == 1 for v in fields.values()), {k: v for k, v in fields.items() if len(v) != 1}


def test_the_boundary_fields_grant_nothing_live():
    f = {k: v[0] for k, v in _fields().items()}
    assert f["REAL_MONEY_AUTHORIZED"] == "NO"
    assert f["H1_LAUNCH_AUTHORIZED"] == "NO"
    assert f["PAPER_LAUNCH_AUTHORIZED"] == "NO"
    assert f["EVALUATION_EXECUTION"].startswith("NOT AUTHORIZED BY THIS RECORD")
    assert "no paper worker" in f["EXECUTION_LIMITS"] and "no live trading" in f["EXECUTION_LIMITS"]
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", f["EXPIRES_UTC"])


def test_the_record_says_it_binds_only_on_owner_merge():
    text = RECORD.read_text(encoding="utf-8")
    assert "only when the Owner merges it" in text
    assert "CEA-1" in text and "program charter" in text


def test_the_governing_law_and_pbo_gate_are_named():
    f = {k: v[0] for k, v in _fields().items()}
    assert "PROFITABILITY-VERIFICATION-LAW-1" in f["GOVERNING_LAW"]
    assert "PBO <= 0.05" in f["GOVERNING_LAW"] and "hard gate" in f["GOVERNING_LAW"]
    assert "never grants live" in f["GOVERNING_LAW"]
