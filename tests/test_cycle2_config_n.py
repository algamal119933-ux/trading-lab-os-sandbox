"""CYCLE-2 UNIT 7.2 PART A — the N LAW (research/cycle2/config_n.py).

family_configuration_N counts DISTINCT configuration identities, never trial
IDs. Fixture ledgers are temporary files built with research/trial_ledger.py
under a temporary repo root; the canonical ledger is only ever read.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from cycle2 import config_n
from trial_ledger import TrialLedger

REPO_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_LEDGER = REPO_ROOT / "research" / "records" / "trial_ledger.jsonl"
PREREG_DIR = REPO_ROOT / "research" / "cycle2" / "prereg"
NULL_PREREGS = ("TRIAL-C2-NULL-MATCHFREQ-1.json", "TRIAL-C2-NULL-BLOCKSHUF-1.json")
FAMILY = "FIXTURE_FAMILY"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def root(tmp_path):
    """A temporary repo root carrying the real closure record (so its pin holds)."""
    (tmp_path / "research").mkdir()
    shutil.copyfile(REPO_ROOT / config_n.CLOSURE_RECORD, tmp_path / config_n.CLOSURE_RECORD)
    (tmp_path / "research" / "cycle2" / "prereg").mkdir(parents=True)
    return tmp_path


def prereg(trial_id: str, grid: list[dict], *, family: str = FAMILY, strategy_sha: str = "a" * 64,
           fixtures: list[dict] | None = None) -> dict:
    return {"trial_id": trial_id, "family_id": family,
            "strategy": {"name": "S", "file": "research/s.py", "sha256": strategy_sha},
            "fixture_files": fixtures if fixtures is not None else [],
            "grid": grid}


def cfg(cid: str, params: dict, gated: bool = False) -> dict:
    return {"config_id": cid, "params": params, "regime_gated": gated}


def write_prereg(root: Path, p: dict) -> tuple[str, str]:
    rel = f"research/cycle2/prereg/{p['trial_id']}.json"
    (root / rel).write_text(json.dumps(p, sort_keys=True), encoding="utf-8")
    return rel, _sha(root / rel)


def payload(p: dict, *, rel: str | None, sha: str | None, state: str = "PREREGISTERED", n: int = 0) -> dict:
    out = {"schema_version": "1.0.0", "family_id": p["family_id"], "lineage_id": f"{p['family_id']}/L2",
           "candidate_id": "C", "config_id": "C/GRID", "experiment_id": f"EXP-CYCLE2-CAL-FIX{n}",
           "run_id": f"RUN-{p['trial_id']}", "trial_id": p["trial_id"], "state": state,
           "purpose": "unit-test fixture ledger; not a research trial",
           "dataset_identity": {k: v for k, v in (("prereg_file", rel), ("prereg_sha256", sha)) if v}}
    if state != "PREREGISTERED":
        out["outcome"] = {"reason": "fixture", "engine_invocations": 0}
    return out


def ledger(tmp: Path, *payloads: dict) -> Path:
    path = tmp / "ledger.jsonl"
    led = TrialLedger(path)
    for i, p in enumerate(payloads):
        led.append(p, recorded_utc=f"2026-10-01T00:00:{i:02d}Z")
    return path


def bound(root: Path, *preregs: dict) -> Path:
    payloads = []
    for i, p in enumerate(preregs):
        rel, sha = write_prereg(root, p)
        payloads.append(payload(p, rel=rel, sha=sha, n=i))
    return ledger(root, *payloads)


def n_of(root: Path, ledger_path: Path, family: str = FAMILY, extra=()) -> dict:
    return config_n.family_configuration_n(family, ledger_path=ledger_path, extra_preregs=list(extra),
                                           repo_root=root)


# -- the canonical result -----------------------------------------------------------------


def test_pipeline_null_calibration_n_is_2_on_the_real_ledger():
    out = config_n.family_configuration_n("PIPELINE_NULL_CALIBRATION", ledger_path=CANONICAL_LEDGER)
    assert out["status"] == "EVALUATED"
    assert out["family_configuration_N"] == 2
    # six Cycle-1 null trial IDs (plus any Cycle-2 ones) — and still N = 2
    assert out["derivation"]["trial_id_count_not_n"] >= 6


@pytest.mark.parametrize("name", NULL_PREREGS)
def test_each_null_preregistration_freezes_the_recomputed_n(name):
    p = json.loads((PREREG_DIR / name).read_text())
    out = config_n.family_configuration_n("PIPELINE_NULL_CALIBRATION", ledger_path=CANONICAL_LEDGER,
                                          extra_preregs=[p])
    assert out["status"] == "EVALUATED"
    assert out["family_configuration_N"] == 2 == p["multiple_testing"]["effective_trials"]
    # the Cycle-2 identity IS one of the two Cycle-1 design identities: same bytes, same configuration
    assert set(out["derivation"]["cycle2_distinct_identities"]) <= set(out["derivation"]["cycle1"]["identities"])


def test_both_null_preregistrations_together_still_give_2():
    preregs = [json.loads((PREREG_DIR / n).read_text()) for n in NULL_PREREGS]
    out = config_n.family_configuration_n("PIPELINE_NULL_CALIBRATION", ledger_path=CANONICAL_LEDGER,
                                          extra_preregs=preregs)
    assert out["family_configuration_N"] == 2
    assert len(out["derivation"]["cycle2_distinct_identities"]) == 2


def test_the_cycle1_null_identities_come_from_the_fixtures_on_disk():
    for design, strat, sched in [
        ("NULL_MATCHED_FREQUENCY", "NullControlMatchedFrequency.py", "null_matched_frequency_schedule.json"),
        ("NULL_BLOCK_SHUFFLED", "NullControlBlockShuffled.py", "null_block_shuffled_schedule.json"),
    ]:
        d = next(x for x in config_n.CYCLE1_FAMILIES["PIPELINE_NULL_CALIBRATION"]["designs"]
                 if x["design"] == design)
        assert d["strategy_sha256"] == _sha(REPO_ROOT / "research" / "null_controls" / strat)
        assert d["fixture_sha256s"] == [_sha(REPO_ROOT / "research" / "null_controls" / sched)]


def test_the_cycle1_table_matches_the_closure_record_text():
    text = (REPO_ROOT / config_n.CLOSURE_RECORD).read_text(encoding="utf-8")
    assert _sha(REPO_ROOT / config_n.CLOSURE_RECORD) == config_n.CLOSURE_SHA256
    for entry in config_n.CYCLE1_FAMILIES.values():
        assert entry["closure_text"] in text


# -- trial IDs are not N ----------------------------------------------------------------------


def test_many_trials_of_one_configuration_are_n_1(root):
    same = [cfg("CFG1", {"buy": {"x": 1}})]
    path = bound(root, *[prereg(f"TRIAL-FIX-{i}", same) for i in range(5)])
    out = n_of(root, path)
    assert out["family_configuration_N"] == 1
    assert out["derivation"]["trial_id_count_not_n"] == 5


def test_rerunning_an_identical_configuration_is_not_a_new_configuration(root):
    path = bound(root, prereg("TRIAL-FIX-1", [cfg("A", {"buy": {"x": 1}})]))
    rerun = prereg("TRIAL-FIX-2", [cfg("RENAMED", {"buy": {"x": 1}}, gated=False)])
    assert n_of(root, path, extra=[rerun])["family_configuration_N"] == 1


def test_robustness_neighbours_and_regime_gated_variants_count(root):
    grid = [cfg("C", {"buy": {"x": 10}}), cfg("N1", {"buy": {"x": 9}}), cfg("N2", {"buy": {"x": 11}}),
            cfg("G", {"buy": {"x": 10, "gate": "trend"}}, gated=True)]
    path = bound(root, prereg("TRIAL-FIX-1", grid))
    assert n_of(root, path)["family_configuration_N"] == 4


def test_the_evaluated_trial_is_included(root):
    path = bound(root, prereg("TRIAL-FIX-1", [cfg("A", {"buy": {"x": 1}})]))
    new = prereg("TRIAL-FIX-2", [cfg("B", {"buy": {"x": 2}})])
    assert n_of(root, path)["family_configuration_N"] == 1
    assert n_of(root, path, extra=[new])["family_configuration_N"] == 2


def test_a_different_fixture_or_strategy_is_a_different_configuration(root):
    a = prereg("TRIAL-FIX-1", [cfg("A", {})], fixtures=[{"path": "research/f.json", "sha256": "1" * 64}])
    b = prereg("TRIAL-FIX-2", [cfg("A", {})], fixtures=[{"path": "research/f.json", "sha256": "2" * 64}])
    c = prereg("TRIAL-FIX-3", [cfg("A", {})], strategy_sha="b" * 64,
               fixtures=[{"path": "research/f.json", "sha256": "1" * 64}])
    assert n_of(root, bound(root, a, b, c))["family_configuration_N"] == 3


def test_identity_ignores_fixture_order_and_the_strategy_file_itself():
    s = "a" * 64
    one = prereg("T", [cfg("A", {})], strategy_sha=s,
                 fixtures=[{"path": "research/s.py", "sha256": s}, {"path": "research/f.json", "sha256": "1" * 64},
                           {"path": "research/g.json", "sha256": "2" * 64}])
    two = prereg("T", [cfg("A", {})], strategy_sha=s,
                 fixtures=[{"path": "research/g.json", "sha256": "2" * 64},
                           {"path": "research/f.json", "sha256": "1" * 64}])
    assert config_n.prereg_identities(one) == config_n.prereg_identities(two)


# -- fail-closed ------------------------------------------------------------------------------


def test_a_missing_prereg_file_makes_n_not_evaluable(root):
    p = prereg("TRIAL-FIX-1", [cfg("A", {"buy": {"x": 1}})])
    path = ledger(root, payload(p, rel="research/cycle2/prereg/ABSENT.json", sha="0" * 64))
    out = n_of(root, path)
    assert out["status"] == "NOT_EVALUABLE" and out["family_configuration_N"] is None
    assert "missing" in out["reason"]


def test_a_prereg_file_changed_after_binding_makes_n_not_evaluable(root):
    p = prereg("TRIAL-FIX-1", [cfg("A", {"buy": {"x": 1}})])
    path = bound(root, p)
    (root / "research/cycle2/prereg/TRIAL-FIX-1.json").write_text("{}", encoding="utf-8")
    out = n_of(root, path)
    assert out["status"] == "NOT_EVALUABLE"
    assert "does not hash" in out["reason"]


def test_a_ledger_record_without_a_prereg_binding_makes_n_not_evaluable(root):
    p = prereg("TRIAL-FIX-1", [cfg("A", {"buy": {"x": 1}})])
    out = n_of(root, ledger(root, payload(p, rel=None, sha=None)))
    assert out["status"] == "NOT_EVALUABLE"


def test_an_unreadable_grid_makes_n_not_evaluable(root):
    p = prereg("TRIAL-FIX-1", [{"config_id": "A"}])
    out = n_of(root, bound(root, p))
    assert out["status"] == "NOT_EVALUABLE"
    assert "unresolvable" in out["reason"]


def test_a_count_only_cycle1_family_sharing_a_strategy_file_is_not_evaluable(root, tmp_path):
    ema = config_n.CYCLE1_FAMILIES["BTSL_EMA_REGIME"]["strategy_sha256s"][0]
    same = prereg("TRIAL-FIX-1", [cfg("A", {"buy": {"x": 1}})], family="BTSL_EMA_REGIME", strategy_sha=ema)
    out = n_of(root, bound(root, same), family="BTSL_EMA_REGIME")
    assert out["status"] == "NOT_EVALUABLE"
    assert "overlap cannot be ruled out" in out["reason"]


def test_a_count_only_cycle1_family_adds_its_count_to_new_strategy_configurations(root):
    new = prereg("TRIAL-FIX-1", [cfg("A", {"buy": {"x": 1}}), cfg("B", {"buy": {"x": 2}})],
                 family="MEAN_REVERSION", strategy_sha="c" * 64)
    out = n_of(root, bound(root, new), family="MEAN_REVERSION")
    assert out["status"] == "EVALUATED"
    assert out["family_configuration_N"] == 4 + 2


def test_a_closure_record_mismatch_refuses(root):
    path = bound(root, prereg("TRIAL-FIX-1", [cfg("A", {"buy": {"x": 1}})]))
    record = root / config_n.CLOSURE_RECORD
    record.write_text(record.read_text(encoding="utf-8") + "\nedited\n", encoding="utf-8")
    with pytest.raises(config_n.ConfigNRefusal, match="sha256"):
        n_of(root, path)


def test_a_null_family_ledger_without_the_cycle1_design_records_refuses(root):
    p = prereg("TRIAL-FIX-1", [cfg("A", {})], family="PIPELINE_NULL_CALIBRATION")
    with pytest.raises(config_n.ConfigNRefusal, match="not in the ledger"):
        n_of(root, bound(root, p), family="PIPELINE_NULL_CALIBRATION")


def test_a_ledger_that_does_not_verify_refuses(root):
    path = bound(root, prereg("TRIAL-FIX-1", [cfg("A", {"buy": {"x": 1}})]),
                 prereg("TRIAL-FIX-2", [cfg("A", {"buy": {"x": 2}})]))
    lines = path.read_text().splitlines()
    path.write_text(lines[1] + "\n" + lines[0] + "\n")
    with pytest.raises(config_n.ConfigNRefusal, match="does not verify"):
        n_of(root, path)


def test_n_never_reads_trial_count_or_writes_the_ledger(root):
    path = bound(root, prereg("TRIAL-FIX-1", [cfg("A", {"buy": {"x": 1}})]))
    before = path.read_bytes()
    n_of(root, path)
    assert path.read_bytes() == before
    source = Path(config_n.__file__).read_text()
    assert ".append(p" not in source and "ledger_family_trial_count" not in source


# -- determinism and the CLI ------------------------------------------------------------------


def _cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(REPO_ROOT / "research" / "cycle2" / "config_n.py"), *args],
                          capture_output=True, text=True, cwd=REPO_ROOT)


def test_the_cli_is_deterministic_across_two_processes():
    a, b = _cli("--family", "PIPELINE_NULL_CALIBRATION"), _cli("--family", "PIPELINE_NULL_CALIBRATION")
    assert a.returncode == 0 == b.returncode, a.stderr
    assert a.stdout == b.stdout
    assert json.loads(a.stdout)["family_configuration_N"] == 2


def test_the_cli_exits_3_when_not_evaluable(root):
    p = prereg("TRIAL-FIX-1", [cfg("A", {"buy": {"x": 1}})])
    path = ledger(root, payload(p, rel="research/cycle2/prereg/ABSENT.json", sha="0" * 64))
    proc = _cli("--family", FAMILY, "--ledger", str(path))
    assert proc.returncode == 3, proc.stderr
    assert json.loads(proc.stdout)["status"] == "NOT_EVALUABLE"
