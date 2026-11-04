"""P3-PLN-02 inventory of live runtime service data (Grafana, Prometheus, MLflow) under /srv/project-data.

The data is owned by the containers and changes while the runtime runs, so a per-file hash against a manifest can
never be current. Its recovery source is the newest backup set that covers *this* root, every link required:
- the set verifies;
- its record lists the root as a data source, with LIVE_DATA_COVERAGE = PASS;
- a persisted drill of *that* set restored data:<name>.
Each missing link is produced here and withholds PASS.

The root is still walked for coverage, by names and lstat only. An unreadable directory is a coverage FAIL,
as for every other root. Synthetic only: no host path, no Docker (the backup's exporter and lister are injected).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "research"))
sys.path.insert(0, str(REPO / "scripts" / "p3"))

from p3 import backup, state_inventory as inv  # noqa: E402

CLASSES = REPO / "research" / "p3" / "records" / "state_classes.json"


def tar_exporter(source: str, out: Path) -> None:
    subprocess.run(["tar", "-C", source, "-cf", str(out), "."], check=True)


@pytest.fixture
def grafana(tmp_path) -> Path:
    root = tmp_path / "srv" / "runtime" / "data" / "grafana"
    (root / "plugins").mkdir(parents=True)
    (root / "grafana.db").write_bytes(b"SQLite format 3\0x")
    (root / "csv").mkdir()
    return root


def make_set(tmp_path: Path, root: Path, *, covered=True, stamp="20261104T050000Z") -> Path:
    mounts = [{"container": "tlos_runtime-grafana-1", "type": "bind", "source": str(root),
               "destination": "/var/lib/grafana", "rw": True}]
    backup.create_backup(tmp_path / "sets", roots={}, repos={}, data={"grafana": str(root)}, stamp=stamp,
                         volume_exporter=tar_exporter, data_lister=lambda s: backup.source_manifest(Path(s), excludes=()),
                         compose_project="tlos_runtime" if covered else None,
                         inspector=(lambda project: mounts) if covered else None)
    return tmp_path / "sets" / stamp


def run(root: Path, set_dir: Path | None, drill: dict | None) -> dict:
    backup_set = None if set_dir is None else {
        "set_dir": str(set_dir), "record": json.loads((set_dir / backup.RECORD).read_text()),
        "verify": backup.verify_backup(set_dir), "drill": drill}
    return inv.inventory(root, inv.load_classes(CLASSES, "runtime_data"), publication={}, lock={},
                         cold_manifest=None, archive_verifier=lambda p: None, backup_set=backup_set)


def recovery(report: dict) -> dict:
    (cls,) = report["classes"]
    assert cls["recovery_kind"] == "BACKUP_SET_DATA"
    return cls["recovery"]


def test_a_root_covered_by_a_verified_drilled_set_passes(tmp_path, grafana):
    set_dir = make_set(tmp_path, grafana)
    drill = backup.restore_drill(set_dir, tmp_path / "scratch")
    report = run(grafana, set_dir, drill)
    assert report["PLN_02_STATE_INVENTORY"] == "PASS" and report["COVERAGE"] == "PASS"
    assert "data:grafana" in recovery(report)["detail"] and "coverage PASS" in recovery(report)["detail"]


def test_live_data_changing_after_the_set_does_not_break_the_recovery_source(tmp_path, grafana):
    set_dir = make_set(tmp_path, grafana)
    drill = backup.restore_drill(set_dir, tmp_path / "scratch")
    (grafana / "grafana.db").write_bytes(b"SQLite format 3\0changed by the running service")
    (grafana / "new-dashboard.json").write_text("{}")
    report = run(grafana, set_dir, drill)
    assert recovery(report)["status"] == "PASS" and "1 files at backup time" in recovery(report)["detail"] \
        and "2 files seen now" in recovery(report)["detail"]


def test_no_backup_set_is_unverified(grafana):
    assert recovery(run(grafana, None, None))["status"] == "UNVERIFIED"


def test_a_set_that_does_not_back_up_this_root_is_missing(tmp_path, grafana):
    other = tmp_path / "other"
    other.mkdir()
    (other / "x").write_text("x")
    set_dir = make_set(tmp_path, other)
    drill = backup.restore_drill(set_dir, tmp_path / "scratch")
    assert recovery(run(grafana, set_dir, drill))["status"] == "MISSING"


def test_a_set_without_live_data_coverage_is_unverified(tmp_path, grafana):
    set_dir = make_set(tmp_path, grafana, covered=False)
    drill = backup.restore_drill(set_dir, tmp_path / "scratch")
    rec = recovery(run(grafana, set_dir, drill))
    assert rec["status"] == "UNVERIFIED" and "live-data coverage is not recorded" in rec["detail"]


@pytest.mark.parametrize("break_drill", [
    lambda d: None,
    lambda d: {**d, "backup_set": "20261101T000000Z"},
    lambda d: {**d, "PLN_03_RESTORE_DRILL": "FAIL"},
    lambda d: {**d, "checks": {k: v for k, v in d["checks"].items() if k != "data:grafana"}},
])
def test_without_a_passing_drill_of_that_set_restoring_this_data_it_is_unverified(tmp_path, grafana, break_drill):
    set_dir = make_set(tmp_path, grafana)
    drill = backup.restore_drill(set_dir, tmp_path / "scratch")
    rec = recovery(run(grafana, set_dir, break_drill(drill)))
    assert rec["status"] == "UNVERIFIED" and "no passing drill" in rec["detail"]


def test_a_set_that_does_not_verify_fails(tmp_path, grafana):
    set_dir = make_set(tmp_path, grafana)
    drill = backup.restore_drill(set_dir, tmp_path / "scratch")
    (set_dir / "data" / "grafana.tar").write_bytes(b"tampered")
    assert recovery(run(grafana, set_dir, drill))["status"] == "FAIL"


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads every directory")
def test_an_unreadable_directory_still_fails_coverage(tmp_path, grafana):
    set_dir = make_set(tmp_path, grafana)
    drill = backup.restore_drill(set_dir, tmp_path / "scratch")
    (grafana / "plugins").chmod(0)
    try:
        report = run(grafana, set_dir, drill)
    finally:
        (grafana / "plugins").chmod(0o755)
    assert report["COVERAGE"] == "FAIL" and report["PLN_02_STATE_INVENTORY"] == "NOT_PASS"


def test_cli_runtime_data_profile(tmp_path, grafana, capsys):
    import state_inventory as cli
    set_dir = make_set(tmp_path, grafana)
    drill_json = tmp_path / "drill.json"
    drill_json.write_text(json.dumps(backup.restore_drill(set_dir, tmp_path / "scratch")))
    args = ["--root", str(grafana), "--profile", "runtime_data", "--backup-set", str(set_dir)]
    assert cli.main(args + ["--drill-json", str(drill_json)]) == 0
    assert cli.main(args) == 1  # no drill: UNVERIFIED
    capsys.readouterr()
