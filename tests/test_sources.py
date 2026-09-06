"""Static sanity of every tracked source file.

Cheap checks that would otherwise only fail inside a container: Python must
compile, shell must parse, and the trading helper scripts must run the paper
guard before they touch Freqtrade.
"""

from __future__ import annotations

import ast
import shutil
import subprocess

import pytest


def tracked(repo_root, suffix: str) -> list[str]:
    out = subprocess.check_output(["git", "-C", str(repo_root), "ls-files", f"*{suffix}"], text=True)
    return [line for line in out.split() if line]


def test_every_tracked_python_file_compiles(repo_root):
    files = tracked(repo_root, ".py")
    assert files, "expected tracked Python files"
    for rel in files:
        source = (repo_root / rel).read_text(encoding="utf-8")
        try:
            ast.parse(source, filename=rel)
        except SyntaxError as exc:  # pragma: no cover - failure path
            pytest.fail(f"{rel}: {exc}")


def test_every_tracked_shell_script_parses(repo_root):
    scripts = tracked(repo_root, ".sh")
    assert scripts, "expected tracked shell scripts"
    bash = shutil.which("bash")
    assert bash, "bash is required to validate the helper scripts"
    for rel in scripts:
        result = subprocess.run([bash, "-n", str(repo_root / rel)], capture_output=True, text=True)
        assert result.returncode == 0, f"{rel}: {result.stderr}"


def test_shell_scripts_use_strict_mode(repo_root):
    for rel in tracked(repo_root, ".sh"):
        text = (repo_root / rel).read_text(encoding="utf-8")
        assert "set -euo pipefail" in text or "_common.sh" in text, f"{rel} is not strict-mode"


@pytest.mark.parametrize(
    "script",
    ["scripts/backtest.sh", "scripts/lookahead.sh", "scripts/recursive.sh",
     "scripts/download_data.sh", "scripts/start_paper.sh"],
)
def test_trading_scripts_run_the_paper_guard_first(repo_root, script):
    text = (repo_root / script).read_text(encoding="utf-8")
    assert "require_paper_config" in text, f"{script} does not invoke the paper guard"
    guard_at = text.index("require_paper_config")
    compose_at = text.find("docker compose")
    if compose_at != -1:
        assert guard_at < compose_at, f"{script} touches Freqtrade before guarding"


@pytest.mark.parametrize(
    "script",
    ["scripts/backtest.sh", "scripts/lookahead.sh", "scripts/recursive.sh", "scripts/download_data.sh"],
)
def test_research_scripts_require_an_explicit_timerange(repo_root, script):
    """An implicit window makes a result unreproducible, so it must be refused."""
    result = subprocess.run(["bash", script], cwd=str(repo_root), capture_output=True, text=True)
    assert result.returncode == 2
    assert "usage:" in result.stderr


def test_backtest_does_not_pin_a_timeframe_the_strategy_owns(repo_root):
    text = (repo_root / "scripts/backtest.sh").read_text(encoding="utf-8")
    assert "--timeframe " not in text, "timeframe must come from the strategy, not the script"


def test_powershell_bootstrapper_keeps_the_guard(repo_root):
    text = (repo_root / "START_WINDOWS.ps1").read_text(encoding="utf-8")
    assert "paper_guard.py" in text
    assert "Paper Guard failed" in text


def test_no_source_hardcodes_the_owners_local_machine(repo_root):
    """The cloud copy must not depend on paths that only exist on one Windows box."""
    needle = "C:" + "/trading_lab_os_v1"
    offenders = []
    for suffix in (".py", ".sh", ".yml", ".json"):
        for rel in tracked(repo_root, suffix):
            if rel == "tests/test_sources.py":
                continue  # this file names the pattern it looks for
            text = (repo_root / rel).read_text(encoding="utf-8", errors="ignore")
            if needle in text or needle.replace("/", "\\") in text:
                offenders.append(rel)
    assert offenders == [], f"local-machine paths leaked into: {offenders}"
