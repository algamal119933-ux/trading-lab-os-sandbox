"""AUTH-2 records (FUNNEL_LAW_2.md §FINAL_AUTH2_SPEC "Records the package needs"): the funnel
law, the preregistrations and the charter equal what the code produces, every safety constant
is pinned, the trial ledger binds every preregistration, and the Cycle-2 errata changes nothing
it must not.

PAPER / RESEARCH ONLY.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

pytest.importorskip("numpy")
jsonschema = pytest.importorskip("jsonschema")

from auth2 import make_preregs as MP  # noqa: E402
from auth2 import run_node as RN  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
PROGRAM = json.loads((REPO / RN.PROGRAM_REL).read_text())
LAW = (REPO / "research/auth2/FUNNEL_LAW_2.md").read_text()


def sha(rel: str) -> str:
    return hashlib.sha256((REPO / rel).read_bytes()).hexdigest()


def test_committed_preregistrations_and_charter_are_exactly_what_the_code_produces():
    assert MP.main(["--check"]) == 0


def test_every_preregistration_validates_and_is_paper_only():
    schema = json.loads((REPO / "research/auth2/prereg.schema.json").read_text())
    v = jsonschema.validators.validator_for(schema)(schema)
    pres = sorted((REPO / MP.PREREG_DIR).glob("*.json"))
    assert [p.stem for p in pres] == sorted(RN.NODES)
    for p in pres:
        pre = json.loads(p.read_text())
        assert list(v.iter_errors(pre)) == [], p.name
        assert (pre["dry_run"], pre["real_money_authorized"], pre["hyperopt"], pre["llm_agent_tokens"]) == \
            (True, False, 0, 0)
        assert pre["engine"]["image"] == "freqtradeorg/freqtrade:2026.7"
        assert pre["funnel_law"]["sha256"] == sha("research/auth2/FUNNEL_LAW_2.md")
        assert pre["dataset_lock"]["sha256"] == sha("research/datasets/dataset_v3.lock.json")
        assert pre["requirements"]["sha256"] == sha("research/auth2/requirements-auth2.txt")


def test_the_charter_pins_every_preregistration_and_the_caps():
    for n in PROGRAM["dag"]["nodes"]:
        assert n["prereg_sha256"] == sha(n["prereg_path"]), n["id"]
    assert PROGRAM["caps"] == {"configurations": 16, "scientific_trial_ids": 5, "calibration_trial_ids": 12,
                               "engine_invocations": 240, "hyperopt": 0, "attributed_linux_minutes": 4000,
                               "paid_actions_overage_usd": 0, "llm_agent_tokens": 0}
    assert [f["inherited_n"] for f in PROGRAM["families"]] == [15, 0, 0]
    assert len(PROGRAM["dag"]["nodes"]) == 17 and PROGRAM["terminal"] == "closure_record"
    assert PROGRAM["frozen_hashes"]["funnel_law"]["sha256"] == sha("research/auth2/FUNNEL_LAW_2.md")


def test_the_funnel_law_carries_every_package_section_and_the_omissions_are_named():
    for section in ("## FINAL_AUTH2_SPEC", "## PRIMARY_CONFIGS", "## ROBUSTNESS_PERTURBATIONS",
                    "## Matched benchmarks", "## COMMON_GATES (C1–C12)", "## A1_SPECIFIC_GATES",
                    "## A2_SPECIFIC_GATES", "## A3_SPECIFIC_GATES", "## POINT_IN_TIME_UNIVERSE_LAW",
                    "## A3_VALID_WINDOW", "## CALIBRATION_DAG", "## MULTIPLE_TESTING_LAW", "## BOOTSTRAP_RULE",
                    "## REPLAY_EVALUATOR_CONTRACT", "## CALIBRATION_POWER_PROOF", "## COMPUTE_CAP_PROOF",
                    "## MONTHLY_BILLING_PACING_RULE", "## DAG_OPERATIONS"):
        assert section in LAW, section
    for absent in ("## PAPER_R1_RULE", "## Real-money ladder", "## ERRATA_DRAFT", "### Planning pre-check"):
        assert absent not in LAW, absent
    assert "eda2d62b6b631bd4b3ddfaa67ea4f7e528ec1cb42a863d1af2cb69c03d099361" in LAW  # the package's sha256


def test_the_ledger_binds_every_preregistration_and_records_no_outcome():
    from trial_ledger import TrialLedger

    led = TrialLedger(REPO / RN.LEDGER_REL)
    assert led.verify() == []
    want = {t: {n["id"]: n["prereg_sha256"] for n in PROGRAM["dag"]["nodes"] if n["trial_id"] == t}
            for t in {n["trial_id"] for n in PROGRAM["dag"]["nodes"]}}
    assert len(want) == 14
    present = [t for t in want if led.preregistration_for(t) is not None]
    # all or nothing: the 14 records are appended together, in a commit after the charter's, and
    # only once every preregistration is final (an appended record can never be re-appended)
    assert len(present) in (0, 14), present
    if not present:
        pytest.skip("AUTH-2 PREREGISTERED records are not appended yet (they follow the charter commit)")
    for trial, preregs in want.items():
        pre = led.preregistration_for(trial)
        assert pre is not None, trial
        assert pre.payload["dataset_identity"]["preregs"] == preregs
        assert [r for r in led.records_for(trial_id=trial) if r.payload["state"] != "PREREGISTERED"] == []
    # each committed PREREGISTERED payload is exactly the one make_preregs derives from the charter
    for payload in MP.ledger_preregistrations({n: s for t in want.values() for n, s in t.items()}):
        assert led.preregistration_for(payload["trial_id"]).payload == payload, payload["trial_id"]


def test_the_ledger_records_are_newer_than_the_program():
    import check_research_program as crp

    assert crp.check(REPO) == []


def test_the_errata_facts_hold_on_this_tree():
    text = (REPO / "research/RESEARCH_CYCLE2_CLOSURE_1_ERRATA_1.md").read_text()
    for trial, universe in (("TRIAL-C2-NULL-MATCHFREQ-1", ["BTC/USDT"]), ("TRIAL-C2-NULL-BLOCKSHUF-1", ["BTC/USDT"]),
                            ("TRIAL-C2-TREND-DONCHIAN-1", ["BTC/USDT", "ETH/USDT"])):
        pre = json.loads((REPO / f"research/cycle2/prereg/{trial}.json").read_text())
        assert pre["pair_universe"] == universe, trial
        assert trial in text
    closure = (REPO / "research/RESEARCH_CYCLE2_CLOSURE_1.md").read_text()
    assert "Universe limits: BTC/USDT only in every Cycle-2 run" in closure  # the closure itself is not edited
    for line in ("VERDICT_CHANGE         = NONE", "RESULT_CHANGE          = NONE",
                 "LEDGER_HISTORY_CHANGE  = NONE", "FUNNEL_LAW_2_RETROACTIVE = NO"):
        assert line in text


def test_the_dataset_lock_is_frozen_and_keeps_its_generators():
    lock = json.loads((REPO / "research/datasets/dataset_v3.lock.json").read_text())
    assert lock["status"] == "frozen" and lock["market_data_committed"] is False
    assert lock["real_money_authorized"] is False and lock["market_type"] == "spot"
    for name, digest in lock["generator_code_sha256"].items():
        assert sha(f"research/auth2/{name}") == digest, name
    assert lock["data_limited"] == {"A1": False, "A2": False, "A3": False}


def test_requirements_are_hash_pinned():
    lines = [l for l in (REPO / "research/auth2/requirements-auth2.txt").read_text().splitlines()
             if l.strip() and not l.lstrip().startswith("#")]
    reqs = [l for l in lines if "==" in l]
    assert any(l.startswith("arch==8.0.0") for l in reqs)
    text = (REPO / "research/auth2/requirements-auth2.txt").read_text()
    for l in reqs:
        name = l.split("==")[0]
        block = text.split(l, 1)[1].split("==", 1)[0]
        assert "--hash=sha256:" in l or "--hash=sha256:" in block, name


def test_the_ledger_only_appends_to_main():
    import subprocess

    def git(*a):
        return subprocess.run(["git", "-C", str(REPO), *a], capture_output=True, text=True)

    base = next((r.stdout.strip() for ref in ("origin/main", "main")
                 if (r := git("merge-base", "HEAD", ref)).returncode == 0), None)
    if base is None:
        pytest.skip("no main reference in this checkout")
    before = git("show", f"{base}:{RN.LEDGER_REL}")
    assert before.returncode == 0, before.stderr
    assert (REPO / RN.LEDGER_REL).read_text().startswith(before.stdout)
