#!/usr/bin/env python3
"""Build, validate and summarise Trading Lab OS experiment records.

CLOUD-0 / C0.6 — research evidence schema.

Every gate decision must be backed by a JSON record that validates against
``research/schema/experiment_record.schema.json``. The record carries enough
information to re-run the experiment from a clean checkout: code commit, config
hash, dataset fingerprints, strategy hash, engine version, window, costs and the
gate decision with its reason.

Subcommands
-----------
    template                     print an empty record skeleton
    stamp   RECORD               fill in repo-derived fields in place
    validate RECORD [RECORD...]  validate against the schema (exit 2 on failure)
    summarize RECORD [-o OUT.md] render a concise Markdown summary

Locked-OOS rule: records labelled ``oos`` are refused by ``stamp`` and
``summarize`` unless ``--unlock-oos`` is passed explicitly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "research" / "schema" / "experiment_record.schema.json"
STRATEGY_DIR = REPO_ROOT / "freqtrade" / "user_data" / "strategies"

SCHEMA_VERSION = "1.0.0"


def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def git_state() -> tuple[str, bool]:
    """Return (commit_sha, dirty). Falls back to zeros outside a git checkout."""
    try:
        sha = subprocess.check_output(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"], text=True
        ).strip()
    except Exception:  # noqa: BLE001
        return "0" * 40, True
    try:
        dirty = bool(
            subprocess.check_output(
                ["git", "-C", str(REPO_ROOT), "status", "--porcelain"], text=True
            ).strip()
        )
    except Exception:  # noqa: BLE001
        dirty = True
    return sha, dirty


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rel(path: Path) -> str:
    """Repo-relative path when possible, absolute otherwise."""
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def strategy_fingerprint(name: str) -> dict:
    path = STRATEGY_DIR / f"{name}.py"
    if not path.exists():
        raise SystemExit(f"strategy file not found: {path}")
    return {"name": name, "file": rel(path), "sha256": sha256_file(path)}


def effective_config_hash(config_paths: list[str]) -> str:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import effective_config  # noqa: PLC0415 - local helper, imported lazily on purpose

    if config_paths:
        paths = [REPO_ROOT / p for p in config_paths]
    else:
        paths = [effective_config.default_config_path()]
    return effective_config.build(paths, [], environ={})["effective_config_sha256"]


def template() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "timestamp_utc": "",
        "experiment": "baseline-1",
        "run_name": "",
        "command": "",
        "code_commit": "",
        "code_dirty": False,
        "config_hash": "",
        "config_files": ["freqtrade/user_data/config.paper.json.example"],
        "dataset_hashes": {},
        "dataset_audit_pass": False,
        "strategy": {"name": "", "file": "", "sha256": ""},
        "freqtrade_version": "",
        "pairs": ["BTC/USDT", "ETH/USDT"],
        "timeframe": "1h",
        "detail_timeframe": None,
        "timerange": "20250901-20260501",
        "period_label": "development",
        "fee_assumption": {
            "per_side_ratio": 0.001,
            "source": "assumed Binance spot taker fee; replace with the fee actually configured",
        },
        "wallet": 100,
        "stake": 10,
        "max_open_trades": 2,
        "metrics": {},
        "analyses": {"lookahead": "not_run", "recursive": "not_run", "detail_timeframe_simulation": "not_run"},
        "gate": "INFORMATIONAL",
        "reason": "",
    }


def stamp(record: dict, config_paths: list[str] | None = None) -> dict:
    sha, dirty = git_state()
    record["schema_version"] = SCHEMA_VERSION
    record["timestamp_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    record["code_commit"] = f"dirty:{sha}" if dirty else sha
    record["code_dirty"] = dirty
    paths = config_paths if config_paths is not None else record.get("config_files") or []
    record["config_hash"] = effective_config_hash(list(paths))
    if paths:
        record["config_files"] = list(paths)
    name = (record.get("strategy") or {}).get("name")
    if name:
        record["strategy"] = strategy_fingerprint(name)
    return record


def validate(record: dict) -> list[str]:
    """Return a list of schema violations (empty means valid)."""
    try:
        import jsonschema  # noqa: PLC0415
    except ImportError:  # pragma: no cover - CI installs the pin
        raise SystemExit(
            "jsonschema is required: pip install -r requirements-dev.txt"
        ) from None

    validator_cls = jsonschema.validators.validator_for(load_schema())
    validator = validator_cls(load_schema())
    errors = sorted(validator.iter_errors(record), key=lambda e: list(e.absolute_path))
    return [
        f"{'/'.join(str(p) for p in err.absolute_path) or '<root>'}: {err.message}"
        for err in errors
    ]


def _fmt(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.6g}"
    if isinstance(value, dict):
        return ", ".join(f"{k}={_fmt(v)}" for k, v in sorted(value.items())) or "—"
    if isinstance(value, list):
        return ", ".join(str(v) for v in value) or "—"
    if value is None or value == "":
        return "—"
    return str(value)


def to_markdown(record: dict) -> str:
    lines: list[str] = []
    title = record.get("run_name") or record.get("experiment") or "experiment"
    lines.append(f"# Experiment record — {title}")
    lines.append("")
    lines.append(f"**Gate: {record.get('gate', '—')}** — {record.get('reason', '—')}")
    if record.get("code_dirty"):
        lines.append("")
        lines.append("> WARNING: recorded from a dirty worktree. Not valid gate evidence.")
    lines.append("")
    lines.append("## Reproduction")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("| --- | --- |")
    repro = [
        ("Recorded (UTC)", record.get("timestamp_utc")),
        ("Command", f"`{record.get('command', '')}`"),
        ("Code commit", record.get("code_commit")),
        ("Config hash", record.get("config_hash")),
        ("Config files", record.get("config_files")),
        ("Strategy", (record.get("strategy") or {}).get("name")),
        ("Strategy sha256", (record.get("strategy") or {}).get("sha256")),
        ("Freqtrade version", record.get("freqtrade_version")),
        ("Period", record.get("period_label")),
        ("Timerange", record.get("timerange")),
        ("Pairs", record.get("pairs")),
        ("Timeframe", record.get("timeframe")),
        ("Detail timeframe", record.get("detail_timeframe")),
        ("Fee per side", (record.get("fee_assumption") or {}).get("per_side_ratio")),
        ("Fee source", (record.get("fee_assumption") or {}).get("source")),
        ("Wallet", record.get("wallet")),
        ("Stake", record.get("stake")),
        ("Max open trades", record.get("max_open_trades")),
        ("Dataset audit", "PASS" if record.get("dataset_audit_pass") else "NOT PROVEN"),
    ]
    for key, value in repro:
        lines.append(f"| {key} | {_fmt(value)} |")

    lines.append("")
    lines.append("## Dataset fingerprints")
    lines.append("")
    hashes = record.get("dataset_hashes") or {}
    if hashes:
        lines.append("| Dataset | sha256 |")
        lines.append("| --- | --- |")
        for key in sorted(hashes):
            lines.append(f"| {key} | `{hashes[key]}` |")
    else:
        lines.append("_none recorded_")

    lines.append("")
    lines.append("## Metrics")
    lines.append("")
    metrics = record.get("metrics") or {}
    if metrics:
        lines.append("| Metric | Value |")
        lines.append("| --- | --- |")
        for key in sorted(metrics):
            lines.append(f"| {key} | {_fmt(metrics[key])} |")
    else:
        lines.append("_none recorded_")

    analyses = record.get("analyses") or {}
    if analyses:
        lines.append("")
        lines.append("## Supporting analyses")
        lines.append("")
        for key in sorted(analyses):
            lines.append(f"- {key}: **{analyses[key]}**")

    if record.get("notes"):
        lines.append("")
        lines.append("## Notes")
        lines.append("")
        lines.append(str(record["notes"]))

    lines.append("")
    return "\n".join(lines)


def _oos_locked(record: dict, unlocked: bool) -> bool:
    return record.get("period_label") == "oos" and not unlocked


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("template", help="print an empty record skeleton")

    p_stamp = sub.add_parser("stamp", help="fill in repo-derived fields in place")
    p_stamp.add_argument("record")
    p_stamp.add_argument("--config", action="append", default=None, metavar="PATH")
    p_stamp.add_argument("--unlock-oos", action="store_true")

    p_val = sub.add_parser("validate", help="validate records against the schema")
    p_val.add_argument("records", nargs="+")

    p_sum = sub.add_parser("summarize", help="render a Markdown summary")
    p_sum.add_argument("record")
    p_sum.add_argument("-o", "--out", default=None)
    p_sum.add_argument("--unlock-oos", action="store_true")

    args = parser.parse_args(argv)

    if args.cmd == "template":
        json.dump(template(), sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    if args.cmd == "validate":
        failed = False
        for name in args.records:
            path = Path(name)
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                print(f"INVALID {name}: unreadable JSON: {exc}", file=sys.stderr)
                failed = True
                continue
            errors = validate(record)
            if errors:
                failed = True
                print(f"INVALID {name}", file=sys.stderr)
                for err in errors:
                    print(f"  - {err}", file=sys.stderr)
            else:
                print(f"VALID   {name}")
        return 2 if failed else 0

    path = Path(args.record)
    record = json.loads(path.read_text(encoding="utf-8"))

    if _oos_locked(record, args.unlock_oos):
        print(
            "OOS_LOCKED: this record is labelled 'oos'. Pass --unlock-oos only at the final OOS gate.",
            file=sys.stderr,
        )
        return 3

    if args.cmd == "stamp":
        stamp(record, args.config)
        path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        print(f"stamped {path}")
        errors = validate(record)
        if errors:
            print("record is stamped but still incomplete:", file=sys.stderr)
            for err in errors:
                print(f"  - {err}", file=sys.stderr)
            return 2
        return 0

    markdown = to_markdown(record)
    if args.out:
        Path(args.out).write_text(markdown, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        sys.stdout.write(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
