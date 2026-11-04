"""P3-PLN-02: governed copies of the host's tlos-p3-backup.service drop-ins (recovery source).

These two drop-ins live only in ~/.config/systemd/user on the host, which is in no backup root. The governed
copies were taken byte for byte on 2026-11-04 (docs/p3/PLN_02_STATE_INVENTORY.md, "Remaining items closed").
The pinned hashes make any edit here a visible change that must update that record.

PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DROPINS = REPO / "scripts" / "p3" / "ops" / "systemd" / "tlos-p3-backup.service.d"
LIVE_2026_11_04 = {
    "10-hdd-destination.conf": "4cd00835d4c2913584b3eefe6b9d58980e19c47a9d2fc1a44f45b5fca1e453b2",
    "20-umask-0077.conf": "d2bb7c9f85695671b5056a03cbf3ed19a2b8ccd98cceb8dfd91383441024d1a7",
}


def test_governed_copies_equal_the_recorded_host_bytes():
    assert sorted(p.name for p in DROPINS.iterdir()) == sorted(LIVE_2026_11_04)
    for name, digest in LIVE_2026_11_04.items():
        assert hashlib.sha256((DROPINS / name).read_bytes()).hexdigest() == digest, name


def test_the_destination_drop_in_runs_the_installed_governed_wrapper():
    text = (DROPINS / "10-hdd-destination.conf").read_text(encoding="utf-8")
    assert re.findall(r"^ExecStart=(.*)$", text, re.M) == ["", "%h/projects/trading/tlos-runtime/backup.sh"]
    assert re.findall(r"^RequiresMountsFor=(.*)$", text, re.M) == ["", "/srv/project-data"]
    # backup_host_install.sh installs the governed wrapper at exactly that path.
    installer = (REPO / "scripts" / "p3" / "ops" / "backup_host_install.sh").read_text(encoding="utf-8")
    assert '$H/projects/trading/tlos-runtime/backup.sh' in installer


def test_the_umask_drop_in_keeps_sets_owner_only():
    assert (DROPINS / "20-umask-0077.conf").read_text(encoding="utf-8") == "[Service]\nUMask=0077\n"


def test_the_drop_ins_are_not_picked_up_by_the_documented_unit_copy():
    # PLN_03_BACKUP_RESTORE.md installs units with `cp .../scripts/p3/units/tlos-p3-backup.* ...`; a directory there
    # would make that cp fail, so the drop-ins live under scripts/p3/ops/systemd/.
    assert not list((REPO / "scripts" / "p3" / "units").glob("*.d"))
