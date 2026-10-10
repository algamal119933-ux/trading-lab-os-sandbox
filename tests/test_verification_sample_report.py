"""CV-01: the sample verification report is reproducible from its pinned inputs.

PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("verification_report", REPO_ROOT / "verification" / "report.py")
report = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(report)

CASE = json.loads(report.SAMPLE_CASE.read_text(encoding="utf-8"))


def test_the_committed_report_is_exactly_what_its_inputs_render():
    assert report.render(CASE) == report.SAMPLE_REPORT.read_text(encoding="utf-8")
    assert report.main([]) == 0


def test_rendering_is_deterministic():
    assert report.render(CASE) == report.render(CASE)


def test_a_drifted_input_refuses_to_render(tmp_path):
    for spec in CASE["inputs"].values():
        dest = tmp_path / spec["path"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO_ROOT / spec["path"], dest)
    assert report.render(CASE, tmp_path) == report.render(CASE)
    result = tmp_path / CASE["inputs"]["result"]["path"]
    result.write_text(result.read_text(encoding="utf-8").replace("20.02157908", "40.02157908"), encoding="utf-8")
    with pytest.raises(report.InputDrift):
        report.render(CASE, tmp_path)


def test_every_input_is_committed_evidence_outside_the_lane():
    for spec in CASE["inputs"].values():
        assert (REPO_ROOT / spec["path"]).is_file()
        assert not spec["path"].startswith("verification/")


def test_the_strategy_licence_and_source_are_pinned_by_commit():
    pins = json.loads((REPO_ROOT / CASE["inputs"]["pins"]["path"]).read_text(encoding="utf-8"))
    source = pins["sources"][CASE["source_key"]]
    assert len(source["commit"]) == 40
    assert source["license"]["spdx"] == "GPL-3.0"
    paths = {f["path"] for f in source["files"]}
    assert {"LICENSE", CASE["strategy_file"], CASE["params_file"]} <= paths


def test_no_upstream_source_is_vendored_into_the_lane():
    import hashlib

    pins = json.loads((REPO_ROOT / CASE["inputs"]["pins"]["path"]).read_text(encoding="utf-8"))
    upstream = {f["sha256"] for src in pins["sources"].values() for f in src["files"] if f.get("sha256")}
    assert len(upstream) > 10
    sample = REPO_ROOT / "verification" / "sample"
    assert not [p for p in sample.rglob("*.py")], "the sample holds no code"
    for path in (p for p in (REPO_ROOT / "verification").rglob("*") if p.is_file()):
        assert hashlib.sha256(path.read_bytes()).hexdigest() not in upstream, path


def test_the_report_states_its_limits():
    text = report.SAMPLE_REPORT.read_text(encoding="utf-8")
    for needle in ("not investment advice", "nothing here was traded with real money", "NOT TESTED LIKE-FOR-LIKE",
                   "EDGE                        NOT DEMONSTRATED", "Fair comparison", "Limits of this report",
                   "CONTROLLED_RE_DERIVATION_REQUIRED"):
        assert needle in text, needle


def test_the_sample_case_carries_no_customer_fields():
    assert CASE["kind"] == "PUBLIC_SAMPLE"
    forbidden = {"customer", "customer_name", "email", "contact", "api_key", "secret"}
    assert not forbidden & set(CASE)
