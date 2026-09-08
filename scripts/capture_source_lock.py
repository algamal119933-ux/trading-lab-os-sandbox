#!/usr/bin/env python3
"""Capture an immutable source lock for each approved strategy candidate.

The identity of a research candidate is never "main", "master" or "latest": a
branch name points at different code on different days, and NostalgiaForInfinity
in particular rewrites its canonical strategy file daily. The identity used here
is the tuple the directive names:

    commit SHA + file SHA256 + effective config + parameters

This script reads that tuple out of local mirror clones and emits JSON. It is
deterministic given the same clones, it never writes to a source repository, it
never touches the live runtime, and it has no execution, credential or network
path of its own beyond the git mirrors it is pointed at.

Usage:
    python3 scripts/capture_source_lock.py --source-root /mnt/d/TradingLabResearch/sources
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

# Candidate -> (repo dir, path within the repo at its pinned commit).
# Paths were discovered by searching each tree, never assumed from memory.
CANDIDATES = {
    "A1": ("btc-strategy-lab", "user_data/strategies/EmaCross.py", "EmaCross"),
    "A2": ("btc-strategy-lab", "user_data/strategies/EmaCrossFunding.py", "EmaCrossFunding"),
    "A3": ("freqtrade-strategies-that-work", "EMAPriceCrossoverWithThreshold.py", "EMAPriceCrossoverWithThreshold"),
    "A4": ("freqtrade-strategies", "user_data/strategies/berlinguyinca/ReinforcedAverageStrategy.py", "ReinforcedAverageStrategy"),
    "A5": ("freqtrade-strategies-that-work", "DoubleEMACrossoverWithTrend.py", "DoubleEMACrossoverWithTrend"),
    "A6": ("freqtrade-strategies-that-work", "RSIDirectionalWithTrendSlow.py", "RSIDirectionalWithTrendSlow"),
    # The user_data/strategies path in NFI is a symlink (git mode 120000); the
    # canonical file is at the repository root. Locking the symlink would hash
    # 31 bytes of link text instead of 2.5 MB of strategy.
    "A7": ("NostalgiaForInfinity", "NostalgiaForInfinityX8.py", "NostalgiaForInfinityX8"),
}

PARAMS = {
    "A1": ("btc-strategy-lab", "user_data/strategies/EmaCross.json"),
    "A2": ("btc-strategy-lab", "user_data/strategies/EmaCrossFunding.json"),
}

CONFIGS = {
    "A1": ("btc-strategy-lab", "config.json"),
    "A2": ("btc-strategy-lab", "config.json"),
    "A7": ("NostalgiaForInfinity", "configs/exampleconfig.json"),
}

LICENSE_CANDIDATES = ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING", "NOTICE")

REPO_URLS = {
    "btc-strategy-lab": "https://github.com/wiktorj137/btc-strategy-lab",
    "freqtrade-strategies-that-work": "https://github.com/paulcpk/freqtrade-strategies-that-work",
    "freqtrade-strategies": "https://github.com/freqtrade/freqtrade-strategies",
    "NostalgiaForInfinity": "https://github.com/iterativv/NostalgiaForInfinity",
}


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def git_bytes(repo: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(repo), *args])


def default_branch(repo: Path) -> str:
    """Resolve the default branch from the remote rather than assuming main."""
    try:
        return git(repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD").split("/", 1)[1]
    except subprocess.CalledProcessError:
        return "UNRESOLVED"


def blob_sha256(repo: Path, sha: str, path: str) -> tuple[str | None, int | None, str | None]:
    """SHA256, byte length and git file mode for one path at one commit."""
    try:
        entry = git(repo, "ls-tree", sha, "--", path)
    except subprocess.CalledProcessError:
        return None, None, None
    if not entry:
        return None, None, None
    mode = entry.split()[0]
    data = git_bytes(repo, "show", f"{sha}:{path}")
    return hashlib.sha256(data).hexdigest(), len(data), mode


def licenses_for(repo: Path, sha: str) -> list[dict]:
    tree = git(repo, "ls-tree", "-r", "--name-only", sha).splitlines()
    found = []
    for name in tree:
        if name.split("/")[-1] in LICENSE_CANDIDATES:
            data = git_bytes(repo, "show", f"{sha}:{name}")
            head = data.decode("utf-8", "replace")[:400]
            if "GNU GENERAL PUBLIC LICENSE" in head and "Version 3" in head:
                spdx = "GPL-3.0-only"
            elif head.lstrip().startswith("MIT License"):
                spdx = "MIT"
            elif name.split("/")[-1] == "NOTICE":
                spdx = "NOTICE (attribution file, not a licence grant)"
            else:
                spdx = "UNKNOWN"
            found.append(
                {
                    "file": name,
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "spdx": spdx,
                }
            )
    return found


def build(source_root: Path) -> dict:
    repos: dict[str, dict] = {}
    for name, url in REPO_URLS.items():
        repo = source_root / name
        sha = git(repo, "rev-parse", "origin/HEAD")
        repos[name] = {
            "source_repo": name,
            "source_url": url,
            "default_branch": default_branch(repo),
            "source_commit_sha": sha,
            "source_commit_date": git(repo, "log", "-1", "--format=%cI", sha),
            "licenses": licenses_for(repo, sha),
        }

    out = []
    for cid, (repo_name, path, strategy) in sorted(CANDIDATES.items()):
        repo = source_root / repo_name
        sha = repos[repo_name]["source_commit_sha"]
        digest, size, mode = blob_sha256(repo, sha, path)
        record = {
            "candidate_id": cid,
            "strategy_name": strategy,
            "source_repo": repo_name,
            "source_url": repos[repo_name]["source_url"],
            "default_branch": repos[repo_name]["default_branch"],
            "source_commit_sha": sha,
            "source_commit_date": repos[repo_name]["source_commit_date"],
            "source_file_path": path,
            "source_file_sha256": digest,
            "source_file_bytes": size,
            "source_file_git_mode": mode,
            "source_last_material_update": git(
                repo, "log", "-1", "--format=%cI %h %s", sha, "--", path
            )[:160],
            "licenses": repos[repo_name]["licenses"],
        }
        for label, table in (("parameters", PARAMS), ("config", CONFIGS)):
            entry = table.get(cid)
            if entry:
                d, s, _ = blob_sha256(source_root / entry[0], sha if entry[0] == repo_name else git(source_root / entry[0], "rev-parse", "origin/HEAD"), entry[1])
                record[f"source_{label}_file"] = entry[1]
                record[f"source_{label}_sha256"] = d
                record[f"source_{label}_bytes"] = s
            else:
                record[f"source_{label}_file"] = None
                record[f"source_{label}_sha256"] = None
        out.append(record)

    return {
        "schema_version": "1.0.0",
        "generated_by": "scripts/capture_source_lock.py",
        "identity_contract": "commit SHA + file SHA256 + effective config + parameters",
        "note": (
            "Branch names are not identity. NostalgiaForInfinity rewrites its canonical strategy file "
            "daily, so a lock taken against 'main' would name different code tomorrow."
        ),
        "repositories": [repos[k] for k in sorted(repos)],
        "candidates": out,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("-o", "--out", default=None)
    args = parser.parse_args(argv)

    record = build(Path(args.source_root))
    text = json.dumps(record, indent=2, sort_keys=True) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
