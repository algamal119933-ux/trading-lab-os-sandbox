#!/usr/bin/env python3
"""family_configuration_N — the N LAW of research/cycle2/FUNNEL_LAW_1.md (CYCLE-2 UNIT 7.2 PART A).

N is the number of DISTINCT tested configuration identities in a family, across
cycles, including the configurations of the trial being evaluated. It is not a
trial-ID count: re-running one frozen configuration under a new trial ID is not
a new configuration, and research/trial_ledger.py stays the authority for trial
IDs and accounting only.

Identity = sha256 of the canonical JSON

    {"fixture_sha256s": sorted sha256s of the fixture/schedule files other than
                        the strategy file itself,
     "params":          the configuration's params, canonical,
     "strategy_sha256": sha256 of the strategy file}

Sources, in order:

(a) Cycle 1 — the per-family configuration counts of
    research/RESEARCH_CYCLE1_CLOSURE_1.md §D, frozen in :data:`CYCLE1_FAMILIES`
    and pinned by that file's sha256 (a mismatch is a refusal). Where §D's
    configurations can be resolved to identities from the ledger (the two null
    designs, whose superseding attempt-3 records carry the strategy and
    schedule sha256s) they are listed and cross-checked against the ledger.
    Where they cannot (H1's centre and neighbours, MR's 2x2 grid: their params
    were module constants of the Cycle-1 runners and are not in the ledger),
    only the count and the strategy files are frozen.
(b) Cycle 2 — the grid of every preregistration bound in the ledger for the
    family: a PREREGISTERED record whose dataset_identity names a prereg file
    (`prereg_file`) whose bytes hash to its `prereg_sha256`; plus, optionally,
    the preregistration being evaluated.

Fail-closed: a Cycle-2 configuration that cannot be resolved (prereg file
missing, sha256 mismatch, unreadable grid), or one that shares a strategy file
with a count-only Cycle-1 family and so might coincide with one of its
unlisted configurations, makes N NOT_EVALUABLE — never a guessed or smaller N.

Pure and read-only: reads the closure record, the ledger and preregistration
files; writes nothing; no clock, no randomness, no network.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RESEARCH_DIR = REPO_ROOT / "research"
DEFAULT_LEDGER = RESEARCH_DIR / "records" / "trial_ledger.jsonl"
CLOSURE_RECORD = "research/RESEARCH_CYCLE1_CLOSURE_1.md"
CLOSURE_SHA256 = "de16406d49e6620b1207360e6ad498b642c820fea081eacc3cb08999333432d4"
CYCLE2_EXPERIMENT_PREFIX = "EXP-CYCLE2-"

EVALUATED = "EVALUATED"
NOT_EVALUABLE = "NOT_EVALUABLE"

# RESEARCH_CYCLE1_CLOSURE_1.md §D, "Scientific configurations (13 strategy
# parameter points + 2 null designs)". Frozen; pinned by CLOSURE_SHA256.
CYCLE1_FAMILIES: dict[str, dict] = {
    "BTSL_EMA_REGIME": {
        "configurations": 9,
        "closure_text": "H1 — 1 frozen centre + 8 sensitivity neighbours = 9",
        "strategy_sha256s": ["387cf39f58d266bb63d06865a0784bc2e08676edf54f4610c7d7709bb2a95f24"],
        "designs": None,
    },
    "MEAN_REVERSION": {
        "configurations": 4,
        "closure_text": "Mean-Reversion — 2×2 grid = 4",
        "strategy_sha256s": ["7bf98861338f4e4a79cd96113f8e73185247398c71af801d8756a9f2c65885fc"],
        "designs": None,
    },
    "PIPELINE_NULL_CALIBRATION": {
        "configurations": 2,
        "closure_text": "Null controls — 2 schedule designs",
        "strategy_sha256s": ["e4140750e5d68d4cee7f58c85f1116ea5ba84c810ccbfd784e8298f689386db2",
                             "6d016b207e55359d42b9132445ad292f101dcaa034e86cb4fd5106f93c0a1bbc"],
        # §D: attempts 1 and 2 were technical defects "superseded by attempt 3,
        # which PASSED"; each design's identity is its attempt-3 identity.
        "designs": [
            {"design": "NULL_MATCHED_FREQUENCY", "ledger_trial_id": "TRIAL-NULL-MATCHFREQ-3",
             "strategy_sha256": "e4140750e5d68d4cee7f58c85f1116ea5ba84c810ccbfd784e8298f689386db2",
             "fixture_sha256s": ["35c25a56b47e2370842ba1ba39b0acbf4cc0b23adb35830cfb1ed206b1ab2518"],
             "params": {}},
            {"design": "NULL_BLOCK_SHUFFLED", "ledger_trial_id": "TRIAL-NULL-BLOCKSHUF-3",
             "strategy_sha256": "6d016b207e55359d42b9132445ad292f101dcaa034e86cb4fd5106f93c0a1bbc",
             "fixture_sha256s": ["0081752198f2e275f4d5b00eafdf0bf66fbfabc33be5c7481fbd54c05b6d4d2a"],
             "params": {}},
        ],
    },
}


class ConfigNRefusal(RuntimeError):
    """N cannot be computed at all: the closure pin, the ledger or a frozen cross-check says no."""


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def config_identity(strategy_sha256: str, fixture_sha256s: list[str], params: dict) -> str:
    return hashlib.sha256(canonical({
        "fixture_sha256s": sorted(fixture_sha256s),
        "params": params,
        "strategy_sha256": strategy_sha256,
    }).encode("utf-8")).hexdigest()


def prereg_identities(prereg: dict) -> list[dict]:
    """One identity per grid configuration of a preregistration (raises KeyError/TypeError if malformed)."""
    strategy = prereg["strategy"]
    fixtures = sorted(f["sha256"] for f in prereg.get("fixture_files", []) if f["path"] != strategy["file"])
    out = []
    for cfg in prereg["grid"]:
        if not isinstance(cfg["params"], dict):
            raise TypeError("params is not an object")
        out.append({"config_id": cfg["config_id"], "strategy_sha256": strategy["sha256"],
                    "identity": config_identity(strategy["sha256"], fixtures, cfg["params"])})
    return out


def _ledger(path: Path):
    if str(RESEARCH_DIR) not in sys.path:
        sys.path.insert(0, str(RESEARCH_DIR))
    from trial_ledger import TrialLedger

    return TrialLedger(path)


def check_closure_pin(repo_root: Path | None = None) -> None:
    path = (repo_root or REPO_ROOT) / CLOSURE_RECORD
    if not path.is_file():
        raise ConfigNRefusal(f"{CLOSURE_RECORD} is missing; the Cycle-1 table cannot be trusted")
    actual = sha256_file(path)
    if actual != CLOSURE_SHA256:
        raise ConfigNRefusal(f"{CLOSURE_RECORD} sha256 {actual} != pinned {CLOSURE_SHA256}; "
                             "the frozen Cycle-1 table no longer matches its source")


def _cycle1(family: str, records: list) -> dict:
    entry = CYCLE1_FAMILIES.get(family)
    if entry is None:
        return {"configurations": 0, "identities": [], "resolved": True, "strategy_sha256s": [],
                "closure_text": "family absent from Cycle 1"}
    if entry["designs"] is None:
        return {"configurations": entry["configurations"], "identities": None, "resolved": False,
                "strategy_sha256s": list(entry["strategy_sha256s"]), "closure_text": entry["closure_text"]}
    identities = []
    for d in entry["designs"]:
        # Cross-check the frozen identity against the ledger record it came from.
        matches = [r.payload for r in records if r.payload.get("trial_id") == d["ledger_trial_id"]]
        if not matches:
            raise ConfigNRefusal(f"Cycle-1 design {d['design']}: {d['ledger_trial_id']} is not in the ledger")
        for p in matches:
            code = (p.get("code_identity") or {}).get("sha256")
            sched = (p.get("dataset_identity") or {}).get("schedule_sha256")
            if code != d["strategy_sha256"] or [sched] != d["fixture_sha256s"]:
                raise ConfigNRefusal(f"Cycle-1 design {d['design']}: ledger {d['ledger_trial_id']} identity "
                                     "does not match the frozen table")
        identities.append({"design": d["design"], "strategy_sha256": d["strategy_sha256"],
                           "identity": config_identity(d["strategy_sha256"], d["fixture_sha256s"], d["params"])})
    if len({i["identity"] for i in identities}) != entry["configurations"]:
        raise ConfigNRefusal(f"Cycle-1 {family}: frozen designs do not give {entry['configurations']} "
                             "distinct identities")
    return {"configurations": entry["configurations"], "identities": identities, "resolved": True,
            "strategy_sha256s": list(entry["strategy_sha256s"]), "closure_text": entry["closure_text"]}


def _resolve_bound(payload: dict, repo_root: Path) -> tuple[dict | None, str | None]:
    ident = payload.get("dataset_identity") or {}
    rel, sha = ident.get("prereg_file"), ident.get("prereg_sha256")
    if not rel or not sha:
        return None, "ledger preregistration names no prereg_file / prereg_sha256"
    path = (repo_root / rel).resolve()
    try:
        path.relative_to(repo_root.resolve())
    except ValueError:
        return None, f"prereg_file {rel} lies outside the repository"
    if not path.is_file():
        return None, f"prereg_file {rel} is missing"
    if sha256_file(path) != sha:
        return None, f"prereg_file {rel} does not hash to the ledger's prereg_sha256"
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except ValueError as exc:
        return None, f"prereg_file {rel} is not JSON: {exc}"


def family_configuration_n(family_id: str, *, ledger_path: Path = DEFAULT_LEDGER,
                           extra_preregs: list[dict] = (), repo_root: Path | None = None) -> dict:
    """The N LAW. Returns {status, family_configuration_N, reason, derivation}; refuses (raises
    ConfigNRefusal) only when the closure pin, the ledger chain or a frozen cross-check fails."""
    repo_root = repo_root or REPO_ROOT
    check_closure_pin(repo_root)
    ledger = _ledger(Path(ledger_path))
    problems = ledger.verify()
    if problems:
        raise ConfigNRefusal(f"trial ledger does not verify: {problems}")
    records = ledger.records()
    cycle1 = _cycle1(family_id, records)

    unresolved: list[str] = []
    cycle2: list[dict] = []
    seen_trials: set[str] = set()
    for record in records:
        p = record.payload
        if (p.get("family_id") != family_id or p.get("state") != "PREREGISTERED"
                or not str(p.get("experiment_id", "")).startswith(CYCLE2_EXPERIMENT_PREFIX)):
            continue
        seen_trials.add(p["trial_id"])
        prereg, why = _resolve_bound(p, repo_root)
        if prereg is None:
            unresolved.append(f"{p['trial_id']}: {why}")
            continue
        if prereg.get("trial_id") != p["trial_id"] or prereg.get("family_id") != family_id:
            unresolved.append(f"{p['trial_id']}: prereg file names a different trial or family")
            continue
        try:
            cycle2.append({"trial_id": p["trial_id"], "source": "ledger",
                           "configurations": prereg_identities(prereg)})
        except (KeyError, TypeError) as exc:
            unresolved.append(f"{p['trial_id']}: grid identity unresolvable ({exc!r})")
    for prereg in extra_preregs:
        if prereg.get("family_id") != family_id:
            raise ConfigNRefusal(f"preregistration {prereg.get('trial_id')} is not in family {family_id}")
        if prereg.get("trial_id") in seen_trials:
            continue  # already counted from its bound ledger record
        try:
            cycle2.append({"trial_id": prereg["trial_id"], "source": "evaluated_preregistration",
                           "configurations": prereg_identities(prereg)})
        except (KeyError, TypeError) as exc:
            unresolved.append(f"{prereg.get('trial_id')}: grid identity unresolvable ({exc!r})")

    c2_ids = {c["identity"] for t in cycle2 for c in t["configurations"]}
    c2_strategies = {c["strategy_sha256"] for t in cycle2 for c in t["configurations"]}
    if not cycle1["resolved"]:
        overlap = sorted(c2_strategies & set(cycle1["strategy_sha256s"]))
        if overlap:
            unresolved.append(f"Cycle-1 {family_id} configurations are count-only and share strategy file(s) "
                              f"{overlap} with Cycle-2 configurations; overlap cannot be ruled out")

    trial_ids = sorted({r.payload["trial_id"] for r in records if r.payload.get("family_id") == family_id}
                       | {p["trial_id"] for p in extra_preregs if "trial_id" in p})
    derivation = {
        "closure_record": {"path": CLOSURE_RECORD, "sha256": CLOSURE_SHA256},
        "cycle1": {"configurations": cycle1["configurations"], "closure_text": cycle1["closure_text"],
                   "identities_resolved": cycle1["resolved"],
                   "identities": sorted(i["identity"] for i in cycle1["identities"] or [])},
        "cycle2": cycle2,
        "cycle2_distinct_identities": sorted(c2_ids),
        "trial_id_count_not_n": len(trial_ids),
        "unresolved": unresolved,
    }
    if unresolved:
        return {"family_id": family_id, "status": NOT_EVALUABLE, "family_configuration_N": None,
                "reason": "; ".join(unresolved), "derivation": derivation}
    if cycle1["resolved"]:
        n = len({i["identity"] for i in cycle1["identities"]} | c2_ids)
        how = "distinct identities across Cycle 1 (resolved) and Cycle 2"
    else:
        n = cycle1["configurations"] + len(c2_ids)
        how = ("Cycle-1 count-only configurations plus distinct Cycle-2 identities; disjoint because no "
               "Cycle-2 configuration uses a Cycle-1 strategy file of this family")
    return {"family_id": family_id, "status": EVALUATED, "family_configuration_N": n, "reason": how,
            "derivation": derivation}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--family", required=True)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--prereg", type=Path, action="append", default=[],
                        help="a preregistration being evaluated (counted even if not yet bound)")
    args = parser.parse_args(argv)
    try:
        extra = [json.loads(p.read_text(encoding="utf-8")) for p in args.prereg]
        result = family_configuration_n(args.family, ledger_path=args.ledger, extra_preregs=extra)
    except (ConfigNRefusal, OSError, ValueError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == EVALUATED else 3


if __name__ == "__main__":
    raise SystemExit(main())
