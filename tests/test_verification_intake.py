"""CV-02: intake form, checklist and deterministic triage.

PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
INTAKE = REPO_ROOT / "verification" / "intake"
_spec = importlib.util.spec_from_file_location("verification_triage", INTAKE / "triage.py")
triage = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(triage)

EXAMPLE = json.loads((INTAKE / "example_intake.json").read_text(encoding="utf-8"))


def changed(**paths) -> dict:
    """EXAMPLE with dotted paths replaced; a value of ... deletes the key."""
    intake = copy.deepcopy(EXAMPLE)
    for dotted, value in paths.items():
        *parents, leaf = dotted.split("__")
        node = intake
        for p in parents:
            node = node[p]
        if value is ...:
            node.pop(leaf)
        else:
            node[leaf] = value
    return intake


def test_the_example_intake_is_accepted():
    result = triage.triage(EXAMPLE)
    assert result == {"outcome": "ACCEPT", "reasons": [], "messages": [], "notes": []}
    assert triage.main([str(INTAKE / "example_intake.json")]) == 0


def test_triage_is_deterministic():
    bad = changed(config__dry_run=False, strategy__strategy_sha256=None)
    assert triage.triage(bad) == triage.triage(copy.deepcopy(bad))


@pytest.mark.parametrize("paths,reason", [
    ({"config__dry_run": False}, "LIVE_TRADING_REQUESTED"),
    ({"config__trading_mode": "futures"}, "FUTURES_OR_MARGIN"),
    ({"config__margin_mode": "isolated"}, "FUTURES_OR_MARGIN"),
    ({"config__can_short": True}, "SHORTS"),
    ({"config__leverage": 3}, "LEVERAGE"),
    ({"rights__licence_spdx": None}, "NO_RIGHTS"),
])
def test_each_boundary_is_out_of_scope(paths, reason):
    result = triage.triage(changed(**paths))
    assert result["outcome"] == "OUT_OF_SCOPE"
    assert reason in result["reasons"]


@pytest.mark.parametrize("field", ["api_key", "apiKey", "secret", "password", "passphrase", "private_key",
                                   "token", "key", "uid"])
def test_a_credential_is_refused_even_in_a_malformed_intake(field):
    intake = changed()
    intake["config"][field] = "abc123"
    result = triage.triage(intake)
    assert result["outcome"] == "OUT_OF_SCOPE"
    assert result["reasons"][0] == "SECRET_IN_SUBMISSION"


def test_a_private_key_block_in_any_text_is_refused():
    result = triage.triage(changed(claim__text="-----BEGIN EC " + "PRIVATE KEY-----\nMHcC..."))
    assert "SECRET_IN_SUBMISSION" in result["reasons"]


@pytest.mark.parametrize("paths,reason", [
    ({"strategy__strategy_sha256": None}, "IDENTITY_INCOMPLETE:strategy"),
    ({"strategy__params_sha256": None}, "IDENTITY_INCOMPLETE:params"),
    ({"config__sha256": "not-a-hash"}, "IDENTITY_INCOMPLETE:config"),
    ({"engine__freqtrade_version": None}, "IDENTITY_INCOMPLETE:engine"),
    ({"market__timerange": None}, "IDENTITY_INCOMPLETE:market"),
    ({"market__pairs": []}, "IDENTITY_INCOMPLETE:market"),
    ({"strategy__source__commit": "b68a551"}, "SOURCE_UNPINNED"),
    ({"claim__source": ...}, "CLAIM_WITHOUT_SOURCE"),
])
def test_each_identity_gap_needs_info(paths, reason):
    result = triage.triage(changed(**paths))
    assert result["outcome"] == "NEEDS_INFO"
    assert reason in result["reasons"]


def test_a_stated_absent_params_file_is_complete():
    result = triage.triage(changed(strategy__params_sha256=None, strategy__params_file_absent=True))
    assert result["outcome"] == "ACCEPT"


def test_an_archive_needs_its_hash():
    archive = {"kind": "archive"}
    assert "SOURCE_UNPINNED" in triage.triage(changed(strategy__source=archive))["reasons"]
    archive["archive_sha256"] = "0" * 64
    assert triage.triage(changed(strategy__source=archive))["outcome"] == "ACCEPT"


def test_no_claim_is_accepted_with_a_note():
    result = triage.triage(changed(claim={"stated": False}))
    assert result["outcome"] == "ACCEPT"
    assert result["notes"] == [triage.RUBRIC["notes"]["NO_CLAIM"]]


def test_out_of_scope_outranks_needs_info():
    result = triage.triage(changed(config__can_short=True, strategy__strategy_sha256=None))
    assert result["outcome"] == "OUT_OF_SCOPE"
    assert triage.EXIT[result["outcome"]] == 2


@pytest.mark.parametrize("field", ["customer_name", "name", "email", "contact", "phone", "code", "data"])
def test_the_form_has_no_field_for_personal_data(field):
    assert field not in json.dumps(triage.SCHEMA["properties"])
    result = triage.triage(changed(**{field: "x"}))
    assert result["outcome"] == "NEEDS_INFO" and "SCHEMA_INVALID" in result["reasons"]


def test_every_reason_triage_can_emit_has_a_rubric_entry():
    source = (INTAKE / "triage.py").read_text(encoding="utf-8")
    import re
    emitted = set(re.findall(r'"([A-Z_]{4,})(?::|")', source)) - {"ACCEPT", "NEEDS_INFO", "OUT_OF_SCOPE", "NO_CLAIM"}
    assert emitted and emitted <= set(triage.RUBRIC["reasons"])
    for entry in triage.RUBRIC["reasons"].values():
        assert entry["outcome"] in triage.RUBRIC["precedence"] and entry["message"]


def test_the_form_says_no_secrets_and_the_lane_has_no_service_or_database():
    form = (INTAKE / "INTAKE_FORM.md").read_text(encoding="utf-8")
    assert "Never send an API key, secret, password or any exchange credential" in form
    names = {p.name for p in INTAKE.iterdir()}
    assert names == {"INTAKE_FORM.md", "CHECKLIST.md", "intake.schema.json", "rubric.json", "triage.py",
                     "example_intake.json"}
    source = (INTAKE / "triage.py").read_text(encoding="utf-8")
    for forbidden in ("sqlite3", "http.server", "flask", "fastapi", "socket", "requests"):
        assert f"import {forbidden}" not in source
