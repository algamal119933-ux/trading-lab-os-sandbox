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
    PINS_PATH.write_text(json.dumps(pins, indent=2) + "\n")


def iter_files(pins: dict):
    """Yield (source_key, source, file_entry) for every pinned file."""
    for key, source in pins["sources"].items():
        for entry in source.get("files", []):
            yield key, source, entry


def process(pins: dict, cache_dir: Path, refresh: bool) -> tuple[list[str], list[str]]:
    """Fetch every pinned file. Returns (failures, changes)."""
    failures: list[str] = []
    changes: list[str] = []

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
    cache_dir = Path(args.cache_dir) if args.cache_dir else REPO_ROOT / ".upstream-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    print(f"Pinned sources: {len(pins['sources'])}   cache: {cache_dir}")
    failures, changes = process(pins, cache_dir, refresh=args.refresh)

    if changes:
        save_pins(pins)
        print(f"\nRecorded {len(changes)} new hash(es) in {PINS_PATH.relative_to(REPO_ROOT)}")

    if failures:
        print(f"\nUPSTREAM_PIN_GATE = FAIL ({len(failures)} problem(s))", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1

    print("\nUPSTREAM_PIN_GATE = PASS")

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
