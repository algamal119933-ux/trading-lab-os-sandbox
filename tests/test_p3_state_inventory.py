"""P3-PLN-02 state inventory: coverage and recovery verification, on synthetic repositories only.

Every refusal is proven by producing it: an unclassified file, an unreadable directory, a dirty
tracked tree, an unreachable HEAD, a stale or missing cold-backup entry, a dataset hash mismatch
and a failing sealed archive each turn the verdict to NOT_PASS. The committed declared classes
must load for every profile.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "research"))

from p3 import state_inventory as inv  # noqa: E402

CLASSES = [
    inv.StateClass(id="source", authority="SOURCE", recovery="GIT_REMOTE", tracked=True),
    inv.StateClass(id="sealed", authority="CANONICAL_EVIDENCE", recovery="SEALED_ARCHIVE", sealed_archives=True),
    inv.StateClass(id="derived", authority="DERIVED", recovery="DISPOSABLE", globs=["*/__pycache__/*", ".venv/*"]),
    inv.StateClass(id="datasets", authority="DATASET", recovery="DATASET_LOCK", globs=["dataset-cache/*"]),
    inv.StateClass(id="secrets", authority="CONFIG_SECRET", recovery="COLD_BACKUP", globs=[".env"]),
    inv.StateClass(id="artifacts", authority="EVIDENCE_NONCANONICAL", recovery="COLD_BACKUP", globs=["artifacts/*"]),
]


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True).stdout


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def repo(tmp_path) -> Path:
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    root = tmp_path / "work"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    (root / "code.py").write_text("print('x')\n")
    git(root, "add", "code.py")
    git(root, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "c")
    git(root, "remote", "add", "origin", str(remote))
    git(root, "push", "-q", "origin", "main")
    git(root, "fetch", "-q", "origin")
    (root / ".env").write_text("SECRET=x\n")
    (root / "artifacts" / "run1").mkdir(parents=True)
    (root / "artifacts" / "run1" / "out.txt").write_text("result\n")
    (root / "artifacts" / "sealedA").mkdir(parents=True)
    (root / "artifacts" / "sealedA" / "archive_manifest.json").write_text("{}\n")
    (root / "pkg" / "__pycache__").mkdir(parents=True)
    (root / "pkg" / "__pycache__" / "m.pyc").write_bytes(b"\0")
    (root / "dataset-cache").mkdir()
    (root / "dataset-cache" / "BTC_USDT-1h.feather").write_bytes(b"candles")
    return root


def run(root: Path, *, manifest="auto", lock=None, verifier=lambda p: None, classes=CLASSES) -> dict:
    if manifest == "auto":
        manifest = {rel: sha(root / rel) for rel in (".env", "artifacts/run1/out.txt")}
    if lock is None:
        lock = {"raw_file_hashes": {"BTC/USDT 1h": sha(root / "dataset-cache" / "BTC_USDT-1h.feather")}}
    return inv.inventory(root, classes, publication={"archives": [{"archive_name": "sealedA"}]},
                         lock=lock, cold_manifest=manifest, archive_verifier=verifier)


def test_a_fully_covered_and_recoverable_root_passes(repo):
    report = run(repo)
    assert report["COVERAGE"] == "PASS" and report["RECOVERY"] == "PASS", report
    assert report["PLN_02_STATE_INVENTORY"] == "PASS"
    counts = {c["id"]: c["files"] for c in report["classes"]}
    assert counts == {"source": 1, "sealed": 1, "derived": 1, "datasets": 1, "secrets": 1, "artifacts": 1}
    assert report["real_money_authorized"] is False


def test_an_unclassified_file_fails_coverage(repo):
    (repo / "stray.bin").write_bytes(b"?")
    report = run(repo)
    assert report["COVERAGE"] == "FAIL" and "stray.bin" in report["unclassified"]["examples"]
    assert report["PLN_02_STATE_INVENTORY"] == "NOT_PASS"


@pytest.mark.skipif(os.geteuid() == 0, reason="root can read a mode-000 directory")
def test_an_unreadable_directory_fails_coverage(repo):
    hidden = repo / "artifacts" / "locked"
    hidden.mkdir()
    hidden.chmod(0)
    try:
        report = run(repo)
    finally:
        hidden.chmod(0o755)
    assert report["COVERAGE"] == "FAIL" and report["unreadable_dirs"]["count"] == 1


def test_a_dirty_tracked_tree_is_stale(repo):
    (repo / "code.py").write_text("print('changed')\n")
    source = next(c for c in run(repo)["classes"] if c["id"] == "source")
    assert source["recovery"]["status"] == "STALE"


def test_a_head_on_no_remote_ref_fails(repo):
    (repo / "new.py").write_text("x\n")
    git(repo, "add", "new.py")
    git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "local only")
    source = next(c for c in run(repo)["classes"] if c["id"] == "source")
    assert source["recovery"]["status"] == "FAIL"


def test_cold_backup_stale_missing_and_absent_manifest(repo):
    stale = {".env": "0" * 64, "artifacts/run1/out.txt": sha(repo / "artifacts/run1/out.txt")}
    secrets = next(c for c in run(repo, manifest=stale)["classes"] if c["id"] == "secrets")
    assert secrets["recovery"]["status"] == "STALE"
    missing = {".env": sha(repo / ".env")}
    artifacts = next(c for c in run(repo, manifest=missing)["classes"] if c["id"] == "artifacts")
    assert artifacts["recovery"]["status"] == "MISSING"
    report = run(repo, manifest=None)
    assert next(c for c in report["classes"] if c["id"] == "secrets")["recovery"]["status"] == "UNVERIFIED"
    assert report["RECOVERY"] == "NOT_PASS"


def test_a_dataset_hash_mismatch_is_unverified(repo):
    report = run(repo, lock={"raw_file_hashes": {"BTC/USDT 1h": "f" * 64}})
    datasets = next(c for c in report["classes"] if c["id"] == "datasets")
    assert datasets["recovery"]["status"] == "UNVERIFIED"
    assert datasets["recovery"]["files"] == {"dataset-cache/BTC_USDT-1h.feather": "RAW_MISMATCH"}


def test_a_failing_sealed_archive_fails_recovery(repo):
    def refuse(path):
        raise RuntimeError(f"{path.name} no longer matches its sealed manifest")
    sealed = next(c for c in run(repo, verifier=refuse)["classes"] if c["id"] == "sealed")
    assert sealed["recovery"]["status"] == "FAIL"
    assert "sealedA" in sealed["recovery"]["detail"][0]


def test_the_inventory_writes_nothing_into_the_root(repo):
    before = sorted(p.relative_to(repo).as_posix() for p in repo.rglob("*") if ".git" not in p.parts)
    run(repo)
    after = sorted(p.relative_to(repo).as_posix() for p in repo.rglob("*") if ".git" not in p.parts)
    assert before == after


def test_manifest_parsing_takes_only_the_prefixed_paths(tmp_path):
    manifest = tmp_path / "m.sha256"
    manifest.write_text(f"{'a' * 64}  projects/x/.env\n{'b' * 64}  other/y\n{'c' * 64}  ./projects/x/z\n")
    assert inv.load_manifest(manifest, "projects/x/") == {".env": "a" * 64, "z": "c" * 64}


@pytest.mark.parametrize("profile", ["runtime", "worktree", "operator"])
def test_the_committed_declared_classes_load(profile):
    classes = inv.load_classes(REPO / "research" / "p3" / "records" / "state_classes.json", profile)
    assert classes and all(c.recovery in inv.RECOVERY_KINDS for c in classes)


def test_an_unknown_recovery_kind_or_profile_is_refused(tmp_path):
    with pytest.raises(ValueError):
        inv.StateClass(id="x", authority="A", recovery="HOPE")
    with pytest.raises(ValueError):
        inv.load_classes(REPO / "research" / "p3" / "records" / "state_classes.json", "nope")


def test_the_cli_reports_and_exits_by_verdict(repo, tmp_path):
    out = tmp_path / "r.json"
    result = subprocess.run([sys.executable, str(REPO / "scripts" / "p3" / "state_inventory.py"),
                             "--root", str(repo), "--profile", "operator", "--json", str(out)],
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 1, result.stdout + result.stderr  # no cold manifest: UNVERIFIED
    report = json.loads(out.read_text())
    assert report["PLN_02_STATE_INVENTORY"] == "NOT_PASS"
    assert "PLN_02_STATE_INVENTORY = NOT_PASS" in result.stdout
