#!/usr/bin/env python3
"""Tier-2 digest publication: commit what was sealed, never what it contained.

    scripts/publish_evidence_digest.py artifacts/fp-control-2-20260916T120000Z
    scripts/publish_evidence_digest.py <archive> --verify-only

Tier 1 puts a lane out of container reach on this host. It cannot survive the
host. Tier 2 does not fix that — nothing on one machine can — but it changes
what a loss *means*: with ledger tips, a daily pack digest, record counts and a
per-file sha256 tracked in Git, surviving evidence is provably the evidence that
was sealed, and a loss and its exact extent are provable rather than
reconstructed.

What it may not claim is that anything is recoverable. A digest is not a backup.
It converts an unbounded loss into a bounded, documented one, and the record it
writes says so in its own text so a later reader cannot acquire a stronger
belief from the file than the contract grants.

No evidence CONTENT leaves the host: names and hashes only.

Every archive is re-read from disk and rehashed before publication. A digest
published from the manifest alone would record what was believed at seal time,
not what is on the disk now — and the difference between those two is the only
thing this tier exists to detect.

Exit codes: 0 published (or verified, under ``--verify-only``); 2 refused.

PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for _extra in (str(REPO_ROOT / "research"), str(REPO_ROOT / "scripts")):
    if _extra not in sys.path:
        sys.path.insert(0, _extra)

from fp import archive as fp_archive  # noqa: E402

PUBLICATION = REPO_ROOT / "research" / "fp" / "records" / "evidence_digest_publication.json"


class PublishError(Exception):
    pass


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def verify_archive(archive_dir: Path) -> dict:
    """Re-read every file in the archive and compare it to the sealed manifest.

    Returns the entry that would be published. Raises on any divergence: an
    archive that no longer matches its own manifest is the event this tier is
    built to make visible, and publishing it anyway would bury it.
    """
    archive_dir = Path(archive_dir).resolve()
    manifest_path = archive_dir / fp_archive.ARCHIVE_MANIFEST
    if not manifest_path.is_file():
        raise PublishError(
            f"{archive_dir} carries no {fp_archive.ARCHIVE_MANIFEST}; it was not sealed by "
            "scripts/archive_fp_lane.py and its contents cannot be attributed to a lane"
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    declared = manifest.get("files") or {}
    on_disk = {
        str(rel): fp_archive.sha256_path(archive_dir / rel)
        for rel in fp_archive.walk_files(archive_dir)
        if str(rel) != fp_archive.ARCHIVE_MANIFEST
    }
    missing = sorted(set(declared) - set(on_disk))
    added = sorted(set(on_disk) - set(declared))
    changed = sorted(p for p in set(declared) & set(on_disk) if declared[p] != on_disk[p])
    if missing or added or changed:
        raise PublishError(
            f"{archive_dir} no longer matches its sealed manifest — "
            f"missing {missing[:3]}, added {added[:3]}, changed {changed[:3]}"
        )

    return {
        "archive_name": archive_dir.name,
        "role": manifest["role"],
        "cohort_id": manifest.get("cohort_id"),
        "lane_status_at_archival": manifest.get("lane_status_at_archival"),
        "reason": manifest.get("reason", ""),
        "archived_utc": manifest["archived_utc"],
        "verified_utc": _utc(),
        "source_lane": manifest["source_lane"],
        "file_count": manifest["file_count"],
        "total_bytes": manifest["total_bytes"],
        "files": dict(sorted(on_disk.items())),
        "evidence": manifest["evidence"],
    }


def publish(entry: dict, publication_path: Path | None = None) -> dict:
    """Add or re-verify one archive in the tracked publication.

    An archive already published may be re-verified — that is the point of a
    digest — but its digests may never be *changed*. A published hash that can
    be edited in place proves nothing, because the edit is exactly what a
    tampered archive would need.
    """
    path = Path(publication_path or PUBLICATION)
    document = json.loads(path.read_text(encoding="utf-8"))
    archives = document.setdefault("archives", [])

    existing = next(
        (item for item in archives if item["archive_name"] == entry["archive_name"]), None
    )
    if existing is not None:
        immutable = ("role", "cohort_id", "archived_utc", "source_lane", "file_count", "files", "evidence")
        divergent = [field for field in immutable if existing.get(field) != entry.get(field)]
        if divergent:
            raise PublishError(
                f"{entry['archive_name']} is already published with different {divergent}; a "
                "published digest is never rewritten — the divergence IS the finding"
            )
        existing["verified_utc"] = entry["verified_utc"]
    else:
        archives.append(entry)
        archives.sort(key=lambda item: (item["archived_utc"], item["archive_name"]))

    document["published_utc"] = _utc()
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return document


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("archive", help="a sealed archive directory under artifacts/")
    parser.add_argument("--publication", default=None)
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="rehash the archive against its manifest and change no tracked file",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        entry = verify_archive(Path(args.archive))
    except (PublishError, OSError, KeyError, json.JSONDecodeError) as exc:
        print(f"DIGEST_PUBLICATION_REFUSED: {exc}", file=sys.stderr)
        return 2

    if args.verify_only:
        print(f"ARCHIVE_VERIFIED {entry['archive_name']} — {entry['file_count']} file(s) rehashed")
        print(f"  daily pack digest {entry['evidence'].get('daily_pack_digest')}")
        return 0

    try:
        document = publish(entry, Path(args.publication) if args.publication else None)
    except PublishError as exc:
        print(f"DIGEST_PUBLICATION_REFUSED: {exc}", file=sys.stderr)
        return 2

    if args.json:
        sys.stdout.write(json.dumps(document, indent=2) + "\n")
    else:
        print(f"PUBLISHED {entry['archive_name']} ({entry['file_count']} file digests)")
        print(f"  role           {entry['role']}  cohort {entry['cohort_id']}")
        print(f"  pack digest    {entry['evidence'].get('daily_pack_digest')}")
        print(f"  archives now   {len(document['archives'])}")
        print()
        print("DURABILITY_TIER = 2")
        print(f"  {document['tier_2_disclaimer']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
