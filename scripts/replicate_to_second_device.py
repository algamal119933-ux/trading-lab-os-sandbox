#!/usr/bin/env python3
"""Place a sealed evidence archive on the second physical device, append-only.

    scripts/replicate_to_second_device.py artifacts/fp-control-2-20260920T140000Z
    scripts/replicate_to_second_device.py <archive> --verify-only

P2 contract section 8. When the secondary WDC disk is available and healthy, the
sealed evidence is copied onto it, so the failure of either single drive does not
by itself destroy the cohort's evidence.

WHAT THIS IS NOT. Two drives in one chassis share a power supply, a room, and a
thief. Every record this writes says so on its face:

    SAME_HOST_SECOND_DEVICE = YES
    HOST_LOSS_REDUNDANCY    = NOT_PROVEN

It is not called Tier 3. Independent-host storage, restore qualification and
disaster recovery are P3 operational-hardening scope.

APPEND-ONLY, AND HOW. The device is NTFS, which carries no POSIX ownership or
immutability bits, so append-only cannot be enforced by the filesystem and is
not pretended to be. It is enforced by this tool's refusals instead: a replica
directory is written once and never overwritten; re-running against an unchanged
archive re-verifies it and writes nothing; and an archive whose bytes no longer
match an existing replica is REFUSED rather than reconciled, because that
divergence is the single most important thing either copy could tell you.

Nothing here deletes anything, ever.

Exit codes: 0 replicated or verified; 2 refused; 3 no healthy second device.

PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for _extra in (str(REPO_ROOT / "research"), str(REPO_ROOT / "scripts")):
    if _extra not in sys.path:
        sys.path.insert(0, _extra)

import second_device_discovery  # noqa: E402
from fp import archive as fp_archive  # noqa: E402
from fp import lane as fp_lane  # noqa: E402

REPLICA_ROOT_NAME = "trading-lab-os-evidence"
REPLICA_MANIFEST = "replica_manifest.json"
REPLICA_VERSION = "FP_SECOND_DEVICE_REPLICA_V1"

SAME_HOST_SECOND_DEVICE = "YES"
HOST_LOSS_REDUNDANCY = "NOT_PROVEN"

CLAIM = (
    "The sealed evidence exists on a second physical device in this workstation, so the "
    "failure of either single drive does not by itself destroy it."
)
DISCLAIMER = (
    "SAME-HOST copy. It does NOT establish survival of host loss, workstation destruction, "
    "theft, or a host-wide filesystem or OS catastrophe. HOST_LOSS_REDUNDANCY = NOT_PROVEN. "
    "This is not Tier 3; independent-host storage and restore qualification are P3 scope."
)


class ReplicationRefused(Exception):
    pass


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def select_device() -> dict:
    report = second_device_discovery.discover()
    if not report["selected"]:
        raise ReplicationRefused(
            "no healthy second physical device is available. This does not block T0: Tier 1 and "
            "Tier 2 are unconditional and the cohort proceeds on them. Recorded, not repaired"
        )
    return report


def _archive_digests(archive_dir: Path) -> dict[str, str]:
    return {
        str(rel): fp_archive.sha256_path(archive_dir / rel)
        for rel in fp_archive.walk_files(archive_dir)
    }


def replicate(archive_dir: Path, *, device_root: Path | None = None,
              verify_only: bool = False) -> dict:
    archive_dir = Path(archive_dir).resolve()
    manifest_path = archive_dir / fp_archive.ARCHIVE_MANIFEST
    if not manifest_path.is_file():
        raise ReplicationRefused(
            f"{archive_dir} carries no {fp_archive.ARCHIVE_MANIFEST}; it was not sealed by "
            "scripts/archive_fp_lane.py and its contents cannot be attributed to a lane"
        )
    source_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    if device_root is None:
        device = select_device()
        target_root = Path(device["selected"]["target"]) / REPLICA_ROOT_NAME
        device_detail = {
            "block_device": device["selected"]["block_device"],
            "model": device["selected"]["model"],
            "mount": device["selected"]["target"],
            "fstype": device["selected"]["fstype"],
        }
    else:
        target_root = Path(device_root) / REPLICA_ROOT_NAME
        device_detail = {"block_device": None, "model": "", "mount": str(device_root),
                         "fstype": ""}

    target_root = target_root.resolve() if target_root.exists() else target_root
    # A replica is not a lane and must never land inside one, nor inside the
    # repository, where it would be an untracked tree the integrity gate trips on.
    for declared in fp_lane.all_lane_roots():
        if target_root == declared or declared in target_root.parents:
            raise ReplicationRefused(f"{target_root} is inside the evidence lane {declared}")
    if REPO_ROOT == target_root or REPO_ROOT in target_root.parents:
        raise ReplicationRefused(
            f"{target_root} is inside the repository; a replica there is an untracked tree the "
            "integrity gate trips on, and it is on the same device besides"
        )

    digests = _archive_digests(archive_dir)
    replica = target_root / archive_dir.name

    if replica.exists():
        existing = {
            str(rel): fp_archive.sha256_path(replica / rel)
            for rel in fp_archive.walk_files(replica)
            if str(rel) != REPLICA_MANIFEST
        }
        missing = sorted(set(digests) - set(existing))
        added = sorted(set(existing) - set(digests))
        changed = sorted(p for p in set(digests) & set(existing) if digests[p] != existing[p])
        if missing or added or changed:
            raise ReplicationRefused(
                f"{replica} already exists and does not match {archive_dir} — missing {missing[:3]}, "
                f"added {added[:3]}, changed {changed[:3]}. A replica is written once and never "
                "overwritten; this divergence is the finding, not something to reconcile"
            )
        action = "VERIFIED"
    elif verify_only:
        raise ReplicationRefused(f"{replica} does not exist yet, so there is nothing to verify")
    else:
        target_root.mkdir(parents=True, exist_ok=True)
        staging = target_root / f".{archive_dir.name}.incoming"
        if staging.exists():
            shutil.rmtree(staging)
        # Copy into a staging name and rename into place only once every byte has
        # been re-read from the device. A partially written replica that carried
        # the final name would be indistinguishable from a complete one.
        shutil.copytree(archive_dir, staging, symlinks=True)
        for rel, expected in digests.items():
            landed = staging / rel
            if not landed.is_file():
                raise ReplicationRefused(f"{rel} did not arrive on the device")
            actual = fp_archive.sha256_path(landed)
            if actual != expected:
                raise ReplicationRefused(
                    f"{rel} hashes to {actual[:12]} on the device but {expected[:12]} in the "
                    "archive; the replica is not the evidence"
                )
        staging.rename(replica)
        action = "REPLICATED"

    record = {
        "replica_version": REPLICA_VERSION,
        "action": action,
        "replicated_utc": _utc(),
        "archive_name": archive_dir.name,
        "source_archive": str(archive_dir),
        "replica_dir": str(replica),
        "role": source_manifest.get("role"),
        "cohort_id": source_manifest.get("cohort_id"),
        "file_count": len(digests),
        "files": dict(sorted(digests.items())),
        "evidence": source_manifest.get("evidence"),
        "device": device_detail,
        "same_host_second_device": SAME_HOST_SECOND_DEVICE,
        "host_loss_redundancy": HOST_LOSS_REDUNDANCY,
        "durability_claim": CLAIM,
        "durability_disclaimer": DISCLAIMER,
        "append_only_enforced_by": (
            "refusal, not filesystem attributes: the device is NTFS and carries no POSIX "
            "immutability. A replica is written once, re-verified on repeat runs, and a "
            "divergent archive is refused rather than reconciled."
        ),
        "real_money_authorized": False,
    }
    if action == "REPLICATED":
        (replica / REPLICA_MANIFEST).write_text(json.dumps(record, indent=2) + "\n",
                                                encoding="utf-8")
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("archive", help="a sealed archive directory under artifacts/")
    parser.add_argument("--device-root", default=None,
                        help="override the discovered mount point (testing)")
    parser.add_argument("--verify-only", action="store_true",
                        help="re-read an existing replica and write nothing")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        record = replicate(
            Path(args.archive),
            device_root=Path(args.device_root) if args.device_root else None,
            verify_only=args.verify_only,
        )
    except ReplicationRefused as exc:
        message = str(exc)
        print(f"SECOND_DEVICE_REPLICATION_REFUSED: {message}", file=sys.stderr)
        return 3 if "no healthy second physical device" in message else 2
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        print(f"SECOND_DEVICE_REPLICATION_REFUSED: {exc}", file=sys.stderr)
        return 2

    if args.json:
        sys.stdout.write(json.dumps(record, indent=2) + "\n")
    else:
        print(f"{record['action']} {record['archive_name']} -> {record['replica_dir']}")
        print(f"  device         {record['device']['block_device']} "
              f"({record['device']['model']})")
        print(f"  files          {record['file_count']}, each re-read from the device and hashed")
        print()
        print(f"SAME_HOST_SECOND_DEVICE = {record['same_host_second_device']}")
        print(f"HOST_LOSS_REDUNDANCY = {record['host_loss_redundancy']}")
        print(f"  {record['durability_disclaimer']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
