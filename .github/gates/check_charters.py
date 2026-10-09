#!/usr/bin/env python3
"""Validate every CEA-1 charter and evidence ticket.

docs/governance/CONTINUOUS_EXECUTION_AUTHORITY_1.md §1, §13. A charter opens
work, so a malformed one is an authority defect, not a typo:

  · every charters/<ID>.json validates against charters/charter.schema.json,
    its id matches its file name, and its record (.md) exists;
  · its scope can never reach a protected path (.github/gates/protected_paths.txt);
  · unit ids are unique, and every unit_done prerequisite names a unit of the
    same charter;
  · every ticket validates against charters/ticket.schema.json, sits under its
    own charter, and a manual_minutes ticket names the case id of a paid one.

Exit 0 PASS · 2 FAIL.

PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cea_policy as cp  # noqa: E402

CHARTER_SCHEMA = "charters/charter.schema.json"
TICKET_SCHEMA = "charters/ticket.schema.json"


def _validator(schema: dict):
    import jsonschema

    return jsonschema.Draft202012Validator(schema)


def _walk_prereqs(prereqs: list[dict]):
    for p in prereqs:
        yield p
        if p.get("kind") == "any_of":
            yield from _walk_prereqs(p["of"])


def check(repo: Path) -> list[str]:
    problems: list[str] = []
    protected = cp.protected_at(repo, None)
    charter_v = _validator(json.loads((repo / CHARTER_SCHEMA).read_text(encoding="utf-8")))
    ticket_v = _validator(json.loads((repo / TICKET_SCHEMA).read_text(encoding="utf-8")))

    charter_files = sorted(p for p in (repo / cp.CHARTER_DIR).glob("*.json") if not p.name.endswith(".schema.json"))
    ids: set[str] = set()
    for path in charter_files:
        rel = path.relative_to(repo).as_posix()
        charter = json.loads(path.read_text(encoding="utf-8"))
        for err in sorted(charter_v.iter_errors(charter), key=lambda e: list(e.path)):
            problems.append(f"{rel}: schema: {'/'.join(map(str, err.path)) or '<root>'}: {err.message}")
        if problems and any(p.startswith(f"{rel}: schema") for p in problems):
            continue
        cid = charter["id"]
        ids.add(cid)
        if path.stem != cid:
            problems.append(f"{rel}: id {cid} does not match the file name")
        if not (repo / charter["record"]).is_file():
            problems.append(f"{rel}: record {charter['record']} does not exist")
        for scope in charter["scope"]["paths"]:
            for glob, _ in protected:
                if cp.globs_may_overlap(scope, glob):
                    problems.append(f"{rel}: scope {scope!r} can reach protected path {glob!r}")
        unit_ids = [u["id"] for u in charter["units"]]
        if len(unit_ids) != len(set(unit_ids)):
            problems.append(f"{rel}: duplicate unit ids")
        for unit in charter["units"]:
            for p in _walk_prereqs(unit["prerequisites"]):
                if p["kind"] == "unit_done" and p["unit"] not in unit_ids:
                    problems.append(f"{rel}: {unit['id']} depends on unknown unit {p['unit']}")

    ticket_root = repo / cp.TICKET_DIR
    tickets_by_charter: dict[str, list[tuple[str, dict]]] = {}
    for path in sorted(ticket_root.rglob("*.json")) if ticket_root.is_dir() else []:
        rel = path.relative_to(repo).as_posix()
        ticket = json.loads(path.read_text(encoding="utf-8"))
        errors = list(ticket_v.iter_errors(ticket))
        for err in errors:
            problems.append(f"{rel}: schema: {'/'.join(map(str, err.path)) or '<root>'}: {err.message}")
        if errors:
            continue
        if path.parent.name != ticket["charter"] or ticket["charter"] not in ids:
            problems.append(f"{rel}: ticket is not under its own, existing charter")
        if path.stem != ticket["id"]:
            problems.append(f"{rel}: id {ticket['id']} does not match the file name")
        tickets_by_charter.setdefault(ticket["charter"], []).append((rel, ticket))
    for charter_id, tickets in tickets_by_charter.items():
        paid_cases = {t.get("case_id") for _, t in tickets if t["kind"] == "paid" and t.get("case_id")}
        for rel, t in tickets:
            if t["kind"] == "manual_minutes" and t.get("case_id") not in paid_cases:
                problems.append(f"{rel}: manual_minutes ticket must name the case_id of a paid ticket")
            if t["kind"] in ("paid", "manual_minutes") and not t.get("case_id"):
                problems.append(f"{rel}: {t['kind']} ticket needs a case_id")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=".")
    args = ap.parse_args(argv)
    problems = check(Path(args.repo).resolve())
    for p in problems:
        print(f"FAIL  {p}")
    print("CHARTER_CHECK = " + ("FAIL" if problems else "PASS"))
    return 2 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
