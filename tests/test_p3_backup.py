"""P3-PLN-03 backup sets and restore drills, on synthetic roots only (no Docker, no host paths).

The drill must catch what it exists to catch. Each of these is produced and must fail it: a
tampered archive, a backup set overwritten, a restore over a non-empty scratch, a sealed
archive that no longer verifies, and a failed config load.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "research"))

from p3 import backup  # noqa: E402


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True).stdout


@pytest.fixture
def source(tmp_path) -> Path:
    root = tmp_path / "runtime"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    (root / "code.py").write_text("print(1)\n")
    git(root, "add", "code.py")
    git(root, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "c")
    (root / ".env").write_text("SECRET=x\n")
    (root / "artifacts" / "sealedA").mkdir(parents=True)
    (root / "artifacts" / "sealedA" / "archive_manifest.json").write_text("{}\n")
    (root / "artifacts" / "sealedA" / "ledger.jsonl").write_text('{"x":1}\n')
    (root / "freqtrade" / "user_data").mkdir(parents=True)
    (root / "freqtrade" / "user_data" / "config.json").write_text('{"dry_run": true}\n')
    (root / ".venv" / "lib").mkdir(parents=True)
    (root / ".venv" / "lib" / "big.so").write_bytes(b"\0" * 1000)
    (root / "pkg" / "__pycache__").mkdir(parents=True)
    (root / "pkg" / "__pycache__" / "m.pyc").write_bytes(b"\0")
    return root


def make(tmp_path: Path, source: Path, stamp: str = "20261025T000000Z") -> Path:
    target = tmp_path / "backups"
    backup.create_backup(target, roots={"runtime": source}, repos={"runtime": source}, stamp=stamp)
    return target / stamp


def test_a_backup_set_restores_byte_identically(tmp_path, source):
    set_dir = make(tmp_path, source)
    entries = (set_dir / "roots" / "runtime.files.sha256").read_text().splitlines()
    work_tree = [e[66:] for e in entries if not e[66:].startswith(".git/")]
    # .git travels with the root (worktree links, config, refs); derived files never do
    assert sorted(work_tree) == [".env", "artifacts/sealedA/archive_manifest.json", "artifacts/sealedA/ledger.jsonl",
                                 "code.py", "freqtrade/user_data/config.json"]
    assert any(e[66:].startswith(".git/") for e in entries)
    assert backup.verify_backup(set_dir)["status"] == "PASS"
    report = backup.restore_drill(set_dir, tmp_path / "scratch", archive_verifier=lambda p: None,
                                  config_check=lambda root: (True, "ok"))
    assert report["PLN_03_RESTORE_DRILL"] == "PASS", report
    assert set(report["checks"]) == {"backup_integrity", "root:runtime", "sealed:runtime",
                                     "config_load:runtime", "git:runtime"}
    restored = tmp_path / "scratch" / "roots" / "runtime"
    assert (restored / ".env").read_text() == "SECRET=x\n"
    assert not (restored / ".venv").exists() and not (restored / "pkg" / "__pycache__").exists()


def test_a_backup_set_is_never_overwritten(tmp_path, source):
    make(tmp_path, source)
    with pytest.raises(backup.BackupError, match="never overwritten"):
        make(tmp_path, source)


def test_a_tampered_artifact_fails_verify_and_the_drill(tmp_path, source):
    set_dir = make(tmp_path, source)
    bundle = set_dir / "git" / "runtime.bundle"
    bundle.write_bytes(bundle.read_bytes() + b"tamper")
    assert backup.verify_backup(set_dir)["status"] == "FAIL"
    report = backup.restore_drill(set_dir, tmp_path / "scratch")
    assert report["PLN_03_RESTORE_DRILL"] == "FAIL"


def test_a_rewritten_sums_file_is_caught_by_the_record_digest(tmp_path, source):
    set_dir = make(tmp_path, source)
    (set_dir / backup.SUMS).write_text("")
    assert backup.verify_backup(set_dir)["status"] == "FAIL"


def test_the_drill_never_restores_over_a_non_empty_scratch(tmp_path, source):
    set_dir = make(tmp_path, source)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    (scratch / "live.txt").write_text("do not touch")
    with pytest.raises(backup.BackupError, match="not empty"):
        backup.restore_drill(set_dir, scratch)
    assert (scratch / "live.txt").read_text() == "do not touch"


def test_a_sealed_archive_that_no_longer_verifies_fails_the_drill(tmp_path, source):
    set_dir = make(tmp_path, source)

    def refuse(path):
        raise RuntimeError("no longer matches its sealed manifest")
    report = backup.restore_drill(set_dir, tmp_path / "scratch", archive_verifier=refuse)
    assert report["checks"]["sealed:runtime"]["status"] == "FAIL"
    assert report["PLN_03_RESTORE_DRILL"] == "FAIL"


def test_a_failed_config_load_fails_the_drill(tmp_path, source):
    set_dir = make(tmp_path, source)
    report = backup.restore_drill(set_dir, tmp_path / "scratch", config_check=lambda root: (False, "boom"))
    assert report["checks"]["config_load:runtime"]["status"] == "FAIL"


def test_the_git_bundle_carries_the_recorded_head(tmp_path, source):
    set_dir = make(tmp_path, source)
    head = git(source, "rev-parse", "HEAD").strip()
    report = backup.restore_drill(set_dir, tmp_path / "scratch")
    assert report["checks"]["git:runtime"] == {**report["checks"]["git:runtime"], "head": head,
                                               "head_present": True, "status": "PASS"}


def test_volumes_go_through_the_injected_exporter(tmp_path, source):
    seen = []

    def exporter(volume, out):
        seen.append(volume)
        out.write_bytes(b"tar")
    backup.create_backup(tmp_path / "b", roots={"r": source}, repos={}, volumes=("vol_a",),
                         stamp="s1", volume_exporter=exporter)
    assert seen == ["vol_a"] and (tmp_path / "b" / "s1" / "volumes" / "vol_a.tar").read_bytes() == b"tar"
    assert backup.verify_backup(tmp_path / "b" / "s1")["status"] == "PASS"


def test_the_cli_create_verify_and_drill(tmp_path, source):
    cli = [sys.executable, str(REPO / "scripts" / "p3" / "backup.py")]
    target = tmp_path / "t"
    made = subprocess.run(cli + ["create", "--target", str(target), "--root", f"runtime={source}",
                                 "--repo", f"runtime={source}", "--stamp", "s"],
                          capture_output=True, text=True, timeout=120)
    assert made.returncode == 0, made.stdout + made.stderr
    assert subprocess.run(cli + ["verify", "--set", str(target / "s")], capture_output=True).returncode == 0
    drill = subprocess.run(cli + ["drill", "--set", str(target / "s"), "--scratch", str(tmp_path / "x")],
                           capture_output=True, text=True, timeout=120)
    assert drill.returncode in (0, 1), drill.stderr  # a synthetic archive_manifest.json cannot verify
    assert "PLN_03_RESTORE_DRILL" in drill.stdout


def test_sealed_and_config_checks_find_a_runtime_one_level_down(tmp_path, source):
    parent = tmp_path / "projects"
    parent.mkdir()
    source.rename(parent / "checkout")
    backup.create_backup(tmp_path / "b", roots={"trading": parent}, repos={}, stamp="s")
    seen = []
    report = backup.restore_drill(tmp_path / "b" / "s", tmp_path / "scratch",
                                  archive_verifier=lambda p: seen.append(p.name),
                                  config_check=lambda root: (True, root.name))
    assert seen == ["sealedA"]
    assert report["checks"]["sealed:trading/checkout"]["status"] == "PASS"
    assert report["checks"]["config_load:trading/checkout"] == {"status": "PASS", "detail": "checkout"}


def test_a_named_config_target_is_required_and_others_are_not_probed(tmp_path, source):
    set_dir = make(tmp_path, source)
    probed = []
    report = backup.restore_drill(set_dir, tmp_path / "scratch", archive_verifier=lambda p: None,
                                  config_check=lambda root: (probed.append(root.name) or True, "ok"),
                                  config_targets=("runtime",))
    assert report["PLN_03_RESTORE_DRILL"] == "PASS" and probed == ["runtime"]
    missing = backup.restore_drill(set_dir, tmp_path / "scratch2", config_check=lambda root: (True, "ok"),
                                   config_targets=("runtime/absent",))
    assert missing["checks"]["config_load:runtime/absent"]["status"] == "FAIL"


def test_symlinks_are_backed_up_and_verified_by_target(tmp_path, source):
    (source / "lock").symlink_to("host:+1234")  # dangling, like a browser profile lock
    set_dir = make(tmp_path, source)
    entries = {line[66:]: line[:64]
               for line in (set_dir / "roots" / "runtime.files.sha256").read_text().splitlines()}
    assert entries["lock"] == backup.entry_digest(source / "lock")
    report = backup.restore_drill(set_dir, tmp_path / "scratch")
    assert report["checks"]["root:runtime"]["status"] == "PASS"
    assert (tmp_path / "scratch" / "roots" / "runtime" / "lock").is_symlink()

