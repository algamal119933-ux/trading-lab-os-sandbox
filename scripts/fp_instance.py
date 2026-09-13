#!/usr/bin/env python3
"""Resolve which FP control instance a runtime may run as — or fail closed.

The launchers need three strings before they can render a stack: the role, the
instance directory and the bot name. Deriving them in shell would mean a second
place that decides which instance is runnable, and the moment those two places
disagree the runtime writes somewhere the registry did not authorise. So the
decision stays in ``research/fp/capture.py`` and this script only prints it.

A CLOSED instance, an unknown role and a duplicated role are all refused by the
selector, so no launcher can start into a terminated cohort's paths.

Usage:
    python3 scripts/fp_instance.py FP-CONTROL-2            # shell-eval lines
    python3 scripts/fp_instance.py FP-CONTROL-2 --json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "research"))

from fp.capture import InstanceSelectionError, select_instance  # noqa: E402


def resolve(role: str) -> dict:
    instance = select_instance(role)
    identity = instance["runtime_identity"]
    evidence_dir = identity.get("evidence_dir") or ""
    # ".../<instance_dir>/evidence" -> "<instance_dir>"
    instance_dir = evidence_dir.rsplit("/", 2)[-2] if "/" in evidence_dir else ""
    if not instance_dir or not identity.get("bot_name"):
        raise InstanceSelectionError(f"{role} has no bound instance directory or bot name")
    return {
        "role": role,
        "instance_dir": instance_dir,
        "bot_name": identity["bot_name"],
        "status": instance.get("status"),
        "t0_utc": instance.get("t0_utc"),
        "cohort_id": instance.get("cohort_id"),
        "evidence_dir": evidence_dir,
        "db_path": identity.get("db_path"),
        "log_path": identity.get("log_path"),
    }


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not 1 <= len(args) <= 2 or (len(args) == 2 and args[1] != "--json"):
        print("usage: fp_instance.py ROLE [--json]", file=sys.stderr)
        return 2
    try:
        resolved = resolve(args[0])
    except InstanceSelectionError as exc:
        print(f"FP_SELECTION_FAIL: {exc}", file=sys.stderr)
        return 3
    if len(args) == 2:
        print(json.dumps(resolved, indent=2))
        return 0
    print(f"FP_ROLE={resolved['role']}")
    print(f"FP_INSTANCE_DIR={resolved['instance_dir']}")
    print(f"FP_BOT_NAME={resolved['bot_name']}")
    print(f"FP_T0={resolved['t0_utc'] or 'T0_NOT_FROZEN'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
