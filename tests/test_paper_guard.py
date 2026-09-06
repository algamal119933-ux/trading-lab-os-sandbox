"""CLOUD-0 / C0.3 — the paper-safety invariant must fail closed.

Every test that mutates the shipped example config asserts that the guard
*rejects* it. A guard that only proves the happy path is not a safety control.
"""

from __future__ import annotations

import copy
import json

import pytest

import paper_guard


def run(path) -> int:
    return paper_guard.main(["--config", str(path), "--skip-strategies"])


def test_shipped_example_config_passes(capsys):
    assert paper_guard.main([]) == 0
    assert "PAPER_GUARD_PASS" in capsys.readouterr().out


def test_missing_config_fails_closed(tmp_path):
    assert paper_guard.main(["--config", str(tmp_path / "nope.json")]) == 2


def test_invalid_json_fails_closed(tmp_path):
    bad = tmp_path / "config.json"
    bad.write_text("{ not json", encoding="utf-8")
    assert run(bad) == 2


def test_empty_object_fails_closed(write_config):
    assert run(write_config({})) == 2


@pytest.mark.parametrize(
    ("mutation", "label"),
    [
        ({"dry_run": False}, "live trading"),
        ({"dry_run": "true"}, "stringly-typed dry_run"),
        ({"trading_mode": "futures"}, "futures"),
        ({"trading_mode": "margin"}, "margin"),
        ({"margin_mode": "isolated"}, "isolated margin"),
        ({"leverage": 3}, "leverage"),
        ({"max_leverage": 5}, "max leverage"),
        ({"can_short": True}, "shorting"),
        ({"max_open_trades": -1}, "unlimited open trades"),
        ({"max_open_trades": 25}, "excessive open trades"),
        ({"max_open_trades": 0}, "zero open trades"),
        ({"stake_amount": "unlimited"}, "unlimited stake"),
        ({"stake_amount": -5}, "negative stake"),
        ({"stake_amount": 500}, "stake above wallet"),
        ({"dry_run_wallet": 0}, "empty wallet"),
        ({"dry_run_wallet": 10_000_000}, "unbounded wallet"),
        ({"tradable_balance_ratio": 1.5}, "ratio above 1"),
        ({"force_entry_enable": True}, "forced entries"),
        ({"withdraw_enabled": True}, "withdrawal path"),
        ({"minimal_roi": {"0": 0.05}}, "config-level ROI"),
        ({"stoploss": -0.1}, "config-level stoploss"),
        ({"timeframe": "5m"}, "config-level timeframe"),
        ({"trailing_stop": True}, "config-level trailing stop"),
    ],
)
def test_unsafe_top_level_mutations_are_rejected(example_config, write_config, mutation, label):
    config = copy.deepcopy(example_config)
    config.update(mutation)
    assert run(write_config(config)) == 2, f"guard accepted {label}"


@pytest.mark.parametrize(
    "field",
    ["key", "secret", "password", "uid", "apiKey", "privateKey", "walletAddress"],
)
def test_exchange_credentials_are_rejected(example_config, write_config, field):
    config = copy.deepcopy(example_config)
    config["exchange"][field] = "AKIAIOSFODNN7EXAMPLEVALUE"
    assert run(write_config(config)) == 2


def test_ccxt_credentials_are_rejected(example_config, write_config):
    config = copy.deepcopy(example_config)
    config["exchange"]["ccxt_config"]["apiKey"] = "leaked-value"
    assert run(write_config(config)) == 2


def test_exchange_withdraw_key_is_rejected(example_config, write_config):
    config = copy.deepcopy(example_config)
    config["exchange"]["withdrawal_enabled"] = True
    assert run(write_config(config)) == 2


@pytest.mark.parametrize("pair", ["BTC/USDT:USDT", "BTCUP/USDT", "ETHDOWN/USDT", "BTC3L/USDT"])
def test_derivative_and_leveraged_pairs_are_rejected(example_config, write_config, pair):
    config = copy.deepcopy(example_config)
    config["exchange"]["pair_whitelist"] = [pair]
    assert run(write_config(config)) == 2


def test_empty_whitelist_is_rejected(example_config, write_config):
    config = copy.deepcopy(example_config)
    config["exchange"]["pair_whitelist"] = []
    assert run(write_config(config)) == 2


def test_telegram_enabled_is_rejected(example_config, write_config):
    config = copy.deepcopy(example_config)
    config["telegram"]["enabled"] = True
    assert run(write_config(config)) == 2


def test_disabled_api_server_is_rejected(example_config, write_config):
    config = copy.deepcopy(example_config)
    config["api_server"]["enabled"] = False
    assert run(write_config(config)) == 2


def test_guard_reports_every_violation_not_only_the_first(example_config, write_config, capsys):
    config = copy.deepcopy(example_config)
    config["dry_run"] = False
    config["trading_mode"] = "futures"
    config["max_open_trades"] = 50
    assert run(write_config(config)) == 2
    err = capsys.readouterr().err
    assert "dry_run" in err and "trading_mode" in err and "max_open_trades" in err


def test_no_config_present_at_all_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setattr(paper_guard, "DEFAULT_CANDIDATES", (tmp_path / "absent.json",))
    assert paper_guard.main([]) == 2


def test_committed_strategies_are_long_only_spot():
    violations = paper_guard.Violations()
    paper_guard.check_strategies(violations)
    assert violations == []


def test_shorting_strategy_is_rejected(monkeypatch, tmp_path):
    strategy = tmp_path / "ShortStrategy.py"
    strategy.write_text("class S:\n    can_short = True\n", encoding="utf-8")
    monkeypatch.setattr(paper_guard, "STRATEGY_DIR", tmp_path)
    monkeypatch.setattr(paper_guard, "REPO_ROOT", tmp_path)
    violations = paper_guard.Violations()
    paper_guard.check_strategies(violations)
    assert violations, "guard accepted a shorting strategy"


def test_guard_list_mode_names_the_shipped_example(capsys):
    assert paper_guard.main(["--list"]) == 0
    assert "config.paper.json.example" in capsys.readouterr().out


def test_runtime_config_when_present_is_also_checked(repo_root, monkeypatch, tmp_path):
    """A local config.json must be inspected, not skipped in favour of the example."""
    runtime = tmp_path / "config.json"
    runtime.write_text(json.dumps({"dry_run": False}), encoding="utf-8")
    monkeypatch.setattr(
        paper_guard,
        "DEFAULT_CANDIDATES",
        (runtime, repo_root / "freqtrade" / "user_data" / "config.paper.json.example"),
    )
    assert paper_guard.main([]) == 2
