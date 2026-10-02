"""CYCLE-2 UNIT 7.1 — the §6.1 + §6.2 driver, tested WITHOUT executing anything.

subprocess is mocked everywhere: no docker, no freqtrade, no market data. The
tests assert the exact engine argv (fee flag included), trade export on every
run, cap refusal against what the ledger already records, schema rejection of
sweep syntax, a dry run that prints the plan and exits 0, and that the §11
summary is deterministic. The engine-propagation proof from a real run log is
§7.2's, not this file's.

Ledgers here are temporary files built with research/trial_ledger.py; the
canonical ledger is only ever read.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

from cycle2 import driver
from trial_ledger import TrialLedger

REPO_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_LEDGER = REPO_ROOT / "research" / "records" / "trial_ledger.jsonl"
STRATEGY_FILE = "research/mean_reversion/MeanReversionZScore.py"
IMAGE = "freqtradeorg/freqtrade:2026.7"
LAW_RECORD = "research/cycle2/FUNNEL_LAW_1.md"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def base_prereg() -> dict:
    """A synthetic fixture. Every value is a test fixture, not a research choice."""
    return {
        "schema_version": "cycle2-prereg-1.0.0",
        "cycle_id": "OFFLINE-RESEARCH-CYCLE-2",
        "family_id": "FIXTURE_FAMILY",
        "lineage_id": "FIXTURE_FAMILY/L1",
        "candidate_id": "FIXTURE_CANDIDATE",
        "experiment_id": "EXP-CYCLE2-SCI-FIXTURE",
        "run_id": "RUN-FIXTURE-1",
        "trial_id": "TRIAL-FIXTURE-1",
        "trial_class": "scientific",
        "lineage_kind": "TREND",
        "funnel_step": "DEVELOPMENT_WALK_FORWARD",
        "strategy": {"name": "FixtureStrategy", "file": STRATEGY_FILE,
                     "sha256": _sha(REPO_ROOT / STRATEGY_FILE)},
        "engine_image": IMAGE,
        "wallet": 100.0,
        "selection_metric": "return_over_drawdown",
        "grid": [
            {"config_id": "A", "params": {"buy": {"lookback": 10}}, "regime_gated": False},
            {"config_id": "B", "params": {"buy": {"lookback": 20}, "sell": {"exit": 1.5}}, "regime_gated": False},
            {"config_id": "C", "params": {"buy": {"lookback": 30}}, "regime_gated": True},
        ],
        "folds": [
            {"fold": 1, "train": {"start": "20210101", "end": "20221231"},
             "eval": {"start": "20230101", "end": "20231231"}},
            {"fold": 2, "train": {"start": "20210101", "end": "20231231"},
             "eval": {"start": "20240101", "end": "20241231"}},
        ],
        "lanes": ["walk_forward", "robustness"],
        "robustness_window": {"start": "20210101", "end": "20241231"},
        "fee_levels": {"base": 0.001, "stress": [0.002, 0.003]},
        "multiple_testing": {"dsr_threshold": 0.5, "pbo_threshold": 0.5, "pbo_block_count": 8,
                             "periods_per_year": 365, "effective_trials": 3},
        "selection_debt_statement": "fixture: cumulative family N plus upstream selection debt stated here",
        "funnel_law": {"record": LAW_RECORD, "sha256": _sha(REPO_ROOT / LAW_RECORD)},
    }


# 2 folds x (3 train + 1 eval + 2 stress) + 3 robustness
PLANNED = 2 * (3 + 1 + 2) + 3


def write_prereg(tmp_path: Path, prereg: dict) -> Path:
    path = tmp_path / "prereg.json"
    path.write_text(json.dumps(prereg, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def ledger_payload(prereg: dict, state: str, *, prereg_sha: str | None = None, outcome: dict | None = None,
                   **overrides) -> dict:
    payload = {
        "schema_version": "1.0.0",
        "family_id": prereg["family_id"], "lineage_id": prereg["lineage_id"],
        "candidate_id": prereg["candidate_id"], "config_id": f"{prereg['candidate_id']}/GRID",
        "experiment_id": prereg["experiment_id"], "run_id": prereg["run_id"],
        "trial_id": prereg["trial_id"], "state": state,
        "purpose": "unit-test fixture ledger; not a research trial",
        "dataset_identity": {"prereg_sha256": prereg_sha or "0" * 64},
    }
    if outcome is not None:
        payload["outcome"] = {"reason": "fixture", **outcome}
    payload.update(overrides)
    return payload


def make_ledger(tmp_path: Path, *payloads: dict) -> Path:
    path = tmp_path / "ledger.jsonl"
    ledger = TrialLedger(path)
    for i, p in enumerate(payloads):
        ledger.append(p, recorded_utc=f"2026-10-01T00:00:{i:02d}Z")
    return path


def closed_trial(n: int, *, invocations: int, configs: list[str] | None, scientific: bool = True,
                 lineage: str = "FIXTURE_FAMILY/L1") -> list[dict]:
    other = base_prereg()
    other.update({"trial_id": f"TRIAL-PRIOR-{n}", "run_id": f"RUN-PRIOR-{n}", "lineage_id": lineage,
                  "experiment_id": f"EXP-CYCLE2-{'SCI' if scientific else 'CAL'}-PRIOR{n}"})
    outcome = {"engine_invocations": invocations}
    if configs is not None:
        outcome["config_ids"] = configs
    return [ledger_payload(other, "PREREGISTERED"),
            ledger_payload(other, "REJECTED", outcome=outcome)]


@pytest.fixture
def bound(tmp_path):
    """A preregistration bound to a temporary ledger by its sha256."""
    prereg = base_prereg()
    path = write_prereg(tmp_path, prereg)
    ledger = make_ledger(tmp_path, ledger_payload(prereg, "PREREGISTERED", prereg_sha=_sha(path)))
    return prereg, path, ledger


class FakeEngine:
    """Stands in for subprocess.run. Nothing is executed; every call is recorded."""

    def __init__(self, user_data: Path, *, fail_docker: bool = False):
        self.calls: list[list[str]] = []
        self.user_data = user_data
        self.fail_docker = fail_docker
        self.n = 0

    def __call__(self, cmd, stdout=None, stderr=None, capture_output=False, text=False, check=False, **_):
        cmd = list(cmd)
        self.calls.append(cmd)
        if cmd[0] == "sudo":
            return subprocess.CompletedProcess(cmd, 0)
        if cmd[0] == "docker":
            fee = float(cmd[cmd.index("--fee") + 1])
            stdout.write(f"2026 - freqtrade.optimize.backtesting - INFO - Using fee {fee * 100:.4f}% from config.\n")
            if self.fail_docker:
                return subprocess.CompletedProcess(cmd, 1)
            self.n += 1
            results = self.user_data / "backtest_results"
            results.mkdir(parents=True, exist_ok=True)
            out = results / f"backtest-result-{self.n:04d}.json"
            out.write_text(json.dumps({"n": self.n, "argv": cmd[cmd.index("backtesting"):]}), encoding="utf-8")
            os.utime(out, (1_000_000 + self.n, 1_000_000 + self.n))
            return subprocess.CompletedProcess(cmd, 0)
        if cmd[1].endswith("summarize_backtest.py"):
            params = json.loads((self.user_data / "strategies" / "FixtureStrategy.json").read_text())
            lookback = params["params"]["buy"]["lookback"]
            fee = float(cmd[cmd.index("--fee") + 1])
            metrics = {"total_return_pct": lookback / 10 - fee * 100, "max_drawdown_pct": 2.0,
                       "trade_count": 12, "fee": fee}
            Path(cmd[cmd.index("--out") + 1]).write_text(json.dumps(metrics), encoding="utf-8")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        raise AssertionError(f"unexpected subprocess call: {cmd}")

    def docker_calls(self):
        return [c for c in self.calls if c[0] == "docker"]

    def summarize_calls(self):
        return [c for c in self.calls if c[0] != "docker" and c[0] != "sudo"]


@pytest.fixture
def engine(tmp_path, monkeypatch):
    user_data = tmp_path / "user_data"
    (user_data / "strategies").mkdir(parents=True)
    (user_data / "backtest_results").mkdir(parents=True)
    monkeypatch.setattr(driver, "USER_DATA", user_data)
    monkeypatch.setattr(driver, "STRATEGY_DIR", user_data / "strategies")
    monkeypatch.setattr(driver, "BACKTEST_RESULTS", user_data / "backtest_results")
    fake = FakeEngine(user_data)
    monkeypatch.setattr(driver.subprocess, "run", fake)
    return fake


# -- argv: the Cycle-1 shape, with the fee reaching the engine --------------------


def test_the_engine_argv_is_exact(engine):
    argv = driver.backtest_argv(IMAGE, "FixtureStrategy", {"start": "20210101", "end": "20221231"}, 0.002)
    assert argv == [
        "docker", "run", "--rm",
        "-v", f"{driver.USER_DATA}:/freqtrade/user_data",
        IMAGE, "backtesting",
        "--config", "/freqtrade/user_data/config.research.json",
        "--strategy", "FixtureStrategy", "--strategy-path", "/freqtrade/user_data/strategies",
        "--timerange", "20210101-20221231", "--timeframe-detail", "5m",
        "--enable-protections", "--export", "trades",
        "--fee", "0.002",
    ]
    assert not any("hyperopt" in a.lower() for a in argv)


def test_a_real_run_passes_every_preregistered_fee_to_the_engine_and_exports_trades(bound, engine, tmp_path):
    prereg, path, ledger = bound
    art = tmp_path / "art"
    assert driver.main(["--prereg", str(path), "--ledger", str(ledger), "--artifacts-dir", str(art)]) == 0

    docker = engine.docker_calls()
    assert len(docker) == PLANNED
    for argv in docker:
        assert argv[argv.index("--export") + 1] == "trades"
        assert argv.count("--fee") == 1
    fees = [float(a[a.index("--fee") + 1]) for a in docker]
    assert fees.count(0.002) == 2 and fees.count(0.003) == 2
    assert fees.count(0.001) == PLANNED - 4
    # the summariser is handed the same fee the engine got, run for run
    summ = engine.summarize_calls()
    assert [float(c[c.index("--fee") + 1]) for c in summ] == fees

    stress = json.loads((art / "invocation_fold1_cost_stress_eval_SELECTED_fee0.003.json").read_text())
    assert stress["fee_level"] == 0.003
    assert stress["fee_model"] == "symmetric fee proxy"
    assert stress["friction"] == {"slippage": "NOT_SUPPORTED", "latency": "NOT_SUPPORTED",
                                  "partial_fills": "NOT_SUPPORTED"}
    assert stress["engine_fee_propagation"] == "PROVEN"


def test_fee_propagation_is_unproven_without_the_engine_saying_so():
    assert driver.engine_fee_propagation(None, 0.002) == "UNPROVEN"
    assert driver.engine_fee_propagation("Using fee 0.1000% from config", 0.002) == "UNPROVEN"
    assert driver.engine_fee_propagation("Using fee 0.2000% from config", 0.002) == "PROVEN"


def test_walk_forward_selects_on_train_only_and_evaluates_the_selection(bound, engine, tmp_path):
    prereg, path, ledger = bound
    art = tmp_path / "art"
    driver.main(["--prereg", str(path), "--ledger", str(ledger), "--artifacts-dir", str(art)])
    summary = json.loads((art / "cycle2_run_summary.json").read_text())
    # the fake engine scores lookback/10: C (30) wins every TRAIN
    assert summary["selected_config_by_fold"] == {"1": "C", "2": "C"}
    evals = [json.loads((art / f"invocation_fold{f}_eval_SELECTED_fee0.001.json").read_text())
             for f in (1, 2)]
    assert [e["config_id"] for e in evals] == ["C", "C"]
    assert evals[0]["timerange"] == "20230101-20231231"


def test_params_are_written_nested_by_space(bound, engine, tmp_path):
    prereg, path, ledger = bound
    driver.main(["--prereg", str(path), "--ledger", str(ledger), "--artifacts-dir", str(tmp_path / "a")])
    written = json.loads((driver.STRATEGY_DIR / "FixtureStrategy.json").read_text())
    assert written["params"] == {"buy": {"lookback": 30}}  # robustness lane ends on C


# -- §11 summary --------------------------------------------------------------------

S11_FIELDS = {"cycle_id", "family_id", "lineage_id", "candidate_id", "config_id", "trial_id", "funnel_step",
              "fee_level", "invocation", "budget", "ledger", "evidence", "status", "authority"}


def test_every_invocation_writes_a_section_11_summary(bound, engine, tmp_path):
    prereg, path, ledger = bound
    art = tmp_path / "art"
    driver.main(["--prereg", str(path), "--ledger", str(ledger), "--artifacts-dir", str(art)])
    files = sorted(art.glob("invocation_*.json"))
    assert len(files) == PLANNED
    for f in files:
        s = json.loads(f.read_text())
        assert S11_FIELDS <= set(s)
        assert s["authority"] == "DERIVED_NON_AUTHORITATIVE"
        assert s["ledger"] == {"verify": "PASS", "binding": "BOUND", "records": 1}
        assert s["status"] == "OK"
        for ev in s["evidence"]:
            assert ev["sha256"] == _sha(art / ev["path"])
    last = json.loads((art / "invocation_robustness_C_fee0.001.json").read_text())
    assert last["budget"]["engine_invocations_consumed"] == PLANNED
    assert last["budget"]["engine_invocations_remaining"] == 120 - PLANNED
    summary = json.loads((art / "cycle2_run_summary.json").read_text())
    assert summary["terminal_decision"] is None
    assert summary["budget"]["consumed_after"]["scientific_configurations"] == 3
    assert summary["budget"]["consumed_after"]["scientific_trial_ids"] == 1


def test_the_summary_is_deterministic(tmp_path, monkeypatch):
    outputs = []
    for run in ("one", "two"):
        root = tmp_path / run
        root.mkdir()
        prereg = base_prereg()
        path = write_prereg(root, prereg)
        ledger = make_ledger(root, ledger_payload(prereg, "PREREGISTERED", prereg_sha=_sha(path)))
        user_data = tmp_path / "user_data"  # same mount path both times, as on a runner
        if user_data.exists():
            for p in sorted(user_data.rglob("*"), reverse=True):
                p.unlink() if p.is_file() else p.rmdir()
        (user_data / "strategies").mkdir(parents=True, exist_ok=True)
        (user_data / "backtest_results").mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(driver, "USER_DATA", user_data)
        monkeypatch.setattr(driver, "STRATEGY_DIR", user_data / "strategies")
        monkeypatch.setattr(driver, "BACKTEST_RESULTS", user_data / "backtest_results")
        monkeypatch.setattr(driver.subprocess, "run", FakeEngine(user_data))
        art = tmp_path / "artifacts"
        if art.exists():
            for p in sorted(art.rglob("*"), reverse=True):
                p.unlink() if p.is_file() else p.rmdir()
        assert driver.main(["--prereg", str(path), "--ledger", str(ledger), "--artifacts-dir", str(art)]) == 0
        outputs.append({p.relative_to(art).as_posix(): p.read_bytes()
                        for p in sorted(art.rglob("*.json"))})
    assert outputs[0] == outputs[1]


def test_a_systemic_failure_exits_nonzero(bound, tmp_path, monkeypatch):
    prereg, path, ledger = bound
    user_data = tmp_path / "ud"
    (user_data / "strategies").mkdir(parents=True)
    (user_data / "backtest_results").mkdir(parents=True)
    monkeypatch.setattr(driver, "USER_DATA", user_data)
    monkeypatch.setattr(driver, "STRATEGY_DIR", user_data / "strategies")
    monkeypatch.setattr(driver, "BACKTEST_RESULTS", user_data / "backtest_results")
    monkeypatch.setattr(driver.subprocess, "run", FakeEngine(user_data, fail_docker=True))
    assert driver.main(["--prereg", str(path), "--ledger", str(ledger),
                        "--artifacts-dir", str(tmp_path / "a")]) == 1


# -- dry run --------------------------------------------------------------------------


def test_a_dry_run_prints_the_plan_executes_nothing_and_exits_zero(tmp_path, engine, capsys):
    prereg = base_prereg()
    path = write_prereg(tmp_path, prereg)
    ledger = make_ledger(tmp_path, *closed_trial(1, invocations=10, configs=["X"]))
    assert driver.main(["--prereg", str(path), "--ledger", str(ledger), "--dry-run"]) == 0
    assert engine.calls == []
    out = json.loads(capsys.readouterr().out)
    assert out["mode"] == "DRY_RUN" and out["executes"] is False
    assert len(out["plan"]) == PLANNED
    assert out["ledger"]["binding"] == "NOT_PREREGISTERED"
    assert out["budget"]["consumed_before"]["engine_invocations"] == 10
    assert out["budget"]["remaining_after"]["engine_invocations"] == 120 - 10 - PLANNED
    assert out["budget"]["consumed_after"]["scientific_configurations"] == 4
    assert out["budget"]["consumed_after"]["scientific_trial_ids"] == 2
    assert all("--fee" in s["argv"] and "trades" in s["argv"] for s in out["plan"])


def test_a_dry_run_against_the_canonical_ledger_reads_it_and_leaves_it_untouched(tmp_path, engine, capsys):
    before = CANONICAL_LEDGER.read_bytes()
    path = write_prereg(tmp_path, base_prereg())
    assert driver.main(["--prereg", str(path), "--dry-run"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["budget"]["consumed_before"]["engine_invocations"] == 0  # no Cycle-2 trial exists yet
    assert CANONICAL_LEDGER.read_bytes() == before
    assert engine.calls == []


def test_a_real_run_refuses_without_a_ledger_preregistration(tmp_path, engine, capsys):
    path = write_prereg(tmp_path, base_prereg())
    ledger = make_ledger(tmp_path, *closed_trial(1, invocations=1, configs=["X"]))
    assert driver.main(["--prereg", str(path), "--ledger", str(ledger), "--artifacts-dir",
                        str(tmp_path / "a")]) == 2
    assert "not preregistered" in capsys.readouterr().err
    assert engine.calls == []


# -- hard caps -------------------------------------------------------------------------


def _refused(tmp_path, engine, capsys, prereg, *ledger_payloads, bind=True) -> str:
    path = write_prereg(tmp_path, prereg)
    payloads = list(ledger_payloads)
    if bind:
        payloads.append(ledger_payload(prereg, "PREREGISTERED", prereg_sha=_sha(path)))
    ledger = make_ledger(tmp_path, *payloads)
    rc = driver.main(["--prereg", str(path), "--ledger", str(ledger), "--artifacts-dir", str(tmp_path / "a")])
    err = capsys.readouterr().err
    assert rc == 2, err
    assert engine.calls == []
    return err


def test_refuses_when_planned_invocations_would_exceed_the_120_cap(tmp_path, engine, capsys):
    err = _refused(tmp_path, engine, capsys, base_prereg(),
                   *closed_trial(1, invocations=120 - PLANNED + 1, configs=["X"]))
    assert f"engine_invocations: {121} > cap 120" in err


def test_exactly_at_the_invocation_cap_is_allowed(tmp_path, engine):
    prereg = base_prereg()
    path = write_prereg(tmp_path, prereg)
    ledger = make_ledger(tmp_path, *closed_trial(1, invocations=120 - PLANNED, configs=["X"]),
                         ledger_payload(prereg, "PREREGISTERED", prereg_sha=_sha(path)))
    assert driver.main(["--prereg", str(path), "--ledger", str(ledger), "--dry-run"]) == 0


def test_refuses_past_24_scientific_configurations(tmp_path, engine, capsys):
    prior = []
    for n in range(3):  # 3 x 7 configurations in other lineages, within their own sub-limits
        prior += closed_trial(n, invocations=1, configs=[f"P{n}C{i}" for i in range(7)],
                              lineage=f"OTHER/L{n}")
    path = write_prereg(tmp_path, base_prereg())
    assert driver.main(["--prereg", str(path), "--ledger", str(make_ledger(tmp_path, *prior)),
                        "--dry-run"]) == 0  # 21 + 3 = 24: at the cap, allowed
    capsys.readouterr()
    prior += closed_trial(9, invocations=1, configs=["EXTRA"], lineage="OTHER/L9")
    tmp2 = tmp_path / "second"
    tmp2.mkdir()
    err = _refused(tmp2, engine, capsys, base_prereg(), *prior)
    assert "scientific_configurations: 25 > cap 24" in err


def test_refuses_past_12_scientific_trial_ids_counting_aborts(tmp_path, engine, capsys):
    prior = []
    for n in range(12):
        prior += closed_trial(n, invocations=0, configs=[], lineage=f"OTHER/L{n}")
    err = _refused(tmp_path, engine, capsys, base_prereg(), *prior)
    assert "scientific_trial_ids: 13 > cap 12" in err


def test_refuses_past_6_calibration_trial_ids(tmp_path, engine, capsys):
    prereg = base_prereg()
    prereg.update({"trial_class": "calibration", "experiment_id": "EXP-CYCLE2-CAL-FIXTURE",
                   "lineage_kind": "NULL_CALIBRATION", "funnel_step": "NULL_RECALIBRATION"})
    prior = []
    for n in range(6):
        prior += closed_trial(n, invocations=0, configs=None, scientific=False)
    err = _refused(tmp_path, engine, capsys, prereg, *prior)
    assert "calibration_trial_ids: 7 > cap 6" in err


def test_refuses_past_the_trend_and_regime_gated_sub_limits(tmp_path, engine, capsys):
    err = _refused(tmp_path, engine, capsys, base_prereg(),
                   *closed_trial(1, invocations=1, configs=[f"T{i}" for i in range(10)]))
    assert "TREND configurations in FIXTURE_FAMILY/L1: 13 > sub-limit 12" in err
    prereg = base_prereg()
    prereg["grid"] = [{"config_id": f"G{i}", "params": {"buy": {"lookback": i + 1}}, "regime_gated": True}
                      for i in range(5)]
    tmp2 = tmp_path / "gated"
    tmp2.mkdir()
    err = _refused(tmp2, engine, capsys, prereg)
    assert "regime/session-gated configurations: 5 > sub-limit 4" in err


def test_a_cap_is_never_extended_by_any_input():
    assert driver.CAPS == {"engine_invocations": 120, "scientific_configurations": 24,
                           "scientific_trial_ids": 12, "calibration_trial_ids": 6}
    schema = json.loads(driver.SCHEMA_PATH.read_text())
    assert not any("cap" in k.lower() or "budget" in k.lower() for k in schema["properties"])


# -- fail-closed ledger reading --------------------------------------------------------


def test_refuses_an_open_cycle2_trial_with_unknown_consumption(tmp_path, engine, capsys):
    other = closed_trial(1, invocations=1, configs=["X"])[:1]
    err = _refused(tmp_path, engine, capsys, base_prereg(), *other)
    assert "preregistered but not closed" in err


def test_refuses_a_closed_trial_that_does_not_state_its_consumption(tmp_path, engine, capsys):
    prior = closed_trial(1, invocations=1, configs=["X"])
    del prior[1]["outcome"]["engine_invocations"]
    err = _refused(tmp_path, engine, capsys, base_prereg(), *prior)
    assert "does not state engine_invocations" in err
    prior = closed_trial(2, invocations=1, configs=None)
    tmp2 = tmp_path / "b"
    tmp2.mkdir()
    err = _refused(tmp2, engine, capsys, base_prereg(), *prior)
    assert "does not state config_ids" in err


def test_refuses_a_ledger_that_does_not_verify(tmp_path, engine, capsys):
    prereg = base_prereg()
    path = write_prereg(tmp_path, prereg)
    ledger = make_ledger(tmp_path, *closed_trial(1, invocations=1, configs=["X"]))
    lines = ledger.read_text().splitlines()
    ledger.write_text(lines[1] + "\n" + lines[0] + "\n")
    assert driver.main(["--prereg", str(path), "--ledger", str(ledger), "--dry-run"]) == 2
    assert "does not verify" in capsys.readouterr().err


def test_refuses_when_the_prereg_file_changed_after_ledger_preregistration(tmp_path, engine, capsys):
    prereg = base_prereg()
    err = _refused(tmp_path, engine, capsys, prereg,
                   ledger_payload(prereg, "PREREGISTERED", prereg_sha="f" * 64), bind=False)
    assert "does not carry this file's sha256" in err


def test_refuses_a_trial_that_is_already_closed(tmp_path, engine, capsys):
    prereg = base_prereg()
    path = write_prereg(tmp_path, prereg)
    ledger = make_ledger(tmp_path, ledger_payload(prereg, "PREREGISTERED", prereg_sha=_sha(path)),
                         ledger_payload(prereg, "ABORTED", prereg_sha=_sha(path),
                                        outcome={"engine_invocations": 0, "config_ids": []}))
    assert driver.main(["--prereg", str(path), "--ledger", str(ledger), "--dry-run"]) == 2
    assert "never re-run" in capsys.readouterr().err


def test_refuses_a_strategy_whose_sha256_does_not_match(tmp_path, engine, capsys):
    prereg = base_prereg()
    prereg["strategy"]["sha256"] = "0" * 64
    path = write_prereg(tmp_path, prereg)
    assert driver.main(["--prereg", str(path), "--ledger", str(make_ledger(tmp_path)), "--dry-run"]) == 2
    assert "does not match its preregistered sha256" in capsys.readouterr().err


def test_the_driver_never_writes_the_ledger(bound, engine, tmp_path):
    prereg, path, ledger = bound
    before = ledger.read_bytes()
    driver.main(["--prereg", str(path), "--ledger", str(ledger), "--artifacts-dir", str(tmp_path / "a")])
    assert ledger.read_bytes() == before
    source = Path(driver.__file__).read_text()
    assert "ledger.append" not in source and "TrialLedger(path).append" not in source


# -- schema: explicit enumeration only ---------------------------------------------------


def _schema_refuses(tmp_path, mutate) -> str:
    prereg = copy.deepcopy(base_prereg())
    mutate(prereg)
    path = write_prereg(tmp_path, prereg)
    with pytest.raises(driver.DriverRefusal) as exc:
        driver.load_prereg(path)
    return str(exc.value)


@pytest.mark.parametrize("mutate", [
    lambda p: p.__setitem__("grid", {"lookback": {"min": 10, "max": 50, "step": 5}}),
    lambda p: p["grid"][0]["params"]["buy"].__setitem__("lookback", [10, 20, 30]),
    lambda p: p["grid"][0]["params"]["buy"].__setitem__("lookback", {"low": 10, "high": 50}),
    lambda p: p["grid"][0]["params"]["buy"].__setitem__("lookback", "range(10,50,5)"),
    lambda p: p["grid"][0]["params"]["buy"].__setitem__("lookback", "10:50:5"),
    lambda p: p["grid"][0]["params"]["buy"].__setitem__("lookback", "10..50"),
    lambda p: p["grid"][0].__setitem__("sweep", True),
    lambda p: p.__setitem__("hyperopt", {"epochs": 100}),
    lambda p: p.__setitem__("search_space", {"lookback": [10, 50]}),
    lambda p: p["grid"][0]["params"].__setitem__("lookback", 10),
])
def test_the_schema_rejects_any_sweep_or_range_syntax(tmp_path, mutate):
    assert "prereg.schema.json" in _schema_refuses(tmp_path, mutate)


@pytest.mark.parametrize("mutate,why", [
    (lambda p: p["folds"][0]["eval"].__setitem__("end", "20250601"), "schema"),
    (lambda p: p["folds"][0]["train"].__setitem__("start", "20200101"), "schema"),
    (lambda p: p.__setitem__("robustness_window", {"start": "20240101", "end": "20230101"}), "Development"),
    (lambda p: p["folds"][0]["eval"].__setitem__("start", "20220101"), "eval does not start after train"),
    (lambda p: p.__setitem__("experiment_id", "EXP-CYCLE2-CAL-FIXTURE"), "does not match trial_class"),
    (lambda p: p["grid"][1].__setitem__("config_id", "A"), "not unique"),
    (lambda p: p["grid"][1].__setitem__("params", {"buy": {"lookback": 10}}), "identical params"),
    (lambda p: p["fee_levels"]["stress"].append(0.001), "equals the base fee"),
    (lambda p: p.pop("multiple_testing"), "schema"),
    (lambda p: p["multiple_testing"].pop("dsr_threshold"), "schema"),
    (lambda p: p.__setitem__("lineage_kind", "MEAN_REVERSION"), "schema"),
    (lambda p: p.pop("robustness_window"), "schema"),
    (lambda p: p.__setitem__("grid", [{"config_id": f"G{i}", "params": {"buy": {"x": i}},
                                        "regime_gated": False} for i in range(25)]), "schema"),
])
def test_the_schema_and_semantics_refuse_out_of_bounds_inputs(tmp_path, mutate, why):
    assert why in _schema_refuses(tmp_path, mutate)


def test_the_fixture_preregistration_itself_validates(tmp_path):
    assert driver.load_prereg(write_prereg(tmp_path, base_prereg()))["trial_id"] == "TRIAL-FIXTURE-1"


def test_importing_the_driver_executes_nothing(monkeypatch):
    import importlib

    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append(a))
    importlib.reload(driver)
    assert calls == []


# -- UNIT 7.2 PART A: the null fixtures and the null sequencing law ----------------------------

PREREG_DIR = REPO_ROOT / "research" / "cycle2" / "prereg"
NULL1 = PREREG_DIR / "TRIAL-C2-NULL-MATCHFREQ-1.json"
NULL2 = PREREG_DIR / "TRIAL-C2-NULL-BLOCKSHUF-1.json"
NULLS = (NULL1, NULL2)


class NullEngine:
    """subprocess.run stand-in for a parameter-free null: every run yields fixed metrics."""

    def __init__(self, user_data: Path):
        self.user_data, self.calls, self.n = user_data, [], 0

    def __call__(self, cmd, stdout=None, stderr=None, capture_output=False, text=False, check=False, **_):
        cmd = list(cmd)
        self.calls.append(cmd)
        if cmd[0] == "sudo":
            return subprocess.CompletedProcess(cmd, 0)
        if cmd[0] == "docker":
            fee = float(cmd[cmd.index("--fee") + 1])
            stdout.write(f"freqtrade - INFO - Using fee {fee * 100:.4f}% from config.\n")
            self.n += 1
            out = self.user_data / "backtest_results" / f"backtest-result-{self.n:04d}.json"
            out.write_text(json.dumps({"n": self.n}), encoding="utf-8")
            os.utime(out, (1_000_000 + self.n, 1_000_000 + self.n))
            return subprocess.CompletedProcess(cmd, 0)
        if cmd[1].endswith("summarize_backtest.py"):
            Path(cmd[cmd.index("--out") + 1]).write_text(
                json.dumps({"total_return_pct": -1.0, "max_drawdown_pct": 2.0, "trade_count": 12}), encoding="utf-8")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        raise AssertionError(f"unexpected subprocess call: {cmd}")

    def docker_calls(self):
        return [c for c in self.calls if c[0] == "docker"]


@pytest.fixture
def null_engine(tmp_path, monkeypatch):
    user_data = tmp_path / "user_data"
    (user_data / "strategies").mkdir(parents=True)
    (user_data / "backtest_results").mkdir(parents=True)
    (user_data / "config.research.json").write_text(
        json.dumps({"exchange": {"name": "binance", "pair_whitelist": ["BTC/USDT", "ETH/USDT"]}}), encoding="utf-8")
    monkeypatch.setattr(driver, "USER_DATA", user_data)
    monkeypatch.setattr(driver, "STRATEGY_DIR", user_data / "strategies")
    monkeypatch.setattr(driver, "BACKTEST_RESULTS", user_data / "backtest_results")
    fake = NullEngine(user_data)
    monkeypatch.setattr(driver.subprocess, "run", fake)
    return fake


def null_payload(path: Path, state: str = "PREREGISTERED", **outcome) -> dict:
    p = json.loads(path.read_text())
    payload = {
        "schema_version": "1.0.0", "family_id": p["family_id"], "lineage_id": p["lineage_id"],
        "candidate_id": p["candidate_id"], "config_id": f"{p['candidate_id']}/CFG1",
        "experiment_id": p["experiment_id"], "run_id": p["run_id"], "trial_id": p["trial_id"], "state": state,
        "purpose": "unit-test fixture ledger; not a research trial",
        "dataset_identity": {"prereg_file": path.relative_to(REPO_ROOT).as_posix(), "prereg_sha256": _sha(path),
                             "lineage_kind": p["lineage_kind"]},
    }
    if state != "PREREGISTERED":
        payload["outcome"] = {"reason": "fixture", **outcome}
    return payload


def both_bound(tmp_path: Path, *extra: dict) -> Path:
    return make_ledger(tmp_path, null_payload(NULL1), null_payload(NULL2), *extra)


def real(path: Path, ledger: Path, tmp_path: Path) -> list[str]:
    return ["--prereg", str(path), "--ledger", str(ledger), "--artifacts-dir", str(tmp_path / "art")]


@pytest.mark.parametrize("path", NULLS)
def test_each_null_preregistration_validates_and_plans_six_fee_carrying_invocations(path, tmp_path, engine,
                                                                                    capsys):
    prereg = driver.load_prereg(path)
    assert prereg["lineage_kind"] == "NULL_CALIBRATION" and prereg["trial_class"] == "calibration"
    assert [c["params"] for c in prereg["grid"]] == [{}]
    assert driver.main(["--prereg", str(path), "--ledger", str(both_bound(tmp_path)), "--dry-run"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ledger"]["binding"] == "BOUND"
    assert len(out["plan"]) == 6
    assert all(s["argv"].count("--fee") == 1 for s in out["plan"])
    assert sorted(float(s["argv"][-1]) for s in out["plan"]) == [0.001] * 4 + [0.002] * 2
    b = out["budget"]
    assert b["consumed_before"]["engine_invocations"] == 0
    assert b["consumed_after"]["engine_invocations"] == 12  # 6 reserved for the other open null + 6 planned
    assert b["consumed_after"]["calibration_trial_ids"] == 2
    assert b["consumed_after"]["scientific_trial_ids"] == 0 and b["consumed_after"]["scientific_configurations"] == 0
    assert engine.calls == []


@pytest.mark.parametrize("path", NULLS)
def test_each_null_preregistration_is_bound_in_the_canonical_ledger(path, engine, capsys):
    before = CANONICAL_LEDGER.read_bytes()
    assert driver.main(["--prereg", str(path), "--dry-run"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ledger"]["binding"] == "BOUND"
    assert out["budget"]["consumed_after"]["engine_invocations"] == 12
    assert out["budget"]["consumed_after"]["calibration_trial_ids"] == 2
    assert CANONICAL_LEDGER.read_bytes() == before


def test_the_null_preregistrations_bind_the_frozen_law_and_unchanged_fixtures():
    for path in NULLS:
        p = json.loads(path.read_text())
        assert p["funnel_law"] == {"record": LAW_RECORD, "sha256": _sha(REPO_ROOT / LAW_RECORD)}
        for f in p["fixture_files"]:
            assert f["sha256"] == _sha(REPO_ROOT / f["path"])
        assert p["pair_universe"] == ["BTC/USDT"]
        assert p["multiple_testing"] == {"dsr_threshold": 0.95, "pbo_threshold": 0.05, "pbo_block_count": 8,
                                         "periods_per_year": 8760, "effective_trials": 2}
    assert "requires_prior_terminal" not in json.loads(NULL1.read_text())
    assert json.loads(NULL2.read_text())["requires_prior_terminal"] == {"trial_id": "TRIAL-C2-NULL-MATCHFREQ-1",
                                                                         "state": "REJECTED"}


def test_a_fixture_whose_sha256_does_not_match_is_refused(tmp_path, engine, capsys):
    p = json.loads(NULL1.read_text())
    p["fixture_files"][1]["sha256"] = "0" * 64
    path = write_prereg(tmp_path, p)
    assert driver.main(["--prereg", str(path), "--ledger", str(make_ledger(tmp_path)), "--dry-run"]) == 2
    assert "fixture file research/null_controls/null_matched_frequency_schedule.json" in capsys.readouterr().err


def test_empty_params_are_allowed_only_for_null_calibration(tmp_path):
    p = base_prereg()
    p["grid"] = [{"config_id": "A", "params": {}, "regime_gated": False}]
    with pytest.raises(driver.DriverRefusal, match="prereg.schema.json"):
        driver.load_prereg(write_prereg(tmp_path, p))
    p.update({"trial_class": "calibration", "experiment_id": "EXP-CYCLE2-CAL-FIXTURE",
              "lineage_kind": "NULL_CALIBRATION", "funnel_step": "NULL_RECALIBRATION"})
    assert driver.load_prereg(write_prereg(tmp_path, p))["grid"][0]["params"] == {}


def test_requires_prior_terminal_accepts_only_rejected(tmp_path):
    p = json.loads(NULL2.read_text())
    p["requires_prior_terminal"]["state"] = "COMPLETED"
    with pytest.raises(driver.DriverRefusal, match="prereg.schema.json"):
        driver.load_prereg(write_prereg(tmp_path, p))


def test_a_null_real_run_installs_its_fixtures_byte_unchanged_and_writes_no_params(tmp_path, null_engine):
    assert driver.main(real(NULL1, both_bound(tmp_path), tmp_path)) == 0
    assert len(null_engine.docker_calls()) == 6
    for f in json.loads(NULL1.read_text())["fixture_files"]:
        src = REPO_ROOT / f["path"]
        assert (driver.STRATEGY_DIR / src.name).read_bytes() == src.read_bytes()
    assert not (driver.STRATEGY_DIR / "NullControlMatchedFrequency.json").exists()
    config = json.loads((driver.USER_DATA / "config.research.json").read_text())
    assert config["exchange"]["pair_whitelist"] == ["BTC/USDT"]
    assert all(c[c.index("--fee") + 1] in ("0.001", "0.002") for c in null_engine.docker_calls())


def test_null_one_runs_while_null_two_is_open_and_sequencing_blocked(tmp_path, null_engine):
    ledger = both_bound(tmp_path)
    assert driver.main(real(NULL1, ledger, tmp_path)) == 0
    summary = json.loads((tmp_path / "art" / "cycle2_run_summary.json").read_text())
    assert summary["budget"]["reserved_open_trials"] == {"TRIAL-C2-NULL-BLOCKSHUF-1": 6}
    assert summary["budget"]["consumed_after"]["engine_invocations"] == 12


def test_null_two_is_refused_without_a_null_one_terminal(tmp_path, null_engine, capsys):
    ledger = both_bound(tmp_path)
    assert driver.main(real(NULL2, ledger, tmp_path)) == 2
    assert "TRIAL-C2-NULL-MATCHFREQ-1" in capsys.readouterr().err
    assert null_engine.calls == []
    seq = driver.sequencing(driver.load_prereg(NULL2), ledger)
    assert seq["status"] == "BLOCKED"
    assert seq["reasons"] == ["requires_prior_terminal: the ledger holds no terminal record for "
                              "TRIAL-C2-NULL-MATCHFREQ-1"]


@pytest.mark.parametrize("state,outcome", [
    ("SURVIVED", {"funnel_result": "SURVIVED"}),
    ("COMPLETED", {"funnel_result": "INCONCLUSIVE"}),
    ("ABORTED", {}),
])
def test_null_two_is_refused_unless_null_one_was_rejected(tmp_path, null_engine, capsys, state, outcome):
    ledger = both_bound(tmp_path, null_payload(NULL1, state, engine_invocations=6, **outcome))
    assert driver.main(real(NULL2, ledger, tmp_path)) == 2
    err = capsys.readouterr().err
    assert f"is {state}, not REJECTED" in err and "Cycle-2 STOP" in err
    assert null_engine.calls == []


def test_null_two_runs_only_once_null_one_is_rejected(tmp_path, null_engine):
    ledger = both_bound(tmp_path, null_payload(NULL1, "REJECTED", engine_invocations=6, funnel_result="REJECTED"))
    assert driver.main(real(NULL2, ledger, tmp_path)) == 0
    assert len(null_engine.docker_calls()) == 6
    summary = json.loads((tmp_path / "art" / "cycle2_run_summary.json").read_text())
    assert summary["budget"]["consumed_after"]["engine_invocations"] == 12


@pytest.mark.parametrize("state", ["SURVIVED", "COMPLETED", "ABORTED", "FAILED"])
def test_any_non_rejected_null_terminal_blocks_every_later_cycle2_run(tmp_path, engine, capsys, state):
    prereg = base_prereg()
    path = write_prereg(tmp_path, prereg)
    ledger = make_ledger(tmp_path, null_payload(NULL1), null_payload(NULL1, state, engine_invocations=6),
                         ledger_payload(prereg, "PREREGISTERED", prereg_sha=_sha(path)))
    assert driver.main(["--prereg", str(path), "--ledger", str(ledger), "--artifacts-dir",
                        str(tmp_path / "a")]) == 2
    assert "Cycle-2 STOP" in capsys.readouterr().err
    assert engine.calls == []


def test_a_rejected_null_does_not_block_a_later_cycle2_run(tmp_path, engine):
    prereg = base_prereg()
    path = write_prereg(tmp_path, prereg)
    ledger = make_ledger(tmp_path, null_payload(NULL1), null_payload(NULL1, "REJECTED", engine_invocations=6),
                         ledger_payload(prereg, "PREREGISTERED", prereg_sha=_sha(path)))
    assert driver.main(["--prereg", str(path), "--ledger", str(ledger), "--artifacts-dir",
                        str(tmp_path / "a")]) == 0


def test_an_open_trial_that_could_have_run_still_refuses_a_real_run(tmp_path, engine, capsys):
    prereg = base_prereg()
    path = write_prereg(tmp_path, prereg)
    ledger = make_ledger(tmp_path, null_payload(NULL1),
                         ledger_payload(prereg, "PREREGISTERED", prereg_sha=_sha(path)))
    assert driver.main(["--prereg", str(path), "--ledger", str(ledger), "--artifacts-dir",
                        str(tmp_path / "a")]) == 2
    assert "TRIAL-C2-NULL-MATCHFREQ-1 is preregistered but not closed" in capsys.readouterr().err
    assert engine.calls == []
    # the dry run reserves it instead, at its full plan
    assert driver.main(["--prereg", str(path), "--ledger", str(ledger), "--dry-run"]) == 0


def test_a_dry_run_reports_sequencing_without_executing(tmp_path, engine, capsys):
    assert driver.main(["--prereg", str(NULL2), "--ledger", str(both_bound(tmp_path)), "--dry-run"]) == 0
    seq = json.loads(capsys.readouterr().out)["sequencing"]
    assert seq["status"] == "BLOCKED"
    assert engine.calls == []
