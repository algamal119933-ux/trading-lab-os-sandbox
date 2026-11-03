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
    data/<name>.tar               each declared live data source (a bind-mounted host directory or a named
                                  volume), archived by the root helper read-only; the restore drill restores it
    data/<name>.files.sha256      sha256 of every file in that archive, proven equal to the live source
    SHA256SUMS                    every artifact above
    BACKUP_RECORD.json            what was backed up, when, with counts and the SHA256SUMS digest

PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import hashlib
import contextlib
import fcntl
import json
import os
import re
import shutil
import stat
import subprocess
import tarfile
import time
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


def _excluded(rel: str, excludes: tuple[str, ...] = DERIVED_EXCLUDES) -> bool:
    return any(part in excludes for part in Path(rel).parts)


def source_manifest(root: Path, excludes: tuple[str, ...] = DERIVED_EXCLUDES) -> dict[str, str]:
    """sha256 of every regular file and symlink under root, excluding derived files (``excludes``)."""
    entries = {}
    for current, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if d not in excludes]
        for d in [d for d in dirs if os.path.islink(os.path.join(current, d))]:
            dirs.remove(d)
            names.append(d)
        for name in names:
            path = Path(current) / name
            rel = path.relative_to(root).as_posix()
            if _excluded(rel, excludes) or not (path.is_symlink() or path.is_file()):
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


PRIVATE_UMASK = 0o077


def group_or_other_accessible(path: Path) -> list[str]:
    """Every entry under ``path`` (itself included) whose mode grants anything to group or other."""
    path = Path(path)
    loose = []
    for entry in [path, *path.rglob("*")]:
        if not entry.is_symlink() and stat.S_IMODE(entry.lstat().st_mode) & 0o077:
            loose.append(f"{stat.S_IMODE(entry.lstat().st_mode):04o} {entry.relative_to(path).as_posix()}")
    return loose


def create_backup(target: Path, *, roots: dict[str, Path], repos: dict[str, Path],
                  volumes: tuple[str, ...] = (), stamp: str | None = None,
                  volume_exporter: Callable[[str, Path], None] | None = None,
                  data: dict[str, str] | None = None, compose_project: str | None = None,
                  inspector: Callable[[str], list[dict]] | None = None,
                  data_lister: Callable[[str], dict[str, str]] | None = None,
                  coverage_report: Path | None = None) -> dict:
    """Write one private backup set (see ``_create_backup``). One run at a time per target: an exclusive lock
    on ``<target>/.backup.lock`` refuses a concurrent run. The process umask is 077 for the whole creation,
    whatever the caller's, so every directory, archive, bundle and manifest the set holds is owner-only.
    The set holds the runtime ``.env`` and Grafana's database (P3 security audit SEC-03). Before the set is
    published, any entry still open to group or other refuses it. Other (historical) sets are never touched."""
    # Every refusal that needs no lock comes first, so a refused run writes nothing at all.
    data, coverage = _preflight(roots=roots, data=data, compose_project=compose_project, inspector=inspector,
                                coverage_report=coverage_report)
    old = os.umask(PRIVATE_UMASK)
    try:
        Path(target).mkdir(parents=True, exist_ok=True)
        with exclusive_lock(Path(target) / LOCK_NAME):
            return _create_backup(target, roots=roots, repos=repos, volumes=volumes, stamp=stamp,
                                  volume_exporter=volume_exporter, data=data, coverage=coverage,
                                  data_lister=data_lister)
    finally:
        os.umask(old)


def _preflight(*, roots: dict[str, Path], data: dict[str, str] | None, compose_project: str | None,
               inspector: Callable[[str], list[dict]] | None, coverage_report: Path | None) -> tuple[dict, dict | None]:
    data = dict(data or {})
    for name, source in data.items():
        _check_name(name)
        _helper_mount(source)  # refuse a malformed source before anything is written
    if compose_project is not None and coverage_report is not None:
        raise BackupError("give --compose-project (observe now) or --coverage-report (observed before the stop), not both")
    coverage = None
    if coverage_report is not None:
        coverage = bind_coverage_report(coverage_report, data=data, roots=roots)
    if compose_project is not None:
        coverage = {**live_data_coverage((inspector or _docker_project_mounts)(compose_project), data=data,
                                         roots=roots), "compose_project": compose_project, "observed": "at_create",
                    "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        if coverage["LIVE_DATA_COVERAGE"] != "PASS":
            raise BackupError("LIVE_DATA_COVERAGE = FAIL: "
                              f"uncovered writable mounts {coverage['uncovered_rw']}; "
                              f"declared data sources no container uses {coverage['stale_data_sources']}")
    return data, coverage


def _create_backup(target: Path, *, roots: dict[str, Path], repos: dict[str, Path],
                   volumes: tuple[str, ...], stamp: str | None,
                   volume_exporter: Callable[[str, Path], None] | None,
                   data: dict[str, str], coverage: dict | None,
                   data_lister: Callable[[str], dict[str, str]] | None) -> dict:
    """Write one backup set. ``data`` maps a name to a live data source, either an absolute host directory
    (a bind mount) or a named volume. With ``compose_project``, the project's containers are inspected first,
    and the set is refused unless every writable mount they use is backed up and no declared data source is
    unused (LIVE_DATA_COVERAGE)."""
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
    record_data = {}
    if data:
        (staging / DATA_DIR).mkdir()
        exporter = volume_exporter or _docker_volume_export
        lister = data_lister or _docker_source_manifest
        for name, source in data.items():
            archive = staging / DATA_DIR / f"{name}.tar"
            exporter(source, archive)
            archived, size = _archive_manifest(archive)
            # Read the live source again, as root and read-only: the archive must hold exactly what it holds.
            # A difference means files the export could not read, or a writer still running (stop the runtime).
            live = lister(source)
            if live != archived:
                missing = sorted(set(live) - set(archived))[:10]
                differ = sorted(k for k in set(live) & set(archived) if live[k] != archived[k])[:10]
                extra = sorted(set(archived) - set(live))[:10]
                raise BackupError(f"data source {name} ({source}) changed or was not fully read during the backup: "
                                  f"missing {missing}, differ {differ}, extra {extra}")
            _write_manifest(archived, staging / DATA_DIR / f"{name}.files.sha256")
            record_data[name] = {"source": source, "files": len(archived), "bytes": size}
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
        "data_sources": record_data,
        "live_data_coverage": coverage,
        "derived_excluded": list(DERIVED_EXCLUDES),
        "sha256sums_digest": sha256_file(staging / SUMS),
        "real_money_authorized": False,
    }
    (staging / RECORD).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    loose = group_or_other_accessible(staging)
    if loose:
        raise BackupError(f"GROUP_OR_OTHER_ACCESSIBLE_ENTRIES = {len(loose)}; the set is not published: {loose[:10]}")
    staging.rename(set_dir)
    return record


VOLUME_HELPER_IMAGE = "python:3.12-slim"
ARCHIVE_MODE = 0o600
DATA_DIR = "data"
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")


def _check_name(name: str) -> None:
    if not _NAME.fullmatch(name):
        raise BackupError(f"data source name {name!r} must match {_NAME.pattern}")


def _helper_mount(source: str) -> list[str]:
    """The helper's only mount: the source read-only at /v.

    A named volume is mounted as before. An absolute host directory (a live bind mount) is mounted with
    ``--mount type=bind,readonly``, which refuses a missing directory, where ``-v`` would create an empty one
    and archive nothing.
    """
    if source.startswith("/"):
        if os.path.normpath(source) != source or "," in source:
            raise BackupError(f"data source {source!r} is not a normalized absolute directory usable as a bind mount")
        return ["--mount", f"type=bind,src={source},dst=/v,readonly"]
    if not _NAME.fullmatch(source):
        raise BackupError(f"data source {source!r} is neither an absolute host directory nor a volume name")
    return ["-v", f"{source}:/v:ro"]


def _docker_volume_export(volume: str, out: Path) -> None:
    """Export a Docker volume to ``out``: private to the backup user (0600, its uid:gid), whatever the umask.

    The helper container runs as root so it can read every file in the volume, including root-owned 0600
    ones. ``docker run --user`` would silently archive less. The container has no write mount: it streams
    the archive to stdout. This process creates the file itself with O_EXCL and mode 0600. Ownership and mode
    therefore come from the backup user by construction, not from a root ``chown`` after the fact. A
    volume archive holds Grafana's database, so it gets the same owner-only rule as the rest of the set
    (P3 security audit SEC-03). The result is then re-checked, and anything else fails closed.
    """
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), ARCHIVE_MODE)
    with os.fdopen(fd, "wb") as handle:
        result = subprocess.run(["docker", "run", "--rm", "--network", "none", *_helper_mount(volume),
                                 VOLUME_HELPER_IMAGE, "tar", "-C", "/v", "-cf", "-", "."],
                                stdout=handle, stderr=subprocess.PIPE, timeout=900)
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", "replace").strip()[:400]
        raise BackupError(f"volume export of {volume} failed ({result.returncode}): {stderr}")
    _require_private_archive(out)


def _require_private_archive(path: Path) -> None:
    """Refuse a volume archive that is not a regular file, owned by this uid:gid, with mode exactly 0600."""
    st = os.lstat(path)
    problems = []
    if not stat.S_ISREG(st.st_mode):
        problems.append("not a regular file")
    if (st.st_uid, st.st_gid) != (os.getuid(), os.getgid()):
        problems.append(f"owner {st.st_uid}:{st.st_gid}, expected {os.getuid()}:{os.getgid()}")
    if stat.S_IMODE(st.st_mode) != ARCHIVE_MODE:
        problems.append(f"mode {stat.S_IMODE(st.st_mode):04o}, expected {ARCHIVE_MODE:04o}")
    if st.st_size == 0:
        problems.append("empty archive")
    if problems:
        raise BackupError(f"volume archive {path.name} is not private to the backup user: {'; '.join(problems)}")


def _symlink_digest(target: bytes) -> str:
    return hashlib.sha256(b"symlink\0" + target).hexdigest()


def _rel(name: str) -> str:
    return name[2:] if name.startswith("./") else name


def _archive_manifest(path: Path) -> tuple[dict[str, str], int]:
    """(sha256 of every file and symlink in a tar, by the same rule as ``entry_digest``; total file bytes)."""
    entries, size = {}, 0
    with tarfile.open(path) as tar:
        for member in tar:
            if member.isfile() or member.islnk():
                digest = hashlib.sha256()
                handle = tar.extractfile(member)
                for chunk in iter(lambda: handle.read(1 << 20), b""):
                    digest.update(chunk)
                entries[_rel(member.name)] = digest.hexdigest()
                size += member.size
            elif member.issym():
                entries[_rel(member.name)] = _symlink_digest(member.linkname.encode("utf-8", "surrogateescape"))
    return dict(sorted(entries.items())), size


# Root and read-only, like the export: NUL-separated "<sha256>  <path>" per file, one empty record, then
# "<path>" "<target>" per symlink. GNU find/xargs/coreutils, as in the helper image.
_LIST_SCRIPT = ('cd /v && find . -type f -print0 | xargs -0r sha256sum -z && printf "\\0" '
                '&& find . -type l -printf "%p\\0%l\\0"')


def _parse_source_listing(raw: bytes) -> dict[str, str]:
    parts = raw.split(b"\0")
    if b"" not in parts:
        raise BackupError("source listing is malformed (no file/link separator)")
    sep = parts.index(b"")
    entries = {}
    for record in parts[:sep]:
        if len(record) < 67 or record[64:66] != b"  ":
            raise BackupError(f"source listing record is malformed: {record[:80]!r}")
        entries[_rel(record[66:].decode("utf-8", "surrogateescape"))] = record[:64].decode("ascii")
    links = parts[sep + 1:]
    if links and links[-1] == b"":
        links = links[:-1]
    if len(links) % 2:
        raise BackupError("source listing is malformed (odd symlink records)")
    for name, target in zip(links[0::2], links[1::2]):
        entries[_rel(name.decode("utf-8", "surrogateescape"))] = _symlink_digest(target)
    return dict(sorted(entries.items()))


def _docker_source_manifest(source: str) -> dict[str, str]:
    """sha256 of every file and symlink in a live data source, read by the root helper read-only."""
    result = subprocess.run(["docker", "run", "--rm", "--network", "none", *_helper_mount(source),
                             VOLUME_HELPER_IMAGE, "sh", "-c", _LIST_SCRIPT], capture_output=True, timeout=900)
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", "replace").strip()[:400]
        raise BackupError(f"listing of {source} failed ({result.returncode}): {stderr}")
    return _parse_source_listing(result.stdout)


# Mount sources that are host plumbing, never TLOS state (a socket, /proc, /sys, …).
SYSTEM_MOUNT_PREFIXES = ("/proc", "/sys", "/dev", "/run", "/var/run")


def _docker_project_mounts(project: str) -> list[dict]:
    """Every mount of every container (running or stopped) of a compose project, as Docker reports it."""
    ids = _run(["docker", "ps", "-a", "-q", "--filter", f"label=com.docker.compose.project={project}"]).stdout.split()
    if not ids:
        raise BackupError(f"LIVE_DATA_COVERAGE = FAIL: no container of compose project {project!r} exists")
    mounts = []
    for container in json.loads(_run(["docker", "inspect", *ids]).stdout):
        for m in container.get("Mounts") or []:
            mounts.append({"container": container["Name"].lstrip("/"), "type": m.get("Type"),
                           "source": m.get("Source") if m.get("Type") == "bind" else m.get("Name"),
                           "destination": m.get("Destination"), "rw": bool(m.get("RW"))})
    return mounts


def _under(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip("/") + "/")


LOCK_NAME = ".backup.lock"
COVERAGE_REPORT_VERSION = "P3_LIVE_DATA_COVERAGE_REPORT_V1"
COVERAGE_MAX_AGE_S = 1800       # a pre-stop observation older than this does not describe this backup
COVERAGE_FUTURE_SKEW_S = 300


@contextlib.contextmanager
def exclusive_lock(path: Path):
    """Hold an exclusive, non-blocking flock on ``path`` (created 0600) for the block; refuse if another run holds it.
    The kernel releases it when the holder exits, however it exits (SIGKILL and power loss included)."""
    fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise BackupError(f"{path} is held by another run; two runs never overlap") from None
        yield
    finally:
        os.close(fd)


def _resolved_roots(roots: dict[str, Path]) -> dict[str, str]:
    return {name: os.path.realpath(str(path)) for name, path in sorted(roots.items())}


def coverage_report(project: str, *, data: dict[str, str], roots: dict[str, Path],
                    mounts: list[dict] | None = None) -> dict:
    """LIVE_DATA_COVERAGE for ``project`` now, with the provenance ``bind_coverage_report`` needs."""
    report = live_data_coverage(mounts if mounts is not None else _docker_project_mounts(project), data=data, roots=roots)
    now = time.time()
    return {"report_version": COVERAGE_REPORT_VERSION, **report, "compose_project": project,
            "data": dict(sorted(data.items())), "roots": _resolved_roots(roots), "generated_epoch": now,
            "generated_utc": datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}


def write_coverage_report(report: dict, path: Path) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(report, indent=2) + "\n")


def bind_coverage_report(path: Path, *, data: dict[str, str], roots: dict[str, Path],
                         now: float | None = None) -> dict:
    """Accept a coverage report observed before the runtime stop only if it describes *this* backup: PASS, the
    current report version, exactly this create's data sources and roots, and observed within the last
    COVERAGE_MAX_AGE_S. The record then carries it with its observation phase and the report file's sha256."""
    path = Path(path)
    try:
        raw = path.read_bytes()
        report = json.loads(raw)
    except (OSError, ValueError) as exc:
        raise BackupError(f"coverage report {path} is unreadable: {exc}") from None
    problems = []
    if report.get("report_version") != COVERAGE_REPORT_VERSION:
        problems.append(f"report_version {report.get('report_version')!r}")
    if report.get("LIVE_DATA_COVERAGE") != "PASS":
        problems.append(f"LIVE_DATA_COVERAGE = {report.get('LIVE_DATA_COVERAGE')}")
    if not report.get("compose_project"):
        problems.append("no compose_project")
    if report.get("data") != dict(sorted(data.items())):
        problems.append(f"data sources {report.get('data')} differ from this backup's {dict(sorted(data.items()))}")
    if report.get("roots") != _resolved_roots(roots):
        problems.append(f"roots {report.get('roots')} differ from this backup's {_resolved_roots(roots)}")
    age = (now if now is not None else time.time()) - float(report.get("generated_epoch") or 0)
    if not -COVERAGE_FUTURE_SKEW_S <= age <= COVERAGE_MAX_AGE_S:
        problems.append(f"observed {age:.0f} s ago (allowed 0..{COVERAGE_MAX_AGE_S} s)")
    if problems:
        raise BackupError("coverage report does not bind to this backup: " + "; ".join(problems))
    return {**report, "observed": "before_runtime_stop", "report_path": str(path),
            "report_sha256": hashlib.sha256(raw).hexdigest()}


def _root_archives(source: str, root_paths: list[str]) -> bool:
    """Is ``source`` under a declared root **and** archived by it? A path through a derived (excluded) directory,
    e.g. ``…/.venv/…``, is under the root but never reaches the archive, so it covers nothing."""
    for candidate in {source, os.path.realpath(source)}:
        for root in root_paths:
            if _under(candidate, root) and not _excluded(os.path.relpath(candidate, root)):
                return True
    return False


def live_data_coverage(mounts: list[dict], *, data: dict[str, str], roots: dict[str, Path]) -> dict:
    """PASS when every writable mount of the live containers is backed up, as a declared data source or under
    a declared root, and every declared data source is mounted by some container (none is stale).

    Read-only mounts (configuration) are reported with what covers them but do not decide the verdict. Host
    plumbing (``SYSTEM_MOUNT_PREFIXES``) and tmpfs are not state.
    """
    declared = set(data.values())
    root_paths = [os.path.realpath(str(r)) for r in roots.values()]
    rows = []
    for m in mounts:
        source = m.get("source") or ""
        if m.get("type") == "tmpfs" or (m.get("type") == "bind" and any(_under(source, p) for p in SYSTEM_MOUNT_PREFIXES)):
            covered = "not_state"
        elif source in declared:
            covered = "data"
        elif m.get("type") == "bind" and _root_archives(source, root_paths):
            covered = "root"
        else:
            covered = None
        rows.append({**m, "covered_by": covered})
    uncovered = [f"{r['container']}:{r['destination']} <- {r['type']} {r['source']}"
                 for r in rows if r["rw"] and r["covered_by"] is None]
    used = {m.get("source") for m in mounts}
    stale = sorted(s for s in declared if s not in used)
    return {"LIVE_DATA_COVERAGE": "PASS" if not uncovered and not stale else "FAIL",
            "containers": sorted({r["container"] for r in rows}), "mounts": rows,
            "uncovered_rw": uncovered, "stale_data_sources": stale}


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
    for name, info in (record.get("data_sources") or {}).items():
        dest = scratch / DATA_DIR / name
        dest.mkdir(parents=True)
        _run(["tar", "-xf", str(set_dir / DATA_DIR / f"{name}.tar"), "--no-same-owner", "--no-same-permissions",
              "-C", str(dest)])
        _run(["chmod", "-R", "u+rwX", str(dest)])  # a 0000 file in the source must still be hashable here
        expected = _read_manifest(set_dir / DATA_DIR / f"{name}.files.sha256")
        restored = source_manifest(dest, excludes=())
        differ = sorted(k for k in expected if restored.get(k) != expected[k])
        extra = sorted(set(restored) - set(expected))
        checks[f"data:{name}"] = {"status": "PASS" if not differ and not extra and len(expected) == info["files"]
                                  else "FAIL", "source": info["source"], "files": len(expected),
                                  "differ": differ[:20], "extra": extra[:20]}
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



# --------------------------------------------------------------------------------------------------
# PLN-05 portable copy: compare a Windows Get-FileHash export of a copied set with the set's manifests
# --------------------------------------------------------------------------------------------------

EXPORT_VERSION = "P3_PORTABLE_COPY_COMPARE_V1"


def _export_rows(export_csv: Path) -> list[dict]:
    """Rows of ``Get-FileHash | Export-Csv`` (PowerShell 5.1 or 7): Algorithm, Hash, Path; BOM and #TYPE tolerated."""
    import csv
    import io

    text = Path(export_csv).read_text(encoding="utf-8-sig")
    lines = [line for line in text.splitlines() if not line.startswith("#TYPE")]
    return list(csv.DictReader(io.StringIO("\n".join(lines))))


def _windows_relative(path: str, root: str) -> str | None:
    """``path`` relative to ``root`` with '/' separators, compared case-insensitively as Windows does; else None."""
    norm_root = root.replace("/", "\\").rstrip("\\")
    norm_path = path.replace("/", "\\")
    if not norm_path.lower().startswith(norm_root.lower() + "\\"):
        return None
    return norm_path[len(norm_root) + 1:].replace("\\", "/")


def expected_artifact_count(record: dict) -> int:
    """How many artifacts ``create_backup`` lists in SHA256SUMS for this record: an archive and a manifest per
    root and per data source, a bundle per repository, an archive per volume. A historical record has no
    ``data_sources`` key and counts as before."""
    return (2 * len(record["roots"]) + len(record["repos"]) + len(record["volumes"])
            + 2 * len(record.get("data_sources") or {}))


def compare_hash_export(set_dir: Path, export_csv: Path, export_root: str) -> dict:
    """Is the copy that ``export_csv`` hashed, file by file, the backup set whose manifests are in ``set_dir``?

    ``set_dir`` needs only the set's own ``SHA256SUMS`` and ``BACKUP_RECORD.json``: the original set (the
    strongest reading, because it proves the copy *is* that set), or copies of the two manifests. The export is
    ``Get-ChildItem -LiteralPath <copy> -Recurse -File -Force | Get-FileHash -Algorithm SHA256 | Export-Csv``
    taken on the machine that holds the copy, and ``export_root`` is the copy's folder as that machine named it.

    The rules are ``verify_backup``'s: the manifest digest equals the record, and every listed artifact is
    present with an equal hash. To them it adds the checks a copy needs: the copy's two manifests are
    byte-identical to these, the listed count is what ``create_backup`` writes for the record
    (``expected_artifact_count``), and the copy holds no unlisted file. Read-only; nothing is extracted, so no
    secret is read. An unreadable or empty export is UNPROVEN, which withholds PASS exactly as FAIL does.
    """
    set_dir = Path(set_dir)
    report = {"compare_version": EXPORT_VERSION, "set_dir": str(set_dir), "export": str(export_csv),
              "export_root": export_root, "checks": {}, "PORTABLE_COPY_MATCHES_SET": "UNPROVEN",
              "real_money_authorized": False}
    checks = report["checks"]
    try:
        record = json.loads((set_dir / RECORD).read_text(encoding="utf-8"))
        sums_digest = sha256_file(set_dir / SUMS)
        record_digest = sha256_file(set_dir / RECORD)
        listed = _read_manifest(set_dir / SUMS)
        expected_count = expected_artifact_count(record)
        rows = _export_rows(export_csv)
    except (OSError, KeyError, TypeError, ValueError) as exc:
        checks["inputs_readable"] = {"status": "UNPROVEN", "detail": f"{type(exc).__name__}: {exc}"[:300]}
        return report
    checks["inputs_readable"] = {"status": "PASS" if rows else "UNPROVEN",
                                 "detail": f"{len(rows)} export row(s)" if rows else "the export holds no row"}
    if not rows:
        return report

    hashed: dict[str, str] = {}
    unreadable, outside, duplicate = [], [], []
    for index, row in enumerate(rows):
        algorithm, digest, path = (row.get("Algorithm") or ""), (row.get("Hash") or "").lower(), row.get("Path") or ""
        if algorithm.upper() != "SHA256" or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            unreadable.append(index)
            continue
        rel = _windows_relative(path, export_root)
        if rel is None:
            outside.append(path[:200])
            continue
        if rel in hashed:
            duplicate.append(rel)
        hashed[rel] = digest
    checks["export_rows"] = {"status": "UNPROVEN" if unreadable else ("FAIL" if outside or duplicate else "PASS"),
                             "unreadable_rows": unreadable[:20], "outside_root": outside[:20],
                             "duplicate_paths": duplicate[:20]}
    checks["record_digest"] = {"status": "PASS" if sums_digest == record.get("sha256sums_digest") else "FAIL",
                               "detail": "SHA256SUMS digest against BACKUP_RECORD.json sha256sums_digest"}
    same_sums, same_record = hashed.get(SUMS) == sums_digest, hashed.get(RECORD) == record_digest
    checks["manifests_identical"] = {"status": "PASS" if same_sums and same_record else "FAIL",
                                     "SHA256SUMS": same_sums, "BACKUP_RECORD.json": same_record}
    checks["listed_count"] = {"status": "PASS" if listed and len(listed) == expected_count else "FAIL",
                              "listed": len(listed), "expected_from_record": expected_count}
    missing = sorted(rel for rel in listed if rel not in hashed)
    mismatched = sorted(rel for rel, digest in listed.items() if rel in hashed and hashed[rel] != digest)
    checks["artifacts"] = {"status": "PASS" if not missing and not mismatched else "FAIL",
                           "ok": len(listed) - len(missing) - len(mismatched),
                           "missing": missing[:20], "mismatched": mismatched[:20]}
    extra = sorted(rel for rel in hashed if rel not in listed and rel not in (SUMS, RECORD))
    checks["no_unlisted_file"] = {"status": "PASS" if not extra else "FAIL", "extra": extra[:20]}

    statuses = {c["status"] for c in checks.values()}
    report["PORTABLE_COPY_MATCHES_SET"] = ("FAIL" if "FAIL" in statuses
                                           else "UNPROVEN" if statuses != {"PASS"} else "PASS")
    return report


# --------------------------------------------------------------------------------------------------
# Second-device (SSD) mirror: verified full-set generations, published without ever destroying the
# last verified one
# --------------------------------------------------------------------------------------------------

MIRROR_LOCK = ".mirror.lock"
MIRROR_SETS = "sets"
MIRROR_CURRENT = "current"
MIRROR_MARGIN_BYTES = 20 * 1024 ** 3


def _set_files(path: Path) -> list[str]:
    return sorted(p.relative_to(path).as_posix() for p in Path(path).rglob("*") if p.is_file() or p.is_symlink())


def _tree_bytes(path: Path) -> int:
    return sum(p.lstat().st_size for p in Path(path).rglob("*") if p.is_file() and not p.is_symlink())


def _privatize(path: Path) -> None:
    for entry in [path, *path.rglob("*")]:
        if not entry.is_symlink():
            entry.chmod(0o700 if entry.is_dir() else 0o600)


def mirror_generations(mirror_root: Path) -> list[str]:
    """Published (therefore verified) full generations, oldest first. Dot-names are staging or retiring."""
    sets = Path(mirror_root) / MIRROR_SETS
    return sorted(p.name for p in sets.iterdir() if p.is_dir() and not p.name.startswith(".")) if sets.is_dir() else []


def publish_mirror(set_dir: Path, mirror_root: Path, *, keep: int = 2, margin_bytes: int = MIRROR_MARGIN_BYTES,
                   _step: Callable[[str], None] = lambda step: None) -> dict:
    """Copy a verified backup set to ``<mirror_root>/sets/<stamp>`` and point ``<mirror_root>/current`` at it.

    Invariant: the last verified full generation is never destroyed while a replacement is published.
    - The copy is staged as ``sets/.incoming-<stamp>``. It becomes ``sets/<stamp>`` (one rename) only after
      ``verify_backup`` passes on the copy, the copy's file list equals the source's, its record is byte-identical,
      and no entry is open to group or other. A non-dot name under ``sets/`` therefore always means verified.
    - ``current`` is switched by an atomic symlink replace, only to a published generation.
    - Only then are generations beyond ``keep`` retired, oldest first and never the current one. Each is renamed to
      ``.retiring-<name>`` before it is deleted, so an interrupted deletion never leaves a half-deleted generation
      under a verified name.
    - Space is never made by deleting: too little free space refuses the copy.
    - Anything else in ``mirror_root`` (the legacy ``latest``/``previous``/``.incoming`` partial copies) is not touched.
    Interrupted at any point, a re-run completes it: dot-name leftovers are discarded, published generations kept.
    """
    if keep < 1:
        raise BackupError("keep must be at least 1: the newest verified generation is always kept")
    set_dir, mirror_root = Path(set_dir), Path(mirror_root)
    source = verify_backup(set_dir)
    if source["status"] != "PASS":
        raise BackupError(f"source set {set_dir} does not verify; nothing is mirrored")
    stamp = json.loads((set_dir / RECORD).read_text(encoding="utf-8"))["stamp"]
    _check_name(stamp)
    old = os.umask(PRIVATE_UMASK)
    try:
        mirror_root.mkdir(parents=True, exist_ok=True)
        sets = mirror_root / MIRROR_SETS
        sets.mkdir(mode=0o700, exist_ok=True)
        with exclusive_lock(mirror_root / MIRROR_LOCK):
            for leftover in sorted(p for p in sets.iterdir() if p.name.startswith((".incoming-", ".retiring-"))):
                shutil.rmtree(leftover)  # never a published generation: dot-names are not verified
            final = sets / stamp
            if final.exists():
                if verify_backup(final)["status"] != "PASS":
                    raise BackupError(f"{final} exists and does not verify; it is not overwritten")
            else:
                need = _tree_bytes(set_dir) + margin_bytes
                free = shutil.disk_usage(mirror_root).free
                if free < need:
                    raise BackupError(f"mirror refused: {free} bytes free, {need} needed (set + margin); "
                                      "nothing is deleted to make room")
                incoming = sets / f".incoming-{stamp}"
                _step("copy")
                shutil.copytree(set_dir, incoming, symlinks=True, copy_function=shutil.copy2)
                _privatize(incoming)
                _step("verify")
                problems = []
                if verify_backup(incoming)["status"] != "PASS":
                    problems.append("verify FAIL")
                if _set_files(incoming) != _set_files(set_dir):
                    problems.append("file list differs")
                if (incoming / RECORD).read_bytes() != (set_dir / RECORD).read_bytes():
                    problems.append("record differs")
                if group_or_other_accessible(incoming):
                    problems.append("entries open to group/other")
                if problems:
                    raise BackupError(f"mirror copy of {stamp} not published: {', '.join(problems)}")
                _step("publish")
                os.rename(incoming, final)
            _step("pointer")
            link = mirror_root / f".{MIRROR_CURRENT}.tmp"
            if link.is_symlink() or link.exists():
                link.unlink()
            os.symlink(f"{MIRROR_SETS}/{stamp}", link)
            os.replace(link, mirror_root / MIRROR_CURRENT)
            retired = []
            for name in mirror_generations(mirror_root)[:-keep]:
                if name == stamp:
                    continue
                _step("retire")
                retiring = sets / f".retiring-{name}"
                os.rename(sets / name, retiring)
                _step("delete")
                shutil.rmtree(retiring)
                retired.append(name)
            legacy = sorted(p.name for p in mirror_root.iterdir()
                            if p.name not in (MIRROR_SETS, MIRROR_CURRENT, MIRROR_LOCK))
            return {"mirror_version": "P3_SSD_MIRROR_V1", "published": stamp, "current": f"{MIRROR_SETS}/{stamp}",
                    "generations": mirror_generations(mirror_root), "retired": retired, "keep": keep,
                    "bytes": _tree_bytes(final), "legacy_untouched": legacy, "SSD_MIRROR": "PASS"}
    finally:
        os.umask(old)


# --------------------------------------------------------------------------------------------------
# Runtime restoration: each compose service individually
# --------------------------------------------------------------------------------------------------

def _docker_service_state(project: str, service: str) -> list[dict]:
    ids = _run(["docker", "ps", "-a", "-q", "--filter", f"label=com.docker.compose.project={project}",
                "--filter", f"label=com.docker.compose.service={service}"]).stdout.split()
    return json.loads(_run(["docker", "inspect", *ids]).stdout) if ids else []


def _started_epoch(text: str) -> float | None:
    try:
        return datetime.strptime(text[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
    except (TypeError, ValueError):
        return None


def runtime_check(project: str, services: tuple[str, ...], *, started_after: float | None = None,
                  wait_s: float = 0, poll_s: float = 2,
                  state_of: Callable[[str, str], list[dict]] | None = None,
                  sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.time) -> dict:
    """Is each named service of the compose project back? Per service: exactly one container, running, not
    restarting, healthy when it defines a healthcheck, and (with ``started_after``) started by this restoration.
    Polls for up to ``wait_s`` seconds; whatever is not OK by then is FAIL (an incomplete recovery is a failure)."""
    if not services:
        raise BackupError("runtime_check needs the services that must be back")
    state_of = state_of or _docker_service_state
    deadline = clock() + wait_s
    while True:
        results = {}
        for service in services:
            containers = state_of(project, service)
            problems = []
            if len(containers) != 1:
                problems.append(f"{len(containers)} containers")
            else:
                st = containers[0].get("State") or {}
                if st.get("Status") != "running" or st.get("Restarting"):
                    problems.append(f"status {st.get('Status')}{' restarting' if st.get('Restarting') else ''}")
                health = (st.get("Health") or {}).get("Status")
                if health is not None and health != "healthy":
                    problems.append(f"health {health}")
                started = _started_epoch(st.get("StartedAt", ""))
                if started_after is not None and (started is None or started + 1 < started_after):
                    problems.append(f"started {st.get('StartedAt')} before this restoration")
            results[service] = {"status": "FAIL" if problems else "PASS", "problems": problems}
        ok = all(r["status"] == "PASS" for r in results.values())
        if ok or clock() >= deadline:
            return {"compose_project": project, "services": results, "RUNTIME_RECOVERY": "PASS" if ok else "FAIL"}
        sleep(poll_s)
