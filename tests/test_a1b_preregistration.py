"""A1B-PREREGISTRATION-1: the frozen A1b spec is intact, complete and inside the paper/research boundary.

Synthetic-free and offline: reads only committed files. Nothing here runs a backtest, downloads data or
touches a runtime. PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "research" / "a1b"
SPEC = DIR / "a1b_prereg.json"
SUMS = DIR / "SHA256SUMS"
DOC = DIR / "A1B_PREREGISTRATION_1.md"


@pytest.fixture(scope="module")
def spec() -> dict:
    return json.loads(SPEC.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_the_spec_digest_matches_its_frozen_record():
    line = SUMS.read_text(encoding="utf-8").strip()
    digest, name = line.split("  ")
    assert name == "a1b_prereg.json"
    assert _sha(SPEC) == digest, "a1b_prereg.json changed after it was frozen; a frozen spec is never edited"


def test_the_spec_is_canonical_json():
    raw = SPEC.read_bytes()
    canonical = (json.dumps(json.loads(raw), indent=1, sort_keys=True, ensure_ascii=False) + "\n").encode()
    assert raw == canonical


def test_every_required_field_is_present(spec):
    required = {"schema_version", "prereg_id", "authority", "identity", "hypothesis", "signal",
                "declared_changes_from_a1", "universe", "rebalance_rule", "open_inputs", "costs", "wallets",
                "variants", "baselines", "data", "windows_utc", "gates", "multiple_testing", "terminal_states",
                "stop_rules", "caps", "selection_debt_disclosure", "drawdown_note", "citations",
                "code_sha256", "non_claims", "prospective_plan"}
    assert required <= set(spec), sorted(required - set(spec))
    for gate in ("E0_DATA", "E1_CAUSALITY", "E2_PARITY", "E3_FEASIBILITY", "E4_PAPER_GUARD", "E5_SCREEN",
                 "E6_ROBUSTNESS", "E7_PBO", "E8_DSR", "E9_EXPOSURE", "E10_SAMPLE_PERIOD", "E11_HOLDOUT"):
        assert gate in spec["gates"]


def test_the_paper_research_boundary_holds(spec):
    assert spec["dry_run"] is True
    assert spec["hyperopt"] == 0 and spec["caps"]["hyperopt"] == 0
    for flag in ("real_money_authorized", "paper_launch_authorized", "h1_launch_authorized",
                 "leverage", "futures", "shorts", "margin", "exchange_keys"):
        assert spec[flag] is False, flag
    assert spec["universe"]["long_only"] is True
    assert spec["universe"]["market_type"] == "spot"
    assert spec["rebalance_rule"]["gross_exposure_cap"] <= 1.0
    text = SPEC.read_text(encoding="utf-8").lower()
    for forbidden in ('"dry_run": false', "api_key", "api_secret", "secret_key", "withdraw"):
        assert forbidden not in text, forbidden


def test_the_signal_is_a1s_unchanged(spec):
    a1 = json.loads((ROOT / "research/auth2/prereg/A1.json").read_text(encoding="utf-8"))["configurations"]["primary"]
    sig = spec["signal"]
    assert sig["lookbacks_days"] == a1["lookbacks"]
    assert sig["target_vol"] == a1["target_vol"]
    assert sig["vol_window_days"] == a1["vol_window"]
    assert spec["costs"]["base_fee_per_side"] == 0.0015


def test_every_pinned_file_still_has_its_frozen_digest(spec):
    for rel, digest in spec["code_sha256"].items():
        assert _sha(ROOT / rel) == digest, f"{rel} changed since A1b was preregistered"


def test_the_variant_set_is_small_and_only_v1_can_be_a_candidate(spec):
    v = spec["variants"]
    ids = sorted(k for k in v if k.startswith("V"))
    assert ids == ["V1", "V2", "V3", "V4"]
    assert v["count_toward_n"] == len(ids) == spec["caps"]["configurations"] <= 4
    assert [k for k in ids if v[k]["role"] == "PRIMARY"] == ["V1"]
    assert all(v[k]["role"] == "REJECT_ONLY_PERTURBATION" for k in ids if k != "V1")
    assert all(1 <= v[k]["rank_cap"] <= 6 and v[k]["sleeves"] == v[k]["rank_cap"] for k in ids)
    assert 3 <= v["V1"]["rank_cap"] <= 5


def test_the_minimum_order_input_is_open_not_invented(spec):
    mn = spec["open_inputs"]["min_notional_usdt"]
    assert mn["value"] is None and mn["status"] == "OPEN_INPUT"
    assert "exchangeInfo" in mn["source_rule"] and "never chosen from a result" in mn["source_rule"]


def _t(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")


def test_the_windows_are_ordered_contiguous_and_the_holdout_is_after_dataset_v3(spec):
    w = spec["windows_utc"]
    dev, val, hold = w["development"], w["validation"], w["locked_holdout"]
    for a, b in (dev, val, hold):
        assert _t(a) < _t(b)
    assert dev[1] == val[0] and val[1] == hold[0]
    assert _t(hold[0]) >= _t("2026-09-01T00:00:00Z")  # Dataset V3 ends 2026-08-31: nothing in it was seen
    assert w["evidence_class"]["development"].startswith("HISTORICAL_EXPLORATORY")
    assert w["evidence_class"]["validation"].startswith("HISTORICAL_EXPLORATORY")
    assert w["evidence_class"]["locked_holdout"].startswith("HISTORICAL_UNSEEN")


def test_the_thresholds_are_at_least_as_strict_as_the_research_plan(spec):
    g = spec["gates"]
    assert "PBO <= 0.05" in g["E7_PBO"] and "hard gate" in g["E7_PBO"]
    assert "deflated sharpe" in g["E8_DSR"].lower() and ">= 0.95" in g["E8_DSR"]
    assert "N = max(39" in g["E8_DSR"]
    assert ">= 95%" in g["E3_FEASIBILITY"]


def test_the_document_points_at_the_frozen_digest_and_the_authority():
    doc = DOC.read_text(encoding="utf-8")
    assert "a1b_prereg.json" in doc and "SHA256SUMS" in doc
    assert "OWNER_RESEARCH_AUTHORIZATION_A1B_1.md" in doc
    assert "PROFITABILITY_VERIFICATION_LAW_1.md" in doc
    assert "REAL_MONEY_AUTHORIZED = NO" in doc and "PAPER_LAUNCH_AUTHORIZED = NO" in doc



def test_the_prospective_plan_follows_the_owner_decisions(spec):
    plan = spec["prospective_plan"]
    assert plan["alpha"] == 0.05 and plan["beta"] == 0.2 and plan["burn_in_units_min"] >= 20
    assert "[0.50, 0.75]" in plan["alternative_s"] and "DSR-deflated" in plan["alternative_s"]
    for model in ("Gaussian", "Student-t(3)", "GARCH(1,1)-t(3)", "block bootstrap"):
        assert model in plan["calibration"], model
    assert "never below Wald" in plan["calibration"]
    assert "NOT REFUTED" in plan["verdicts"] and "never live authorization" in plan["verdicts"]
    assert "no real-money, live or scaling authority follows automatically" in plan["verdicts"]
    assert "authorizes no paper or live step" in plan["binding_on"]
    assert spec["windows_utc"]["locked_holdout"] == ["2026-09-01T00:00:00Z", "2027-01-01T00:00:00Z"]
