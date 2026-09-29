#!/usr/bin/env python3
"""H1-PAPER-COHORT-PACKAGE-1: static verification, launch preflight, incident append.

    python3 research/paper/h1/package/h1_paper.py verify
    python3 research/paper/h1/package/h1_paper.py preflight --lane-dir D --strategy-dir S
    python3 research/paper/h1/package/h1_paper.py incident --lane-dir D --type T --detail "..."

``verify``    proves the package is internally consistent and paper-safe. Reads
              files only.
``preflight`` checks the two launch-time host bindings. It never starts,
              stops or edits a container.
``incident``  appends one record to the cohort's hash-chained incident ledger,
              reusing research/fp/ledger.py (CANONICAL_LEDGER_V1).

Nothing here starts the paper worker. Starting it needs a separate Owner launch
authorization that names this package's PACKAGE_MANIFEST.sha256 digest.

PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import jsonschema
import yaml

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parents[3]
for _extra in (REPO_ROOT / "research", REPO_ROOT / "scripts"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

import paper_guard  # noqa: E402
from fp.ledger import Ledger  # noqa: E402

MANIFEST = PACKAGE_DIR / "PACKAGE_MANIFEST.sha256"
COHORT = PACKAGE_DIR / "cohort.json"
CONFIG = PACKAGE_DIR / "config.h1-paper.json"
COMPOSE = PACKAGE_DIR / "docker-compose.h1-paper.yml"
SCHEMA = PACKAGE_DIR / "incident.schema.json"
PAPER_TEMPLATE = REPO_ROOT / "freqtrade" / "user_data" / "config.paper.json.example"
UPSTREAM_PINS = REPO_ROOT / "research" / "external" / "upstream_pins.json"
P2_REGISTRY = REPO_ROOT / "research" / "fp" / "records" / "forward_paper_cohort_registry.json"

# Ports FP-CONTROL-3 publishes on this host (docker port, 2026-09-29).
P2_PORTS = {"8080", "3000", "9090", "9108", "5000"}
# Path fragments that identify P2 state. A mount containing any of them is a
# P2 mount, whatever else it is.
P2_PATH_MARKERS = ("fp-control", "trading_lab_os_final", "freqtrade/user_data")
STRATEGY_FILES = {"EmaCross.py": "sha256", "EmaCross.json": "params_sha256"}
MIN_FREE_BYTES = 20 * 1024**3
INCIDENT_LEDGER = Path("evidence") / "paper_incident_ledger.jsonl"
LANE_MARKER = ".h1-paper-cohort-1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest_digest() -> str:
    return sha256(MANIFEST)


def read_manifest() -> dict[str, str]:
    entries = {}
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            digest, name = line.split(maxsplit=1)
            entries[name.strip()] = digest
    return entries


def packaged_files() -> list[str]:
    return sorted(p.name for p in PACKAGE_DIR.iterdir()
                  if p.is_file() and p.name != MANIFEST.name and p.suffix != ".pyc")


def write_manifest() -> None:
    lines = ["# H1-PAPER-COHORT-PACKAGE-1 manifest: sha256 of every package file.",
             "# This file's own sha256 is the package digest a launch authorization names."]
    lines += [f"{sha256(PACKAGE_DIR / name)}  {name}" for name in packaged_files()]
    MANIFEST.write_text("\n".join(lines) + "\n", encoding="utf-8")


# -- verify ------------------------------------------------------------------


def check_manifest(errors: list[str]) -> None:
    if not MANIFEST.exists():
        errors.append("PACKAGE_MANIFEST.sha256 is missing")
        return
    listed = read_manifest()
    present = packaged_files()
    for name in sorted(set(present) - set(listed)):
        errors.append(f"manifest: {name} is in the package but not in the manifest")
    for name, digest in listed.items():
        path = PACKAGE_DIR / name
        if not path.exists():
            errors.append(f"manifest: {name} is listed but missing")
        elif sha256(path) != digest:
            errors.append(f"manifest: {name} does not match its recorded sha256")


def check_identity(cohort: dict, errors: list[str]) -> None:
    pins = json.loads(UPSTREAM_PINS.read_text(encoding="utf-8"))["sources"]["btc_strategy_lab"]
    by_path = {f["path"]: f for f in pins["files"]}
    strategy = cohort["strategy"]
    if pins["commit"] != strategy["upstream_commit"]:
        errors.append("identity: upstream commit differs from upstream_pins.json")
    if by_path[strategy["upstream_path"]]["sha256"] != strategy["sha256"]:
        errors.append("identity: strategy sha256 differs from upstream_pins.json")
    if by_path[strategy["params_path"]]["sha256"] != strategy["params_sha256"]:
        errors.append("identity: params sha256 differs from upstream_pins.json")
    if by_path["LICENSE"]["sha256"] != strategy["license"]["license_sha256"]:
        errors.append("identity: LICENSE sha256 differs from upstream_pins.json")
    if strategy["params"] != {"ema_period": 600, "exit_threshold": 2.0}:
        errors.append("identity: params are not the frozen ema_period=600, exit_threshold=2.0")
    if cohort["market"]["pairs"] != ["BTC/USDT"] or cohort["market"]["timeframe"] != "1h":
        errors.append("identity: universe is not the frozen BTC/USDT 1h")
    if cohort["t0"]["t0_utc"] is not None or cohort["t0"]["activation_utc"] is not None:
        errors.append("t0: the package must not carry a T0 or activation time")
    if cohort["real_money_authorized"] is not False:
        errors.append("cohort: real_money_authorized must be false")


def check_config(cohort: dict, errors: list[str]) -> None:
    violations = paper_guard.Violations()
    paper_guard.check_config(CONFIG, violations)
    errors.extend(f"paper_guard: {v}" for v in violations)
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    template = json.loads(PAPER_TEMPLATE.read_text(encoding="utf-8"))
    template["exchange"]["pair_whitelist"] = ["BTC/USDT"]
    template["bot_name"] = cohort["runtime_identity"]["bot_name"]
    if config != template:
        errors.append("config: differs from config.paper.json.example beyond pair_whitelist and bot_name")
    if config.get("dry_run") is not True:
        errors.append("config: dry_run is not true")
    if config["exchange"].get("key") or config["exchange"].get("secret"):
        errors.append("config: exchange key/secret must be empty")
    for field in ("dry_run_wallet", "stake_amount", "max_open_trades", "tradable_balance_ratio"):
        if config.get(field) != cohort["sizing"][field]:
            errors.append(f"config: {field} differs from cohort sizing")
    if config.get("fee") != cohort["fee_model"]["per_side_ratio"]:
        errors.append("config: fee differs from cohort fee model")


def check_compose(cohort: dict, errors: list[str]) -> None:
    compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    rid = cohort["runtime_identity"]
    if compose.get("name") != rid["compose_project"]:
        errors.append("compose: project name is not the cohort's own")
    if set(compose.get("services", {})) != {"freqtrade"}:
        errors.append("compose: exactly one service (freqtrade) is allowed")
        return
    svc = compose["services"]["freqtrade"]
    if svc.get("container_name") != rid["container"]:
        errors.append("compose: container name is not the cohort's own")
    if svc.get("image") != f"freqtradeorg/freqtrade@{cohort['engine']['image_digest']}":
        errors.append("compose: image is not pinned to the cohort's engine digest")
    command = " ".join(str(svc.get("command", "")).split())
    for fragment in ("trade ", "--strategy EmaCross", "--config /freqtrade/h1config/config.json",
                     f"--db-url sqlite:///{rid['container_paths']['db']}",
                     f"--logfile {rid['container_paths']['log']}"):
        if fragment not in command:
            errors.append(f"compose: command lacks {fragment.strip()!r}")
    for name in svc.get("environment", {}):
        if name.upper().startswith("FREQTRADE__EXCHANGE") or "DRY_RUN" in name.upper():
            errors.append(f"compose: environment may not override exchange or dry_run ({name})")
    ports = svc.get("ports", [])
    if ports != [rid["api_port_host"] + ":8080"]:
        errors.append(f"compose: ports must be exactly {rid['api_port_host']}:8080, found {ports}")
    for port in ports:
        host_port = str(port).split(":")[-2]
        if host_port in P2_PORTS:
            errors.append(f"compose: host port {host_port} collides with FP-CONTROL-3")
        if not str(port).startswith("127.0.0.1:"):
            errors.append(f"compose: port {port} is not loopback-only")
    volumes = svc.get("volumes", [])
    if len(volumes) != 3:
        errors.append("compose: exactly three mounts (config ro, strategy ro, lane) are allowed")
    for volume in volumes:
        source, target, *mode = str(volume).split(":")
        if any(marker in source for marker in P2_PATH_MARKERS):
            errors.append(f"compose: mount source {source} is a P2 path")
        if target in ("/freqtrade/h1config/config.json", "/freqtrade/h1strategy") and mode != ["ro"]:
            errors.append(f"compose: {target} must be mounted read-only")
    limits = {"cpus": 1.0, "cpu_shares": 256, "mem_limit": "1g", "memswap_limit": "1g",
              "pids_limit": 256, "oom_score_adj": 500}
    for key, value in limits.items():
        if svc.get(key) != value:
            errors.append(f"compose: resource limit {key} must be {value!r}")
    if "no-new-privileges:true" not in svc.get("security_opt", []):
        errors.append("compose: no-new-privileges is required")
    networks = compose.get("networks", {})
    if svc.get("networks") != ["h1paper"] or networks.get("h1paper", {}).get("name") != rid["network"]:
        errors.append("compose: the service must sit on the cohort's own network only")


def check_p2_separation(cohort: dict, errors: list[str]) -> None:
    registry = json.loads(P2_REGISTRY.read_text(encoding="utf-8"))
    rid = cohort["runtime_identity"]
    own = {cohort["paper_cohort_id"], rid["compose_project"], rid["container"], rid["bot_name"],
           rid["network"]}
    for row in registry["instances"]:
        taken = {row.get("role"), row.get("cohort_id"),
                 (row.get("runtime_identity") or {}).get("bot_name")}
        if own & {t for t in taken if t}:
            errors.append(f"p2: cohort identity collides with P2 registry row {row.get('role')}")
    for name in own:
        if any(reused.lower() in name.lower() for reused in cohort["forbidden_identity_reuse"]):
            errors.append(f"p2: identity {name} reuses a P2 identity")


def check_schema(errors: list[str]) -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    try:
        jsonschema.Draft202012Validator.check_schema(schema)
    except jsonschema.SchemaError as exc:
        errors.append(f"incident schema: {exc.message}")


def verify() -> list[str]:
    errors: list[str] = []
    check_manifest(errors)
    cohort = json.loads(COHORT.read_text(encoding="utf-8"))
    check_identity(cohort, errors)
    check_config(cohort, errors)
    check_compose(cohort, errors)
    check_p2_separation(cohort, errors)
    check_schema(errors)
    return errors


# -- preflight ---------------------------------------------------------------


def _inside_git_worktree(path: Path) -> bool:
    probe = path if path.exists() else path.parent
    while not probe.exists():
        probe = probe.parent
    result = subprocess.run(["git", "-C", str(probe), "rev-parse", "--is-inside-work-tree"],
                            capture_output=True, text=True)
    return result.returncode == 0 and result.stdout.strip() == "true"


def preflight(lane_dir: Path, strategy_dir: Path) -> list[str]:
    """Launch-time checks of the two host bindings. Starts nothing."""
    errors = verify()
    cohort = json.loads(COHORT.read_text(encoding="utf-8"))
    lane_dir, strategy_dir = lane_dir.resolve(), strategy_dir.resolve()
    for label, path in (("lane", lane_dir), ("strategy", strategy_dir)):
        if any(marker in str(path) for marker in P2_PATH_MARKERS):
            errors.append(f"preflight: {label} dir {path} is a P2 path")
        if _inside_git_worktree(path):
            errors.append(f"preflight: {label} dir {path} is inside a git worktree")
    if lane_dir == strategy_dir or strategy_dir in lane_dir.parents or lane_dir in strategy_dir.parents:
        errors.append("preflight: lane and strategy dirs must be disjoint")
    if lane_dir.exists() and any(p.name != LANE_MARKER for p in lane_dir.iterdir()):
        errors.append(f"preflight: lane dir {lane_dir} is not empty; a cohort never reuses a lane")
    expected = {name: cohort["strategy"][field] for name, field in STRATEGY_FILES.items()}
    expected["LICENSE"] = cohort["strategy"]["license"]["license_sha256"]
    present = {p.name for p in strategy_dir.iterdir()} if strategy_dir.is_dir() else set()
    if present != set(expected):
        errors.append(f"preflight: strategy dir must hold exactly {sorted(expected)}, found {sorted(present)}")
    for name, digest in expected.items():
        if name in present and sha256(strategy_dir / name) != digest:
            errors.append(f"preflight: {name} does not match its pinned sha256")
    probe = lane_dir if lane_dir.exists() else lane_dir.parent
    while not probe.exists():
        probe = probe.parent
    if shutil.disk_usage(probe).free < MIN_FREE_BYTES:
        errors.append("preflight: less than 20 GB free on the lane's filesystem")
    return errors


# -- incident ----------------------------------------------------------------


def append_incident(lane_dir: Path, incident_type: str, detail: str, **fields) -> dict:
    """Append one validated incident. The restart counter is derived, never supplied."""
    path = lane_dir / INCIDENT_LEDGER
    path.parent.mkdir(parents=True, exist_ok=True)
    ledger = Ledger(path, "incident")
    prior = [r.payload for r in ledger.records()] if path.exists() else []
    problems = ledger.verify() if path.exists() else []
    if problems:
        raise SystemExit(f"incident ledger chain is broken: {problems}")
    if incident_type == "COHORT_START" and prior:
        raise SystemExit("COHORT_START may only be the first record; a cohort starts once")
    if incident_type != "COHORT_START" and not prior:
        raise SystemExit("the first record of a cohort must be COHORT_START")
    if prior and prior[-1]["incident_type"] == "COHORT_TERMINAL":
        raise SystemExit("the cohort is terminal; nothing may follow COHORT_TERMINAL")
    counter = prior[-1]["restart_counter"] if prior else 0
    if incident_type == "PROCESS_RESTART":
        counter += 1
    payload = {"cohort_id": "H1-PAPER-COHORT-1", "package_manifest_sha256": manifest_digest(),
               "incident_type": incident_type, "restart_counter": counter, "detail": detail}
    payload.update({k: v for k, v in fields.items() if v is not None})
    jsonschema.validate(payload, json.loads(SCHEMA.read_text(encoding="utf-8")))
    return ledger.append(payload).as_dict()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("verify")
    sub.add_parser("write-manifest")
    pre = sub.add_parser("preflight")
    pre.add_argument("--lane-dir", required=True, type=Path)
    pre.add_argument("--strategy-dir", required=True, type=Path)
    inc = sub.add_parser("incident")
    inc.add_argument("--lane-dir", required=True, type=Path)
    inc.add_argument("--type", required=True, dest="incident_type")
    inc.add_argument("--detail", required=True)
    inc.add_argument("--missed-candles", type=int, default=None)
    args = parser.parse_args(argv)

    if args.command == "write-manifest":
        write_manifest()
        print(f"PACKAGE_MANIFEST_SHA256 = {manifest_digest()}")
        return 0
    if args.command == "incident":
        record = append_incident(args.lane_dir, args.incident_type, args.detail,
                                 missed_candles_1h=args.missed_candles)
        print(json.dumps(record, indent=2))
        return 0
    errors = verify() if args.command == "verify" else preflight(args.lane_dir, args.strategy_dir)
    gate = "H1_PAPER_PACKAGE_VERIFY" if args.command == "verify" else "H1_PAPER_PREFLIGHT"
    for error in errors:
        print(f"  - {error}", file=sys.stderr)
    print(f"{gate} = {'FAIL' if errors else 'PASS'}")
    print(f"PACKAGE_MANIFEST_SHA256 = {manifest_digest() if MANIFEST.exists() else 'MISSING'}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
