#!/usr/bin/env python3
"""P3-PLN-02: inventory every stateful file under a root and verify its recovery source.

    scripts/p3/state_inventory.py --root /home/hamza/projects/trading/trading_lab_os_final \\
        [--cold-manifest <sha256sum file> --cold-prefix projects/trading/trading_lab_os_final/] \\
        [--profile runtime|worktree|operator] [--json report.json]

See research/p3/state_inventory.py. Reads only; writes nothing but --json.
Exit codes: 0 PLN_02_STATE_INVENTORY = PASS · 1 NOT_PASS · 2 error.

PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for _extra in (str(REPO_ROOT / "research"), str(REPO_ROOT / "scripts")):
    if _extra not in sys.path:
        sys.path.insert(0, _extra)

from p3 import state_inventory as inv  # noqa: E402
import publish_evidence_digest  # noqa: E402

CLASSES = REPO_ROOT / "research" / "p3" / "records" / "state_classes.json"
PUBLICATION = REPO_ROOT / "research" / "fp" / "records" / "evidence_digest_publication.json"
LOCK = REPO_ROOT / "research" / "datasets" / "dataset_v2.lock.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--classes", type=Path, default=CLASSES)
    parser.add_argument("--profile", default="runtime", help="runtime | worktree | operator")
    parser.add_argument("--cold-manifest", type=Path)
    parser.add_argument("--cold-prefix", default="")
    parser.add_argument("--json", type=Path)
    args = parser.parse_args(argv)
    try:
        report = inv.inventory(
            args.root, inv.load_classes(args.classes, args.profile),
            publication=json.loads(PUBLICATION.read_text(encoding="utf-8")),
            lock=json.loads(LOCK.read_text(encoding="utf-8")),
            cold_manifest=inv.load_manifest(args.cold_manifest, args.cold_prefix) if args.cold_manifest else None,
            archive_verifier=publish_evidence_digest.verify_archive,
        )
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"P3_STATE_INVENTORY_ERROR: {exc}", file=sys.stderr)
        return 2
    if args.json:
        args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"root {report['root']} · files {report['files_seen']}")
    for c in report["classes"]:
        print(f"  {c['id']:24} {c['files']:7} files {c['bytes']:>14} B  {c['recovery_kind']:15} {c['recovery']['status']}")
    print(f"  unclassified {report['unclassified']['count']} · unreadable dirs {report['unreadable_dirs']['count']}")
    print(f"COVERAGE = {report['COVERAGE']} · RECOVERY = {report['RECOVERY']}")
    print(f"PLN_02_STATE_INVENTORY = {report['PLN_02_STATE_INVENTORY']}")
    return 0 if report["PLN_02_STATE_INVENTORY"] == inv.PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
