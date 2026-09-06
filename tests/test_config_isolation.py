"""CLOUD-0 / C0.4 — configuration isolation and precedence.

The failure this guards against is a silent one: a value living in both the
config and the strategy, so a backtest is not reproducible from the strategy file
and the effective settings are only discoverable by running the container.
"""

from __future__ import annotations

import json

import pytest

import effective_config
import paper_guard


CONFIG_EXAMPLE = "freqtrade/user_data/config.paper.json.example"


def test_runtime_config_json_is_not_tracked(repo_root):
    """config.json is generated locally; tracking it would create two sources of truth."""
    import subprocess

    tracked = subprocess.check_output(["git", "-C", str(repo_root), "ls-files"], text=True).split()
    assert "freqtrade/user_data/config.json" not in tracked


def test_example_config_carries_no_strategy_owned_keys(example_config):
    overlap = sorted(set(paper_guard.STRATEGY_OWNED_KEYS) & set(example_config))
    assert overlap == [], f"config silently overrides strategy values: {overlap}"


def test_strategy_owns_roi_stoploss_and_timeframe(repo_root):
    strategy = (repo_root / "freqtrade/user_data/strategies/PlumbingSmokeStrategy.py").read_text()
    for token in ("timeframe", "minimal_roi", "stoploss"):
        assert token in strategy, f"{token} must be defined by the strategy"


def test_effective_config_matches_the_file_with_no_overrides(repo_root, example_config):
    report = effective_config.build([repo_root / CONFIG_EXAMPLE], [], environ={})
    effective = report["effective_config"]
    assert effective["dry_run"] is True
    assert effective["max_open_trades"] == example_config["max_open_trades"]
    assert report["environment_overrides_applied"] == []
    assert report["cli_overrides_applied"] == []


def test_environment_overrides_beat_the_config_file(repo_root):
    report = effective_config.build(
        [repo_root / CONFIG_EXAMPLE], [], environ={"FREQTRADE__MAX_OPEN_TRADES": "1"}
    )
    assert report["effective_config"]["max_open_trades"] == 1
    assert report["environment_overrides_applied"] == ["FREQTRADE__MAX_OPEN_TRADES"]


def test_cli_overrides_beat_the_environment(repo_root):
    report = effective_config.build(
        [repo_root / CONFIG_EXAMPLE],
        ["max_open_trades=3"],
        environ={"FREQTRADE__MAX_OPEN_TRADES": "1"},
    )
    assert report["effective_config"]["max_open_trades"] == 3


def test_nested_environment_override_reaches_a_section(repo_root):
    report = effective_config.build(
        [repo_root / CONFIG_EXAMPLE], [], environ={"FREQTRADE__EXCHANGE__NAME": "kraken"}
    )
    assert report["effective_config"]["exchange"]["name"] == "kraken"
    # Sibling keys in the same section survive the merge.
    assert "pair_whitelist" in report["effective_config"]["exchange"]


def test_credentials_are_redacted_and_never_hashed(repo_root, tmp_path):
    config = json.loads((repo_root / CONFIG_EXAMPLE).read_text())
    config["exchange"]["secret"] = "super-secret-value"
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")

    report = effective_config.build([path], [], environ={})
    rendered = json.dumps(report)
    assert "super-secret-value" not in rendered
    assert report["effective_config"]["exchange"]["secret"] == effective_config.REDACTED


def test_config_hash_is_stable_and_change_sensitive(repo_root):
    first = effective_config.build([repo_root / CONFIG_EXAMPLE], [], environ={})
    second = effective_config.build([repo_root / CONFIG_EXAMPLE], [], environ={})
    assert first["effective_config_sha256"] == second["effective_config_sha256"]

    changed = effective_config.build([repo_root / CONFIG_EXAMPLE], ["stake_amount=11"], environ={})
    assert changed["effective_config_sha256"] != first["effective_config_sha256"]


def test_secret_value_does_not_change_the_config_hash(repo_root, tmp_path):
    """Rotating a local password must not invalidate a recorded config fingerprint."""
    base = json.loads((repo_root / CONFIG_EXAMPLE).read_text())
    hashes = set()
    for password in ("password-one", "password-two"):
        config = json.loads(json.dumps(base))
        config["api_server"]["password"] = password
        path = tmp_path / f"{password}.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        hashes.add(effective_config.build([path], [], environ={})["effective_config_sha256"])
    assert len(hashes) == 1


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("1", 1), ("true", True), ("0.5", 0.5), ('["BTC/USDT"]', ["BTC/USDT"]), ("spot", "spot")],
)
def test_override_values_are_typed_like_freqtrade_parses_them(raw, expected):
    assert effective_config.coerce(raw) == expected


def test_fee_is_stated_explicitly_rather_than_inherited(example_config):
    """An exchange-default fee is invisible in the record and can change upstream."""
    assert example_config["fee"] == 0.001


def test_config_fee_matches_the_dataset_v2_lock(repo_root, example_config):
    import json

    lock = json.loads((repo_root / "research/datasets/dataset_v2.lock.json").read_text())
    assert example_config["fee"] == lock["fee_assumption"]["per_side_ratio"]


def test_config_sizing_matches_the_dataset_v2_lock(repo_root, example_config):
    import json

    lock = json.loads((repo_root / "research/datasets/dataset_v2.lock.json").read_text())
    sizing = lock["sizing"]
    assert example_config["dry_run_wallet"] == sizing["dry_run_wallet"]
    assert example_config["stake_amount"] == sizing["stake_amount"]
    assert example_config["max_open_trades"] == sizing["max_open_trades"]
    assert example_config["stake_currency"] == sizing["stake_currency"]


def test_precedence_is_documented_in_the_output(repo_root):
    report = effective_config.build([repo_root / CONFIG_EXAMPLE], [], environ={})
    assert report["precedence"] == "cli > environment > config file(s) > strategy defaults"
