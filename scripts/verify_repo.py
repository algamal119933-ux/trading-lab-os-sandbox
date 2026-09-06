#!/usr/bin/env python3
"""Deterministic repository checks (CLOUD-0 / C0.2 + C0.5).

Verifies, from tracked files only:

* no secret material, credential file, trade database, market-data directory,
  runtime log or MLflow state is tracked;
* every tracked ``.json`` parses and every tracked ``.yml``/``.yaml`` parses;
* ``MANIFEST.txt`` lists exactly the tracked files with their current sha256.

``--fix`` regenerates ``MANIFEST.txt``. Everything else is report-only.

Exit codes: 0 clean, 2 problems found.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPO_ROOT / "MANIFEST.txt"
MANIFEST_NAME = "MANIFEST.txt"

# Paths that must never be tracked, matched against the repo-relative posix path.
FORBIDDEN_PATH_PATTERNS = (
    (r"(^|/)\.env$", "environment file with local credentials"),
    (r"(^|/)\.env\.(?!example$)", "environment file variant"),
    (r"(^|/)config\.json$", "runtime-generated Freqtrade config"),
    (r"\.sqlite(3)?(-journal|-wal|-shm)?$", "trade database"),
    (r"(^|/)freqtrade/user_data/data/", "market-data directory"),
    (r"(^|/)freqtrade/user_data/logs/", "runtime logs"),
    (r"(^|/)freqtrade/user_data/(models|freqaimodels)/", "model artifacts"),
    (r"(^|/)freqtrade/user_data/hyperopt_results/", "hyperopt results"),
    (r"(^|/)mlruns/", "MLflow runtime state"),
    (r"\.(pem|key|p12|pfx|jks|keystore)$", "private key material"),
    (r"\.(feather|parquet)$", "market-data payload"),
    (r"(^|/)backtest_results/", "backtest result archive"),
    (r"\.(zip|tar|tar\.gz|tgz|7z)$", "binary archive"),
)

# A line carrying this marker is a deliberate test fixture or detector pattern,
# not a leaked credential. Keep the marker rare and always adjacent to the value.
ALLOWLIST_MARKER = "allowlist-secret"

SECRET_CONTENT_PATTERNS = (
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "private key block"),
    (r"\bghp_[A-Za-z0-9]{30,}", "GitHub personal access token"),
    (r"\bgithub_pat_[A-Za-z0-9_]{30,}", "GitHub fine-grained token"),
    (r"\bAKIA[0-9A-Z]{16}\b", "AWS access key id"),
    (r"\bxox[baprs]-[A-Za-z0-9-]{10,}", "Slack token"),
    (r"\bsk-[A-Za-z0-9]{32,}", "API secret key"),
    (r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}", "JWT"),
    (r"\"secret\"\s*:\s*\"(?!\s*\")[^\"]{8,}\"", "non-empty secret field"),
    (r"\"key\"\s*:\s*\"(?!\s*\")[A-Za-z0-9]{16,}\"", "non-empty exchange key field"),
)

TEXT_SUFFIXES = {
    ".py", ".sh", ".ps1", ".json", ".yml", ".yaml", ".md", ".txt", ".example", ".cfg", ".toml", ".ini", ""
}


def tracked_files() -> list[str]:
    out = subprocess.check_output(["git", "-C", str(REPO_ROOT), "ls-files", "-z"], text=True)
    return sorted(p for p in out.split("\0") if p)


def staged_bytes(rel: str) -> bytes:
    """Content of a tracked file as it currently stands in the git index.

    The manifest must describe what gets committed, not what happens to be in the
    working tree: hashing the worktree lets an unstaged edit slip a hash into the
    manifest for content that is never committed, which then fails in CI.
    """
    try:
        return subprocess.check_output(
            ["git", "-C", str(REPO_ROOT), "show", f":{rel}"], stderr=subprocess.DEVNULL
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Outside a git index (tests, exported tarball): fall back to the file.
        return (REPO_ROOT / rel).read_bytes()


def sha256_staged(rel: str) -> str:
    return hashlib.sha256(staged_bytes(rel)).hexdigest()


def build_manifest(paths: list[str]) -> str:
    lines = [
        "# Tracked-file manifest for trading-lab-os-sandbox.",
        "# sha256 of each tracked file as staged in git, not as it sits in the",
        "# working tree — regenerate after staging: python3 scripts/verify_repo.py --fix",
        f"# {MANIFEST_NAME} itself is excluded (it cannot contain its own hash).",
    ]
    for rel in paths:
        if rel == MANIFEST_NAME:
            continue
        lines.append(f"{sha256_staged(rel)}  {rel}")
    return "\n".join(lines) + "\n"


def check_forbidden(paths: list[str], problems: list[str]) -> None:
    for rel in paths:
        for pattern, label in FORBIDDEN_PATH_PATTERNS:
            if re.search(pattern, rel):
                problems.append(f"forbidden tracked artifact ({label}): {rel}")


def check_secrets(paths: list[str], problems: list[str]) -> None:
    for rel in paths:
        if Path(rel).suffix not in TEXT_SUFFIXES and not rel.endswith(".json.example"):
            continue
        try:
            text = staged_bytes(rel).decode("utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        lines = text.splitlines()
        for pattern, label in SECRET_CONTENT_PATTERNS:
            for match in re.finditer(pattern, text):
                line_no = text.count("\n", 0, match.start()) + 1
                if ALLOWLIST_MARKER in lines[line_no - 1]:
                    continue
                problems.append(f"possible {label} in {rel}:{line_no}")


def check_parsable(paths: list[str], problems: list[str]) -> None:
    for rel in paths:
        if rel.endswith(".json") or rel.endswith(".json.example"):
            try:
                json.loads(staged_bytes(rel).decode("utf-8"))
            except Exception as exc:  # noqa: BLE001
                problems.append(f"invalid JSON in {rel}: {exc}")
        elif rel.endswith((".yml", ".yaml")):
            try:
                import yaml  # noqa: PLC0415

                list(yaml.safe_load_all(staged_bytes(rel).decode("utf-8")))
            except ImportError:
                problems.append("PyYAML is required to validate YAML files")
                return
            except Exception as exc:  # noqa: BLE001
                problems.append(f"invalid YAML in {rel}: {exc}")


def check_manifest(paths: list[str], problems: list[str], fix: bool) -> None:
    expected = build_manifest(paths)
    if fix:
        MANIFEST.write_text(expected, encoding="utf-8")
        return
    if not MANIFEST.exists():
        problems.append(f"{MANIFEST_NAME} is missing; run: python3 scripts/verify_repo.py --fix")
        return
    current = staged_bytes(MANIFEST_NAME).decode("utf-8")
    if current != expected:
        problems.append(
            f"{MANIFEST_NAME} is stale; stage your changes, then run: "
            "python3 scripts/verify_repo.py --fix && git add MANIFEST.txt"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fix", action="store_true", help="Regenerate MANIFEST.txt.")
    args = parser.parse_args(argv)

    paths = tracked_files()
    problems: list[str] = []
    check_forbidden(paths, problems)
    check_secrets(paths, problems)
    check_parsable(paths, problems)
    check_manifest(paths, problems, args.fix)

    if problems:
        for item in problems:
            print(f"REPO_CHECK_FAIL: {item}", file=sys.stderr)
        return 2
    print(f"REPO_CHECK_PASS ({len(paths)} tracked files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
