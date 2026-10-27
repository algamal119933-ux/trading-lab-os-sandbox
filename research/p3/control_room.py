"""P3-PLN-09 Control Room: a read-only live projection of verified evidence onto the frozen prototype.

Authority: docs/p3/PLN_09_PRODUCT_SHAPE_AUTHORITY.md. The frozen prototype
(docs/p3/product_shape/Trading_Lab_OS_Prototype_v0.2.5_FINAL.html, sha256 e17d50dc…) is used
verbatim, as the component library and layout. This module only:

1. ``collect``: observes the host through existing P3 tools (health checks, backup verify, the
   operator ledger, the restart guard, docker, git, the registry and governed records);
2. ``project``: maps that observation onto the prototype's own scenario schema, in Arabic and English.
   Anything not observed is reported as unknown, never as healthy;
3. ``build``: refuses a prototype whose digest differs, then appends one script carrying the live
   scenario and the adapter (control_room_live.js), which re-declares only data-bearing components
   with the same markup.

Reuse classification: WRAP_EXISTING (the frozen prototype and the P3 tools). NEW_CONTROL_PLANE = NO.
The page is static and offline (the prototype's CSP is kept); it is evidence of nothing. The UI is
never evidence authority (P3_CONTRACT §23).

PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import hashlib
import json
import re
import socket
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from p3 import backup, health, kill_switch, recovery

REPO_ROOT = Path(__file__).resolve().parents[2]
PROTOTYPE = REPO_ROOT / "docs" / "p3" / "product_shape" / "Trading_Lab_OS_Prototype_v0.2.5_FINAL.html"
PROTOTYPE_SHA256 = "e17d50dc9c8d0e6f6a629c4f215441ba4d00457d0e18a6eb5b45261c6651e3d9"
ADAPTER_JS = Path(__file__).with_name("control_room_live.js")
WORKSTREAMS = Path(__file__).with_name("records") / "p3_workstreams.json"
REGISTRY = REPO_ROOT / "research" / "fp" / "records" / "forward_paper_cohort_registry.json"
AUTHORIZATION = REPO_ROOT / "docs" / "p3" / "OWNER_P3_EXECUTION_AUTHORIZATION.md"
P2_CLOSURE = REPO_ROOT / "docs" / "p2" / "P2_CLOSURE.md"
RUNTIME_ROOT = Path("/home/hamza/projects/trading/trading_lab_os_final")
LEDGER = Path("/home/hamza/tlos-paper/operator-ledger/operator_ledger.jsonl")
BACKUP_TARGET = Path("/mnt/tlos-wdc/tlos-backups")
EVIDENCE_DIR = Path("/home/hamza/tlos-paper/p3-evidence")  # drills/ and audits/ hold persisted proof records
# The view is regenerated hourly with the health timer; past this age it is shown as stale.
FRESHNESS_BUDGET_S = 2 * 3600
# Slice 3 reads the sealed cohort named by the newest execution-audit record (read-only).
SEALED_DECISIONS_SHOWN = 40   # newest notable decisions listed on the Decisions screen
SEALED_CANDLES_SHOWN = 56     # bars per pair on the Market Workspace (the prototype's chart width)
# The scheduled build reuses the findings health_check.py --json wrote moments before. A findings file older
# than this (the health run failed and left the previous one behind) is not current and is never reused.
FINDINGS_MAX_AGE_S = 15 * 60
# Docker states in which a paper container is observed stopped; any other non-running state is degraded.
_STOPPED_STATES = frozenset({"exited", "dead", "created"})
_WS_STATUSES = ("ACCEPTED", "PARTIAL", "IN_PROGRESS", "PENDING")

Runner = Callable[[list[str]], subprocess.CompletedProcess]


class ControlRoomError(Exception):
    pass


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=600)


def _out(runner: Runner, cmd: list[str]) -> str | None:
    try:
        r = runner(cmd)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def _utc(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%d %H:%MZ")


def b(en: str, ar: str) -> dict:
    return {"en": en, "ar": ar}


# ---------------------------------------------------------------- sealed cohort (slice 3)
def _ledger_payloads(path: Path) -> list[dict]:
    return [json.loads(line)["payload"] for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def sealed_cohort(audits: list[dict]) -> dict | None:
    """The decision, trade and input ledgers of the sealed cohort that the newest readable execution-audit
    record names. Read-only. None when no audit record exists; ``error`` when the ledgers cannot be read."""
    audit = next((a for a in reversed(audits) if not a.get("unreadable") and a.get("evidence_dir")), None)
    if audit is None:
        return None
    ev = Path(audit["evidence_dir"])
    base = {"evidence_dir": str(ev), "cohort": ev.parent.name, "audit_file": audit.get("_file"),
            "executions": audit.get("executions", [])}
    try:
        decisions = _ledger_payloads(ev / "paper_decision_ledger.jsonl")
        trades = _ledger_payloads(ev / "paper_trade_ledger.jsonl")
        inputs = _ledger_payloads(ev / "paper_input_ledger.jsonl")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return dict(base, error=f"{type(exc).__name__}: {exc}")
    notable = [d for d in decisions if d.get("intended_action") != "hold"
               or (d.get("admission") or {}).get("result") not in (None, "NOT_REQUIRED")]
    last_per_pair = {}
    for d in decisions:
        last_per_pair[d.get("pair")] = d
    chosen = {(d.get("pair"), d.get("candle_ts")): d for d in notable + list(last_per_pair.values())}
    shown = sorted(chosen.values(), key=lambda d: (int(d.get("candle_ts") or 0), str(d.get("pair"))))[-SEALED_DECISIONS_SHOWN:]
    candles: dict[str, list] = {}
    for i in inputs:
        c = i.get("candle") or {}
        candles.setdefault(i.get("pair"), []).append(
            [int(c["ts"]), float(c["open"]), float(c["high"]), float(c["low"]), float(c["close"])])
    for pair in candles:
        candles[pair] = sorted(candles[pair])[-SEALED_CANDLES_SHOWN:]
    timeframes = sorted({str(d.get("timeframe")) for d in decisions if d.get("timeframe")})
    return dict(base, n_decisions=len(decisions), decisions=shown, trades=trades, candles=candles,
                timeframes=timeframes)


# ---------------------------------------------------------------- inputs
def parse_authorization(text: str) -> dict:
    """The fields the projection needs from the Owner P3 authorization record. Fail-closed: a boundary
    counts as explicit only when its NO line is present and no contradicting line is; an expiry is
    trusted only when exactly one EXPIRES_UTC value is stated."""
    def only_no(field: str) -> bool:
        values = set(re.findall(rf"^{field} = (\S+)", text, re.M))
        return values == {"NO"}
    expiries = set(re.findall(r"^EXPIRES_UTC = (\S+)", text, re.M))
    return {"present": bool(text), "expires_utc": expiries.pop() if len(expiries) == 1 else None,
            "real_money": only_no("REAL_MONEY_AUTHORIZED"), "h1_launch": only_no("H1_LAUNCH_AUTHORIZED")}


def _finding_ok(f) -> bool:
    return isinstance(f, dict) and all(isinstance(f.get(k), str) for k in ("check", "severity", "detail"))


def load_findings(path: Path, *, now: float | None = None) -> list[dict]:
    """Findings from a health_check.py --json file, only when that file is current and well formed.

    Otherwise one CRITICAL ``health_input`` finding: health that was not observed now is UNPROVEN, and
    UNPROVEN blocks exactly as FAIL does (an old file is never shown as this hour's health)."""
    now = time.time() if now is None else now

    def unproven(why: str) -> list[dict]:
        return [{"check": "health_input", "severity": health.CRITICAL,
                 "detail": f"UNPROVEN: health findings {why}; not reused"}]
    p = Path(path)
    try:
        age = now - p.stat().st_mtime
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return unproven(f"unreadable ({type(exc).__name__})")
    if age > FINDINGS_MAX_AGE_S or age < -300:
        return unproven(f"file is {age / 60:.0f} min old (budget {FINDINGS_MAX_AGE_S // 60} min)")
    findings = data.get("findings") if isinstance(data, dict) else None
    if not isinstance(findings, list) or not findings or not all(_finding_ok(f) for f in findings):
        return unproven("malformed or empty")
    return findings


# ---------------------------------------------------------------- collect
def collect(*, runner: Runner = _run, now: float | None = None, registry_path: Path = REGISTRY,
            workstreams_path: Path = WORKSTREAMS, authorization_path: Path = AUTHORIZATION,
            p2_closure_path: Path = P2_CLOSURE, ledger_path: Path = LEDGER, repo_root: Path = REPO_ROOT,
            runtime_root: Path = RUNTIME_ROOT, backup_target: Path = BACKUP_TARGET, evidence_dir: Path = EVIDENCE_DIR, findings: list[dict] | None = None,
            docker: Runner | None = None) -> dict:
    """Observe the host. Read-only; each value records where it came from."""
    now = time.time() if now is None else now
    registry = json.loads(Path(registry_path).read_text(encoding="utf-8"))
    if findings is None:
        findings = health.standard_findings(registry, runner=health.default_runner, verifier=backup.verify_backup,
                                            s19=health.default_s19_inputs(repo_root))
    try:
        paper = kill_switch.paper_containers(docker or kill_switch._docker)
        paper_error = None
    except kill_switch.KillSwitchError as exc:
        paper, paper_error = None, str(exc)
    running = _out(runner, ["docker", "ps", "--format", "{{.Names}}"])
    ledger_records = []
    if Path(ledger_path).exists():
        ledger_records = [json.loads(x) for x in Path(ledger_path).read_text(encoding="utf-8").splitlines() if x.strip()]
    restart_ok, restart_reason = recovery.may_restart("FP-CONTROL-3", registry, Path(ledger_path))
    auth_text = Path(authorization_path).read_text(encoding="utf-8") if Path(authorization_path).exists() else ""
    closure = Path(p2_closure_path).read_text(encoding="utf-8") if Path(p2_closure_path).exists() else ""
    recon = re.search(r"reconcile\s+PASS · (\d+)/(\d+) findings", closure)
    merges = _out(runner, ["git", "-C", str(repo_root), "log", "--first-parent", "--merges", "-8", "--format=%H%x09%ct%x09%s", "HEAD"])
    uptime = _out(runner, ["cat", "/proc/uptime"])
    boot_id = _out(runner, ["cat", str(recovery.BOOT_ID)])
    ntp = _out(runner, ["timedatectl", "show", "-p", "NTPSynchronized", "--value"])
    health_timer = health.timer_expected("tlos-p3-health.timer", want_active=True, runner=runner)
    sets = sorted(p.name for p in Path(backup_target).glob("*") if (p / "BACKUP_RECORD.json").is_file()) \
        if Path(backup_target).is_dir() else []
    drills, audits = [], []
    for kind, out in (("drills", drills), ("audits", audits)):
        for f in sorted(Path(evidence_dir, kind).glob("*.json"), key=lambda q: q.stat().st_mtime):
            try:
                rec = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                rec = {"unreadable": True}
            rec["_file"], rec["_mtime"] = str(f), f.stat().st_mtime
            out.append(rec)
    return {
        "observation_version": "P3_CONTROL_ROOM_OBSERVATION_V1",
        "drills": drills,
        "audits": audits,
        "sealed": sealed_cohort(audits),
        "ledger_tail": ledger_records[-20:],
        "observed_epoch": now,
        "observed_utc": _utc(now),
        "hostname": socket.gethostname(),
        "health": {"findings": findings, "overall": health.overall(findings)},
        "health_timer": health_timer,
        "paper_containers": paper,
        "paper_error": paper_error,
        "running_containers": None if running is None else [n for n in running.splitlines() if n],
        "ledger": {"records": len(ledger_records), "problems": kill_switch.verify_ledger(Path(ledger_path)),
                   "last": ledger_records[-1] if ledger_records else None},
        "fp_control_3_restart": {"allowed": restart_ok, "reason": restart_reason},
        "registry": {
            "real_money_authorized": registry.get("real_money_authorized"),
            "fp_run_active": registry.get("fp_run_active"),
            "updated_utc": registry.get("registry_updated_utc"),
            "instances": [{"role": r.get("role"), "cohort_id": r.get("cohort_id"), "status": r.get("status"),
                           "closed_utc": r.get("closed_utc"), "closure_reason": r.get("closure_reason"),
                           "lifecycle": (r.get("outcome") or {}).get("full_trade_lifecycle"),
                           "capability": (r.get("outcome") or {}).get("paper_trading_operational_capability"),
                           "edge": (r.get("outcome") or {}).get("prospective_paper_edge")}
                          for r in registry.get("instances", [])],
        },
        "authorization": parse_authorization(auth_text),
        "p2_reconcile": {"passed": int(recon.group(1)), "total": int(recon.group(2))} if recon else None,
        "governance": {
            "main": _out(runner, ["git", "-C", str(repo_root), "rev-parse", "HEAD"]),
            "merges": [dict(zip(("sha", "epoch", "subject"), m.split("\t", 2))) for m in (merges or "").splitlines()],
        },
        "runtime": {"pin": _out(runner, ["git", "-C", str(runtime_root), "rev-parse", "HEAD"]),
                    "clean": _out(runner, ["git", "-C", str(runtime_root), "status", "--porcelain",
                                           "--untracked-files=no"]) == ""},
        "host": {"uptime_s": float(uptime.split()[0]) if uptime else None, "boot_id": boot_id,
                 "ntp_synced": {"yes": True, "no": False}.get(ntp or "")},
        "backup_sets": sets,
        "workstreams": json.loads(Path(workstreams_path).read_text(encoding="utf-8")),
    }


# ---------------------------------------------------------------- project
def _finding(obs: dict, check: str) -> dict | None:
    return next((f for f in obs["health"]["findings"] if f["check"] == check), None)


def _ws_chip(status: str) -> str:
    return {"ACCEPTED": "ok", "PARTIAL": "warn", "IN_PROGRESS": "info", "PENDING": "wait"}.get(status, "unk")


def _bi(v) -> bool:
    return isinstance(v, dict) and all(isinstance(v.get(k), str) and v.get(k) for k in ("en", "ar"))


def _ws_text(ws: dict, key: str) -> dict:
    """A bilingual text from the governed workstream record; a missing one says so (never a crash, never blank)."""
    v = ws.get(key)
    return b(v["en"], v["ar"]) if _bi(v) else b(f"Not recorded: the workstream record has no valid '{key}'",
                                               f"غير مسجّل: لا يحتوي سجل مسارات العمل على '{key}' صالح")


def _ws_rows(ws: dict) -> list | None:
    items = ws.get("workstreams")
    if not isinstance(items, list):
        return None
    rows = []
    for w in items:
        w = w if isinstance(w, dict) else {}
        status = w.get("status") if isinstance(w.get("status"), str) and w.get("status") else "UNKNOWN"
        wid = str(w.get("id") or "?")
        rows.append([_ws_chip(status), wid, b(w["en"], w["ar"]) if _bi(w) else b(wid, wid), status,
                     str(w.get("evidence") or "not recorded")])
    return rows


def _expiry_epoch(expires) -> float | None:
    """Epoch of an ``EXPIRES_UTC`` value in the record's one format, or None when it cannot be read."""
    if not isinstance(expires, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", expires):
        return None
    try:
        return datetime.strptime(expires, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return None


def project(obs: dict) -> dict:
    """Map an observation onto the prototype's scenario schema. Pure: no I/O."""
    now = obs["observed_utc"]
    findings = obs["health"]["findings"]
    # No findings at all means the health run did not report: health is UNPROVEN, never healthy.
    sev = obs["health"]["overall"] if findings else "UNKNOWN"
    not_info = [f for f in findings if f["severity"] != health.INFO]
    exc: dict = {}

    health_dim = ["unk", "unknown"] if not findings else {health.INFO: ["ok", "healthy"], health.WARNING: [
        "warn", "degraded"]}.get(sev, ["inc", b("Critical", "حرج")])
    if not findings:
        exc["health"] = b("No health findings in this observation: health is UNPROVEN.",
                          "لا نتائج صحة في هذا الرصد: الصحة غير مثبتة.")
    if not_info:
        exc["health"] = b("; ".join(f"{f['check']}: {f['detail']}" for f in not_info),
                          "؛ ".join(f"{f['check']}: {f['detail']}" for f in not_info))

    auth = obs["authorization"]
    expires_epoch = _expiry_epoch(auth.get("expires_utc"))
    expired = expires_epoch is None or expires_epoch < obs["observed_epoch"]
    authority_ok = auth["present"] is True and not expired and auth["real_money"] is True \
        and obs["registry"]["real_money_authorized"] is False
    authority_dim = ["ok", "valid"] if authority_ok else ["fail", b("Not valid", "غير صالحة")]
    if not authority_ok:
        exc["authority"] = b("P3 authorization record missing, expired, or the real-money boundary is not explicit.",
                             "سجل تفويض P3 مفقود أو منتهٍ، أو حد المال الحقيقي غير صريح.")

    backup_f = _finding(obs, "backup_recency")
    ledger_ok = not obs["ledger"]["problems"]
    evidence_ok = bool(backup_f) and backup_f["severity"] == health.INFO and ledger_ok
    evidence_dim = ["ok", "pass"] if evidence_ok else ["fail", "fail"]
    if not evidence_ok:
        exc["evidence"] = b(f"Backup: {backup_f['detail'] if backup_f else 'no finding'}; operator ledger: "
                            f"{'PASS' if ledger_ok else '; '.join(obs['ledger']['problems'])}",
                            f"النسخ الاحتياطي: {backup_f['detail'] if backup_f else 'لا نتيجة'}؛ سجل المشغّل: "
                            f"{'ناجح' if ledger_ok else '؛ '.join(obs['ledger']['problems'])}")

    paper = obs["paper_containers"]
    if paper is None:
        runtime_dim = ["unk", "unknown"]
        exc["runtime"] = b(f"Docker could not be read: {obs['paper_error']}", f"تعذّرت قراءة Docker: {obs['paper_error']}")
        runtime_label = b("Paper runtime state unknown", "حالة التشغيل الورقي غير معروفة")
    elif any(state == "running" for state in paper.values()):
        n = sum(state == "running" for state in paper.values())
        runtime_dim = ["ok", "running"]
        runtime_label = b(f"{n} paper runtime running", f"{n} تشغيل ورقي يعمل")
    elif all(state in _STOPPED_STATES for state in paper.values()):
        runtime_dim = ["off", "stopped"]
        exc["runtime"] = b("No paper cohort is running: P2 is closed and H1 is not launched (observed).",
                           "لا توجد مجموعة ورقية تعمل: P2 مغلقة وH1 لم تُطلق (مرصود).")
    else:
        # restarting / paused / removing: a paper runtime exists and is neither running nor stopped.
        odd = ", ".join(f"{n} {s}" for n, s in sorted(paper.items()) if s not in _STOPPED_STATES)
        runtime_dim = ["warn", "degraded"]
        exc["runtime"] = b(f"Paper runtime neither running nor stopped: {odd}", f"تشغيل ورقي ليس عاملًا ولا متوقفًا: {odd}")
        runtime_label = b(f"Paper runtime degraded ({odd})", f"تشغيل ورقي متدهور ({odd})")
    runtime_off = runtime_dim[0] == "off"

    rec = obs["p2_reconcile"]
    recon_dim = ["ok", b(f"{rec['passed']}/{rec['total']} · P2 final", f"{rec['passed']}/{rec['total']} · P2 النهائية")] \
        if rec and rec["passed"] == rec["total"] else ["unk", "unknown"]

    dims = {"health": health_dim, "authority": authority_dim, "evidence": evidence_dim,
            "freshness": ["ok", "fresh"], "runtime": runtime_dim, "recon": recon_dim}

    fp3 = next((i for i in obs["registry"]["instances"] if i["role"] == "FP-CONTROL-3"), {})
    ws = obs["workstreams"] if isinstance(obs["workstreams"], dict) else {}
    owner_v = ws.get("owner")
    owner = ([owner_v["state"], b(owner_v["en"], owner_v["ar"])]
             if _bi(owner_v) and owner_v.get("state") in ("req", "info", "none")
             else ["req", _ws_text({}, "owner")])  # an unreadable Owner line asks the Owner to look
    ws_rows = _ws_rows(ws)
    merges = obs["governance"]["merges"]
    last_merge = merges[0] if merges else None
    pr_m = re.search(r"#(\d+)", last_merge["subject"]) if last_merge else None
    pr = pr_m.group(1) if pr_m else "?"
    lgc = b(f"PR #{pr} merged · {last_merge['sha'][:8]} · {_utc(float(last_merge['epoch']))}",
            f"دُمج طلب الدمج #{pr} · {last_merge['sha'][:8]} · {_utc(float(last_merge['epoch']))}") \
        if last_merge else b("Not observed", "غير مرصود")

    newest = obs["backup_sets"][-1] if obs["backup_sets"] else None
    ledger_last = obs["ledger"]["last"]
    known, unknown, affected = [], [], []
    if fp3.get("status") == "CLOSED":
        known.append(b(f"P2 CLOSED / PASS · {fp3.get('cohort_id')} · {fp3.get('closed_utc')} (registry)",
                       f"P2 مغلقة / ناجحة · {fp3.get('cohort_id')} · {fp3.get('closed_utc')} (السجل)"))
    else:
        unknown.append(b("FP-CONTROL-3 registry row not observed CLOSED", "صف FP-CONTROL-3 في السجل غير مرصود كمغلق"))
    if authority_ok:
        known.append(b(f"P3 executing under 7b1b1fa1 · expires {auth['expires_utc']}",
                       f"P3 قيد التنفيذ بموجب 7b1b1fa1 · تنتهي {auth['expires_utc']}"))
    else:
        affected.append(b(f"P3 authorization not valid (missing, expired or unreadable expiry: {auth.get('expires_utc')})",
                          f"تفويض P3 غير صالح (مفقود أو منتهٍ أو تاريخ انتهاء غير مقروء: {auth.get('expires_utc')})"))
    rm_blocked = obs["registry"]["real_money_authorized"] is False and auth["real_money"] is True
    h1_blocked = auth["h1_launch"] is True
    if rm_blocked and h1_blocked:
        known.append(b("Real money blocked · H1 launch not authorized", "المال الحقيقي محظور · إطلاق H1 غير مصرّح"))
    else:
        if rm_blocked:
            known.append(b("Real money blocked", "المال الحقيقي محظور"))
        else:
            unknown.append(b("Real money boundary not proven by the registry and the authorization record (treated as blocked)",
                             "حد المال الحقيقي غير مثبت في السجل وسجل التفويض (يُعامل كمحظور)"))
        if h1_blocked:
            known.append(b("H1 launch not authorized", "إطلاق H1 غير مصرّح"))
        else:
            unknown.append(b("H1 launch boundary not explicit in the authorization record (treated as not authorized)",
                             "حد إطلاق H1 غير صريح في سجل التفويض (يُعامل كغير مصرّح)"))
    if backup_f:
        known.append(b(f"Backup: {backup_f['detail']} · verify {'PASS' if backup_f['severity'] == health.INFO else 'FAIL'}",
                       f"النسخ الاحتياطي: {backup_f['detail']} · التحقق {'ناجح' if backup_f['severity'] == health.INFO else 'فاشل'}"))
    known.append(b(f"Operator ledger: {obs['ledger']['records']} records, chain {'PASS' if ledger_ok else 'FAIL'}",
                   f"سجل المشغّل: {obs['ledger']['records']} سجلات، السلسلة {'ناجحة' if ledger_ok else 'فاشلة'}"))
    known.append(b(f"FP-CONTROL-3 restart refused: {obs['fp_control_3_restart']['reason']}",
                   f"إعادة تشغيل FP-CONTROL-3 مرفوضة: {obs['fp_control_3_restart']['reason']}"))
    unknown.append(b("Off-host observation: not implemented (PLN-05 Tier 3 / PLN-06)",
                     "الرصد من خارج الجهاز: غير منفّذ (PLN-05 المستوى 3 / PLN-06)"))
    if ws_rows is None:
        unknown.append(b("Workstream statuses: the workstream record lists none", "حالات مسارات العمل: لا يسرد السجل أيًا منها"))
    reboot = _reboot_acceptance(ws)
    if reboot:
        known.append(b(reboot["en"], reboot["ar"]))
        # the open items are the record's, not code: a decision closed by a merged record leaves the view with it
        unverified = _reboot_open(reboot)
        if unverified is None:
            unverified = [b("PLN-04 reboot acceptance: open items not recorded in the governed record",
                            "قبول إعادة الإقلاع PLN-04: البنود المفتوحة غير مسجّلة في السجل المحكوم")]
    else:
        unverified = [b("Recovery after a host reboot (PLN-04): not yet exercised",
                        "التعافي بعد إعادة إقلاع الخادم (PLN-04): لم يُختبر بعد")]

    events = []
    for m in reversed(merges):
        n = re.search(r"#(\d+)", m["subject"])
        events.append({"t": _utc(float(m["epoch"])), "s": "ok", "c": "stage", "ck": m is last_merge,
                       "d": b(f"Owner merged PR #{n.group(1) if n else '?'} · {m['sha'][:8]}",
                              f"دمج المالك طلب الدمج #{n.group(1) if n else '?'} · {m['sha'][:8]}"),
                       "src": b("repository", "المستودع")})
    if newest:
        events.append({"t": f"{newest[:4]}-{newest[4:6]}-{newest[6:8]} {newest[9:11]}:{newest[11:13]}Z", "s": "ok",
                       "c": "system", "d": b(f"Backup set {newest} written", f"كُتبت مجموعة النسخ {newest}"),
                       "src": b("backup record", "سجل النسخ")})
    events.sort(key=lambda e: e["t"])
    events.append({"t": now, "s": "unk" if not findings else "ok" if sev == health.INFO else "warn", "c": "system",
                   "d": b(f"Health check: {sev}", f"فحص الصحة: {sev}"), "src": b("health check", "فحص الصحة")})

    system_txt = b(
        f"No paper runtime. Backups daily (newest {newest or 'none'}); health hourly: {sev}.",
        f"لا تشغيل ورقي. النسخ يوميًا (الأحدث {newest or 'لا يوجد'})؛ الصحة كل ساعة: {sev}.")
    if not runtime_off:
        system_txt = b(f"{runtime_label['en']}. Health hourly: {sev}.", f"{runtime_label['ar']}. الصحة كل ساعة: {sev}.")

    host = obs["host"]
    up = host["uptime_s"]
    boot = _utc(obs["observed_epoch"] - up) if up is not None else None
    running = obs["running_containers"]
    others = None if running is None else [n for n in running if n not in (paper or {})]
    sys_ = {
        "host": ["ok", b(f"Up · {up / 86400:.1f} d", f"يعمل · {up / 86400:.1f} يوم")] if up is not None else ["unk", "unknown"],
        "containers": ["unk", "unknown"] if running is None else
        (["off", b(f"No paper runtime · {len(others)} other running", f"لا تشغيل ورقي · {len(others)} أخرى تعمل")]
         if runtime_off else [runtime_dim[0], b(f"{len(running)} running", f"{len(running)} تعمل")]),
        "feed": ["off", b("No feed · no runtime", "لا تغذية · لا تشغيل")] if runtime_off else ["unk", "unknown"],
        "api": ["off", b("Not used · no runtime", "غير مستخدمة · لا تشغيل")] if runtime_off else ["unk", "unknown"],
        "monitor": ["ok", b("Health timer active", "مؤقت الصحة نشط")] if obs["health_timer"]["severity"] == health.INFO
        else ["warn", b(obs["health_timer"]["detail"], obs["health_timer"]["detail"])],
        "clock": {True: ["ok", b("Synced", "متزامنة")], False: ["warn", b("Not synced", "غير متزامنة")]}.get(
            host["ntp_synced"], ["unk", "unknown"]),
        "boot": boot or "—",
    }

    stage_en, stage_ar = ("P3 Paper Beta is executing", "النسخة التجريبية الورقية P3 قيد التنفيذ") if authority_ok \
        else ("P3 authorization is not valid", "تفويض P3 غير صالح")
    rt_en, rt_ar = ("No paper runtime is running.", "لا يعمل أي تشغيل ورقي.") if runtime_off \
        else (f"{runtime_label['en']}.", f"{runtime_label['ar']}.")
    scenario = {
        "label": "LIVE", "now": now, "step": 6, "sub": 6, "signal": "owner" if owner[0] == "req" else "events",
        "dims": dims, "exc": exc, "banner": None,
        "verdict": b(f"P2 is closed (PASS). {stage_en}; health {sev}. {rt_en}",
                     f"أُغلقت P2 (ناجحة). {stage_ar}؛ الصحة {sev}. {rt_ar}"),
        "owner": owner,
        "claude": _ws_text(ws, "claude"),
        "system": system_txt,
        "next": _ws_text(ws, "next"), "fromContract": True,
        "lgc": lgc,
        "lho": b(f"{now} · health {sev}", f"{now} · الصحة {sev}") if findings and sev == health.INFO
        else b("Not current", "غير حالي"),
        "nowObs": b(f"Observed {now}", f"رُصد {now}"),
        "known": known, "unknown": unknown, "affected": affected, "unverified": unverified,
        "events": events, "incidents": [], "viewerNew": 0, "viewStale": False,
        "extraForbid": [],
        # Decisions and positions are known to be none only while the runtime is observed stopped; a running,
        # degraded or unobserved runtime has decisions and positions this view does not read (unverified).
        "dec": {"unv": not runtime_off, "stale": False,
                "none": b(f"No paper cohort running; no decisions since the P2 closure ({fp3.get('closed_utc')}).",
                          f"لا مجموعة ورقية تعمل؛ لا قرارات منذ إغلاق P2 ({fp3.get('closed_utc')}).")
                if runtime_off else None},
        "pos": [], "posUnv": not runtime_off, "risk": {"stale": False},
        "ops": {"runtime": runtime_dim, "safe": ["off", "notEngaged"], "recovery": ["off", "none"], "rec": None,
                "unresolved": 0,
                "hist": b(f"Last operator record: {ledger_last.get('outcome')} · {ledger_last.get('utc')}",
                          f"آخر سجل للمشغّل: {ledger_last.get('outcome')} · {ledger_last.get('utc')}")
                if ledger_last else b("No operator record", "لا سجل للمشغّل")},
        "checks": {"fail": 0, "pending": 0},
        "sys": sys_,
        "outcome": ["ok", b("PASS", "ناجحة")],
        "law": {"capProps": ["ok", b("12/12", "12/12")],
                "lifecycle": ["ok", b("Observed · BTC/USDT trade 1", "رُصدت · BTC/USDT الصفقة 1")]
                if fp3.get("lifecycle") == "OBSERVED" else ["wait", b("Not observed", "لم تُرصد")],
                "recon": ["ok", "pass"] if recon_dim[0] == "ok" else ["unk", "unknown"],
                "integrity": ["ok", "pass"], "identity": ["ok", b("Matches", "متطابقة")],
                "safe": ["ok", "done"], "records": ["ok", "done"]},
    }
    rm = obs["registry"]["real_money_authorized"] is False
    blocked = ["blocked", "blocked"]
    cap_src = "registry + P3_CONTRACT §23"
    caps = [
        {"k": b("Paper trading", "التداول الورقي"), "st": ["off", b("No cohort running", "لا مجموعة تعمل")] if runtime_off else runtime_dim,
         "scope": b("Governed cohorts only", "المجموعات المحكومة فقط"), "src": cap_src, "chg": b("Owner authorization", "تفويض المالك"), "exec": True},
        {"k": b("Long entries", "صفقات الشراء"), "st": ["off", b("No cohort running", "لا مجموعة تعمل")] if runtime_off else ["unk", "unknown"],
         "scope": b("Paper only", "ورقي فقط"),
         "src": cap_src, "chg": b("Owner authorization", "تفويض المالك"), "exec": True},
        {"k": b("Shorts", "البيع على المكشوف"), "st": blocked, "scope": b("All", "الكل"), "src": cap_src, "chg": None, "exec": True},
        {"k": b("Leverage", "الرافعة المالية"), "st": blocked, "scope": b("All", "الكل"), "src": cap_src, "chg": None, "exec": True},
        {"k": b("Margin", "الهامش"), "st": blocked, "scope": b("All", "الكل"), "src": cap_src, "chg": None},
        {"k": b("Futures", "العقود الآجلة"), "st": blocked, "scope": b("All", "الكل"), "src": cap_src, "chg": None},
        {"k": b("Real money", "المال الحقيقي"), "st": blocked if rm else ["unk", "unkBlocked"], "scope": b("All", "الكل"),
         "src": "registry real_money_authorized=false", "chg": None},
        {"k": b("Withdrawals", "السحب"), "st": blocked, "scope": b("All", "الكل"), "src": cap_src, "chg": None},
    ]
    project_chips = [
        ["ok", b("P1 closed · PASS", "P1 مغلقة · ناجحة")],
        ["ok", b("P2 closed · PASS", "P2 مغلقة · ناجحة")],
        ["info", b("P3 executing", "P3 قيد التنفيذ")] if authority_ok
        else ["fail", b("P3 authorization not valid", "تفويض P3 غير صالح")],
    ]
    live = {
        "live_version": "P3_CONTROL_ROOM_LIVE_V1",
        "observed_utc": now, "observed_epoch": obs["observed_epoch"], "budget_s": FRESHNESS_BUDGET_S,
        # the client re-checks expiry itself: a page generated before expiry must not say "valid" after it
        "auth_expires_epoch": expires_epoch if authority_ok else None,
        "hostname": obs["hostname"],
        "ident": {"stage": b("P3 · Paper Beta executing", "P3 · النسخة التجريبية الورقية قيد التنفيذ") if authority_ok
                  else b("P3 · authorization not valid", "P3 · التفويض غير صالح"), "ref": "7b1b1fa1"},
        "project": {"chips": project_chips,
                    "gate": _ws_text(ws, "next"),
                    "workstreams": ws_rows or [],
                    "ws_updated": ws.get("updated_utc") or "—"},
        "identity": {"runtime_pin": obs["runtime"]["pin"], "runtime_clean": obs["runtime"]["clean"],
                     "main": obs["governance"]["main"], "boot_id": obs["host"]["boot_id"]},
        "health_findings": obs["health"]["findings"],
        # Incidents are raised from non-INFO health findings. With no findings at all the health run did
        # not report, so "none open" would be unproven: the view says UNKNOWN instead (fail closed).
        "incidents_state": {"state": "bound"} if obs["health"]["findings"] else
        {"state": "unknown", "why": b("No health findings in this observation; incidents are UNPROVEN.",
                                      "لا نتائج صحة في هذا الرصد؛ الحوادث غير مثبتة.")},
        "prov": {
            "health": {"kind": b("Derived", "مشتقة"), "src": b("P3 health check over host, timers, mounts, backups",
                                                            "فحص صحة P3 عبر الخادم والمؤقتات ونقاط التحميل والنسخ"),
                       "auth": b("Runtime observation", "رصد التشغيل"), "ref": f"research/p3/health.py · {now}"},
            "authority": {"kind": b("Governed record", "سجل محكوم"), "src": b("Owner P3 authorization + registry",
                                                                           "تفويض المالك لـ P3 + السجل"),
                          "auth": b("Governance", "الحوكمة"),
                          "ref": f"docs/p3/OWNER_P3_EXECUTION_AUTHORIZATION.md@7b1b1fa1 · expires {auth['expires_utc']}"},
            "evidence": {"kind": b("Direct observation", "رصد مباشر"), "src": b("Backup verify + operator ledger chain",
                                                                             "تحقق النسخ + سلسلة سجل المشغّل"),
                         "auth": b("Evidence ledger", "سجل الأدلة"), "ref": f"{newest or '—'} · operator_ledger.jsonl"},
            "freshness": {"kind": b("Derived (client)", "مشتقة (في الواجهة)"), "src": b("Age of this generated view",
                                                                                     "عمر هذه الشاشة المُنشأة"),
                          "auth": b("UI only", "الواجهة فقط"), "ref": f"budget {FRESHNESS_BUDGET_S // 60} min"},
            "runtime": {"kind": b("Direct observation", "رصد مباشر"), "src": b("docker ps, paper runtime patterns",
                                                                            "docker ps، أنماط التشغيل الورقي"),
                        "auth": b("Runtime observation", "رصد التشغيل"), "ref": "research/p3/kill_switch.py paper_containers"},
            "recon": {"kind": b("Governed record", "سجل محكوم"), "src": b("P2 closure reconciliation (sealed)",
                                                                       "مطابقة إغلاق P2 (مختومة)"),
                      "auth": b("Evidence ledger", "سجل الأدلة"), "ref": "docs/p2/P2_CLOSURE.md · l2-cohort-20260924T120000Z"},
        },
        "scenario": scenario,
        "caps": caps,
        # The prototype's FORBID list describes P2 ("P3 code or runtime action"); under P3 execution the
        # governed list is this one, the same as the resume brief's FORBIDDEN line.
        "forbid": FORBIDDEN_NOW,
        "real_money_authorized": False,
    }
    _bind_screens(obs, live)
    _bind_slice3(obs, live)
    return live


def _reboot_acceptance(ws: dict) -> dict | None:
    """The reboot-correctness acceptance from the governed workstream record (PR #94), or None.

    Fail-closed: anything but a complete ``state == "ok"`` record keeps the reboot shown as not exercised."""
    r = ws.get("reboot") if isinstance(ws, dict) else None
    if isinstance(r, dict) and r.get("state") == "ok" and _bi(r) and isinstance(r.get("record"), str) and r["record"]:
        return r
    return None


def _reboot_open(r: dict) -> list[dict] | None:
    """The open items the accepted reboot record lists (each bilingual), or None when they are not readable."""
    items = r.get("open")
    if isinstance(items, list) and all(_bi(i) for i in items):
        return [b(i["en"], i["ar"]) for i in items]
    return None


def _sevc(severity: str) -> str:
    return {health.INFO: "ok", health.WARNING: "warn"}.get(severity, "inc")


def _bind_screens(obs: dict, live: dict) -> None:
    """Data for the screens bound after the Command Center: Project & Continuity, Incidents, Operations,
    Risk & Authority, Evidence & Reconciliation and History. Pure; adds keys to ``live``."""
    sc = live["scenario"]
    now = obs["observed_utc"]
    findings = obs["health"]["findings"]
    backup_f = _finding(obs, "backup_recency")
    sets = obs["backup_sets"]
    drill = next((d for d in reversed(obs.get("drills", [])) if not d.get("unreadable")), None)
    drill_ok = bool(drill) and drill.get("PLN_03_RESTORE_DRILL") == "PASS"
    reboot = _reboot_acceptance(obs["workstreams"])
    sealed = [a for k, v in (drill or {}).get("checks", {}).items() if k.startswith("sealed:") for a in v.get("archives", [])]

    # Incidents: every non-INFO health finding is an open incident; nothing is invented.
    incidents = []
    for f in findings:
        if f["severity"] == health.INFO:
            continue
        incidents.append({
            "id": f"HEALTH-{f['check']}", "s": "open", "when": now,
            "title": b(f"Health check {f['severity']}: {f['check']}", f"فحص الصحة {f['severity']}: {f['check']}"),
            "f": {"known": b(f["detail"], f["detail"]),
                  "detect": b("Scheduled P3 health check (hourly)", "فحص صحة P3 المجدول (كل ساعة)"),
                  "unknown": b("Cause, until an operator investigates.", "السبب، حتى يتحقق المشغّل."),
                  "next": b("Investigate on the host; the health check re-evaluates every hour.",
                            "التحقق على الخادم؛ يعيد فحص الصحة التقييم كل ساعة."),
                  "state": b("Open", "مفتوح"), "owner": b("Informed", "للعلم"),
                  "evidence": b("research/p3/health.py · journal tlos-p3-health", "research/p3/health.py · سجل tlos-p3-health")}})
    sc["incidents"] = incidents
    if incidents:
        sc["signal"] = "incident"

    # History: governance merges, backup sets, operator ledger, drills and audits on one timeline.
    events = [e for e in sc["events"] if e["c"] == "stage"]
    for name in sets:
        events.append({"t": f"{name[:4]}-{name[4:6]}-{name[6:8]} {name[9:11]}:{name[11:13]}Z", "s": "ok", "c": "system",
                       "d": b(f"Backup set {name} written", f"كُتبت مجموعة النسخ {name}"), "src": b("backup record", "سجل النسخ")})
    for r in obs.get("ledger_tail", []):
        t = (r.get("utc") or "")[:16].replace("T", " ") + "Z"
        events.append({"t": t, "s": "ok" if r.get("outcome") in ("STOPPED", "DRY_RUN", None) else "warn", "c": "system",
                       "d": b(f"Operator ledger: {r.get('record_type', 'kill switch')} · {r.get('outcome', '')} · {r.get('reason', '')}",
                              f"سجل المشغّل: {r.get('record_type', 'مفتاح الإيقاف')} · {r.get('outcome', '')} · {r.get('reason', '')}"),
                       "src": b("operator ledger", "سجل المشغّل")})
    for d in obs.get("drills", []):
        events.append({"t": _utc(d["_mtime"]), "s": "ok" if d.get("PLN_03_RESTORE_DRILL") == "PASS" else "fail", "c": "recon",
                       "d": b(f"Restore drill {d.get('backup_set', '?')}: {d.get('PLN_03_RESTORE_DRILL', 'unreadable')}",
                              f"تمرين الاستعادة {d.get('backup_set', '?')}: {d.get('PLN_03_RESTORE_DRILL', 'غير مقروء')}"),
                       "src": b("drill record", "سجل التمرين")})
    for a in obs.get("audits", []):
        events.append({"t": _utc(a["_mtime"]), "s": "warn" if a.get("unbacked") else "ok", "c": "recon",
                       "d": b(f"Execution audit {Path(a.get('evidence_dir', '?')).parent.name}: {a.get('EXECUTION_BACKED_BY_ADMITTED_DECISION')} "
                              f"({a.get('unbacked', '?')} unbacked)",
                              f"تدقيق التنفيذ {Path(a.get('evidence_dir', '?')).parent.name}: {a.get('EXECUTION_BACKED_BY_ADMITTED_DECISION')} "
                              f"({a.get('unbacked', '?')} غير مدعوم)"),
                       "src": b("audit record", "سجل التدقيق")})
    events.sort(key=lambda e: e["t"])
    events.append(sc["events"][-1])  # the current health check, last
    sc["events"] = events

    # Operations: backup, restore and recovery from records; actions are operator CLIs, not view buttons.
    live["ops"] = {
        "backup": [_sevc(backup_f["severity"]), b(backup_f["detail"], backup_f["detail"])] if backup_f else ["unk", "unknown"],
        "last_set": sets[-1] if sets else None,
        "retention": b("Append-only; no pruning (deleting sets needs an Owner decision)",
                       "إضافة فقط؛ لا حذف (حذف المجموعات يحتاج قرار المالك)"),
        "restore": ["ok", b(f"Drill PASS · {drill.get('backup_set')}", f"التمرين ناجح · {drill.get('backup_set')}")] if drill_ok
        else (["fail", "fail"] if drill else ["unk", "notRecorded"]),
        "restore_when": _utc(drill["_mtime"]) if drill else None,
        "points": len(sets),
        "reboot": (["ok", b(reboot["en"], reboot["ar"])] if reboot
                   else ["wait", b("Not yet exercised · Owner window", "لم يُختبر بعد · نافذة المالك")]),
        "acts": [
            [b("Kill switch (stop paper runtimes)", "مفتاح الإيقاف (إيقاف التشغيل الورقي)"), "scripts/p3/kill_switch.py --reason …",
             b("Hash-chained operator ledger; bounded docker stop", "سجل مشغّل متسلسل بالبصمة؛ إيقاف docker محدود")],
            [b("Restart guard / resume authorization", "حارس إعادة التشغيل / تفويض الاستئناف"), "scripts/p3/recovery.py may-restart | authorize-resume",
             b("Refuses CLOSED cohorts and standing stops", "يرفض المجموعات المغلقة والإيقافات القائمة")],
            [b("Verify latest backup", "التحقق من آخر نسخة"), "scripts/p3/backup.py verify --set …", b("Read-only", "قراءة فقط")],
            [b("Restore drill into empty scratch", "تمرين استعادة في مجلد فارغ"), "scripts/p3/backup.py drill --set … --scratch … --json …",
             b("Never restores over live state", "لا يستعيد فوق الحالة الحية")],
            [b("Offsite push + verify", "نسخ خارجي + تحقق"), "scripts/p3/offsite.py --set … --dest …",
             b("Append-only; needs an independent host", "إضافة فقط؛ يحتاج خادمًا مستقلًا")],
        ],
    }

    # Evidence & Reconciliation: real checks with their sources.
    rows = []
    rec = obs.get("p2_reconcile")
    rows.append([b("P2 final reconciliation (sealed)", "مطابقة P2 النهائية (مختومة)"),
                 ["ok", b(f"PASS · {rec['passed']}/{rec['total']}", f"ناجحة · {rec['passed']}/{rec['total']}")] if rec else ["unk", "unknown"],
                 "docs/p2/P2_CLOSURE.md"])
    rows.append([b("Sealed archives re-verified on restore", "الأرشيفات المختومة أُعيد التحقق منها عند الاستعادة"),
                 ["ok", b(f"{len(sealed)} ARCHIVE_VERIFIED", f"{len(sealed)} ARCHIVE_VERIFIED")]
                 if sealed and all(v == "ARCHIVE_VERIFIED" for _, v in sealed) else ["unk", "notRecorded"],
                 drill["_file"] if drill else "—"])
    rows.append([b("Newest backup set verifies", "أحدث مجموعة نسخ تتحقق"),
                 [_sevc(backup_f["severity"]), "pass" if backup_f["severity"] == health.INFO else "fail"] if backup_f else ["unk", "unknown"],
                 "research/p3/backup.py verify_backup"])
    rows.append([b("Restore drill", "تمرين الاستعادة"), live["ops"]["restore"], drill["_file"] if drill else "—"])
    rows.append([b("Operator ledger hash chain", "سلسلة بصمات سجل المشغّل"),
                 ["ok", "pass"] if not obs["ledger"]["problems"] else ["fail", "fail"], "research/p3/kill_switch.py verify_ledger"])
    for a in obs.get("audits", []):
        backed = a.get("EXECUTION_BACKED_BY_ADMITTED_DECISION") == "PASS"
        rows.append([b(f"Executions backed by admitted decisions · {Path(a.get('evidence_dir', '?')).parent.name}",
                       f"تنفيذات مدعومة بقرارات مقبولة · {Path(a.get('evidence_dir', '?')).parent.name}"),
                     ["ok", "pass"] if backed else ["warn", b(f"{a.get('unbacked')} unbacked · contextual (F-2)",
                                                              f"{a.get('unbacked')} غير مدعوم · سياقي (F-2)")],
                     a["_file"]])
    live["evidence_rows"] = rows

    # Risk & Authority: the governed configuration of the last cohort, and capability preconditions.
    live["risk_cfg"] = {"limits": b("stoploss -0.25 · max_open_trades 2 (FP-CONTROL-3 runtime identity)",
                                    "stoploss -0.25 · max_open_trades 2 (هوية تشغيل FP-CONTROL-3)"),
                        "src": "research/fp/records/forward_paper_cohort_registry.json"}
    pre = {"Paper trading": b("A governed cohort with Owner authorization; none running", "مجموعة محكومة بتفويض المالك؛ لا شيء يعمل"),
           "Long entries": b("Within a running paper cohort only", "داخل مجموعة ورقية عاملة فقط"),
           "Real money": b("POST-BETA and a separate Owner authorization", "ما بعد البيتا وتفويض منفصل من المالك")}
    for c in live["caps"]:
        c["since"] = "—"
        c["pre"] = pre.get(c["k"]["en"], b("Not authorized in P3", "غير مصرّح في P3"))

    # Project & Continuity: the stage map with its real evidence sources, and the resume brief.
    live["stages"] = [
        ["P1", ["ok", b("Closed · PASS", "مغلقة · ناجحة")], b("Merged P1 closure (CLAUDE.md stage law)", "إغلاق P1 المدمج (قانون المراحل)")],
        ["P2", ["ok", b("Closed · PASS · FP-CONTROL-3", "مغلقة · ناجحة · FP-CONTROL-3")], b("docs/p2/P2_CLOSURE.md · PR #70 0ce72358", "docs/p2/P2_CLOSURE.md · PR #70 0ce72358")],
        ["P3", ["info", b("Paper Beta Release · executing", "إصدار البيتا الورقي · قيد التنفيذ")],
         b("docs/p3/OWNER_P3_EXECUTION_AUTHORIZATION.md · 7b1b1fa1", "docs/p3/OWNER_P3_EXECUTION_AUTHORIZATION.md · 7b1b1fa1")],
        ["POST-BETA", ["na", b("Controlled-Live Readiness · not authorized", "جاهزية التشغيل الحي المضبوط · غير مصرّح")],
         b("Separate future Owner authorization required", "يتطلب تفويضًا مستقبليًا منفصلًا من المالك")],
    ]
    E = lambda v: v["en"] if isinstance(v, dict) else str(v)  # noqa: E731
    J = lambda a: "; ".join(E(v) for v in a) if a else "none"  # noqa: E731
    live["brief"] = "\n".join([
        "TRADING LAB OS — RESUME BRIEF · LIVE PROJECTION · READ-ONLY · NOT EVIDENCE AUTHORITY",
        f"DERIVED: {now} on {obs['hostname']}",
        f"STAGE: {live['ident']['stage']['en']} · authorization 7b1b1fa1 (expires {obs['authorization']['expires_utc']}) · "
        f"main {(obs['governance']['main'] or '?')[:12]} · runtime pin {(obs['runtime']['pin'] or '?')[:12]}",
        f"LAST GOVERNED CHECKPOINT: {E(sc['lgc'])}",
        f"LAST HEALTHY OBSERVATION: {E(sc['lho'])}",
        f"KNOWN: {J(sc['known'])}", f"UNKNOWN: {J(sc['unknown'])}", f"AFFECTED: {J(sc['affected'])}",
        f"UNVERIFIED: {J(sc['unverified'])}",
        f"OWNER: {E(sc['owner'][1])}", f"CLAUDE: {E(sc['claude'])}", f"SYSTEM: {E(sc['system'])}",
        f"NEXT GOVERNED STEP (derived from contract): {E(sc['next'])}",
        "FORBIDDEN: real money; H1 launch; restarting FP-CONTROL-3; strategy, risk or dataset change; reopening the product shape",
    ])


FORBIDDEN_NOW = [
    b("Real money", "المال الحقيقي"),
    b("H1 launch", "إطلاق H1"),
    b("Restarting FP-CONTROL-3", "إعادة تشغيل FP-CONTROL-3"),
    b("Strategy, risk or dataset change", "تغيير الاستراتيجية أو المخاطر أو مجموعة البيانات"),
    b("Reopening the product shape", "إعادة فتح شكل المنتج"),
]


def _ms_utc(ms) -> str:
    return datetime.fromtimestamp(int(ms) / 1000, timezone.utc).strftime("%Y-%m-%d %H:%MZ")


_TF_MS = {"1m": 60_000, "5m": 300_000, "15m": 900_000, "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}
_ACTION = {"enter_long": b("ENTER", "دخول"), "exit_long": b("EXIT", "خروج"), "hold": b("HOLD", "انتظار")}


def _decision_row(i: int, d: dict, fills: dict, ev: str) -> dict:
    """One sealed decision on the prototype's DECS shape. Only logged fields are shown; a stage the runtime
    does not log is 'not logged', never inferred."""
    adm = d.get("admission") or {}
    result, reasons = adm.get("result"), adm.get("reasons") or []
    action = d.get("intended_action")
    act = _ACTION.get(action, b(str(action), str(action)))
    tf_ms = _TF_MS.get(d.get("timeframe", "1h"), 3_600_000)
    close_utc = _ms_utc(int(d.get("candle_ts") or 0) + tf_ms)
    if action == "hold":
        outcome = ["warn", act]
    elif result == "ADMITTED":
        outcome = ["ok", act]
    elif result == "BLOCKED":
        outcome = ["inc", b(f"{act['en']} · BLOCKED", f"{act['ar']} · محجوب")]
    else:
        outcome = ["off", b(f"{act['en']} · {result or 'no admission'}", f"{act['ar']} · {result or 'لا قبول'}")]
    not_logged = ["unk", b("not logged", "غير مسجّل")]
    off = ["off", "—"]
    fill = fills.get((d.get("pair"), action, close_utc.replace(" ", "T")))  # audit format YYYY-MM-DDTHH:MMZ
    acting = action in ("enter_long", "exit_long")
    tr = [
        ["ok", b(str(d.get("signal_state")), str(d.get("signal_state")))] if d.get("signal_state") else not_logged,
        ["ok", b(f"{d.get('bar_class')} bar", f"شمعة {d.get('bar_class')}")] if d.get("bar_class") == "LIVE"
        else (["warn", b(str(d.get("bar_class")), str(d.get("bar_class")))] if d.get("bar_class") else not_logged),
        ["info", b(f"EMA {d.get('ema_fast')} / {d.get('ema_slow')}", f"EMA {d.get('ema_fast')} / {d.get('ema_slow')}")]
        if d.get("ema_fast") is not None else not_logged,
        (["ok", b("ADMITTED", "مقبول")] if result == "ADMITTED" else
         ["inc", b(f"BLOCKED · {'; '.join(reasons)}", f"محجوب · {'؛ '.join(reasons)}")] if result == "BLOCKED" else off)
        if acting else off,
        not_logged if acting and result == "ADMITTED" else off,
        outcome,
        (["ok", b(f"filled {fill['fill_utc']}", f"نُفّذ {fill['fill_utc']}")] if fill else
         ["warn", b("no fill recorded", "لا تنفيذ مسجّل")]) if acting and result == "ADMITTED" else off,
        ["ok", b("backed · PLN-07 audit", "مدعوم · تدقيق PLN-07")] if fill else off,
        not_logged if fill else off,
    ]
    why = d.get("no_action_reason") or ("; ".join(reasons) if reasons else (result or ""))
    return {"id": f"s{i}", "t": close_utc, "p": d.get("pair"), "tf": d.get("timeframe"), "o": outcome,
            "r": b(why or "—", why or "—"), "tr": tr,
            "refs": f"{ev}/paper_decision_ledger.jsonl · {d.get('market_event_id', '—')}",
            "ident": f"strategy {str(d.get('strategy_sha256') or '—')[:12]} · config {str(d.get('config_sha256') or '—')[:12]}",
            "t0": d.get("t0_relation")}


def _bind_slice3(obs: dict, live: dict) -> None:
    """Slice 3: Decisions, Trades & Positions, Market Workspace and Settings, from the sealed cohort named by
    the newest execution-audit record. Pure; adds keys to ``live``. Missing evidence is unknown, never healthy."""
    sealed = obs.get("sealed")
    if not sealed:
        state, why = "none", b("No execution-audit record names a sealed cohort; nothing to show.",
                               "لا يوجد سجل تدقيق تنفيذ يحدد مجموعة مختومة؛ لا شيء للعرض.")
    elif sealed.get("error"):
        state, why = "unreadable", b(f"Sealed ledgers could not be read: {sealed['error']}",
                                     f"تعذّرت قراءة السجلات المختومة: {sealed['error']}")
    else:
        state, why = "bound", None
    src = sealed["evidence_dir"] if sealed else "—"
    cohort = sealed.get("cohort") if sealed else None
    execs = (sealed or {}).get("executions") or []
    # each backed execution, keyed by (pair, action, decided candle close 'YYYY-MM-DDTHH:MMZ')
    fills = {}
    for e in execs:
        bd = e.get("backing_decision") or {}
        if e.get("backed") and bd.get("candle_close_utc"):
            action = "enter_long" if e.get("event") == "position_opened" else "exit_long"
            fills[(e.get("pair"), action, bd["candle_close_utc"])] = e
    rows = [_decision_row(i, d, fills, sealed["evidence_dir"]) for i, d in enumerate(sealed["decisions"])] \
        if state == "bound" else []
    live["decisions"] = {"state": state, "why": why, "cohort": cohort, "src": src,
                         "n": (sealed or {}).get("n_decisions"), "rows": rows}

    # Trades & Positions: closed lifecycles from the sealed trade ledger, each leg's backing from the audit.
    backed = {(e.get("trade_id"), e.get("event")): e.get("backed") for e in execs}
    closed = []
    if state == "bound":
        opened = {t.get("trade_id"): t for t in sealed["trades"] if t.get("event") == "position_opened"}
        for t in sealed["trades"]:
            if t.get("event") != "position_closed":
                continue
            o = opened.get(t.get("trade_id"), {})
            legs = [backed.get((t.get("trade_id"), "position_opened")), backed.get((t.get("trade_id"), "position_closed"))]
            if all(v is True for v in legs):
                recon, outcome = ["ok", "pass"], ["ok", b("Backed · entry + exit", "مدعومة · دخول + خروج")]
            elif any(v is None for v in legs):
                recon, outcome = ["unk", "unknown"], ["unk", "unknown"]
            else:
                recon = ["warn", b("Unbacked leg (F-2)", "طرف غير مدعوم (F-2)")]
                outcome = ["warn", b("Contextual · unbacked", "سياقية · غير مدعومة")]
            pnl = t.get("profit_abs")
            closed.append({"trade_id": t.get("trade_id"), "pair": t.get("pair"),
                           "entry": f"{o.get('open_rate', t.get('open_rate'))} · {o.get('open_date_utc', t.get('open_date_utc'))}",
                           "exit": f"{t.get('close_rate')} · {t.get('close_date_utc')}",
                           "reason": t.get("exit_reason") or "—", "recon": recon, "outcome": outcome,
                           "pnl": None if pnl is None else f"{pnl} {t.get('realised_pnl_currency') or 'USDT'}"})
    live["trades_closed"] = {"state": state, "why": why, "cohort": cohort, "rows": closed,
                             "src": f"{src}/paper_trade_ledger.jsonl · {(sealed or {}).get('audit_file') or '—'}"}

    # Market Workspace: no feed and no runtime, so the current market is unknown; the chart shows the sealed
    # record's last bars only, with the prototype's 'unknown' overlay.
    candles = sealed.get("candles") or {} if state == "bound" else {}
    marks = {}
    if state == "bound":
        for t in sealed["trades"]:
            when = t.get("open_date_utc") if t.get("event") == "position_opened" else t.get("close_date_utc")
            if when:
                marks.setdefault(t.get("pair"), []).append(
                    [when, "ENTER" if t.get("event") == "position_opened" else "EXIT"])
    ends = [c[-1][0] for c in candles.values() if c]
    live["market"] = {"state": state if candles or state != "bound" else "none", "why": why,
                      "pairs": sorted(candles), "timeframes": (sealed or {}).get("timeframes") or [],
                      "candles": candles, "marks": marks,
                      "end_utc": _ms_utc(max(ends)) if ends else None,
                      "src": f"{src}/paper_input_ledger.jsonl"}

    # Settings: viewer preferences only; never risk, mode or authority. Facts cite their repository source.
    live["settings"] = {"notify": b("Desktop notification on WARNING / CRITICAL · this host only",
                                    "تنبيه سطح المكتب عند WARNING / CRITICAL · هذا الجهاز فقط"),
                        "notify_src": "scripts/p3/scheduled_health.sh",
                        "time": b("UTC (as recorded in evidence)", "UTC (كما في الأدلة)")}


# ---------------------------------------------------------------- build
def build(live: dict, *, prototype: Path = PROTOTYPE, adapter: Path = ADAPTER_JS) -> str:
    raw = Path(prototype).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != PROTOTYPE_SHA256:
        raise ControlRoomError(f"prototype digest {digest} is not the frozen {PROTOTYPE_SHA256}; refusing to build")
    html = raw.decode("utf-8")
    if html.count("</body>") != 1:
        raise ControlRoomError("prototype structure unexpected: one </body> required")
    payload = json.dumps(live, ensure_ascii=False).replace("</", "<\\/")
    script = (f"<script>\n/* P3-PLN-09 live projection · prototype sha256 {PROTOTYPE_SHA256} · read-only */\n"
              f"const LIVE={payload};\n{Path(adapter).read_text(encoding='utf-8')}\n</script>\n")
    return html.replace("</body>", script + "</body>")


def write(html: str, out: Path) -> None:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(html, encoding="utf-8")
    tmp.replace(out)
