"""P3-PLN-06: the master plan §19 CRITICAL checks in research/p3/health.py.

Synthetic fixtures only. Each condition has a positive (CRITICAL) and a negative (INFO) case, secret
values never reach a finding, and the emitted check names are exactly the labels the promtool rule
tests use. PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
for _extra in (str(REPO_ROOT / "research"), str(REPO_ROOT / "scripts")):
    if _extra not in sys.path:
        sys.path.insert(0, _extra)

from p3 import health, kill_switch  # noqa: E402

SECRET = "s3cr3t-value-that-must-never-appear"
EXAMPLE = REPO_ROOT / "freqtrade" / "user_data" / "config.paper.json.example"
RULE_TESTS = REPO_ROOT / "scripts" / "p3" / "ops" / "rules" / "tlos_p3_alerts.test.yml"


def _cfg(tmp_path: Path, name: str = "config.json", **overrides) -> Path:
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    data.update(overrides)
    path = tmp_path / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _real_checker():
    return health.default_s19_inputs(REPO_ROOT)["config_checker"]


# --- paper guard failure ------------------------------------------------------------------------------

def test_paper_guard_passes_the_committed_example():
    f = health.paper_guard_configs([EXAMPLE], _real_checker())
    assert f["check"] == "paper_guard" and f["severity"] == "INFO"


def test_paper_guard_failure_is_critical(tmp_path):
    f = health.paper_guard_configs([_cfg(tmp_path, dry_run=False, max_open_trades=99)], _real_checker())
    assert f["severity"] == "CRITICAL" and "dry_run" in f["detail"]


def test_a_guard_that_cannot_run_is_critical_not_healthy(tmp_path):
    def broken(_):
        raise RuntimeError("boom")
    assert health.paper_guard_configs([_cfg(tmp_path)], broken)["severity"] == "CRITICAL"


def test_no_config_on_the_host_is_info(tmp_path):
    assert health.paper_guard_configs([tmp_path / "absent.json"], _real_checker())["severity"] == "INFO"


# --- real-money-enabled state -------------------------------------------------------------------------

def test_clean_paper_state_is_info(tmp_path):
    env = tmp_path / ".env"
    env.write_text("FREQTRADE_API_PASSWORD=x\nFREQTRADE__API_SERVER__USERNAME=u\nFREQTRADE__DRY_RUN=true\n")
    f = health.real_money_state([_cfg(tmp_path)], [env], {"tradinglab-fp-control-3": {"FREQTRADE__DRY_RUN": "true"}})
    assert f["check"] == "real_money" and f["severity"] == "INFO"


@pytest.mark.parametrize("case", ["config_dry_run", "config_key", "ccxt_secret", "env_secret", "env_dry_run",
                                  "container_secret", "container_dry_run"])
def test_every_live_switch_is_critical_and_never_leaks_the_value(tmp_path, case):
    configs, envs, containers = [_cfg(tmp_path)], [], {}
    if case == "config_dry_run":
        configs = [_cfg(tmp_path, dry_run=False)]
    elif case == "config_key":
        data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        data["exchange"]["key"] = SECRET
        configs = [_cfg(tmp_path, exchange=data["exchange"])]
    elif case == "ccxt_secret":
        data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        data["exchange"]["ccxt_config"] = {"secret": SECRET}
        configs = [_cfg(tmp_path, exchange=data["exchange"])]
    elif case == "env_secret":
        (tmp_path / ".env").write_text(f"export FREQTRADE__EXCHANGE__SECRET='{SECRET}'\n")
        envs = [tmp_path / ".env"]
    elif case == "env_dry_run":
        (tmp_path / ".env").write_text("FREQTRADE__DRY_RUN=false\n")
        envs = [tmp_path / ".env"]
    elif case == "container_secret":
        containers = {"tlos-h1-paper-cohort-1-freqtrade": {"FREQTRADE__EXCHANGE__KEY": SECRET}}
    elif case == "container_dry_run":
        containers = {"tradinglab-fp-control-3": {"FREQTRADE__DRY_RUN": "False"}}
    f = health.real_money_state(configs, envs, containers)
    assert f["severity"] == "CRITICAL", f
    assert SECRET not in json.dumps(f)


def test_container_env_is_parsed_by_name_only():
    class R:
        returncode = 0
        stdout = f"PATH=/usr/bin\nFREQTRADE__EXCHANGE__KEY={SECRET}\n"
    envs = health._container_envs(["tradinglab-fp-control-3"], lambda cmd: R())
    f = health.real_money_state([], [], envs)
    assert f["severity"] == "CRITICAL" and SECRET not in f["detail"]


# --- broken evidence chains ---------------------------------------------------------------------------

def _ledger(path: Path, n: int = 3) -> Path:
    prev, lines = kill_switch.GENESIS, []
    for i in range(n):
        rec = {"seq": i, "utc": f"2026-10-26T00:0{i}:00Z", "outcome": "STOPPED", "prev_digest": prev}
        rec["digest"] = kill_switch._digest(rec)
        prev = rec["digest"]
        lines.append(json.dumps(rec))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_intact_operator_ledger_is_info(tmp_path):
    f = health.operator_ledger_chain(_ledger(tmp_path / "l.jsonl"), kill_switch.verify_ledger)
    assert f["check"] == "evidence_chain:operator_ledger" and f["severity"] == "INFO"


def test_tampered_operator_ledger_is_critical(tmp_path):
    path = _ledger(tmp_path / "l.jsonl")
    lines = path.read_text().splitlines()
    rec = json.loads(lines[1])
    rec["outcome"] = "RESUMED"
    lines[1] = json.dumps(rec)
    path.write_text("\n".join(lines) + "\n")
    assert health.operator_ledger_chain(path, kill_switch.verify_ledger)["severity"] == "CRITICAL"


def test_absent_operator_ledger_is_a_warning_not_healthy(tmp_path):
    assert health.operator_ledger_chain(tmp_path / "none.jsonl", kill_switch.verify_ledger)["severity"] == "WARNING"


def _archive(root: Path, name: str) -> Path:
    archive = root / "artifacts" / name
    archive.mkdir(parents=True)
    (archive / "archive_manifest.json").write_text("{}")
    return archive


def test_sealed_archives_verified_is_info_and_a_broken_one_is_critical(tmp_path):
    good, bad = _archive(tmp_path / "a", "l2-cohort-1"), _archive(tmp_path / "b", "l2-cohort-2")

    def verifier(archive):
        if archive == bad:
            raise RuntimeError("no longer matches its sealed manifest")
        return {}
    ok = health.sealed_archives([tmp_path / "a"], verifier)
    assert ok["check"] == "evidence_chain:sealed_archives" and ok["severity"] == "INFO" and "1 sealed" in ok["detail"]
    broken = health.sealed_archives([tmp_path / "a", tmp_path / "b"], verifier)
    assert broken["severity"] == "CRITICAL" and "l2-cohort-2" in broken["detail"]
    assert good.is_dir()


def test_no_sealed_archive_is_a_warning(tmp_path):
    assert health.sealed_archives([tmp_path], lambda a: {})["severity"] == "WARNING"


def test_real_archive_verifier_detects_a_changed_sealed_file(tmp_path):
    verify = health.default_s19_inputs(REPO_ROOT)["archive_verifier"]
    from fp import archive as fp_archive
    archive = tmp_path / "x" / "artifacts" / "l2-cohort-test"
    archive.mkdir(parents=True)
    (archive / "tradesv3.sqlite").write_bytes(b"sealed-db-bytes")
    manifest = {"role": "FP-CONTROL-T", "archived_utc": "2026-10-26T00:00:00Z", "source_lane": "lane",
                "file_count": 1, "total_bytes": 15, "evidence": {},
                "files": {"tradesv3.sqlite": fp_archive.sha256_path(archive / "tradesv3.sqlite")}}
    (archive / fp_archive.ARCHIVE_MANIFEST).write_text(json.dumps(manifest))
    assert health.sealed_archives([tmp_path / "x"], verify)["severity"] == "INFO"
    (archive / "tradesv3.sqlite").write_bytes(b"corrupted-db-bytes")  # §19 'DB corruption' of sealed evidence
    assert health.sealed_archives([tmp_path / "x"], verify)["severity"] == "CRITICAL"


# --- unauthorized execution / stopped control ---------------------------------------------------------

REG = {"instances": [{"role": "FP-CONTROL-3", "status": "CLOSED"}]}
REG_RUNNING = {"instances": [{"role": "FP-CONTROL-4", "status": "RUNNING"}]}


def test_no_paper_runtime_and_no_running_cohort_is_info():
    [f] = health.paper_runtime_vs_registry(REG, {})
    assert f["check"] == "unauthorized_execution" and f["severity"] == "INFO"


def test_a_paper_container_without_a_running_cohort_is_unauthorized_execution():
    # The current state of authority: H1_LAUNCH_AUTHORIZED = NO, so a running H1 container is unauthorized.
    [f] = health.paper_runtime_vs_registry(REG, {"tlos-h1-paper-cohort-1-freqtrade": "running"})
    assert f["severity"] == "CRITICAL"


def test_a_running_cohort_without_its_container_is_a_stopped_control():
    found = {f["check"]: f for f in health.paper_runtime_vs_registry(REG_RUNNING, {"tradinglab-fp-control-4": "exited"})}
    assert found["control_running:FP-CONTROL-4"]["severity"] == "CRITICAL"
    found = {f["check"]: f for f in health.paper_runtime_vs_registry(REG_RUNNING, {"tradinglab-fp-control-4": "running"})}
    assert found["control_running:FP-CONTROL-4"]["severity"] == "INFO"
    assert found["unauthorized_execution"]["severity"] == "INFO"


def test_docker_unavailable_is_unproven_not_healthy():
    [f] = health.paper_runtime_vs_registry(REG, None)
    assert f["severity"] == "WARNING" and "UNKNOWN" in f["detail"]


# --- wiring -------------------------------------------------------------------------------------------

def test_s19_findings_end_to_end_with_fakes(tmp_path):
    class R:
        def __init__(self, out):
            self.returncode, self.stdout, self.stderr = 0, out, ""

    def docker(cmd):
        if cmd[0] == "ps":
            return R("moneyprinterturbo-api\trunning\n")
        return R("")
    findings = health.s19_findings(
        REG, paper_configs=[_cfg(tmp_path)], env_files=[], ledger=_ledger(tmp_path / "l.jsonl"),
        archive_roots=[_archive(tmp_path / "r", "a1").parent.parent], config_checker=_real_checker(),
        ledger_verifier=kill_switch.verify_ledger, archive_verifier=lambda a: {}, docker_runner=docker)
    checks = {f["check"]: f["severity"] for f in findings}
    assert checks == {"paper_guard": "INFO", "real_money": "INFO", "evidence_chain:operator_ledger": "INFO",
                      "evidence_chain:sealed_archives": "INFO", "unauthorized_execution": "INFO"}
    text = health.prometheus_text(findings)
    for check in checks:
        assert f'tlos_p3_health_check{{check="{check}"}} 0' in text


def test_standard_findings_without_s19_is_unchanged(tmp_path):
    class R:
        returncode, stdout, stderr = 0, "enabled\n", ""
    findings = health.standard_findings({"instances": []}, runner=lambda cmd: R(), verifier=None,
                                        lane=tmp_path, backup_target=tmp_path, fp_lane_root=tmp_path)
    assert not any(f["check"] in ("paper_guard", "real_money") for f in findings)


def test_the_promtool_rule_tests_cover_every_s19_check_label():
    text = RULE_TESTS.read_text(encoding="utf-8")
    for label in ("paper_guard", "real_money", "evidence_chain:operator_ledger", "evidence_chain:sealed_archives",
                  "unauthorized_execution", "control_running:FP-CONTROL-3"):
        assert f'check="{label}"' in text and f'check: "{label}"' in text


def test_health_cli_runs_the_s19_checks_by_default():
    src = (REPO_ROOT / "scripts" / "p3" / "health_check.py").read_text(encoding="utf-8")
    assert "default_s19_inputs(REPO_ROOT)" in src and "--no-s19" in src
    out = subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "p3" / "health_check.py"), "--help"],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0 and "--no-s19" in out.stdout


def test_the_s19_defaults_are_read_only_paths_and_never_secret_values():
    inputs = health.default_s19_inputs(REPO_ROOT)
    assert inputs["env_files"] == [health.RUNTIME_ROOT / ".env"]
    assert health.OPERATOR_LEDGER.name == "operator_ledger.jsonl"
    assert hashlib.sha256(EXAMPLE.read_bytes()).hexdigest()  # the example stays readable
