"""Durability law after the Owner amendment: two required tiers, one second device.

Independent-host storage is no longer a P2 T0 precondition. It was an
Owner-added precaution and is superseded — **removed as a blocker, not
satisfied** — and off-host storage, restore qualification and disaster recovery
are P3 operational-hardening scope.

What replaces it is smaller and honest. This workstation already holds a second
physical disk, so when it is available and healthy the sealed evidence is copied
onto it, and every record of that copy says on its face what it is:

    SAME_HOST_SECOND_DEVICE = YES
    HOST_LOSS_REDUNDANCY    = NOT_PROVEN

Two drives in one chassis share a power supply, a room, and a thief. These tests
exist because that sentence is the thing most likely to erode: the copy is real
and useful, which is exactly what makes it tempting to describe as more than it
is. The project has already paid once for that conflation.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

import replicate_to_second_device as replicator
import second_device_discovery as discovery
from fp import archive as fp_archive

CONTRACT = Path("docs/p2/P2_CONTRACT.md")
SECOND_DEVICE_SURFACES = (
    "scripts/second_device_discovery.py",
    "scripts/replicate_to_second_device.py",
)


# -- the blocker is gone, and gone by removal ------------------------------


def test_independent_host_storage_is_not_a_t0_precondition():
    """Removed as a blocker, and said so — not quietly dropped."""
    text = CONTRACT.read_text(encoding="utf-8")
    preconditions = text[text.index("## 9. Conditional T0 authority"):text.index("## 10. Authority")]
    # It is not in the precondition block...
    opening = preconditions.index("```text")
    block = preconditions[opening:preconditions.index("```", opening + 7)]
    assert "Tier-3" not in block and "Tier 3" not in block
    assert "independent-host" not in block.lower()
    assert "Tier 1 + Tier 2 satisfied" in block
    assert "second device used when available/healthy" in block
    # ...and its absence is stated rather than left to be noticed.
    assert "Independent-host storage is **not** among them" in preconditions


def test_an_unavailable_second_device_does_not_block_t0():
    text = CONTRACT.read_text(encoding="utf-8")
    assert "does not block T0 either" in text
    report = discovery.discover()
    assert report["blocks_t0"] is False


def test_an_unavailable_second_device_is_not_an_owner_return():
    text = CONTRACT.read_text(encoding="utf-8")
    authority = text[text.index("## 10. Authority"):text.index("## 11. Defects after T0")]
    assert "Tier-3 unavailable" not in authority
    assert "an unavailable second device is NOT a return" in authority


def test_off_host_storage_is_named_as_p3_scope():
    text = CONTRACT.read_text(encoding="utf-8")
    assert "P3\noperational-hardening scope" in text or "P3 operational-hardening scope" in text
    assert "no cloud or NAS provisioning is required for" in text


def test_the_two_required_tiers_remain_required():
    text = CONTRACT.read_text(encoding="utf-8")
    durability = text[text.index("## 8. Durability"):text.index("## 9. Conditional T0 authority")]
    assert "TIER 1 — WHOLE-LANE ARCHIVAL                                       REQUIRED" in durability
    assert "TIER 2 — DIGEST PUBLICATION                                        REQUIRED" in durability


# -- the second device is labelled truthfully, everywhere -----------------


def test_the_contract_labels_the_second_device_truthfully():
    text = CONTRACT.read_text(encoding="utf-8")
    durability = text[text.index("## 8. Durability"):text.index("## 9. Conditional T0 authority")]
    assert "SAME_HOST_SECOND_DEVICE = YES" in durability
    assert "HOST_LOSS_REDUNDANCY    = NOT_PROVEN" in durability
    assert "IT IS NOT CALLED TIER 3, in any record, at any time." in durability
    for forbidden_claim in ("host loss", "workstation destruction", "theft"):
        assert forbidden_claim in durability


def test_discovery_reports_the_truthful_labels():
    report = discovery.discover()
    assert report["host_loss_redundancy"] == "NOT_PROVEN"
    assert report["SAME_HOST_SECOND_DEVICE"] in ("YES", "NO")
    assert report["provisioned"] is False
    assert report["actions_taken"].startswith("NONE")
    for phrase in ("host loss", "workstation destruction", "theft"):
        assert phrase in report["may_not_claim"]


@pytest.mark.parametrize("path", SECOND_DEVICE_SURFACES)
def test_no_second_device_surface_calls_itself_tier_3(path):
    text = Path(path).read_text(encoding="utf-8")
    lowered = text.lower()
    # It may say what it is NOT — that is the point — but never claim the name.
    for claim in ("is tier 3", "tier-3 snapshot", "tier 3 storage", "tier3_destination"):
        assert claim not in lowered, f"{path} claims {claim!r}"


@pytest.mark.parametrize("path", SECOND_DEVICE_SURFACES)
def test_no_second_device_surface_claims_host_loss_survival(path):
    """Claim-shaped, not vocabulary-shaped.

    These files must be able to SAY "disaster recovery is P3 scope" — that is
    the disclaimer doing its job. What they may not do is assert the property.
    A test that banned the words would pressure someone to delete the very
    sentences that keep the record honest.
    """
    lowered = Path(path).read_text(encoding="utf-8").lower()
    for claim in (
        "survives host loss",
        "host-loss redundancy is provided",
        "provides disaster recovery",
        "is an offsite copy",
        "off-site backup",
        "host_loss_redundancy = yes",
        'host_loss_redundancy": "proven"',
    ):
        assert claim not in lowered, f"{path} claims {claim!r}"
    # And the disclaimer is present and unambiguous.
    assert "not_proven" in lowered
    assert "p3" in lowered


@pytest.mark.parametrize("path", SECOND_DEVICE_SURFACES)
def test_no_second_device_surface_provisions_anything(path):
    text = Path(path).read_text(encoding="utf-8")
    for needle in ("mkfs", "parted", "fdisk", "mount(", "umount", "boto3", "rclone",
                   "requests.", "urllib.request"):
        assert needle not in text, f"{path} reaches for {needle}"


# -- discovery answers the question the law actually asks ------------------


def test_two_partitions_of_one_disk_are_not_a_second_device():
    """The repository's own disk cannot be its own redundancy, however partitioned."""
    report = discovery.discover()
    repo_disk = report["repository_block_device"]
    if repo_disk is None:
        # A checkout on tmpfs or an overlay — a reproduction clone under /tmp is
        # the normal case. Nothing may be offered at all; see the fail-closed
        # test below, which is where that path is actually asserted.
        assert report["candidates"] == []
        assert report["status"] == discovery.UNAVAILABLE
        return
    for candidate in report["candidates"]:
        assert candidate["block_device"] != repo_disk, candidate


def test_an_unidentifiable_repository_disk_offers_nothing(monkeypatch):
    """Fail closed: if we cannot name our own disk, nothing is a different one.

    Offering a candidate here could hand back the repository's own drive as its
    own redundancy — the exact conflation this section exists to prevent. Found
    by running the suite in a reproduction clone on tmpfs, where the repository
    has no block device at all.
    """
    monkeypatch.setattr(discovery, "_block_device_of", lambda source: None)
    report = discovery.discover()
    assert report["status"] == discovery.UNAVAILABLE
    assert report["candidates"] == []
    assert report["selected"] is None
    assert report["SAME_HOST_SECOND_DEVICE"] == "NO"
    assert "could not be identified" in report["unresolved"]
    assert report["host_loss_redundancy"] == "NOT_PROVEN"
    assert report["blocks_t0"] is False


def test_a_device_that_is_not_writable_is_unhealthy_not_selected(monkeypatch):
    monkeypatch.setattr(discovery, "_writable", lambda target: (False, "read-only file system"))
    report = discovery.discover()
    assert report["selected"] is None
    assert report["status"] == discovery.UNAVAILABLE
    assert report["SAME_HOST_SECOND_DEVICE"] == "NO"
    for candidate in report["candidates"]:
        assert candidate["health"] == discovery.UNHEALTHY
        assert any("not writable" in problem for problem in candidate["problems"])


def test_a_device_without_room_is_unhealthy(monkeypatch):
    monkeypatch.setattr(discovery, "MIN_FREE_BYTES", 1 << 60)
    report = discovery.discover()
    assert report["selected"] is None
    assert any("free" in p for c in report["candidates"] for p in c["problems"])


# -- replication is append-only, by refusal ------------------------------


@pytest.fixture
def sealed(tmp_path):
    """A sealed archive, built without touching any real lane."""
    archive = tmp_path / "artifacts" / "fp-control-2-20260920T140000Z"
    (archive / "evidence").mkdir(parents=True)
    (archive / "evidence" / "paper_input_ledger.jsonl").write_text("{}\n", encoding="utf-8")
    (archive / "tradesv3.sqlite").write_text("db\n", encoding="utf-8")
    (archive / fp_archive.ARCHIVE_MANIFEST).write_text(
        json.dumps({
            "role": "FP-CONTROL-2", "cohort_id": None, "archived_utc": "2026-09-20T14:00:00Z",
            "evidence": {"present": True, "counts": {"input": 1}},
        }, indent=2) + "\n", encoding="utf-8")
    return archive


def test_a_replica_is_written_once_and_re_verified_thereafter(sealed, tmp_path):
    device = tmp_path / "device"
    device.mkdir()
    first = replicator.replicate(sealed, device_root=device)
    assert first["action"] == "REPLICATED"
    assert first["same_host_second_device"] == "YES"
    assert first["host_loss_redundancy"] == "NOT_PROVEN"

    again = replicator.replicate(sealed, device_root=device)
    assert again["action"] == "VERIFIED"


def test_a_divergent_archive_is_refused_not_reconciled(sealed, tmp_path):
    """The divergence is the finding. Overwriting would destroy it."""
    device = tmp_path / "device"
    device.mkdir()
    replicator.replicate(sealed, device_root=device)
    (sealed / "tradesv3.sqlite").write_text("tampered\n", encoding="utf-8")
    with pytest.raises(replicator.ReplicationRefused, match="never\noverwritten|never overwritten"):
        replicator.replicate(sealed, device_root=device)


def test_a_replica_never_lands_inside_the_repository(sealed):
    with pytest.raises(replicator.ReplicationRefused, match="inside the repository"):
        replicator.replicate(sealed, device_root=replicator.REPO_ROOT)


def test_an_unsealed_directory_is_refused(tmp_path):
    loose = tmp_path / "loose"
    loose.mkdir()
    (loose / "paper_input_ledger.jsonl").write_text("{}\n", encoding="utf-8")
    with pytest.raises(replicator.ReplicationRefused, match="not sealed"):
        replicator.replicate(loose, device_root=tmp_path / "device")


def test_a_corrupted_transfer_leaves_no_replica_in_place(sealed, tmp_path, monkeypatch):
    """A partial copy must never acquire the final name."""
    device = tmp_path / "device"
    device.mkdir()
    real = fp_archive.sha256_path
    monkeypatch.setattr(fp_archive, "sha256_path",
                        lambda p: "0" * 64 if "device" in str(p) else real(p))
    with pytest.raises(replicator.ReplicationRefused, match="not the evidence"):
        replicator.replicate(sealed, device_root=device)
    replica = device / replicator.REPLICA_ROOT_NAME / sealed.name
    assert not replica.exists()


def test_the_replica_manifest_states_what_it_is_not(sealed, tmp_path):
    device = tmp_path / "device"
    device.mkdir()
    record = replicator.replicate(sealed, device_root=device)
    written = json.loads(
        (Path(record["replica_dir"]) / replicator.REPLICA_MANIFEST).read_text(encoding="utf-8")
    )
    assert written["host_loss_redundancy"] == "NOT_PROVEN"
    assert "does NOT establish survival of host loss" in written["durability_disclaimer"]
    assert "not Tier 3" in written["durability_disclaimer"]
    assert "NTFS" in written["append_only_enforced_by"]
    assert written["real_money_authorized"] is False


def test_no_healthy_device_is_a_recorded_fact_not_a_blocker(sealed, tmp_path, monkeypatch):
    monkeypatch.setattr(replicator.second_device_discovery, "discover",
                        lambda: {"selected": None})
    with pytest.raises(replicator.ReplicationRefused, match="does not block T0"):
        replicator.replicate(sealed)
    # exit code 3 distinguishes "no device" from "refused"
    assert replicator.main([str(sealed)]) == 3


def test_replication_never_deletes(sealed, tmp_path):
    device = tmp_path / "device"
    device.mkdir()
    replicator.replicate(sealed, device_root=device)
    code = Path("scripts/replicate_to_second_device.py").read_text(encoding="utf-8")
    body = code.split('"""', 2)[2]
    assert "unlink" not in body
    # One rmtree exists, and only to clear a failed staging directory.
    assert body.count("rmtree") == 1
    assert "if staging.exists():" in body
