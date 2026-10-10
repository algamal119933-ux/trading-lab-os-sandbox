"""CV-03: the minimum isolated runner refuses unsafe cases and plans an isolated container.

These tests need no Docker: they check what the runner refuses and the exact
command it would run. PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER = REPO_ROOT / "verification" / "runner"
_spec = importlib.util.spec_from_file_location("verification_run_case", RUNNER / "run_case.py")
rc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rc)

STRATEGY = """from freqtrade.strategy import IStrategy
class T(IStrategy):
    timeframe = '1h'
    minimal_roi = {"0": 0.02}
    stoploss = -0.05
"""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def case(tmp_path: Path) -> Path:
    d = tmp_path / "case"
    (d / "strategy").mkdir(parents=True)
    (d / "strategy" / "T.py").write_text(STRATEGY, encoding="utf-8")
    cfg = json.loads(rc.PAPER_EXAMPLE.read_text(encoding="utf-8"))
    cfg.pop("api_server")
    (d / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    (d / "exchangeInfo.json").write_text('{"symbols": []}', encoding="utf-8")
    write_case(d)
    (tmp_path / "data").mkdir()
    return d


def write_case(d: Path, **over) -> None:
    case = {"case_id": "C-900", "strategy_class": "T", "strategy_file": "strategy/T.py",
            "strategy_sha256": _sha(d / "strategy" / "T.py"), "params_file": None, "params_sha256": None,
            "config_file": "config.json", "config_sha256": _sha(d / "config.json"),
            "markets_file": "exchangeInfo.json", "markets_sha256": _sha(d / "exchangeInfo.json"),
            "timeframe": "1h", "timerange": "20240105-", "fee": 0.001}
    case.update(over)
    (d / "case.json").write_text(json.dumps(case), encoding="utf-8")


def plan(case: Path, containers=(), env=None, execute=False, out=None) -> list[str]:
    return rc.prepare(case, case.parent / "data", out or case.parent / "out", containers=list(containers),
                      env=env or {}, execute=execute)


def test_the_planned_container_is_isolated(case):
    cmd = plan(case)
    joined = " ".join(cmd)
    assert cmd[cmd.index("--network") + 1] == "none"
    for flag in ("--read-only", "no-new-privileges", "--cap-drop ALL", "--user 1000:1000", "--rm"):
        assert flag in joined, flag
    assert rc.IMAGE in cmd and re.fullmatch(r"freqtradeorg/freqtrade@sha256:[0-9a-f]{64}", rc.IMAGE)
    mounts = [cmd[i + 1] for i, part in enumerate(cmd) if part == "-v"]
    assert [m for m in mounts if not m.endswith(":ro")] == [f"{(case.parent / 'out' / 'results').resolve()}:/out:rw"]


def test_the_engine_is_pinned_by_digest_not_tag():
    assert rc.ENGINE["index_digest"].startswith("sha256:") and len(rc.ENGINE["index_digest"]) == 71
    assert ":" + rc.ENGINE["tag"] not in rc.IMAGE


def test_the_effective_config_reaches_only_loopback_and_passes_the_paper_guard(case):
    plan(case)
    effective = json.loads((case.parent / "out" / "effective_config.json").read_text(encoding="utf-8"))
    urls = json.dumps(effective["exchange"]["ccxt_config"]["urls"])
    assert set(re.findall(r"https?://([^/:\"]+)", urls)) == {"127.0.0.1"}
    violations = rc.paper_guard.Violations()
    rc.paper_guard.check_config(case.parent / "out" / "effective_config.json", violations)
    assert violations == []
    assert json.loads((case / "config.json").read_text(encoding="utf-8")).get("api_server") is None


def test_the_cloud_executor_never_executes_a_case(case):
    with pytest.raises(rc.Refused, match="cloud executor"):
        plan(case, env={"CLAUDE_CODE_REMOTE": "true"}, execute=True)
    plan(case, env={"CLAUDE_CODE_REMOTE": "true"}, execute=False)


def test_the_p2_host_is_refused(case):
    with pytest.raises(rc.Refused, match="P2 host"):
        plan(case, containers=["tradinglab-fpc3-freqtrade", "other"])


def test_paths_inside_the_repository_are_refused(case):
    with pytest.raises(rc.Refused, match="inside the repository"):
        plan(case, out=REPO_ROOT / "verification" / "runner" / "out")


@pytest.mark.parametrize("name", ["strategy/T.py", "config.json", "exchangeInfo.json"])
def test_a_file_that_does_not_match_its_pin_is_refused(case, name):
    (case / name).write_text((case / name).read_text(encoding="utf-8") + "\n# changed\n", encoding="utf-8")
    with pytest.raises(rc.Refused, match="pinned sha256"):
        plan(case)


def test_a_path_escaping_the_case_is_refused(case):
    write_case(case, strategy_file="../T.py")
    with pytest.raises(rc.Refused, match="relative path inside"):
        plan(case)


@pytest.mark.parametrize("change", [{"dry_run": False}, {"trading_mode": "futures"}, {"can_short": True},
                                    {"leverage": 3}])
def test_a_config_outside_the_paper_boundary_is_refused(case, change):
    cfg = json.loads((case / "config.json").read_text(encoding="utf-8"))
    cfg.update(change)
    (case / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    write_case(case)
    with pytest.raises(rc.Refused, match="paper guard"):
        plan(case)


def test_exchange_credentials_are_refused(case):
    cfg = json.loads((case / "config.json").read_text(encoding="utf-8"))
    cfg["exchange"]["key"] = "abc"
    (case / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    write_case(case)
    with pytest.raises(rc.Refused, match="paper guard"):
        plan(case)


def test_a_shorting_strategy_is_refused(case):
    (case / "strategy" / "T.py").write_text(STRATEGY + "    can_short = True\n", encoding="utf-8")
    write_case(case)
    with pytest.raises(rc.Refused, match="shorts"):
        plan(case)


def test_the_runner_uses_existing_interfaces_as_is():
    source = (RUNNER / "run_case.py").read_text(encoding="utf-8")
    assert '"scripts" / "paper_guard.py"' in source
    assert "cycle2" not in source
    assert {p.name for p in RUNNER.iterdir()} == {"README.md", "run_case.py", "entrypoint.sh", "engine.json"}


def test_the_entrypoint_serves_only_the_pinned_snapshot_on_loopback():
    text = (RUNNER / "entrypoint.sh").read_text(encoding="utf-8")
    assert "--bind 127.0.0.1" in text
    assert 'cp "$CASE_DIR/exchangeInfo.json"' in text
    assert "exec freqtrade backtesting" in text
