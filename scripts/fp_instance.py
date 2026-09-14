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
    python3 scripts/fp_instance.py FP-CONTROL-2            # start-class selection
    python3 scripts/fp_instance.py FP-CONTROL-2 --stop     # stop-class selection
    python3 scripts/fp_instance.py FP-CONTROL-2 --json
"""

from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "research"))

from fp.capture import InstanceSelectionError  # noqa: E402
from fp.lane import (  # noqa: E402
    EXECUTABLE_STATUSES,
    STOPPABLE_STATUSES,
    LaneError,
    resolve_lane,
    select_row,
)

# Which statuses each caller may address. Starting a runtime and stopping one are
# different questions: a PAUSED row must never start by itself, and must always
# be stoppable, or the only way out of PAUSED is editing the registry by hand.
MODES = {"start": EXECUTABLE_STATUSES, "stop": STOPPABLE_STATUSES}


def resolve(role: str, mode: str = "start") -> dict:
    """Every value the launcher needs, from the one shared resolver.

    Nothing is reconstructed here. The launcher, the capture loop, preflight and
    the compose guard all ask the same module the same question, so they cannot
    disagree about where this instance writes.
    """
    try:
        lane = resolve_lane(role, allowed_statuses=MODES[mode])
    except LaneError as exc:
        raise InstanceSelectionError(str(exc)) from exc
    except KeyError as exc:  # pragma: no cover - guarded by the CLI
        raise InstanceSelectionError(f"unknown mode {mode!r}") from exc
    row = select_row(role)
    return {
        "role": lane.role,
        "instance_dir": lane.instance_dir,
        "bot_name": lane.bot_name,
        "status": lane.status,
        "t0_utc": row.get("t0_utc"),
        "cohort_id": row.get("cohort_id"),
        "evidence_dir": str(lane.container_evidence_dir),
        "db_path": str(lane.container_db_path),
        "log_path": str(lane.container_log_path),
        "host_instance_dir": str(lane.host_instance_dir),
        "host_evidence_dir": str(lane.host_evidence_dir),
    }


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    mode = "start"
    flags = [a for a in args[1:] if a.startswith("--")]
    for flag in list(flags):
        if flag in ("--start", "--stop"):
            mode = flag.lstrip("-")
            args = [a for a in args if a != flag]
    if not 1 <= len(args) <= 2 or (len(args) == 2 and args[1] != "--json"):
        print("usage: fp_instance.py ROLE [--start|--stop] [--json]", file=sys.stderr)
        return 2
    try:
        resolved = resolve(args[0], mode)
    except InstanceSelectionError as exc:
        print(f"FP_SELECTION_FAIL: {exc}", file=sys.stderr)
        return 3
    if len(args) == 2:
        print(json.dumps(resolved, indent=2))
        return 0
    # Every value is shell-quoted. The launchers `eval` this output, and an
    # unquoted registry string would be shell input rather than data.
    emit = {
        "FP_ROLE": resolved["role"],
        "FP_INSTANCE_DIR": resolved["instance_dir"],
        "FP_BOT_NAME": resolved["bot_name"],
        "FP_DB_PATH": resolved["db_path"] or "",
        "FP_LOG_PATH": resolved["log_path"] or "",
        "FP_EVIDENCE_DIR": resolved["evidence_dir"],
        "FP_HOST_INSTANCE_DIR": resolved["host_instance_dir"],
        "FP_HOST_EVIDENCE_DIR": resolved["host_evidence_dir"],
        "FP_T0": resolved["t0_utc"] or "T0_NOT_FROZEN",
    }
    for key, value in emit.items():
        print(f"{key}={shlex.quote(value)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
