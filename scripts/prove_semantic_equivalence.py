#!/usr/bin/env python3
"""Prove two commits run the same system, or refuse to say they do.

P2's source-commit model (contract section 5) declares ``source_commit`` = M1,
the merged main immediately before the freeze, while every record is stamped
with M2, the commit the runtime actually ran at. That is only honest if the two
are equivalent, and equivalence has to be *proved* rather than declared — the
predecessor model declared a source commit and compared it to nothing.

    scripts/prove_semantic_equivalence.py M1 M2
    scripts/prove_semantic_equivalence.py Mq HEAD --require-equivalent

Exit codes: 0 report produced; 2 not EQUIVALENT under ``--require-equivalent``.
UNPROVEN exits 2 exactly as DIFFERENT does: a question that could not be
answered has not been answered favourably.

PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for _extra in (str(REPO_ROOT / "research"), str(REPO_ROOT / "scripts")):
    if _extra not in sys.path:
        sys.path.insert(0, _extra)

from fp import lane as fp_lane  # noqa: E402
from fp import semantic_identity as si  # noqa: E402

DEFAULT_ROLE = "FP-CONTROL-2"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("left", help="a revision — typically Mq or M1")
    parser.add_argument("right", help="a revision — typically M1 or M2")
    parser.add_argument("--role", default=DEFAULT_ROLE)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("-o", "--out", default=None)
    parser.add_argument(
        "--require-equivalent",
        action="store_true",
        help="exit 2 unless the result is EQUIVALENT; UNPROVEN exits 2 as DIFFERENT does",
    )
    args = parser.parse_args(argv)

    report = si.compare(args.left, args.right, args.role)
    text = json.dumps(report, indent=2) + "\n"

    if args.out:
        # A report is not evidence and may not be written where evidence lives.
        # One mistyped path is all it takes to overwrite a hash-chained ledger
        # with a report, and reconstructing a truncated ledger is not possible.
        destination = Path(args.out).resolve()
        for declared in fp_lane.all_lane_roots():
            if destination == declared or declared in destination.parents:
                print(
                    f"EQUIVALENCE_REFUSED: {args.out} is inside the evidence lane {declared}; "
                    "a report must not be written where evidence lives",
                    file=sys.stderr,
                )
                return 2
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")

    if args.json:
        sys.stdout.write(text)
    elif not args.out:
        print(f"SEMANTIC_IDENTITY — role {report['role']}")
        print(f"  left  {report['left'].get('commit', report['left']['rev'])}")
        print(f"  right {report['right'].get('commit', report['right']['rev'])}")
        for difference in report["differences"]:
            where = difference.get("path") or difference.get("field")
            print(f"  [DIFF] {difference['kind']} {where}")
            print(f"         left  {difference['left']}")
            print(f"         right {difference['right']}")
        print()
        print(f"SEMANTIC_EQUIVALENCE = {report['result']}")
        print(f"  {report['detail']}")

    if args.require_equivalent and report["result"] != si.EQUIVALENT:
        print(
            f"SEMANTIC_EQUIVALENCE_FAILED: {report['result']} — {report['detail']}",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
