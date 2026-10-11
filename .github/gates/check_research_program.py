#!/usr/bin/env python3
"""Validate precommitted research programs (AUTH-2 structure).

docs/governance/CONTINUOUS_EXECUTION_AUTHORITY_1.md §12. A program is
precommitted only if everything that could be chosen after a result was fixed
before the first one. JSON Schema (charters/research_program.schema.json)
fixes the shape; this adds what a schema cannot see:

  · every node's preregistration exists and its sha256 is the one listed;
  · every frozen hash (funnel law, funnel.py, multiple_testing.py, config_n.py)
    matches the file;
  · the DAG is a DAG: edges name real nodes, no cycle, depth and node count
    inside the declared maxima, and the first node is a null calibration;
  · schema v2 (AUTH-2, OD-7): the first node is the data lock instead, every
    SCIENTIFIC node descends from a NULL_CALIBRATION node of its own family, a
    SECONDARY_CONFIRM node carries its family's scientific trial ID, and the
    trial-ID caps count distinct trial IDs;
  · commit order: the program file was committed before any ledger record of
    any of its nodes (a node recorded first was designed after a result).

No program instance exists at CEA-1 merge. `--self-test` proves the refusals on
synthetic programs without writing anything into the repository.

Exit 0 PASS · 2 FAIL.

PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cea_policy as cp  # noqa: E402

SCHEMA = "charters/research_program.schema.json"
LEDGER = "research/records/trial_ledger.jsonl"


def _sha256(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def _depth(nodes: list[str], edges: list[dict]) -> int | None:
    """Longest path length in nodes, or None if there is a cycle."""
    children: dict[str, list[str]] = {n: [] for n in nodes}
    for e in edges:
        children[e["from"]].append(e["to"])
    memo: dict[str, int] = {}
    visiting: set[str] = set()

    def walk(n: str) -> int | None:
        if n in memo:
            return memo[n]
        if n in visiting:
            return None
        visiting.add(n)
        best = 1
        for c in children[n]:
            d = walk(c)
            if d is None:
                return None
            best = max(best, 1 + d)
        visiting.discard(n)
        memo[n] = best
        return best

    depths = [walk(n) for n in nodes]
    return None if any(d is None for d in depths) else max(depths, default=0)


def ledger_first_records(repo: Path) -> dict[str, datetime]:
    """trial_id -> earliest recorded_utc in the canonical ledger."""
    first: dict[str, datetime] = {}
    path = repo / LEDGER
    if not path.is_file():
        return first
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        tid = rec.get("payload", {}).get("trial_id")
        when = datetime.fromisoformat(rec["recorded_utc"].replace("Z", "+00:00"))
        if tid and (tid not in first or when < first[tid]):
            first[tid] = when
    return first


def program_commit_time(repo: Path, rel: str) -> datetime | None:
    out = subprocess.run(["git", "-C", str(repo), "log", "--diff-filter=A", "--format=%cI", "--", rel],
                         capture_output=True, text=True).stdout.split()
    return datetime.fromisoformat(out[-1]).astimezone(timezone.utc) if out else None


def check_program(repo: Path, program: dict, rel: str, validator, ledger_first: dict[str, datetime],
                  committed_at: datetime | None) -> list[str]:
    problems = [f"{rel}: schema: {'/'.join(map(str, e.path)) or '<root>'}: {e.message}"
                for e in validator.iter_errors(program)]
    if problems:
        return problems
    for key, pin in program["frozen_hashes"].items():
        if _sha256(repo / pin["path"]) != pin["sha256"]:
            problems.append(f"{rel}: frozen hash {key} ({pin['path']}) does not match the file")
    nodes = program["dag"]["nodes"]
    ids = [n["id"] for n in nodes]
    if len(ids) != len(set(ids)):
        problems.append(f"{rel}: duplicate node ids")
    for n in nodes:
        if _sha256(repo / n["prereg_path"]) != n["prereg_sha256"]:
            problems.append(f"{rel}: node {n['id']} preregistration sha256 is not the one listed")
    v2 = program.get("schema_version") == 2
    if v2:
        problems += _v2_problems(rel, nodes, program["dag"]["edges"])
    elif nodes[0]["kind"] != "NULL_CALIBRATION":
        problems.append(f"{rel}: the first node must be a null calibration")
    for e in program["dag"]["edges"]:
        if e["from"] not in ids or e["to"] not in ids:
            problems.append(f"{rel}: edge {e['from']}->{e['to']} names an unknown node")
    if not any(p.endswith("unknown node") for p in problems):
        depth = _depth(ids, program["dag"]["edges"])
        if depth is None:
            problems.append(f"{rel}: the DAG has a cycle")
        elif depth > program["dag"]["max_depth"]:
            problems.append(f"{rel}: depth {depth} exceeds max_depth {program['dag']['max_depth']}")
    if len(nodes) > program["dag"]["max_nodes"]:
        problems.append(f"{rel}: {len(nodes)} nodes exceed max_nodes {program['dag']['max_nodes']}")
    if v2:
        sci = len({n["trial_id"] for n in nodes if n["kind"] in ("SCIENTIFIC", "SECONDARY_CONFIRM")})
        cal = len({n["trial_id"] for n in nodes if n["kind"] not in ("SCIENTIFIC", "SECONDARY_CONFIRM")})
    else:
        sci = sum(1 for n in nodes if n["kind"] == "SCIENTIFIC")
        cal = len(nodes) - sci
    if sci > program["caps"]["scientific_trial_ids"] or cal > program["caps"]["calibration_trial_ids"]:
        problems.append(f"{rel}: the DAG needs more trial IDs than its caps allow")
    for n in nodes:
        first = ledger_first.get(n["trial_id"])
        if first is not None and (committed_at is None or first < committed_at):
            problems.append(f"{rel}: node {n['id']} ({n['trial_id']}) has a ledger record older than the program")
    return problems


def _v2_problems(rel: str, nodes: list[dict], edges: list[dict]) -> list[str]:
    problems = []
    ids = {n["id"]: n for n in nodes}
    if nodes[0]["kind"] != "DATA_LOCK":
        problems.append(f"{rel}: the first node of a v2 program must be the data lock")
    parents: dict[str, set[str]] = {n: set() for n in ids}
    for e in edges:
        if e["to"] in parents and e["from"] in ids:
            parents[e["to"]].add(e["from"])

    def ancestors(n: str, seen: set[str]) -> set[str]:
        for p in parents[n] - seen:
            seen.add(p)
            ancestors(p, seen)
        return seen

    sci_trial = {n["family"]: n["trial_id"] for n in nodes if n["kind"] == "SCIENTIFIC"}
    for n in nodes:
        if n["kind"] == "SCIENTIFIC" and not any(
                ids[a]["kind"] == "NULL_CALIBRATION" and ids[a]["family"] == n["family"]
                for a in ancestors(n["id"], set())):
            problems.append(f"{rel}: scientific node {n['id']} does not descend from a null calibration "
                            f"of family {n['family']}")
        if n["kind"] == "SECONDARY_CONFIRM" and sci_trial.get(n["family"]) != n["trial_id"]:
            problems.append(f"{rel}: secondary node {n['id']} does not carry its family's scientific trial ID")
    return problems


def check(repo: Path) -> list[str]:
    import jsonschema

    validator = jsonschema.Draft202012Validator(json.loads((repo / SCHEMA).read_text(encoding="utf-8")))
    ledger_first = ledger_first_records(repo)
    problems: list[str] = []
    for path in sorted((repo / cp.PROGRAM_DIR).glob("*.json")) if (repo / cp.PROGRAM_DIR).is_dir() else []:
        rel = path.relative_to(repo).as_posix()
        program = json.loads(path.read_text(encoding="utf-8"))
        problems += check_program(repo, program, rel, validator, ledger_first, program_commit_time(repo, rel))
        if path.stem != program.get("program_id"):
            problems.append(f"{rel}: program_id does not match the file name")
    return problems


def synthetic_program(repo: Path) -> dict:
    """A valid program over files that exist, for --self-test and the tests."""
    def pin(path: str) -> dict:
        return {"path": path, "sha256": _sha256(repo / path)}

    null = "research/cycle2/prereg/TRIAL-C2-NULL-MATCHFREQ-1.json"
    sci = "research/cycle2/prereg/TRIAL-C2-TREND-DONCHIAN-1.json"
    return {
        "program_id": "SELF-TEST-PROGRAM",
        "version": 1,
        "status": "ACTIVE",
        "families": [{"id": "SELF_TEST_FAMILY", "hypothesis_class": "synthetic", "inherited_n": 0}],
        "dataset_lock": "research/datasets/dataset_v2.lock.json",
        "development_window": {"start": "2021-01-01", "end": "2024-12-31"},
        "holdout_law": "prospective paper only (OPENING-1 §5 Option B)",
        "frozen_hashes": {
            "funnel_law": pin("research/cycle2/FUNNEL_LAW_1.md"),
            "funnel_py": pin("research/cycle2/funnel.py"),
            "multiple_testing_py": pin("research/cycle2/multiple_testing.py"),
            "config_n_py": pin("research/cycle2/config_n.py"),
        },
        "n_law": "cumulative family N (research/cycle2/config_n.py)",
        "caps": {"configurations": 6, "scientific_trial_ids": 1, "calibration_trial_ids": 1,
                 "engine_invocations": 30, "hyperopt": 0},
        "dag": {
            "nodes": [
                {"id": "N0", "trial_id": "SELF-TEST-NULL", "kind": "NULL_CALIBRATION",
                 "prereg_path": null, "prereg_sha256": _sha256(repo / null)},
                {"id": "N1", "trial_id": "SELF-TEST-SCI", "kind": "SCIENTIFIC",
                 "prereg_path": sci, "prereg_sha256": _sha256(repo / sci)},
            ],
            "edges": [{"from": "N0", "on": "REJECTED", "to": "N1"}],
            "max_depth": 2,
            "max_nodes": 2,
        },
        "null_calibration_first": True,
        "stop_rules": ["any cap", "calibration FAIL", "integrity FAIL", "DAG exhausted"],
        "terminal": "closure_record",
    }


def synthetic_program_v2(repo: Path) -> dict:
    """A valid schema-v2 program (data lock first, per-family null ancestry) over existing files."""
    p = synthetic_program(repo)
    lock = "research/datasets/dataset_v2.lock.json"
    null, sci = p["dag"]["nodes"][0]["prereg_path"], p["dag"]["nodes"][1]["prereg_path"]
    p["schema_version"] = 2
    p["caps"].update(attributed_linux_minutes=100, paid_actions_overage_usd=0, llm_agent_tokens=0,
                     calibration_trial_ids=2)
    p["dag"] = {
        "nodes": [
            {"id": "D0", "trial_id": "SELF-TEST-D0", "kind": "DATA_LOCK", "family": None,
             "prereg_path": lock, "prereg_sha256": _sha256(repo / lock)},
            {"id": "N0", "trial_id": "SELF-TEST-NULL", "kind": "NULL_CALIBRATION", "family": "SELF_TEST_FAMILY",
             "prereg_path": null, "prereg_sha256": _sha256(repo / null)},
            {"id": "N1", "trial_id": "SELF-TEST-SCI", "kind": "SCIENTIFIC", "family": "SELF_TEST_FAMILY",
             "prereg_path": sci, "prereg_sha256": _sha256(repo / sci)},
            {"id": "S1", "trial_id": "SELF-TEST-SCI", "kind": "SECONDARY_CONFIRM", "family": "SELF_TEST_FAMILY",
             "prereg_path": sci, "prereg_sha256": _sha256(repo / sci)},
        ],
        "edges": [{"from": "D0", "on": "PASS", "to": "N0"}, {"from": "N0", "on": "REJECTED", "to": "N1"},
                  {"from": "N1", "on": "PRE_HOLM_PASS", "to": "S1"}],
        "max_depth": 4,
        "max_nodes": 4,
    }
    return p


def self_test(repo: Path) -> list[str]:
    """Each refusal must fire on its own mutation; the valid program must pass."""
    import jsonschema

    validator = jsonschema.Draft202012Validator(json.loads((repo / SCHEMA).read_text(encoding="utf-8")))
    now = datetime.now(timezone.utc)
    base = synthetic_program(repo)
    failures: list[str] = []
    if check_program(repo, base, "self-test", validator, {}, now):
        failures.append("the valid synthetic program was refused")

    def expect(name: str, mutate, ledger=None) -> None:
        p = copy.deepcopy(base)
        mutate(p)
        if not check_program(repo, p, "self-test", validator, ledger or {}, now):
            failures.append(f"refusal did not fire: {name}")

    expect("prereg sha256 not the one listed", lambda p: p["dag"]["nodes"][1].update(prereg_sha256="0" * 64))
    expect("frozen hash mismatch", lambda p: p["frozen_hashes"]["funnel_py"].update(sha256="0" * 64))
    expect("edge on a non-terminal state", lambda p: p["dag"]["edges"][0].update(on="LOOKS_PROMISING"))
    expect("hyperopt not 0", lambda p: p["caps"].update(hyperopt=1))
    expect("missing cap", lambda p: p["caps"].pop("engine_invocations"))
    expect("first node not a null", lambda p: p["dag"]["nodes"].reverse())
    expect("cycle", lambda p: p["dag"]["edges"].append({"from": "N1", "on": "REJECTED", "to": "N0"}))
    expect("ledger record older than the program", lambda p: None,
           ledger={"SELF-TEST-SCI": datetime(2000, 1, 1, tzinfo=timezone.utc)})
    expect("DAG needs more trial IDs than the caps", lambda p: p["caps"].update(scientific_trial_ids=0))
    expect("v1 program using a v2 node kind", lambda p: p["dag"]["nodes"][1].update(kind="POSITIVE_CONTROL"))
    expect("v1 program using a v2 edge state", lambda p: p["dag"]["edges"][0].update(on="PASS"))

    v2 = synthetic_program_v2(repo)
    if check_program(repo, v2, "self-test-v2", validator, {}, now):
        failures.append("the valid synthetic v2 program was refused")

    def expect_v2(name: str, mutate) -> None:
        p = copy.deepcopy(v2)
        mutate(p)
        if not check_program(repo, p, "self-test-v2", validator, {}, now):
            failures.append(f"refusal did not fire: v2 {name}")

    def no_null_ancestor(p: dict) -> None:
        p["dag"]["edges"][1] = {"from": "D0", "on": "PASS", "to": "N1"}

    expect_v2("first node not the data lock", lambda p: p["dag"]["nodes"].insert(0, p["dag"]["nodes"].pop(1)))
    expect_v2("scientific node without a null of its family above it", no_null_ancestor)
    expect_v2("null of another family", lambda p: p["dag"]["nodes"][1].update(family="OTHER"))
    expect_v2("secondary node with another trial ID", lambda p: p["dag"]["nodes"][3].update(trial_id="X"))
    expect_v2("node without a family", lambda p: p["dag"]["nodes"][2].pop("family"))
    expect_v2("missing attributed-minutes cap", lambda p: p["caps"].pop("attributed_linux_minutes"))
    expect_v2("paid overage not USD 0", lambda p: p["caps"].update(paid_actions_overage_usd=5))
    expect_v2("agent tokens not 0", lambda p: p["caps"].update(llm_agent_tokens=1))
    expect_v2("hyperopt not 0", lambda p: p["caps"].update(hyperopt=1))
    expect_v2("edge on a non-terminal state", lambda p: p["dag"]["edges"][0].update(on="LOOKS_PROMISING"))
    expect_v2("calibration trial IDs over the cap", lambda p: p["caps"].update(calibration_trial_ids=1))
    return failures


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=".")
    ap.add_argument("--self-test", action="store_true", help="prove every refusal on synthetic programs")
    args = ap.parse_args(argv)
    repo = Path(args.repo).resolve()
    problems = check(repo)
    if args.self_test:
        problems += [f"self-test: {f}" for f in self_test(repo)]
    programs = len(list((repo / cp.PROGRAM_DIR).glob("*.json"))) if (repo / cp.PROGRAM_DIR).is_dir() else 0
    for p in problems:
        print(f"FAIL  {p}")
    print(f"RESEARCH_PROGRAMS = {programs}")
    print("RESEARCH_PROGRAM_CHECK = " + ("FAIL" if problems else "PASS"))
    return 2 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
