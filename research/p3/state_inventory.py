"""P3-PLN-02 State & Recovery Inventory: every stateful file, its class, and its proven recovery source.

docs/p3/P3_CONTRACT.md §3, PLN-02. Acceptance: the inventory covers 100% of the state under each
declared root, and every class has a *verified* recovery source.

This is the small missing layer the contract's reuse law (§10) permits. It builds nothing that
already exists. It classifies files against the declared classes in
``research/p3/records/state_classes.json`` and verifies each class through tooling the project
already trusts:

    GIT_REMOTE      the tracked tree is clean and HEAD is reachable from a remote-tracking ref
    SEALED_ARCHIVE  the archive is published (Tier 2) and rehashes against its sealed manifest
                    (scripts/publish_evidence_digest.py verify_archive, unchanged)
    DATASET_LOCK    the raw sha256 equals research/datasets/dataset_v2.lock.json raw_file_hashes
    COLD_BACKUP     the file's sha256 is in a cold-backup manifest (sha256sum format); a different
                    hash is STALE, and an absent one is MISSING
    DISPOSABLE      derived and regenerable (virtualenvs, bytecode, caches); no recovery is owed

It reads only and writes nothing outside ``--json``. A file that no class claims, or a directory
that cannot be read, is a coverage failure: the inventory cannot vouch for what it cannot see.

PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

PASS, STALE, MISSING, FAIL, UNVERIFIED = "PASS", "STALE", "MISSING", "FAIL", "UNVERIFIED"
RECOVERY_KINDS = ("GIT_REMOTE", "SEALED_ARCHIVE", "DATASET_LOCK", "COLD_BACKUP", "DISPOSABLE")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass
class StateClass:
    id: str
    authority: str
    recovery: str
    globs: list[str] = field(default_factory=list)
    tracked: bool = False
    sealed_archives: bool = False

    def __post_init__(self) -> None:
        if self.recovery not in RECOVERY_KINDS:
            raise ValueError(f"class {self.id}: unknown recovery kind {self.recovery!r}")


def load_classes(path: Path, profile: str = "runtime") -> list[StateClass]:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    profiles = document["profiles"]
    if profile not in profiles:
        raise ValueError(f"unknown profile {profile!r}; declared: {sorted(profiles)}")
    classes = [StateClass(**entry) for entry in profiles[profile]]
    ids = [c.id for c in classes]
    if len(ids) != len(set(ids)):
        raise ValueError(f"duplicate class ids in {path}")
    return classes


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)


def tracked_files(root: Path) -> set[str]:
    result = _git(root, "ls-files", "-z")
    if result.returncode != 0:
        return set()
    return {p for p in result.stdout.split("\0") if p}


def walk(root: Path) -> tuple[list[str], list[str]]:
    """Every file and symlink under root (``.git`` excluded), and every unreadable directory."""
    files, unreadable = [], []

    def onerror(error: OSError) -> None:
        unreadable.append(os.path.relpath(error.filename, root))

    for current, dirs, names in os.walk(root, onerror=onerror, followlinks=False):
        rel_dir = os.path.relpath(current, root)
        if rel_dir == ".git" or rel_dir.startswith(".git" + os.sep):
            dirs[:] = []
            continue
        dirs[:] = [d for d in dirs if not (rel_dir == "." and d == ".git")]
        for d in list(dirs):
            if os.path.islink(os.path.join(current, d)):
                dirs.remove(d)
                names.append(d)
        for name in names:
            rel = os.path.normpath(os.path.join(rel_dir, name))
            files.append(rel)
    return sorted(files), sorted(set(unreadable))


def _matches(rel: str, globs: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(rel, g) for g in globs)


def classify(files: list[str], tracked: set[str], classes: list[StateClass],
             sealed: set[str]) -> tuple[dict[str, list[str]], list[str]]:
    """First matching class wins. Returns {class id: [files]} and the unclassified files."""
    assigned: dict[str, list[str]] = {c.id: [] for c in classes}
    unclassified = []
    for rel in files:
        for cls in classes:
            if cls.tracked:
                hit = rel in tracked
            elif cls.sealed_archives:
                parts = rel.split(os.sep)
                hit = len(parts) > 2 and parts[0] == "artifacts" and parts[1] in sealed
            else:
                hit = rel not in tracked and _matches(rel, cls.globs)
            if hit:
                assigned[cls.id].append(rel)
                break
        else:
            unclassified.append(rel)
    return assigned, unclassified


# -- recovery verifiers -------------------------------------------------------


def verify_git_remote(root: Path, _files: list[str]) -> dict:
    head = _git(root, "rev-parse", "HEAD").stdout.strip()
    remotes = _git(root, "branch", "-r", "--contains", head).stdout.split() if head else []
    dirty = _git(root, "status", "--porcelain", "--untracked-files=no").stdout.strip()
    if not head or not remotes:
        return {"status": FAIL, "detail": f"HEAD {head or '?'} is not reachable from any remote-tracking ref"}
    if dirty:
        return {"status": STALE, "detail": "tracked files differ from HEAD; uncommitted changes are not recoverable"}
    return {"status": PASS, "detail": f"HEAD {head[:12]} on a remote-tracking ref; tracked tree clean"}


def verify_sealed(root: Path, files: list[str], sealed: set[str],
                  verifier: Callable[[Path], object]) -> dict:
    present = sorted({f.split(os.sep)[1] for f in files})
    failures = []
    for name in present:
        try:
            verifier(root / "artifacts" / name)
        except Exception as exc:  # noqa: BLE001 — any refusal is a failed recovery source
            failures.append(f"{name}: {exc}")
    if failures:
        return {"status": FAIL, "archives": present, "detail": failures}
    return {"status": PASS, "archives": present,
            "detail": f"{len(present)} published archive(s) rehash against their sealed manifests"}


def _dataset_key(rel: str) -> str | None:
    # dataset-cache/binance/BTC_USDT-1h.feather -> "BTC/USDT 1h"
    stem = Path(rel).name
    if not stem.endswith(".feather") or "-" not in stem:
        return None
    pair, timeframe = stem[: -len(".feather")].rsplit("-", 1)
    return f"{pair.replace('_', '/', 1)} {timeframe}"


def verify_dataset(root: Path, files: list[str], lock: dict) -> dict:
    expected = lock.get("raw_file_hashes", {})
    per_file, worst = {}, PASS
    for rel in files:
        key = _dataset_key(rel)
        if key is None or key not in expected:
            per_file[rel], worst = "NOT_IN_LOCK", UNVERIFIED
            continue
        ok = sha256_file(root / rel) == expected[key]
        per_file[rel] = "RAW_MATCH" if ok else "RAW_MISMATCH"
        if not ok:
            worst = UNVERIFIED  # a raw mismatch may be serialization only; canonical digest decides
    return {"status": worst, "files": per_file}


def load_manifest(path: Path, prefix: str) -> dict[str, str]:
    entries = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if len(line) > 66 and line[64:66] == "  ":
            name = line[66:]
            name = name[2:] if name.startswith("./") else name
            if name.startswith(prefix):
                entries[name[len(prefix):]] = line[:64]
    return entries


def verify_cold(root: Path, files: list[str], manifest: dict[str, str] | None) -> dict:
    if manifest is None:
        return {"status": UNVERIFIED, "detail": "no cold-backup manifest supplied"}
    counts = {PASS: 0, STALE: 0, MISSING: 0}
    examples: dict[str, list[str]] = {STALE: [], MISSING: []}
    for rel in files:
        recorded = manifest.get(rel)
        if recorded is None:
            state = MISSING
        elif os.path.islink(root / rel) or recorded == sha256_file(root / rel):
            state = PASS
        else:
            state = STALE
        counts[state] += 1
        if state != PASS and len(examples[state]) < 10:
            examples[state].append(rel)
    status = PASS if counts[STALE] == counts[MISSING] == 0 else (MISSING if counts[MISSING] else STALE)
    return {"status": status, "counts": counts, "examples": examples}


def inventory(root: Path, classes: list[StateClass], *, publication: dict, lock: dict,
              cold_manifest: dict[str, str] | None,
              archive_verifier: Callable[[Path], object]) -> dict:
    root = Path(root).resolve()
    sealed = {a["archive_name"] for a in publication.get("archives", [])}
    files, unreadable = walk(root)
    tracked = tracked_files(root)
    assigned, unclassified = classify(files, tracked, classes, sealed)
    report_classes = []
    for cls in classes:
        members = assigned[cls.id]
        size = sum((root / f).lstat().st_size for f in members)
        if not members:
            recovery = {"status": PASS, "detail": "no files in this class"}
        elif cls.recovery == "GIT_REMOTE":
            recovery = verify_git_remote(root, members)
        elif cls.recovery == "SEALED_ARCHIVE":
            recovery = verify_sealed(root, members, sealed, archive_verifier)
        elif cls.recovery == "DATASET_LOCK":
            recovery = verify_dataset(root, members, lock)
        elif cls.recovery == "COLD_BACKUP":
            recovery = verify_cold(root, members, cold_manifest)
        else:
            recovery = {"status": PASS, "detail": "disposable; regenerated, not recovered"}
        report_classes.append({"id": cls.id, "authority": cls.authority, "recovery_kind": cls.recovery,
                               "files": len(members), "bytes": size, "recovery": recovery})
    coverage_complete = not unclassified and not unreadable
    recovery_ok = all(c["recovery"]["status"] == PASS for c in report_classes)
    return {
        "inventory_version": "P3_STATE_INVENTORY_V1",
        "root": str(root),
        "files_seen": len(files),
        "unclassified": {"count": len(unclassified), "examples": unclassified[:50]},
        "unreadable_dirs": {"count": len(unreadable), "examples": unreadable[:50]},
        "classes": report_classes,
        "COVERAGE": PASS if coverage_complete else FAIL,
        "RECOVERY": PASS if recovery_ok else "NOT_PASS",
        "PLN_02_STATE_INVENTORY": PASS if coverage_complete and recovery_ok else "NOT_PASS",
        "real_money_authorized": False,
    }
