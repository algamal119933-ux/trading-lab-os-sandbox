#!/usr/bin/env python3
"""Assert the FP control compose overlay cannot drift into an unsafe runtime.

The overlay decides which strategy the forward-paper control actually runs and
what the capture loop is allowed to write. Both are the kind of thing that
breaks quietly: a merge that restores the smoke strategy, or a convenience mount
that makes the repository writable from inside the capture container, would each
leave a stack that starts cleanly and produces worthless evidence.

So the rendered overlay — not the source file, which says nothing about what the
merge produced — is checked for:

* BASELINE-1 is the strategy, and the smoke strategy is absent;
* the control's own database, log and evidence paths are in use;
* the capture loop's only writable mount is the evidence lane;
* no execution endpoint appears anywhere in the rendered stack.

Usage:
    docker compose -f docker-compose.yml -f docker-compose.fp.yml config > rendered.yml
    python3 scripts/check_fp_overlay.py rendered.yml FP-CONTROL-2
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

REGISTRY_PATH = Path(__file__).resolve().parent.parent / "research/fp/records/forward_paper_cohort_registry.json"
FORBIDDEN_ENDPOINTS = ("forcebuy", "forceenter", "forcesell", "forceexit")


def declared_identity(role: str) -> dict:
    """The selected instance's declared identity, or a hard failure.

    The guard reads the registry itself rather than trusting a directory name it
    was handed: a rendered stack is only safe if it matches the instance the
    registry says may run, field for field.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "research"))
    from fp.capture import select_instance  # noqa: PLC0415

    instance = select_instance(role, json.loads(REGISTRY_PATH.read_text(encoding="utf-8")))
    return instance["runtime_identity"]


def check(rendered: dict, role: str) -> list[str]:
    """``instance_dir`` is the directory of the instance the launcher selected.

    Checking the rendered stack against *that* instance rather than a constant is
    what stops a successor runtime from being rendered onto a closed cohort's
    paths by a stale variable.
    """
    problems: list[str] = []
    try:
        identity = declared_identity(role)
    except Exception as exc:  # noqa: BLE001 — any selection failure is a refusal
        return [f"the overlay names an unusable instance {role}: {exc}"]

    evidence_dir = identity["evidence_dir"]
    instance_dir = evidence_dir.rsplit("/", 2)[-2]
    # The writable boundary is the instance's own lane, which contains its
    # evidence directory, its database and its logs. Anything writable outside
    # that lane is what this guard exists to catch.
    evidence_target = f"/freqtrade/user_data/{instance_dir}"
    services = rendered.get("services") or {}

    freqtrade = services.get("freqtrade")
    if not freqtrade:
        return ["the rendered overlay declares no freqtrade service"]

    command = freqtrade.get("command")
    command_text = " ".join(command) if isinstance(command, list) else str(command)
    if "BaselineEmaRegimeV1" not in command_text:
        problems.append(f"freqtrade does not run BASELINE-1: {command_text}")
    if "PlumbingSmokeStrategy" in command_text:
        problems.append("the smoke strategy is running under the FP control overlay")
    # Exact path components, not a substring: "fp-control-2" is a substring of
    # "fp-control-2-evil", so a drifted lane would have passed a containment test.
    expected_prefix = f"/freqtrade/user_data/{instance_dir}/"
    used = {token for token in re.findall(r"/freqtrade/user_data/[^\s'\"]+", command_text)}
    allowed = {identity["db_path"], identity["log_path"], "/freqtrade/user_data/config.json",
               f"/freqtrade/user_data/{instance_dir}"}
    stray = sorted(p for p in used if p not in allowed and not p.startswith(expected_prefix))
    if stray:
        problems.append(f"freqtrade writes outside {instance_dir}: {stray}")
    # The declared paths must appear exactly, not merely something under the lane.
    for field in ("db_path", "log_path"):
        if identity[field] not in command_text:
            problems.append(f"freqtrade does not use the declared {field} {identity[field]}: {command_text}")

    environment = freqtrade.get("environment") or {}
    bot_name = environment.get("FREQTRADE__BOT_NAME") if isinstance(environment, dict) else None
    if bot_name is not None and bot_name != identity["bot_name"]:
        problems.append(f"freqtrade runs as bot {bot_name!r}, not the declared {identity['bot_name']!r}")

    # Every writable mount on freqtrade must be the selected lane.
    for volume in freqtrade.get("volumes") or []:
        target = volume.get("target") if isinstance(volume, dict) else str(volume).split(":")[1:2]
        read_only = volume.get("read_only") if isinstance(volume, dict) else ":ro" in str(volume)
        target_text = target if isinstance(target, str) else (target[0] if target else "")
        inside = target_text == f"/freqtrade/user_data/{instance_dir}" or target_text.startswith(expected_prefix)
        if not read_only and target_text.startswith("/freqtrade/user_data") and not inside:
            problems.append(f"freqtrade mounts {target_text} writable, outside its own lane")
    if "--dry-run false" in command_text or "--dry-run=false" in command_text:
        problems.append("a live-trading flag is present in the freqtrade command")

    capture = services.get("fp-capture")
    if not capture:
        problems.append("the rendered overlay declares no fp-capture service")
    else:
        capture_command = capture.get("command")
        capture_text = " ".join(capture_command) if isinstance(capture_command, list) else str(capture_command)
        if f"--role={role}" not in capture_text:
            problems.append(f"the capture service does not name the selected instance: {capture_text}")
        if f"--evidence-dir={evidence_dir}" not in capture_text:
            problems.append(
                f"the capture service does not write the declared evidence lane {identity['evidence_dir']}"
            )
        for volume in capture.get("volumes") or []:
            target = volume.get("target") if isinstance(volume, dict) else str(volume)
            read_only = volume.get("read_only") if isinstance(volume, dict) else ":ro" in str(volume)
            target_text = str(target)
            inside = target_text == evidence_target or target_text.startswith(evidence_target + "/")
            if not read_only and not inside:
                problems.append(f"capture loop has a writable mount outside the evidence lane: {target}")

    text = yaml.dump(rendered)
    for endpoint in FORBIDDEN_ENDPOINTS:
        if endpoint in text:
            problems.append(f"an execution endpoint appears in the rendered stack: {endpoint}")

    # Exchange credentials specifically. The stack legitimately passes local
    # REST-API secrets (FREQTRADE__API_SERVER__*) between its own services, so a
    # blanket search for "SECRET" would flag the healthy case and train whoever
    # reads this to ignore it.
    exchange_tokens = ("EXCHANGE", "BINANCE", "CCXT")
    for name, service in services.items():
        environment = service.get("environment") or {}
        pairs = environment.items() if isinstance(environment, dict) else (
            (item.split("=", 1)[0], item.split("=", 1)[-1]) for item in environment
        )
        for key, _ in pairs:
            upper = str(key).upper()
            if any(token in upper for token in exchange_tokens) and any(
                secret in upper for secret in ("KEY", "SECRET", "PASSWORD", "TOKEN", "UID")
            ):
                problems.append(f"{name} receives what looks like an exchange credential: {key}")

    return problems


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 2:
        print("usage: check_fp_overlay.py RENDERED_COMPOSE_YAML FP-CONTROL-ROLE", file=sys.stderr)
        print("  the role is required: there is no safe default once a cohort has closed", file=sys.stderr)
        return 2

    rendered = yaml.safe_load(Path(args[0]).read_text(encoding="utf-8"))
    problems = check(rendered, args[1])
    if problems:
        for problem in problems:
            print(f"FP_OVERLAY_FAIL: {problem}", file=sys.stderr)
        print(f"FP_OVERLAY_FAIL: {len(problems)} problem(s)", file=sys.stderr)
        return 1

    print("FP_OVERLAY_PASS: BASELINE-1 on isolated paths, evidence-only writable mount, no execution path")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
