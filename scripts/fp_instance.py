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
import shlex
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
    for field in ("db_path", "log_path"):
        declared = identity.get(field)
        if not declared:
            raise InstanceSelectionError(f"{role} declares no {field}")
        # The launcher consumes the declared paths verbatim; reconstructing them
        # from the directory name would let the registry and the runtime disagree
        # about where the database lives.
        if not declared.startswith(f"/freqtrade/user_data/{instance_dir}/"):
            raise InstanceSelectionError(
                f"{role}.{field} ({declared}) is not inside its own lane /freqtrade/user_data/{instance_dir}/"
            )
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
    # Every value is shell-quoted. The launchers `eval` this output, and an
    # unquoted registry string would be shell input rather than data.
    emit = {
        "FP_ROLE": resolved["role"],
        "FP_INSTANCE_DIR": resolved["instance_dir"],
        "FP_BOT_NAME": resolved["bot_name"],
        "FP_DB_PATH": resolved["db_path"] or "",
        "FP_LOG_PATH": resolved["log_path"] or "",
        "FP_EVIDENCE_DIR": resolved["evidence_dir"],
        "FP_T0": resolved["t0_utc"] or "T0_NOT_FROZEN",
    }
    for key, value in emit.items():
        print(f"{key}={shlex.quote(value)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
