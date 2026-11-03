"""P3-PLN-03 Docker volume export: every volume archive is private to the backup user (0600, its uid:gid).

Regression for the 2026-11-03 host finding: set 20261103T183447Z verified PASS, but its three volume archives were
root:root 0644. The cause was the root helper container writing them through a bind mount. The fix streams the
archive out of the container (stdout) into a file this process creates with O_EXCL and mode 0600. The container
keeps its read-only volume mount and ``--network none`` and gets no write mount. It still runs as root, so
root-owned 0600 files in a volume are archived, not skipped (no ``docker run --user``).

Most tests emulate ``docker run`` with the host's GNU tar on a synthetic "volume", so the real file handling,
stdout wiring and post-checks run without Docker. The last test uses real Docker only when the daemon is up
and the helper image is present (pulled on GitHub Actions only).
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
import tarfile
import uuid
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "research"))

from p3 import backup  # noqa: E402

_REAL_RUN = subprocess.run


class FakeDocker:
    """Stand-in for ``subprocess.run`` that runs ``docker run … -v <vol>:/v:ro <image> tar -C /v -cf - .``
    as a local tar of ``volumes[<vol>]``, writing to whatever stdout the caller passed. Other commands run for real."""

    def __init__(self, volumes: dict[str, Path], *, returncode: int | None = None, stderr: bytes = b""):
        self.volumes, self.returncode, self.stderr, self.calls = volumes, returncode, stderr, []

    def __call__(self, cmd, *args, **kwargs):
        if not cmd or cmd[0] != "docker":
            return _REAL_RUN(cmd, *args, **kwargs)
        self.calls.append(list(cmd))
        if self.returncode is not None:
            return subprocess.CompletedProcess(cmd, self.returncode, b"", self.stderr)
        mounts = [cmd[i + 1] for i, a in enumerate(cmd) if a == "-v"]
        src = self.volumes[mounts[0].split(":")[0]]
        tar_args = cmd[cmd.index(backup.VOLUME_HELPER_IMAGE) + 1:]
        assert tar_args == ["tar", "-C", "/v", "-cf", "-", "."]
        return _REAL_RUN(["tar", "-C", str(src), "-cf", "-", "."], stdout=kwargs["stdout"],
                         stderr=kwargs.get("stderr"), timeout=kwargs.get("timeout"))


@pytest.fixture
def volume(tmp_path) -> Path:
    vol = tmp_path / "vol-src"
    (vol / "data").mkdir(parents=True)
    (vol / "data" / "grafana.db").write_bytes(b"SQLite format 3\0secret")
    (vol / "data" / "grafana.db").chmod(0o600)
    (vol / "public.txt").write_text("x\n")
    return vol


@pytest.fixture
def loose_umask():
    """The pre-fix archives were 0644 under a permissive umask; the fix must not depend on the caller's umask."""
    old = os.umask(0o022)
    yield
    os.umask(old)


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "root"
    root.mkdir()
    (root / "f.txt").write_text("1\n")
    return root


def test_every_volume_archive_is_0600_and_owned_by_the_backup_user(tmp_path, volume, loose_umask, monkeypatch):
    names = ("tlos_runtime_grafana_data", "tlos_runtime_mlflow_data", "tlos_runtime_prometheus_data")
    fake = FakeDocker({n: volume for n in names})
    monkeypatch.setattr(backup.subprocess, "run", fake)
    record = backup.create_backup(tmp_path / "b", roots={"r": _root(tmp_path)}, repos={}, volumes=names, stamp="s1")
    set_dir = tmp_path / "b" / "s1"
    assert record["volumes"] == list(names) and len(fake.calls) == 3
    for name in names:
        st = os.lstat(set_dir / "volumes" / f"{name}.tar")
        assert stat.S_ISREG(st.st_mode)
        assert stat.S_IMODE(st.st_mode) == 0o600
        assert (st.st_uid, st.st_gid) == (os.getuid(), os.getgid())
    assert backup.verify_backup(set_dir)["status"] == "PASS"


def test_the_archive_is_complete_and_byte_identical(tmp_path, volume, monkeypatch):
    monkeypatch.setattr(backup.subprocess, "run", FakeDocker({"v": volume}))
    out = tmp_path / "v.tar"
    backup._docker_volume_export("v", out)
    with tarfile.open(out) as tar:
        members = {m.name for m in tar.getmembers() if m.isfile()}
        assert members == {"./data/grafana.db", "./public.txt"}
        assert tar.extractfile("./data/grafana.db").read() == b"SQLite format 3\0secret"


def test_the_helper_reads_as_root_through_a_read_only_mount_with_no_network_and_no_write_mount(
        tmp_path, volume, monkeypatch):
    fake = FakeDocker({"v": volume})
    monkeypatch.setattr(backup.subprocess, "run", fake)
    backup._docker_volume_export("v", tmp_path / "v.tar")
    (cmd,) = fake.calls
    assert cmd[:3] == ["docker", "run", "--rm"]
    assert cmd[cmd.index("--network") + 1] == "none"
    mounts = [cmd[i + 1] for i, a in enumerate(cmd) if a in ("-v", "--volume", "--mount")]
    assert mounts == ["v:/v:ro"], "exactly one mount, the volume, read-only: the container can write nothing on the host"
    # --user would make root-owned 0600 volume files unreadable and the archive silently incomplete
    assert not {"--user", "-u", "--privileged", "--network=host"} & set(cmd)
    assert cmd[cmd.index(backup.VOLUME_HELPER_IMAGE):] == [backup.VOLUME_HELPER_IMAGE, "tar", "-C", "/v", "-cf", "-", "."], \
        "the archive leaves the container on stdout only"


def test_a_failed_export_fails_closed_and_publishes_no_set(tmp_path, monkeypatch):
    monkeypatch.setattr(backup.subprocess, "run", FakeDocker({}, returncode=125, stderr=b"no such volume"))
    with pytest.raises(backup.BackupError, match=r"volume export of gone failed \(125\): no such volume"):
        backup.create_backup(tmp_path / "b", roots={"r": _root(tmp_path)}, repos={}, volumes=("gone",), stamp="s1")
    assert not (tmp_path / "b" / "s1").exists(), "a failed set is never published under its stamp"


def test_an_empty_stream_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(backup.subprocess, "run", FakeDocker({}, returncode=0))
    with pytest.raises(backup.BackupError, match="empty archive"):
        backup._docker_volume_export("v", tmp_path / "v.tar")


def test_an_existing_archive_is_never_overwritten_or_followed(tmp_path, volume, monkeypatch):
    monkeypatch.setattr(backup.subprocess, "run", FakeDocker({"v": volume}))
    existing = tmp_path / "v.tar"
    existing.write_bytes(b"old")
    with pytest.raises(FileExistsError):
        backup._docker_volume_export("v", existing)
    assert existing.read_bytes() == b"old"
    victim = tmp_path / "victim"
    victim.write_bytes(b"keep")
    (tmp_path / "link.tar").symlink_to(victim)
    with pytest.raises(OSError):
        backup._docker_volume_export("v", tmp_path / "link.tar")
    assert victim.read_bytes() == b"keep"


@pytest.mark.parametrize("mode", [0o644, 0o640, 0o604, 0o664, 0o700, 0o400])
def test_any_mode_other_than_0600_is_refused(tmp_path, mode):
    f = tmp_path / "x.tar"
    f.write_bytes(b"t")
    f.chmod(mode)
    with pytest.raises(backup.BackupError, match=f"mode {mode:04o}, expected 0600"):
        backup._require_private_archive(f)


def test_a_foreign_owner_is_refused(tmp_path, monkeypatch):
    # The pre-fix archives were root:root. Seen from the backup user, any other owner is foreign.
    f = tmp_path / "x.tar"
    f.write_bytes(b"t")
    f.chmod(0o600)
    backup._require_private_archive(f)  # own file, 0600: accepted
    real_uid, real_gid = os.getuid(), os.getgid()
    monkeypatch.setattr(backup.os, "getuid", lambda: real_uid + 1)
    with pytest.raises(backup.BackupError, match=rf"owner {real_uid}:{real_gid}, expected {real_uid + 1}:{real_gid}"):
        backup._require_private_archive(f)
    monkeypatch.setattr(backup.os, "getuid", lambda: real_uid)
    monkeypatch.setattr(backup.os, "getgid", lambda: real_gid + 1)
    with pytest.raises(backup.BackupError, match="owner"):
        backup._require_private_archive(f)


def test_a_non_regular_archive_is_refused(tmp_path):
    d = tmp_path / "x.tar"
    d.mkdir(mode=0o600)
    with pytest.raises(backup.BackupError, match="not a regular file"):
        backup._require_private_archive(d)


def _docker_ready() -> bool:
    """The helper image is pulled on GitHub Actions only; elsewhere it must already be local. Never a pull here."""
    if shutil.which("docker") is None or _REAL_RUN(["docker", "info"], capture_output=True, timeout=30).returncode:
        return False
    probe = _REAL_RUN(["docker", "image", "inspect", backup.VOLUME_HELPER_IMAGE], capture_output=True, timeout=30)
    if probe.returncode == 0:
        return True
    if os.environ.get("GITHUB_ACTIONS") == "true":
        return _REAL_RUN(["docker", "pull", "-q", backup.VOLUME_HELPER_IMAGE], capture_output=True,
                         timeout=600).returncode == 0
    return False


@pytest.mark.skipif(not _docker_ready(), reason="needs Docker with the helper image (pulled on GitHub Actions only)")
def test_real_docker_root_only_volume_files_are_archived_into_a_private_file(tmp_path, loose_umask):
    vol = f"tlos-test-{uuid.uuid4().hex[:12]}"
    _REAL_RUN(["docker", "volume", "create", vol], check=True, capture_output=True)
    try:
        _REAL_RUN(["docker", "run", "--rm", "--network", "none", "-v", f"{vol}:/v", backup.VOLUME_HELPER_IMAGE,
                   "sh", "-c", "umask 077 && mkdir /v/d && printf secret > /v/d/grafana.db"],
                  check=True, capture_output=True, timeout=120)
        out = tmp_path / f"{vol}.tar"
        backup._docker_volume_export(vol, out)
        st = os.lstat(out)
        assert stat.S_IMODE(st.st_mode) == 0o600 and (st.st_uid, st.st_gid) == (os.getuid(), os.getgid())
        with tarfile.open(out) as tar:
            member = tar.getmember("./d/grafana.db")
            assert (member.uid, stat.S_IMODE(member.mode)) == (0, 0o600), "a root-only file inside the volume"
            assert tar.extractfile(member).read() == b"secret"
    finally:
        _REAL_RUN(["docker", "volume", "rm", "-f", vol], capture_output=True)


def test_the_exporter_source_gives_the_container_no_host_write_mount():
    src = (REPO / "research" / "p3" / "backup.py").read_text(encoding="utf-8")
    assert "/out" not in src, "the helper container must not get a host write mount again"
