#!/usr/bin/env python3
"""Render the effective Freqtrade config without needing secrets or a container.

CLOUD-0 / C0.4 — configuration isolation.

Freqtrade resolves configuration with this precedence (highest wins):

    CLI  >  environment (FREQTRADE__SECTION__KEY)  >  config file(s)  >  strategy

This script reproduces the first three layers deterministically so CI and the
research record can show exactly what a run would have used. Credential-bearing
fields are redacted, so the output is safe to print, commit as evidence, or hash.

Usage
-----
    python3 scripts/effective_config.py
    python3 scripts/effective_config.py --config freqtrade/user_data/config.paper.json.example
    python3 scripts/effective_config.py --set max_open_trades=1 --set exchange.pair_whitelist='["BTC/USDT"]'
    python3 scripts/effective_config.py --hash-only
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
USER_DATA = REPO_ROOT / "freqtrade" / "user_data"

DEFAULT_CONFIG_ORDER = (
    USER_DATA / "config.json",
    USER_DATA / "config.paper.json.example",
)

REDACTED = "***REDACTED***"
SECRET_FIELD_HINTS = (
    "key",
    "secret",
    "password",
    "token",
    "uid",
    "jwt",
    "apikey",
    "privatekey",
    "walletaddress",
)
# Fields whose *name* matches a hint but which carry no secret material.
SECRET_FIELD_EXCEPTIONS = {"ws_token_enabled", "keyword"}

ENV_PREFIX = "FREQTRADE__"


def default_config_path() -> Path:
    for candidate in DEFAULT_CONFIG_ORDER:
        if candidate.exists():
            return candidate
    raise SystemExit(
        "no config found; expected one of: " + ", ".join(rel(p) for p in DEFAULT_CONFIG_ORDER)
    )


def rel(path: Path) -> str:
    """Repo-relative path when possible, absolute otherwise."""
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def deep_merge(base: dict, overlay: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def coerce(raw: str) -> object:
    """Parse a value the way Freqtrade parses env/CLI overrides: JSON, else string."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def env_overrides(environ: dict[str, str] | None = None) -> tuple[dict, list[str]]:
    """Translate FREQTRADE__SECTION__KEY variables into a nested override dict."""
    environ = os.environ if environ is None else environ
    overrides: dict = {}
    applied: list[str] = []
    for name in sorted(environ):
        if not name.startswith(ENV_PREFIX):
            continue
        path = [part.lower() for part in name[len(ENV_PREFIX):].split("__") if part]
        if not path:
            continue
        node = overrides
        for part in path[:-1]:
            node = node.setdefault(part, {})
            if not isinstance(node, dict):  # pragma: no cover - conflicting env shape
                break
        else:
            node[path[-1]] = coerce(environ[name])
            applied.append(name)
    return overrides, applied


def cli_overrides(pairs: list[str]) -> tuple[dict, list[str]]:
    overrides: dict = {}
    applied: list[str] = []
    for item in pairs:
        if "=" not in item:
            raise SystemExit(f"--set expects key=value, got {item!r}")
        dotted, raw = item.split("=", 1)
        path = [p for p in dotted.split(".") if p]
        if not path:
            raise SystemExit(f"--set key must not be empty in {item!r}")
        node = overrides
        for part in path[:-1]:
            node = node.setdefault(part, {})
        node[path[-1]] = coerce(raw)
        applied.append(dotted)
    return overrides, applied


def redact(value: object, field: str = "") -> object:
    if isinstance(value, dict):
        return {k: redact(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v, field) for v in value]
    lowered = field.lower()
    if lowered in SECRET_FIELD_EXCEPTIONS:
        return value
    if any(hint in lowered for hint in SECRET_FIELD_HINTS):
        return REDACTED if value not in ("", None) else value
    return value


def canonical(config: dict) -> str:
    return json.dumps(config, sort_keys=True, separators=(",", ":"))


def config_hash(config: dict) -> str:
    return hashlib.sha256(canonical(config).encode("utf-8")).hexdigest()


def build(config_paths: list[Path], sets: list[str], environ: dict[str, str] | None = None) -> dict:
    merged: dict = {}
    for path in config_paths:
        merged = deep_merge(merged, json.loads(path.read_text(encoding="utf-8")))
    env_over, env_applied = env_overrides(environ)
    merged = deep_merge(merged, env_over)
    cli_over, cli_applied = cli_overrides(sets)
    merged = deep_merge(merged, cli_over)

    safe = redact(merged)
    return {
        "precedence": "cli > environment > config file(s) > strategy defaults",
        "config_files": [rel(p) for p in config_paths],
        "environment_overrides_applied": env_applied,
        "cli_overrides_applied": cli_applied,
        "redacted_fields_note": (
            "credential-bearing fields are replaced with "
            f"{REDACTED!r} before printing and before hashing"
        ),
        "effective_config_sha256": config_hash(safe),
        "effective_config": safe,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render the redacted effective Freqtrade config.")
    parser.add_argument("--config", action="append", default=[], metavar="PATH",
                        help="Config file, repeatable; later files win. Defaults to the paper config.")
    parser.add_argument("--set", action="append", default=[], metavar="dotted.key=value",
                        help="Simulate a CLI override (highest precedence).")
    parser.add_argument("--hash-only", action="store_true", help="Print only the effective config sha256.")
    args = parser.parse_args(argv)

    if args.config:
        paths = [Path(p) if Path(p).is_absolute() else REPO_ROOT / p for p in args.config]
        missing = [p for p in paths if not p.exists()]
        if missing:
            raise SystemExit("missing config: " + ", ".join(str(p) for p in missing))
    else:
        paths = [default_config_path()]

    report = build(paths, args.set)
    if args.hash_only:
        print(report["effective_config_sha256"])
    else:
        json.dump(report, sys.stdout, indent=2, sort_keys=False)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
