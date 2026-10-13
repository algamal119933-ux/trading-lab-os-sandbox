#!/usr/bin/env python3
"""Content-addressed snapshot of the Dataset V3 archive (Owner decision OD-S2; review section 3, stage 2).

    python -m auth2q2.snapshot address     --manifest manifest.json
    python -m auth2q2.snapshot check       --manifest manifest.json --digest sha256:HEX [--tar snapshot.tar]
    python -m auth2q2.snapshot restore     --manifest manifest.json --digest sha256:HEX --tar snapshot.tar
                                           --dest DIR [--receipt FILE]
    python -m auth2q2.snapshot verify-tree --manifest manifest.json --digest sha256:HEX --dir DIR

The snapshot holds every archive file the Dataset V3 lock reads (each monthly zip, and the checksum file
research/auth2/archive.py fetch_verified writes beside it, which is what makes a restored tree a warm archive
cache) plus the listing the science phase replays (listing.py). It is three objects:

  manifest.json  canonical JSON naming every file's path, sha256 and size, sorted by path. Its sha256 is the
                 snapshot's address, "sha256:<hex>", and the release tag carries it.
  snapshot.tar   the manifest's files, in manifest order, as one canonical tar: ustar headers with fixed
                 metadata (mode 0644, uid and gid 0, mtime 0, no owner names) and a POSIX pax "path" record only
                 where a path does not fit a ustar name. The same files give the same bytes on any machine.
  restore        reads only that canonical form, member by member in manifest order, and checks each file's
                 size and sha256 as it writes it. Anything else (a link, a directory entry, a path or a member
                 the manifest does not list, a missing member, padding that is not zero, bytes after the end)
                 stops it, naming the file, before any science step can start. It writes only into a new or
                 empty directory, and only regular files.

Nothing here touches the network. PAPER / RESEARCH ONLY.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path

SCHEMA = "AUTH2Q2_SNAPSHOT_MANIFEST_1"
PROGRAM_ID = "AUTH-2-DISCOVERY-QUALIFICATION-2"
DATASET_ID = "dataset_v3"
LOCK_REL = "research/datasets/dataset_v3.lock.json"
LISTING_REL = "listing/archive_listing.json"
CHECKSUM_SUFFIX = ".CHECKSUM"
DIGEST = re.compile(r"sha256:([0-9a-f]{64})")
HEX64 = re.compile(r"[0-9a-f]{64}")
MONTH = re.compile(r"\d{4}-(0[1-9]|1[0-2])")
_SEG = r"[^/\\\x00-\x1f\x7f]+"
KLINE = re.compile(rf"data/spot/monthly/klines/(?P<sym>{_SEG})/1h/(?P=sym)-1h-(?P<month>\d{{4}}-\d{{2}})\.zip")
FUNDING = re.compile(rf"data/futures/um/monthly/fundingRate/(?P<sym>{_SEG})/(?P=sym)-fundingRate-"
                     rf"(?P<month>\d{{4}}-\d{{2}})\.zip")
MAX_PATH_BYTES = 1024
CHUNK = 1 << 20
BLOCK = 512
ZERO = b"\0" * BLOCK
_PAX_NAME = b"PaxHeader"
_PAX_FILE_NAME = b"PaxPath"
_PAX_MAX = 4096
TOP_FIELDS = {"schema", "program", "dataset", "counts", "listing", "files"}
DATASET_FIELDS = {"id", "lock_path", "lock_sha256", "last_month", "archive"}
COUNT_FIELDS = {"kline_archive_files", "funding_archive_files", "checksum_files", "files"}
FILE_FIELDS = {"path", "sha256", "size"}


class SnapshotError(Exception):
    """The snapshot, or a tree claimed to be it, is not what its address says. Fail closed."""


def dumps(obj) -> bytes:
    """The canonical bytes of a manifest (one form only: ``load_manifest`` refuses any other)."""
    return (json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def address(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _unique(pairs: list) -> dict:
    keys = [k for k, _ in pairs]
    if len(set(keys)) != len(keys):
        raise ValueError(f"duplicate keys {sorted({k for k in keys if keys.count(k) > 1})}")
    return dict(pairs)


# -- paths -----------------------------------------------------------------------------------------

def data_kind(path: str) -> str | None:
    """'kline' or 'funding' for an archive zip, 'checksum' for its checksum file, 'listing', or None."""
    if path == LISTING_REL:
        return "listing"
    zip_path = path[: -len(CHECKSUM_SUFFIX)] if path.endswith(CHECKSUM_SUFFIX) else path
    kind = "kline" if KLINE.fullmatch(zip_path) else "funding" if FUNDING.fullmatch(zip_path) else None
    if kind is None:
        return None
    return "checksum" if zip_path != path else kind


def valid_path(path) -> bool:
    """A relative POSIX path the snapshot may hold: no absolute path, no '.', '..' or empty segment, no
    backslash, NUL or control character, and one of the archive layouts (or the listing)."""
    if not isinstance(path, str) or not path or len(path.encode("utf-8")) > MAX_PATH_BYTES:
        return False
    if path.startswith("/") or "\\" in path or any(ord(c) < 0x20 or ord(c) == 0x7F for c in path):
        return False
    if any(seg in ("", ".", "..") for seg in path.split("/")):
        return False
    return data_kind(path) is not None


def month_of(path: str) -> str | None:
    m = (KLINE.fullmatch(path) or FUNDING.fullmatch(path))
    return m["month"] if m else None


# -- the manifest ----------------------------------------------------------------------------------

def manifest_problems(man) -> list[str]:
    """Why ``man`` is not a well-formed snapshot manifest ([] when it is)."""
    if not isinstance(man, dict) or set(man) != TOP_FIELDS:
        return [f"manifest fields {sorted(man) if isinstance(man, dict) else type(man).__name__} are not "
                f"{sorted(TOP_FIELDS)}"]
    p: list[str] = []
    if man["schema"] != SCHEMA or man["program"] != PROGRAM_ID:
        p.append(f"schema {str(man['schema'])[:40]!r} / program {str(man['program'])[:60]!r}, not {SCHEMA} / "
                 f"{PROGRAM_ID}")
    ds = man["dataset"]
    if not isinstance(ds, dict) or set(ds) != DATASET_FIELDS or not all(isinstance(v, str) for v in ds.values()):
        return p + [f"dataset fields are not {sorted(DATASET_FIELDS)} (strings)"]
    if (ds["id"], ds["lock_path"]) != (DATASET_ID, LOCK_REL) or not HEX64.fullmatch(ds["lock_sha256"]) \
            or not MONTH.fullmatch(ds["last_month"]) or not ds["archive"].startswith("https://"):
        p.append("dataset identity is malformed")
    files = man["files"]
    if not isinstance(files, list) or not files:
        return p + ["files is not a non-empty list"]
    for i, f in enumerate(files):
        if not isinstance(f, dict) or set(f) != FILE_FIELDS:
            return p + [f"file {i + 1} fields are not {sorted(FILE_FIELDS)}"]
        if not valid_path(f["path"]):
            return p + [f"file {i + 1} path {str(f['path'])[:200]!r} is not a snapshot path"]
        if not isinstance(f["sha256"], str) or not HEX64.fullmatch(f["sha256"]):
            return p + [f"{f['path']}: sha256 is not 64 lowercase hex"]
        if not isinstance(f["size"], int) or isinstance(f["size"], bool) or f["size"] < 0:
            return p + [f"{f['path']}: size is not a whole number of bytes"]
    paths = [f["path"] for f in files]
    if any(a >= b for a, b in zip(paths, paths[1:])):
        p.append("files are not strictly sorted by path (or a path repeats)")
    dirs = {"/".join(x.split("/")[:k]) for x in paths for k in range(1, x.count("/") + 1)}
    clash = sorted(set(paths) & dirs)
    if clash:
        p.append(f"{clash[0]} is both a file and a directory")
    kinds = {x: data_kind(x) for x in paths}
    zips = {x for x, k in kinds.items() if k in ("kline", "funding")}
    sums = {x[: -len(CHECKSUM_SUFFIX)] for x, k in kinds.items() if k == "checksum"}
    if zips != sums:
        p.append(f"zip and checksum files do not pair: {sorted(zips ^ sums)[:3]}")
    late = sorted(x for x in zips if month_of(x) > ds["last_month"])
    if late:
        p.append(f"{late[0]} is after the last month {ds['last_month']}")
    want = {"kline_archive_files": sum(k == "kline" for k in kinds.values()),
            "funding_archive_files": sum(k == "funding" for k in kinds.values()),
            "checksum_files": len(sums), "files": len(paths)}
    if man["counts"] != want:
        p.append(f"counts {man['counts']} do not match the files {want}")
    listing = next((f for f in files if f["path"] == LISTING_REL), None)
    if listing is None or man["listing"] != listing:
        p.append(f"listing {man['listing']} is not the files entry for {LISTING_REL}")
    return p


def load_manifest(raw: bytes, digest: str) -> dict:
    """The manifest, only if its bytes hash to ``digest`` and it is well formed and canonical."""
    m = DIGEST.fullmatch(digest or "") if isinstance(digest, str) else None
    if not m:
        raise SnapshotError(f"{str(digest)[:80]!r} is not a snapshot address (sha256:<64 lowercase hex>)")
    got = hashlib.sha256(raw).hexdigest()
    if got != m[1]:
        raise SnapshotError(f"the manifest hashes to sha256:{got}, not the snapshot address {digest}")
    try:
        man = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique)
    except (UnicodeDecodeError, ValueError) as exc:
        raise SnapshotError(f"the manifest is not JSON ({str(exc)[:120]})") from exc
    problems = manifest_problems(man)
    if problems:
        raise SnapshotError("the manifest is malformed: " + "; ".join(problems[:5]))
    if dumps(man) != raw:
        raise SnapshotError("the manifest is not in its canonical form")
    return man


def build_manifest(entries: list[dict], *, lock_sha256: str, last_month: str, archive: str) -> tuple[dict, bytes]:
    """The manifest over ``entries`` (path, sha256, size, as ``write_tar`` returns them)."""
    files = sorted(entries, key=lambda f: f["path"])
    kinds = [data_kind(f["path"]) for f in files]
    listing = next((f for f in files if f["path"] == LISTING_REL), None)
    man = {"schema": SCHEMA, "program": PROGRAM_ID,
           "dataset": {"id": DATASET_ID, "lock_path": LOCK_REL, "lock_sha256": lock_sha256,
                       "last_month": last_month, "archive": archive},
           "counts": {"kline_archive_files": kinds.count("kline"), "funding_archive_files": kinds.count("funding"),
                      "checksum_files": kinds.count("checksum"), "files": len(files)},
           "listing": dict(listing) if listing else None, "files": [dict(f) for f in files]}
    problems = manifest_problems(man)
    if problems:
        raise SnapshotError("cannot build a manifest: " + "; ".join(problems[:5]))
    return man, dumps(man)


# -- the canonical tar -----------------------------------------------------------------------------

def _octal(n: int, width: int) -> bytes:
    out = f"{n:0{width - 1}o}".encode() + b"\0"
    if n < 0 or len(out) != width:
        raise SnapshotError(f"{n} does not fit a {width}-byte tar field")
    return out


def _header(name: bytes, size: int, typeflag: bytes) -> bytes:
    """The one ustar header this module writes for (name, size, type): every other field is fixed."""
    if not name or len(name) > 100 or b"\0" in name:
        raise SnapshotError(f"{name[:120]!r} is not a ustar name")
    h = bytearray(BLOCK)
    h[0:len(name)] = name
    h[100:108] = b"0000644\0"
    h[108:116] = b"0000000\0"
    h[116:124] = b"0000000\0"
    h[124:136] = _octal(size, 12)
    h[136:148] = _octal(0, 12)
    h[148:156] = b" " * 8
    h[156:157] = typeflag
    h[257:263] = b"ustar\0"
    h[263:265] = b"00"
    h[329:337] = b"0000000\0"
    h[337:345] = b"0000000\0"
    h[148:156] = f"{sum(h):06o}".encode() + b"\0 "
    return bytes(h)


def _needs_pax(path: str) -> bool:
    return not path.isascii() or len(path) > 100


def _pax_record(key: str, value: str) -> bytes:
    body = f" {key}={value}\n".encode("utf-8")
    n = len(body) + 1
    for _ in range(8):
        m = len(body) + len(str(n))
        if m == n:
            return str(n).encode() + body
        n = m
    raise SnapshotError("pax record length does not converge")  # unreachable for any real length


def _pad(n: int) -> bytes:
    return b"\0" * (-n % BLOCK)


def _member_headers(path: str, size: int) -> bytes:
    if _needs_pax(path):
        rec = _pax_record("path", path)
        return _header(_PAX_NAME, len(rec), b"x") + rec + _pad(len(rec)) + _header(_PAX_FILE_NAME, size, b"0")
    return _header(path.encode("ascii"), size, b"0")


def _regular_file(root: Path, rel: str) -> Path:
    """``root/rel``, refused unless every segment below ``root`` is a real directory and the leaf a regular
    file (no symlink anywhere below the root)."""
    if not valid_path(rel):
        raise SnapshotError(f"{rel[:200]!r} is not a snapshot path")
    cur = root
    parts = rel.split("/")
    for i, seg in enumerate(parts):
        cur = cur / seg
        try:
            mode = os.lstat(cur).st_mode
        except FileNotFoundError as exc:
            raise SnapshotError(f"{rel}: missing") from exc
        ok = stat.S_ISREG(mode) if i == len(parts) - 1 else stat.S_ISDIR(mode)
        if not ok:
            raise SnapshotError(f"{rel}: {'/'.join(parts[: i + 1])} is not a "
                                f"{'regular file' if i == len(parts) - 1 else 'directory'}")
    return cur


def write_tar(root: Path, paths: list[str], out: Path) -> tuple[list[dict], str, int]:
    """Write the canonical tar of ``paths`` (sorted here) under ``root`` to ``out``.

    Returns (entries, tar sha256, tar bytes), where entries are each file's path, sha256 and size, hashed in
    the same pass that writes it, so the manifest built from them describes exactly the bytes in the tar."""
    paths = sorted(paths)
    if len(set(paths)) != len(paths):
        raise SnapshotError("a path is listed twice")
    th = hashlib.sha256()
    total = 0
    entries = []
    with open(out, "wb") as f:
        def put(b: bytes) -> None:
            nonlocal total
            f.write(b)
            th.update(b)
            total += len(b)

        for rel in paths:
            src = _regular_file(root, rel)
            size = os.stat(src).st_size
            put(_member_headers(rel, size))
            fh = hashlib.sha256()
            got = 0
            with open(src, "rb") as s:
                while chunk := s.read(CHUNK):
                    fh.update(chunk)
                    got += len(chunk)
                    put(chunk)
            if got != size:
                raise SnapshotError(f"{rel}: changed while it was being packed")
            put(_pad(size))
            entries.append({"path": rel, "sha256": fh.hexdigest(), "size": size})
        put(ZERO * 2)
    return entries, th.hexdigest(), total


class _Stream:
    """Exact reads from a file object, hashing every byte (the tar's own sha256)."""

    def __init__(self, f) -> None:
        self.f, self.h, self.n = f, hashlib.sha256(), 0

    def read(self, n: int) -> bytes:
        out = bytearray()
        while len(out) < n:
            b = self.f.read(min(n - len(out), CHUNK))
            if not b:
                raise SnapshotError(f"the tar ends early, at byte {self.n + len(out)}")
            out += b
        self.h.update(out)
        self.n += n
        return bytes(out)


def _size_field(block: bytes) -> int:
    field = block[124:136]
    if not re.fullmatch(rb"[0-7]{11}\0", field):
        raise SnapshotError("a tar header has a malformed size field")
    return int(field[:11], 8)


def _pax_path(rec: bytes) -> str:
    try:
        text = rec.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SnapshotError("a pax record is not UTF-8") from exc
    m = re.fullmatch(r"\d+ path=(.+)\n", text, flags=re.S)
    if not m or _pax_record("path", m[1]) != rec or not _needs_pax(m[1]):
        raise SnapshotError("a pax header is not the one canonical path record")
    return m[1]


def _create(dest: Path, rel: str):
    path = dest / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0), 0o644)
    return os.fdopen(fd, "wb")


def scan_tar(f, files: list[dict], dest: Path | None = None) -> str:
    """Read a canonical snapshot tar whose members are exactly ``files`` (the manifest's list, in its order),
    checking each member's path, size and sha256; with ``dest``, write each one below it. Returns the tar's
    sha256. Raises SnapshotError naming the first file that is wrong."""
    s = _Stream(f)
    for i, want in enumerate(files):
        block = s.read(BLOCK)
        if block == ZERO:
            raise SnapshotError(f"{want['path']}: missing (the tar ends after {i} of {len(files)} members)")
        kind = block[156:157]
        if kind == b"x":
            size = _size_field(block)
            if size > _PAX_MAX or block != _header(_PAX_NAME, size, b"x"):
                raise SnapshotError(f"member {i + 1}: non-canonical pax header (expected {want['path']})")
            rec = s.read(size)
            if s.read(-size % BLOCK).strip(b"\0"):
                raise SnapshotError(f"member {i + 1}: pax padding is not zero")
            path = _pax_path(rec)
            block = s.read(BLOCK)
            size = _size_field(block)
            if block != _header(_PAX_FILE_NAME, size, b"0"):
                raise SnapshotError(f"{path}: non-canonical file header after its pax record")
        elif kind == b"0":
            name = block[0:100].split(b"\0", 1)[0]
            try:
                path = name.decode("ascii")
            except UnicodeDecodeError as exc:
                raise SnapshotError(f"member {i + 1}: a ustar name that is not ASCII") from exc
            size = _size_field(block)
            if not name or _needs_pax(path) or block != _header(name, size, b"0"):
                raise SnapshotError(f"{path or f'member {i + 1}'}: non-canonical header")
        else:
            raise SnapshotError(f"member {i + 1} is not a regular file (tar type {kind!r}); links, directories "
                                "and every other type are refused")
        if path != want["path"]:
            raise SnapshotError(f"member {i + 1} is {path[:200]!r}; the manifest lists {want['path']!r} there")
        if size != want["size"]:
            raise SnapshotError(f"{path}: {size} bytes in the tar, {want['size']} in the manifest")
        fh = hashlib.sha256()
        out = _create(dest, path) if dest is not None else None
        try:
            left = size
            while left:
                chunk = s.read(min(left, CHUNK))
                fh.update(chunk)
                if out is not None:
                    out.write(chunk)
                left -= len(chunk)
        finally:
            if out is not None:
                out.close()
        if s.read(-size % BLOCK).strip(b"\0"):
            raise SnapshotError(f"{path}: padding after the file is not zero")
        if fh.hexdigest() != want["sha256"]:
            raise SnapshotError(f"{path}: sha256 {fh.hexdigest()} is not the manifest's {want['sha256']}")
    end = s.read(2 * BLOCK)
    if end != ZERO * 2:
        raise SnapshotError("the tar holds a member the manifest does not list, or its end is malformed")
    if f.read(1):
        raise SnapshotError("bytes follow the end of the tar")
    return s.h.hexdigest()


# -- trees -----------------------------------------------------------------------------------------

def _empty_dir(dest: Path) -> None:
    if dest.is_symlink():
        raise SnapshotError(f"{dest} is a symlink")
    if dest.exists():
        if not dest.is_dir() or any(dest.iterdir()):
            raise SnapshotError(f"{dest} is not a new or empty directory; a restore never writes over files")
    else:
        dest.mkdir(parents=True)


def restore(tar: Path, man: dict, dest: Path, tar_sha256: str | None = None) -> str:
    """Restore the snapshot tar into ``dest`` (new or empty), every file checked. Returns the tar sha256."""
    _empty_dir(dest)
    with open(tar, "rb") as f:
        got = scan_tar(f, man["files"], dest)
    if tar_sha256 is not None and got != tar_sha256:
        raise SnapshotError(f"the tar hashes to {got}, not {tar_sha256}")
    return got


def verify_tree(root: Path, man: dict) -> list[str]:
    """Why the tree at ``root`` is not exactly the manifest's files ([] when it is): every file must be a
    regular file the manifest lists, with its size and sha256, and every listed file must be there."""
    want = {f["path"]: f for f in man["files"]}
    seen: set[str] = set()
    problems: list[str] = []
    if not root.is_dir() or root.is_symlink():
        return [f"{root} is not a directory"]
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        for d in dirnames:
            if os.path.islink(os.path.join(dirpath, d)):
                problems.append(f"{Path(dirpath, d).relative_to(root).as_posix()}: a symlink")
        for name in sorted(filenames):
            p = Path(dirpath, name)
            rel = p.relative_to(root).as_posix()
            mode = os.lstat(p).st_mode
            if not stat.S_ISREG(mode):
                problems.append(f"{rel}: not a regular file")
                continue
            f = want.get(rel)
            if f is None:
                problems.append(f"{rel}: not in the manifest")
                continue
            seen.add(rel)
            if os.lstat(p).st_size != f["size"]:
                problems.append(f"{rel}: {os.lstat(p).st_size} bytes, the manifest says {f['size']}")
                continue
            h = hashlib.sha256()
            with open(p, "rb") as fh:
                while chunk := fh.read(CHUNK):
                    h.update(chunk)
            if h.hexdigest() != f["sha256"]:
                problems.append(f"{rel}: sha256 {h.hexdigest()} is not the manifest's {f['sha256']}")
    problems += [f"{rel}: missing" for rel in sorted(set(want) - seen)]
    return problems


def tree_digest(root: Path) -> str:
    """sha256 over every regular file below ``root`` (path, sha256, size), computed from the disk alone, so two
    restores can be compared without trusting either's manifest check."""
    lines = []
    for dirpath, _dirs, filenames in os.walk(root, followlinks=False):
        for name in filenames:
            p = Path(dirpath, name)
            h = hashlib.sha256()
            with open(p, "rb") as fh:
                while chunk := fh.read(CHUNK):
                    h.update(chunk)
            lines.append(f"{p.relative_to(root).as_posix()}\0{h.hexdigest()}\0{p.stat().st_size}\n")
    return "sha256:" + hashlib.sha256("".join(sorted(lines)).encode("utf-8")).hexdigest()


# -- CLI -------------------------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("address")
    a.add_argument("--manifest", required=True)
    for name in ("check", "restore", "verify-tree"):
        p = sub.add_parser(name)
        p.add_argument("--manifest", required=True)
        p.add_argument("--digest", required=True)
        p.add_argument("--tar", required=name == "restore")
        p.add_argument("--tar-sha256")
        if name == "restore":
            p.add_argument("--dest", required=True)
            p.add_argument("--receipt")
        if name == "verify-tree":
            p.add_argument("--dir", required=True)
    args = ap.parse_args(argv)
    raw = Path(args.manifest).read_bytes()
    if args.cmd == "address":
        print(address(raw))
        return 0
    try:
        man = load_manifest(raw, args.digest)
        if args.cmd == "check":
            if args.tar:
                with open(args.tar, "rb") as f:
                    got = scan_tar(f, man["files"])
                if args.tar_sha256 and got != args.tar_sha256:
                    raise SnapshotError(f"the tar hashes to {got}, not {args.tar_sha256}")
                print(f"tar sha256 {got}")
            print(f"SNAPSHOT_CHECK = PASS ({man['counts']['files']} files, {args.digest})")
        elif args.cmd == "restore":
            got = restore(Path(args.tar), man, Path(args.dest), args.tar_sha256)
            if args.receipt:
                Path(args.receipt).write_text(json.dumps({"address": args.digest, "tar_sha256": got,
                                                          "files": man["counts"]["files"]}, sort_keys=True) + "\n")
            print(f"SNAPSHOT_RESTORE = PASS ({man['counts']['files']} files verified into {args.dest})")
        else:
            problems = verify_tree(Path(args.dir), man)
            for line in problems[:50]:
                print(f"::error::SNAPSHOT_VERIFY: {line}")
            if problems:
                raise SnapshotError(f"{len(problems)} file(s) differ from the manifest; first: {problems[0]}")
            print(f"SNAPSHOT_VERIFY = PASS ({man['counts']['files']} files match {args.digest})")
    except (SnapshotError, OSError) as exc:
        print(f"::error::SNAPSHOT_REFUSED: {exc}")
        print("SNAPSHOT = FAIL")
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
