#!/usr/bin/env python3
"""Assert the FP-CONTROL-1 compose overlay cannot drift into an unsafe runtime.

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
    python3 scripts/check_fp_overlay.py rendered.yml
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

EVIDENCE_TARGET = "/freqtrade/user_data/fp-control-1"
FORBIDDEN_ENDPOINTS = ("forcebuy", "forceenter", "forcesell", "forceexit")


def check(rendered: dict) -> list[str]:
    problems: list[str] = []
    services = rendered.get("services") or {}

    freqtrade = services.get("freqtrade")
    if not freqtrade:
        return ["the rendered overlay declares no freqtrade service"]

    command = freqtrade.get("command")
    command_text = " ".join(command) if isinstance(command, list) else str(command)
    if "BaselineEmaRegimeV1" not in command_text:
        problems.append(f"freqtrade does not run BASELINE-1: {command_text}")
    if "PlumbingSmokeStrategy" in command_text:
        problems.append("the smoke strategy is running under the FP-CONTROL-1 overlay")
    if "fp-control-1" not in command_text:
        problems.append(f"freqtrade is not using the control's isolated paths: {command_text}")
    if "--dry-run false" in command_text or "--dry-run=false" in command_text:
        problems.append("a live-trading flag is present in the freqtrade command")

    capture = services.get("fp-capture")
    if not capture:
        problems.append("the rendered overlay declares no fp-capture service")
    else:
        for volume in capture.get("volumes") or []:
            target = volume.get("target") if isinstance(volume, dict) else str(volume)
            read_only = volume.get("read_only") if isinstance(volume, dict) else ":ro" in str(volume)
            if not read_only and not str(target).startswith(EVIDENCE_TARGET):
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
    if len(args) != 1:
        print("usage: check_fp_overlay.py RENDERED_COMPOSE_YAML", file=sys.stderr)
        return 2

    rendered = yaml.safe_load(Path(args[0]).read_text(encoding="utf-8"))
    problems = check(rendered)
    if problems:
        for problem in problems:
            print(f"FP_OVERLAY_FAIL: {problem}", file=sys.stderr)
        print(f"FP_OVERLAY_FAIL: {len(problems)} problem(s)", file=sys.stderr)
        return 1

    print("FP_OVERLAY_PASS: BASELINE-1 on isolated paths, evidence-only writable mount, no execution path")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
