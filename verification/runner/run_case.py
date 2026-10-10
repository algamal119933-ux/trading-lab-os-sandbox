#!/usr/bin/env python3
"""Minimum isolated runner for one Freqtrade Strategy Verification case.

    python3 verification/runner/run_case.py --case CASE_DIR --data-dir DATA --out-dir OUT           # plan only
    python3 verification/runner/run_case.py --case CASE_DIR --data-dir DATA --out-dir OUT --execute

The case directory, the market data and the output all live OUTSIDE this
repository, on a machine that is neither the P2 host nor a cloud executor. The
runner checks, in order, and stops at the first failure:

    1. location   not the cloud executor, not the P2 host, no path inside the repo
    2. identity   every file the case names hashes to the sha256 the case pins
    3. safety     scripts/paper_guard.py (unchanged) passes the effective config
                  the engine will read; the strategy declares no shorts
    4. isolation  one container from the pinned engine digest, --network none,
                  read-only root, no capabilities, every input mounted read-only

Freqtrade loads the exchange's market list before a backtest. Inside the
container that list comes from the case's pinned exchangeInfo snapshot, served
on loopback by entrypoint.sh; the engine is used as published.

Exit codes: 0 planned or executed cleanly · 2 refused · other: the engine's.

PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
ENGINE = json.loads((HERE / "engine.json").read_text(encoding="utf-8"))
IMAGE = f"{ENGINE['image']}@{ENGINE['index_digest']}"
STUB_PORT = 18080
PAPER_EXAMPLE = REPO_ROOT / "freqtrade" / "user_data" / "config.paper.json.example"
P2_CONTAINER_PREFIX = "tradinglab-"
CASE_KEYS = ("case_id", "strategy_class", "strategy_file", "strategy_sha256", "params_file", "params_sha256",
             "config_file", "config_sha256", "markets_file", "markets_sha256", "timeframe", "timerange", "fee")
_SHORTS = re.compile(r"can_short\s*[:=]\s*True")

_spec = importlib.util.spec_from_file_location("paper_guard_as_is", REPO_ROOT / "scripts" / "paper_guard.py")
paper_guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(paper_guard)


class Refused(Exception):
    """A check failed. The case does not run."""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def running_containers() -> list[str]:
    try:
        out = subprocess.run(["docker", "ps", "--format", "{{.Names}}"], capture_output=True, text=True,
                             check=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        raise Refused(f"cannot list containers to rule out the P2 host: {exc}") from exc
    return [line.strip() for line in out.splitlines() if line.strip()]


def check_location(paths: list[Path], containers: list[str], env: dict, execute: bool) -> None:
    if execute and env.get("CLAUDE_CODE_REMOTE"):
        raise Refused("customer cases never run inside the cloud executor")
    p2 = [n for n in containers if n.startswith(P2_CONTAINER_PREFIX)]
    if p2:
        raise Refused(f"this looks like the P2 host (running: {', '.join(sorted(p2))})")
    for path in paths:
        resolved = path.resolve()
        if resolved == REPO_ROOT or REPO_ROOT in resolved.parents:
            raise Refused(f"{path} is inside the repository; case inputs and outputs stay outside it")


def load_case(case_dir: Path) -> dict:
    case = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))
    missing = [k for k in CASE_KEYS if k not in case]
    if missing:
        raise Refused(f"case.json is missing {missing}")
    pins = [("strategy_file", "strategy_sha256"), ("config_file", "config_sha256"),
            ("markets_file", "markets_sha256")]
    if case["params_file"] is not None:
        pins.append(("params_file", "params_sha256"))
    for file_key, sha_key in pins:
        rel = Path(case[file_key])
        if rel.is_absolute() or ".." in rel.parts:
            raise Refused(f"{file_key} must be a relative path inside the case directory")
        path = case_dir / rel
        if not path.is_file():
            raise Refused(f"{case[file_key]} does not exist")
        if sha256(path) != case[sha_key]:
            raise Refused(f"{case[file_key]} does not match its pinned sha256")
    if Path(case["strategy_file"]).parent != Path("strategy"):
        raise Refused("strategy_file must live in the case's strategy/ directory")
    if case["markets_file"] != "exchangeInfo.json":
        raise Refused("markets_file must be exchangeInfo.json at the case root")
    return case


def guard(config: Path) -> None:
    violations = paper_guard.Violations()
    paper_guard.check_config(config, violations)
    if violations:
        raise Refused(f"paper guard: {'; '.join(str(v) for v in violations)}")


def check_strategy(case_dir: Path, case: dict) -> None:
    if _SHORTS.search((case_dir / case["strategy_file"]).read_text(encoding="utf-8")):
        raise Refused("the strategy enables shorts; only long-only spot is in scope")


def effective_config(config: dict) -> dict:
    """What the engine actually reads: the customer's config with two blocks replaced.

    The exchange's REST endpoints point at the loopback markets stub, and
    api_server is the repository's placeholder block, which the paper guard
    requires and backtesting never starts. Every other key is the customer's,
    and the paper guard judges the result.
    """
    api = f"http://127.0.0.1:{STUB_PORT}/api/v3"
    ccxt = {"urls": {"api": {"public": api, "private": api, "v1": api, "v3": api}},
            "options": {"fetchMarkets": {"types": ["spot"]}, "fetchCurrencies": False}}
    out = json.loads(json.dumps(config))
    if not isinstance(out.get("exchange"), dict):
        raise Refused("the config has no exchange section")
    out["exchange"]["ccxt_config"] = ccxt
    out["exchange"]["ccxt_async_config"] = ccxt
    out["api_server"] = json.loads(PAPER_EXAMPLE.read_text(encoding="utf-8"))["api_server"]
    return out


def docker_command(case_dir: Path, case: dict, data_dir: Path, out_dir: Path) -> list[str]:
    return [
        "docker", "run", "--rm",
        "--network", "none",
        "--read-only", "--tmpfs", "/tmp:rw,size=512m",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--pids-limit", "512", "--memory", "4g", "--cpus", "2",
        "--user", "1000:1000",
        "--env", "CASE_DIR=/case",
        "-v", f"{(case_dir / 'strategy').resolve()}:/case/strategy:ro",
        "-v", f"{(case_dir / 'exchangeInfo.json').resolve()}:/case/exchangeInfo.json:ro",
        "-v", f"{(out_dir / 'effective_config.json').resolve()}:/case/config.json:ro",
        "-v", f"{data_dir.resolve()}:/data:ro",
        "-v", f"{(HERE / 'entrypoint.sh').resolve()}:/runner/entrypoint.sh:ro",
        "-v", f"{(out_dir / 'results').resolve()}:/out:rw",
        "--entrypoint", "/bin/bash",
        IMAGE, "/runner/entrypoint.sh",
        "--config", "/case/config.json",
        "--strategy", case["strategy_class"], "--strategy-path", "/case/strategy",
        "--datadir", "/data", "--userdir", "/tmp/userdir",
        "--timeframe", case["timeframe"], "--timerange", case["timerange"],
        "--fee", str(case["fee"]),
        "--export", "trades", "--backtest-directory", "/out",
    ]


def prepare(case_dir: Path, data_dir: Path, out_dir: Path, *, containers: list[str], env: dict,
            execute: bool) -> list[str]:
    check_location([case_dir, data_dir, out_dir], containers, env, execute)
    case = load_case(case_dir)
    check_strategy(case_dir, case)
    config = json.loads((case_dir / case["config_file"]).read_text(encoding="utf-8"))
    (out_dir / "results").mkdir(parents=True, exist_ok=True)
    effective = out_dir / "effective_config.json"
    effective.write_text(json.dumps(effective_config(config), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    guard(effective)
    return docker_command(case_dir, case, data_dir, out_dir)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--case", type=Path, required=True)
    ap.add_argument("--data-dir", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--execute", action="store_true", help="run the container (default: print the plan)")
    args = ap.parse_args(argv)
    try:
        command = prepare(args.case, args.data_dir, args.out_dir, containers=running_containers(),
                          env=dict(os.environ), execute=args.execute)
    except Refused as exc:
        print(f"RUNNER = REFUSED\n  - {exc}")
        return 2
    print("RUNNER = PLANNED" if not args.execute else "RUNNER = EXECUTING")
    print(shlex.join(command))
    if not args.execute:
        return 0
    return subprocess.run(command).returncode


if __name__ == "__main__":
    sys.exit(main())
