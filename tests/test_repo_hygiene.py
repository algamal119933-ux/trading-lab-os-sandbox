"""CLOUD-0 / C0.2 — secret and artifact hygiene."""

from __future__ import annotations

import subprocess

import pytest

import verify_repo


def tracked(repo_root) -> list[str]:
    return subprocess.check_output(["git", "-C", str(repo_root), "ls-files"], text=True).split()


def test_repository_passes_every_deterministic_check(capsys):
    assert verify_repo.main([]) == 0
    assert "REPO_CHECK_PASS" in capsys.readouterr().out


def test_no_secret_material_is_tracked(repo_root):
    problems: list[str] = []
    verify_repo.check_secrets(tracked(repo_root), problems)
    assert problems == []


def test_no_forbidden_artifact_is_tracked(repo_root):
    problems: list[str] = []
    verify_repo.check_forbidden(tracked(repo_root), problems)
    assert problems == []


def test_every_tracked_json_and_yaml_parses(repo_root):
    problems: list[str] = []
    verify_repo.check_parsable(tracked(repo_root), problems)
    assert problems == []


def test_no_source_file_is_left_untracked():
    """An untracked file works locally and is simply absent in CI."""
    problems: list[str] = []
    verify_repo.check_untracked(problems)
    assert problems == []


def test_manifest_is_current(repo_root):
    problems: list[str] = []
    verify_repo.check_manifest(tracked(repo_root), problems, fix=False)
    assert problems == []


@pytest.mark.parametrize(
    "path",
    [
        ".env",
        "freqtrade/user_data/config.json",
        "freqtrade/user_data/data/binance/BTC_USDT-1h.feather",
        "freqtrade/user_data/logs/freqtrade.log",
        "freqtrade/user_data/tradesv3.sqlite",
        "mlruns/0/meta.yaml",
        "certs/exchange.pem",
        "freqtrade/user_data/backtest_results/result.json",
        "archive.zip",
        "set/roots/trading.tar.zst",
        "set/git/trading.bundle",
        "runtime/state.db",
    ],
)
def test_forbidden_paths_are_detected(path):
    problems: list[str] = []
    verify_repo.check_forbidden([path], problems)
    assert problems, f"{path} should be rejected"


def test_env_example_is_allowed():
    problems: list[str] = []
    verify_repo.check_forbidden([".env.example"], problems)
    assert problems == []


@pytest.mark.parametrize(
    "content",
    [
        "-----BEGIN RSA PRIVATE KEY-----\nabc\n",  # allowlist-secret: detector fixture
        "token = ghp_abcdefghijklmnopqrstuvwxyz0123456789\n",  # allowlist-secret: detector fixture
        "aws = AKIAIOSFODNN7EXAMPLE\n",  # allowlist-secret: detector fixture
        'cfg = {"secret": "0123456789abcdef"}\n',  # allowlist-secret: detector fixture
        "bot = 123456789:AAabcdefghijklmnopqrstuvwxyz0123456\n",  # allowlist-secret: detector fixture
    ],
)
def test_secret_patterns_are_detected(tmp_path, monkeypatch, content):
    leak = tmp_path / "leak.py"
    leak.write_text(content, encoding="utf-8")
    monkeypatch.setattr(verify_repo, "REPO_ROOT", tmp_path)
    problems: list[str] = []
    verify_repo.check_secrets(["leak.py"], problems)
    assert problems, f"undetected secret pattern: {content!r}"


@pytest.mark.parametrize(
    "path",
    [
        ".env",
        "freqtrade/user_data/config.json",
        "freqtrade/user_data/data/binance/BTC_USDT-1h.feather",
        "freqtrade/user_data/tradesv3.sqlite",
        "mlruns/0/meta.yaml",
        "freqtrade/user_data/backtest_results/x.json",
        "private.pem",
        "state.db",
        "set.bundle",
        "set/roots/x.tar.zst",
        "rendered.yml",
    ],
)
def test_gitignore_covers_local_only_artifacts(repo_root, path):
    result = subprocess.run(
        ["git", "-C", str(repo_root), "check-ignore", "-q", path],
        check=False,
    )
    assert result.returncode == 0, f"{path} is not ignored"


def test_env_example_stays_trackable(repo_root):
    result = subprocess.run(
        ["git", "-C", str(repo_root), "check-ignore", "-q", ".env.example"],
        check=False,
    )
    assert result.returncode != 0, ".env.example must remain trackable"


def test_env_example_contains_only_placeholders(repo_root):
    text = (repo_root / ".env.example").read_text(encoding="utf-8")
    for line in text.splitlines():
        if not line.strip() or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if any(hint in key.upper() for hint in ("PASSWORD", "SECRET", "TOKEN")):
            assert value.startswith("CHANGE_ME"), f"{key} must ship as a placeholder"


def test_git_history_never_carried_a_secret_bearing_path(repo_root):
    out = subprocess.check_output(
        ["git", "-C", str(repo_root), "log", "--all", "--pretty=format:", "--name-only", "--diff-filter=A"],
        text=True,
    )
    historical = sorted({line for line in out.splitlines() if line.strip()})
    problems: list[str] = []
    verify_repo.check_forbidden(historical, problems)
    assert problems == [], f"a forbidden artifact was committed at some point: {problems}"
