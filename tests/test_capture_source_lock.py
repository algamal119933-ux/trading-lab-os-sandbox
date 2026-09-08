"""The source-lock capture script.

The lock is the identity of a research candidate, so the properties worth testing
are the ones that would silently corrupt that identity: hashing a symlink instead
of a file, treating a branch name as identity, or emitting different bytes on two
runs over the same input.

These tests use a purpose-built git repository in tmp_path. They never touch the
mirror clones, the research repo or the live runtime.
"""

from __future__ import annotations

import hashlib
import json
import subprocess

import pytest

import capture_source_lock as lock


def _git(repo, *args):
    subprocess.check_call(["git", "-C", str(repo), *args], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


@pytest.fixture
def repo(tmp_path):
    path = tmp_path / "demo"
    path.mkdir()
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "t@example.invalid")
    _git(path, "config", "user.name", "t")
    (path / "Strategy.py").write_text("class S:\n    timeframe = '1h'\n", encoding="utf-8")
    (path / "LICENSE").write_text("MIT License\n\nCopyright (c) 2020 Someone\n", encoding="utf-8")
    _git(path, "add", "-A")
    _git(path, "commit", "-qm", "initial")
    return path


def test_blob_sha256_matches_the_file_bytes(repo):
    sha = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    digest, size, mode = lock.blob_sha256(repo, sha, "Strategy.py")
    expected = hashlib.sha256((repo / "Strategy.py").read_bytes()).hexdigest()
    assert digest == expected
    assert size == len((repo / "Strategy.py").read_bytes())
    assert mode == "100644"


def test_a_symlink_is_reported_as_a_symlink(repo):
    """The A7 trap: a strategy path that is really a 31-byte link.

    Hashing it silently yields a valid-looking digest of the wrong thing, so the
    git mode must survive into the lock.
    """
    (repo / "linked.py").symlink_to("Strategy.py")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "add symlink")
    sha = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()

    digest, size, mode = lock.blob_sha256(repo, sha, "linked.py")
    assert mode == "120000", "a symlink must not be indistinguishable from a regular file"
    real_digest, real_size, real_mode = lock.blob_sha256(repo, sha, "Strategy.py")
    assert real_mode == "100644"
    assert digest != real_digest
    assert size < real_size


def test_a_missing_path_returns_none_rather_than_guessing(repo):
    sha = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    assert lock.blob_sha256(repo, sha, "does/not/exist.py") == (None, None, None)


def test_mit_is_detected_from_the_licence_text(repo):
    sha = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    found = lock.licenses_for(repo, sha)
    assert [item["spdx"] for item in found] == ["MIT"]
    assert found[0]["file"] == "LICENSE"


def test_gpl3_is_detected_from_the_licence_text(repo):
    (repo / "LICENSE").write_text(
        "                    GNU GENERAL PUBLIC LICENSE\n                       Version 3, 29 June 2007\n",
        encoding="utf-8",
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "gpl")
    sha = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    assert lock.licenses_for(repo, sha)[0]["spdx"] == "GPL-3.0-only"


def test_an_unrecognised_licence_is_unknown_not_guessed(repo):
    (repo / "LICENSE").write_text("All rights reserved. Ask me first.\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "custom")
    sha = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    assert lock.licenses_for(repo, sha)[0]["spdx"] == "UNKNOWN"


def test_default_branch_is_resolved_not_assumed(repo):
    """With no origin/HEAD there is no default branch, and the script must say so
    rather than quietly writing 'main'."""
    assert lock.default_branch(repo) == "UNRESOLVED"


def test_output_is_deterministic_across_runs(tmp_path, monkeypatch):
    """Two runs over identical input must produce byte-identical JSON.

    A lock that varies between runs cannot pin an experiment identity. Rather
    than stubbing git, this builds a repository that actually has an
    origin/HEAD, so the real resolution path is the one under test.
    """
    origin = tmp_path / "origin"
    origin.mkdir()
    _git(origin, "init", "-q", "--bare", "--initial-branch=main")

    work = tmp_path / "work"
    work.mkdir()
    _git(work, "init", "-q", "--initial-branch=main")
    _git(work, "config", "user.email", "t@example.invalid")
    _git(work, "config", "user.name", "t")
    (work / "Strategy.py").write_text("class S:\n    timeframe = '1h'\n", encoding="utf-8")
    (work / "LICENSE").write_text("MIT License\n\nCopyright (c) 2020 Someone\n", encoding="utf-8")
    _git(work, "add", "-A")
    _git(work, "commit", "-qm", "initial")
    _git(work, "remote", "add", "origin", str(origin))
    _git(work, "push", "-q", "origin", "main")

    root = tmp_path / "root"
    root.mkdir()
    _git(root, "clone", "-q", str(origin), "demo")
    clone = root / "demo"
    _git(clone, "remote", "set-head", "origin", "--auto")

    monkeypatch.setattr(lock, "REPO_URLS", {"demo": "https://example.invalid/demo"})
    monkeypatch.setattr(lock, "CANDIDATES", {"Z1": ("demo", "Strategy.py", "S")})
    monkeypatch.setattr(lock, "PARAMS", {})
    monkeypatch.setattr(lock, "CONFIGS", {})

    first = lock.build(root)
    second = lock.build(root)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)

    candidate = first["candidates"][0]
    assert candidate["default_branch"] == "main"
    assert candidate["source_file_git_mode"] == "100644"
    assert candidate["source_config_file"] is None
    assert candidate["source_parameters_sha256"] is None


def test_the_script_has_no_execution_or_credential_path():
    """Structural: a research tool must not be able to trade or read secrets."""
    source = (lock.__file__ and open(lock.__file__, encoding="utf-8").read()) or ""
    for forbidden in ("forcebuy", "forceenter", "forcesell", "forceexit", "create_order",
                      "api_key", "apiKey", "secret", "dotenv", ".env"):
        assert forbidden not in source, f"{forbidden} must not appear in a research script"
