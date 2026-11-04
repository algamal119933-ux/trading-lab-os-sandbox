"""The guarded host installation steps H2 and H4 (scripts/p3/ops/backup_host_install.sh).

Real files, a real git checkout and a real flock; only `systemctl` is stubbed (it answers the backup unit's
ActiveState from a file and fails on anything else, so a unit or timer change would fail the test).

Proved here:
- nothing changes while tlos-p3-backup.service is active or activating, or while a run holds the wrapper lock;
- install requires the original wrapper's sha256, keeps a verified rollback copy, and replaces the wrapper through a
  same-directory temporary file and one rename: the wrapper is never partly written, and a refused replacement
  leaves no temporary file behind;
- rollback accepts only the original;
- checkout moves only to a commit on origin/main that fast-forwards the current one, on a clean tree, detached.

Synthetic tests are not host acceptance.
"""

from __future__ import annotations

import hashlib
import os
import stat
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "p3" / "ops" / "backup_host_install.sh"
GOVERNED = REPO / "scripts" / "p3" / "ops" / "tlos_runtime_backup.sh"
ORIG_SHA = "561c44d2c0602a7a0471b60a024bc3d7a25ef5d98457391f1ea6c5c17413b531"

SYSTEMCTL = """#!/usr/bin/env bash
echo "$*" >> "$TLOS_TEST_LOG"
[ "$*" = "--user show -p ActiveState --value tlos-p3-backup.service" ] || exit 9
cat "$TLOS_TEST_STATE"
"""


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(cwd: Path, *args: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t"}
    return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True,
                          env=env).stdout.strip()


@pytest.fixture
def host(tmp_path, monkeypatch):
    """A home with the original wrapper (stand-in whose sha256 the script is told about), a tools checkout cloned
    from an 'origin' with two commits on main, and a stubbed systemctl."""
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "systemctl").write_text(SYSTEMCTL)
    (bin_ / "systemctl").chmod(0o755)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    origin = tmp_path / "origin"
    origin.mkdir()
    git(origin, "init", "-q", "-b", "main")
    (origin / "scripts" / "p3" / "ops").mkdir(parents=True)
    (origin / "scripts" / "p3" / "ops" / "tlos_runtime_backup.sh").write_bytes(GOVERNED.read_bytes())
    git(origin, "add", "-A")
    git(origin, "commit", "-q", "-m", "one")
    first = git(origin, "rev-parse", "HEAD")
    p3 = tmp_path / "home" / "projects" / "trading" / "tlos-p3"
    p3.parent.mkdir(parents=True)
    subprocess.run(["git", "clone", "-q", str(origin), str(p3)], check=True)
    git(p3, "checkout", "-q", "--detach", first)
    (origin / "README").write_text("two\n")
    git(origin, "add", "-A")
    git(origin, "commit", "-q", "-m", "two")
    second = git(origin, "rev-parse", "HEAD")
    wdir = tmp_path / "home" / "projects" / "trading" / "tlos-runtime"
    wdir.mkdir(parents=True)
    wrapper = wdir / "backup.sh"
    original = "#!/usr/bin/env bash\necho original\n"
    wrapper.write_text(original)
    wrapper.chmod(0o700)
    state = tmp_path / "unit_state"
    state.write_text("inactive\n")
    env = {**os.environ, "PATH": f"{bin_}:{os.environ['PATH']}", "TLOS_HOME": str(tmp_path / "home"),
           "XDG_RUNTIME_DIR": str(run_dir), "TLOS_TEST_STATE": str(state),
           "TLOS_TEST_LOG": str(tmp_path / "systemctl.log")}
    # The script pins the real original's sha256; the test feeds it a copy of the script with the stand-in's.
    script = tmp_path / "backup_host_install.sh"
    script.write_text(SCRIPT.read_text().replace(ORIG_SHA, hashlib.sha256(original.encode()).hexdigest()))
    script.chmod(0o755)
    return {"env": env, "script": script, "wrapper": wrapper, "p3": p3, "first": first, "second": second,
            "state": state, "run": run_dir, "log": tmp_path / "systemctl.log",
            "orig_sha": hashlib.sha256(original.encode()).hexdigest()}


def run(h, *args):
    p = subprocess.run([str(h["script"]), *args], env=h["env"], capture_output=True, text=True, timeout=60)
    return p.returncode, p.stdout, p.stderr


def leftovers(h):
    return sorted(p.name for p in h["wrapper"].parent.iterdir() if p.name.startswith(".backup.sh."))


def test_the_script_pins_the_recorded_original_wrapper_hash():
    assert f"ORIG_SHA={ORIG_SHA}" in SCRIPT.read_text()


def test_install_replaces_the_original_atomically_and_keeps_a_verified_rollback_copy(host):
    code, out, err = run(host, "install")
    assert code == 0, err
    assert sha(host["wrapper"]) == sha(GOVERNED)
    assert stat.S_IMODE(host["wrapper"].stat().st_mode) == 0o700
    copies = list(host["wrapper"].parent.glob("backup.sh.pre-p3-*"))
    assert len(copies) == 1 and sha(copies[0]) == host["orig_sha"]
    assert stat.S_IMODE(copies[0].stat().st_mode) == 0o700
    assert leftovers(host) == []
    assert "INSTALLED" in out and "ROLLBACK_COPY" in out
    # Only the read-only state query was issued: no unit or timer was touched.
    assert set(host["log"].read_text().splitlines()) == {"--user show -p ActiveState --value tlos-p3-backup.service"}

    assert run(host, "install")[0] == 0 and "ALREADY_INSTALLED" in run(host, "install")[1]
    code, out, err = run(host, "rollback", str(copies[0]))
    assert code == 0, err
    assert sha(host["wrapper"]) == host["orig_sha"] and leftovers(host) == []


@pytest.mark.parametrize("unit_state", ["active", "activating", "deactivating", "reloading", ""])
@pytest.mark.parametrize("args", [("install",), ("checkout", "SECOND"), ("rollback", "COPY")])
def test_nothing_changes_while_the_backup_unit_is_not_idle(host, unit_state, args):
    host["state"].write_text(unit_state + "\n")
    copy = host["wrapper"].parent / "copy"
    copy.write_bytes(host["wrapper"].read_bytes())
    args = tuple(host["second"] if a == "SECOND" else str(copy) if a == "COPY" else a for a in args)
    code, _, err = run(host, *args)
    assert code == 3 and "tlos-p3-backup.service" in err
    assert sha(host["wrapper"]) == host["orig_sha"] and git(host["p3"], "rev-parse", "HEAD") == host["first"]
    assert not list(host["wrapper"].parent.glob("backup.sh.pre-p3-*")) and leftovers(host) == []


@pytest.mark.parametrize("unit_state", ["inactive", "failed"])
def test_an_idle_or_failed_unit_permits_the_install(host, unit_state):
    host["state"].write_text(unit_state + "\n")
    assert run(host, "install")[0] == 0


def test_nothing_changes_while_a_backup_run_holds_the_wrapper_lock(host):
    lock = host["run"] / "tlos-p3-backup.lock"
    holder = subprocess.Popen(["flock", str(lock), "sleep", "30"])
    try:
        for _ in range(100):
            if subprocess.run(["flock", "-n", str(lock), "true"]).returncode != 0:
                break
        code, _, err = run(host, "install")
    finally:
        holder.kill()
        holder.wait()
    assert code == 75 and "holds" in err
    assert sha(host["wrapper"]) == host["orig_sha"]


def test_install_refuses_a_wrapper_that_is_not_the_original(host):
    host["wrapper"].write_text("#!/usr/bin/env bash\necho edited\n")
    before = sha(host["wrapper"])
    code, _, err = run(host, "install")
    assert code == 3 and "not the original" in err
    assert sha(host["wrapper"]) == before
    assert not list(host["wrapper"].parent.glob("backup.sh.pre-p3-*")) and leftovers(host) == []


def test_a_governed_copy_that_does_not_parse_is_never_renamed_into_place(host):
    src = host["p3"] / "scripts" / "p3" / "ops" / "tlos_runtime_backup.sh"
    src.write_text("#!/usr/bin/env bash\nif then\n")
    code, _, err = run(host, "install")
    assert code == 3 and "does not parse" in err
    assert sha(host["wrapper"]) == host["orig_sha"]
    assert leftovers(host) == []
    # The verified rollback copy was taken before the attempt and stays.
    assert [sha(p) for p in host["wrapper"].parent.glob("backup.sh.pre-p3-*")] == [host["orig_sha"]]


def test_rollback_refuses_anything_but_the_original(host):
    assert run(host, "install")[0] == 0
    bogus = host["wrapper"].parent / "bogus"
    bogus.write_text("#!/usr/bin/env bash\necho bogus\n")
    code, _, err = run(host, "rollback", str(bogus))
    assert code == 3 and "not the original" in err
    assert sha(host["wrapper"]) == sha(GOVERNED)


def test_checkout_fast_forwards_to_a_main_commit_detached(host):
    code, out, err = run(host, "checkout", host["second"])
    assert code == 0, err
    assert git(host["p3"], "rev-parse", "HEAD") == host["second"]
    assert git(host["p3"], "status", "--porcelain", "--branch").startswith("## HEAD (no branch)")
    assert f"ROLLBACK git -C {host['p3']} checkout --detach {host['first']}" in out


def test_checkout_refuses_a_dirty_tree_a_non_main_commit_and_a_bad_sha(host):
    (host["p3"] / "stray").write_text("x\n")
    assert run(host, "checkout", host["second"])[0] == 3
    (host["p3"] / "stray").unlink()
    git(host["p3"], "checkout", "-q", "-b", "side")
    (host["p3"] / "side").write_text("x\n")
    git(host["p3"], "add", "-A")
    git(host["p3"], "commit", "-q", "-m", "side")
    side = git(host["p3"], "rev-parse", "HEAD")
    git(host["p3"], "checkout", "-q", "--detach", host["first"])
    code, _, err = run(host, "checkout", side)
    assert code == 3 and "not on origin/main" in err
    assert run(host, "checkout", "main")[0] == 2
    assert git(host["p3"], "rev-parse", "HEAD") == host["first"]


def test_checkout_refuses_to_move_backwards(host):
    assert run(host, "checkout", host["second"])[0] == 0
    code, _, err = run(host, "checkout", host["first"])
    assert code == 3 and "fast-forward" in err
    assert git(host["p3"], "rev-parse", "HEAD") == host["second"]
