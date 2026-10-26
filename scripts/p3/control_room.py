#!/usr/bin/env python3
"""P3-PLN-09: build the live Control Room view from verified evidence.

    scripts/p3/control_room.py build [--out /home/hamza/tlos-paper/p3-evidence/control_room/index.html]
                                     [--observation-json obs.json] [--findings-json health.json]

The frozen prototype (docs/p3/product_shape/…v0.2.5_FINAL.html, sha256 e17d50dc…) is used verbatim.
The build refuses any other digest. See research/p3/control_room.py. Read-only towards the system:
it writes only the output page (atomically) and the optional observation JSON.

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

from p3 import control_room  # noqa: E402

DEFAULT_OUT = Path("/home/hamza/tlos-paper/p3-evidence/control_room/index.html")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    bld = sub.add_parser("build")
    bld.add_argument("--out", type=Path, default=DEFAULT_OUT)
    bld.add_argument("--observation-json", type=Path)
    bld.add_argument("--findings-json", type=Path, help="reuse the findings health_check.py --json just wrote")
    args = parser.parse_args(argv)
    try:
        findings = None
        if args.findings_json:
            findings = json.loads(args.findings_json.read_text(encoding="utf-8"))["findings"]
        obs = control_room.collect(findings=findings)
        live = control_room.project(obs)
        html = control_room.build(live)
    except control_room.ControlRoomError as exc:
        print(f"CONTROL_ROOM_BUILD = REFUSED: {exc}")
        return 2
    control_room.write(html, args.out)
    if args.observation_json:
        args.observation_json.write_text(json.dumps(obs, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    dims = live["scenario"]["dims"]
    print("  " + "  ".join(f"{k}={v[0]}" for k, v in dims.items()))
    print(f"CONTROL_ROOM_BUILD = PASS · {args.out} · observed {live['observed_utc']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
