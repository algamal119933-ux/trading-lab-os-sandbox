"""P3-PLN-05 offsite push and the P3 scheduled units; synthetic only, nothing is installed.

The offsite push must refuse an unverified source, verify on the destination, never overwrite, and
report a tampered destination as FAIL. The units must point at the clean tools checkout and at scripts
that exist; the timers must be persistent; and the health service must not count WARNING (1) or
CRITICAL (2) as a unit failure, because a failed unit would hide the alert it just raised.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "research"))

from p3 import backup, offsite  # noqa: E402

UNITS = REPO / "scripts" / "p3" / "units"


@pytest.fixture
def backup_set(tmp_path) -> Path:
    root = tmp_path / "root"
    root.mkdir()
    (root / "a.txt").write_text("evidence\n")
    backup.create_backup(tmp_path / "sets", roots={"r": root}, repos={}, stamp="s1")
    return tmp_path / "sets" / "s1"


def test_a_set_is_pushed_and_verified_on_the_destination(tmp_path, backup_set):
    report = offsite.push(backup_set, str(tmp_path / "offsite"))
    assert report["action"] == "PUSHED" and report["destination_verify"] == "PASS"
    assert report["host_loss_redundancy"] == "NOT_PROVEN"  # a local path is never host-loss redundancy
    again = offsite.push(backup_set, str(tmp_path / "offsite"))
    assert again["action"] == "VERIFIED_EXISTING" and again["destination_verify"] == "PASS"


def test_a_tampered_destination_copy_fails_and_is_not_overwritten(tmp_path, backup_set):
    offsite.push(backup_set, str(tmp_path / "offsite"))
    victim = next((tmp_path / "offsite" / "s1" / "roots").glob("*.tar.zst"))
    victim.write_bytes(victim.read_bytes() + b"x")
    report = offsite.push(backup_set, str(tmp_path / "offsite"))
    assert report["destination_verify"] == "FAIL" and report["action"] == "VERIFIED_EXISTING"
    assert victim.read_bytes().endswith(b"x"), "the divergent copy is reported, never silently replaced"


def test_an_unverified_source_is_never_pushed(tmp_path, backup_set):
    (backup_set / backup.SUMS).write_text("")
    with pytest.raises(offsite.OffsiteError, match="does not verify"):
        offsite.push(backup_set, str(tmp_path / "offsite"))
    assert not (tmp_path / "offsite").exists()


def test_a_remote_target_is_verified_on_the_remote_host(tmp_path, backup_set):
    calls = []

    def runner(cmd):
        calls.append(cmd)
        rc = 1 if cmd[:2] == ["ssh", "u@h"] and cmd[2:4] == ["test", "-d"] else 0
        return subprocess.CompletedProcess(cmd, rc, "", "")
    report = offsite.push(backup_set, "u@h:/srv/off", runner=runner)
    assert report["remote"] is True and report["host_loss_redundancy"] == "CANDIDATE"
    assert ["rsync", "-a", "--ignore-existing", f"{backup_set}/", "u@h:/srv/off/s1/"] in calls
    assert calls[-1] == ["ssh", "u@h", "cd /srv/off/s1 && sha256sum -c --quiet SHA256SUMS"]


@pytest.mark.parametrize("dest,remote", [("u@h:/x", True), ("/mnt/x", False), ("relative/dir", False)])
def test_remote_detection(dest, remote):
    assert offsite.is_remote(dest) is remote


@pytest.mark.parametrize("unit", ["tlos-p3-backup", "tlos-p3-health"])
def test_the_units_run_from_the_clean_tools_checkout_and_exist(unit):
    service = (UNITS / f"{unit}.service").read_text()
    timer = (UNITS / f"{unit}.timer").read_text()
    exec_line = next(l for l in service.splitlines() if l.startswith("ExecStart="))
    assert exec_line.startswith("ExecStart=%h/projects/trading/tlos-p3/scripts/p3/")
    assert (REPO / exec_line.split("tlos-p3/", 1)[1]).is_file()
    assert "Persistent=true" in timer and f"Unit={unit}.service" in timer


def test_the_health_service_does_not_hide_its_alert_as_a_unit_failure():
    assert "SuccessExitStatus=1 2" in (UNITS / "tlos-p3-health.service").read_text()


@pytest.mark.parametrize("script", ["scheduled_backup.sh", "scheduled_health.sh"])
def test_the_wrappers_parse(script):
    assert subprocess.run(["bash", "-n", str(REPO / "scripts" / "p3" / script)]).returncode == 0
