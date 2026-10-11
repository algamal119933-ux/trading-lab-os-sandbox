#!/usr/bin/env python3
"""Write (or --check) every AUTH-2 preregistration and the program charter.

    python research/auth2/make_preregs.py            # write
    python research/auth2/make_preregs.py --check    # exit 2 unless the committed files are exactly these

Every value comes from a frozen source: the node table and thresholds from
run_node.py (which the gates read), the configurations from families.py, the
windows from the Dataset V3 lock, the calibration edges from
research/auth2/calibration_edges.json, and the sha256 of every pinned file. The
program charter lists each preregistration's sha256, so nothing in a
preregistration can change without the charter (and its Owner merge) changing.

PAPER / RESEARCH ONLY.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
if str(HERE.parent) not in sys.path:
    sys.path.insert(0, str(HERE.parent))

from auth2 import calibration as CA  # noqa: E402
from auth2 import families as F  # noqa: E402
from auth2 import run_node as RN  # noqa: E402
from auth2 import synthetic as SY  # noqa: E402

PREREG_DIR = "research/auth2/prereg"
EDGES_REL = "research/auth2/calibration_edges.json"
FUNNEL_LAW_REL = "research/auth2/FUNNEL_LAW_2.md"
LOCK_REL = "research/datasets/dataset_v3.lock.json"
REQUIREMENTS_REL = "research/auth2/requirements-auth2.txt"
LAUNCHER_REL = "research/auth2/engine/run_backtest.py"
STRATEGY_REL = "research/auth2/engine/AUTH2ScheduleFollower.py"

TRIAL = {n: f"TRIAL-AUTH2-{n}" for n in RN.NODES}
for _f in F.FAMILIES:
    TRIAL[f"SC-{_f}"] = TRIAL[_f]  # the secondary segment is part of the family's scientific trial

HYPOTHESIS = {
    "A1": "TSMOM-VT: per-sleeve time-series momentum with volatility targeting on point-in-time U6, long or cash",
    "A2": "XSMOM-LO: weekly cross-sectional momentum, top 3 of point-in-time U12 with a cash gate, long or cash",
    "A3": "CROWD-OVERLAY (risk-overlay experiment): BTC/ETH volatility-targeted base cut to 50% while 7-day "
          "mean funding is crowded (z > 2)",
}
BENCHMARK = {
    "A1": "A1-BENCH: same U6, same per-sleeve VT law (25%, 30-day vol), same 1/6 sleeves and timing, always long",
    "A2": "A2-BENCH: same U12, schedule, skip-day lookback and cash gate; gross exposure min(k, n_eligible)/k spread "
          "equally over all eligible coins; no ranking",
    "A3": "A3-BASE: the base exposure without the overlay (paired ablation)",
}
NULL = {
    "A1": "random timing: each sleeve's primary position series circularly shifted by an independent uniform "
          "offset in [90 days, T - 90 days]",
    "A2": "random selection: each week k coins drawn uniformly from the eligible set, same exposure",
    "A3": "random overlay: the same number and durations of overlay episodes at random non-overlapping times",
}

DISCLOSURES = [
    "Primary configurations are a human selection from the literature (package PRIMARY_CONFIGS), fixed before "
    "any AUTH-2 result; perturbations are reject-only.",
    "Engine launcher (research/auth2/engine/run_backtest.py) installs a frozen market table, uses the frozen "
    "markets' price precision (none) instead of the tick Freqtrade infers from candles, and skips Freqtrade's "
    "defensive deep copy of the trade passed to strategy callbacks (proven result-identical); disclosed in "
    "IMPLEMENTATION_NOTES.md.",
    "Before preregistration an implementation smoke test ran the A3 and A1 primary configurations once each on "
    "real Dataset V3 data over their scored windows and printed their engine total returns (A3 +104.0%, A1 "
    "+260.5%, under a since-removed -99% stop); no benchmark, dSR, p-value or gate was computed and nothing "
    "frozen was changed after it (IMPLEMENTATION_NOTES.md §Disclosed pre-registration exposure).",
    "The A3 synthetic planted-edge generator was corrected before preregistration so a planted world keeps the "
    "no-edge expected drift (IMPLEMENTATION_NOTES.md §Synthetic worlds); the A3 edge was calibrated after it.",
    "H1 upstream selection debt (42 strategies) is disclosed verbatim and not folded into A1's N = 21; lifetime "
    "TLOS configurations tested: 19 before AUTH-2 + 16 = 35.",
]

PURPOSE = {
    "DATA_LOCK": "D0: rebuild Dataset V3 from the Binance public archive and prove the committed lock, membership, "
                 "delisting and coverage tables byte-identical; decides DATA_LIMITED per family.",
    "CALIBRATION_STAT": "CAL-{f}-STAT: size (<= 10/200 no-edge worlds accepted) and power (>= 160/200 planted-edge "
                        "worlds accepted at delta {d}) of family {f}'s full gate stack, before any market-data trial.",
    "POSITIVE_CONTROL": "PC-{f}: family {f}'s engine fixtures on one planted-edge synthetic world (seed 777) must "
                        "SURVIVE every gate; replay parity of every run.",
    "NULL_CALIBRATION": "N-{f}: family {f}'s null fixture (seed 0, perturbation seeds 1001..) on real Dataset V3 data "
                        "through every gate must be REJECTED; replay parity of every run.",
    "SCIENTIFIC": "{f}: the frozen primary configuration of family {f} against its matched benchmark on Dataset V3, "
                  "with its precommitted reject-only perturbations, stresses and family gates (FUNNEL-LAW-2).",
    "HOLM": "HOLM: Holm step-down across the three family hypotheses, m = 3 fixed, FWER 0.05; an untested family "
            "enters with p = 1.",
    "SECONDARY_CONFIRM": "SC-{f}: reject-only secondary confirmation of family {f} on 2025-01-01 to 2026-08-31 "
                         "(dSR point estimate > 0); can never rescue.",
}

TERMINAL = {
    "DATA_LOCK": ["PASS", "INVALID_RUN"],
    "CALIBRATION_STAT": ["PASS", "LAW_INVALID", "INCONCLUSIVE_UNDERPOWERED"],
    "POSITIVE_CONTROL": ["SURVIVED", "NOT_SURVIVED", "INVALID_RUN"],
    "NULL_CALIBRATION": ["REJECTED", "NOT_REJECTED", "INVALID_RUN"],
    "SCIENTIFIC": ["PRE_HOLM_PASS", "REJECTED", "INCONCLUSIVE", "INVALID_RUN"],
    "HOLM": ["COMPLETE"],
    "SECONDARY_CONFIRM": ["SURVIVED", "REJECTED", "INVALID_RUN"],
}

EDGE_ON = {"CAL": "PASS", "PC": "SURVIVED", "N": "REJECTED", "A": "ANY_TERMINAL", "SC": "HOLM_PASS"}


def sha256_file(rel: str) -> str:
    return hashlib.sha256((REPO / rel).read_bytes()).hexdigest()


def pin(rel: str) -> dict:
    return {"path": rel, "sha256": sha256_file(rel)}


def dumps(obj) -> str:
    return json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def windows(fam: str | None) -> dict:
    lock = json.loads((REPO / LOCK_REL).read_text())
    start = lock["a3_start_utc"] if fam == "A3" else "2019-01-01T00:00:00Z"
    return {"scored": {"start_utc": start, "end_utc": "2025-01-01T00:00:00Z"},
            "secondary": {"start_utc": "2025-01-01T00:00:00Z", "end_utc": "2026-09-01T00:00:00Z"}}


def generator_constants() -> dict:
    names = ("ANNUAL_VOL", "GARCH_ALPHA", "GARCH_BETA", "T_DOF", "FACTOR_RHO", "INTRADAY_RANGE", "FUNDING_PER_DAY",
             "FUNDING_MEAN", "FUNDING_PHI", "FUNDING_SD", "CRASH_P_BASE", "CRASH_LOG_JUMP", "CRASH_HORIZON_DAYS",
             "N_ASSETS")
    return {n: getattr(SY, n) for n in names} | {"world_start_utc": SY.WORLD_START.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                                   "world_end_utc": SY.WORLD_END.strftime("%Y-%m-%dT%H:%M:%SZ")}


def configurations(fam: str | None) -> dict:
    if fam is None:
        return {}
    return {"primary": F.PRIMARY[fam], "perturbations": F.PERTURBATIONS[fam], "matched_benchmark": BENCHMARK[fam],
            "null": NULL[fam], "family_configuration_n": F.FAMILY_N[fam], "hypothesis": HYPOTHESIS[fam]}


def predecessors(node: str) -> list[dict]:
    return [{"node": n, "on": list(on)} for n, on in RN.predecessors(node)]


def prereg(node: str) -> dict:
    spec = RN.NODES[node]
    kind, fam = spec["kind"], spec["family"]
    edges = json.loads((REPO / EDGES_REL).read_text())
    out = {
        "schema_version": "auth2-prereg-1.0.0",
        "program_id": RN.PROGRAM_ID,
        "node_id": node,
        "trial_id": TRIAL[node],
        "kind": kind,
        "family": fam,
        "purpose": PURPOSE[kind].format(f=fam, d=CA.DELTA.get(fam)),
        "funnel_law": pin(FUNNEL_LAW_REL),
        "dataset_lock": pin(LOCK_REL),
        "engine": {"image": "freqtradeorg/freqtrade:2026.7", "launcher": pin(LAUNCHER_REL),
                   "strategy": pin(STRATEGY_REL), "timeframe": "4h",
                   "disclosed_engine_patches": ["frozen ccxt market table (offline; delisted symbols)",
                                                "price precision from the frozen markets (none)",
                                                "defensive trade deep copy skipped (result-identical)"]},
        "windows": windows(fam),
        "configurations": configurations(fam),
        "thresholds": json.loads(json.dumps(RN.thresholds())),
        "compute": {"timeout_minutes": spec["timeout_minutes"], "parts": spec["parts"],
                    "planned_engine_invocations": spec["invocations"]},
        "predecessors": predecessors(node),
        "terminal_states": TERMINAL[kind],
        "code_sha256": RN.code_sha256(),
        "requirements": pin(REQUIREMENTS_REL),
        "disclosures": DISCLOSURES,
        "dry_run": True,
        "real_money_authorized": False,
        "hyperopt": 0,
        "llm_agent_tokens": 0,
    }
    if kind in ("CALIBRATION_STAT", "POSITIVE_CONTROL"):
        e = edges["families"][fam]
        out["calibration"] = {"delta": e["delta"], "edge": e["edge"], "true_delta": e["true_delta"],
                              "first_seed": e["first_seed"], "years": e["years"], "record": pin(EDGES_REL),
                              "generator": generator_constants()}
    return out


def node_order() -> list[str]:
    order = ["D0"]
    for f in F.FAMILIES:
        order.append(f"CAL-{f}")
    for f in F.FAMILIES:
        order.append(f"PC-{f}")
    for f in F.FAMILIES:
        order.append(f"N-{f}")
    order += list(F.FAMILIES) + ["HOLM"] + [f"SC-{f}" for f in F.FAMILIES]
    return order


def dag_edges() -> list[dict]:
    edges = []
    for f in F.FAMILIES:
        edges += [{"from": "D0", "on": "PASS", "to": f"CAL-{f}"},
                  {"from": f"CAL-{f}", "on": EDGE_ON["CAL"], "to": f"PC-{f}"},
                  {"from": f"PC-{f}", "on": EDGE_ON["PC"], "to": f"N-{f}"},
                  {"from": f"N-{f}", "on": EDGE_ON["N"], "to": f},
                  {"from": f, "on": EDGE_ON["A"], "to": "HOLM"},
                  {"from": "HOLM", "on": EDGE_ON["SC"], "to": f"SC-{f}"}]
    return edges


def program(prereg_sha: dict[str, str]) -> dict:
    nodes = [{"id": n, "trial_id": TRIAL[n], "kind": RN.NODES[n]["kind"], "family": RN.NODES[n]["family"],
              "prereg_path": f"{PREREG_DIR}/{n}.json", "prereg_sha256": prereg_sha[n]} for n in node_order()]
    return {
        "program_id": RN.PROGRAM_ID,
        "schema_version": 2,
        "version": 1,
        "status": "ACTIVE",
        "families": [{"id": "A1", "hypothesis_class": HYPOTHESIS["A1"], "inherited_n": 15},
                     {"id": "A2", "hypothesis_class": HYPOTHESIS["A2"], "inherited_n": 0},
                     {"id": "A3", "hypothesis_class": HYPOTHESIS["A3"], "inherited_n": 0}],
        "dataset_lock": LOCK_REL,
        "development_window": {"start": "2019-01-01", "end": "2024-12-31"},
        "holdout_law": "Option B unchanged: the first strict holdout is prospective live-market paper. The "
                       "secondary segment 2025-01-01..2026-08-31 is non-pristine and reject-only (C10). A3 is "
                       "scored from the lock's A3_START.",
        "frozen_hashes": {"funnel_law": pin(FUNNEL_LAW_REL), "funnel_py": pin("research/auth2/gates.py"),
                          "multiple_testing_py": pin("research/auth2/stats.py"),
                          "config_n_py": pin("research/auth2/families.py")},
        "n_law": "Cumulative family configuration N for DSR: A1 = 21 (15 inherited + 6), A2 = 6, A3 = 4; the H1 "
                 "upstream 42-strategy debt is disclosed, not folded in; lifetime TLOS configurations 19 + 16 = 35.",
        "caps": {"configurations": 16, "scientific_trial_ids": 5, "calibration_trial_ids": 12,
                 "engine_invocations": 240, "hyperopt": 0, "attributed_linux_minutes": 4000,
                 "paid_actions_overage_usd": 0, "llm_agent_tokens": 0},
        "dag": {"nodes": nodes, "edges": dag_edges(), "max_depth": 7, "max_nodes": 17},
        "null_calibration_first": True,
        "stop_rules": [
            "a node outside this DAG, or a node whose predecessor did not end in the edge's state, never runs",
            "CAL-Ax size FAIL => family LAW_INVALID; power FAIL or PC-Ax not SURVIVED => INCONCLUSIVE_UNDERPOWERED; "
            "N-Ax not REJECTED => LAW_INVALID; DATA_LIMITED at D0 => the family has no further node",
            "one family's calibration failure never stops another family",
            "any C1 integrity failure => INVALID_RUN; one technical retry within caps, otherwise STOP_PROGRAM",
            "HOLM is the join: it runs once every family is terminal; a family without a scientific p-value "
            "enters with p = 1",
            "any cap (240 invocations, 4,000 attributed minutes, USD 0 overage, monthly reserve) => no dispatch",
            "DAG exhausted => closure record (terminal) and STOP",
        ],
        "terminal": "closure_record",
    }


FAMILY_ID = {"A1": "AUTH2_A1_TSMOM_VT", "A2": "AUTH2_A2_XSMOM_LO", "A3": "AUTH2_A3_CROWD_OVERLAY",
             None: "AUTH2_PROGRAM"}


def ledger_preregistrations(prereg_sha: dict[str, str]) -> list[dict]:
    """One PREREGISTERED trial record per distinct trial ID (14), each binding the sha256 of every
    preregistration that runs under it (a family's scientific trial binds Ax and SC-Ax). run_node.py
    refuses a node whose preregistration sha256 is not the one bound here."""
    lock_sha = sha256_file(LOCK_REL)
    out = []
    for trial in dict.fromkeys(TRIAL[n] for n in node_order()):
        nodes = [n for n in node_order() if TRIAL[n] == trial]
        spec = RN.NODES[nodes[0]]
        kind, fam = spec["kind"], spec["family"]
        scientific = kind == "SCIENTIFIC"
        cfg = configurations(fam) if fam else {}
        out.append({
            "schema_version": "1.0.0",
            "family_id": FAMILY_ID[fam],
            "lineage_id": f"{FAMILY_ID[fam]}/L1",
            "candidate_id": f"{FAMILY_ID[fam]}/{'PRIMARY' if scientific else kind}",
            "config_id": f"{FAMILY_ID[fam]}/{'PRIMARY+' + str(len(cfg.get('perturbations', {}))) + 'P' if scientific else nodes[0]}",
            "experiment_id": f"EXP-AUTH2-{nodes[0]}",
            "run_id": f"RUN-AUTH2-{nodes[0]}",
            "trial_id": trial,
            "state": "PREREGISTERED",
            "purpose": PURPOSE[kind].format(f=fam, d=CA.DELTA.get(fam)),
            "config_hash": hashlib.sha256(json.dumps(cfg, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            if cfg else None,
            "code_identity": {"file": "research/auth2/run_node.py", "sha256": sha256_file("research/auth2/run_node.py")},
            "dataset_identity": {"program_id": RN.PROGRAM_ID, "program": RN.PROGRAM_REL,
                                 "dataset_lock": {"path": LOCK_REL, "sha256": lock_sha},
                                 "funnel_law": FUNNEL_LAW_REL, "engine_version": "freqtradeorg/freqtrade:2026.7",
                                 "nodes": nodes, "preregs": {n: prereg_sha[n] for n in nodes},
                                 "planned_engine_invocations": sum(RN.NODES[n]["invocations"] for n in nodes)},
            "deterministic_seed": None,
            "notes": ("Scientific trial ID: the family's primary, its precommitted reject-only perturbations, "
                      "stresses and family gates (node " + nodes[0] + ") and its reject-only secondary "
                      "confirmation (SC-" + str(fam) + ") if Holm passes. Family configuration N = "
                      + str(F.FAMILY_N[fam]) + "." if scientific else
                      "Calibration/law trial ID of AUTH-2 (not a scientific configuration). Seeds and thresholds "
                      "are in the bound preregistration.") + " PAPER / RESEARCH ONLY.",
        })
    return out


def build() -> dict[str, bytes]:
    files = {}
    shas = {}
    for n in node_order():
        body = dumps(prereg(n)).encode()
        files[f"{PREREG_DIR}/{n}.json"] = body
        shas[n] = hashlib.sha256(body).hexdigest()
    files[RN.PROGRAM_REL] = dumps(program(shas)).encode()
    return files


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--append-ledger", action="store_true",
                    help="append the 14 PREREGISTERED records (run once, in a commit after the program's)")
    a = ap.parse_args(argv)
    files = build()
    if a.append_ledger:
        from trial_ledger import TrialLedger

        shas = {n: hashlib.sha256(files[f"{PREREG_DIR}/{n}.json"]).hexdigest() for n in node_order()}
        led = TrialLedger(REPO / RN.LEDGER_REL)
        for payload in ledger_preregistrations(shas):
            if led.preregistration_for(payload["trial_id"]) is not None:
                print(f"already preregistered {payload['trial_id']}")
                continue
            rec = led.append(payload)
            print(f"appended seq {rec.seq} {payload['trial_id']}")
        return 0
    if a.check:
        bad = [rel for rel, body in files.items() if not (REPO / rel).is_file() or (REPO / rel).read_bytes() != body]
        extra = sorted(p.relative_to(REPO).as_posix() for p in (REPO / PREREG_DIR).glob("*.json")
                       if p.relative_to(REPO).as_posix() not in files)
        for rel in bad:
            print(f"DIFFERS  {rel}")
        for rel in extra:
            print(f"EXTRA    {rel}")
        print("AUTH2_PREREG_CHECK = " + ("FAIL" if bad or extra else "PASS"))
        return 2 if bad or extra else 0
    for rel, body in files.items():
        (REPO / rel).parent.mkdir(parents=True, exist_ok=True)
        (REPO / rel).write_bytes(body)
        print(f"wrote {rel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
