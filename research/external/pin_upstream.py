#!/usr/bin/env python3
"""Pin, fetch and verify external upstream sources by content hash.

External benchmark candidates are never vendored into this repository. Two of the
pinned projects carry GPL-3.0 and three carry no license at all, so copying their
source here would be a license incorporation decision that no directive has
authorised. Instead this module pins each file by upstream commit plus content
hash, fetches it on demand into a scratch directory, and refuses to hand back
bytes that do not match the pin.

Fetching goes through raw.githubusercontent.com because the sandbox egress policy
answers 403 to github.com and codeload.github.com, so neither `git clone` nor a
tarball download is available. Fetching one blob at a pinned commit is in any case
the narrower operation.

Two digests are recorded per file:

  sha256        - over the bytes as fetched. The identity used by every gate.
  git_blob_sha1 - sha1(b"blob <len>\\0" + bytes), the value GitHub displays as a
                  file's blob SHA. Recorded so a pin can be checked against what a
                  human read in the GitHub UI without downloading anything.

A source whose upstream has gone away is listed in upstream_vanished.json, which
leaves upstream_pins.json byte-identical. Its pins stay the identity: a 404 on one
of its files is recorded rather than failed, but only while the records the entry
names are present with their pinned sha256, and any bytes that are fetched must
still match exactly. Nothing is cached for a vanished file, so --materialize
refuses it.

Usage:
    python3 research/external/pin_upstream.py --verify        # gate: fetch, check every pin
    python3 research/external/pin_upstream.py --refresh       # fill in empty hashes
    python3 research/external/pin_upstream.py --cache-dir DIR # where fetched bytes land
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PINS_PATH = REPO_ROOT / "research" / "external" / "upstream_pins.json"
VANISHED_PATH = REPO_ROOT / "research" / "external" / "upstream_vanished.json"
RAW_BASE = "https://raw.githubusercontent.com"
TIMEOUT_SECONDS = 60


def git_blob_sha1(data: bytes) -> str:
    """The blob SHA GitHub shows for a file: sha1 over git's blob header plus content."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def raw_url(repo: str, commit: str, path: str) -> str:
    return f"{RAW_BASE}/{repo}/{commit}/{path}"


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "trading-lab-os-pin/1"})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        return response.read()


def load_pins() -> dict:
    return json.loads(PINS_PATH.read_text())


def save_pins(pins: dict) -> None:
    # The vanished entries live in their own file; they never leak into the pins.
    clean = json.loads(json.dumps(pins))
    for source in clean["sources"].values():
        source.pop("upstream_vanished", None)
    PINS_PATH.write_text(json.dumps(clean, indent=2) + "\n")


def attach_vanished(pins: dict, path: Path | None = None) -> list[str]:
    """Attach each upstream_vanished.json entry to its pinned source. Returns failures.

    An entry for a source that is not pinned is a failure, not a no-op: a list of
    excuses that names nothing it excuses is a list nobody is checking.
    """
    path = VANISHED_PATH if path is None else path
    if not path.exists():
        return []
    vanished = json.loads(path.read_text(encoding="utf-8"))
    failures = []
    for key, entry in vanished.get("sources", {}).items():
        if key not in pins["sources"]:
            failures.append(f"{key}: listed in {path.name} but not pinned")
            continue
        pins["sources"][key]["upstream_vanished"] = dict(entry, authority=vanished.get("authority"))
    return failures


def iter_files(pins: dict):
    """Yield (source_key, source, file_entry) for every pinned file."""
    for key, source in pins["sources"].items():
        for entry in source.get("files", []):
            yield key, source, entry


def vanished_problems(key: str, source: dict, repo_root: Path | None = None) -> list[str]:
    """Why a source's ``upstream_vanished`` block cannot excuse a 404. Empty when it can.

    The block must say VANISHED, name an authority, and name at least one record
    that is in this repository with exactly its pinned sha256: the evidence that
    the upstream is gone has to be as pinned as the bytes were. Every file of the
    source must keep a full pin, because the pin is all that is left of its identity.
    """
    repo_root = REPO_ROOT if repo_root is None else repo_root
    block = source.get("upstream_vanished")
    if block is None:
        return [f"{key}: no upstream_vanished block"]
    problems = []
    if (block.get("repo"), block.get("commit")) != (source.get("repo"), source.get("commit")):
        problems.append(f"{key}: upstream_vanished names {block.get('repo')}@{block.get('commit')}, "
                        f"not the pinned {source.get('repo')}@{source.get('commit')}")
    if block.get("state") != "VANISHED":
        problems.append(f"{key}: upstream_vanished.state is {block.get('state')!r}, not 'VANISHED'")
    if not block.get("authority"):
        problems.append(f"{key}: upstream_vanished names no authority")
    records = block.get("records") or {}
    if not records:
        problems.append(f"{key}: upstream_vanished names no record")
    for rel, want in records.items():
        raw = repo_root / rel
        path = raw.resolve()
        if raw.is_symlink() or repo_root.resolve() not in path.parents or not path.is_file():
            problems.append(f"{key}: vanished record {rel} is not a file in this repository")
        elif sha256(path.read_bytes()) != want:
            problems.append(f"{key}: vanished record {rel} does not match its pinned sha256")
    for entry in source.get("files", []):
        if entry.get("expect_missing"):
            problems.append(f"{key}:{entry['path']}: expect_missing cannot be combined with upstream_vanished")
        elif not (entry.get("sha256") and entry.get("git_blob_sha1") and entry.get("size_bytes")):
            problems.append(f"{key}:{entry['path']}: a vanished source keeps a full pin (sha256, blob sha1, size)")
    return problems


def process(pins: dict, cache_dir: Path, refresh: bool) -> tuple[list[str], list[str]]:
    """Fetch every pinned file. Returns (failures, changes)."""
    failures: list[str] = []
    changes: list[str] = []
    vanished = {key: vanished_problems(key, source)
                for key, source in pins["sources"].items() if "upstream_vanished" in source}
    for problems in vanished.values():
        failures.extend(problems)

    for key, source, entry in iter_files(pins):
        repo, commit, path = source["repo"], source["commit"], entry["path"]
        label = f"{key}:{path}"
        url = raw_url(repo, commit, path)

        expect_missing = entry.get("expect_missing", False)
        try:
            data = fetch(url)
        except urllib.error.HTTPError as exc:
            if exc.code == 404 and expect_missing:
                print(f"  OK   {label}: absent upstream, as pinned (404)")
                continue
            if exc.code == 404 and key in vanished and not vanished[key]:
                print(f"  VANISHED {label}: upstream gone (404); identity = pinned sha256 "
                      f"{entry['sha256'][:16]}..., nothing cached")
                continue
            failures.append(f"{label}: HTTP {exc.code} fetching {url}")
            continue
        except (urllib.error.URLError, TimeoutError) as exc:
            failures.append(f"{label}: {exc} fetching {url}")
            continue

        if expect_missing:
            failures.append(f"{label}: pinned as absent upstream but fetched {len(data)} bytes")
            continue

        got_sha256, got_blob = sha256(data), git_blob_sha1(data)

        # A blob SHA transcribed from the GitHub UI is the check that the pinned
        # commit and path name the file a human actually read.
        want_blob = entry.get("git_blob_sha1")
        if want_blob and want_blob != got_blob:
            failures.append(
                f"{label}: git blob SHA mismatch\n"
                f"      pinned {want_blob}\n"
                f"      got    {got_blob}"
            )
            continue

        want_sha256 = entry.get("sha256")
        if want_sha256:
            if want_sha256 != got_sha256:
                failures.append(
                    f"{label}: sha256 mismatch — upstream content changed at a pinned commit\n"
                    f"      pinned {want_sha256}\n"
                    f"      got    {got_sha256}"
                )
                continue
        elif refresh:
            entry["sha256"] = got_sha256
            entry["size_bytes"] = len(data)
            entry.setdefault("git_blob_sha1", got_blob)
            changes.append(f"{label}: recorded sha256 {got_sha256[:16]}...")
        else:
            failures.append(f"{label}: no sha256 pinned; run with --refresh")
            continue

        destination = cache_dir / key / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            destination.chmod(stat.S_IRUSR | stat.S_IWUSR)  # allow refresh of an existing pin
        destination.write_bytes(data)
        # The cache is evidence, not a working copy. Anything that wants to run these
        # files must materialise its own disposable workspace first.
        destination.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        print(f"  OK   {label}  sha256={got_sha256[:16]}...  {len(data)} bytes")

    return failures, changes


# Credential-shaped environment variables. An isolated upstream execution must not
# inherit any of them: the workspace runs third-party code, and it needs no identity.
CREDENTIAL_ENV_MARKERS = ("TOKEN", "SECRET", "PASSWORD", "APIKEY", "API_KEY",
                          "PRIVATE_KEY", "CREDENTIAL", "SESSION", "COOKIE")


def credential_env_present(environ=None) -> list[str]:
    """Names of credential-shaped variables visible to this process."""
    environ = os.environ if environ is None else environ
    return sorted(
        name for name in environ
        if any(marker in name.upper() for marker in CREDENTIAL_ENV_MARKERS)
    )


def materialize(pins: dict, cache_dir: Path, workspace: Path) -> list[Path]:
    """Copy verified pinned files into a disposable execution workspace.

    Upstream scripts are mutable and are not ours. Running them where the evidence
    lives would let a candidate rewrite the very bytes it is being judged against, so
    the cache stays read-only and every execution gets a throwaway copy.

    The workspace must not already exist and be populated: reusing one silently carries
    state between candidates, which is the contamination this separation exists to stop.
    """
    cache_dir, workspace = cache_dir.resolve(), workspace.resolve()
    if workspace == cache_dir or cache_dir in workspace.parents:
        raise SystemExit(
            f"refusing to materialise inside the pin cache ({cache_dir}): "
            "the cache is read-only evidence, not a working directory"
        )
    if workspace.exists() and any(workspace.iterdir()):
        raise SystemExit(f"refusing to reuse a non-empty workspace: {workspace}")

    written: list[Path] = []
    for key, _, entry in iter_files(pins):
        if entry.get("expect_missing"):
            continue
        source = cache_dir / key / entry["path"]
        if not source.exists() and "upstream_vanished" in pins["sources"][key]:
            raise SystemExit(
                f"refusing to materialise {key}:{entry['path']}: the upstream has vanished and no "
                "verified bytes exist in the cache. Use a recovered copy verified against the pins "
                "(H1-MATERIALISATION-AMENDMENT-1); never a repin or a reconstruction.")
        if not source.exists():
            raise SystemExit(f"not in cache: {source}. Run --verify first.")
        destination = workspace / key / entry["path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        destination.chmod(stat.S_IRUSR | stat.S_IWUSR)  # writable in the workspace only
        written.append(destination)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true", help="fail if any pin does not match")
    parser.add_argument("--refresh", action="store_true", help="record hashes that are not yet pinned")
    parser.add_argument("--cache-dir", default=None, help="directory for fetched bytes (read-only evidence)")
    parser.add_argument("--materialize", default=None, metavar="DIR",
                        help="copy verified pins into a fresh disposable execution workspace")
    args = parser.parse_args()

    if not args.verify and not args.refresh:
        parser.error("pass --verify or --refresh")

    pins = load_pins()
    attach_failures = attach_vanished(pins)
    cache_dir = Path(args.cache_dir) if args.cache_dir else REPO_ROOT / ".upstream-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    print(f"Pinned sources: {len(pins['sources'])}   cache: {cache_dir}")
    failures, changes = process(pins, cache_dir, refresh=args.refresh)
    failures = attach_failures + failures

    if changes:
        save_pins(pins)
        print(f"\nRecorded {len(changes)} new hash(es) in {PINS_PATH.relative_to(REPO_ROOT)}")

    if failures:
        print(f"\nUPSTREAM_PIN_GATE = FAIL ({len(failures)} problem(s))", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1

    gone = sorted(key for key, source in pins["sources"].items() if "upstream_vanished" in source)
    print("\nUPSTREAM_PIN_GATE = PASS" + (f" (upstream VANISHED, pins retained: {', '.join(gone)})" if gone else ""))

    if args.materialize:
        leaked = credential_env_present()
        if leaked:
            print(f"\nISOLATION_GATE = FAIL: credential-shaped environment present: {leaked}",
                  file=sys.stderr)
            print("  An isolated upstream execution needs no identity. Scrub these before "
                  "materialising a workspace.", file=sys.stderr)
            return 1
        written = materialize(pins, cache_dir, Path(args.materialize))
        print(f"ISOLATION_GATE = PASS")
        print(f"  materialised {len(written)} file(s) into {args.materialize}")
        print("  cache stays read-only; discard this workspace after hashing its artifacts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
