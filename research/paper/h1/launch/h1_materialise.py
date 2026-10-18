#!/usr/bin/env python3
"""H1-MATERIALISATION-AMENDMENT-1 (G.2-b): copy H1's three pinned files into a fresh workspace.

    env -i PATH=/usr/bin:/bin python3 -I research/paper/h1/launch/h1_materialise.py \
        --source /home/hamza/projects/trading/tlos-control/.upstream-cache/btc_strategy_lab \
        --workspace-root /home/hamza/tlos-paper/materialise

It replaces H1 launch precondition 5 (PREREGISTRATION.md §9), as recorded in
research/paper/h1/amendments/H1_AMENDMENTS_G6.md. In order, it:

1. refuses to run unless the environment is credential-free (``env -i``);
2. checks the three source files: each must be a regular file (never a symlink), with
   exactly the pinned size and sha256;
3. creates a NEW workspace ``<root>/h1-materialise-<UTC>`` that is outside every git
   worktree and is never reused;
4. copies exactly EmaCross.py, EmaCross.json and LICENSE into
   ``<workspace>/btc_strategy_lab/user_data/strategies/``, the layout cohort.json
   names for H1_PAPER_STRATEGY_DIR;
5. re-hashes the copies and fails closed on any mismatch, deleting the workspace;
6. writes ``<workspace>/MATERIALISATION_RECORD.json``. It sits outside the strategy
   dir, which must hold exactly the three files. Its fields are the ``host_bindings``
   COHORT_START carries.

It never repins, reconstructs, substitutes or edits a byte. It uses the standard
library only, so it runs under ``python3 -I`` with an empty environment. It reads no
key, opens no network connection, and starts nothing. PAPER / RESEARCH ONLY.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# The pins, as research/external/upstream_pins.json (btc_strategy_lab @ b68a5518) and
# research/paper/h1/package/cohort.json record them. They are written out here so the
# procedure can run from a copy of this one file on the launch host. The test suite
# checks they equal both sources.
UPSTREAM_COMMIT = "b68a5518b4a3eba2fde1733160d7d7de356023b5"
PINNED = {
    "EmaCross.py": ("user_data/strategies/EmaCross.py",
                    "387cf39f58d266bb63d06865a0784bc2e08676edf54f4610c7d7709bb2a95f24", 2183),
    "EmaCross.json": ("user_data/strategies/EmaCross.json",
                      "9209a90e5092216af166fd10b9e7415690ab16af0fb3010c7e94e162c027e3ee", 168),
    "LICENSE": ("LICENSE", "3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986", 35149),
}
STRATEGY_SUBDIR = Path("btc_strategy_lab") / "user_data" / "strategies"
RECORD_NAME = "MATERIALISATION_RECORD.json"
# h1_paper.py P2_PATH_MARKERS: a path containing any of these is P2 state.
P2_PATH_MARKERS = ("fp-control", "trading_lab_os_final", "freqtrade/user_data")
# The only variables a credential-free shell may carry. Anything else (a token, a proxy,
# HOME, a key) means the caller did not run under env -i.
ENV_ALLOWLIST = frozenset({"PATH", "LC_ALL", "LANG", "PWD", "SHLVL", "_"})


class MaterialisationError(Exception):
    """Any refusal. Nothing is left behind when one is raised after the workspace exists."""


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_environment(environ: dict[str, str]) -> None:
    extra = sorted(set(environ) - ENV_ALLOWLIST)
    if extra:
        raise MaterialisationError(
            f"the environment is not credential-free (run under env -i); unexpected variables: {extra}")


def _inside_git_worktree(path: Path) -> bool:
    probe = path
    while not probe.exists():
        probe = probe.parent
    git = shutil.which("git", path="/usr/bin:/bin:/usr/local/bin")
    if git is None:
        # Without git, fall back to looking for a .git entry on the way up.
        return any((p / ".git").exists() for p in [probe, *probe.parents])
    result = subprocess.run([git, "-C", str(probe), "rev-parse", "--is-inside-work-tree"],
                            capture_output=True, text=True, env={"PATH": "/usr/bin:/bin"})
    return result.returncode == 0 and result.stdout.strip() == "true"


def verify_source(source: Path, pinned: dict = PINNED) -> dict[str, dict]:
    """Every source file must be a regular file with the pinned size and sha256."""
    found: dict[str, dict] = {}
    problems: list[str] = []
    for name, (rel, digest, size) in pinned.items():
        path = source / rel
        if path.is_symlink() or not path.is_file():
            problems.append(f"{rel}: missing, not a regular file, or a symlink")
            continue
        actual = sha256_file(path)
        if actual != digest:
            problems.append(f"{rel}: sha256 {actual} != pinned {digest}")
        if path.stat().st_size != size:
            problems.append(f"{rel}: size {path.stat().st_size} != pinned {size}")
        found[name] = {"source_path": str(path), "sha256": actual}
    if problems:
        raise MaterialisationError("source verification failed: " + "; ".join(problems))
    return found


def materialise(source: Path, workspace_root: Path, *, pinned: dict = PINNED,
                environ: dict[str, str] | None = None, now: datetime | None = None) -> dict:
    check_environment(dict(os.environ) if environ is None else environ)
    source, workspace_root = source.resolve(), workspace_root.resolve()
    found = verify_source(source, pinned)
    if any(marker in str(workspace_root) for marker in P2_PATH_MARKERS):
        raise MaterialisationError(f"workspace root {workspace_root} is a P2 path")
    if _inside_git_worktree(workspace_root):
        raise MaterialisationError(f"workspace root {workspace_root} is inside a git worktree")
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    workspace = workspace_root / f"h1-materialise-{stamp}"
    if workspace.exists():
        raise MaterialisationError(f"{workspace} exists; a workspace is never reused")
    strategy_dir = workspace / STRATEGY_SUBDIR
    try:
        strategy_dir.mkdir(parents=True)
        files = {}
        for name, (_rel, digest, _size) in pinned.items():
            target = strategy_dir / name
            shutil.copyfile(found[name]["source_path"], target)
            os.chmod(target, 0o444)
            copied = sha256_file(target)
            if copied != digest:
                raise MaterialisationError(f"{name}: copy sha256 {copied} != pinned {digest}")
            files[name] = {"source_path": found[name]["source_path"], "sha256": copied}
        present = sorted(p.name for p in strategy_dir.iterdir())
        if present != sorted(pinned):
            raise MaterialisationError(f"strategy dir holds {present}, expected exactly {sorted(pinned)}")
        record = {
            "record_type": "H1_MATERIALISATION_RECORD",
            "amendment": "H1-MATERIALISATION-AMENDMENT-1 (G.2-b)",
            "cohort_id": "H1-PAPER-COHORT-1",
            "upstream_commit": UPSTREAM_COMMIT,
            "materialised_utc": (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source_dir": str(source),
            "workspace": str(workspace),
            "H1_PAPER_STRATEGY_DIR": str(strategy_dir),
            "files": files,
            "environment": "credential-free (env -i)",
            "procedure_sha256": sha256_file(Path(__file__)),
            "gpl_vendored_into_tlos": False,
            "real_money_authorized": False,
        }
        (workspace / RECORD_NAME).write_text(json.dumps(record, indent=1, sort_keys=True) + "\n",
                                             encoding="utf-8")
        return record
    except BaseException:
        shutil.rmtree(workspace, ignore_errors=True)
        raise


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", required=True, type=Path, help="the recovered btc_strategy_lab directory")
    ap.add_argument("--workspace-root", required=True, type=Path,
                    help="a directory outside every git worktree and every P2 path")
    args = ap.parse_args(argv)
    try:
        record = materialise(args.source, args.workspace_root)
    except MaterialisationError as exc:
        print(f"  - {exc}", file=sys.stderr)
        print("H1_MATERIALISATION = FAIL")
        return 1
    print(json.dumps(record, indent=1, sort_keys=True))
    print("H1_MATERIALISATION = PASS")
    print(f"H1_PAPER_STRATEGY_DIR = {record['H1_PAPER_STRATEGY_DIR']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
