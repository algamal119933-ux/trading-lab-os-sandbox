"""CYCLE-2 UNIT 7.2 PART A — static checks of .github/workflows/cycle2_research.yml.

Nothing here dispatches or runs the workflow; it is parsed and read only.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "cycle2_research.yml"
PREREGS = ["research/cycle2/prereg/TRIAL-C2-NULL-MATCHFREQ-1.json",
           "research/cycle2/prereg/TRIAL-C2-NULL-BLOCKSHUF-1.json",
           "research/cycle2/prereg/TRIAL-C2-TREND-DONCHIAN-1.json"]


@pytest.fixture(scope="module")
def wf() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def steps(wf) -> list[dict]:
    (job,) = wf["jobs"].values()
    return job["steps"]


def _index(steps: list[dict], needle: str) -> int:
    hits = [i for i, s in enumerate(steps) if needle in s.get("run", "")]
    assert len(hits) == 1, (needle, hits)
    return hits[0]


def test_the_only_trigger_is_manual_dispatch(wf):
    on = wf.get("on", wf.get(True))  # PyYAML reads a bare `on:` key as True
    assert list(on) == ["workflow_dispatch"]
    for forbidden in ("push", "pull_request", "pull_request_target", "schedule", "workflow_run",
                      "repository_dispatch", "workflow_call"):
        assert forbidden not in on


def test_the_input_is_a_choice_of_exactly_the_preregistered_trials(wf):
    inputs = wf.get("on", wf.get(True))["workflow_dispatch"]["inputs"]
    assert list(inputs) == ["prereg"]
    assert inputs["prereg"]["type"] == "choice" and inputs["prereg"]["required"] is True
    assert inputs["prereg"]["options"] == PREREGS
    for p in PREREGS:
        assert (REPO_ROOT / p).is_file()


def test_permissions_are_contents_read_only(wf):
    assert wf["permissions"] == {"contents": "read"}
    (job,) = wf["jobs"].values()
    assert "permissions" not in job


def test_runs_are_serialised_and_never_cancelled(wf):
    assert wf["concurrency"]["cancel-in-progress"] is False


def test_no_secret_token_or_write_path_is_used(text):
    lowered = text.lower()
    for needle in ("secrets.", "github_token", "token:", "contents: write", "git commit", "git push",
                   "gh workflow", "trial_ledger", "ledger.append", "--dry-run"):
        assert needle not in lowered, needle


def test_the_cycle2_requirements_are_installed_hash_checked(steps):
    _index(steps, "pip install --require-hashes --no-deps -r research/requirements-cycle2.txt")


def test_one_preregistration_per_dispatch(wf, steps, text):
    (job,) = wf["jobs"].values()
    assert "strategy" not in job and "matrix:" not in text
    assert _index(steps, "research/cycle2/driver.py --prereg \"$PREREG\"") >= 0
    runs = "\n".join(s.get("run", "") for s in steps)
    assert runs.count("research/cycle2/driver.py") == 1
    # the preregistered trial IDs appear together only in the allowlist of the resolve step
    both = [s for s in steps if all(p in s.get("run", "") for p in PREREGS)]
    assert len(both) == 1 and "case \"$PREREG\" in" in both[0]["run"]
    assert "for " not in both[0]["run"]


def test_every_gate_precedes_the_driver_and_the_funnel_follows_it(steps):
    driver = _index(steps, "research/cycle2/driver.py")
    for gate in ("generate_schedules.py --check", "scripts/paper_guard.py --config freqtrade/user_data/config.research.json",
                 "reproduction_identity.json", "scripts/audit_data.py", "--gate lock",
                 "scripts/join_warmup_overlay.py", "docker pull \"$IMAGE\"", "lookahead-analysis",
                 "recursive-analysis"):
        assert _index(steps, gate) < driver, gate
    assert _index(steps, "research/cycle2/funnel.py") > driver


def test_the_engine_image_is_pinned(wf):
    assert wf["env"]["IMAGE"] == "freqtradeorg/freqtrade:2026.7"


def test_every_artifact_is_uploaded_always(steps):
    upload = [s for s in steps if str(s.get("uses", "")).startswith("actions/upload-artifact")]
    assert len(upload) == 1 and upload[0]["if"] == "always()"
    assert upload[0]["with"]["path"] == "artifacts"


def test_the_input_reaches_scripts_only_through_the_environment(steps):
    for s in steps:
        assert "${{ inputs." not in s.get("run", "")


# -- PRE-FREEZE REVISION: the exposure-matched passive benchmark -----------------------------------

BENCH = "freqtrade/user_data/baseline_benchmarks.py"


def _bench_steps(steps: list[dict]) -> list[dict]:
    return [s for s in steps if BENCH in s.get("run", "")]


def test_one_benchmark_step_per_eval_fold_and_fee_level(steps):
    bench = [s for s in _bench_steps(steps) if "--period robustness" not in s["run"]]
    assert len(bench) == 4
    pairs = sorted((s["run"].split("--period ")[1].split()[0], s["env"]["FEE"].split(".")[-1].strip(" }"))
                   for s in bench)
    assert pairs == [("fold1_eval", "fee_base"), ("fold1_eval", "fee_stress"),
                     ("fold2_eval", "fee_base"), ("fold2_eval", "fee_stress")]
    for s in bench:
        assert "if" not in s


def test_l4_robustness_benchmark_runs_only_with_a_preregistered_criterion(steps):
    """UNIT 7.3: one base-fee passive line over the robustness window, gated on parameter_robustness."""
    (step,) = [s for s in _bench_steps(steps) if "--period robustness" in s["run"]]
    assert step["if"] == "steps.bench.outputs.has_robustness == 'true'"
    assert step["env"]["FEE"] == "${{ steps.bench.outputs.fee_base }}"
    assert '--out "artifacts/benchmarks/robustness_fee$TAG.json"' in step["run"]
    derive = steps[_index(steps, "artifacts/cycle2_eval_windows.json\").write_text")]["run"]
    assert 'has_robustness = "parameter_robustness" in prereg' in derive
    assert 'prereg["robustness_window"]' in derive and '["robustness"]' in derive


def test_the_benchmark_runs_after_the_driver_and_before_the_funnel(steps):
    driver = _index(steps, "research/cycle2/driver.py")
    funnel = _index(steps, "research/cycle2/funnel.py")
    for s in _bench_steps(steps):
        assert driver < steps.index(s) < funnel
    derive = _index(steps, "artifacts/cycle2_eval_windows.json\").write_text")
    assert driver < derive < min(steps.index(s) for s in _bench_steps(steps))
    assert "--benchmark-dir artifacts/benchmarks" in steps[funnel]["run"]


def test_the_benchmark_uses_the_same_window_fee_universe_wallet_and_sizing(steps):
    derive = steps[_index(steps, "artifacts/cycle2_eval_windows.json\").write_text")]
    run = derive["run"]
    # windows come from the preregistered folds, matching the summariser's window (00:00 .. 23:00)
    assert 'prereg["folds"]' in run and "23:00:00" in run and "00:00:00" in run
    assert 'prereg["fee_levels"]["base"]' in run and 'prereg["fee_levels"]["stress"][0]' in run
    assert 'prereg["pair_universe"]' in run and 'prereg["wallet"]' in run
    assert 'config["stake_amount"]' in run and 'config["max_open_trades"]' in run
    assert "config.research.json" in run
    for s in _bench_steps(steps):
        r = s["run"]
        assert "--lock artifacts/cycle2_eval_windows.json" in r
        for flag, var in (("--fee", "$FEE"), ("--wallet", "$WALLET"), ("--stake", "$STAKE"),
                          ("--max-open-trades", "$MOT"), ("--universe", "$UNIVERSE")):
            assert f'{flag} "{var}"' in r
        assert '--out "artifacts/benchmarks/' in r
        assert all(v.startswith("${{ steps.bench.outputs.") for v in s["env"].values())


def test_the_benchmark_code_itself_is_not_changed_by_the_workflow(text):
    assert "sed -i" not in text and "> freqtrade/user_data/baseline_benchmarks.py" not in text
