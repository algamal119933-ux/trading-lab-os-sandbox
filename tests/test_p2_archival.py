"""Tier-1 archival and Tier-2 digest publication, with their refusals.

Archiving is the mechanism that keeps the three lanes of contract section 4
from becoming one. Two properties carry that weight, and each has a negative
control here:

* **the whole lane moves, or nothing does.** Archiving only ``evidence/`` would
  carry pre-T0 wallet and position state into a post-T0 cohort through
  ``tradesv3.sqlite`` — the database is the leak, not the ledgers, and it is the
  file a reasonable person would forget.
* **the destination is outside every mounted lane.** ``freqtrade/user_data`` is
  the only host tree any container mounts, so an archive kept inside it is not
  archived at all; and ``lane.resolve_lane`` refuses a root outside canonical
  user_data, which is what stops an archive ever being read back as a lane.

Tier 2 then publishes digests of what was sealed. Its own negative control is
the one that matters: an archive that no longer matches its manifest must refuse
publication rather than quietly publish the new bytes, because the divergence IS
the finding.
"""

from __future__ import annotations

import copy
import fcntl
import json
import os
import shutil
from pathlib import Path

import jsonschema
import pytest

import publish_evidence_digest as publisher
from fp import archive as fp_archive
from fp import lane as fp_lane

REGISTRY_PATH = Path("research/fp/records/forward_paper_cohort_registry.json")
ROLE = "FP-CONTROL-2"
TEST_LANE = "fp-control-2-s2archivetest"


@pytest.fixture
def lane_registry(tmp_path):
    """A registry whose successor row points at a disposable real lane.

    The lane must live under the canonical ``freqtrade/user_data`` — a lane
    anywhere else is refused by ``resolve_lane``, which is the behaviour being
    relied on, so the fixture cannot sidestep it by using tmp_path.
    """
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    registry = copy.deepcopy(registry)
    row = next(item for item in registry["instances"] if item["role"] == ROLE)
    identity = row["runtime_identity"]
    for field in ("db_path", "log_path", "evidence_dir"):
        identity[field] = identity[field].replace("/fp-control-2/", f"/{TEST_LANE}/")
    root = fp_lane.HOST_USER_DATA / TEST_LANE
    if root.exists():
        shutil.rmtree(root)
    try:
        yield registry, root
    finally:
        if root.exists():
            shutil.rmtree(root)


def populate(root: Path) -> dict:
    """A lane holding everything a real one does, including the database."""
    (root / "evidence").mkdir(parents=True)
    (root / "logs").mkdir(parents=True)
    files = {
        "evidence/paper_input_ledger.jsonl": "",
        "evidence/paper_decision_ledger.jsonl": "",
        "evidence/paper_trade_ledger.jsonl": "",
        "evidence/paper_incident_ledger.jsonl": "",
        "evidence/capture_runtime.json": '{"written_utc": "2026-09-16T00:00:00Z"}\n',
        "evidence/.fp_capture.lock": "",
        "logs/freqtrade.log": "engine started\n",
        "tradesv3.sqlite": "SQLite format 3\x00 wallet and position state\n",
    }
    for name, body in files.items():
        (root / name).write_text(body, encoding="utf-8")
    return files


# -- the whole lane moves --------------------------------------------------


def test_the_whole_lane_is_archived_including_the_database(lane_registry, tmp_path):
    registry, root = lane_registry
    files = populate(root)
    manifest = fp_archive.archive_lane(
        ROLE, name="whole-lane", archive_root=tmp_path / "artifacts",
        reason="test", registry=registry,
    )
    archived = set(manifest["files"])
    assert archived == set(files), archived ^ set(files)
    # The database is the file that would carry wallet and position state
    # across, and the one most likely to be left behind by an
    # evidence-directory-only archive.
    assert "tradesv3.sqlite" in archived
    assert "evidence/.fp_capture.lock" in archived
    assert "logs/freqtrade.log" in archived
    landed = tmp_path / "artifacts" / "whole-lane" / "tradesv3.sqlite"
    assert "wallet and position state" in landed.read_text(encoding="utf-8")


def test_the_lane_is_returned_empty(lane_registry, tmp_path):
    registry, root = lane_registry
    populate(root)
    fp_archive.archive_lane(ROLE, name="emptied", archive_root=tmp_path / "artifacts",
                            registry=registry)
    assert root.is_dir()
    assert list(root.iterdir()) == []
    empty, detail = fp_archive.lane_is_empty(ROLE, registry)
    assert empty, detail


def test_a_lane_holding_a_file_is_not_empty(lane_registry):
    registry, root = lane_registry
    populate(root)
    empty, detail = fp_archive.lane_is_empty(ROLE, registry)
    assert not empty
    assert "holds" in detail


def test_the_manifest_never_claims_host_loss_redundancy(lane_registry, tmp_path):
    registry, root = lane_registry
    populate(root)
    manifest = fp_archive.archive_lane(ROLE, name="claims", archive_root=tmp_path / "artifacts",
                                       registry=registry)
    assert manifest["durability_tier"] == 1
    assert manifest["host_loss_redundancy"] is False
    assert "does NOT establish survival of host loss" in manifest["tier_1_disclaimer"]
    assert manifest["real_money_authorized"] is False


# -- refusals --------------------------------------------------------------


def test_archiving_under_a_live_writer_is_refused(lane_registry, tmp_path):
    """Moving a ledger mid-append is how an archive becomes a truncated chain."""
    registry, root = lane_registry
    populate(root)
    handle = os.open(root / "evidence" / ".fp_capture.lock", os.O_RDWR)
    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        with pytest.raises(fp_archive.ArchiveError, match="holds the lock"):
            fp_archive.archive_lane(ROLE, name="live", archive_root=tmp_path / "artifacts",
                                    registry=registry)
    finally:
        fcntl.flock(handle, fcntl.LOCK_UN)
        os.close(handle)
    # Refused means unchanged: the lane still holds every file.
    assert (root / "tradesv3.sqlite").is_file()


def test_an_existing_archive_is_never_overwritten(lane_registry, tmp_path):
    registry, root = lane_registry
    populate(root)
    destination = tmp_path / "artifacts" / "taken"
    destination.mkdir(parents=True)
    with pytest.raises(fp_archive.ArchiveError, match="already exists"):
        fp_archive.archive_lane(ROLE, name="taken", archive_root=tmp_path / "artifacts",
                                registry=registry)
    assert (root / "tradesv3.sqlite").is_file()


def test_an_archive_inside_a_mounted_lane_is_refused(lane_registry):
    """An archive a container can reach is not archived."""
    registry, root = lane_registry
    populate(root)
    with pytest.raises(fp_archive.ArchiveError, match="mounts|declared lane"):
        fp_archive.archive_lane(ROLE, name="inside", archive_root=fp_lane.HOST_USER_DATA,
                                registry=registry)
    assert (root / "tradesv3.sqlite").is_file()


def test_a_lane_containing_a_symlink_is_refused(lane_registry, tmp_path):
    """A link points at something the lane does not own, so the lane is not self-contained."""
    registry, root = lane_registry
    populate(root)
    (root / "evidence" / "elsewhere.jsonl").symlink_to(tmp_path / "outside.jsonl")
    with pytest.raises(fp_archive.ArchiveError, match="symlink"):
        fp_archive.archive_lane(ROLE, name="linked", archive_root=tmp_path / "artifacts",
                                registry=registry)


def test_archiving_a_lane_that_does_not_exist_is_refused(lane_registry, tmp_path):
    registry, _ = lane_registry
    with pytest.raises(fp_archive.ArchiveError, match="does not exist"):
        fp_archive.archive_lane(ROLE, name="absent", archive_root=tmp_path / "artifacts",
                                registry=registry)


# -- Tier 2 ----------------------------------------------------------------


@pytest.fixture
def sealed(lane_registry, tmp_path):
    registry, root = lane_registry
    populate(root)
    manifest = fp_archive.archive_lane(ROLE, name="sealed", archive_root=tmp_path / "artifacts",
                                       reason="tier-2 test", registry=registry)
    return tmp_path / "artifacts" / "sealed", manifest


def test_a_published_digest_validates_against_its_schema(sealed, tmp_path):
    archive_dir, _ = sealed
    entry = publisher.verify_archive(archive_dir)
    publication = tmp_path / "publication.json"
    publication.write_text(
        Path("research/fp/records/evidence_digest_publication.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    document = publisher.publish(entry, publication)
    schema = json.loads(
        Path("research/schema/evidence_digest_publication.schema.json").read_text(encoding="utf-8")
    )
    errors = list(jsonschema.validators.validator_for(schema)(schema).iter_errors(document))
    assert not errors, [e.message for e in errors]
    assert document["archives"][0]["archive_name"] == "sealed"
    assert document["host_loss_redundancy"] is False


def test_publication_carries_no_evidence_content(sealed, tmp_path):
    """Names and hashes only. The ledger bytes stay on the host."""
    archive_dir, _ = sealed
    entry = publisher.verify_archive(archive_dir)
    text = json.dumps(entry)
    assert "wallet and position state" not in text
    assert "engine started" not in text
    for digest in entry["files"].values():
        assert len(digest) == 64


def test_a_mutated_archive_refuses_publication(sealed):
    archive_dir, _ = sealed
    (archive_dir / "tradesv3.sqlite").write_text("tampered\n", encoding="utf-8")
    with pytest.raises(publisher.PublishError, match="changed"):
        publisher.verify_archive(archive_dir)


def test_a_file_added_to_an_archive_refuses_publication(sealed):
    archive_dir, _ = sealed
    (archive_dir / "planted.jsonl").write_text("{}\n", encoding="utf-8")
    with pytest.raises(publisher.PublishError, match="added"):
        publisher.verify_archive(archive_dir)


def test_a_file_removed_from_an_archive_refuses_publication(sealed):
    archive_dir, _ = sealed
    (archive_dir / "logs" / "freqtrade.log").unlink()
    with pytest.raises(publisher.PublishError, match="missing"):
        publisher.verify_archive(archive_dir)


def test_an_unsealed_directory_refuses_publication(tmp_path):
    loose = tmp_path / "loose"
    loose.mkdir()
    (loose / "paper_input_ledger.jsonl").write_text("{}\n", encoding="utf-8")
    with pytest.raises(publisher.PublishError, match="not sealed"):
        publisher.verify_archive(loose)


def test_a_published_digest_is_never_rewritten(sealed, tmp_path):
    """Re-verification is the point. Silent replacement is the attack."""
    archive_dir, _ = sealed
    publication = tmp_path / "publication.json"
    publication.write_text(
        Path("research/fp/records/evidence_digest_publication.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    entry = publisher.verify_archive(archive_dir)
    publisher.publish(entry, publication)

    # Re-verifying the same archive is allowed and only moves verified_utc.
    again = publisher.verify_archive(archive_dir)
    document = publisher.publish(again, publication)
    assert len(document["archives"]) == 1

    forged = dict(again)
    forged["files"] = dict(again["files"])
    forged["files"]["tradesv3.sqlite"] = "0" * 64
    with pytest.raises(publisher.PublishError, match="already published with different"):
        publisher.publish(forged, publication)


def test_the_committed_publication_starts_empty_and_valid():
    document = json.loads(
        Path("research/fp/records/evidence_digest_publication.json").read_text(encoding="utf-8")
    )
    schema = json.loads(
        Path("research/schema/evidence_digest_publication.schema.json").read_text(encoding="utf-8")
    )
    assert not list(jsonschema.validators.validator_for(schema)(schema).iter_errors(document))
    assert document["archives"] == []
    assert document["host_loss_redundancy"] is False
    assert "not a backup" in document["tier_2_disclaimer"]
