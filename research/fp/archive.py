"""Tier-1 archival: move a whole evidence lane out of reach, and seal it.

Contract section 8 names what this may and may not claim, and the distinction
is the whole point. Tier 1 makes lanes uncommingleable on this host: no running
container can reach an archived lane, and operator error in the live lane cannot
destroy archived evidence. It does **not** survive host loss, disk failure or
this machine being decommissioned, and a same-host copy is never described as
host-loss redundancy, in any record, at any time. The project has already paid
once for conflating the two, under the closure reason
``EVIDENCE_LANE_LOST_IN_HOST_MIGRATION``.

Two rules decide almost everything here.

**The whole lane moves, or nothing does.** Archiving only ``evidence/`` would
carry pre-T0 wallet and position state into a post-T0 cohort through
``tradesv3.sqlite``, which is exactly the cross-lane crediting the contract's
section 4 exists to prevent. So the unit is the lane directory: evidence, logs,
the database, ``capture_runtime.json``, the lock file, and anything else that is
in there — including files this module has never heard of, because a file nobody
anticipated is the one most likely to carry state across.

**The destination is outside the only mounted host tree.** ``docker-compose``
mounts ``freqtrade/user_data`` and nothing else, so an archive under
``artifacts/`` cannot be reached from inside any container, and
``lane.resolve_lane`` refuses any lane root resolving outside canonical
``user_data`` — which means an archive can never later be mistaken for a lane.

**There is no rename, and no ``mv``.** The protocol is, in this order and
always:

    COPY    every file, symlinks refused outright
    VERIFY  re-read every byte from the DESTINATION and hash it against the
            source; refuse on the first divergence, and on any file that
            arrived which the lane did not have
    VERIFY  re-open the archived ledgers and require their tips, their daily
            pack digest and their record counts to equal what the lane had
    SEAL    write the manifest into the archive
    REMOVE  only now delete the source, and recreate the lane root empty

A rename would be atomic and far cheaper, and it is deliberately not used.
``os.rename`` fails across filesystems, and ``shutil.move``/GNU ``mv`` silently
degrade to a copy-and-unlink when it does — so a lane on one device and an
archive on another would take a completely different code path from the one
anybody tested, discovered at the moment a 6 GB evidence lane is being sealed.
More importantly, a rename gives no opportunity to re-read what landed, and an
archive nobody has read back is an assumption rather than a copy. The manifest
records both devices so a later reader can see whether the copy crossed one,
but the protocol does not branch on the answer: it is the same protocol either
way.

Nothing here deletes anything until the archive is complete, verified and
sealed.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

from fp import lane as fp_lane  # noqa: E402
from fp import ledger as fp_ledger  # noqa: E402

ARCHIVE_ROOT = REPO_ROOT / "artifacts"
ARCHIVE_MANIFEST = "archive_manifest.json"
ARCHIVE_ENGINE_VERSION = "FP_LANE_ARCHIVE_V1"
LOCK_FILENAME = ".fp_capture.lock"

# What this tier may truthfully claim, carried in every manifest so a later
# reader cannot acquire a stronger belief from the file than the contract grants.
TIER1_CLAIM = (
    "TIER_1_SAME_HOST_ARCHIVAL: lanes cannot be commingled or cross-credited; no running "
    "container can reach this archive; operator error in the live lane cannot destroy it."
)
TIER1_DISCLAIMER = (
    "This is a SAME-HOST copy. It does NOT establish survival of host loss, disk failure, "
    "filesystem corruption, or this machine being decommissioned. Only a Tier-3 "
    "independent-host snapshot may claim host-loss redundancy."
)


class ArchiveError(Exception):
    """Archival refused or failed. Never partial, never advisory."""


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def lane_is_locked(evidence_dir: Path) -> bool:
    """Is a capture loop holding this lane's advisory lock right now?

    Archiving under a live writer would move a ledger mid-append. ``flock`` is
    the same mechanism the capture loop uses, and the kernel drops it when the
    holding process dies, so a crashed runtime does not block archival forever
    while a genuinely live one does.
    """
    lock_path = Path(evidence_dir) / LOCK_FILENAME
    if not lock_path.is_file():
        return False
    try:
        handle = os.open(lock_path, os.O_RDWR)
    except OSError:
        # Unreadable is not "unlocked": fail closed.
        return True
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return True
    else:
        fcntl.flock(handle, fcntl.LOCK_UN)
        return False
    finally:
        os.close(handle)


def running_container(bot_name: str) -> str | None:
    """The name of a running container for this lane, or None.

    The evidence lock catches a live capture loop. It does not catch the
    ENGINE: freqtrade holds ``tradesv3.sqlite`` open, writes to it, and never
    touches the capture lock — so a lane could be archived out from under a
    running engine with every lock check passing, and the archived database
    would be a mid-write snapshot.

    A docker daemon that cannot be reached is treated as "nothing is running",
    and that is sound rather than lenient: this stack exists only as a
    docker-compose project, so if there is no daemon there is no engine. An
    unreachable daemon on a host that never had one is the normal case in CI.
    """
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", f"name={bot_name}", "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    names = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return names[0] if names else None


def walk_files(root: Path) -> list[Path]:
    """Every regular file under ``root``, relative, sorted.

    Symlinks are not followed and not archived: a link is a pointer to
    something outside the lane, and copying the pointer would produce an archive
    whose contents depend on a live filesystem it no longer owns.
    """
    out: list[Path] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ArchiveError(
                f"{path} is a symlink. A lane containing a link does not contain its own "
                "evidence, and an archive of the link would depend on a tree it no longer owns"
            )
        if path.is_file():
            out.append(path.relative_to(root))
    return out


def _ledger_digests(evidence_dir: Path) -> dict:
    """Ledger tips, the daily pack digest and record counts — Tier-2's payload.

    Read before the move, so what is published describes the lane as it was
    sealed. If the lane holds no ledgers — a lane that never ran — the fields
    are explicitly null rather than absent: "there were none" and "we did not
    look" must not collapse into the same record.
    """
    if not Path(evidence_dir).is_dir():
        return {"present": False, "ledger_tips": None, "daily_pack_digest": None, "counts": None}
    ledgers = fp_ledger.open_ledgers(evidence_dir)
    counts = {}
    problems: list[str] = []
    for kind, led in sorted(ledgers.items()):
        records = led.records()
        counts[kind] = len(records)
        problems.extend(f"{kind}: {item}" for item in led.verify())
    return {
        "present": True,
        "ledger_tips": {kind: led.tip_digest() for kind, led in sorted(ledgers.items())},
        "daily_pack_digest": fp_ledger.daily_pack_digest(ledgers.values()),
        "counts": counts,
        "chain_problems": problems,
    }


def archive_lane(
    role: str,
    *,
    name: str | None = None,
    archive_root: Path | None = None,
    reason: str = "",
    registry: dict | None = None,
) -> dict:
    """Move ``role``'s entire lane into ``artifacts/<name>/`` and seal it.

    Returns the manifest. Raises :class:`ArchiveError` on any refusal, and a
    refusal leaves the lane exactly as it was — archival is all-or-nothing
    because a half-moved lane is neither archived nor live.
    """
    # No allowed_statuses: archiving is not executing. A CLOSED lane is the
    # normal thing to archive, and a PAUSED one must not become unarchivable for
    # the same reason it must not become unstoppable.
    try:
        lane = fp_lane.resolve_lane(role, registry)
    except fp_lane.LaneError as exc:
        raise ArchiveError(str(exc)) from exc
    lane.assert_root_is_canonical()

    # Canonicalised on both sides. resolve_lane has already refused a root that
    # escapes user_data, but the value that goes into the manifest — and the one
    # every containment comparison below uses — must be the real path, not the
    # name that led to it.
    source = lane.host_instance_dir.resolve()
    if not source.is_dir():
        raise ArchiveError(f"{role}'s lane {source} does not exist; there is nothing to archive")

    if lane_is_locked(lane.host_evidence_dir):
        raise ArchiveError(
            f"a capture loop holds the lock on {lane.host_evidence_dir}. Archiving under a live "
            "writer would move a ledger mid-append; stop the runtime first"
        )
    container = running_container(lane.bot_name)
    if container:
        raise ArchiveError(
            f"container {container!r} is running for {role}. The engine holds "
            f"{lane.host_db_path.name} open and never touches the capture lock, so archiving now "
            "would seal a mid-write database; stop the stack first: "
            f"scripts/stop_fp_control.sh {role}"
        )

    root = Path(archive_root or ARCHIVE_ROOT)
    archive_name = name or f"{lane.instance_dir}-{utc_stamp()}"
    if "/" in archive_name or archive_name in (".", ".."):
        raise ArchiveError(f"{archive_name!r} is not a single directory name")
    destination = (root / archive_name).resolve()

    # The destination must be outside every declared lane, or the archive would
    # be reachable from a container and could later be mistaken for a lane.
    for declared in fp_lane.all_lane_roots(registry):
        if destination == declared or declared in destination.parents:
            raise ArchiveError(
                f"{destination} is inside the declared lane {declared}; an archive kept inside a "
                "mounted lane is reachable from a container and is not archived at all"
            )
    user_data = fp_lane.HOST_USER_DATA.resolve()
    if destination == user_data or user_data in destination.parents:
        raise ArchiveError(
            f"{destination} is under {user_data}, the only host tree any container mounts"
        )
    if destination.exists():
        raise ArchiveError(
            f"{destination} already exists. Archives are never overwritten: the existing one is "
            "evidence, and replacing it is how a sealed lane silently becomes a different lane"
        )

    files = walk_files(source)
    digests_before = {str(rel): sha256_path(source / rel) for rel in files}
    ledger_state = _ledger_digests(lane.host_evidence_dir)

    root.mkdir(parents=True, exist_ok=True)
    source_device = os.stat(source).st_dev
    archive_device = os.stat(root).st_dev
    # COPY. Never os.rename, never shutil.move, never mv: rename fails across
    # filesystems and move silently degrades to copy-and-unlink when it does, so
    # a cross-device lane would take a code path nobody tested, at the moment a
    # multi-gigabyte evidence lane is being sealed. walk_files has already
    # refused any symlink, so symlinks=True here copies nothing that could
    # escape — it is set so that a link appearing between the walk and the copy
    # is preserved as a link and then caught by the extra-files check, rather
    # than silently followed out of the lane.
    shutil.copytree(source, destination, symlinks=True)

    verified: dict[str, str] = {}
    for rel, expected in digests_before.items():
        landed = destination / rel
        if not landed.is_file():
            raise ArchiveError(f"{rel} did not arrive in {destination}; the archive is incomplete")
        actual = sha256_path(landed)
        if actual != expected:
            raise ArchiveError(
                f"{rel} hashes to {actual[:12]} in the archive but {expected[:12]} in the lane; "
                "the copy is not the evidence"
            )
        verified[rel] = actual

    extra = {str(rel) for rel in walk_files(destination)} - set(digests_before) - {ARCHIVE_MANIFEST}
    if extra:
        raise ArchiveError(f"the archive holds files the lane did not: {sorted(extra)[:5]}")

    # The ledgers are re-opened FROM THE ARCHIVE and required to agree with what
    # the lane held. Per-file hashes already prove the bytes arrived; this proves
    # the archived chains still verify as chains, and that the record counts and
    # pack digest a Tier-2 publication will carry describe the archive rather
    # than a memory of the lane.
    archived_evidence = destination / lane.host_evidence_dir.name
    ledger_state_after = _ledger_digests(archived_evidence)
    for field in ("ledger_tips", "daily_pack_digest", "counts"):
        if ledger_state.get(field) != ledger_state_after.get(field):
            raise ArchiveError(
                f"the archived evidence disagrees with the lane on {field}: "
                f"{ledger_state.get(field)} in the lane, {ledger_state_after.get(field)} in "
                f"{destination}"
            )
    if ledger_state_after.get("chain_problems"):
        raise ArchiveError(
            f"the archived ledgers do not verify: {ledger_state_after['chain_problems'][:3]}"
        )

    manifest = {
        "archive_engine_version": ARCHIVE_ENGINE_VERSION,
        "archived_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "role": role,
        "lane_status_at_archival": lane.status,
        "cohort_id": (fp_lane.select_row(role, registry).get("cohort_id")),
        "source_lane": str(source),
        "archive_dir": str(destination),
        # Recorded, never branched on. The protocol is copy-verify-seal-remove
        # whether or not the copy crossed a device boundary, so that a cross-
        # filesystem archive does not take a different code path from the one
        # that was tested.
        "source_device": source_device,
        "archive_device": archive_device,
        "crossed_filesystem": source_device != archive_device,
        "transfer_protocol": "COPY -> VERIFY BYTES -> VERIFY LEDGERS -> SEAL -> REMOVE",
        "rename_used": False,
        "reason": reason,
        "file_count": len(verified),
        "total_bytes": sum((destination / rel).stat().st_size for rel in verified),
        "files": dict(sorted(verified.items())),
        "evidence": ledger_state,
        "durability_tier": 1,
        "tier_1_claim": TIER1_CLAIM,
        "tier_1_disclaimer": TIER1_DISCLAIMER,
        "host_loss_redundancy": False,
        "real_money_authorized": False,
    }
    (destination / ARCHIVE_MANIFEST).write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )

    # Only now is the source removed, and the lane root is recreated empty so
    # the next run starts from a lane that demonstrably holds nothing.
    shutil.rmtree(source)
    source.mkdir(parents=True, exist_ok=False)

    remaining = list(source.iterdir())
    if remaining:
        raise ArchiveError(
            f"{source} still holds {[p.name for p in remaining][:5]} after archival; a lane that is "
            "not empty is not a fresh lane, and this tool does not return one"
        )
    return manifest


def lane_is_empty(role: str, registry: dict | None = None) -> tuple[bool, str]:
    """Is ``role``'s lane empty — the state a fresh cohort requires?

    Used by the freeze gate, which must never freeze a T0 over a lane that still
    holds someone else's records.
    """
    try:
        lane = fp_lane.resolve_lane(role, registry)
    except fp_lane.LaneError as exc:
        return False, str(exc)
    root = lane.host_instance_dir
    if not root.exists():
        return True, f"{root} does not exist yet"
    entries = sorted(p.name for p in root.rglob("*") if p.is_file() or p.is_symlink())
    if entries:
        return False, f"{root} holds {len(entries)} file(s): {entries[:5]}"
    return True, f"{root} exists and holds no file"
