#!/usr/bin/env python3
"""P3-PLN-05: seal a verified backup set, push it to an independent target, and open it in a restore drill.

    scripts/p3/offsite.py --seal --set <store>/<stamp> --out-root <store>-sealed \
        --recipient <40-hex fingerprint> --gnupghome ~/.config/tlos-p3/offsite-gnupg
    scripts/p3/offsite.py --set <store>-sealed/<stamp> --dest tlos-offsite:/srv/tlos-offsite
    scripts/p3/offsite.py --open --sealed <scratch>/sealed/<stamp> --scratch <scratch>/open --gnupghome <drill keyring>
    scripts/p3/offsite.py --set <set> --dest /path/on/another/device      (local path: NOT host-loss redundancy)

Only a sealed set may go to a remote destination (PLN_05_DESTINATION_DECISIONS.md §8). Sealing refuses when the
secret key is in the keyring it uses. Append-only: an existing copy is re-verified, never overwritten.
Exit codes: 0 PASS · 1 FAIL · 2 error.
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

from p3 import backup, offsite  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--seal", action="store_true", help="encrypt --set into --out-root/<set name>")
    mode.add_argument("--open", action="store_true", help="decrypt --sealed into --scratch and verify it")
    parser.add_argument("--set", type=Path, dest="set_dir")
    parser.add_argument("--dest")
    parser.add_argument("--out-root", type=Path)
    parser.add_argument("--recipient")
    parser.add_argument("--gnupghome", type=Path)
    parser.add_argument("--sealed", type=Path)
    parser.add_argument("--scratch", type=Path)
    args = parser.parse_args(argv)
    needed = (("set_dir", "out_root", "recipient", "gnupghome") if args.seal
              else ("sealed", "scratch", "gnupghome") if args.open else ("set_dir", "dest"))
    missing = [n for n in needed if getattr(args, n) is None]
    if missing:
        parser.error("missing: " + ", ".join("--" + n.replace("_dir", "").replace("_", "-") for n in missing))
    try:
        if args.seal:
            report = offsite.seal(args.set_dir, args.out_root, args.recipient, args.gnupghome)
            ok = report["status"] == "PASS"
        elif args.open:
            report = offsite.open_sealed(args.sealed, args.scratch, args.gnupghome)
            ok = report["status"] == "PASS"
        else:
            report = offsite.push(args.set_dir, args.dest)
            ok = report["destination_verify"] == "PASS"
    except (offsite.OffsiteError, backup.BackupError, OSError, json.JSONDecodeError) as exc:
        print(f"P3_OFFSITE_ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
