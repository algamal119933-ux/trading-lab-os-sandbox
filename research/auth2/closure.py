#!/usr/bin/env python3
"""The AUTH-2 closure record and its terminal ledger records (FUNNEL_LAW_2.md §DAG_OPERATIONS).

    python research/auth2/closure.py --results DIR --out CLOSURE.json [--append-ledger] [--stop-program]

Reads every node result record downloaded from the program's workflow runs,
refuses unless the frozen DAG has nothing left to run (run_node.eligible), and
writes one closure record: each node's terminal state, each family's terminal,
the Holm table, the lifetime disclosure, the engine invocations used and, only
when two or more families SURVIVED, a DIAGNOSTIC-ONLY inverse-volatility
combination of the survivors' primary engine return series (0 engine
invocations; never evidence of allocation edge). With --append-ledger it
appends one terminal record per trial ID, mapped exactly as the law states.

Every terminal is accepted as it falls, including zero survivors. Nothing here
re-runs, re-scores or re-thresholds anything.

PAPER / RESEARCH ONLY.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
if str(HERE.parent) not in sys.path:
    sys.path.insert(0, str(HERE.parent))

from auth2 import families as F  # noqa: E402
from auth2 import run_node as RN  # noqa: E402
from auth2 import stats as ST  # noqa: E402

NOT_RUN = "NOT_RUN"
LIFETIME = "TLOS strategy configurations tested: 19 before AUTH-2 + 16 = 35"


def family_terminal(fam: str, results: dict[str, dict]) -> tuple[str, str | None]:
    """(the family's terminal under the law, the node it ended at) from its node records."""
    st = {k: v.get("terminal_state") for k, v in results.items()}
    if st.get("D0") != RN.PASS:
        return ("INVALID_RUN" if st.get("D0") == RN.INVALID else "STOP_PROGRAM"), "D0"
    if results["D0"].get("data_limited", {}).get(fam):
        return "DATA_LIMITED", "D0"
    chain = [(f"CAL-{fam}", {RN.PASS: None}), (f"PC-{fam}", {"SURVIVED": None, "NOT_SURVIVED": "INCONCLUSIVE_UNDERPOWERED"}),
             (f"N-{fam}", {"REJECTED": None, "NOT_REJECTED": "LAW_INVALID"}), (fam, {"PRE_HOLM_PASS": None})]
    for node, law in chain:
        t = st.get(node)
        if t is None:
            return "STOP_PROGRAM", node
        if t not in law:
            return t, node  # CAL: LAW_INVALID | INCONCLUSIVE_UNDERPOWERED; Ax: REJECTED | INCONCLUSIVE; INVALID_RUN
        if law[t] is not None:
            return law[t], node
    if "HOLM" not in st:
        return "STOP_PROGRAM", "HOLM"
    if not results["HOLM"]["holm_pass"].get(fam):
        return "REJECTED", "HOLM"  # Holm not passed
    t = st.get(f"SC-{fam}")
    return (t or "STOP_PROGRAM"), f"SC-{fam}"  # SURVIVED | REJECTED | INVALID_RUN


def ledger_state(node: str, results: dict[str, dict], fams: dict[str, tuple[str, str | None]],
                 stopped: bool) -> tuple[str, str]:
    """(trial_record state, outcome terminal) for the trial ID that ``node`` names."""
    kind = RN.NODES[node]["kind"]
    if kind == "SCIENTIFIC":
        t, at = fams[node]
        if t == "INVALID_RUN" and at in (node, f"SC-{node}"):
            return "FAILED", t
        if t in ("SURVIVED", "REJECTED") and at not in ("D0",):
            return t, t
        if t == "INCONCLUSIVE":
            return "COMPLETED", t
        return "ABORTED", f"{NOT_RUN}: {t}"
    rec = results.get(node)
    if rec is None:
        return "ABORTED", NOT_RUN + (": STOP_PROGRAM" if stopped else "")
    t = rec["terminal_state"]
    return ("FAILED", t) if t == RN.INVALID else ("COMPLETED", t)


def combination(results: dict[str, dict], survivors: list[str], repo: Path) -> dict | None:
    """DIAGNOSTIC ONLY: inverse-volatility weights on the survivors' primary engine series, aligned on their
    common final days (every scored window ends 2025-01-01)."""
    if len(survivors) < 2:
        return None
    series = {f: np.asarray(results[f]["engine_runs"]["primary"]["returns"], dtype=float) for f in survivors}
    n = min(len(s) for s in series.values())
    mat = np.column_stack([series[f][-n:] for f in survivors])
    vol = mat.std(axis=0, ddof=1)
    w = (1.0 / vol) / (1.0 / vol).sum()
    combo = mat @ w
    return {"status": "DIAGNOSTIC_ONLY", "engine_invocations": 0, "families": survivors,
            "weights": dict(zip(survivors, w.tolist())), "days": int(n), "sharpe": ST.sharpe(combo),
            "total_return": ST.total_return(combo), "max_drawdown": ST.max_drawdown(combo),
            "note": "historical; not allocation evidence (allocation evidence is prospective paper or a separate "
                    "Owner program)"}


def closure(results: dict[str, dict], repo: Path, stop_program: bool = False) -> dict:
    """``stop_program``: a node ended INVALID_RUN and its one technical retry is spent (the dispatch guard's
    ATTEMPTS record shows it), so the program stops with every unreached node NOT_RUN."""
    nxt = RN.eligible(results)
    if stop_program and not nxt["retry"]:
        RN.refuse("STOP_PROGRAM needs a node whose last result is INVALID_RUN")
    if not stop_program and (nxt["next"] or nxt["retry"]):
        RN.refuse(f"the DAG is not exhausted: next {nxt['next']}, retry {nxt['retry']}")
    shas = {r.get("program_sha256") for r in results.values()}
    if len(shas) != 1:
        RN.refuse("result records come from more than one program sha256")
    fams = {f: family_terminal(f, results) for f in F.FAMILIES}
    survivors = [f for f, (t, _) in fams.items() if t == "SURVIVED"]
    trials = {}
    for node in RN.NODES:
        if RN.NODES[node]["kind"] == "SECONDARY_CONFIRM":
            continue  # part of the family's scientific trial
        state, outcome = ledger_state(node, results, fams, stop_program)
        trials[f"TRIAL-AUTH2-{node}"] = {"node": node, "state": state, "terminal": outcome}
    invocations = sum(int(r.get("engine_invocations", 0)) for r in results.values())
    return {
        "program_id": RN.PROGRAM_ID, "program_sha256": shas.pop(),
        "stop_program": stop_program,
        "nodes": {k: v.get("terminal_state") for k, v in sorted(results.items())},
        "families": {f: {"terminal": t, "at": at} for f, (t, at) in fams.items()},
        "survivors": survivors, "zero_survivors": not survivors,
        "holm": results.get("HOLM", {}).get("holm"),
        "trials": trials, "engine_invocations_used": invocations,
        "lifetime_disclosure": LIFETIME,
        "diagnostic_combination": combination(results, survivors, repo),
        "real_money_authorized": False, "dry_run": True,
        "terminal": "CLOSURE_RECORD",
    }


def append_ledger(rec: dict, repo: Path) -> list[int]:
    from trial_ledger import TrialLedger

    led = TrialLedger(repo / RN.LEDGER_REL)
    seqs = []
    for trial, t in rec["trials"].items():
        pre = led.preregistration_for(trial)
        if pre is None:
            RN.refuse(f"{trial} has no PREREGISTERED record")
        if [r for r in led.records_for(trial_id=trial) if r.payload["state"] != "PREREGISTERED"]:
            RN.refuse(f"{trial} already has a terminal record")
        payload = {k: v for k, v in pre.payload.items() if k != "notes"}
        payload["state"] = t["state"]
        payload["outcome"] = {"reason": f"AUTH-2 closure: {t['node']} terminal {t['terminal']}",
                              "terminal": t["terminal"], "program_sha256": rec["program_sha256"]}
        seqs.append(led.append(payload).seq)
    return seqs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--results", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--repo", default=str(REPO))
    ap.add_argument("--append-ledger", action="store_true")
    ap.add_argument("--stop-program", action="store_true",
                    help="close after an INVALID_RUN whose one technical retry is spent")
    a = ap.parse_args(argv)
    repo = Path(a.repo).resolve()
    rec = closure(RN.scan_results(Path(a.results)), repo, a.stop_program)
    Path(a.out).write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n")
    if a.append_ledger:
        rec["ledger_seqs"] = append_ledger(rec, repo)
    print(json.dumps({k: rec[k] for k in ("families", "survivors", "engine_invocations_used")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
