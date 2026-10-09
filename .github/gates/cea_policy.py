#!/usr/bin/env python3
"""Shared policy reading for the CEA-1 gates.

docs/governance/CONTINUOUS_EXECUTION_AUTHORITY_1.md §3-§5. One place that knows
how a protected-path glob matches, where the policy files live, and how to read
them at a git revision rather than from whatever happens to be checked out:
merge_law.py must judge a PR by the policy on its BASE, and a reader that
silently fell back to the working tree would let the PR judge itself.

It lives under .github/gates/ for the reason check_t0_authority.py gives:
scripts/*.py is RUNTIME_TREE (P2 contract section 5), and nothing here can
change what the runtime does.

PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import json
import re
import subprocess
from functools import lru_cache
from pathlib import Path

PROTECTED_PATHS = ".github/gates/protected_paths.txt"
AUTONOMY_STATE = ".github/gates/AUTONOMY_STATE.json"
ACTIVATION = ".github/gates/ACTIVATION.json"
CHARTER_DIR = "charters"
PROGRAM_DIR = "charters/programs"
TICKET_DIR = "charters/tickets"
CHARTER_BRANCH = re.compile(r"^auto/(?P<charter>[A-Z0-9][A-Z0-9-]*)/(?P<unit>[A-Za-z0-9][A-Za-z0-9.-]*)$")
ALWAYS_ALLOWED = ("MANIFEST.txt",)
ACTIVATION_FLAGS = ("platform_enforcement", "executor_identity", "executor_proven", "p2_closed")


@lru_cache(maxsize=None)
def _glob_regex(pattern: str) -> re.Pattern[str]:
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(out) + r"\Z")


def glob_match(pattern: str, path: str) -> bool:
    """`*` stays inside one path segment; `**` crosses segments."""
    return _glob_regex(pattern).match(path) is not None


def literal_prefix(pattern: str) -> str:
    cut = min((i for i, c in enumerate(pattern) if c in "*?"), default=len(pattern))
    return pattern[:cut]


def globs_may_overlap(a: str, b: str) -> bool:
    """Conservative: True whenever some path could match both globs.

    Used to prove a charter scope never reaches a protected path. A false
    positive only refuses a charter; a false negative would let a charter
    authorize a protected path, so the test errs towards overlap.
    """
    pa, pb = literal_prefix(a), literal_prefix(b)
    if not (pa.startswith(pb) or pb.startswith(pa)):
        return False
    if glob_match(a, pb) or glob_match(b, pa):
        return True
    probe_a, probe_b = pa + "x", pb + "x"
    if glob_match(b, probe_a) or glob_match(a, probe_b):
        return True
    # Both have wildcards after a shared prefix: only a literal mismatch after
    # the wildcard could keep them apart, which this check does not attempt.
    return ("*" in a[len(pa):] or "?" in a[len(pa):]) and ("*" in b[len(pb):] or "?" in b[len(pb):])


def parse_protected(text: str) -> list[tuple[str, bool]]:
    """[(glob, is_future)] from protected_paths.txt."""
    out: list[tuple[str, bool]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        future = False
        if "#" in line:
            line, comment = (part.strip() for part in line.split("#", 1))
            future = comment == "future"
        out.append((line, future))
    return out


def is_protected(path: str, globs: list[tuple[str, bool]]) -> bool:
    return any(glob_match(g, path) for g, _ in globs)


# -- reading policy at a revision -------------------------------------------


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          check=True).stdout


def read_at(repo: Path, rev: str | None, path: str) -> str | None:
    """A file's text at `rev`, or in the working tree when rev is None; None if absent."""
    if rev is None:
        p = repo / path
        return p.read_text(encoding="utf-8") if p.is_file() else None
    probe = subprocess.run(["git", "-C", str(repo), "show", f"{rev}:{path}"],
                           capture_output=True, text=True)
    return probe.stdout if probe.returncode == 0 else None


def list_at(repo: Path, rev: str | None, directory: str) -> list[str]:
    """Every file path under `directory` at `rev` (working tree when None)."""
    if rev is None:
        root = repo / directory
        if not root.is_dir():
            return []
        return sorted(p.relative_to(repo).as_posix() for p in root.rglob("*") if p.is_file())
    out = git(repo, "ls-tree", "-r", "--name-only", rev, "--", directory)
    return sorted(line for line in out.splitlines() if line.strip())


def json_at(repo: Path, rev: str | None, path: str):
    text = read_at(repo, rev, path)
    return None if text is None else json.loads(text)


def protected_at(repo: Path, rev: str | None) -> list[tuple[str, bool]]:
    text = read_at(repo, rev, PROTECTED_PATHS)
    if text is None:
        raise FileNotFoundError(f"{PROTECTED_PATHS} is absent at {rev or 'the working tree'}")
    return parse_protected(text)


def charters_at(repo: Path, rev: str | None) -> dict[str, dict]:
    """{charter id: charter} for every charters/<ID>.json (schemas excluded)."""
    found: dict[str, dict] = {}
    for path in list_at(repo, rev, CHARTER_DIR):
        rel = path[len(CHARTER_DIR) + 1:]
        if "/" in rel or not rel.endswith(".json") or rel.endswith(".schema.json"):
            continue
        charter = json_at(repo, rev, path)
        found[charter["id"]] = charter
    return found


def tickets_at(repo: Path, rev: str | None, charter_id: str) -> list[dict]:
    out = []
    for path in list_at(repo, rev, f"{TICKET_DIR}/{charter_id}"):
        if path.endswith(".json"):
            out.append(json_at(repo, rev, path))
    return out


def programs_at(repo: Path, rev: str | None) -> dict[str, dict]:
    found: dict[str, dict] = {}
    for path in list_at(repo, rev, PROGRAM_DIR):
        if path.endswith(".json"):
            program = json_at(repo, rev, path)
            found[program["program_id"]] = program
    return found


def auto_merge_active(activation: dict, autonomy: dict) -> tuple[bool, list[str]]:
    """CEA-1 §5: every flag must hold. Returns (active, the flags that do not)."""
    missing = [f for f in ACTIVATION_FLAGS if not activation.get(f)]
    if autonomy.get("state") != "ACTIVE":
        missing.append("AUTONOMY_STATE")
    return (not missing, missing)
