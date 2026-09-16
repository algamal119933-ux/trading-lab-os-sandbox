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

from fp import ledger as fp_ledger

import publish_evidence_digest as publisher
from fp import archive as fp_archive
from fp import lane as fp_lane

REGISTRY_PATH = Path("research/fp/records/forward_paper_cohort_registry.json")
ROLE = "FP-CONTROL-2"
TEST_LANE = "fp-testlane-s2archive"


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


PUBLICATION_RECORD = Path("research/fp/records/evidence_digest_publication.json")


def fresh_publication(tmp_path: Path) -> Path:
    """An empty publication document with the real record's claims and shape.

    The tests below are about the publish mechanism, so they must start from an
    empty ledger of archives. They used to start from a verbatim copy of the
    committed record, which was indistinguishable from this while that record
    was empty and stopped being so the first time Tier 2 was used for real: on
    the S3 branch, four of these tests failed on the two archives S3 had
    genuinely published. Shape and claims are still read from the real document
    — a test carrying its own copy of the tier-2 disclaimer would stop noticing
    if the real one changed — and only the accumulated entries are dropped.
    """
    document = json.loads(PUBLICATION_RECORD.read_text(encoding="utf-8"))
    document["archives"] = []
    document["published_utc"] = None
    path = tmp_path / "publication.json"
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return path


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
    publication = fresh_publication(tmp_path)
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
    publication = fresh_publication(tmp_path)
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


def test_the_committed_publication_is_valid_and_claims_no_more_than_tier_2():
    """It accumulates. What it must never do is grow a stronger claim.

    This asserted an empty `archives` list until S3, which was a statement
    about the record having never been used rather than about the record. Tier
    2 exists to be appended to; the invariants that matter are that every entry
    validates, that no entry carries evidence content, and that the document
    keeps saying a digest is not a backup.
    """
    document = json.loads(PUBLICATION_RECORD.read_text(encoding="utf-8"))
    schema = json.loads(
        Path("research/schema/evidence_digest_publication.schema.json").read_text(encoding="utf-8")
    )
    assert not list(jsonschema.validators.validator_for(schema)(schema).iter_errors(document))
    assert document["host_loss_redundancy"] is False
    assert document["durability_tier"] == 2
    assert "not a backup" in document["tier_2_disclaimer"]

    for entry in document["archives"]:
        assert entry["archive_name"] and entry["role"]
        assert entry["files"], "an entry with no per-file hashes proves no extent"
        assert all(len(digest) == 64 for digest in entry["files"].values())
        # Identity and extent only. A published digest never carries a ledger
        # payload, a wallet, or a position.
        assert set(entry) <= {
            "archive_name", "role", "cohort_id", "lane_status_at_archival", "reason",
            "archived_utc", "verified_utc", "source_lane", "file_count", "total_bytes",
            "files", "evidence",
        }


# =========================================================================
# Provenance and atomicity.
#
# The archive is the only thing that will exist after the lane is gone, so the
# properties that matter are: it records where it came from, it proves it
# arrived intact rather than assuming it, and nothing is destroyed until that
# proof holds.
# =========================================================================


def test_the_archive_records_where_it_came_from(lane_registry, tmp_path):
    registry, root = lane_registry
    populate(root)
    manifest = fp_archive.archive_lane(
        ROLE, name="provenance", archive_root=tmp_path / "artifacts",
        reason="L1 qualification", registry=registry,
    )
    assert manifest["source_lane"] == str(root.resolve())
    assert manifest["archive_dir"] == str((tmp_path / "artifacts" / "provenance").resolve())
    assert manifest["role"] == ROLE
    assert manifest["reason"] == "L1 qualification"
    assert manifest["lane_status_at_archival"] == "NOT_STARTED"
    # The path recorded is canonical, not the name that led to it.
    assert Path(manifest["source_lane"]).is_absolute()


def _executable_source(path: str) -> str:
    """The module's code with docstrings and comments stripped.

    Scanning the raw text would match the very prose that explains why a rename
    is not used — a test that fails because the reasoning is documented is a
    test that pressures someone to delete the reasoning.
    """
    import ast, io, tokenize

    text = Path(path).read_text(encoding="utf-8")
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                text = text.replace(doc, "")
    out = []
    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        if token.type != tokenize.COMMENT:
            out.append(token.string)
    return "".join(out)


def test_the_protocol_is_copy_verify_seal_remove_and_never_a_rename(lane_registry, tmp_path):
    """A rename is cheaper and is deliberately not used. Proven, not asserted."""
    registry, root = lane_registry
    populate(root)
    manifest = fp_archive.archive_lane(ROLE, name="protocol", archive_root=tmp_path / "artifacts",
                                       registry=registry)
    assert manifest["rename_used"] is False
    assert manifest["transfer_protocol"] == "COPY -> VERIFY BYTES -> VERIFY LEDGERS -> SEAL -> REMOVE"
    code = _executable_source("research/fp/archive.py")
    for forbidden in ("os.rename", "shutil.move", "os.replace", '"mv"', "'mv'"):
        assert forbidden not in code, f"archive.py uses {forbidden}"
    assert "shutil.copytree" in code


def test_the_manifest_records_both_devices_without_branching_on_them(lane_registry, tmp_path):
    """Cross-filesystem archival takes the same code path as same-filesystem."""
    registry, root = lane_registry
    populate(root)
    manifest = fp_archive.archive_lane(ROLE, name="devices", archive_root=tmp_path / "artifacts",
                                       registry=registry)
    assert isinstance(manifest["source_device"], int)
    assert isinstance(manifest["archive_device"], int)
    assert manifest["crossed_filesystem"] == (
        manifest["source_device"] != manifest["archive_device"]
    )
    # Recorded and never consulted: the devices appear exactly once each, in the
    # manifest literal, and no branch anywhere selects a transfer strategy from
    # them. A cross-filesystem archive therefore runs the code that was tested.
    code = _executable_source("research/fp/archive.py")
    import re as _re

    for name in ("source_device", "archive_device", "crossed_filesystem"):
        for statement in _re.findall(r"^\s*(?:if|elif|while)\b.*$", code, _re.MULTILINE):
            assert name not in statement, f"{name} is branched on: {statement.strip()}"


def test_pre_and_post_ledger_state_must_be_identical(lane_registry, tmp_path, monkeypatch):
    """The archived chains are re-opened and required to agree with the lane."""
    registry, root = lane_registry
    evidence = root / "evidence"
    evidence.mkdir(parents=True)
    (root / "logs").mkdir(parents=True)
    (root / "tradesv3.sqlite").write_text("db\n", encoding="utf-8")
    ledgers = fp_ledger.open_ledgers(evidence, create=True)
    for index in range(3):
        ledgers["input"].append({"pair": "BTC/USDT", "candle_ts": index, "identity": {}})

    manifest = fp_archive.archive_lane(ROLE, name="ledgers", archive_root=tmp_path / "artifacts",
                                       registry=registry)
    assert manifest["evidence"]["counts"]["input"] == 3
    assert manifest["evidence"]["chain_problems"] == []

    # And the archived copy really is the thing that was verified.
    archived = fp_ledger.open_ledgers(tmp_path / "artifacts" / "ledgers" / "evidence")
    assert archived["input"].tip_digest() == manifest["evidence"]["ledger_tips"]["input"]
    assert archived["input"].verify() == []


def test_a_copy_that_does_not_match_leaves_the_lane_untouched(lane_registry, tmp_path, monkeypatch):
    """Nothing is destroyed until the proof holds."""
    registry, root = lane_registry
    populate(root)
    real = fp_archive.sha256_path
    # Every re-read from the destination returns a wrong hash, as a silently
    # corrupted copy would.
    monkeypatch.setattr(fp_archive, "sha256_path",
                        lambda p: "0" * 64 if "artifacts" in str(p) else real(p))
    with pytest.raises(fp_archive.ArchiveError, match="is not the evidence"):
        fp_archive.archive_lane(ROLE, name="mismatch", archive_root=tmp_path / "artifacts",
                                registry=registry)
    # The lane survives a failed archival completely.
    assert (root / "tradesv3.sqlite").is_file()
    assert (root / "evidence" / "paper_input_ledger.jsonl").is_file()


def test_the_archive_is_sealed_before_the_source_is_removed(lane_registry, tmp_path, monkeypatch):
    """If the remove fails, a complete sealed archive already exists."""
    registry, root = lane_registry
    populate(root)
    monkeypatch.setattr(fp_archive.shutil, "rmtree",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("permission denied")))
    with pytest.raises(OSError):
        fp_archive.archive_lane(ROLE, name="sealed-first", archive_root=tmp_path / "artifacts",
                                registry=registry)
    archive = tmp_path / "artifacts" / "sealed-first"
    assert (archive / fp_archive.ARCHIVE_MANIFEST).is_file()
    assert (archive / "tradesv3.sqlite").is_file()
    manifest = json.loads((archive / fp_archive.ARCHIVE_MANIFEST).read_text(encoding="utf-8"))
    assert manifest["file_count"] == 8


def test_a_running_container_refuses_archival(lane_registry, tmp_path, monkeypatch):
    """The engine holds the database open and never touches the capture lock."""
    registry, root = lane_registry
    populate(root)
    monkeypatch.setattr(fp_archive, "running_container", lambda bot_name: "fp-control-2-engine")
    with pytest.raises(fp_archive.ArchiveError, match="mid-write database"):
        fp_archive.archive_lane(ROLE, name="engine-up", archive_root=tmp_path / "artifacts",
                                registry=registry)
    assert (root / "tradesv3.sqlite").is_file()


def test_an_unreachable_docker_daemon_reads_as_nothing_running():
    """Sound rather than lenient: this stack exists only as a compose project."""
    assert fp_archive.running_container("a-name-no-container-has-" + "x" * 20) is None


def test_a_previously_published_digest_still_verifies_after_a_later_archive(
    lane_registry, tmp_path
):
    """Archive Point A survives Archive Point B. Tier 2's whole purpose."""
    registry, root = lane_registry
    populate(root)
    fp_archive.archive_lane(ROLE, name="point-a", archive_root=tmp_path / "artifacts",
                            reason="A", registry=registry)
    publication = fresh_publication(tmp_path)
    entry_a = publisher.verify_archive(tmp_path / "artifacts" / "point-a")
    publisher.publish(entry_a, publication)

    # A second, entirely separate lane is archived afterwards.
    populate(root)
    fp_archive.archive_lane(ROLE, name="point-b", archive_root=tmp_path / "artifacts",
                            reason="B", registry=registry)
    entry_b = publisher.verify_archive(tmp_path / "artifacts" / "point-b")
    document = publisher.publish(entry_b, publication)

    assert len(document["archives"]) == 2
    # Point A re-verifies byte for byte, and its published digests are unchanged.
    again = publisher.verify_archive(tmp_path / "artifacts" / "point-a")
    assert again["files"] == entry_a["files"]
    assert again["evidence"]["daily_pack_digest"] == entry_a["evidence"]["daily_pack_digest"]
    published_a = next(a for a in document["archives"] if a["archive_name"] == "point-a")
    assert published_a["files"] == entry_a["files"]
