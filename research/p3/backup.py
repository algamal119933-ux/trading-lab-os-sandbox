"""P3-PLN-03 Backup & Restore: append-only backup sets and a restore drill that proves them.

docs/p3/P3_CONTRACT.md §3 PLN-03. Acceptance: a restore drill into a scratch location passes. That
means manifest sha256 equal, git fsck clean, ARCHIVE_VERIFIED on every restored sealed archive,
and the restored paper config and strategy load. It is repeated after a change.

Reuse (§10): GNU tar + zstd for archives, `git bundle --all` for history, a read-only helper
container for Docker volumes, and `scripts/publish_evidence_digest.py verify_archive` for sealed
evidence. This module only orchestrates and records. It builds no storage engine.

A backup set is written once to ``<target>/<stamp>/`` and never overwritten:

    roots/<name>.tar.zst          each declared root, derived files excluded
    roots/<name>.files.sha256     sha256 of every archived source file, relative to the root
    git/<name>.bundle             full history (--all) of each declared repository
    volumes/<name>.tar            each declared Docker volume, exported read-only (optional)
    SHA256SUMS                    every artifact above
    BACKUP_RECORD.json            what was backed up, when, with counts and the SHA256SUMS digest

PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

# Regenerable, never backed up (the PLN-02 DISPOSABLE class).
DERIVED_EXCLUDES = (".venv", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache")
RECORD = "BACKUP_RECORD.json"
SUMS = "SHA256SUMS"


class BackupError(Exception):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def entry_digest(path: Path) -> str:
    """sha256 of a regular file's bytes, or of a symlink's target text (links are state too)."""
    if os.path.islink(path):
        return hashlib.sha256(b"symlink\0" + os.readlink(path).encode()).hexdigest()
    return sha256_file(path)


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _excluded(rel: str) -> bool:
    return any(part in DERIVED_EXCLUDES for part in Path(rel).parts)


def source_manifest(root: Path) -> dict[str, str]:
    """sha256 of every regular file under root, excluding derived files and broken links."""
    entries = {}
    for current, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if d not in DERIVED_EXCLUDES]
        for d in [d for d in dirs if os.path.islink(os.path.join(current, d))]:
            dirs.remove(d)
            names.append(d)
        for name in names:
            path = Path(current) / name
            rel = path.relative_to(root).as_posix()
            if _excluded(rel) or not (path.is_symlink() or path.is_file()):
                continue
            entries[rel] = entry_digest(path)
    return dict(sorted(entries.items()))


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    result = subprocess.run(cmd, capture_output=True, text=True, **kwargs)
    if result.returncode != 0:
        raise BackupError(f"{' '.join(cmd[:3])}… failed ({result.returncode}): {result.stderr.strip()[:400]}")
    return result


def _write_manifest(entries: dict[str, str], path: Path) -> None:
    path.write_text("".join(f"{digest}  {rel}\n" for rel, digest in entries.items()), encoding="utf-8")


def _read_manifest(path: Path) -> dict[str, str]:
    return {line[66:]: line[:64] for line in path.read_text(encoding="utf-8").splitlines() if len(line) > 66}


def create_backup(target: Path, *, roots: dict[str, Path], repos: dict[str, Path],
                  volumes: tuple[str, ...] = (), stamp: str | None = None,
                  volume_exporter: Callable[[str, Path], None] | None = None) -> dict:
    stamp = stamp or utc_stamp()
    set_dir = Path(target) / stamp
    if set_dir.exists():
        raise BackupError(f"{set_dir} exists; a backup set is written once and never overwritten")
    staging = Path(target) / f".{stamp}.incoming"
    if staging.exists():
        shutil.rmtree(staging)
    (staging / "roots").mkdir(parents=True)
    (staging / "git").mkdir()
    record_roots = {}
    for name, root in roots.items():
        root = Path(root).resolve()
        if not root.is_dir():
            raise BackupError(f"root {name} = {root} is not a directory")
        entries = source_manifest(root)
        _write_manifest(entries, staging / "roots" / f"{name}.files.sha256")
        excludes = [f"--exclude={e}" for e in DERIVED_EXCLUDES]
        _run(["tar", "--zstd", "-cf", str(staging / "roots" / f"{name}.tar.zst"), *excludes,
              "--numeric-owner", "-C", str(root), "."])
        record_roots[name] = {"path": str(root), "files": len(entries)}
    record_repos = {}
    for name, repo in repos.items():
        bundle = staging / "git" / f"{name}.bundle"
        _run(["git", "-C", str(repo), "bundle", "create", str(bundle), "--all"])
        heads = _run(["git", "-C", str(repo), "rev-parse", "HEAD"]).stdout.strip()
        record_repos[name] = {"path": str(Path(repo).resolve()), "head": heads}
    if volumes:
        (staging / "volumes").mkdir()
        exporter = volume_exporter or _docker_volume_export
        for volume in volumes:
            exporter(volume, staging / "volumes" / f"{volume}.tar")
    artifacts = sorted(p for p in staging.rglob("*") if p.is_file())
    sums = {p.relative_to(staging).as_posix(): sha256_file(p) for p in artifacts}
    _write_manifest(sums, staging / SUMS)
    record = {
        "record_type": "P3_BACKUP_SET_V1",
        "stamp": stamp,
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "roots": record_roots,
        "repos": record_repos,
        "volumes": list(volumes),
        "derived_excluded": list(DERIVED_EXCLUDES),
        "sha256sums_digest": sha256_file(staging / SUMS),
        "real_money_authorized": False,
    }
    (staging / RECORD).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    staging.rename(set_dir)
    return record


def _docker_volume_export(volume: str, out: Path) -> None:
    _run(["docker", "run", "--rm", "--network", "none", "-v", f"{volume}:/v:ro", "-v", f"{out.parent}:/out",
          "python:3.12-slim", "tar", "-C", "/v", "-cf", f"/out/{out.name}", "."], timeout=900)


def verify_backup(set_dir: Path) -> dict:
    set_dir = Path(set_dir)
    record = json.loads((set_dir / RECORD).read_text(encoding="utf-8"))
    if sha256_file(set_dir / SUMS) != record["sha256sums_digest"]:
        return {"status": "FAIL", "detail": "SHA256SUMS does not match the record's digest"}
    bad = [rel for rel, digest in _read_manifest(set_dir / SUMS).items()
           if not (set_dir / rel).is_file() or sha256_file(set_dir / rel) != digest]
    return {"status": "FAIL" if bad else "PASS", "mismatched": bad[:20]}


def restore_drill(set_dir: Path, scratch: Path, *, archive_verifier: Callable[[Path], object] | None = None,
                  config_check: Callable[[Path], tuple[bool, str]] | None = None,
                  config_targets: tuple[str, ...] | None = None) -> dict:
    """Restore every root and bundle into scratch and prove the copies are the evidence."""
    set_dir, scratch = Path(set_dir), Path(scratch)
    if scratch.exists() and any(scratch.iterdir()):
        raise BackupError(f"scratch {scratch} is not empty; a drill never restores over anything")
    scratch.mkdir(parents=True, exist_ok=True)
    checks: dict[str, dict] = {"backup_integrity": verify_backup(set_dir)}
    record = json.loads((set_dir / RECORD).read_text(encoding="utf-8"))
    for name in record["roots"]:
        dest = scratch / "roots" / name
        dest.mkdir(parents=True)
        # Never restore ownership or setuid/setgid bits into the scratch copy (security audit SEC-12).
        _run(["tar", "--zstd", "-xf", str(set_dir / "roots" / f"{name}.tar.zst"), "--numeric-owner",
              "--no-same-owner", "--no-same-permissions", "-C", str(dest)])
        expected = _read_manifest(set_dir / "roots" / f"{name}.files.sha256")
        restored = source_manifest(dest)
        differ = sorted(k for k in expected if restored.get(k) != expected[k])
        extra = sorted(set(restored) - set(expected))
        checks[f"root:{name}"] = {"status": "PASS" if not differ and not extra else "FAIL",
                                  "files": len(expected), "differ": differ[:20], "extra": extra[:20]}
        # A root may hold the runtime directly or one level down (projects/trading/<checkout>).
        candidates = [dest] + sorted(p for p in dest.iterdir() if p.is_dir() and not p.name.startswith("."))
        for base in candidates:
            label = name if base == dest else f"{name}/{base.name}"
            if archive_verifier is not None and (base / "artifacts").is_dir():
                sealed = []
                for archive in sorted(p for p in (base / "artifacts").iterdir()
                                      if (p / "archive_manifest.json").is_file()):
                    try:
                        archive_verifier(archive)
                        sealed.append((archive.name, "ARCHIVE_VERIFIED"))
                    except Exception as exc:  # noqa: BLE001
                        sealed.append((archive.name, f"FAIL: {exc}"))
                if sealed:
                    checks[f"sealed:{label}"] = {"status": "PASS" if all(s == "ARCHIVE_VERIFIED" for _, s in sealed)
                                                 else "FAIL", "archives": sealed}
            wanted = config_targets is None or label in config_targets
            if config_check is not None and wanted and (base / "freqtrade" / "user_data" / "config.json").is_file():
                ok, detail = config_check(base)
                checks[f"config_load:{label}"] = {"status": "PASS" if ok else "FAIL", "detail": detail}
    for name, info in record["repos"].items():
        mirror = scratch / "git" / f"{name}.git"
        clone = subprocess.run(["git", "clone", "-q", "--mirror", str(set_dir / "git" / f"{name}.bundle"),
                                str(mirror)], capture_output=True, text=True)
        if clone.returncode != 0:
            checks[f"git:{name}"] = {"status": "FAIL", "head": info["head"], "head_present": False,
                                     "fsck": f"bundle does not clone: {clone.stderr.strip()[:300]}"}
            continue
        fsck = subprocess.run(["git", "-C", str(mirror), "fsck", "--full", "--no-dangling"],
                              capture_output=True, text=True)
        has_head = subprocess.run(["git", "-C", str(mirror), "cat-file", "-e", info["head"]],
                                  capture_output=True).returncode == 0
        checks[f"git:{name}"] = {"status": "PASS" if fsck.returncode == 0 and has_head else "FAIL",
                                 "head": info["head"], "head_present": has_head,
                                 "fsck": fsck.stderr.strip()[:300]}
    for target in config_targets or ():
        if f"config_load:{target}" not in checks:
            checks[f"config_load:{target}"] = {"status": "FAIL", "detail": "named runtime not found in the restore"}
    verdict = all(c["status"] == "PASS" for c in checks.values())
    return {"drill_version": "P3_RESTORE_DRILL_V1", "backup_set": record["stamp"], "checks": checks,
            "PLN_03_RESTORE_DRILL": "PASS" if verdict else "FAIL", "real_money_authorized": False}

