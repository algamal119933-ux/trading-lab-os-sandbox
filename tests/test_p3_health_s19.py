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


def test_no_config_on_the_host_is_unproven_not_healthy(tmp_path):
    f = health.paper_guard_configs([tmp_path / "absent.json"], _real_checker())
    assert f["severity"] == "WARNING" and "UNPROVEN" in f["detail"]


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
    envs, failed = health._container_envs(["tradinglab-fp-control-3"], lambda cmd: R())
    assert failed == []
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
                  "unauthorized_execution", "control_running:FP-CONTROL-3", "s19_checks"):
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


# --- fail-closed: nothing that cannot be proven is reported as healthy ---------------------------------

def test_real_money_with_nothing_inspected_is_unproven(tmp_path):
    f = health.real_money_state([tmp_path / "absent.json"], [tmp_path / ".env-absent"], {})
    assert f["severity"] == "WARNING" and "UNPROVEN" in f["detail"]


def test_real_money_with_docker_unknown_is_unproven(tmp_path):
    f = health.real_money_state([_cfg(tmp_path)], [], {}, containers_known=False)
    assert f["severity"] == "WARNING" and "docker" in f["detail"]


def test_a_running_paper_container_whose_env_cannot_be_read_is_critical(tmp_path):
    f = health.real_money_state([_cfg(tmp_path)], [], {}, uninspectable=["tlos-h1-paper-cohort-1"])
    assert f["severity"] == "CRITICAL" and "unreadable" in f["detail"]


def test_container_env_inspect_failure_is_reported_not_dropped():
    class R:
        def __init__(self, rc, out=""):
            self.returncode, self.stdout, self.stderr = rc, out, ""

    def docker(cmd):
        if cmd[0] == "ps":
            return R(0, "tradinglab-fp-control-3\trunning\n")
        raise OSError("docker went away")
    envs, failed = health._container_envs(["tradinglab-fp-control-3"], docker)
    assert envs == {} and failed == ["tradinglab-fp-control-3"]


def test_a_s19_run_that_raises_is_critical_not_omitted(tmp_path):
    class R:
        returncode, stdout, stderr = 0, "enabled\n", ""

    def explode(_cfg):
        raise RuntimeError("guard import broke")
    s19 = dict(paper_configs=[_cfg(tmp_path)], env_files=[], ledger=tmp_path / "absent.jsonl", archive_roots=[],
               config_checker=explode, ledger_verifier=kill_switch.verify_ledger, archive_verifier=lambda a: {},
               docker_runner=None)
    real = health.s19_findings
    try:
        health.s19_findings = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
        findings = health.standard_findings({"instances": []}, runner=lambda cmd: R(), verifier=None,
                                            lane=tmp_path, backup_target=tmp_path, fp_lane_root=tmp_path, s19=s19)
    finally:
        health.s19_findings = real
    s19f = [f for f in findings if f["check"] == "s19_checks"]
    assert s19f and s19f[0]["severity"] == "CRITICAL"
    assert health.overall(findings) == "CRITICAL"


def test_the_health_cli_never_drops_the_s19_set_silently():
    src = (REPO_ROOT / "scripts" / "p3" / "health_check.py").read_text(encoding="utf-8")
    # a set that cannot be prepared is CRITICAL; a deliberately disabled set is a WARNING, never absent
    assert '"check": "s19_checks", "severity": health.CRITICAL' in src
    assert '"check": "s19_checks", "severity": health.WARNING' in src


# -- fail-closed: base checks and the run itself (Owner review 2026-10-27) ----------------------------


def test_a_timer_whose_state_systemd_cannot_give_is_unproven_not_healthy():
    def silent(cmd):  # systemctl answered nothing at all
        return subprocess.CompletedProcess(cmd, 1, "", "")
    for want_active in (True, False):
        f = health.timer_expected("tlos-p2-window-fp-control-3.timer", want_active=want_active, runner=silent)
        assert f["severity"] == health.WARNING and "UNPROVEN" in f["detail"]


def test_a_timer_check_whose_runner_raises_is_unproven_not_healthy():
    def broken(cmd):
        raise OSError("no user bus")
    f = health.timer_expected("tlos-p2-window-fp-control-3.timer", want_active=False, runner=broken)
    assert f["severity"] == health.WARNING and "UNPROVEN" in f["detail"]


def test_a_crashed_health_run_is_critical_with_exit_2_and_a_critical_textfile(tmp_path, monkeypatch, capsys):
    import importlib.util
    spec = importlib.util.spec_from_file_location("hc_failclosed", REPO_ROOT / "scripts" / "p3" / "health_check.py")
    hc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hc)

    def boom(argv=None):
        raise RuntimeError("registry unreadable")
    monkeypatch.setattr(hc, "_run", boom)
    prom = tmp_path / "tlos_p3_health.prom"
    assert hc.main(["--prom-textfile", str(prom)]) == 2
    text = prom.read_text(encoding="utf-8")
    assert 'tlos_p3_health_check{check="health_run"} 2' in text
    assert "HEALTH = CRITICAL" in capsys.readouterr().out


# -- residual §19 review (Lane B2, 2026-10-27): monitoring self-failure and startup after reboot ---------


def _answers(mapping):
    def run(cmd):
        key = " ".join(cmd)
        for needle, out in mapping.items():
            if needle in key:
                if isinstance(out, Exception):
                    raise out
                return subprocess.CompletedProcess(cmd, 0, out + "\n", "")
        return subprocess.CompletedProcess(cmd, 0, "\n", "")
    return run


def test_an_unscheduled_health_timer_is_critical_because_the_monitor_is_blind():
    run = _answers({"is-enabled tlos-p3-health.timer": "disabled", "is-active tlos-p3-health.timer": "inactive"})
    f = health.monitor_timer("tlos-p3-health.timer", runner=run)
    assert f["check"] == "timer:tlos-p3-health.timer" and f["severity"] == health.CRITICAL
    ok = _answers({"is-enabled tlos-p3-health.timer": "enabled", "is-active tlos-p3-health.timer": "active"})
    assert health.monitor_timer("tlos-p3-health.timer", runner=ok)["severity"] == health.INFO


def test_a_health_timer_state_systemd_cannot_give_stays_unproven_not_critical_nor_info():
    f = health.monitor_timer("tlos-p3-health.timer", runner=_answers({}))
    assert f["severity"] == health.WARNING and "UNPROVEN" in f["detail"]
    f = health.monitor_timer("tlos-p3-health.timer", runner=_answers({"is-enabled": OSError("no bus")}))
    assert f["severity"] == health.WARNING and "UNPROVEN" in f["detail"]


def test_clock_sync_is_info_only_when_ntp_says_yes():
    assert health.clock_sync(_answers({"NTPSynchronized": "yes"}))["severity"] == health.INFO
    assert health.clock_sync(_answers({"NTPSynchronized": "no"}))["severity"] == health.WARNING
    unknown = health.clock_sync(_answers({}))
    assert unknown["severity"] == health.WARNING and "UNPROVEN" in unknown["detail"]
    raised = health.clock_sync(_answers({"timedatectl": FileNotFoundError("timedatectl")}))
    assert raised["severity"] == health.WARNING and "UNPROVEN" in raised["detail"]


def test_standard_findings_include_the_monitor_self_check_and_clock_sync(tmp_path):
    run = _answers({"is-enabled": "enabled", "is-active": "active", "NTPSynchronized": "yes"})
    checks = {f["check"]: f["severity"] for f in health.standard_findings(
        {"instances": []}, runner=run, verifier=None, lane=tmp_path, backup_target=tmp_path, fp_lane_root=tmp_path)}
    assert checks["timer:tlos-p3-health.timer"] == health.INFO
    assert checks["clock_sync"] == health.INFO


def test_the_promtool_rule_tests_cover_the_monitor_self_check_and_clock_sync():
    text = RULE_TESTS.read_text(encoding="utf-8")
    for label in ("timer:tlos-p3-health.timer", "clock_sync", "health_run"):  # health_run: the crashed-run label
        assert f'check="{label}"' in text and f'check: "{label}"' in text


# -- round 3 (Lane A): unknown states and malformed findings are never INFO ------------------------------


def test_overall_never_reports_info_for_an_unknown_severity_or_an_empty_run():
    assert health.overall([{"check": "x", "severity": "OK", "detail": ""}]) == health.CRITICAL
    assert health.overall([{"check": "x", "severity": "info", "detail": ""},
                           {"check": "y", "severity": health.INFO, "detail": ""}]) == health.CRITICAL
    assert health.overall([{"check": "x", "detail": "no severity"}]) == health.CRITICAL
    assert health.overall([]) == health.WARNING  # nothing was checked: unproven, not healthy
    assert health.overall([{"check": "x", "severity": health.INFO, "detail": ""}]) == health.INFO
    text = health.prometheus_text([{"check": "x", "severity": "OK", "detail": ""}])  # the label still pages
    assert 'tlos_p3_health_check{check="x"} 2' in text and "tlos_p3_health_overall 2" in text


@pytest.mark.parametrize("enabled,active,want", [
    ("disabled", "inactive", health.INFO), ("masked", "inactive", health.INFO), ("absent", "inactive", health.INFO),
    ("not-found", "inactive", health.INFO), ("disabled", "failed", health.INFO),
    ("enabled", "inactive", health.CRITICAL), ("enabled-runtime", "inactive", health.CRITICAL),
    ("disabled", "active", health.CRITICAL), ("disabled", "activating", health.CRITICAL),
    ("disabled", "reloading", health.CRITICAL),
    ("static", "inactive", health.WARNING), ("linked", "inactive", health.WARNING), ("bad", "inactive", health.WARNING),
    ("disabled", "maintenance", health.WARNING),
])
def test_a_retired_timer_is_info_only_in_a_known_off_state(enabled, active, want):
    run = _answers({"is-enabled": enabled, "is-active": active})
    f = health.timer_expected("tlos-p2-window-fp-control-3.timer", want_active=False, runner=run)
    assert f["severity"] == want, (enabled, active, f)
    if want == health.WARNING:
        assert "UNPROVEN" in f["detail"]


def test_a_backup_set_dated_in_the_future_is_unproven_not_fresh(tmp_path):
    s = tmp_path / "b" / "20261025T000000Z"
    s.mkdir(parents=True)
    (s / "BACKUP_RECORD.json").write_text("{}")
    mtime = (s / "BACKUP_RECORD.json").stat().st_mtime
    f = health.backup_recency(tmp_path / "b", 26, now=mtime - 6 * 3600)  # the record is 6 h in the future
    assert f["severity"] == health.WARNING and "UNPROVEN" in f["detail"]
    assert health.backup_recency(tmp_path / "b", 26, now=mtime - 60)["severity"] == health.INFO  # < 5 min skew


def test_a_running_cohort_whose_evidence_cannot_be_located_is_unproven(tmp_path):
    reg = {"instances": [{"role": "FP-CONTROL-9", "status": "RUNNING", "runtime_identity": {"evidence_dir": "/elsewhere/x"}}]}
    f = health.normal_end_due(reg, tmp_path)[0]
    assert f["severity"] == health.WARNING and "UNPROVEN" in f["detail"]
    reg["instances"][0]["runtime_identity"] = {}
    assert health.normal_end_due(reg, tmp_path)[0]["severity"] == health.WARNING
    reg["instances"][0]["runtime_identity"] = {"evidence_dir": "/freqtrade/user_data/lanes/x"}
    f = health.normal_end_due(reg, tmp_path)[0]  # the lane directory itself is absent (wrong root, unmounted)
    assert f["severity"] == health.WARNING and "UNPROVEN" in f["detail"]
    (tmp_path / "lanes" / "x").mkdir(parents=True)  # present, no ledger yet: no lifecycle completed
    assert health.normal_end_due(reg, tmp_path)[0]["severity"] == health.INFO


@pytest.mark.parametrize("state", ["restarting", "paused", "removing", "weird"])
def test_a_paper_container_that_is_not_cleanly_stopped_counts_as_executing(state):
    f = health.paper_runtime_vs_registry({"instances": []}, {"tradinglab-fp-control-3-x": state})
    assert f[0]["check"] == "unauthorized_execution" and f[0]["severity"] == health.CRITICAL, state
    for stopped in ("exited", "created", "dead"):
        f = health.paper_runtime_vs_registry({"instances": []}, {"tradinglab-fp-control-3-x": stopped})
        assert f[0]["severity"] == health.INFO, stopped


def test_a_restarting_paper_container_has_its_env_inspected_for_live_switches(tmp_path):
    calls = []

    def docker(cmd):
        calls.append(cmd)
        if cmd[0] == "ps":
            return subprocess.CompletedProcess(cmd, 0, "tradinglab-fp-control-3-x\trestarting\n", "")
        return subprocess.CompletedProcess(cmd, 0, "FREQTRADE__DRY_RUN=false\n", "")
    out = health.s19_findings({"instances": []}, paper_configs=[_cfg(tmp_path)], env_files=[], ledger=tmp_path / "l",
                              archive_roots=[], config_checker=lambda c: [], ledger_verifier=lambda p: [],
                              archive_verifier=lambda a: {}, docker_runner=docker)
    rm = next(f for f in out if f["check"] == "real_money")
    assert rm["severity"] == health.CRITICAL and "FREQTRADE__DRY_RUN" in rm["detail"]
    assert any(c[0] == "inspect" for c in calls)


def test_a_textfile_that_cannot_be_written_is_critical_and_leaves_the_old_file_to_go_stale(tmp_path, monkeypatch, capsys):
    import importlib.util
    spec = importlib.util.spec_from_file_location("hc_textfile", REPO_ROOT / "scripts" / "p3" / "health_check.py")
    hc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hc)
    prom = tmp_path / "tlos_p3_health.prom"
    prom.write_text("tlos_p3_health_overall 0\n", encoding="utf-8")
    old = prom.stat().st_mtime_ns
    monkeypatch.setattr(hc.health, "standard_findings",
                        lambda *a, **k: [{"check": "clock_sync", "severity": health.INFO, "detail": "ok"}])
    monkeypatch.setattr(hc.health, "default_s19_inputs", lambda root: {})

    def disk_full(findings, path):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(hc.health, "write_textfile", disk_full)
    assert hc.main(["--prom-textfile", str(prom)]) == 2
    out = capsys.readouterr().out
    assert "health_run" in out and "HEALTH = CRITICAL" in out
    # the previous file is untouched: its mtime stops advancing and TLOSHealthTextfileStale takes over
    assert prom.stat().st_mtime_ns == old and prom.read_text(encoding="utf-8") == "tlos_p3_health_overall 0\n"
