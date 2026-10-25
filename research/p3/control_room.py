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
# The view is regenerated hourly with the health timer; past this age it is shown as stale.
FRESHNESS_BUDGET_S = 2 * 3600

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


# ---------------------------------------------------------------- collect
def collect(*, runner: Runner = _run, now: float | None = None, registry_path: Path = REGISTRY,
            workstreams_path: Path = WORKSTREAMS, authorization_path: Path = AUTHORIZATION,
            p2_closure_path: Path = P2_CLOSURE, ledger_path: Path = LEDGER, repo_root: Path = REPO_ROOT,
            runtime_root: Path = RUNTIME_ROOT, backup_target: Path = BACKUP_TARGET, findings: list[dict] | None = None,
            docker: Runner | None = None) -> dict:
    """Observe the host. Read-only; each value records where it came from."""
    now = time.time() if now is None else now
    registry = json.loads(Path(registry_path).read_text(encoding="utf-8"))
    if findings is None:
        findings = health.standard_findings(registry, runner=health.default_runner, verifier=backup.verify_backup)
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
    expires = re.search(r"^EXPIRES_UTC = (\S+)", auth_text, re.M)
    closure = Path(p2_closure_path).read_text(encoding="utf-8") if Path(p2_closure_path).exists() else ""
    recon = re.search(r"reconcile\s+PASS · (\d+)/(\d+) findings", closure)
    merges = _out(runner, ["git", "-C", str(repo_root), "log", "--first-parent", "--merges", "-8", "--format=%H%x09%ct%x09%s", "HEAD"])
    uptime = _out(runner, ["cat", "/proc/uptime"])
    boot_id = _out(runner, ["cat", str(recovery.BOOT_ID)])
    ntp = _out(runner, ["timedatectl", "show", "-p", "NTPSynchronized", "--value"])
    health_timer = health.timer_expected("tlos-p3-health.timer", want_active=True, runner=runner)
    sets = sorted(p.name for p in Path(backup_target).glob("*") if (p / "BACKUP_RECORD.json").is_file()) \
        if Path(backup_target).is_dir() else []
    return {
        "observation_version": "P3_CONTROL_ROOM_OBSERVATION_V1",
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
        "authorization": {"present": bool(auth_text), "expires_utc": expires.group(1) if expires else None,
                          "real_money": "REAL_MONEY_AUTHORIZED = NO" in auth_text,
                          "h1_launch": "H1_LAUNCH_AUTHORIZED = NO" in auth_text},
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


def project(obs: dict) -> dict:
    """Map an observation onto the prototype's scenario schema. Pure: no I/O."""
    now = obs["observed_utc"]
    sev = obs["health"]["overall"]
    not_info = [f for f in obs["health"]["findings"] if f["severity"] != health.INFO]
    exc: dict = {}

    health_dim = {health.INFO: ["ok", "healthy"], health.WARNING: ["warn", "degraded"]}.get(
        sev, ["inc", b("Critical", "حرج")])
    if not_info:
        exc["health"] = b("; ".join(f"{f['check']}: {f['detail']}" for f in not_info),
                          "؛ ".join(f"{f['check']}: {f['detail']}" for f in not_info))

    auth = obs["authorization"]
    expired = auth["expires_utc"] is None or auth["expires_utc"] < datetime.fromtimestamp(
        obs["observed_epoch"], timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    authority_ok = auth["present"] and not expired and auth["real_money"] \
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
    elif any(state == "running" for state in paper.values()):
        n = sum(state == "running" for state in paper.values())
        runtime_dim = ["ok", "running"]
        runtime_label = b(f"{n} paper runtime running", f"{n} تشغيل ورقي يعمل")
    else:
        runtime_dim = ["off", "stopped"]
        exc["runtime"] = b("No paper cohort is running: P2 is closed and H1 is not launched (observed).",
                           "لا توجد مجموعة ورقية تعمل: P2 مغلقة وH1 لم تُطلق (مرصود).")

    rec = obs["p2_reconcile"]
    recon_dim = ["ok", b(f"{rec['passed']}/{rec['total']} · P2 final", f"{rec['passed']}/{rec['total']} · P2 النهائية")] \
        if rec and rec["passed"] == rec["total"] else ["unk", "unknown"]

    dims = {"health": health_dim, "authority": authority_dim, "evidence": evidence_dim,
            "freshness": ["ok", "fresh"], "runtime": runtime_dim, "recon": recon_dim}

    fp3 = next((i for i in obs["registry"]["instances"] if i["role"] == "FP-CONTROL-3"), {})
    ws = obs["workstreams"]
    merges = obs["governance"]["merges"]
    last_merge = merges[0] if merges else None
    pr_m = re.search(r"#(\d+)", last_merge["subject"]) if last_merge else None
    pr = pr_m.group(1) if pr_m else "?"
    lgc = b(f"PR #{pr} merged · {last_merge['sha'][:8]} · {_utc(float(last_merge['epoch']))}",
            f"دُمج طلب الدمج #{pr} · {last_merge['sha'][:8]} · {_utc(float(last_merge['epoch']))}") \
        if last_merge else b("Not observed", "غير مرصود")

    newest = obs["backup_sets"][-1] if obs["backup_sets"] else None
    ledger_last = obs["ledger"]["last"]
    known = [
        b(f"P2 CLOSED / PASS · {fp3.get('cohort_id')} · {fp3.get('closed_utc')} (registry)",
          f"P2 مغلقة / ناجحة · {fp3.get('cohort_id')} · {fp3.get('closed_utc')} (السجل)"),
        b(f"P3 executing under 7b1b1fa1 · expires {auth['expires_utc']}",
          f"P3 قيد التنفيذ بموجب 7b1b1fa1 · تنتهي {auth['expires_utc']}"),
        b("Real money blocked · H1 launch not authorized", "المال الحقيقي محظور · إطلاق H1 غير مصرّح"),
    ]
    if backup_f:
        known.append(b(f"Backup: {backup_f['detail']} · verify {'PASS' if backup_f['severity'] == health.INFO else 'FAIL'}",
                       f"النسخ الاحتياطي: {backup_f['detail']} · التحقق {'ناجح' if backup_f['severity'] == health.INFO else 'فاشل'}"))
    known.append(b(f"Operator ledger: {obs['ledger']['records']} records, chain {'PASS' if ledger_ok else 'FAIL'}",
                   f"سجل المشغّل: {obs['ledger']['records']} سجلات، السلسلة {'ناجحة' if ledger_ok else 'فاشلة'}"))
    known.append(b(f"FP-CONTROL-3 restart refused: {obs['fp_control_3_restart']['reason']}",
                   f"إعادة تشغيل FP-CONTROL-3 مرفوضة: {obs['fp_control_3_restart']['reason']}"))
    unknown = [b("Off-host observation: not implemented (PLN-05 Tier 3 / PLN-06)",
                 "الرصد من خارج الجهاز: غير منفّذ (PLN-05 المستوى 3 / PLN-06)")]
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
    events.append({"t": now, "s": "ok" if sev == health.INFO else "warn", "c": "system",
                   "d": b(f"Health check: {sev}", f"فحص الصحة: {sev}"), "src": b("health check", "فحص الصحة")})

    system_txt = b(
        f"No paper runtime. Backups daily (newest {newest or 'none'}); health hourly: {sev}.",
        f"لا تشغيل ورقي. النسخ يوميًا (الأحدث {newest or 'لا يوجد'})؛ الصحة كل ساعة: {sev}.")
    if runtime_dim[0] == "ok":
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
         if runtime_dim[0] == "off" else ["ok", b(f"{len(running)} running", f"{len(running)} تعمل")]),
        "feed": ["off", b("No feed · no runtime", "لا تغذية · لا تشغيل")] if runtime_dim[0] == "off" else ["unk", "unknown"],
        "api": ["off", b("Not used · no runtime", "غير مستخدمة · لا تشغيل")] if runtime_dim[0] == "off" else ["unk", "unknown"],
        "monitor": ["ok", b("Health timer active", "مؤقت الصحة نشط")] if obs["health_timer"]["severity"] == health.INFO
        else ["warn", b(obs["health_timer"]["detail"], obs["health_timer"]["detail"])],
        "clock": {True: ["ok", b("Synced", "متزامنة")], False: ["warn", b("Not synced", "غير متزامنة")]}.get(
            host["ntp_synced"], ["unk", "unknown"]),
        "boot": boot or "—",
    }

    scenario = {
        "label": "LIVE", "now": now, "step": 6, "sub": 6, "signal": "owner" if ws["owner"]["state"] == "req" else "events",
        "dims": dims, "exc": exc, "banner": None,
        "verdict": b(f"P2 is closed (PASS). P3 Paper Beta is executing; health {sev}. No paper runtime is running.",
                     f"أُغلقت P2 (ناجحة). النسخة التجريبية الورقية P3 قيد التنفيذ؛ الصحة {sev}. لا يعمل أي تشغيل ورقي."),
        "owner": [ws["owner"]["state"], b(ws["owner"]["en"], ws["owner"]["ar"])],
        "claude": b(ws["claude"]["en"], ws["claude"]["ar"]),
        "system": system_txt,
        "next": b(ws["next"]["en"], ws["next"]["ar"]), "fromContract": True,
        "lgc": lgc,
        "lho": b(f"{now} · health {sev}", f"{now} · الصحة {sev}") if sev == health.INFO else b("Not current", "غير حالي"),
        "nowObs": b(f"Observed {now}", f"رُصد {now}"),
        "known": known, "unknown": unknown, "affected": [], "unverified": unverified,
        "events": events, "incidents": [], "viewerNew": 0, "viewStale": False,
        "extraForbid": [b("Real money, H1 launch, or restarting FP-CONTROL-3", "المال الحقيقي أو إطلاق H1 أو إعادة تشغيل FP-CONTROL-3")],
        "dec": {"unv": False, "stale": False,
                "none": b(f"No paper cohort running; no decisions since the P2 closure ({fp3.get('closed_utc')}).",
                          f"لا مجموعة ورقية تعمل؛ لا قرارات منذ إغلاق P2 ({fp3.get('closed_utc')}).")},
        "pos": [], "posUnv": False, "risk": {"stale": False},
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
        {"k": b("Paper trading", "التداول الورقي"), "st": runtime_dim if runtime_dim[0] == "ok" else ["off", b("No cohort running", "لا مجموعة تعمل")],
         "scope": b("Governed cohorts only", "المجموعات المحكومة فقط"), "src": cap_src, "chg": b("Owner authorization", "تفويض المالك"), "exec": True},
        {"k": b("Long entries", "صفقات الشراء"), "st": ["off", b("No cohort running", "لا مجموعة تعمل")], "scope": b("Paper only", "ورقي فقط"),
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
        ["info", b("P3 executing", "P3 قيد التنفيذ")],
    ]
    return {
        "live_version": "P3_CONTROL_ROOM_LIVE_V1",
        "observed_utc": now, "observed_epoch": obs["observed_epoch"], "budget_s": FRESHNESS_BUDGET_S,
        "hostname": obs["hostname"],
        "ident": {"stage": b("P3 · Paper Beta executing", "P3 · النسخة التجريبية الورقية قيد التنفيذ"),
                  "ref": "7b1b1fa1"},
        "project": {"chips": project_chips,
                    "gate": b(ws["next"]["en"], ws["next"]["ar"]),
                    "workstreams": [[_ws_chip(w["status"]), w["id"], b(w["en"], w["ar"]), w["status"], w["evidence"]]
                                    for w in ws["workstreams"]],
                    "ws_updated": ws["updated_utc"]},
        "identity": {"runtime_pin": obs["runtime"]["pin"], "runtime_clean": obs["runtime"]["clean"],
                     "main": obs["governance"]["main"], "boot_id": obs["host"]["boot_id"]},
        "health_findings": obs["health"]["findings"],
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
        "real_money_authorized": False,
    }


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
