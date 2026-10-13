#!/usr/bin/env python3
"""AUTH-2 governance closure proposal: the evidence snapshot, the proposed record, and the trial-ledger check.

    python3 closure_proposal.py collect    --repo REPO --slug OWNER/NAME --out evidence.json
    python3 closure_proposal.py build      --repo REPO --evidence evidence.json --out-dir DIR
    python3 closure_proposal.py verify     --repo REPO --evidence evidence.json --out-dir DIR
    python3 closure_proposal.py check-live --repo REPO --slug OWNER/NAME --evidence evidence.json

REPO is a checkout of main at the commit the evidence names (8013e216 when this was written).

collect   reads the GitHub Actions API (repository endpoints only, through `gh api`) and REPO, and writes
          the evidence snapshot. Billed minutes come from the repository's own dispatch_guard.billed_minutes
          and guard records from auth2_operator's annotation decoder, so the figures are the ones AUTH-2 counts.
build     is deterministic: from the evidence file and REPO only, it writes the proposed governance closure
          record, the trial-ledger option check, and SHA256SUMS into DIR. It refuses if REPO no longer matches
          the evidence.
verify    builds again into a temporary directory and requires every output to be byte-identical to DIR,
          and the trial ledger and the worktree of REPO to be unchanged before and after.
check-live re-reads the Actions API and reports any difference from the evidence snapshot (a new AUTH-2
          run, a changed conclusion or billed minute).

Nothing here writes to REPO, GitHub or the trial ledger: the ledger check appends to a temporary copy.

PAPER / RESEARCH ONLY.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

PROGRAM_ID = "AUTH-2-DISCOVERY-QUALIFICATION-1"
CHARTER = f"charters/programs/{PROGRAM_ID}.json"
LAW = "research/auth2/FUNNEL_LAW_2.md"
LEDGER = "research/records/trial_ledger.jsonl"
PINNED = ("research/auth2/closure.py", "research/auth2/dispatch_guard.py", "research/auth2/run_node.py",
          ".github/gates/auth2_operator.py", ".github/workflows/auth2.yml")
NODE_WF, GUARD_WF, CLOSURE_WF = "auth2.yml", "auth2-guard.yml", "auth2-closure.yml"
OUTPUTS = ("governance_closure.proposed.json", "trial_ledger_option.check.json")


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def dump(obj) -> bytes:
    return (json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False) + "\n").encode()


def modules(repo: Path):
    for p in (repo / "research", repo / ".github" / "gates"):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    from auth2 import closure as C  # noqa: E402
    from auth2 import dispatch_guard as DG  # noqa: E402
    from auth2 import run_node as RN  # noqa: E402
    import auth2_operator as OP  # noqa: E402
    from trial_ledger import TrialLedger  # noqa: E402
    return C, DG, RN, OP, TrialLedger


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout.strip()


# -- collect (live, read-only) ----------------------------------------------------------------------

def repo_state(repo: Path) -> dict:
    C, DG, RN, OP, TrialLedger = modules(repo)
    led = TrialLedger(repo / LEDGER)
    recs = led.records()
    auth2 = {r.payload["trial_id"]: {"seq": r.seq, "recorded_utc": r.recorded_utc, "state": r.payload["state"],
                                     "purpose": r.payload["purpose"]}
             for r in recs if r.payload["trial_id"].startswith("TRIAL-AUTH2-")}
    preregs = {p.relative_to(repo).as_posix(): sha256_file(p) for p in sorted((repo / "research/auth2/prereg").glob("*.json"))}
    return {
        "head": git(repo, "rev-parse", "HEAD"),
        "files_sha256": {rel: sha256_file(repo / rel) for rel in (CHARTER, LAW, LEDGER, *PINNED)},
        "preregs_sha256": preregs,
        "trial_ledger": {"records": len(recs), "tip_digest": recs[-1].digest, "verify": led.verify(),
                         "auth2": auth2},
    }


def runs_of(DG, slug: str, wf: str) -> list[dict]:
    out, page = [], 1
    while True:
        got = DG._api(f"/repos/{slug}/actions/workflows/{wf}/runs?per_page=100&page={page}")
        batch = got.get("workflow_runs", [])
        out += batch
        if len(batch) < 100:
            return out
        page += 1


def collect(repo: Path, slug: str) -> dict:
    C, DG, RN, OP, TrialLedger = modules(repo)
    timeouts = {NODE_WF: None, GUARD_WF: OP.GUARD_TIMEOUT, CLOSURE_WF: OP.CLOSURE_TIMEOUT}
    runs = []
    for wf in (NODE_WF, GUARD_WF, CLOSURE_WF):
        for r in runs_of(DG, slug, wf):
            title = r.get("display_title") or ""
            timeout = timeouts[wf]
            m = DG.RUN_NAME.match(title)
            if wf == NODE_WF:
                timeout = DG.node_plan(m["node"], int(m["part"]))["timeout_minutes"]
            jobs = DG._api(f"/repos/{slug}/actions/runs/{r['id']}/jobs?per_page=100&filter=all").get("jobs", [])
            entry = {
                "workflow": wf, "run_id": r["id"], "title": title, "event": r.get("event"),
                "head_branch": r.get("head_branch"), "head_sha": r.get("head_sha"), "run_attempt": r.get("run_attempt"),
                "status": r.get("status"), "conclusion": r.get("conclusion"), "created_at": r.get("created_at"),
                "timeout_minutes": timeout,
                "jobs": [{"name": j.get("name"), "run_attempt": j.get("run_attempt"), "status": j.get("status"),
                          "conclusion": j.get("conclusion"), "started_at": j.get("started_at"),
                          "completed_at": j.get("completed_at"), "billed_minutes": DG.billed_minutes(j, timeout),
                          "steps": [{"number": s.get("number"), "name": s.get("name"), "conclusion": s.get("conclusion"),
                                     "started_at": s.get("started_at"), "completed_at": s.get("completed_at")}
                                    for s in j.get("steps") or []]}
                         for j in jobs],
            }
            if wf == GUARD_WF:
                _run, notes = OP.run_annotations(slug, r["id"])
                got = OP.annotated_records(notes)
                if isinstance(got, Exception):
                    entry["guard_records"] = f"unreadable: {got}"
                else:
                    entry["guard_records"] = []
                    for raw in got:
                        g = json.loads(raw)
                        oe = ((g.get("billing") or {}).get("owner_evidence") or {})
                        entry["guard_records"].append({
                            k: g.get(k) for k in ("decision", "reasons", "node", "part", "mode", "checked_utc", "sha",
                                                  "remaining_included_minutes", "a_m", "r_m", "minutes_ledger",
                                                  "aux_minutes_ledger", "total_minutes_ledger")
                        } | {"owner_evidence_digest": oe.get("evidence_digest") if isinstance(oe, dict) else None})
            runs.append(entry)
    runs.sort(key=lambda e: (e["created_at"], e["run_id"]))
    return {"schema": "auth2-closure-evidence/1", "repository": slug,
            "collected_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "repo": repo_state(repo), "runs": runs}


# -- build (deterministic) --------------------------------------------------------------------------

LEDGER_MAPPING = {
    # FUNNEL_LAW_2.md §DAG_OPERATIONS, LEDGER, for a trial whose node was never reached or never produced a result
    "DATA_LOCK": ("NONE", "D0 maps to COMPLETED with its terminal state, FAILED on INVALID_RUN, or ABORTED NOT_RUN if "
                          "never reached; D0 has no result, no INVALID_RUN and was reached twice"),
    "UNREACHED": ("YES", "ABORTED NOT_RUN if never reached"),
    "SCIENTIFIC": ("PARTIAL", "the law lists NOT_RUN reasons DATA_LIMITED, LAW_INVALID and INCONCLUSIVE_UNDERPOWERED; "
                              "STOP_PROGRAM comes only from the pinned closure.py mapping and the charter stop rule"),
}


def refusal(fn) -> str:
    try:
        fn()
    except SystemExit as exc:
        return str(exc)
    return "no refusal"


def build(repo: Path, evidence_bytes: bytes) -> dict[str, bytes]:
    C, DG, RN, OP, TrialLedger = modules(repo)
    ev = json.loads(evidence_bytes)
    now = repo_state(repo)
    if now != ev["repo"]:
        bad = sorted(k for k in now if now[k] != ev["repo"].get(k))
        raise SystemExit(f"REFUSED: the repository no longer matches the evidence ({bad})")
    as_of = ev["collected_utc"]
    nodes = [r for r in ev["runs"] if r["workflow"] == NODE_WF]
    guards = [r for r in ev["runs"] if r["workflow"] == GUARD_WF]
    closures = [r for r in ev["runs"] if r["workflow"] == CLOSURE_WF]
    billed = lambda rs: sum(j["billed_minutes"] for r in rs for j in r["jobs"])  # noqa: E731
    node_min, guard_min, closure_min = billed(nodes), billed(guards), billed(closures)

    # the guard's own decision for D0 part 1 over the evidenced node runs (billing set readable, so only the
    # attempt rule can refuse)
    state = {"now": as_of, "self_run_id": None,
             "billing": {"readable": True, "remaining_included_minutes": 10 ** 6, "budget_usd_zero": True},
             "runs": [{"id": r["run_id"], "node": DG.RUN_NAME.match(r["title"])["node"],
                       "part": int(DG.RUN_NAME.match(r["title"])["part"]), "status": r["status"],
                       "conclusion": r["conclusion"], "created_at": r["created_at"],
                       "jobs": [{k: j[k] for k in ("status", "started_at", "completed_at")} for j in r["jobs"]],
                       "guard": {"month": as_of[:7], "a_m": 10 ** 6}} for r in nodes]}
    guard_d0 = DG.decide(state, "D0", 1)
    closure_refusals = {"normal": refusal(lambda: C.closure({}, repo, False)),
                        "stop_program": refusal(lambda: C.closure({}, repo, True))}

    trials_led = ev["repo"]["trial_ledger"]["auth2"]
    kinds = {n: RN.NODES[n]["kind"] for n in RN.NODES}
    trials = {}
    for tid in sorted(trials_led):
        node = tid.removeprefix("TRIAL-AUTH2-")
        kind = kinds[node]
        if kind == "DATA_LOCK":
            st, why = "CLOSED_NOT_EVALUATED", "operational exhaustion: no result after its one technical retry"
        else:
            st, why = "CLOSED_NOT_RUN", "never reached: D0 produced no result"
        trials[tid] = {"node": node, "kind": kind, "preregistered_seq": trials_led[tid]["seq"],
                       "governance_status": st, "reason": why, "trial_ledger_terminal": "none: the record stays open"}

    d0_runs = []
    for r in nodes:
        steps = r["jobs"][0]["steps"] if r["jobs"] else []
        node_step = next((s for s in steps if s["name"].startswith("Run the node")), None)
        d0_runs.append({"run_id": r["run_id"], "conclusion": r["conclusion"], "head_sha": r["head_sha"],
                        "billed_minutes": sum(j["billed_minutes"] for j in r["jobs"]),
                        "node_step": node_step, "result": "none"})
    causes = {38273417548: ("run_node refused in its program check: a one-commit checkout made every PREREGISTERED "
                            "record look older than the program (fixed by PR #63, merged as 8013e216)",
                            "the node step failed within its first second; PR #63 and its tests"),
              38286502721: ("the 150-minute job timeout cancelled the node step while dataset_v3.build fetched the "
                            "archive (27,898 files) one file at a time; the archive cache restore took under one "
                            "second, so no cache was found",
                            "inferred from the step timings and the code path, because job logs are not readable "
                            "(HTTP 403); see d0-run-38286502721-timeout.md")}
    for d in d0_runs:
        d["cause"], d["cause_basis"] = causes.get(d["run_id"], ("see the evidence", "the evidence file"))

    led_anchor = {"path": LEDGER, "sha256": ev["repo"]["files_sha256"][LEDGER],
                  "records": ev["repo"]["trial_ledger"]["records"], "tip_digest": ev["repo"]["trial_ledger"]["tip_digest"],
                  "auth2_preregistered": len(trials_led),
                  "auth2_terminal": sum(1 for t in trials_led.values() if t["state"] != "PREREGISTERED")}
    record = {
        "record_id": "AUTH2-GOVERNANCE-CLOSURE-1", "record_type": "PROGRAM_CLOSURE", "schema_version": 1,
        "status": "PROPOSED: binding only after the Owner merges it",
        "program": {"id": PROGRAM_ID, "charter_path": CHARTER, "charter_sha256": ev["repo"]["files_sha256"][CHARTER],
                    "funnel_law_sha256": ev["repo"]["files_sha256"][LAW], "main_sha": ev["repo"]["head"]},
        "classification": {
            "terminal": "OPERATIONAL_EXHAUSTION", "scientific_outcome": "NONE", "hypotheses_evaluated": 0,
            "node_results": 0, "engine_invocations": 0,
            "statement": "AUTH-2 stopped because its data-lock node D0 ended twice without a result. No hypothesis was "
                         "evaluated, so this closure is evidence neither for nor against A1, A2 or A3.",
            "distinguished_from": {
                "scientific_hypothesis_failure": "a node result that ends a family under the law (REJECTED, "
                                                 "INCONCLUSIVE, LAW_INVALID, INCONCLUSIVE_UNDERPOWERED, DATA_LIMITED). "
                                                 "No node produced a result.",
                "charter_stop_program": "a C1 integrity failure (INVALID_RUN) whose one technical retry is spent. "
                                        "D0 produced no INVALID_RUN, because it never reached a comparison."}},
        "exhausted_node": {"node": "D0", "part": 1, "trial_id": "TRIAL-AUTH2-D0", "max_attempts": DG.MAX_ATTEMPTS,
                           "runs": d0_runs, "guard_decision_now": {
                               "decision": guard_d0["decision"], "reasons": guard_d0["reasons"],
                               "inputs": "the pinned dispatch_guard.decide over the evidenced D0 runs, with billing "
                                         "set readable and ample so that only the attempt and cap rules can refuse"}},
        "why_not_trial_ledger": [
            {"clause": "FUNNEL_LAW_2.md §DAG_OPERATIONS LEDGER", "finding": LEDGER_MAPPING["DATA_LOCK"][1]},
            {"clause": "FUNNEL_LAW_2.md §DAG_OPERATIONS CLOSURE",
             "finding": "the closure record is written by research/auth2/closure.py, which refuses this state",
             "closure_py_refusals": closure_refusals},
            {"clause": "research/auth2/IMPLEMENTATION_NOTES.md, Ledger",
             "finding": "Terminal records are appended at closure only, mapped as §DAG_OPERATIONS states."}],
        "law_gap": "RETRY covers a job that ends without a result, but the pinned closure's STOP_PROGRAM path needs "
                   "an INVALID_RUN result, so a retry spent without a result has no terminal.",
        "trials": trials,
        "trial_ledger_anchor": led_anchor,
        "compute": {"minutes_ledger": node_min + guard_min + closure_min, "node_minutes": node_min,
                    "guard_minutes": guard_min, "closure_minutes": closure_min, "engine_invocations": 0,
                    "caps": {"minutes": DG.CAP_MINUTES, "invocations": DG.CAP_INVOCATIONS},
                    "node_runs": [r["run_id"] for r in nodes],
                    "guard_runs": [{"run_id": r["run_id"], "run_attempt": r["run_attempt"], "jobs": len(r["jobs"]),
                                    "conclusion": r["conclusion"], "billed_minutes": sum(j["billed_minutes"] for j in r["jobs"]),
                                    "decisions": [g["decision"] for g in r["guard_records"]]
                                    if isinstance(r.get("guard_records"), list) else r.get("guard_records")}
                                   for r in guards],
                    "closure_runs": [r["run_id"] for r in closures]},
        "preserved": ["both D0 runs and their billed minutes", "every guard run and its billed minutes",
                      "the 17 preregistrations, unchanged", "the 14 PREREGISTERED trial-ledger records, unchanged",
                      "the charter, FUNNEL_LAW_2 and every code pin, unchanged"],
        "effects": ["AUTH-2 is closed: no AUTH-2 node, guard or closure job is dispatched after the Owner merges this",
                    "the 14 trial IDs are never preregistered again (the trial ledger refuses a second PREREGISTERED "
                    "record for a trial ID)",
                    "a successor program registers new trial IDs and cites this record by its sha256"],
        "authority": {"owner_decisions": [
            "2026-10-12T22:13:45Z decision card, option A: Close + successor",
            "2026-10-12T22:14:10Z OWNER DECISION: OPTION A, CLOSE + SUCCESSOR, WITH SEPARATE GOVERNANCE AND "
            "ENGINEERING GATES"],
            "merge": "OWNER_MERGE_REQUIRED (CEA-1 §11: no generator exists today, so every CLOSE record is "
                     "OWNER_MERGE_REQUIRED)"},
        "evidence": {"evidence_sha256": hashlib.sha256(evidence_bytes).hexdigest(), "as_of_utc": as_of},
        "dry_run": True, "real_money_authorized": False,
    }

    # the option this proposal rejects: the 14 trial-ledger terminal records, appended to a TEMPORARY copy only
    with tempfile.TemporaryDirectory() as td:
        copy = Path(td) / "trial_ledger.jsonl"
        shutil.copyfile(repo / LEDGER, copy)
        led = TrialLedger(copy)
        rows = {}
        for tid in sorted(trials_led):
            node = tid.removeprefix("TRIAL-AUTH2-")
            kind = kinds[node]
            pre = led.preregistration_for(tid)
            payload = {k: v for k, v in pre.payload.items() if k != "notes"}
            if kind == "DATA_LOCK":
                payload["state"], terminal, mapping = "FAILED", "NO_RESULT_AFTER_RETRY", LEDGER_MAPPING["DATA_LOCK"]
            elif kind == "SCIENTIFIC":
                payload["state"], terminal, mapping = "ABORTED", "NOT_RUN: STOP_PROGRAM", LEDGER_MAPPING["SCIENTIFIC"]
            else:
                payload["state"], terminal, mapping = "ABORTED", "NOT_RUN: STOP_PROGRAM", LEDGER_MAPPING["UNREACHED"]
            payload["outcome"] = {"reason": f"AUTH-2 closure: {node} terminal {terminal}", "terminal": terminal,
                                  "measurement_validity": "NOT_APPLICABLE",
                                  "program_sha256": ev["repo"]["files_sha256"][CHARTER]}
            try:
                led.append(payload, recorded_utc=as_of)
                schema = "PASS"
            except Exception as exc:  # noqa: BLE001
                schema = f"REFUSED: {exc}"
            rows[tid] = {"state": payload["state"], "terminal": terminal, "ledger_schema": schema,
                         "frozen_ledger_mapping": mapping[0], "mapping_note": mapping[1],
                         "produced_by_frozen_closure": "NO: closure.py refuses (see closure_py_refusals)",
                         "payload_sha256": hashlib.sha256(dump(payload)).hexdigest()}
        option = {"option": "trial-ledger terminal records (NOT proposed; shown to prove why)",
                  "appended_to": "a temporary copy of the trial ledger, deleted after this check",
                  "chain_verify_after": led.verify(), "records": rows, "closure_py_refusals": closure_refusals,
                  "verdict": "schema-valid but not producible by the frozen closure, and D0 has no frozen mapping"}

    out = {OUTPUTS[0]: dump(record), OUTPUTS[1]: dump(option)}
    sums = "".join(f"{hashlib.sha256(b).hexdigest()}  {name}\n" for name, b in sorted(out.items()))
    out["SHA256SUMS"] = (f"{hashlib.sha256(evidence_bytes).hexdigest()}  evidence.json\n" + sums).encode()
    return out


def cmd_build(repo: Path, evidence: Path, out_dir: Path) -> int:
    out = build(repo, evidence.read_bytes())
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, b in out.items():
        (out_dir / name).write_bytes(b)
        print(f"{hashlib.sha256(b).hexdigest()}  {name}")
    return 0


def cmd_verify(repo: Path, evidence: Path, out_dir: Path) -> int:
    before = (sha256_file(repo / LEDGER), git(repo, "status", "--porcelain"))
    with tempfile.TemporaryDirectory() as td:
        fresh = build(repo, evidence.read_bytes())
        for name, b in fresh.items():
            (Path(td) / name).write_bytes(b)
    after = (sha256_file(repo / LEDGER), git(repo, "status", "--porcelain"))
    problems = [f"{n} differs from the rebuild" for n, b in fresh.items()
                if not (out_dir / n).exists() or (out_dir / n).read_bytes() != b]
    if before != after:
        problems.append("the repository's trial ledger or worktree changed during the build")
    print("CLOSURE_PROPOSAL_VERIFY =", "PASS" if not problems else "FAIL")
    for p in problems:
        print(" -", p)
    print(f"trial ledger sha256 {after[0]} (unchanged: {before[0] == after[0]}); worktree clean: {after[1] == ''}")
    return 0 if not problems else 1


def cmd_check_live(repo: Path, slug: str, evidence: Path) -> int:
    old = json.loads(evidence.read_bytes())
    new = collect(repo, slug)
    key = lambda e: {r["run_id"]: (r["workflow"], r["status"], r["conclusion"],  # noqa: E731
                                   [j["billed_minutes"] for j in r["jobs"]]) for r in e["runs"]}
    a, b = key(old), key(new)
    diffs = [f"run {i}: snapshot {a.get(i)} live {b.get(i)}" for i in sorted(set(a) | set(b)) if a.get(i) != b.get(i)]
    if old["repo"] != new["repo"]:
        diffs.append("the repository state differs from the snapshot")
    print("EVIDENCE_MATCHES_LIVE =", "YES" if not diffs else "NO")
    for d in diffs:
        print(" -", d)
    return 0 if not diffs else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("collect", "build", "verify", "check-live"):
        s = sub.add_parser(name)
        s.add_argument("--repo", required=True)
        if name in ("collect", "check-live"):
            s.add_argument("--slug", required=True)
        if name == "collect":
            s.add_argument("--out", required=True)
        else:
            s.add_argument("--evidence", required=True)
        if name in ("build", "verify"):
            s.add_argument("--out-dir", required=True)
    a = ap.parse_args(argv)
    repo = Path(a.repo).resolve()
    if a.cmd == "collect":
        Path(a.out).write_bytes(dump(collect(repo, a.slug)))
        print(f"{sha256_file(Path(a.out))}  {a.out}")
        return 0
    if a.cmd == "build":
        return cmd_build(repo, Path(a.evidence), Path(a.out_dir))
    if a.cmd == "verify":
        return cmd_verify(repo, Path(a.evidence), Path(a.out_dir))
    return cmd_check_live(repo, a.slug, Path(a.evidence))


if __name__ == "__main__":
    sys.exit(main())
