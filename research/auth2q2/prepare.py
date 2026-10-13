#!/usr/bin/env python3
"""Preparation: the one stage that uses the network (review section 3, stages 1 and 2; RT-1 and RT-2).

    python -m auth2q2.prepare run --repo . --work DIR --out-dir DIR [--workers 32]

  list     dataset_v3.discover lists the live archive once (research/auth2, unchanged).
  replay   the listing discover kept becomes the snapshot's listing, and discover runs again under
           listing.replay with every socket refused (offline.guard): it must return exactly the same tuple.
  bind     the file counts must be the lock's (counts.kline_archive_files, counts.funding_archive_files).
  fetch    every zip through archive.fetch_verified, WORKERS at a time: each is checked against its published
           .CHECKSUM and cached with it, as the build reads it. A file that fails is retried once; any file still
           failing fails the preparation (nothing is published).
  identity every symbol's archive identity (sha256 over "<name> <sha256>" lines, as dataset_v3.load_symbol
           computes it) must equal candidates.json's archive_sha256, and each funding asset's must equal
           engine_data.json's. So the snapshot is the archive the committed lock was built from, byte for byte.
  pack     the canonical tar and manifest (snapshot.py), and the preparation record, which carries what varies
           between runs (durations, run id) and is never part of the address.

Nothing here writes the repository, a ledger or a release; the publish job (release.py) does that last step.
PAPER / RESEARCH ONLY. It reads Binance's public data archive and nothing else.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from auth2 import archive as A  # noqa: E402
from auth2 import dataset_v3 as D  # noqa: E402
from auth2q2 import listing as L  # noqa: E402
from auth2q2 import offline as OFF  # noqa: E402
from auth2q2 import snapshot as SN  # noqa: E402

WORKERS = 32
RETRY_WORKERS = 8
PROGRESS_EVERY = 2000
RECORD_SCHEMA = "AUTH2Q2_PREPARATION_RECORD_1"
MANIFEST, RECORD, TAR = "manifest.json", "prepare-record.json", "snapshot.tar"


class PreparationError(Exception):
    pass


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while chunk := f.read(SN.CHUNK):
            h.update(chunk)
    return h.hexdigest()


def data_keys(found: tuple) -> list[str]:
    """Every zip the build reads, in its order: each symbol's klines, then the A3 funding files."""
    symbols, kline_keys, funding_keys = found
    return [k for s in symbols for k in kline_keys[s]] + [k for s in D.A3_ASSETS for k in funding_keys[s]]


def replay_problems(listing: dict, found: tuple, base: str = A.DEFAULT_BASE) -> list[str]:
    """discover under the replayed listing, with no network, must return exactly ``found``."""
    refused: list[str] = []
    try:
        with OFF.guard(refused), L.replay(listing) as opener:
            again = D.discover(base)
    except (L.ReplayRefused, OFF.NetworkRemoved) as exc:
        return [f"REPLAY: discover made a request the snapshot cannot answer: {str(exc)[:200]}"]
    p = []
    if again != found:
        p.append("REPLAY: discover under the replayed listing does not return what the live archive gave")
    if opener.refused or refused:
        p.append(f"REPLAY: refused requests {(opener.refused + refused)[:3]}")
    return p


def count_problems(repo: Path, found: tuple) -> list[str]:
    lock = json.loads((repo / D.LOCK_REL).read_text())["counts"]
    symbols, kline_keys, funding_keys = found
    got = {"kline_archive_files": sum(len(kline_keys[s]) for s in symbols),
           "funding_archive_files": sum(len(funding_keys[s]) for s in D.A3_ASSETS)}
    return [f"BIND: {k} is {v}, the lock says {lock.get(k)}" for k, v in got.items() if lock.get(k) != v]


def fetch_all(keys: list[str], cache: Path, base: str, workers: int, log) -> list[str]:
    """Fetch every key with archive.fetch_verified; returns the failures left after one retry."""
    def run(batch: list[str], n_workers: int) -> dict[str, str]:
        failed: dict[str, str] = {}
        t0 = time.monotonic()
        with ThreadPoolExecutor(max_workers=n_workers) as pool:
            futures = {pool.submit(A.fetch_verified, k, cache, base): k for k in batch}
            for n, fut in enumerate(as_completed(futures), 1):
                try:
                    fut.result()
                except Exception as exc:  # noqa: BLE001 - recorded; retried once, then it fails the preparation
                    failed[futures[fut]] = f"{type(exc).__name__}: {exc}"[:300]
                if n % PROGRESS_EVERY == 0:
                    log(f"  {n}/{len(batch)} files, {len(failed)} failed, {round(time.monotonic() - t0)} s")
        return failed

    first = run(keys, workers)
    if first:
        log(f"retrying {len(first)} file(s) once")
    left = run(sorted(first), min(RETRY_WORKERS, workers)) if first else {}
    return [f"{k}: {v}" for k, v in sorted(left.items())]


def archive_identity(cache: Path, keys: list[str]) -> str:
    lines = [f"{Path(k).name} {sha256_file(cache / k)}" for k in keys]
    return hashlib.sha256(("\n".join(lines) + "\n").encode()).hexdigest()


def identity_problems(repo: Path, cache: Path, found: tuple) -> tuple[list[str], int]:
    """(problems, symbols checked): the snapshot's archive identity against the committed lock tables."""
    symbols, kline_keys, funding_keys = found
    tables = repo / D.TABLE_DIR_REL
    cands = json.loads((tables / "candidates.json").read_text())["symbols"]
    funding = json.loads((tables / "engine_data.json").read_text())["funding"]
    p = [f"IDENTITY: {s} is in the lock but not in the archive listing" for s in sorted(set(cands) - set(symbols))]
    checked = 0
    for s in symbols:
        if s not in cands:
            continue  # a symbol with files but no on-grid rows: counted in the lock, no identity recorded
        checked += 1
        keys = kline_keys[s]
        months = [keys[0][-11:-4], keys[-1][-11:-4], len(keys)]
        if cands[s].get("archive_months") != months:
            p.append(f"IDENTITY: {s} months {months}, the lock says {cands[s].get('archive_months')}")
        elif archive_identity(cache, keys) != cands[s].get("archive_sha256"):
            p.append(f"IDENTITY: {s} archive files differ from the lock's archive_sha256")
    for s in D.A3_ASSETS:
        keys = funding_keys[s]
        if funding[s].get("archive_files") != len(keys) or archive_identity(cache, keys) != funding[s].get(
                "archive_sha256"):
            p.append(f"IDENTITY: {s} funding files differ from the lock")
    return p, checked


def checksum_problems(cache: Path, keys: list[str]) -> list[str]:
    """Each checksum file must be exactly what fetch_verified writes for its zip ("<sha256>  <name>\\n"), so two
    preparations write the same bytes."""
    p = []
    for k in keys:
        want = f"{sha256_file(cache / k)}  {Path(k).name}\n".encode()
        got = (cache / (k + SN.CHECKSUM_SUFFIX)).read_bytes()
        if got != want:
            p.append(f"CHECKSUM: {k}{SN.CHECKSUM_SUFFIX} is not the canonical checksum line of its zip")
            if len(p) >= 5:
                break
    return p


def build_snapshot(repo: Path, cache: Path, found: tuple, out_dir: Path) -> dict:
    """Write the listing into ``cache``, then the canonical tar and manifest into ``out_dir``. ``cache`` must
    hold exactly the found keys, their checksum files and nothing else."""
    listing = L.from_discover(found)
    raw_listing = L.dumps(listing)
    L.load(raw_listing)  # well formed and canonical, or refused
    keys = data_keys(found)
    p = checksum_problems(cache, keys)
    if p:
        raise PreparationError("; ".join(p))
    (cache / SN.LISTING_REL).parent.mkdir(parents=True, exist_ok=True)
    (cache / SN.LISTING_REL).write_bytes(raw_listing)
    paths = keys + [k + SN.CHECKSUM_SUFFIX for k in keys] + [SN.LISTING_REL]
    expected = set(paths)
    stray = []
    for dirpath, _dirs, files in os.walk(cache, followlinks=False):
        stray += [x for x in (Path(dirpath, f).relative_to(cache).as_posix() for f in files) if x not in expected]
    if stray:
        raise PreparationError(f"the cache holds {len(stray)} file(s) the snapshot would not list: {stray[:3]}")
    out_dir.mkdir(parents=True, exist_ok=True)
    entries, tar_sha, tar_bytes = SN.write_tar(cache, paths, out_dir / TAR)
    lock_sha = sha256_file(repo / D.LOCK_REL)
    man, raw = SN.build_manifest(entries, lock_sha256=lock_sha, last_month=D.LAST_MONTH, archive=A.LIST_BASE)
    (out_dir / MANIFEST).write_bytes(raw)
    return {"address": SN.address(raw), "tar_sha256": tar_sha, "tar_bytes": tar_bytes, "manifest_bytes": len(raw),
            "counts": man["counts"], "lock_sha256": lock_sha, "symbols": len(found[0])}


def run(repo: Path, work: Path, out_dir: Path, workers: int = WORKERS, base: str = A.DEFAULT_BASE, log=print) -> dict:
    """The whole preparation; the record it writes, or PreparationError naming every problem."""
    cache = work / "cache"
    if cache.exists() and any(cache.iterdir()):
        raise PreparationError(f"{cache} is not empty; a preparation starts cold")
    cache.mkdir(parents=True, exist_ok=True)
    seconds: dict[str, int] = {}
    t = time.monotonic()
    found = D.discover(base)
    seconds["list"] = round(time.monotonic() - t)
    keys = data_keys(found)
    log(f"listed {len(found[0])} symbols, {len(keys)} archive files in {seconds['list']} s")
    t = time.monotonic()
    p = replay_problems(L.from_discover(found), found, base) + count_problems(repo, found)
    seconds["replay_and_bind"] = round(time.monotonic() - t)
    if p:
        raise PreparationError("; ".join(p))
    t = time.monotonic()
    failures = fetch_all(keys, cache, base, workers, log)
    seconds["fetch"] = round(time.monotonic() - t)
    log(f"fetched {len(keys) - len(failures)}/{len(keys)} files with {workers} workers in {seconds['fetch']} s")
    if failures:
        raise PreparationError(f"FETCH: {len(failures)} file(s) failed after one retry: {failures[:3]}")
    t = time.monotonic()
    p, checked = identity_problems(repo, cache, found)
    seconds["identity"] = round(time.monotonic() - t)
    if p:
        raise PreparationError("; ".join(p[:10]))
    t = time.monotonic()
    snap = build_snapshot(repo, cache, found, out_dir)
    seconds["pack"] = round(time.monotonic() - t)
    record = {"schema": RECORD_SCHEMA, "program": SN.PROGRAM_ID, **snap, "workers": workers,
              "symbols_with_lock_identity": checked, "checksum_failures": 0, "replay_equivalent": True,
              "seconds": seconds, "python": platform.python_version(),
              "commit": os.environ.get("GITHUB_SHA"), "run_id": os.environ.get("GITHUB_RUN_ID"),
              "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
              "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    (out_dir / RECORD).write_text(json.dumps(record, indent=1, sort_keys=True) + "\n")
    return record


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--repo", default=".")
    r.add_argument("--work", required=True, help="an empty directory for the cold archive cache")
    r.add_argument("--out-dir", required=True, help="where manifest.json, snapshot.tar and the record go")
    r.add_argument("--workers", type=int, default=WORKERS)
    a = ap.parse_args(argv)
    try:
        rec = run(Path(a.repo).resolve(), Path(a.work).resolve(), Path(a.out_dir).resolve(), max(1, a.workers),
                  log=lambda m: print(m, flush=True))
    except (PreparationError, SN.SnapshotError, A.ArchiveError) as exc:
        print(f"::error::PREPARATION_REFUSED: {str(exc)[:1500]}")
        print("PREPARATION = FAIL")
        return 3
    print(json.dumps(rec, indent=1, sort_keys=True))
    print(f"PREPARATION = PASS address={rec['address']} tar_sha256={rec['tar_sha256']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
