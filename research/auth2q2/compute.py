#!/usr/bin/env python3
"""The successor's guarded compute proof (Owner decision OD-S7; review section 5).

    python -m auth2q2.compute report [--out FILE]

AUTH-2's proof, 2 x 1,980 = 3,960 <= 4,000 (FUNNEL_LAW_2.md §COMPUTE_CAP_PROOF), counted node jobs only and
assumed a job never bills past its timeout. Counting every job at timeout + 1 (run 38286502721 billed 151
minutes for a 150-minute timeout; readiness test RT-10 measures the rounding) and a guard run before every
dispatch, its frozen plan's worst case is 4,448 minutes (``worst_case``). So the successor keeps the 4,000 cap
and guards it instead of claiming a worst case under it:

  R1 dispatch  a node part runs only if
                   ledger + (g + 1) + (t + 1) + retry + RESERVE <= 4,000
               where the ledger holds every program job so far (guard, node and closure jobs, each at its billed
               minutes; a job still running at its timeout + 1), g + 1 is this guard run, t + 1 the node job,
               retry = (g + 1) + (t + 1) when this is the part's first science attempt (AUTH-2's "room for its
               retry"), and RESERVE = (g + 1) + (c + 1) = 32 is the closure's guard and the closure job.
  R2 close     a guard that cannot admit the next part under R1 decides CLOSE, whatever else holds: that part
               and every part not yet terminal end TECHNICAL_EXHAUSTION with reason CAP_REACHED, and this guard
               run is the closure's guard, so the closure runs on the reserved minutes.
  R3 refusals  a guard refuses for another reason (billing evidence, serial) only where R1 would have admitted
               the part, so its own g + 1 minutes come out of what the part needed, never out of the reserve:
               after every guard run that does not close, ledger + RESERVE <= 4,000 still holds.

``simulate`` drives the frozen DAG's node parts (a maximal-work model: every chain node continues, every family
reaches HOLM and SC) through any sequence of run classes and billed minutes, and checks that the ledger never
passes the cap, that every part ends (RESULT, TECHNICAL_EXHAUSTION or NOT_RUN behind an exhausted part) and that
the closure runs once, last. What the reserve does not cover is stated, not hidden: the reserve holds one closing
guard and one closure job. A CLOSE decided on a guard run whose Owner billing evidence is invalid cannot dispatch
the closure, and the next guard run then bills up to g + 1 minutes outside the reserve; a failed closure job is
not retried inside it. The successor law states both before the freeze.

The timeouts here are AUTH-2's frozen ones, the only measured plan that exists. The successor's own come from the
readiness measurements (OD-S8: at least twice the slowest measured run) and are frozen only by the Owner's merge.
Nothing here dispatches, reads billing or writes a ledger. PAPER / RESEARCH ONLY.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from auth2q2 import attempts as AT  # noqa: E402

CAP = 4000
GUARD_TIMEOUT = 10
CLOSURE_TIMEOUT = 20
RESERVE = (GUARD_TIMEOUT + 1) + (CLOSURE_TIMEOUT + 1)
AUTH2_LAW_PROOF = 3960
AUTH2_WORST_CASE = 4448
DISPATCH, CLOSE, NO_DISPATCH = "DISPATCH", "CLOSE", "NO_DISPATCH"

# FUNNEL_LAW_2.md §COMPUTE_CAP_PROOF, job plan (estimated minutes per node, all parts together). Used only to
# show the expected use against the cap; no rule here reads them.
LAW_ESTIMATES = {"D0": 45, "CAL-A1": 25, "CAL-A2": 25, "CAL-A3": 25, "PC-A1": 95, "PC-A2": 250, "PC-A3": 25,
                 "N-A1": 95, "N-A2": 250, "N-A3": 25, "A1": 65, "A2": 160, "A3": 15, "HOLM": 2, "SC": 25}
STAGES = (("D0", ("D0",)), ("CAL", ("CAL-A1", "CAL-A2", "CAL-A3")), ("PC", ("PC-A1", "PC-A2", "PC-A3")),
          ("N", ("N-A1", "N-A2", "N-A3")), ("A", ("A1", "A2", "A3")), ("HOLM", ("HOLM",)),
          ("SC", ("SC-A1", "SC-A2", "SC-A3")))
FAMILIES = ("A1", "A2", "A3")


def nodes() -> dict:
    """AUTH-2's frozen node table (research/auth2/run_node.py NODES, read only): timeout and parts per node."""
    from auth2 import run_node as RN  # numpy is imported there; only the plan table is read

    return {n: {"timeout": int(v["timeout_minutes"]), "parts": int(v["parts"])} for n, v in RN.NODES.items()}


def stage_rows(table: dict | None = None) -> list[dict]:
    """The review's worst-case table: per stage, its parts, the sum of its part timeouts and its attempts."""
    table = table or nodes()
    rows = []
    for stage, members in STAGES:
        rows.append({"stage": stage, "parts": sum(table[n]["parts"] for n in members),
                     "timeout": sum(table[n]["timeout"] * table[n]["parts"] for n in members), "attempts": 2})
    rows.append({"stage": "Closure", "parts": 1, "timeout": CLOSURE_TIMEOUT, "attempts": 1})
    return rows


def worst_case(rows: list[dict], guard_timeout: int = GUARD_TIMEOUT) -> int:
    """Every part tried ``attempts`` times, each job billing its timeout + 1, one guard run per dispatch."""
    return sum(r["attempts"] * (r["timeout"] + r["parts"]) + r["parts"] * r["attempts"] * (guard_timeout + 1)
               for r in rows)


def law_proof(table: dict | None = None) -> int:
    """AUTH-2's own proof: 2 x the sum of node-job timeouts (node jobs only, no rounding)."""
    table = table or nodes()
    return 2 * sum(v["timeout"] * v["parts"] for v in table.values())


# -- the guard's arithmetic (R1 to R3) ---------------------------------------------------------------

def need(timeout: int, first_science_attempt: bool, guard_timeout: int = GUARD_TIMEOUT,
         reserve: int = RESERVE) -> dict:
    g, t = guard_timeout + 1, timeout + 1
    retry = g + t if first_science_attempt else 0
    return {"this_guard": g, "node": t, "retry": retry, "reserve": reserve, "total": g + t + retry + reserve}


def decide(ledger: int, part: dict | None, *, cap: int = CAP, guard_timeout: int = GUARD_TIMEOUT,
           reserve: int = RESERVE, refusals: list[str] | None = None) -> dict:
    """One guard decision. ``part`` = {"node", "part", "timeout", "first_science_attempt"} for the next node part
    the DAG allows, or None when nothing is left to run. ``refusals``: reasons other than the cap that stop a
    dispatch (billing, serial, evidence)."""
    refusals = list(refusals or [])
    out = {"ledger": ledger, "cap": cap, "reserve": reserve,
           "spare_after_this_guard": cap - (ledger + guard_timeout + 1 + reserve)}
    if part is None:
        return {**out, "decision": CLOSE, "reason": None, "why": "the DAG has nothing left to run"}
    n = need(part["timeout"], part["first_science_attempt"], guard_timeout, reserve)
    out["need"] = n
    if ledger + n["total"] > cap:
        return {**out, "decision": CLOSE, "reason": AT.CAP_REACHED,
                "why": f"R2: ledger {ledger} + {n['total']} needed by {part['node']} part {part['part']} > {cap}"}
    if refusals:
        return {**out, "decision": NO_DISPATCH, "reason": None, "why": "R3: " + "; ".join(refusals)}
    return {**out, "decision": DISPATCH, "reason": None, "why": f"R1: ledger {ledger} + {n['total']} <= {cap}"}


# -- the maximal-work model of the frozen DAG -------------------------------------------------------

def parts_in_order(table: dict | None = None) -> list[dict]:
    """Every node part in the frozen DAG's order (FUNNEL_LAW_2 §DAG_OPERATIONS EDGES), with its upstream part:
    D0, then each family's chain CAL -> PC -> N -> Ax (split parts in order), HOLM after every family, then
    SC-Ax. A part runs only after its upstream part ended RESULT."""
    table = table or nodes()
    out = [{"node": "D0", "part": 1, "timeout": table["D0"]["timeout"], "after": []}]
    for stage in ("CAL", "PC", "N", ""):
        for f in FAMILIES:
            node = f"{stage}-{f}" if stage else f
            for p in range(1, table[node]["parts"] + 1):
                if p > 1:
                    after = [(node, p - 1)]
                elif stage == "CAL":
                    after = [("D0", 1)]
                else:
                    prev = {"PC": f"CAL-{f}", "N": f"PC-{f}", "": f"N-{f}"}[stage]
                    after = [(prev, table[prev]["parts"])]
                out.append({"node": node, "part": p, "timeout": table[node]["timeout"], "after": after})
    out.append({"node": "HOLM", "part": 1, "timeout": table["HOLM"]["timeout"], "after": [("D0", 1)]})
    for f in FAMILIES:
        out.append({"node": f"SC-{f}", "part": 1, "timeout": table[f"SC-{f}"]["timeout"],
                    "after": [("HOLM", 1), (f, 1)]})
    return out


def simulate(plan: list[dict], outcome, *, guard_minutes=None, refuse=None, cap: int = CAP,
             guard_timeout: int = GUARD_TIMEOUT, closure_minutes: int | None = None) -> dict:
    """Run the guard (``decide`` + attempts.part_state) over ``plan`` until it closes.

    ``outcome(node, part, k)`` -> (class, billed minutes) of the k-th run of that part (class INFRA, SCIENCE or
    RESULT). ``guard_minutes(i)`` -> billed minutes of the i-th guard run (default g + 1). ``refuse(i, ledger)``
    -> reasons other than the cap that stop the i-th guard run (default none). Every run bills what the model
    says, capped at its timeout + 1, as GitHub ends a job at its timeout."""
    gm = guard_minutes or (lambda _i: guard_timeout + 1)
    history: dict[tuple, list[str]] = {(p["node"], p["part"]): [] for p in plan}
    terminal: dict[tuple, str] = {}
    ledger, guards, trace = 0, 0, []
    peak = 0

    def ready(p) -> bool:
        if p["node"] == "HOLM" and any(terminal.get(k) is None for k in history
                                       if k[0] != "HOLM" and not k[0].startswith("SC-")):
            return False  # HOLM joins: every family chain must have ended first
        return all(terminal.get(a) == AT.RESULT for a in p["after"])

    while True:
        # parts whose upstream can no longer end RESULT are NOT_RUN (never reached)
        for p in plan:
            key = (p["node"], p["part"])
            if key not in terminal and any(terminal.get(a) not in (None, AT.RESULT) for a in p["after"]):
                terminal[key] = "NOT_RUN"
        nxt = next((p for p in plan if (p["node"], p["part"]) not in terminal and ready(p)), None)
        guards += 1
        g_bill = min(gm(guards), guard_timeout + 1)
        part = None
        if nxt is not None:
            st = AT.part_state(history[(nxt["node"], nxt["part"])])
            part = {**nxt, "first_science_attempt": st["first_science_attempt"]}
        reasons = refuse(guards, ledger) if refuse else []
        d = decide(ledger, part, cap=cap, guard_timeout=guard_timeout, refusals=reasons)
        ledger += g_bill
        trace.append({"guard": guards, "decision": d["decision"], "reason": d["reason"], "why": d["why"],
                      "ledger_after_guard": ledger})
        if d["decision"] == CLOSE:
            if d["reason"] == AT.CAP_REACHED:
                for p in plan:
                    terminal.setdefault((p["node"], p["part"]), f"{AT.TECHNICAL_EXHAUSTION}:{AT.CAP_REACHED}")
            ledger += min(CLOSURE_TIMEOUT + 1, closure_minutes if closure_minutes is not None
                          else CLOSURE_TIMEOUT + 1)
            peak = max(peak, ledger)
            trace.append({"closure": True, "ledger_after_closure": ledger})
            break
        if d["decision"] == NO_DISPATCH:
            peak = max(peak, ledger)
            continue
        key = (nxt["node"], nxt["part"])
        k = len(history[key]) + 1
        cls, minutes = outcome(nxt["node"], nxt["part"], k)
        ledger += min(int(minutes), nxt["timeout"] + 1)
        peak = max(peak, ledger)
        history[key].append(cls)
        st = AT.part_state(history[key])
        if st["next"] == AT.DONE:
            terminal[key] = AT.RESULT
        elif st["next"] == AT.EXHAUSTED:
            terminal[key] = f"{AT.TECHNICAL_EXHAUSTION}:{st['reason']}"
        trace.append({"run": f"{nxt['node']} part {nxt['part']} #{k}", "class": cls, "ledger": ledger})
    unended = sorted(f"{n} part {p}" for (n, p) in history if (n, p) not in terminal)
    return {"ledger": ledger, "peak": peak, "guard_runs": guards, "terminal": terminal, "unended": unended,
            "within_cap": peak <= cap and ledger <= cap, "trace": trace,
            "node_runs": sum(len(h) for h in history.values())}


# -- outcome models ---------------------------------------------------------------------------------

# The most minutes a part can use and still end RESULT: two INFRA retries and a SCIENCE attempt, each at its
# timeout + 1, then the result; every part of the DAG then runs, so the cap must stop the program.
HEAVIEST = (AT.INFRA, AT.INFRA, AT.SCIENCE)


def worst_outcomes(pattern: tuple[str, ...]):
    """Every part's runs follow ``pattern`` (then RESULT), each billing its full timeout + 1."""
    def f(_node, _part, k):
        return (pattern[k - 1] if k <= len(pattern) else AT.RESULT), 10 ** 6
    return f


def random_outcomes(seed: int, p_infra: float = 0.3, p_science: float = 0.3):
    rng = random.Random(seed)

    def f(_node, _part, _k):
        x = rng.random()
        cls = AT.INFRA if x < p_infra else AT.SCIENCE if x < p_infra + p_science else AT.RESULT
        return cls, rng.choice([0, 1, rng.randint(0, 10 ** 4), 10 ** 6])
    return f


def expected_outcomes(table: dict | None = None):
    """Every part ends RESULT on its first run, at the law's estimate (split evenly over a node's parts, SC by
    its timeouts)."""
    table = table or nodes()
    sc = {f"SC-{f}": LAW_ESTIMATES["SC"] * table[f"SC-{f}"]["timeout"] /
          sum(table[f"SC-{x}"]["timeout"] for x in FAMILIES) for f in FAMILIES}

    def f(node, _part, _k):
        est = sc[node] if node in sc else LAW_ESTIMATES[node] / table[node]["parts"]
        return AT.RESULT, -(-est // 1)
    return f


def report() -> dict:
    table = nodes()
    rows = stage_rows(table)
    plan = parts_in_order(table)
    exp = simulate(plan, expected_outcomes(table), guard_minutes=lambda _i: 1, closure_minutes=2)
    worst = simulate(plan, worst_outcomes(HEAVIEST))
    return {"cap": CAP, "guard_timeout": GUARD_TIMEOUT, "closure_timeout": CLOSURE_TIMEOUT, "reserve": RESERVE,
            "auth2_law_proof": law_proof(table), "auth2_worst_case_all_jobs": worst_case(rows),
            "stage_rows": rows, "max_runs_per_part": AT.max_runs_per_part(),
            "expected": {"ledger": exp["ledger"], "node_runs": exp["node_runs"], "guard_runs": exp["guard_runs"],
                         "within_cap": exp["within_cap"]},
            "adversarial": {"ledger": worst["ledger"], "peak": worst["peak"], "within_cap": worst["within_cap"],
                            "unended": worst["unended"],
                            "terminals": sorted(set(worst["terminal"].values()))}}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("report")
    r.add_argument("--out")
    a = ap.parse_args(argv)
    rec = report()
    body = json.dumps(rec, indent=1, sort_keys=True) + "\n"
    if a.out:
        Path(a.out).write_text(body)
    print(body, end="")
    ok = rec["auth2_worst_case_all_jobs"] == AUTH2_WORST_CASE and rec["auth2_law_proof"] == AUTH2_LAW_PROOF \
        and rec["expected"]["within_cap"] and rec["adversarial"]["within_cap"] and not rec["adversarial"]["unended"]
    print("COMPUTE_PROOF = " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 3


if __name__ == "__main__":
    sys.exit(main())
