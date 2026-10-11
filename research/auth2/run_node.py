#!/usr/bin/env python3
"""Run one node of AUTH-2-DISCOVERY-QUALIFICATION-1 (FUNNEL_LAW_2.md §CALIBRATION_DAG).

    python -m auth2.run_node --node <ID> [--part 1|2] --repo . --out OUT
                             --predecessors DIR --cache-dir CACHE --engine docker|<python>

One invocation = one node (or one half of a split node). It refuses to run
unless, in order:

  1. the program charter validates and every preregistration, the funnel law
     and every pinned code file match their sha256 (C12);
  2. the node's preregistration is bound in the trial ledger and the ledger
     chain verifies (C1 LEDGER_CHAIN, C12);
  3. every predecessor result named by the DAG is present (downloaded from
     the earlier workflow runs into --predecessors), was produced under the
     same program sha256, and ended in the state the DAG edge requires;
  4. the preregistered thresholds equal the code's (no code defaults).

It then does the node's work, checks C1 integrity (DATA_TRUTH, LOOKAHEAD,
RECURSIVE, ENGINE_FEE_PROPAGATION, REPLAY_PARITY), and writes one result
record (``<OUT>/<NODE>.result.json``) carrying its inputs' hashes, the code
sha256, every engine run's identity, the gate table and the node's terminal
state. It never writes the trial ledger, never commits, never pushes and never
dispatches anything: terminal ledger records and the closure are the
operator's later, separate appends.

Caps: a node never issues more engine invocations than its preregistered plan
(the program-level 240 and 4,000-minute ceilings are enforced before dispatch
by dispatch_guard.py). Hyperopt = 0; no LLM or agent call exists in this code.

PAPER / RESEARCH ONLY. Backtesting only: dry_run true, spot, keyless.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
RESEARCH = HERE.parent
if str(RESEARCH) not in sys.path:
    sys.path.insert(0, str(RESEARCH))

from auth2 import calibration as CA  # noqa: E402
from auth2 import engine_io as EIO  # noqa: E402
from auth2 import families as F  # noqa: E402
from auth2 import gates as GT  # noqa: E402
from auth2 import replay as RP  # noqa: E402
from auth2 import signals as S  # noqa: E402
from auth2 import stats as ST  # noqa: E402
from auth2 import synthetic as SY  # noqa: E402

PROGRAM_ID = "AUTH-2-DISCOVERY-QUALIFICATION-1"
PROGRAM_REL = f"charters/programs/{PROGRAM_ID}.json"
LEDGER_REL = "research/records/trial_ledger.jsonl"
DAY_MS = 86_400_000


def _ms(y: int, mo: int = 1, d: int = 1) -> int:
    return int(datetime(y, mo, d, tzinfo=timezone.utc).timestamp() * 1000)


SCORED = {"A1": (_ms(2019), _ms(2025)), "A2": (_ms(2019), _ms(2025))}  # A3 starts at the lock's A3_START
SECONDARY = (_ms(2025), _ms(2026, 9))


# -- the node table (compute plan: FUNNEL_LAW_2.md §COMPUTE_CAP_PROOF) ---------------

def _family_nodes(f: str, pc_n: int, ax_n: int, t_pc: int, t_ax: int, t_sc: int, parts: int) -> dict:
    return {
        f"CAL-{f}": {"kind": "CALIBRATION_STAT", "family": f, "invocations": 0, "timeout_minutes": 60, "parts": 1},
        f"PC-{f}": {"kind": "POSITIVE_CONTROL", "family": f, "invocations": pc_n, "timeout_minutes": t_pc, "parts": parts},
        f"N-{f}": {"kind": "NULL_CALIBRATION", "family": f, "invocations": pc_n, "timeout_minutes": t_pc, "parts": parts},
        f: {"kind": "SCIENTIFIC", "family": f, "invocations": ax_n, "timeout_minutes": t_ax, "parts": 1},
        f"SC-{f}": {"kind": "SECONDARY_CONFIRM", "family": f, "invocations": 1, "timeout_minutes": t_sc, "parts": 1},
    }


NODES = {"D0": {"kind": "DATA_LOCK", "family": None, "invocations": 0, "timeout_minutes": 150, "parts": 1},
         **_family_nodes("A1", 13, 9, 150, 120, 30, 1),
         **_family_nodes("A2", 15, 10, 180, 240, 45, 2),
         **_family_nodes("A3", 11, 7, 60, 45, 15, 1),
         "HOLM": {"kind": "HOLM", "family": None, "invocations": 0, "timeout_minutes": 15, "parts": 1}}

# terminal states each kind can end in
PASS, INVALID = "PASS", "INVALID_RUN"


def predecessors(node: str) -> list[tuple[str, tuple[str, ...]]]:
    """(predecessor node, accepted terminal states) per the frozen DAG."""
    if node == "D0":
        return []
    if node.startswith("CAL-"):
        return [("D0", (PASS,))]
    if node.startswith("PC-"):
        return [("CAL-" + node[3:], (PASS,))]
    if node.startswith("N-"):
        return [("PC-" + node[2:], ("SURVIVED",))]
    if node in ("A1", "A2", "A3"):
        return [("N-" + node, ("REJECTED",))]
    if node == "HOLM":
        return []  # HOLM reads every family's final record (see holm())
    if node.startswith("SC-"):
        f = node[3:]
        return [("HOLM", ("COMPLETE",)), (f, ("PRE_HOLM_PASS",)), ("N-" + f, ("REJECTED",))]
    raise KeyError(node)


def kind_is_sc(node: str) -> bool:
    return NODES[node]["kind"] == "SECONDARY_CONFIRM"


# -- hashing and records ------------------------------------------------------------

def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def sha256_json(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def code_sha256() -> dict[str, str]:
    files = sorted(list(HERE.glob("*.py")) + list((HERE / "engine").glob("*.py")))
    return {f.relative_to(RESEARCH.parent).as_posix(): sha256_file(f) for f in files}


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, sort_keys=True, allow_nan=True) + "\n")


class Refusal(SystemExit):
    pass


def refuse(msg: str) -> None:
    raise Refusal(f"AUTH2_NODE_REFUSED: {msg}")


# -- preconditions (C12, C1 LEDGER_CHAIN) ---------------------------------------------

def load_program(repo: Path) -> tuple[dict, str]:
    sys.path.insert(0, str(repo / ".github" / "gates"))
    import check_research_program as crp

    problems = crp.check(repo)
    if problems:
        refuse("program check failed: " + "; ".join(problems))
    path = repo / PROGRAM_REL
    return json.loads(path.read_text()), sha256_file(path)


def node_prereg(repo: Path, program: dict, node: str) -> tuple[dict, dict]:
    entry = next((n for n in program["dag"]["nodes"] if n["id"] == node), None)
    if entry is None:
        refuse(f"node {node} is not in the program DAG")
    prereg = json.loads((repo / entry["prereg_path"]).read_text())
    if prereg["node_id"] != node or prereg["trial_id"] != entry["trial_id"]:
        refuse(f"{node}: preregistration does not name this node and trial")
    pins = prereg["code_sha256"]
    now = code_sha256()
    if pins != now:
        bad = sorted(k for k in set(pins) | set(now) if pins.get(k) != now.get(k))
        refuse(f"{node}: code differs from the preregistered sha256 pins: {bad}")
    if prereg["thresholds"] != json.loads(json.dumps(thresholds())):
        refuse(f"{node}: preregistered thresholds differ from the code constants")
    return entry, prereg


def check_ledger(repo: Path, trial_id: str, node: str, prereg_sha: str) -> dict:
    """The ledger chain verifies and the trial's PREREGISTERED record binds this node's preregistration
    (payload.dataset_identity.preregs[node] == its sha256), so a preregistration edited after the ledger
    append can never run."""
    from trial_ledger import TrialLedger

    led = TrialLedger(repo / LEDGER_REL)
    problems = led.verify()
    if problems:
        return {"status": "FAIL", "problems": problems}
    pre = led.preregistration_for(trial_id)
    if pre is None:
        return {"status": "FAIL", "problems": [f"{trial_id} is not preregistered in the ledger"]}
    bound = (pre.payload.get("dataset_identity") or {}).get("preregs", {}).get(node)
    if bound != prereg_sha:
        return {"status": "FAIL", "problems": [f"{trial_id}: the PREREGISTERED record binds {node} to {bound}, "
                                                f"the program to {prereg_sha}"]}
    terminal = [r.seq for r in led.records_for(trial_id=trial_id) if r.payload["state"] != "PREREGISTERED"]
    return {"status": "PASS", "preregistration_seq": pre.seq, "tip": led.tip_digest(), "terminal_records": terminal}


def thresholds() -> dict:
    """Every number a gate reads (FUNNEL_LAW_2.md); the prereg must equal this exactly."""
    return {
        "base_fee": GT.BASE_FEE, "stress_fees": GT.STRESS_FEES, "seeds": GT.SEEDS,
        "holm_alpha": GT.ALPHA_HOLM, "holm_m": GT.HOLM_M, "perturbation_fwer": GT.ALPHA_PERTURBATION,
        "c4_alpha": GT.C4_ALPHA, "c4_draws": F.NULL_DRAWS, "dsr_threshold": GT.DSR_THRESHOLD,
        "spa_alpha": GT.SPA_ALPHA, "pbo_blocks": GT.PBO_BLOCKS, "coverage_min": GT.COVERAGE_MIN,
        "a1_min_sleeve_days": GT.A1_MIN_SLEEVE_DAYS, "a1_sleeves_positive": GT.A1_SLEEVES_POSITIVE,
        "a2_years": GT.A2_YEARS, "a2_years_positive": GT.A2_YEARS_POSITIVE, "a3_cvar_level": GT.A3_CVAR_LEVEL,
        "a3_episode_merge_days": F.A3_EPISODE_MERGE_DAYS, "a1_episode_lookback": F.A1_EPISODE_LOOKBACK,
        "a1_episode_min_days": F.A1_EPISODE_MIN_DAYS, "family_n": F.FAMILY_N, "min_positive": F.MIN_POSITIVE,
        "a2_extra_slippage": F.A2_EXTRA_SLIPPAGE, "a2_exempt_ranks": F.A2_EXEMPT_RANKS,
        "bootstrap": {"resamples": ST.RESAMPLES, "block_min": ST.BLOCK_MIN, "block_max": ST.BLOCK_MAX,
                      "sensitivity": list(ST.SENSITIVITY_BLOCKS), "spa_vol_target": ST.SPA_VOL_TARGET},
        "parity": {"min_correlation": RP.PARITY_MIN_CORRELATION, "max_total_return_diff": RP.PARITY_MAX_TOTAL_RETURN_DIFF},
        "calibration": {"delta": CA.DELTA, "worlds": CA.WORLDS, "size_max_accepted": CA.SIZE_MAX_ACCEPTED,
                        "power_min_accepted": CA.POWER_MIN_ACCEPTED, "size_seeds": [CA.SIZE_SEEDS[0], CA.SIZE_SEEDS[-1]],
                        "power_seeds": [CA.POWER_SEEDS[0], CA.POWER_SEEDS[-1]], "pc_seed": CA.PC_SEED,
                        "true_delta_first_seed": CA.TRUE_DELTA_SEED, "true_delta_years": CA.TRUE_DELTA_YEARS},
        "null_seeds": {"c4": [F.C4_SEEDS[0], F.C4_SEEDS[-1]], "n_fixture": F.N_FIXTURE_SEED,
                       "n_perturbations": F.N_PERTURBATION_SEEDS},
        "perturbations": F.PERTURBATIONS, "primary": F.PRIMARY,
    }


def load_predecessor(pred_dir: Path, node: str, program_sha: str) -> dict:
    hits = sorted(pred_dir.rglob(f"{node}.result.json"))
    if len(hits) != 1:
        refuse(f"predecessor {node}: expected exactly one result record, found {len(hits)}")
    rec = json.loads(hits[0].read_text())
    if rec.get("program_sha256") != program_sha:
        refuse(f"predecessor {node} was produced under a different program sha256")
    rec["_sha256"] = sha256_file(hits[0])
    return rec


# -- markets ---------------------------------------------------------------------------

def a3_start(repo: Path) -> int:
    lock = json.loads((repo / "research/datasets/dataset_v3.lock.json").read_text())
    return int(datetime.strptime(lock["a3_start_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp() * 1000)


def scored(fam: str, repo: Path) -> tuple[int, int]:
    return (a3_start(repo), _ms(2025)) if fam == "A3" else SCORED[fam]


def real_market(fam: str, repo: Path, cache: Path, work: Path) -> tuple[S.Market, RP.Prices, dict, dict]:
    """Dataset V3 engine data for the family, written and sha256-checked against the lock (DATA_TRUTH)."""
    from auth2 import dataset_v3 as D
    from auth2 import market_io as MI

    syms = MI.family_symbols(fam, MI.tables(repo))
    out = work / "engine_data"
    written = D.engine_data(syms, cache, D.A.DEFAULT_BASE, out, repo)
    m, prices, bars = MI.load(fam, out, repo, funding_dir=out)
    truth = {"status": "PASS", "symbols": len(written), "content_sha256_4h": written,
             "lock_sha256": sha256_file(repo / "research/datasets/dataset_v3.lock.json")}
    if fam == "A2":
        lock_u8 = MI.u8_market(m, repo)
        if [p[2] for p in F.u8_market(m).periods] != [p[2] for p in lock_u8.periods]:
            truth = {"status": "FAIL", "reason": "U8 rebuilt from the ranked candidates differs from the lock"}
    return m, prices, bars, truth


def synthetic_market(fam: str, edge: float) -> tuple[S.Market, RP.Prices, dict]:
    w = SY.generate(fam, seed=CA.PC_SEED, edge=edge)
    m = w.market
    prices = RP.fill_like_freqtrade(m.times, {p: w.bars[p][:, :5] for p in m.pairs}, m.pairs)
    return m, prices, w.bars


# -- engine runs ------------------------------------------------------------------------

def run_plan(node: str, fam: str) -> list[dict]:
    """The node's engine runs (names, fee, offset, window, universe) per the compute plan."""
    kind = NODES[node]["kind"]
    perts = list(F.PERTURBATIONS[fam])
    runs = []

    def add(name, cfg, fee=GT.BASE_FEE, off=0, window="scored", universe="base"):
        runs.append({"name": name, "config": cfg, "fee": fee, "offset": off, "window": window, "universe": universe})

    if kind in ("POSITIVE_CONTROL", "NULL_CALIBRATION"):
        add("primary", "primary")
        add("primary@x2", "primary", fee=GT.STRESS_FEES["x2"])
        add("primary@lat", "primary", off=1)
        for p in perts:
            add(p, p)
        add("bench", "bench")
        add("bench@x2", "bench", fee=GT.STRESS_FEES["x2"])
        add("bench@lat", "bench", off=1)
        add("primary@sec", "primary", window="secondary")
        add("bench@sec", "bench", window="secondary")
        if fam == "A2":
            add("primary@u8", "primary", universe="u8")
            add("bench@u8", "bench", universe="u8")
    elif kind == "SCIENTIFIC":
        add("primary", "primary")
        add("primary@x2", "primary", fee=GT.STRESS_FEES["x2"])
        add("primary@x3", "primary", fee=GT.STRESS_FEES["x3"])
        add("primary@lat", "primary", off=1)
        for p in perts:
            add(p, p)
        if fam == "A2":
            add("primary@u8", "primary", universe="u8")
    elif kind == "SECONDARY_CONFIRM":
        add("primary@sec", "primary", window="secondary")
    if len(runs) != NODES[node]["invocations"]:
        raise AssertionError(f"{node}: run plan has {len(runs)} runs, the compute plan {NODES[node]['invocations']}")
    return runs


def _bundle_for(run: dict, fam: str, m: S.Market, win: tuple[int, int], override) -> F.Bundle:
    mm = F.u8_market(m) if run["universe"] == "u8" else m
    return F.bundle(fam, mm, win[0], win[1], [run["config"]], run["offset"], override)


def engine_run(run: dict, fam: str, m: S.Market, prices: RP.Prices, bars: dict, win: tuple[int, int],
               override, work: Path, engine: str, keep_trade_copy: bool = False) -> dict:
    """One Freqtrade invocation plus its replay parity (C1 ENGINE_FEE_PROPAGATION, REPLAY_PARITY)."""
    b = _bundle_for(run, fam, m, win, override)
    mm = F.u8_market(m) if run["universe"] == "u8" else m
    plan = S.Plan(b.exec_times, b.weights, S._forced(mm, win[0], win[1]), b.extra_slippage, b.exempt,
                  {"node_run": run["name"], "family": fam})
    doc = S.schedule_document(mm, plan)
    wd = work / "runs" / run["name"].replace("@", "_")
    wd.mkdir(parents=True, exist_ok=True)
    held = sorted({p for r in doc["rows"] for p in r["w"]} | {f["pair"] for f in doc["forced_exits"]})
    pairs = held or [m.pairs[0]]
    spec = EIO.prepare_run(wd, pairs, {p: bars[p] for p in pairs}, doc, run["fee"], win[0], win[1])
    if engine == "docker":
        cmd = EIO.command(spec, keep_trade_copy=keep_trade_copy)
        subprocess.run(["chmod", "-R", "a+rwX", str(wd)], check=False)  # the image runs as a non-root user
    else:
        cmd = [c.replace("/run/", str(wd) + "/") for c in EIO.command(spec, local_python=engine,
                                                                      keep_trade_copy=keep_trade_copy)]
        cfg = json.loads((wd / "config.json").read_text())
        for k in ("datadir", "exportfilename"):
            cfg[k] = cfg[k].replace("/run/", str(wd) + "/")
        cfg["auth2"]["schedule_file"] = cfg["auth2"]["schedule_file"].replace("/run/", str(wd) + "/")
        (wd / "config.json").write_text(json.dumps(cfg, indent=1, sort_keys=True) + "\n")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    (wd / "engine.log").write_text(proc.stdout[-200_000:] + "\n--- stderr ---\n" + proc.stderr[-200_000:])
    out = {"name": run["name"], "spec": spec, "returncode": proc.returncode, "pairs": len(pairs)}
    if proc.returncode != 0 or not list((wd / "user_data" / "backtest_results").glob("*.zip")):
        out["status"] = "ENGINE_FAILED"
        return out
    marks = EIO.read_marks(wd, win[0], win[1])
    fee_seen = engine_fees(wd)
    sched = RP.Schedule(plan.exec_times, plan.weights, plan.forced_exits, plan.extra_slippage, plan.slippage_exempt)
    rm = RP.run(prices, sched, run["fee"], win[0], win[1], whitelist_order=list(np.argsort(m.pairs)))
    par = RP.parity(marks, rm[0])
    out.update({"status": "OK", "result_sha256": EIO.result_sha256(wd), "returns": GT.daily_returns(marks).tolist(),
                "fee_propagation": {"status": "PASS" if fee_seen <= {run["fee"]} else "FAIL",
                                    "configured": run["fee"], "seen": sorted(fee_seen)},
                "parity": par})
    return out


def engine_fees(wd: Path) -> set[float]:
    import zipfile

    z = zipfile.ZipFile(sorted((wd / "user_data" / "backtest_results").glob("*.zip"))[0])
    name = [n for n in z.namelist() if n.endswith(".json") and "config" not in n and "meta" not in n][0]
    st = list(json.loads(z.read(name))["strategy"].values())[0]
    return {float(t["fee_open"]) for t in st["trades"]} | {float(t["fee_close"]) for t in st["trades"]}


def causality(fam: str, m: S.Market, win: tuple[int, int], override) -> dict:
    """C1 LOOKAHEAD and RECURSIVE on every generator the node judges.

    In N-Ax (``override`` = a null fixture) the checks run on the family's own
    generators, the ones the null traverses the procedure for and Ax will run on
    the same data. The null fixtures themselves are not checked: the law defines
    each null over the whole window (A1 shifts by an offset in [90 days, T - 90
    days]; A3 places the primary's episode count and durations at random times),
    so a truncated window changes them by definition, while their placement reads
    no price.
    """
    names = ["primary", "bench", *F.PERTURBATIONS[fam]]
    out = {}
    for n in names:
        def gen(mm, s, e, n=n):
            b = F.bundle(fam, mm, s, e, [n], 0, None)
            return b.exec_times, b.weights[:, 0, :]
        out[n] = {"lookahead": S.lookahead_check(gen, m, win[0], win[1]),
                  "recursive": S.recursive_check(gen, m, win[0], win[1], warmup_days=400)}
    ok = all(v["lookahead"]["status"] == "PASS" and v["recursive"]["status"] == "PASS" for v in out.values())
    rec = {"status": "PASS" if ok else "FAIL", "by_generator": out}
    if override is not None:
        rec["null_fixtures"] = ("not checked: each null is defined over the whole window by the law and reads no "
                                "price (FUNNEL_LAW_2.md CALIBRATION_DAG, Planted edges and nulls)")
    return rec


# -- node kinds ----------------------------------------------------------------------------

def engine_node(node: str, fam: str, m, prices, bars, win, override, work: Path, engine: str, part: int,
                reuse: dict[str, dict]) -> tuple[dict, dict]:
    """Run (this part of) the node's engine plan; returns (series by name, run records)."""
    plan = run_plan(node, fam)
    parts = NODES[node]["parts"]
    mine = [r for i, r in enumerate(plan) if parts == 1 or (i % parts) == (part - 1)]
    records = dict(reuse)
    for r in mine:
        w = SECONDARY if r["window"] == "secondary" else win
        records[r["name"]] = engine_run(r, fam, m, prices, bars, w, override, work, engine)
    series = {n: np.array(rec["returns"]) for n, rec in records.items() if rec.get("status") == "OK"}
    return series, records


def c1_engine(records: dict) -> dict:
    bad_engine = [n for n, r in records.items() if r.get("status") != "OK"]
    bad_fee = [n for n, r in records.items() if r.get("status") == "OK" and r["fee_propagation"]["status"] != "PASS"]
    bad_par = [n for n, r in records.items() if r.get("status") == "OK" and r["parity"]["status"] != "PASS"]
    return {"ENGINE": {"status": "FAIL" if bad_engine else "PASS", "failed": bad_engine},
            "ENGINE_FEE_PROPAGATION": {"status": "FAIL" if bad_fee else "PASS", "failed": bad_fee},
            "REPLAY_PARITY": {"status": "FAIL" if bad_par else "PASS", "failed": bad_par,
                              "by_run": {n: r["parity"] for n, r in records.items() if r.get("status") == "OK"}}}


def holm_pvalue(res: dict) -> float:
    p = res.get("primary_p_value")
    return 1.0 if p is None else float(p)


def strip(records: dict) -> dict:
    return {n: {k: v for k, v in r.items()} for n, r in records.items()}


def run(node: str, part: int, repo: Path, out: Path, pred_dir: Path, cache: Path, engine: str) -> dict:
    if node not in NODES:
        refuse(f"unknown node {node}")
    spec = NODES[node]
    if not 1 <= part <= spec["parts"]:
        refuse(f"{node} has {spec['parts']} part(s)")
    program, program_sha = load_program(repo)
    entry, prereg = node_prereg(repo, program, node)
    ledger = check_ledger(repo, entry["trial_id"], node, entry["prereg_sha256"])
    if ledger["status"] != "PASS":
        refuse(f"LEDGER_CHAIN: {ledger['problems']}")
    if ledger["terminal_records"]:
        refuse(f"{entry['trial_id']} already has a terminal ledger record; a trial never re-runs")
    preds = {}
    for pn, states in predecessors(node):
        rec = load_predecessor(pred_dir, pn, program_sha)
        if rec["terminal_state"] not in states:
            refuse(f"predecessor {pn} ended {rec['terminal_state']}; the DAG edge requires {states}")
        preds[pn] = rec
    fam = spec["family"]
    if kind_is_sc(node) and not preds["HOLM"]["holm_pass"][fam]:
        refuse(f"{fam} did not pass Holm; SC-{fam} is not in the executed DAG")
    work = out / "work" / node
    work.mkdir(parents=True, exist_ok=True)
    record = {"program_id": PROGRAM_ID, "program_sha256": program_sha, "node": node, "part": part,
              "parts": spec["parts"], "kind": spec["kind"], "family": fam, "trial_id": entry["trial_id"],
              "prereg_path": entry["prereg_path"], "prereg_sha256": entry["prereg_sha256"],
              "code_sha256": code_sha256(), "commit": os.environ.get("GITHUB_SHA", "local"),
              "run_id": os.environ.get("GITHUB_RUN_ID", "local"), "ledger": ledger,
              "predecessors": {k: v["_sha256"] for k, v in preds.items()},
              "engine_image": EIO.IMAGE, "real_money_authorized": False, "dry_run": True}
    kind = spec["kind"]
    if kind == "DATA_LOCK":
        record.update(d0(repo, cache))
    elif kind == "CALIBRATION_STAT":
        if preds["D0"]["data_limited"][fam]:
            refuse(f"{fam} is DATA_LIMITED at D0; the family has no further node")
        cal = CA.size_power(fam, prereg["calibration"]["edge"], a3_start(repo), workers=os.cpu_count() or 2)
        record.update({"calibration": cal, "terminal_state": {"PASS": PASS}.get(CA.outcome(cal), CA.outcome(cal))})
    elif kind in ("POSITIVE_CONTROL", "NULL_CALIBRATION", "SCIENTIFIC", "SECONDARY_CONFIRM"):
        record.update(scored_node(node, fam, part, repo, work, pred_dir, cache, engine, prereg, preds, program_sha))
    elif kind == "HOLM":
        record.update(holm(pred_dir, program_sha))
    write_json(out / (f"{node}.part{part}.result.json" if record.get("partial") else f"{node}.result.json"), record)
    return record


def d0(repo: Path, cache: Path) -> dict:
    from auth2 import dataset_v3 as D

    files = D.build(cache, D.A.DEFAULT_BASE, repo)
    bad = [rel for rel, body in files.items() if not (repo / rel).is_file() or (repo / rel).read_bytes() != body]
    lock = json.loads((repo / D.LOCK_REL).read_text())
    return {"data_truth": {"status": "FAIL" if bad else "PASS", "not_identical": bad,
                           "lock_sha256": sha256_file(repo / D.LOCK_REL)},
            "data_limited": lock["data_limited"], "a3_start_utc": lock["a3_start_utc"],
            "terminal_state": INVALID if bad else PASS}


def scored_node(node, fam, part, repo, work, pred_dir, cache, engine, prereg, preds, program_sha) -> dict:
    kind = NODES[node]["kind"]
    win = scored(fam, repo)
    override = ("null", F.N_FIXTURE_SEED) if kind == "NULL_CALIBRATION" else None
    if kind == "POSITIVE_CONTROL":
        m, prices, bars = synthetic_market(fam, prereg["calibration"]["edge"])
        truth = {"status": "PASS", "synthetic_world": {"seed": CA.PC_SEED, "edge": prereg["calibration"]["edge"]}}
    else:
        m, prices, bars, truth = real_market(fam, repo, cache, work)
    reuse = {}
    if kind in ("SCIENTIFIC", "SECONDARY_CONFIRM"):
        nrec = preds["N-" + fam]
        names = ["bench", "bench@x2", "bench@lat", "bench@u8"] if kind == "SCIENTIFIC" else ["bench@sec"]
        for n in names:
            if n in nrec["engine_runs"]:
                reuse[n] = verify_reuse(nrec["engine_runs"][n], n, fam, m, win, work)
    if NODES[node]["parts"] > 1 and part > 1:
        for i in range(1, part):
            prev = load_part(pred_dir, node, i, program_sha)
            reuse.update(prev["engine_runs"])
    series, records = engine_node(node, fam, m, prices, bars, win, override, work, engine, part, reuse)
    out = {"engine_runs": strip(records), "c1": {"DATA_TRUTH": truth}}
    out["engine_invocations"] = sum(1 for n, r in records.items() if n not in reuse)
    if NODES[node]["parts"] > 1 and part < NODES[node]["parts"]:
        out["partial"] = True
        out["terminal_state"] = "PART_COMPLETE"
        return out
    out["c1"].update(c1_engine(records))
    out["c1"]["CAUSALITY"] = causality(fam, m, win, override) if kind != "SECONDARY_CONFIRM" else {"status": "PASS", "note": "generators verified in the family node"}
    c1_ok = all(v["status"] == "PASS" for v in out["c1"].values())
    if not c1_ok:
        out["terminal_state"] = INVALID
        return out
    ev = GT.Evidence(fam, m, prices, win[0], win[1], sec=SECONDARY, engine=series, primary_override=override)
    if kind == "SECONDARY_CONFIRM":
        sc = GT.secondary(ev)
        out["secondary"] = sc
        out["terminal_state"] = "SURVIVED" if sc["status"] == "PASS" else "REJECTED"
        return out
    res = GT.evaluate(ev, early_exit=False, report=True)
    out["evaluation"] = res
    out["replay_calls"] = ev.replay_calls
    if kind == "SCIENTIFIC":
        out["terminal_state"] = res["verdict"]
    elif kind == "NULL_CALIBRATION":
        out["terminal_state"] = "REJECTED" if res["verdict"] == "REJECTED" else "NOT_REJECTED"
    else:
        holm_ok = res["verdict"] == "PRE_HOLM_PASS" and holm_pvalue(res) <= GT.ALPHA_HOLM / GT.HOLM_M
        sc = GT.secondary(ev)
        out["secondary"] = sc
        out["holm_m3_first_step"] = {"p_value": holm_pvalue(res), "level": GT.ALPHA_HOLM / GT.HOLM_M, "pass": holm_ok}
        out["terminal_state"] = "SURVIVED" if (holm_ok and sc["status"] == "PASS") else "NOT_SURVIVED"
    return out


def verify_reuse(rec: dict, name: str, fam: str, m, win, work) -> dict:
    """Reuse an N-node benchmark run only if its schedule is byte-identical (same configuration)."""
    sched_now = rec["spec"]["schedule_sha256"]
    run = {"name": name, "config": "bench", "offset": 1 if name.endswith("@lat") else 0,
           "window": "secondary" if name.endswith("@sec") else "scored", "universe": "u8" if name.endswith("@u8") else "base"}
    w = SECONDARY if run["window"] == "secondary" else win
    b = _bundle_for(run, fam, m, w, None)
    mm = F.u8_market(m) if run["universe"] == "u8" else m
    plan = S.Plan(b.exec_times, b.weights, S._forced(mm, w[0], w[1]), b.extra_slippage, b.exempt,
                  {"node_run": name, "family": fam})
    doc = S.schedule_document(mm, plan)
    body = (json.dumps(doc, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if hashlib.sha256(body).hexdigest() != sched_now:
        refuse(f"benchmark run {name} of the N node is not the same configuration (schedule sha256 differs)")
    return {**rec, "reused_from_node": "N-" + fam}


def load_part(pred_dir: Path, node: str, i: int, program_sha: str) -> dict:
    hits = sorted(pred_dir.rglob(f"{node}.part{i}.result.json"))
    if len(hits) != 1:
        refuse(f"{node} part {i}: expected exactly one partial record")
    rec = json.loads(hits[0].read_text())
    if rec["program_sha256"] != program_sha:
        refuse(f"{node} part {i} was produced under a different program sha256")
    return rec


def family_final(pred_dir: Path, fam: str, program_sha: str) -> dict:
    """The family's state entering HOLM: the scientific node's verdict, or the terminal it reached earlier."""
    order = [("D0", None), (f"CAL-{fam}", PASS), (f"PC-{fam}", "SURVIVED"), (f"N-{fam}", "REJECTED"), (fam, None)]
    d0rec = load_predecessor(pred_dir, "D0", program_sha)
    if d0rec["terminal_state"] != PASS:
        return {"state": "STOP_PROGRAM", "p_value": None}
    if d0rec["data_limited"][fam]:
        return {"state": "DATA_LIMITED", "p_value": None}
    for n, need in order[1:]:
        hits = sorted(pred_dir.rglob(f"{n}.result.json"))
        if not hits:
            refuse(f"HOLM: {fam} has no terminal record (missing {n})")
        rec = load_predecessor(pred_dir, n, program_sha)
        st = rec["terminal_state"]
        if need is not None and st != need:
            mapped = {"LAW_INVALID": "LAW_INVALID", "INCONCLUSIVE_UNDERPOWERED": "INCONCLUSIVE_UNDERPOWERED",
                      "NOT_SURVIVED": "INCONCLUSIVE_UNDERPOWERED", "NOT_REJECTED": "LAW_INVALID"}.get(st, st)
            return {"state": mapped, "p_value": None, "at": n}
        if n == fam:
            p = rec["evaluation"]["primary_p_value"] if st == "PRE_HOLM_PASS" else None
            return {"state": st, "p_value": p, "at": n}
    raise AssertionError


def holm(pred_dir: Path, program_sha: str) -> dict:
    fams = {f: family_final(pred_dir, f, program_sha) for f in F.FAMILIES}
    res = GT.holm_node({f: v["p_value"] for f, v in fams.items()})
    return {"families": fams, "holm": res,
            "holm_pass": {f: bool(res["rejected"][f] and fams[f]["state"] == "PRE_HOLM_PASS") for f in F.FAMILIES},
            "terminal_state": "COMPLETE"}


# -- which node is next (read-only; FUNNEL_LAW_2.md §DAG_OPERATIONS) -----------------------

def scan_results(results_dir: Path) -> dict[str, dict]:
    """Every result record under ``results_dir`` keyed by node (a split node's parts as '<node>.part<i>')."""
    found: dict[str, dict] = {}
    for f in sorted(results_dir.rglob("*.result.json")):
        key = f.name[: -len(".result.json")]
        if key in found:
            refuse(f"two result records for {key}; pass only the run that counts")
        found[key] = json.loads(f.read_text())
    return found


def eligible(results: dict[str, dict]) -> dict:
    """The (node, part) pairs the frozen DAG allows next, given the result records so far.

    A node that ended INVALID_RUN is listed under ``retry`` (one technical retry, enforced by the dispatch
    guard; a second INVALID_RUN stops the program). ``closure`` is True once nothing can run."""
    state = {k: v.get("terminal_state") for k, v in results.items()}
    nxt: list[tuple[str, int]] = []
    retry = sorted(k for k, v in state.items() if v == INVALID)
    if retry:
        return {"next": [], "retry": retry, "closure": False, "families": {}}
    if "D0" not in state:
        return {"next": [("D0", 1)], "retry": [], "closure": False, "families": {}}
    limited = results["D0"].get("data_limited", {})
    fams: dict[str, str] = {}
    for f in F.FAMILIES:
        if limited.get(f):
            fams[f] = "DATA_LIMITED"
            continue
        chain = [f"CAL-{f}", f"PC-{f}", f"N-{f}", f]
        need = {f"CAL-{f}": None, f"PC-{f}": PASS, f"N-{f}": "SURVIVED", f: "REJECTED"}
        prev = None
        for n in chain:
            if prev is not None and state.get(prev) != need[n]:
                fams[f] = state[prev]
                break
            parts = NODES[n]["parts"]
            done = [i for i in range(1, parts + 1) if f"{n}.part{i}" in state] if parts > 1 else []
            if n not in state:
                nxt.append((n, len(done) + 1 if parts > 1 else 1))
                fams[f] = "RUNNING"
                break
            prev = n
        else:
            fams[f] = state[f]
    if not nxt and "HOLM" not in state:
        nxt.append(("HOLM", 1))
    elif "HOLM" in state:
        for f in F.FAMILIES:
            if results["HOLM"]["holm_pass"].get(f) and f"SC-{f}" not in state:
                nxt.append((f"SC-{f}", 1))
    return {"next": nxt, "retry": [], "closure": not nxt, "families": fams}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--next", metavar="RESULTS_DIR", help="print the nodes the DAG allows next and exit")
    ap.add_argument("--node")
    ap.add_argument("--part", type=int, default=1)
    ap.add_argument("--repo", default=".")
    ap.add_argument("--out")
    ap.add_argument("--predecessors", default="predecessors")
    ap.add_argument("--cache-dir", default="dataset-cache/v3")
    ap.add_argument("--engine", default="docker", help="docker (the pinned image) or a local python with freqtrade 2026.7")
    a = ap.parse_args(argv)
    if a.next:
        print(json.dumps(eligible(scan_results(Path(a.next))), indent=1, sort_keys=True))
        return 0
    if not a.node or not a.out:
        ap.error("--node and --out are required")
    rec = run(a.node, a.part, Path(a.repo).resolve(), Path(a.out).resolve(), Path(a.predecessors).resolve(),
              Path(a.cache_dir).resolve(), a.engine)
    print(f"AUTH2_NODE {a.node} part {a.part}: {rec['terminal_state']}")
    # INVALID_RUN fails the job so the dispatch guard allows its one technical retry; every law terminal
    # (including REJECTED, NOT_SURVIVED and INCONCLUSIVE_UNDERPOWERED) is a successful run.
    return 4 if rec["terminal_state"] == INVALID else 0


if __name__ == "__main__":
    sys.exit(main())
