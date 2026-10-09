#!/usr/bin/env python3
"""What authorized useful work remains unblocked? — the CEA-1 resolver.

docs/governance/CONTINUOUS_EXECUTION_AUTHORITY_1.md §2, §6, §8, §9. Every tick
of the durable executor starts here. It is deterministic and stateless: the
same main checkout and the same GitHub snapshot give byte-identical output, and
nothing is remembered between runs. It reads; it never writes, pushes, opens or
merges anything.

Inputs
  main     the checkout (charters, tickets, programs, AUTONOMY_STATE, ACTIVATION)
  GitHub   open PRs, merged PR heads and auto/* branches — from `gh api`, or from
           --fixtures FILE (a JSON snapshot) in tests and dry runs

A unit's branch is auto/<CHARTER>/<UNIT>. The name is the lease: a branch that
exists means the unit is in flight and is resumed, never duplicated; a merged PR
from it means the unit is done.

Only --dry-run exists in CEA-1.

PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cea_policy as cp  # noqa: E402


def unit_branch(charter_id: str, unit_id: str) -> str:
    return f"auto/{charter_id}/{unit_id}"


def _prereq_holds(p: dict, repo: Path, rev: str | None, done: set[str], tickets: list[dict]) -> bool:
    kind = p["kind"]
    if kind == "file_exists":
        return cp.read_at(repo, rev, p["path"]) is not None
    if kind == "unit_done":
        return p["unit"] in done
    if kind == "evidence_ticket":
        return sum(1 for t in tickets if t.get("kind") == p["ticket_kind"]) >= p["count"]
    if kind == "any_of":
        return any(_prereq_holds(q, repo, rev, done, tickets) for q in p["of"])
    return False


def _describe(p: dict) -> str:
    if p["kind"] == "any_of":
        return "any_of(" + " | ".join(_describe(q) for q in p["of"]) + ")"
    if p["kind"] == "evidence_ticket":
        return f"evidence_ticket({p['ticket_kind']} x{p['count']})"
    return f"{p['kind']}({p.get('path') or p.get('unit')})"


def resolve(repo: Path, github: dict, rev: str | None = None) -> dict:
    autonomy = cp.json_at(repo, rev, cp.AUTONOMY_STATE) or {"state": "SUSPENDED", "revoked_programs": []}
    activation = cp.json_at(repo, rev, cp.ACTIVATION) or {}
    auto_active, missing = cp.auto_merge_active(activation, autonomy)
    suspended = autonomy.get("state") != "ACTIVE"
    revoked = set(autonomy.get("revoked_programs", []))

    open_prs = sorted(github.get("open_prs", []), key=lambda pr: pr["number"])
    open_heads = {pr["head_ref"]: pr for pr in open_prs}
    merged_heads = set(github.get("merged_heads", []))
    branches = set(github.get("branches", []))
    armed = [pr for pr in open_prs if pr.get("auto_merge")]

    lanes: list[dict] = []
    for cid, charter in sorted(cp.charters_at(repo, rev).items(), key=lambda kv: (kv[1]["priority"], kv[0])):
        tickets = cp.tickets_at(repo, rev, cid)
        done = {u["id"] for u in charter["units"] if unit_branch(cid, u["id"]) in merged_heads}
        lane = {"lane": charter["lane"], "charter": cid, "status": charter["status"], "done": sorted(done),
                "eligible_units": [], "in_flight": [], "blocked_units": [], "blockers": [], "owner_required": []}
        if charter["status"] != "ACTIVE" or cid in revoked or suspended:
            reason = "AUTONOMY_SUSPENDED" if suspended else f"CHARTER_{charter['status'] if cid not in revoked else 'REVOKED'}"
            lane["blockers"].append({"class": "AUTHORITY", "scope": cid, "authority_ref": reason})
            lanes.append(lane)
            continue
        for unit in charter["units"]:
            uid, branch = unit["id"], unit_branch(cid, unit["id"])
            if uid in done:
                continue
            if branch in open_heads or branch in branches:
                pr = open_heads.get(branch)
                entry = {"unit": uid, "branch": branch, "pr": pr["number"] if pr else None,
                         "merge_class": unit["merge_class"]}
                lane["in_flight"].append(entry)
                if pr and (unit["merge_class"] == "OWNER" or not auto_active):
                    lane["owner_required"].append({"unit": uid, "pr": pr["number"], "action": "OWNER_MERGE"})
                continue
            unmet = [_describe(p) for p in unit["prerequisites"]
                     if not _prereq_holds(p, repo, rev, done, tickets)]
            if unmet:
                lane["blocked_units"].append({"unit": uid, "unmet": unmet})
            else:
                lane["eligible_units"].append({"unit": uid, "branch": branch, "merge_class": unit["merge_class"]})
        lanes.append(lane)

    programs = cp.programs_at(repo, rev)
    research = {"lane": "RESEARCH", "status": "NO_PROGRAM" if not programs else "PROGRAMS_PRESENT",
                "programs": sorted(programs), "blockers": []}
    if programs:
        research["blockers"].append({"class": "ENGINEERING", "scope": "RESEARCH",
                                     "authority_ref": "DAG resolution is implemented with the first AUTH-2 program"})
    lanes.append(research)

    blockers = []
    if len(armed) > 1:
        blockers.append({"class": "SAFETY", "scope": "MAIN",
                         "authority_ref": f"CEA-1 §6: {len(armed)} armed PRs, at most 1 allowed"})

    if suspended:
        next_action = "EXIT: AUTONOMY_SUSPENDED"
    elif blockers:
        next_action = "EXIT: " + blockers[0]["authority_ref"]
    else:
        in_flight = [(l["charter"], f) for l in lanes if l.get("in_flight") for f in l["in_flight"]]
        eligible = [(l["charter"], e) for l in lanes if l.get("eligible_units") for e in l["eligible_units"]]
        if in_flight:
            c, f = in_flight[0]
            next_action = f"RESUME {f['branch']}" + (f" (PR #{f['pr']})" if f["pr"] else "")
        elif eligible:
            c, e = eligible[0]
            next_action = f"START {e['branch']}"
        else:
            next_action = "IDLE"

    return {
        "autonomy_state": autonomy.get("state"),
        "activation": {f: activation.get(f) for f in cp.ACTIVATION_FLAGS},
        "auto_merge": "ACTIVE" if auto_active else "INACTIVE",
        "auto_merge_missing": missing,
        "armed_pr": armed[0]["number"] if len(armed) == 1 else None,
        "lanes": lanes,
        "blockers": blockers,
        "next_action": next_action,
    }


def github_snapshot(repo_slug: str) -> dict:
    """Read-only GitHub state via `gh api`."""
    def api(path: str) -> list[dict]:
        out = subprocess.run(["gh", "api", "--paginate", path], capture_output=True, text=True, check=True).stdout
        return json.loads(out.replace("][", ",")) if out.strip() else []

    open_prs = [{"number": p["number"], "head_ref": p["head"]["ref"], "auto_merge": p.get("auto_merge") is not None}
                for p in api(f"repos/{repo_slug}/pulls?state=open&per_page=100")]
    merged = [p["head"]["ref"] for p in api(f"repos/{repo_slug}/pulls?state=closed&per_page=100")
              if p.get("merged_at") and p["head"]["ref"].startswith("auto/")]
    branches = [b["name"] for b in api(f"repos/{repo_slug}/branches?per_page=100") if b["name"].startswith("auto/")]
    return {"open_prs": open_prs, "merged_heads": sorted(merged), "branches": sorted(branches)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=".", help="main checkout (default: .)")
    ap.add_argument("--rev", help="read the policy at this revision instead of the working tree")
    ap.add_argument("--fixtures", help="GitHub snapshot JSON instead of live `gh api`")
    ap.add_argument("--github-repo", help="owner/name for live reads")
    ap.add_argument("--dry-run", action="store_true", help="report only (the only mode in CEA-1)")
    args = ap.parse_args(argv)
    if not args.dry_run:
        print("REFUSED: only --dry-run exists under CEA-1", file=sys.stderr)
        return 2
    repo = Path(args.repo).resolve()
    if args.fixtures:
        github = json.loads(Path(args.fixtures).read_text(encoding="utf-8"))
    else:
        if not args.github_repo:
            print("REFUSED: --github-repo or --fixtures is required", file=sys.stderr)
            return 2
        github = github_snapshot(args.github_repo)
    print(json.dumps(resolve(repo, github, args.rev), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
