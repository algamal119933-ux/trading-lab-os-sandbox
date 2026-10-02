"""CYCLE-2 UNIT 7.2 PART A — the frozen funnel law evaluator (research/cycle2/funnel.py).

Runs are produced by the REAL driver against a mocked subprocess (no docker, no
freqtrade, no market data): the fake engine writes a trade list per invocation
from a scenario, and the fake summariser derives the metrics from that list, so
the evaluator reads exactly the artifacts a real run would leave. Ledgers are
temporary copies of the Cycle-1 records plus fixture preregistrations; the
canonical ledger is only ever read.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from cycle2 import config_n, driver, funnel
from trial_ledger import TrialLedger

REPO_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_LEDGER = REPO_ROOT / "research" / "records" / "trial_ledger.jsonl"
NULL_PREREG = REPO_ROOT / "research" / "cycle2" / "prereg" / "TRIAL-C2-NULL-MATCHFREQ-1.json"
REGISTRY = REPO_ROOT / "research" / "external" / "candidate_registry.json"
CYCLE1_RECORDS = 20
EVAL1, EVAL2 = "20230101-20231231", "20240101-20241231"
_RUN = subprocess.run  # the real one; the driver's fixtures patch subprocess.run module-wide


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# -- a fake engine whose metrics are derived from the trades it writes ---------------------


def _trades(window: str, ret_pct: float, count: int, wallet: float = 100.0) -> list[dict]:
    start = datetime.strptime(window.split("-")[0], "%Y%m%d").replace(tzinfo=timezone.utc)
    end = datetime.strptime(window.split("-")[1], "%Y%m%d").replace(tzinfo=timezone.utc)
    span = (end - start).total_seconds() / 3600
    mean = ret_pct * wallet / 100 / max(count, 1)
    out = []
    for i in range(count):
        dev = 0.0 if (count % 2 and i == count - 1) else (0.3 + 0.1 * (i // 2 % 3)) * (1 if i % 2 == 0 else -1)
        close = start + timedelta(hours=int(span * (i + 0.5) / count))
        out.append({"pair": "BTC/USDT", "close_date": close.strftime("%Y-%m-%d %H:%M:%S+00:00"),
                    "profit_abs": mean + dev, "stake_amount": 10.0})
    return out


class Engine:
    """subprocess.run stand-in. scenario(window, fee, params) -> (return_pct, trade_count)."""

    def __init__(self, user_data: Path, scenario, *, fee_line: bool = True):
        self.user_data, self.scenario, self.fee_line, self.n = user_data, scenario, fee_line, 0
        self.calls: list[list[str]] = []

    def __call__(self, cmd, stdout=None, stderr=None, capture_output=False, text=False, check=False, **_):
        cmd = list(cmd)
        self.calls.append(cmd)
        if cmd[0] == "sudo":
            return subprocess.CompletedProcess(cmd, 0)
        if cmd[0] == "docker":
            fee = float(cmd[cmd.index("--fee") + 1])
            window = cmd[cmd.index("--timerange") + 1]
            if self.fee_line:
                stdout.write(f"freqtrade - INFO - Using fee {fee * 100:.4f}% from config.\n")
            strategy = cmd[cmd.index("--strategy") + 1]
            pfile = self.user_data / "strategies" / f"{strategy}.json"
            params = json.loads(pfile.read_text())["params"] if pfile.exists() else {}
            ret, count = self.scenario(window, fee, params)
            self.n += 1
            out = self.user_data / "backtest_results" / f"backtest-result-{self.n:04d}.json"
            out.write_text(json.dumps({"strategy": {strategy: {"trades": _trades(window, ret, count)}}}))
            os.utime(out, (1_000_000 + self.n, 1_000_000 + self.n))
            return subprocess.CompletedProcess(cmd, 0)
        if cmd[1].endswith("summarize_backtest.py"):
            result = json.loads(Path(cmd[cmd.index("--result") + 1]).read_text())
            trades = next(iter(result["strategy"].values()))["trades"]
            total = sum(t["profit_abs"] for t in trades)
            metrics = {"total_return_pct": total, "max_drawdown_pct": 2.0, "trade_count": len(trades)}
            Path(cmd[cmd.index("--out") + 1]).write_text(json.dumps(metrics))
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        raise AssertionError(f"unexpected subprocess call: {cmd}")


def scenario_by_eval(eval_rets: dict[str, float], *, trades: dict[str, int] | None = None,
                     stress_shift: float = -0.4):
    """Base-fee EVAL returns per window; stress fee shifts the return; TRAIN is a fixed loss."""
    def scenario(window, fee, params):
        count = (trades or {}).get(window, 20)
        if window in eval_rets:
            return eval_rets[window] + (stress_shift if fee > 0.001 else 0.0), count
        return -1.0 - 0.5 * len(json.dumps(params)) / 100, 40
    return scenario


LOGS = {
    "lock": "DATASET_LOCK_GATE = PASS (content matches the frozen lock)\n",
    "warm": "WARMUP_OVERLAY_JOIN = PASS\n",
    "look": ("┃ filename ┃ strategy ┃ has_bias ┃ total_signals ┃\n"
             "│ {s}.py │ {s} │       No │            20 │\n"),
    "rec": ("INFO - No variance on indicator(s) found due to recursive formula.\n"
            "INFO - No lookahead bias on indicators found.\n"),
}


class World:
    """Temporary repo root, ledger, user_data and artifacts for one evaluated trial."""

    def __init__(self, tmp: Path, monkeypatch):
        self.tmp, self.mp = tmp, monkeypatch
        self.root = tmp / "root"
        (self.root / "research" / "cycle2" / "prereg").mkdir(parents=True)
        shutil.copyfile(REPO_ROOT / config_n.CLOSURE_RECORD, self.root / config_n.CLOSURE_RECORD)
        monkeypatch.setattr(config_n, "REPO_ROOT", self.root)
        self.ledger = tmp / "ledger.jsonl"
        lines = CANONICAL_LEDGER.read_text(encoding="utf-8").splitlines(keepends=True)[:CYCLE1_RECORDS]
        self.ledger.write_text("".join(lines), encoding="utf-8")
        self.user_data = tmp / "user_data"
        (self.user_data / "strategies").mkdir(parents=True)
        (self.user_data / "backtest_results").mkdir(parents=True)
        (self.user_data / "config.research.json").write_text(json.dumps({"exchange": {"pair_whitelist": []}}))
        monkeypatch.setattr(driver, "USER_DATA", self.user_data)
        monkeypatch.setattr(driver, "STRATEGY_DIR", self.user_data / "strategies")
        monkeypatch.setattr(driver, "BACKTEST_RESULTS", self.user_data / "backtest_results")
        self.art = tmp / "artifacts"

    def bind(self, prereg: dict, *, bind: bool = True) -> Path:
        rel = f"research/cycle2/prereg/{prereg['trial_id']}.json"
        path = self.root / rel
        path.write_text(json.dumps(prereg, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if bind:
            TrialLedger(self.ledger).append({
                "schema_version": "1.0.0", "family_id": prereg["family_id"], "lineage_id": prereg["lineage_id"],
                "candidate_id": prereg["candidate_id"], "config_id": f"{prereg['candidate_id']}/GRID",
                "experiment_id": prereg["experiment_id"], "run_id": prereg["run_id"],
                "trial_id": prereg["trial_id"], "state": "PREREGISTERED",
                "purpose": "unit-test fixture ledger; not a research trial",
                "dataset_identity": {"prereg_file": rel, "prereg_sha256": _sha(path),
                                     "lineage_kind": prereg["lineage_kind"]}},
                recorded_utc="2026-10-02T00:00:00Z")
        return path

    def run(self, prereg_path: Path, scenario, **engine_kw) -> Path:
        self.mp.setattr(driver.subprocess, "run", Engine(self.user_data, scenario, **engine_kw))
        rc = driver.main(["--prereg", str(prereg_path), "--ledger", str(self.ledger),
                          "--artifacts-dir", str(self.art)])
        assert rc in (0, 1)
        return self.art / "cycle2_run_summary.json"

    def logs(self, strategy: str, **override) -> dict:
        out = {}
        for key, arg in (("lock", "data_lock_log"), ("warm", "warmup_log"), ("look", "lookahead_log"),
                         ("rec", "recursive_log")):
            text = override.get(key, LOGS[key].format(s=strategy))
            if text is None:
                continue
            p = self.tmp / f"{key}.log"
            p.write_text(text, encoding="utf-8")
            out[arg] = p
        return out

    def evaluate(self, prereg_path: Path, summary: Path, **override) -> dict:
        prereg = json.loads(prereg_path.read_text())
        return funnel.evaluate(summary, prereg_path, self.ledger, **self.logs(prereg["strategy"]["name"],
                                                                                **override))


def null_prereg() -> dict:
    return json.loads(NULL_PREREG.read_text())


def scientific_prereg() -> dict:
    p = null_prereg()
    p.update({"family_id": "FIXTURE_FAMILY", "lineage_id": "FIXTURE_FAMILY/L1", "candidate_id": "FIX",
              "experiment_id": "EXP-CYCLE2-SCI-FIX", "run_id": "RUN-FIX-1", "trial_id": "TRIAL-FIX-1",
              "trial_class": "scientific", "lineage_kind": "TREND", "funnel_step": "DEVELOPMENT_WALK_FORWARD"})
    p["grid"] = [{"config_id": f"C{i}", "params": {"buy": {"x": i}}, "regime_gated": False} for i in range(3)]
    p["multiple_testing"] = dict(p["multiple_testing"], effective_trials=3)
    return p


@pytest.fixture
def world(tmp_path, monkeypatch):
    return World(tmp_path, monkeypatch)


def run_null(world, eval_rets, **kw):
    path = world.bind(null_prereg())
    summary = world.run(path, scenario_by_eval(eval_rets, **{k: v for k, v in kw.items()
                                                              if k in ("trades", "stress_shift")}),
                        **{k: v for k, v in kw.items() if k == "fee_line"})
    return path, summary


# -- L1 WALK_FORWARD and the null calibration verdict ---------------------------------------


def test_a_null_negative_in_all_folds_is_rejected_and_calibration_passes(world):
    path, summary = run_null(world, {EVAL1: -2.0, EVAL2: -0.5})
    r = world.evaluate(path, summary)
    assert r["gates"]["WALK_FORWARD"]["state"] == "FAIL"
    assert "ALL folds" in r["gates"]["WALK_FORWARD"]["reason"]
    assert r["funnel_result"] == "REJECTED"
    assert r["terminal_proposal"]["ledger_state"] == "REJECTED"
    assert r["calibration"]["verdict"] == "PASS" and r["cycle2_stop"] is False
    assert r["calibration"]["rejected_by"] == ["WALK_FORWARD"]


def test_a_positive_null_is_inconclusive_not_proven_and_stops_cycle2(world):
    path, summary = run_null(world, {EVAL1: 3.0, EVAL2: 1.0})
    r = world.evaluate(path, summary)
    assert r["gates"]["WALK_FORWARD"]["state"] == "PASS"
    assert r["gates"]["COST_STRESS"]["state"] == "PASS"
    assert r["gates"]["MULTIPLE_TESTING"]["state"] == "NOT_EVALUABLE"
    assert r["funnel_result"] == "INCONCLUSIVE"
    assert r["terminal_proposal"]["ledger_state"] == "COMPLETED"
    assert r["terminal_proposal"]["outcome"]["funnel_result"] == "INCONCLUSIVE"
    assert r["calibration"]["verdict"] == "NOT_PROVEN" and r["cycle2_stop"] is True


def test_a_surviving_null_fails_calibration_and_stops_cycle2(world, monkeypatch):
    path, summary = run_null(world, {EVAL1: 3.0, EVAL2: 1.0})
    monkeypatch.setattr(funnel, "multiple_testing_gate",
                        lambda *a, **k: funnel._gate("PASS", "forced by the test"))
    r = world.evaluate(path, summary)
    assert r["funnel_result"] == "SURVIVED"
    assert r["terminal_proposal"]["ledger_state"] == "SURVIVED"
    assert r["calibration"]["verdict"] == "FAIL" and r["cycle2_stop"] is True


def test_mixed_folds_with_a_non_positive_aggregate_fail_walk_forward(world):
    path, summary = run_null(world, {EVAL1: 1.0, EVAL2: -1.5})
    r = world.evaluate(path, summary)
    assert r["gates"]["WALK_FORWARD"]["state"] == "FAIL"
    assert r["gates"]["WALK_FORWARD"]["aggregate_return_pct"] == pytest.approx(-0.5)
    assert r["funnel_result"] == "REJECTED"


def test_every_fold_insufficient_is_inconclusive(world):
    path, summary = run_null(world, {EVAL1: 2.0, EVAL2: -0.5}, trades={EVAL1: 9, EVAL2: 3}, stress_shift=-0.1)
    r = world.evaluate(path, summary)
    assert r["gates"]["WALK_FORWARD"]["state"] == "INCONCLUSIVE"
    assert r["sample_evidence"] == "INSUFFICIENT"
    assert r["funnel_result"] == "INCONCLUSIVE" and r["cycle2_stop"] is True


def test_all_negative_is_rejected_even_when_every_fold_is_insufficient(world):
    path, summary = run_null(world, {EVAL1: -1.0, EVAL2: -0.5}, trades={EVAL1: 9, EVAL2: 3})
    r = world.evaluate(path, summary)
    assert r["gates"]["WALK_FORWARD"]["state"] == "FAIL"
    assert r["funnel_result"] == "REJECTED"


def test_one_insufficient_fold_blocks_survival(world, monkeypatch):
    path, summary = run_null(world, {EVAL1: 3.0, EVAL2: 1.0}, trades={EVAL1: 20, EVAL2: 9})
    monkeypatch.setattr(funnel, "multiple_testing_gate", lambda *a, **k: funnel._gate("PASS", "forced"))
    r = world.evaluate(path, summary)
    assert r["gates"]["WALK_FORWARD"]["state"] == "PASS"
    assert r["sample_evidence"] == "INSUFFICIENT"
    assert r["funnel_result"] == "INCONCLUSIVE"


def test_a_failed_eval_run_is_not_evaluable_never_pass(world, monkeypatch):
    path = world.bind(null_prereg())
    engine = Engine(world.user_data, scenario_by_eval({EVAL1: 3.0, EVAL2: 1.0}))
    real = engine.__call__

    def flaky(cmd, *a, **k):
        if cmd[0] == "docker" and EVAL2 in cmd and "0.001" in cmd:
            engine.calls.append(list(cmd))
            return subprocess.CompletedProcess(cmd, 1)
        return real(cmd, *a, **k)

    monkeypatch.setattr(driver.subprocess, "run", flaky)
    driver.main(["--prereg", str(path), "--ledger", str(world.ledger), "--artifacts-dir", str(world.art)])
    r = world.evaluate(path, world.art / "cycle2_run_summary.json")
    assert r["gates"]["WALK_FORWARD"]["state"] == "NOT_EVALUABLE"
    assert r["funnel_result"] == "INCONCLUSIVE" and r["calibration"]["verdict"] == "NOT_PROVEN"


# -- L2 COST_STRESS --------------------------------------------------------------------------


def test_a_stress_fee_that_flips_the_aggregate_sign_fails_cost_stress(world):
    path, summary = run_null(world, {EVAL1: 0.5, EVAL2: 0.3}, stress_shift=-1.0)
    r = world.evaluate(path, summary)
    cs = r["gates"]["COST_STRESS"]
    assert cs["state"] == "FAIL" and cs["levels"][0]["flips_sign"] is True
    assert r["funnel_result"] == "REJECTED"


def test_unproven_engine_fee_leaves_cost_stress_not_evaluable(world):
    path, summary = run_null(world, {EVAL1: 0.5, EVAL2: 0.3}, stress_shift=-1.0, fee_line=False)
    r = world.evaluate(path, summary)
    assert r["gates"]["COST_STRESS"]["state"] == "NOT_EVALUABLE"
    assert "not PROVEN" in r["gates"]["COST_STRESS"]["reason"]


# -- L3 MULTIPLE_TESTING, N and PBO ---------------------------------------------------------------


def test_null_dsr_and_pbo_are_not_evaluable_and_nothing_claims_pbo_validated(world):
    path, summary = run_null(world, {EVAL1: 3.0, EVAL2: 1.0})
    r = world.evaluate(path, summary)
    mt = r["gates"]["MULTIPLE_TESTING"]
    assert mt["family_configuration_N"] == 2 == mt["preregistered_effective_trials"]
    assert mt["dsr"]["status"] == "NOT_EVALUABLE"
    assert "cross-trial Sharpe variance" in mt["dsr"]["reason"]
    assert mt["pbo"]["status"] == "NOT_EVALUABLE"
    assert "too few configurations" in mt["pbo"]["reason"]
    assert "does not validate PBO" in mt["pbo_disclosure"]
    text = json.dumps(r).lower()
    assert "pbo validated" not in text and "validated pbo" not in text and "pbo = pass" not in text


def test_selection_debt_is_disclosed_verbatim_beside_dsr_and_pbo(world):
    path, summary = run_null(world, {EVAL1: 3.0, EVAL2: 1.0})
    mt = world.evaluate(path, summary)["gates"]["MULTIPLE_TESTING"]
    registry = json.loads(REGISTRY.read_text())
    assert mt["selection_debt"]["verbatim"] == registry["multiple_testing_accounting"]
    assert mt["selection_debt_statement"] == null_prereg()["selection_debt_statement"]


def test_an_effective_trials_that_disagrees_with_the_n_law_is_refused(world):
    p = null_prereg()
    p["multiple_testing"]["effective_trials"] = 8  # the family's trial-ID count, which is not N
    path = world.bind(p)
    summary = world.run(path, scenario_by_eval({EVAL1: 3.0, EVAL2: 1.0}))
    with pytest.raises(funnel.FunnelRefusal, match="family_configuration_N 2"):
        world.evaluate(path, summary)


def test_an_unresolvable_n_makes_dsr_not_evaluable(world, monkeypatch):
    path, summary = run_null(world, {EVAL1: 3.0, EVAL2: 1.0})
    monkeypatch.setattr(funnel.config_n, "family_configuration_n", lambda *a, **k: {
        "status": "NOT_EVALUABLE", "family_configuration_N": None, "reason": "fixture", "derivation": {}})
    mt = world.evaluate(path, summary)["gates"]["MULTIPLE_TESTING"]
    assert mt["dsr"]["status"] == "NOT_EVALUABLE" and "NOT_EVALUABLE" in mt["dsr"]["reason"]
    assert mt["state"] == "NOT_EVALUABLE"


def test_a_multi_config_trial_reaches_trialgate_for_dsr_and_pbo(world):
    try:
        import trialgate  # noqa: F401
    except ImportError:
        if os.environ.get("TLOS_REQUIRE_TRIALGATE") == "1":
            pytest.fail("TLOS_REQUIRE_TRIALGATE=1 but trialgate==0.5.0 is not importable")
        pytest.skip("trialgate==0.5.0 not installed here")
    p = scientific_prereg()
    path = world.bind(p)
    summary = world.run(path, scenario_by_eval({EVAL1: 3.0, EVAL2: 1.0}))
    r = world.evaluate(path, summary)
    mt = r["gates"]["MULTIPLE_TESTING"]
    assert mt["family_configuration_N"] == 3
    assert mt["pbo"]["status"] in ("PASS", "FAIL")  # evaluated, not a precondition refusal
    assert mt["dsr"]["status"] in ("PASS", "FAIL", "NOT_EVALUABLE")
    assert mt["pbo_disclosure"].startswith("PBO evaluated")
    assert r["gates"]["PARAMETER_ROBUSTNESS"]["state"] == "NOT_EVALUABLE"
    assert r["funnel_result"] != "SURVIVED"
    assert r["calibration"] is None and r["cycle2_stop"] is False
    assert r["terminal_proposal"]["outcome"]["config_ids"] == ["C0", "C1", "C2"]


# -- the SURVIVED law ---------------------------------------------------------------------------------


def _gates(**states) -> dict:
    base = {g: funnel._gate("PASS", "") for g in funnel.GATES}
    base.update({k: funnel._gate(v, "") for k, v in states.items()})
    return base


def test_all_pass_and_sufficient_survives():
    assert funnel.decide(_gates(), "SUFFICIENT") == "SURVIVED"
    assert funnel.decide(_gates(PARAMETER_ROBUSTNESS="NOT_APPLICABLE"), "SUFFICIENT") == "SURVIVED"


@pytest.mark.parametrize("gate", funnel.GATES)
def test_any_gate_fail_rejects(gate):
    assert funnel.decide(_gates(**{gate: "FAIL"}), "SUFFICIENT") == "REJECTED"


@pytest.mark.parametrize("gate", funnel.GATES)
@pytest.mark.parametrize("state", ["NOT_EVALUABLE", "INCONCLUSIVE"])
def test_not_evaluable_is_never_pass(gate, state):
    assert funnel.decide(_gates(**{gate: state}), "SUFFICIENT") == "INCONCLUSIVE"


@pytest.mark.parametrize("sample", ["INSUFFICIENT", "NOT_EVALUABLE"])
def test_insufficient_sample_is_never_rounded_up(sample):
    assert funnel.decide(_gates(), sample) == "INCONCLUSIVE"


def test_the_ledger_and_calibration_mappings_are_the_law():
    assert funnel.LEDGER_STATE == {"REJECTED": "REJECTED", "SURVIVED": "SURVIVED", "INCONCLUSIVE": "COMPLETED"}
    assert funnel.CALIBRATION == {"REJECTED": "PASS", "SURVIVED": "FAIL", "INCONCLUSIVE": "NOT_PROVEN"}
    assert funnel.MIN_EVAL_TRADES == 10


def test_parameter_robustness_is_not_applicable_only_for_null_calibration(world):
    path, summary = run_null(world, {EVAL1: -2.0, EVAL2: -0.5})
    assert world.evaluate(path, summary)["gates"]["PARAMETER_ROBUSTNESS"]["state"] == "NOT_APPLICABLE"


# -- pre-engine gates from the workflow's logs -------------------------------------------------------


def test_cycle1_style_gate_logs_pass(world):
    path, summary = run_null(world, {EVAL1: -2.0, EVAL2: -0.5})
    g = world.evaluate(path, summary)["gates"]
    assert [g[k]["state"] for k in ("DATA_TRUTH", "LOOKAHEAD", "RECURSIVE", "LEDGER_CHAIN")] == ["PASS"] * 4


@pytest.mark.parametrize("override,gate,state", [
    ({"look": "│ NullControlMatchedFrequency.py │ NullControlMatchedFrequency │ Yes │ 20 │\n"
              .join(["┃ filename ┃ strategy ┃ has_bias ┃ total_signals ┃\n", ""])}, "LOOKAHEAD", "FAIL"),
    ({"look": None}, "LOOKAHEAD", "NOT_EVALUABLE"),
    ({"look": "no table here\n"}, "LOOKAHEAD", "NOT_EVALUABLE"),
    ({"rec": "INFO - No lookahead bias on indicators found.\n"}, "RECURSIVE", "NOT_EVALUABLE"),
    ({"rec": None}, "RECURSIVE", "NOT_EVALUABLE"),
    ({"lock": "DATASET_LOCK_GATE = FAIL\n"}, "DATA_TRUTH", "FAIL"),
    ({"warm": None}, "DATA_TRUTH", "NOT_EVALUABLE"),
])
def test_gate_logs_are_read_fail_closed(world, override, gate, state):
    path, summary = run_null(world, {EVAL1: 3.0, EVAL2: 1.0})
    assert world.evaluate(path, summary, **override)["gates"][gate]["state"] == state


def test_an_unbound_preregistration_fails_the_ledger_chain(world):
    p = null_prereg()
    path = world.bind(p)
    summary = world.run(path, scenario_by_eval({EVAL1: 3.0, EVAL2: 1.0}))
    other = tmp_ledger = world.tmp / "other.jsonl"
    lines = CANONICAL_LEDGER.read_text(encoding="utf-8").splitlines(keepends=True)[:CYCLE1_RECORDS]
    tmp_ledger.write_text("".join(lines), encoding="utf-8")
    r = funnel.evaluate(summary, path, other, **world.logs(p["strategy"]["name"]))
    assert r["gates"]["LEDGER_CHAIN"]["state"] == "FAIL"
    assert r["ledger"]["binding"] == "NOT_BOUND"


# -- refusals -----------------------------------------------------------------------------------------


def test_a_tampered_artifact_is_refused(world):
    path, summary = run_null(world, {EVAL1: -2.0, EVAL2: -0.5})
    metrics = sorted(world.art.glob("metrics_fold1_eval_*.json"))[0]
    metrics.write_text(json.dumps({"total_return_pct": 99.0, "trade_count": 50}))
    with pytest.raises(funnel.FunnelRefusal, match="sha256"):
        world.evaluate(path, summary)


def test_a_run_of_another_preregistration_is_refused(world):
    path, summary = run_null(world, {EVAL1: -2.0, EVAL2: -0.5})
    p = json.loads(path.read_text())
    p["notes_free_field_absent"] = True
    other = world.tmp / "other.json"
    p.pop("notes_free_field_absent")
    p["wallet"] = 101
    other.write_text(json.dumps(p))
    with pytest.raises(funnel.FunnelRefusal, match="does not belong"):
        funnel.evaluate(summary, other, world.ledger)


def test_a_preregistration_bound_to_another_law_is_refused(world):
    p = null_prereg()
    p["funnel_law"]["sha256"] = "0" * 64
    path = world.bind(p)
    summary = world.run(path, scenario_by_eval({EVAL1: -2.0, EVAL2: -0.5}))
    with pytest.raises(funnel.FunnelRefusal, match="funnel law"):
        world.evaluate(path, summary)


def test_the_cli_refuses_with_exit_2(world, capsys):
    path, summary = run_null(world, {EVAL1: -2.0, EVAL2: -0.5})
    sorted(world.art.glob("invocation_*.json"))[0].write_text("{}")
    assert funnel.main(["--run-summary", str(summary), "--prereg", str(path), "--ledger", str(world.ledger)]) == 2
    assert "REFUSED" in capsys.readouterr().err


# -- determinism, read-only, §11 ----------------------------------------------------------------------


def test_the_evaluation_is_deterministic_and_never_writes_the_ledger(world, tmp_path):
    path, summary = run_null(world, {EVAL1: 3.0, EVAL2: 1.0})
    before = world.ledger.read_bytes()
    a = json.dumps(world.evaluate(path, summary), sort_keys=True)
    b = json.dumps(world.evaluate(path, summary), sort_keys=True)
    assert a == b
    assert world.ledger.read_bytes() == before
    out1, out2 = tmp_path / "o1.json", tmp_path / "o2.json"
    logs = world.logs("NullControlMatchedFrequency")
    for out in (out1, out2):
        argv = ["--run-summary", str(summary), "--prereg", str(path), "--ledger", str(world.ledger),
                "--out", str(out)] + [x for k, v in logs.items() for x in (f"--{k.replace('_', '-')}", str(v))]
        assert funnel.main(argv) == 0
    assert out1.read_bytes() == out2.read_bytes()
    assert world.ledger.read_bytes() == before


def test_the_evaluator_source_never_appends_to_a_ledger():
    source = Path(funnel.__file__).read_text()
    assert "ledger.append" not in source and "TrialLedger(" not in source
    assert ".append(payload" not in source


def test_the_report_carries_the_section_11_fields(world):
    path, summary = run_null(world, {EVAL1: -2.0, EVAL2: -0.5})
    r = world.evaluate(path, summary)
    for field in ("authority", "cycle_id", "family_id", "lineage_id", "candidate_id", "config_ids", "trial_id",
                  "funnel_step", "budget", "ledger", "funnel_result", "terminal_proposal", "calibration"):
        assert field in r
    assert r["authority"] == "DERIVED_NON_AUTHORITATIVE"
    assert r["ledger"]["verify"] == "PASS" and r["ledger"]["binding"] == "BOUND"
    assert r["terminal_proposal"]["proposal_only"] is True
    assert r["terminal_proposal"]["outcome"]["engine_invocations"] == 6
    assert r["funnel_law"] == null_prereg()["funnel_law"]


def test_the_cli_is_deterministic_across_two_processes(world):
    path, summary = run_null(world, {EVAL1: -2.0, EVAL2: -0.5})
    code = ("import sys; sys.path.insert(0, 'research'); from pathlib import Path;"
            "from cycle2 import config_n, funnel; config_n.REPO_ROOT = Path(sys.argv[1]);"
            "raise SystemExit(funnel.main(sys.argv[2:]))")
    outs = []
    for i in range(2):
        out = world.tmp / f"cli{i}.json"
        proc = _RUN([sys.executable, "-c", code, str(world.root), "--run-summary", str(summary),
                               "--prereg", str(path), "--ledger", str(world.ledger), "--out", str(out)],
                              capture_output=True, text=True, cwd=REPO_ROOT)
        assert proc.returncode == 0, proc.stderr
        outs.append(out.read_bytes())
    assert outs[0] == outs[1]
