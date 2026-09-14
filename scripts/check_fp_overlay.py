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
* the control's own database, log and evidence paths are in use, exactly;
* every writable mount is checked on BOTH sides — the container target *and*
  the host source behind it, canonicalised through realpath. Checking targets
  alone let a closed instance's host directory be mounted at the successor's
  container target, which would have written the successor's evidence straight
  into the historical lane;
* every identity-bearing argument — the capture service's --role and
  --evidence-dir, and the engine's --strategy, --db-url, --logfile and --config —
  is parsed and compared exactly, never by substring;
* writable mounts are checked on EVERY rendered service, including services this
  file does not name and services added later;
* the declared bot name is required, not merely "not contradicted";
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
STRATEGY_NAME = "BaselineEmaRegimeV1"
USER_DATA_HOST = (REGISTRY_PATH.parent.parent.parent.parent / "freqtrade" / "user_data").resolve()


def _lane_module():
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "research"))
    from fp import lane as fp_lane  # noqa: PLC0415

    return fp_lane


def parse_args(command) -> dict[str, str]:
    """``--key=value`` and ``--key value`` into exact values.

    Substring matching is what let ``--role=FP-CONTROL-2-evil`` satisfy a check
    for ``--role=FP-CONTROL-2``. Parsing gives the value itself, so equality can
    be required.
    """
    tokens = list(command) if isinstance(command, list) else str(command).split()
    parsed: dict[str, str] = {}
    index = 0
    while index < len(tokens):
        token = str(tokens[index])
        if token.startswith("--"):
            if "=" in token:
                key, value = token.split("=", 1)
                parsed[key] = value
            elif index + 1 < len(tokens) and not str(tokens[index + 1]).startswith("--"):
                parsed[token] = str(tokens[index + 1])
                index += 1
            else:
                parsed[token] = ""
        index += 1
    return parsed


def mount_pairs(service: dict) -> list[tuple[str, str, bool, str]]:
    """(host source, container target, read_only, kind) for every declared mount.

    ``kind`` separates a bind — which names a real host directory and can
    therefore alias an instance lane — from a named volume, which cannot.
    """
    pairs: list[tuple[str, str, bool, str]] = []
    for volume in service.get("volumes") or []:
        if isinstance(volume, dict):
            pairs.append((str(volume.get("source") or ""), str(volume.get("target") or ""),
                          bool(volume.get("read_only")), str(volume.get("type") or "bind")))
        else:
            text = str(volume)
            parts = text.split(":")
            source = parts[0] if parts else ""
            target = parts[1] if len(parts) > 1 else ""
            kind = "bind" if source.startswith((".", "/", "~")) else "volume"
            pairs.append((source, target, text.endswith(":ro"), kind))
    return pairs


def check(rendered: dict, role: str) -> list[str]:
    """``instance_dir`` is the directory of the instance the launcher selected.

    Checking the rendered stack against *that* instance rather than a constant is
    what stops a successor runtime from being rendered onto a closed cohort's
    paths by a stale variable.
    """
    problems: list[str] = []
    fp_lane = _lane_module()
    try:
        lane = fp_lane.resolve_lane(role, allowed_statuses=fp_lane.EXECUTABLE_STATUSES)
    except Exception as exc:  # noqa: BLE001 — any selection failure is a refusal
        return [f"the overlay names an unusable instance {role}: {exc}"]
    others = fp_lane.other_lanes(role)

    identity = {
        "db_path": str(lane.container_db_path),
        "log_path": str(lane.container_log_path),
        "evidence_dir": str(lane.container_evidence_dir),
        "bot_name": lane.bot_name,
    }
    evidence_dir = identity["evidence_dir"]
    instance_dir = lane.instance_dir
    # The writable boundary is the instance's own lane, which contains its
    # evidence directory, its database and its logs. Anything writable outside
    # that lane is what this guard exists to catch.
    evidence_target = str(lane.container_instance_dir)

    def writable_mount_problems(service_name: str, service: dict) -> list[str]:
        """Both sides of every writable mount, canonicalised.

        A mount is two claims: where the container will write, and which real
        host directory receives it. The second claim is the one that was never
        checked, and it is the one that decides whose evidence gets overwritten.
        """
        found: list[str] = []
        repo_root = REGISTRY_PATH.parent.parent.parent.parent
        for source, target, read_only, kind in mount_pairs(service):
            if read_only:
                continue  # shared read-only mounts are fine; they write nothing
            if kind == "volume":
                # A named volume has no host path into the project and cannot
                # alias an instance lane. Grafana's and Prometheus's own storage
                # are exactly this, and flagging them would train a reader to
                # ignore the check that matters.
                continue

            host = None
            if source:
                candidate = Path(source).expanduser()
                if not candidate.is_absolute():
                    candidate = repo_root / candidate
                # resolve() follows symlinks, so an escape lands outside the lane
                host = candidate.resolve()

            touches_lane_target = bool(target) and (
                target == "/freqtrade/user_data" or target.startswith("/freqtrade/user_data/")
            )
            touches_lane_host = host is not None and (
                host == USER_DATA_HOST or USER_DATA_HOST in host.parents
            )
            if not touches_lane_target and not touches_lane_host:
                continue  # a writable mount that cannot reach any instance lane

            # From here the mount can reach an FP lane, so it must be the
            # selected one — on both sides. Target-only checking is what let a
            # closed host lane be mounted at the successor's target.
            inside_target = target == evidence_target or target.startswith(evidence_target + "/")
            if not inside_target:
                found.append(f"{service_name} has a writable mount outside its own lane: {target}")
                continue
            if host is None:
                found.append(f"{service_name} declares a writable mount at {target} with no host source")
                continue
            if not lane.owns_host_path(host):
                found.append(
                    f"{service_name} mounts host {host} at {target}: that host path is not inside "
                    f"the selected lane {lane.host_instance_dir}"
                )
                continue
            for other in others:
                if other.owns_host_path(host):
                    found.append(
                        f"{service_name} mounts host {host} at {target}, which belongs to "
                        f"{other.role} ({other.host_instance_dir})"
                    )
        return found

    services = rendered.get("services") or {}

    freqtrade = services.get("freqtrade")
    if not freqtrade:
        return ["the rendered overlay declares no freqtrade service"]

    command = freqtrade.get("command")
    command_text = " ".join(str(c) for c in command) if isinstance(command, list) else str(command)
    # Every identity-bearing argument is parsed and compared for equality.
    # Containment checks passed BaselineEmaRegimeV1Evil and tradesv3.sqlite-evil:
    # a name that merely *contains* the right one is a different runtime.
    engine_args = parse_args(command)
    strategy = engine_args.get("--strategy")
    if strategy != STRATEGY_NAME:
        problems.append(
            f"freqtrade does not run BASELINE-1: strategy is {strategy!r}, not {STRATEGY_NAME!r}"
        )
    if "PlumbingSmokeStrategy" in command_text:
        problems.append("the smoke strategy is running under the FP control overlay")

    db_url = engine_args.get("--db-url")
    expected_db_urls = {f"sqlite:///{identity['db_path']}", f"sqlite:////{identity['db_path'].lstrip('/')}"}
    if db_url not in expected_db_urls:
        problems.append(
            f"freqtrade uses db-url {db_url!r}, not the declared database {identity['db_path']!r}"
        )
    logfile = engine_args.get("--logfile")
    if logfile != identity["log_path"]:
        problems.append(
            f"freqtrade logs to {logfile!r}, not the declared {identity['log_path']!r}"
        )
    config_arg = engine_args.get("--config")
    if config_arg != "/freqtrade/user_data/config.json":
        problems.append(f"freqtrade reads config {config_arg!r}, not the paper config")

    # Nothing else under user_data may appear in the command at all.
    expected_prefix = f"/freqtrade/user_data/{instance_dir}/"
    used = {token for token in re.findall(r"/freqtrade/user_data/[^\s'\"]+", command_text)}
    allowed = {identity["db_path"], identity["log_path"], "/freqtrade/user_data/config.json",
               f"/freqtrade/user_data/{instance_dir}"}
    stray = sorted(p for p in used if p not in allowed and not p.startswith(expected_prefix))
    if stray:
        problems.append(f"freqtrade writes outside {instance_dir}: {stray}")

    environment = freqtrade.get("environment") or {}
    bot_name = environment.get("FREQTRADE__BOT_NAME") if isinstance(environment, dict) else None
    # Required, not merely uncontradicted: an absent bot name leaves the running
    # instance unidentifiable in its own logs and database.
    if not bot_name:
        problems.append(
            f"freqtrade declares no FREQTRADE__BOT_NAME; the registry requires {identity['bot_name']!r}"
        )
    elif bot_name != identity["bot_name"]:
        problems.append(f"freqtrade runs as bot {bot_name!r}, not the declared {identity['bot_name']!r}")

    # Mount isolation is a property of the whole rendered graph. Checking only
    # the two services this file happens to name let an auxiliary service —
    # exporter, prometheus, grafana, mlflow, or anything added later — mount the
    # closed lane writable and pass. The loop below covers every service that
    # exists now and every service added afterwards.
    for service_name, service in sorted(services.items()):
        if not isinstance(service, dict):
            problems.append(f"{service_name} is not a service mapping; the render cannot be validated")
            continue
        problems.extend(writable_mount_problems(service_name, service))
    if "--dry-run false" in command_text or "--dry-run=false" in command_text:
        problems.append("a live-trading flag is present in the freqtrade command")

    capture = services.get("fp-capture")
    if not capture:
        problems.append("the rendered overlay declares no fp-capture service")
    else:
        args = parse_args(capture.get("command"))
        if args.get("--role") != role:
            problems.append(
                f"the capture service names role {args.get('--role')!r}, not the selected {role!r}"
            )
        if args.get("--evidence-dir") != evidence_dir:
            problems.append(
                f"the capture service writes {args.get('--evidence-dir')!r}, not the declared "
                f"evidence lane {evidence_dir!r}"
            )
        # The loop observes a runtime; it must never be able to edit the code it
        # runs. Lane logic cannot express this — /app/research reaches no
        # instance lane — so it is stated separately.
        for source, target, read_only, kind in mount_pairs(capture):
            if read_only or kind == "volume":
                continue
            if target.startswith("/app/"):
                problems.append(
                    f"capture loop has a writable mount of its own code: {target}"
                )

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
