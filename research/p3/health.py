"""P3-PLN-06 operational health check: capacity, recovery point, timers, runtimes, normal end.

P3_CONTRACT.md §3 PLN-06. It reuses the master plan's §19 severity model (INFO / WARNING /
CRITICAL) and checks the conditions P2 showed matter:
- free space on the root and the lane filesystems (the proposed Owner condition is at least 20 GiB);
- the age of the newest verified backup set against the recovery-point objective (RPO);
- the backup timer installed and active;
- the retired P2 restart timer still disabled (F-5);
- the backup store mounted, and on the configured filesystem UUID when one is set (p3.storage: the
  location is configured once; an unusable configuration is CRITICAL, never a silent default);
- a cohort whose trade ledger already shows a completed lifecycle while its registry row still says
  RUNNING, which means the normal end was reached and a governed stop is due (F-3);
- the master plan §19 CRITICAL conditions that a read-only host check can observe: a paper-guard
  failure on any present paper config, a real-money-enabled state (dry_run not true, exchange
  credentials present in a config, an env file or a running paper container), a broken evidence chain
  (the hash-chained operator ledger and every sealed archive rehashed against its manifest), and a paper
  runtime that disagrees with the registry (a running paper container with no RUNNING cohort is
  unauthorized execution; a RUNNING cohort with no running container is a stopped control).
  Secret values are never read into a finding; only key names are reported.

Read-only. It changes nothing; an operator acts on its findings. Exit codes are 0 (all INFO),
1 (any WARNING) and 2 (any CRITICAL).

PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Callable

INFO, WARNING, CRITICAL = "INFO", "WARNING", "CRITICAL"
GIB = 1024 ** 3


def _finding(check: str, severity: str, detail: str) -> dict:
    return {"check": check, "severity": severity, "detail": detail}


def free_space(path: Path, minimum_gib: float, label: str) -> dict:
    probe = Path(path)
    while not probe.exists():
        probe = probe.parent
    free = shutil.disk_usage(probe).free
    sev = INFO if free >= minimum_gib * GIB else CRITICAL
    return _finding(f"free_space:{label}", sev, f"{free / GIB:.1f} GiB free at {probe} (minimum {minimum_gib} GiB)")


def backup_recency(target: Path, rpo_hours: float, verifier: Callable[[Path], dict] | None = None,
                   now: float | None = None) -> dict:
    sets = sorted(p for p in Path(target).glob("*") if p.is_dir() and not p.name.startswith(".")
                  and (p / "BACKUP_RECORD.json").is_file()) if Path(target).is_dir() else []
    if not sets:
        return _finding("backup_recency", CRITICAL, f"no backup set under {target}")
    newest = sets[-1]
    age_h = ((now or time.time()) - (newest / "BACKUP_RECORD.json").stat().st_mtime) / 3600
    if verifier is not None and verifier(newest).get("status") != "PASS":
        return _finding("backup_recency", CRITICAL, f"newest set {newest.name} does not verify")
    sev = INFO if age_h <= rpo_hours else WARNING
    return _finding("backup_recency", sev, f"newest set {newest.name}, {age_h:.1f} h old (RPO {rpo_hours} h)")


def _unit_state(unit: str, runner) -> tuple[str, str]:
    enabled = runner(["systemctl", "--user", "is-enabled", unit]).stdout.strip() or "absent"
    active = runner(["systemctl", "--user", "is-active", unit]).stdout.strip() or "unknown"
    return enabled, active


def timer_expected(unit: str, *, want_active: bool, runner) -> dict:
    """A timer judged against its expected state. Fail-closed: if systemd cannot be asked, or answers
    nothing for is-active (which always prints a state, including 'inactive' for an absent unit), the
    state is UNPROVEN (WARNING), never INFO."""
    want = "enabled+active" if want_active else "disabled+inactive"
    try:
        enabled, active = _unit_state(unit, runner)
    except Exception as exc:  # noqa: BLE001 - a state that cannot be read is not a healthy state
        return _finding(f"timer:{unit}", WARNING, f"UNPROVEN: systemctl could not be queried "
                                                  f"({type(exc).__name__}); expected {want}")
    if active == "unknown":
        return _finding(f"timer:{unit}", WARNING, f"UNPROVEN: systemctl gave no state ({enabled}/?); expected {want}")
    ok = (enabled == "enabled" and active == "active") if want_active else (enabled != "enabled" and active != "active")
    sev = INFO if ok else (WARNING if want_active else CRITICAL)
    return _finding(f"timer:{unit}", sev, f"{enabled}/{active} (expected {want})")


def monitor_timer(unit: str, *, runner) -> dict:
    """Monitoring self-failure: the hourly health timer itself. If it is not scheduled the hourly monitor is
    blind, so 'not active' is CRITICAL here (not the WARNING an ordinary expected-active timer gets).
    A state systemd cannot give stays WARNING "UNPROVEN" (fail-closed, never INFO)."""
    f = timer_expected(unit, want_active=True, runner=runner)
    if f["severity"] == WARNING and "UNPROVEN" not in f["detail"]:
        return _finding(f["check"], CRITICAL, f"{f['detail']}; the hourly health monitor itself is not scheduled")
    return f


def clock_sync(runner) -> dict:
    """Startup after reboot / evidence timestamps: the host clock must be NTP-synchronised. Bar timing,
    admission and reconciliation all compare timestamps. Unknown is UNPROVEN (WARNING), never INFO."""
    try:
        out = runner(["timedatectl", "show", "-p", "NTPSynchronized", "--value"]).stdout.strip().lower()
    except Exception as exc:  # noqa: BLE001 - a clock state that cannot be read is not a healthy one
        return _finding("clock_sync", WARNING, f"UNPROVEN: timedatectl could not be queried ({type(exc).__name__})")
    if out == "yes":
        return _finding("clock_sync", INFO, "NTP synchronised")
    if out == "no":
        return _finding("clock_sync", WARNING, "NTP NOT synchronised: evidence timestamps may drift")
    return _finding("clock_sync", WARNING, f"UNPROVEN: timedatectl gave no NTP state ({out[:40]!r})")


def storage_findings(runner, store=None) -> list[dict]:
    """The backup-store checks alone (see ``_store_checks``)."""
    return _store_checks(runner, store)[1]


def _store_checks(runner, store=None):
    """The backup store: its resolved location, mounted, and (if configured) the expected filesystem UUID.

    ``store`` is a ``p3.storage.Storage``; None resolves it. An unusable configuration is CRITICAL with no
    fallback (the health check must never judge a default store the backups are not written to). A
    configured UUID that cannot be read is UNPROVEN (WARNING); a different UUID is CRITICAL.
    Returns ``(store or None, findings)``."""
    from p3 import storage as _storage
    if store is None:
        try:
            store = _storage.load()
        except _storage.StorageConfigError as exc:
            return None, [_finding("backup_storage", CRITICAL, f"storage configuration unusable: {str(exc)[:160]}")]
    out = [_finding("backup_storage", INFO, f"{store.backup_target} on {store.backup_mount} (source: {store.source})"),
           mounted(store.backup_mount)]
    if not store.mount_uuid and out[-1]["severity"] == INFO:
        out.append(_finding(f"mount_uuid:{store.backup_mount}", CRITICAL,
                            "UNPROVEN: no mount_uuid configured; any filesystem mounted here would be accepted"))
    if store.mount_uuid and out[-1]["severity"] == INFO:
        check = f"mount_uuid:{store.backup_mount}"
        try:
            got = runner(["findmnt", "-no", "UUID", "--mountpoint", store.backup_mount]).stdout.strip()
        except Exception as exc:  # noqa: BLE001 - an identity that cannot be read is not a proven identity
            out.append(_finding(check, CRITICAL, f"UNPROVEN: findmnt could not be queried ({type(exc).__name__})"))
            got = None
        if got is None:
            pass
        elif not got:
            out.append(_finding(check, CRITICAL, "UNPROVEN: findmnt gave no UUID"))
        elif got.lower() != store.mount_uuid.lower():
            out.append(_finding(check, CRITICAL, f"UUID {got} is not the configured {store.mount_uuid}: "
                                                 f"another filesystem is mounted there"))
        else:
            out.append(_finding(check, INFO, f"UUID {got}"))
    if out[1]["severity"] == INFO and not any(f["severity"] == CRITICAL for f in out):
        try:
            problems = _storage.device_problems(store) + _storage.target_problems(store)
        except OSError as exc:
            problems = [f"target cannot be resolved ({type(exc).__name__})"]
        out.append(_finding("backup_target_on_store", CRITICAL if problems else INFO,
                            "; ".join(problems)[:200] if problems else "target resolves inside the store's filesystem"))
        try:
            perms = _storage.permission_problems(store)
        except OSError as exc:
            perms = [f"permissions cannot be read ({type(exc).__name__})"]
        if perms:
            out.append(_finding("backup_store_permissions", WARNING, "; ".join(perms)[:200]))
    return store, out


def mounted(path: str) -> dict:
    return _finding(f"mount:{path}", INFO if os.path.ismount(path) else CRITICAL,
                    "mounted" if os.path.ismount(path) else "not mounted")


def normal_end_due(registry: dict, lane_root: Path) -> list[dict]:
    findings = []
    for row in registry.get("instances", []):
        if row.get("status") != "RUNNING":
            continue
        evidence = row.get("runtime_identity", {}).get("evidence_dir", "")
        ledger = Path(lane_root) / Path(evidence).relative_to("/freqtrade/user_data") / "paper_trade_ledger.jsonl" \
            if evidence.startswith("/freqtrade/user_data") else None
        closed = 0
        if ledger and ledger.is_file():
            closed = sum(1 for line in ledger.read_text(encoding="utf-8").splitlines()
                         if line.strip() and json.loads(line).get("payload", {}).get("event") == "position_closed")
        sev = WARNING if closed else INFO
        detail = (f"{row['role']} is RUNNING with {closed} closed lifecycle(s): NORMAL END reached, governed stop due"
                  if closed else f"{row['role']} RUNNING, no completed lifecycle yet")
        findings.append(_finding(f"normal_end:{row['role']}", sev, detail))
    if not findings:
        findings.append(_finding("normal_end", INFO, "no RUNNING cohort"))
    return findings


def overall(findings: list[dict]) -> str:
    sevs = {f["severity"] for f in findings}
    return CRITICAL if CRITICAL in sevs else WARNING if WARNING in sevs else INFO


def standard_findings(registry: dict, *, runner, verifier: Callable[[Path], dict] | None,
                      root_min_gib: float = 20.0, lane: Path = Path("/home/hamza/tlos-paper/h1-paper-cohort-1"),
                      lane_min_gib: float = 20.0, backup_target: Path | None = None,
                      rpo_hours: float = 26.0,
                      fp_lane_root: Path = Path("/home/hamza/projects/trading/trading_lab_os_final/freqtrade/user_data"),
                      s19: dict | None = None,
                      ) -> list[dict]:
    """The host's standard check set, shared by the health CLI and the Control Room projection.

    ``s19`` carries the inputs of the §19 CRITICAL checks (see ``s19_findings``); None omits them, which
    keeps callers that only want the capacity/recovery set (and older tests) unchanged.

    ``backup_target`` None means the configured store (``p3.storage``); an explicit path overrides only
    where recency is read, and the store checks still follow the configuration."""
    store, store_findings = _store_checks(runner)
    store_proven = store is not None and not any(f["severity"] == CRITICAL for f in store_findings)
    if backup_target is None:
        # Recency is only measured on a proven store: sets "found" on a wrong or unproven store prove nothing.
        backup_target = store.target if store_proven else None
    findings = [
        free_space(Path("/"), root_min_gib, "root"),
        free_space(lane, lane_min_gib, "h1_lane"),
        *store_findings,
        *([backup_recency(backup_target, rpo_hours, verifier=verifier)] if backup_target is not None else
          [_finding("backup_recency", CRITICAL, "backup store unconfigured or unproven: recency not measured")]),
        timer_expected("tlos-p3-backup.timer", want_active=True, runner=runner),
        timer_expected("tlos-p2-window-fp-control-3.timer", want_active=False, runner=runner),
        monitor_timer("tlos-p3-health.timer", runner=runner),
        clock_sync(runner),
        *normal_end_due(registry, fp_lane_root),
    ]
    if s19 is not None:
        try:
            findings += s19_findings(registry, **s19)
        except Exception as exc:  # noqa: BLE001 - checks that cannot run are a failure, not an absence
            findings.append(_finding("s19_checks", CRITICAL, f"§19 checks could not run ({type(exc).__name__}: "
                                                             f"{str(exc)[:120]})"))
    return findings


def default_runner(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60)


SEVERITY_VALUE = {INFO: 0, WARNING: 1, CRITICAL: 2}


def prometheus_text(findings: list[dict]) -> str:
    """Prometheus text exposition: one gauge per check (0 INFO, 1 WARNING, 2 CRITICAL) and the overall.

    Written as a node-exporter textfile (or scraped through any file-based collector), so alert
    delivery reuses the existing Prometheus/Grafana stack (§10) without touching the FP exporter.
    """
    lines = ["# HELP tlos_p3_health_check Trading Lab OS P3 health check severity (0 INFO, 1 WARNING, 2 CRITICAL)",
             "# TYPE tlos_p3_health_check gauge"]
    for f in findings:
        check = f["check"].replace("\\", "\\\\").replace('"', "'")
        lines.append(f'tlos_p3_health_check{{check="{check}"}} {SEVERITY_VALUE[f["severity"]]}')
    lines += ["# HELP tlos_p3_health_overall Worst severity across all checks",
              "# TYPE tlos_p3_health_overall gauge", f"tlos_p3_health_overall {SEVERITY_VALUE[overall(findings)]}"]
    return "\n".join(lines) + "\n"


def write_textfile(findings: list[dict], path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(prometheus_text(findings), encoding="utf-8")
    os.replace(tmp, path)  # atomic: a scraper never reads a half-written file


# --- master plan §19 CRITICAL conditions (PLN-06) ----------------------------------------------------

TRADING_ROOT = Path("/home/hamza/projects/trading")
RUNTIME_ROOT = TRADING_ROOT / "trading_lab_os_final"
OPERATOR_LEDGER = Path("/home/hamza/tlos-paper/operator-ledger/operator_ledger.jsonl")
H1_LANE = Path("/home/hamza/tlos-paper/h1-paper-cohort-1")
# Env names that would switch a Freqtrade process away from paper or hand it exchange credentials.
_LIVE_ENV_RE = re.compile(r"^FREQTRADE__(DRY_RUN|EXCHANGE__(KEY|SECRET|PASSWORD|UID|APIKEY|PRIVATEKEY))$", re.IGNORECASE)
_EXCHANGE_CREDENTIAL_KEYS = ("key", "secret", "password", "uid", "apiKey", "privateKey", "walletAddress")


def _short(items: list[str], n: int = 3) -> str:
    return "; ".join(items[:n]) + (f" (+{len(items) - n} more)" if len(items) > n else "")


def paper_guard_configs(configs: list[Path], checker: Callable[[Path], list[str]]) -> dict:
    """§19 'paper guard failure': run the repository paper guard on every present paper config."""
    present = [Path(c) for c in configs if Path(c).is_file()]
    if not present:
        return _finding("paper_guard", WARNING,
                        "UNPROVEN: no paper config found at the expected paths, so the guard could not run")
    problems = []
    for cfg in present:
        try:
            problems += [f"{cfg.name}: {v.split(': ', 1)[-1]}" for v in checker(cfg)]
        except Exception as exc:  # noqa: BLE001 - a guard that cannot run is a guard that failed
            problems.append(f"{cfg.name}: guard could not run ({type(exc).__name__})")
    if problems:
        return _finding("paper_guard", CRITICAL, f"{len(problems)} violation(s): {_short(problems)}")
    return _finding("paper_guard", INFO, f"{len(present)} config(s) pass the paper guard")


def _env_names(text: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.removeprefix("export ").partition("=")
        out[name.strip()] = value.strip().strip('"').strip("'")
    return out


def _live_env_problems(env: dict[str, str], source: str) -> list[str]:
    problems = []
    for name, value in env.items():
        if not _LIVE_ENV_RE.match(name):
            continue
        if name.upper() == "FREQTRADE__DRY_RUN":
            if value.lower() != "true":
                problems.append(f"{source}: {name} is not 'true'")
        elif value:
            problems.append(f"{source}: {name} is set")  # the value itself is never reported
    return problems


def real_money_state(configs: list[Path], env_files: list[Path], container_envs: dict[str, dict[str, str]],
                     *, containers_known: bool = True, uninspectable: list[str] | None = None) -> dict:
    """§19 'real-money enabled': any paper config, env file or running paper container that is not paper.

    Fail-closed: a running paper container whose environment cannot be read is a problem, and a run that
    could inspect neither a config nor an env file, or could not ask docker, is UNPROVEN (WARNING), never
    INFO."""
    problems = [f"container {n}: environment unreadable, cannot prove no live switch" for n in (uninspectable or [])]
    checked = 0
    for cfg in (Path(c) for c in configs):
        if not cfg.is_file():
            continue
        checked += 1
        try:
            data = json.loads(cfg.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            problems.append(f"{cfg.name}: unreadable, cannot prove dry_run")
            continue
        if data.get("dry_run") is not True:
            problems.append(f"{cfg.name}: dry_run is not true")
        exchange = data.get("exchange") if isinstance(data.get("exchange"), dict) else {}
        blocks = [exchange] + [exchange.get(k) for k in ("ccxt_config", "ccxt_async_config", "ccxt_sync_config")
                               if isinstance(exchange.get(k), dict)]
        for block in blocks:
            for key in _EXCHANGE_CREDENTIAL_KEYS:
                if block.get(key):
                    problems.append(f"{cfg.name}: exchange credential {key!r} is set")
    for env_file in (Path(e) for e in env_files):
        if env_file.is_file():
            checked += 1
            try:
                problems += _live_env_problems(_env_names(env_file.read_text(encoding="utf-8")), env_file.name)
            except Exception:  # noqa: BLE001
                problems.append(f"{env_file.name}: unreadable, cannot prove no live switch")
    for name, env in container_envs.items():
        problems += _live_env_problems(env, f"container {name}")
    if problems:
        return _finding("real_money", CRITICAL, f"REAL-MONEY STATE: {_short(problems)}")
    if not checked:
        return _finding("real_money", WARNING, "UNPROVEN: no paper config or env file found to inspect")
    if not containers_known:
        return _finding("real_money", WARNING,
                        f"UNPROVEN: {checked} file(s) clean, but docker could not be queried for container env")
    return _finding("real_money", INFO, f"no live switch or exchange credential found in {checked} file(s) "
                                        f"and {len(container_envs)} running paper container(s)")


def operator_ledger_chain(path: Path, verifier: Callable[[Path], list[str]]) -> dict:
    """§19 'evidence chain broken' for the hash-chained operator ledger (PLN-08 / O-1)."""
    if not Path(path).is_file():
        return _finding("evidence_chain:operator_ledger", WARNING, f"operator ledger absent at {path}")
    try:
        problems = verifier(Path(path))
    except Exception as exc:  # noqa: BLE001
        problems = [f"verify could not run ({type(exc).__name__})"]
    if problems:
        return _finding("evidence_chain:operator_ledger", CRITICAL, f"chain BROKEN: {_short(problems)}")
    lines = sum(1 for x in Path(path).read_text(encoding="utf-8").splitlines() if x.strip())
    return _finding("evidence_chain:operator_ledger", INFO, f"{lines} record(s), chain intact")


def sealed_archives(roots: list[Path], verifier: Callable[[Path], object]) -> dict:
    """§19 'evidence chain broken' / 'DB corruption' for sealed evidence: every sealed archive under
    <checkout>/artifacts rehashes against its own manifest (the sealed tradesv3.sqlite included)."""
    archives = sorted(a for root in roots if (Path(root) / "artifacts").is_dir()
                      for a in (Path(root) / "artifacts").iterdir() if (a / "archive_manifest.json").is_file())
    if not archives:
        return _finding("evidence_chain:sealed_archives", WARNING, "no sealed archive found under the checkouts")
    failed = []
    for archive in archives:
        try:
            verifier(archive)
        except Exception as exc:  # noqa: BLE001
            failed.append(f"{archive.parent.parent.name}/{archive.name}: {str(exc)[:120]}")
    if failed:
        return _finding("evidence_chain:sealed_archives", CRITICAL, f"{len(failed)} archive(s) BROKEN: {_short(failed, 2)}")
    return _finding("evidence_chain:sealed_archives", INFO, f"{len(archives)} sealed archive(s) ARCHIVE_VERIFIED")


def paper_runtime_vs_registry(registry: dict, containers: dict[str, str] | None) -> list[dict]:
    """§19 'unauthorized execution' and 'FP-CONTROL stopped': the paper containers that run against the
    registry's RUNNING cohorts. ``containers`` is {name: state} of paper-runtime containers, or None when
    docker could not be asked (then the condition is unproven, not healthy)."""
    if containers is None:
        return [_finding("paper_runtime", WARNING, "docker could not be queried; paper runtime state UNKNOWN")]
    running_roles = {row.get("role") for row in registry.get("instances", []) if row.get("status") == "RUNNING"}
    running = sorted(n for n, s in containers.items() if s == "running")
    findings = []
    unauthorized = [n for n in running if not any(r and r.lower() in n.lower() for r in running_roles)]
    if unauthorized:
        findings.append(_finding("unauthorized_execution", CRITICAL,
                                 f"paper runtime running with no RUNNING registry cohort: {_short(unauthorized)}"))
    else:
        findings.append(_finding("unauthorized_execution", INFO,
                                 f"{len(running)} paper runtime(s) running, all backed by a RUNNING cohort"))
    for role in sorted(r for r in running_roles if r):
        up = any(role.lower() in n.lower() for n in running)
        findings.append(_finding(f"control_running:{role}", INFO if up else CRITICAL,
                                 f"{role} is RUNNING in the registry and its container is "
                                 f"{'running' if up else 'NOT running (control stopped)'}"))
    return findings


def _default_container_lister(runner) -> dict[str, str] | None:
    from p3 import kill_switch  # noqa: PLC0415 - optional dependency, host only
    try:
        return kill_switch.paper_containers(runner)
    except Exception:  # noqa: BLE001
        return None


def _container_envs(names: list[str], runner) -> tuple[dict[str, dict[str, str]], list[str]]:
    """({name: env}, [names whose env could not be read]). An unreadable env is never treated as clean."""
    envs, failed = {}, []
    for name in names:
        try:
            res = runner(["inspect", "--format", "{{range .Config.Env}}{{println .}}{{end}}", name])
        except Exception:  # noqa: BLE001
            res = None
        if res is not None and getattr(res, "returncode", 1) == 0:
            envs[name] = _env_names(res.stdout)
        else:
            failed.append(name)
    return envs, failed


def s19_findings(registry: dict, *, paper_configs: list[Path], env_files: list[Path], ledger: Path,
                 archive_roots: list[Path], config_checker, ledger_verifier, archive_verifier,
                 docker_runner) -> list[dict]:
    """The §19 CRITICAL checks, every dependency injected (tests pass fakes; the host passes defaults)."""
    containers = _default_container_lister(docker_runner) if docker_runner is not None else None
    running = [n for n, s in (containers or {}).items() if s == "running"]
    envs, uninspectable = _container_envs(running, docker_runner) if docker_runner else ({}, [])
    return [
        paper_guard_configs(paper_configs, config_checker),
        real_money_state(paper_configs, env_files, envs, containers_known=containers is not None,
                         uninspectable=uninspectable),
        operator_ledger_chain(ledger, ledger_verifier),
        sealed_archives(archive_roots, archive_verifier),
        *paper_runtime_vs_registry(registry, containers),
    ]


def default_s19_inputs(repo_root: Path) -> dict:
    """Host defaults for s19_findings, importing the repository's own guard and verifiers."""
    import sys  # noqa: PLC0415
    for extra in (str(Path(repo_root) / "scripts"), str(Path(repo_root) / "research")):
        if extra not in sys.path:
            sys.path.insert(0, extra)
    import paper_guard  # noqa: PLC0415
    import publish_evidence_digest  # noqa: PLC0415
    from p3 import kill_switch  # noqa: PLC0415

    def check(cfg: Path) -> list[str]:
        violations = paper_guard.Violations()
        paper_guard.check_config(Path(cfg), violations)
        return list(violations)

    lane_configs = sorted(H1_LANE.glob("**/config*.json")) if H1_LANE.is_dir() else []
    return {
        "paper_configs": [RUNTIME_ROOT / "freqtrade" / "user_data" / "config.json",
                          Path(repo_root) / "research" / "paper" / "h1" / "package" / "config.h1-paper.json",
                          *lane_configs],
        "env_files": [RUNTIME_ROOT / ".env"],
        "ledger": OPERATOR_LEDGER,
        "archive_roots": sorted(p for p in TRADING_ROOT.iterdir() if p.is_dir()) if TRADING_ROOT.is_dir() else [],
        "config_checker": check,
        "ledger_verifier": kill_switch.verify_ledger,
        "archive_verifier": publish_evidence_digest.verify_archive,
        "docker_runner": lambda cmd: subprocess.run(["docker", *cmd], capture_output=True, text=True, timeout=120),
    }
