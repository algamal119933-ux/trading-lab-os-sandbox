"""P3-PLN-03 live data coverage: the backup takes the data the running containers actually use.

Regression for the 2026-11-03 host finding: the runtime's Grafana, Prometheus and MLflow containers bind-mount
``/srv/project-data/trading-data/runtime/data/{grafana,prometheus,mlflow}``, while the backup exported named
volumes that no container uses. ``create_backup(data=…, compose_project=…)`` now:

- refuses the set unless every writable mount of the project's containers is backed up and no declared source
  is stale (LIVE_DATA_COVERAGE);
- archives each live source through the read-only root helper (protected Grafana files included) into a 0600
  file, and proves the archive equal to the live source read again, so a writer still running fails the set;
- restores every data source in the drill and compares it file by file.

``docker`` is emulated with the host's GNU tar, find, xargs and sha256sum on synthetic directories, so the real
listing script and parser run. The last test uses real Docker only when the daemon is up and the helper image
is already local. It never pulls.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "research"))
sys.path.insert(0, str(REPO / "scripts" / "p3"))

from p3 import backup  # noqa: E402

_REAL_RUN = subprocess.run
PROJECT = "tlos_runtime"


class FakeDocker:
    """``docker ps``/``inspect`` from a synthetic container list; ``docker run`` of the helper on local dirs."""

    def __init__(self, containers: list[dict], volumes: dict[str, Path] | None = None, *, on_list=None):
        self.containers, self.volumes, self.on_list, self.calls = containers, volumes or {}, on_list, []

    def _source(self, cmd: list[str]) -> Path:
        if "--mount" in cmd:
            spec = dict(kv.split("=", 1) for kv in cmd[cmd.index("--mount") + 1].split(",") if "=" in kv)
            assert spec["type"] == "bind" and spec["dst"] == "/v" and cmd[cmd.index("--mount") + 1].endswith(",readonly")
            src = Path(spec["src"])
            if not src.is_dir():  # --mount refuses a missing bind source
                raise FileNotFoundError(src)
            return src
        return self.volumes[cmd[cmd.index("-v") + 1].split(":")[0]]

    def __call__(self, cmd, *args, **kwargs):
        if not cmd or cmd[0] != "docker":
            return _REAL_RUN(cmd, *args, **kwargs)
        self.calls.append(list(cmd))
        text = kwargs.get("text", False)
        if cmd[1] == "ps":
            label = cmd[cmd.index("--filter") + 1].rsplit("=", 1)[1]
            ids = [c["Id"] for c in self.containers if c["Config"]["Labels"].get("com.docker.compose.project") == label]
            return subprocess.CompletedProcess(cmd, 0, "\n".join(ids) + ("\n" if ids else ""), "")
        if cmd[1] == "inspect":
            found = [c for c in self.containers if c["Id"] in cmd[2:]]
            return subprocess.CompletedProcess(cmd, 0, json.dumps(found), "")
        assert cmd[1] == "run" and "--network" in cmd and cmd[cmd.index("--network") + 1] == "none"
        assert "--user" not in cmd and "-u" not in cmd
        try:
            src = self._source(cmd)
        except FileNotFoundError as exc:
            return subprocess.CompletedProcess(cmd, 125, b"", f"invalid mount config: bind source path does not exist: {exc}".encode())
        tail = cmd[cmd.index(backup.VOLUME_HELPER_IMAGE) + 1:]
        if tail[0] == "tar":
            assert tail == ["tar", "-C", "/v", "-cf", "-", "."]
            return _REAL_RUN(["tar", "-C", str(src), "-cf", "-", "."], stdout=kwargs["stdout"],
                             stderr=kwargs.get("stderr"), timeout=kwargs.get("timeout"))
        assert tail[:2] == ["sh", "-c"] and tail[2] == backup._LIST_SCRIPT
        if self.on_list:
            self.on_list(src)
        out = _REAL_RUN(["sh", "-c", tail[2].replace("cd /v ", f"cd '{src}' ", 1)], capture_output=True)
        assert not text
        return out


def container(name: str, *mounts: tuple[str, str, str, bool], project: str = PROJECT) -> dict:
    """mounts: (type, source, destination, rw)."""
    return {"Id": uuid.uuid4().hex, "Name": f"/{name}", "Config": {"Labels": {"com.docker.compose.project": project}},
            "Mounts": [{"Type": t, ("Source" if t == "bind" else "Name"): s, "Destination": d, "RW": rw}
                       for t, s, d, rw in mounts]}


@pytest.fixture
def live(tmp_path) -> dict:
    """A host shaped like the finding: three bind-mounted data dirs, a stale named volume, configs under a root."""
    data = tmp_path / "srv" / "trading-data" / "runtime" / "data"
    g, p, m = data / "grafana", data / "prometheus", data / "mlflow"
    (g / "plugins").mkdir(parents=True)
    (g / "grafana.db").write_bytes(b"SQLite format 3\0dashboards+datasource secrets")
    (g / "grafana.db").chmod(0o600)  # "protected": the backup user may not be able to read it directly
    (g / "csv").mkdir()
    (p / "wal").mkdir(parents=True)
    (p / "wal" / "00000001").write_bytes(b"\x01" * 4096)
    (p / "queries.active").write_bytes(b"")
    (p / "lock").write_text("")
    (p / "chunks_head").mkdir()
    os.symlink("wal/00000001", p / "latest")
    (m / "mlruns" / "0").mkdir(parents=True)
    (m / "mlruns" / "0" / "meta.yaml").write_text("name: Default\n")
    (m / "mlflow.db").write_bytes(b"SQLite format 3\0runs")
    os.link(m / "mlflow.db", m / "mlflow.db.hardlink")
    (m / ".hidden").write_text("h\n")
    runtime = tmp_path / "projects" / "trading" / "tlos-runtime"
    (runtime / "prometheus").mkdir(parents=True)
    (runtime / "prometheus" / "prometheus.yml").write_text("scrape_configs: []\n")
    (runtime / ".env").write_text("GF_SECURITY_ADMIN_PASSWORD=x\n")
    stale = tmp_path / "stale-volume"
    stale.mkdir()
    (stale / "old.db").write_text("old\n")
    containers = [
        container("tlos-grafana", ("bind", str(g), "/var/lib/grafana", True)),
        container("tlos-prometheus", ("bind", str(p), "/prometheus", True),
                  ("bind", str(runtime / "prometheus" / "prometheus.yml"), "/etc/prometheus/prometheus.yml", False)),
        container("tlos-mlflow", ("bind", str(m), "/mlflow", True)),
        container("tlos-exporter", ("bind", "/var/run/docker.sock", "/var/run/docker.sock", True),
                  ("tmpfs", "", "/tmp", True)),
        container("other-project", ("bind", str(stale), "/x", True), project="unrelated"),
    ]
    return {"grafana": str(g), "prometheus": str(p), "mlflow": str(m), "runtime": runtime,
            "trading": tmp_path / "projects" / "trading", "stale": stale, "containers": containers}


def sources(live: dict) -> dict[str, str]:
    return {k: live[k] for k in ("grafana", "prometheus", "mlflow")}


def make_set(tmp_path: Path, live: dict, monkeypatch, *, data=None, stamp="20261103T200000Z", fake=None) -> Path:
    monkeypatch.setattr(backup.subprocess, "run", fake or FakeDocker(live["containers"]))
    backup.create_backup(tmp_path / "backups", roots={"trading": live["trading"]}, repos={},
                         data=sources(live) if data is None else data, compose_project=PROJECT, stamp=stamp)
    return tmp_path / "backups" / stamp


def test_the_set_holds_the_live_bind_mounted_data_byte_for_byte(tmp_path, live, monkeypatch):
    set_dir = make_set(tmp_path, live, monkeypatch)
    record = json.loads((set_dir / backup.RECORD).read_text())
    assert record["live_data_coverage"]["LIVE_DATA_COVERAGE"] == "PASS"
    for name in ("grafana", "prometheus", "mlflow"):
        expected = backup.source_manifest(Path(live[name]), excludes=())
        manifest = (set_dir / "data" / f"{name}.files.sha256").read_text().splitlines()
        assert {line[66:]: line[:64] for line in manifest} == expected
        assert record["data_sources"][name]["source"] == live[name]
        assert record["data_sources"][name]["files"] == len(expected) > 0
        st = os.lstat(set_dir / "data" / f"{name}.tar")
        assert stat.S_IMODE(st.st_mode) == 0o600 and (st.st_uid, st.st_gid) == (os.getuid(), os.getgid())
    assert "grafana.db" in (set_dir / "data" / "grafana.files.sha256").read_text()
    assert {"wal/00000001", "latest", "lock"} <= set(backup._read_manifest(set_dir / "data" / "prometheus.files.sha256"))
    assert backup.verify_backup(set_dir)["status"] == "PASS"
    sums = backup._read_manifest(set_dir / backup.SUMS)
    assert {"data/grafana.tar", "data/grafana.files.sha256"} <= set(sums), "SHA256SUMS covers the data artifacts"


def test_the_drill_restores_every_live_source_and_proves_it(tmp_path, live, monkeypatch):
    set_dir = make_set(tmp_path, live, monkeypatch)
    report = backup.restore_drill(set_dir, tmp_path / "scratch")
    assert report["PLN_03_RESTORE_DRILL"] == "PASS", report["checks"]
    for name in ("grafana", "prometheus", "mlflow"):
        assert report["checks"][f"data:{name}"]["status"] == "PASS"
    restored = tmp_path / "scratch" / "data" / "grafana" / "grafana.db"
    assert restored.read_bytes() == Path(live["grafana"], "grafana.db").read_bytes()
    assert os.readlink(tmp_path / "scratch" / "data" / "prometheus" / "latest") == "wal/00000001"


def test_a_consistently_rewritten_data_archive_passes_verify_but_fails_the_drill(tmp_path, live, monkeypatch):
    set_dir = make_set(tmp_path, live, monkeypatch)
    wrong = tmp_path / "wrong"
    shutil.copytree(live["grafana"], wrong)
    (wrong / "grafana.db").write_bytes(b"not the dashboards")
    archive = set_dir / "data" / "grafana.tar"
    archive.unlink()
    _REAL_RUN(["tar", "-C", str(wrong), "-cf", str(archive), "."], check=True)
    sums = backup._read_manifest(set_dir / backup.SUMS)
    sums["data/grafana.tar"] = backup.sha256_file(archive)
    backup._write_manifest(dict(sorted(sums.items())), set_dir / backup.SUMS)
    record = json.loads((set_dir / backup.RECORD).read_text())
    record["sha256sums_digest"] = backup.sha256_file(set_dir / backup.SUMS)
    (set_dir / backup.RECORD).write_text(json.dumps(record))
    assert backup.verify_backup(set_dir)["status"] == "PASS"
    report = backup.restore_drill(set_dir, tmp_path / "scratch")
    assert report["checks"]["data:grafana"]["status"] == "FAIL"
    assert report["checks"]["data:grafana"]["differ"] == ["grafana.db"]
    assert report["PLN_03_RESTORE_DRILL"] == "FAIL"


def test_the_stale_named_volume_selection_is_refused(tmp_path, live, monkeypatch):
    # Exactly the finding: the backup names a volume no container of the project mounts, and misses the binds.
    with pytest.raises(backup.BackupError) as err:
        make_set(tmp_path, live, monkeypatch, data={"grafana": "tlos_runtime_grafana_data"})
    message = str(err.value)
    assert "LIVE_DATA_COVERAGE = FAIL" in message and "tlos_runtime_grafana_data" in message
    for name in ("grafana", "prometheus", "mlflow"):
        assert live[name] in message, f"the uncovered live {name} bind is named"
    assert not (tmp_path / "backups").exists(), "nothing is written when coverage fails"


def test_a_new_writable_mount_that_is_not_declared_is_refused(tmp_path, live, monkeypatch):
    extra = tmp_path / "srv" / "trading-data" / "runtime" / "data" / "loki"
    extra.mkdir()
    live["containers"].append(container("tlos-loki", ("bind", str(extra), "/loki", True)))
    with pytest.raises(backup.BackupError, match=r"uncovered writable mounts \['tlos-loki:/loki <- bind "):
        make_set(tmp_path, live, monkeypatch)


def test_an_anonymous_volume_with_state_is_uncovered_but_plumbing_is_not(live):
    rows = [
        {"container": "c", "type": "volume", "source": "3f" * 32, "destination": "/data", "rw": True},
        {"container": "c", "type": "bind", "source": "/var/run/docker.sock", "destination": "/s", "rw": True},
        {"container": "c", "type": "bind", "source": "/proc", "destination": "/host/proc", "rw": False},
        {"container": "c", "type": "tmpfs", "source": "", "destination": "/tmp", "rw": True},
        {"container": "c", "type": "bind", "source": str(live["runtime"] / ".env"), "destination": "/e", "rw": False},
        {"container": "c", "type": "bind", "source": "/etc/hosts-elsewhere", "destination": "/h", "rw": False},
    ]
    report = backup.live_data_coverage(rows, data={}, roots={"trading": live["trading"]})
    assert report["LIVE_DATA_COVERAGE"] == "FAIL" and report["uncovered_rw"] == [f"c:/data <- volume {'3f' * 32}"]
    by_dest = {r["destination"]: r["covered_by"] for r in report["mounts"]}
    assert by_dest == {"/data": None, "/s": "not_state", "/host/proc": "not_state", "/tmp": "not_state",
                       "/e": "root", "/h": None}, "a read-only mount is reported, never decisive"


def test_no_container_for_the_project_fails_closed(tmp_path, live, monkeypatch):
    live["containers"] = [c for c in live["containers"] if c["Name"] == "/other-project"]
    with pytest.raises(backup.BackupError, match="no container of compose project 'tlos_runtime' exists"):
        make_set(tmp_path, live, monkeypatch)


def test_a_writer_still_running_during_the_backup_fails_the_set(tmp_path, live, monkeypatch):
    # Between the export and the re-read, Prometheus appends to its WAL: the runtime was not stopped.
    def write(src: Path):
        if src.name == "prometheus":
            with open(src / "wal" / "00000001", "ab") as wal:
                wal.write(b"\x02")
    fake = FakeDocker(live["containers"], on_list=write)
    with pytest.raises(backup.BackupError, match=r"prometheus .* changed or was not fully read .*differ \['wal/00000001'\]"):
        make_set(tmp_path, live, monkeypatch, fake=fake)
    assert not (tmp_path / "backups" / "20261103T200000Z").exists()


def test_a_missing_bind_source_is_refused_not_created(tmp_path, live, monkeypatch):
    gone = str(tmp_path / "srv" / "gone")
    live["containers"].append(container("tlos-gone", ("bind", gone, "/g", True)))
    data = {**sources(live), "gone": gone}
    with pytest.raises(backup.BackupError, match="bind source path does not exist"):
        make_set(tmp_path, live, monkeypatch, data=data)
    assert not Path(gone).exists()


@pytest.mark.parametrize("bad", ["/srv/a/../b", "/srv/a/", "/srv/a,b", "relative/dir", "vol:rw", "-v"])
def test_a_malformed_source_is_refused_before_anything_runs(tmp_path, live, monkeypatch, bad):
    fake = FakeDocker(live["containers"])
    monkeypatch.setattr(backup.subprocess, "run", fake)
    with pytest.raises(backup.BackupError):
        backup.create_backup(tmp_path / "b", roots={}, repos={}, data={"x": bad}, stamp="s")
    assert fake.calls == [] and not (tmp_path / "b").exists()


@pytest.mark.parametrize("bad", ["../x", "a/b", "", ".hidden"])
def test_a_data_name_cannot_escape_the_set(tmp_path, live, bad):
    with pytest.raises(backup.BackupError, match="data source name"):
        backup.create_backup(tmp_path / "b", roots={}, repos={}, data={bad: live["grafana"]}, stamp="s")


def test_the_helper_mounts_a_bind_read_only_with_no_network_and_reads_as_root(tmp_path, live, monkeypatch):
    fake = FakeDocker(live["containers"])
    make_set(tmp_path, live, monkeypatch, fake=fake)
    runs = [c for c in fake.calls if c[1] == "run"]
    assert len(runs) == 6, "one export and one re-read per source"
    for cmd in runs:
        assert cmd[cmd.index("--network") + 1] == "none"
        mounts = [cmd[i + 1] for i, a in enumerate(cmd) if a in ("-v", "--volume", "--mount")]
        assert len(mounts) == 1 and mounts[0].startswith("type=bind,src=") and mounts[0].endswith(",dst=/v,readonly")
        assert not {"--user", "-u", "--privileged"} & set(cmd)


def test_a_set_without_data_sources_still_drills_as_before(tmp_path, live, monkeypatch):
    # Historical sets carry no data_sources key: the drill neither requires nor invents one.
    monkeypatch.setattr(backup.subprocess, "run", FakeDocker(live["containers"]))
    backup.create_backup(tmp_path / "b", roots={"trading": live["trading"]}, repos={}, stamp="old")
    record = json.loads((tmp_path / "b" / "old" / backup.RECORD).read_text())
    del record["data_sources"], record["live_data_coverage"]
    (tmp_path / "b" / "old" / backup.RECORD).write_text(json.dumps(record))
    report = backup.restore_drill(tmp_path / "b" / "old", tmp_path / "scratch")
    assert report["PLN_03_RESTORE_DRILL"] == "PASS" and not [k for k in report["checks"] if k.startswith("data:")]


def test_the_cli_coverage_is_read_only_and_names_the_gap(tmp_path, live, monkeypatch, capsys):
    import backup as cli  # scripts/p3/backup.py
    monkeypatch.setattr(backup.subprocess, "run", FakeDocker(live["containers"]))
    before = sorted(str(p) for p in tmp_path.rglob("*"))
    args = ["coverage", "--compose-project", PROJECT, "--root", f"trading={live['trading']}"]
    assert cli.main(args + [f"--data={k}={v}" for k, v in sources(live).items()]) == 0
    assert "LIVE_DATA_COVERAGE = PASS" in capsys.readouterr().out
    assert cli.main(args + ["--data", "grafana=tlos_runtime_grafana_data"]) == 1
    out = capsys.readouterr().out
    assert "UNCOVERED_RW tlos-prometheus:/prometheus" in out and "STALE_DATA_SOURCE tlos_runtime_grafana_data" in out
    assert sorted(str(p) for p in tmp_path.rglob("*")) == before, "coverage writes nothing"


def test_the_cli_create_takes_live_data_and_refuses_bad_coverage(tmp_path, live, monkeypatch, capsys):
    import backup as cli
    monkeypatch.setattr(backup.subprocess, "run", FakeDocker(live["containers"]))
    base = ["create", "--target", str(tmp_path / "b"), "--root", f"trading={live['trading']}",
            "--compose-project", PROJECT]
    assert cli.main(base + ["--stamp", "s1"] + [f"--data={k}={v}" for k, v in sources(live).items()]) == 0
    assert "VERIFY = PASS" in capsys.readouterr().out
    assert cli.main(base + ["--stamp", "s2", "--data", "grafana=tlos_runtime_grafana_data"]) == 2
    assert "LIVE_DATA_COVERAGE = FAIL" in capsys.readouterr().err and not (tmp_path / "b" / "s2").exists()


def _docker_ready() -> bool:
    if shutil.which("docker") is None:
        return False
    probe = _REAL_RUN(["docker", "image", "inspect", backup.VOLUME_HELPER_IMAGE], capture_output=True, timeout=30)
    return probe.returncode == 0


@pytest.mark.skipif(not _docker_ready(), reason="needs a running Docker daemon with the helper image already local")
def test_real_docker_root_only_grafana_files_in_a_bind_are_backed_up_and_restored(tmp_path, monkeypatch):
    project = f"tlos-test-{uuid.uuid4().hex[:10]}"
    data = tmp_path / "data"
    grafana = data / "grafana"
    grafana.mkdir(parents=True)
    grafana.chmod(0o777)  # as found on the host
    name = f"{project}-grafana"
    try:
        # Root inside a container writes a root-owned 0600 database into the bind, as Grafana's would be.
        _REAL_RUN(["docker", "run", "--rm", "--network", "none", "--mount", f"type=bind,src={grafana},dst=/v",
                   backup.VOLUME_HELPER_IMAGE, "sh", "-c", "umask 077 && mkdir /v/d && printf secret > /v/d/grafana.db"],
                  check=True, capture_output=True, timeout=120)
        _REAL_RUN(["docker", "create", "--name", name, "--label", f"com.docker.compose.project={project}",
                   "--mount", f"type=bind,src={grafana},dst=/var/lib/grafana", backup.VOLUME_HELPER_IMAGE, "true"],
                  check=True, capture_output=True, timeout=60)
        record = backup.create_backup(tmp_path / "b", roots={}, repos={}, data={"grafana": str(grafana)},
                                      compose_project=project, stamp="s")
        set_dir = tmp_path / "b" / "s"
        assert record["live_data_coverage"]["LIVE_DATA_COVERAGE"] == "PASS"
        assert record["data_sources"]["grafana"]["files"] == 1
        st = os.lstat(set_dir / "data" / "grafana.tar")
        assert stat.S_IMODE(st.st_mode) == 0o600 and (st.st_uid, st.st_gid) == (os.getuid(), os.getgid())
        report = backup.restore_drill(set_dir, tmp_path / "scratch")
        assert report["checks"]["data:grafana"]["status"] == "PASS", report["checks"]
        assert (tmp_path / "scratch" / "data" / "grafana" / "d" / "grafana.db").read_bytes() == b"secret"
    finally:
        _REAL_RUN(["docker", "rm", "-f", name], capture_output=True)
        _REAL_RUN(["docker", "run", "--rm", "--network", "none", "--mount", f"type=bind,src={data},dst=/v",
                   backup.VOLUME_HELPER_IMAGE, "sh", "-c", "chmod -R a+rwX /v"], capture_output=True, timeout=60)
