#!/usr/bin/env python3
"""P3-PLN-03: create an append-only backup set, verify it, or prove it with a restore drill.

    scripts/p3/backup.py create --target /mnt/tlos-wdc/tlos-backups \\
        --root runtime=/home/hamza/projects/trading/trading_lab_os_final \\
        --repo runtime=/home/hamza/projects/trading/trading_lab_os_final \\
        [--volume trading_lab_os_final_grafana_data ...]
    scripts/p3/backup.py verify --set /mnt/tlos-wdc/tlos-backups/<stamp>
    scripts/p3/backup.py drill  --set /mnt/tlos-wdc/tlos-backups/<stamp> --scratch <empty dir> [--config-load trading/trading_lab_os_final]

See research/p3/backup.py. `create` writes only under --target, in a new <stamp> directory, and
never overwrites one. `drill` writes only under --scratch. `--config-load <runtime>` runs the pinned
Freqtrade image with --network none and the restored user_data mounted read-only. It issues
only list-strategies and show-config, exactly as CI's freqtrade-load job does, and no trading
command. Exit codes: 0 PASS · 1 FAIL · 2 error.

PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for _extra in (str(REPO_ROOT / "research"), str(REPO_ROOT / "scripts")):
    if _extra not in sys.path:
        sys.path.insert(0, _extra)

from p3 import backup  # noqa: E402

ENGINE_IMAGE = "freqtradeorg/freqtrade@sha256:da3428fde0f7f9f976eaafba8abc7eba42bf978f23e4808347e15d476ad9a643"
CONFIG_ERROR = re.compile(r"CRITICAL - Invalid configuration|Configuration error|OperationalException")


def _pairs(values: list[str]) -> dict[str, Path]:
    out = {}
    for value in values:
        name, _, path = value.partition("=")
        if not name or not path:
            raise SystemExit(f"expected NAME=PATH, got {value!r}")
        out[name] = Path(path)
    return out


def config_load(restored_root: Path) -> tuple[bool, str]:
    user_data = restored_root / "freqtrade" / "user_data"
    if not (user_data / "config.json").is_file():
        return False, "restored copy has no freqtrade/user_data/config.json"
    base = ["docker", "run", "--rm", "--network", "none", "-v", f"{user_data}:/freqtrade/user_data:ro", ENGINE_IMAGE]
    results = []
    for args in (["list-strategies", "--config", "/freqtrade/user_data/config.json",
                  "--strategy-path", "/freqtrade/user_data/strategies"],
                 ["show-config", "--config", "/freqtrade/user_data/config.json"]):
        run = subprocess.run(base + args, capture_output=True, text=True, timeout=300)
        output = run.stdout + run.stderr
        ok = run.returncode == 0 and not CONFIG_ERROR.search(output)
        if args[0] == "list-strategies":
            # The configs name no strategy (it is passed at launch), so every strategy the restored
            # tree carries must load, and at least one must be listed.
            # Freqtrade lists each strategy twice (config default path and --strategy-path name the same
            # directory, "DUPLICATE NAME"), as in CI; a broken one would read "LOAD FAILED".
            ok = ok and "LOAD FAILED" not in output and re.search(r"\.py\s*│", output) is not None
        results.append(f"{args[0]}={'OK' if ok else 'FAIL'}")
        if not ok:
            return False, "; ".join(results)
    return True, "; ".join(results) + " (pinned engine, --network none, read-only mount, no trading command)"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument("--target", required=True, type=Path)
    create.add_argument("--root", action="append", default=[])
    create.add_argument("--repo", action="append", default=[])
    create.add_argument("--volume", action="append", default=[])
    create.add_argument("--stamp")
    verify = sub.add_parser("verify")
    verify.add_argument("--set", required=True, type=Path, dest="set_dir")
    drill = sub.add_parser("drill")
    drill.add_argument("--set", required=True, type=Path, dest="set_dir")
    drill.add_argument("--scratch", required=True, type=Path)
    drill.add_argument("--config-load", action="append", default=[], metavar="ROOT[/SUBDIR]",
                       help="the restored runtime whose config and strategies must load, e.g. trading/trading_lab_os_final")
    drill.add_argument("--json", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "create":
            record = backup.create_backup(args.target, roots=_pairs(args.root), repos=_pairs(args.repo),
                                          volumes=tuple(args.volume), stamp=args.stamp)
            print(json.dumps(record, indent=2))
            verdict = backup.verify_backup(args.target / record["stamp"])
            print(f"BACKUP_SET = {record['stamp']} · VERIFY = {verdict['status']}")
            return 0 if verdict["status"] == "PASS" else 1
        if args.command == "verify":
            verdict = backup.verify_backup(args.set_dir)
            print(f"VERIFY = {verdict['status']} {verdict.get('mismatched', '')}")
            return 0 if verdict["status"] == "PASS" else 1
        import publish_evidence_digest
        report = backup.restore_drill(args.set_dir, args.scratch,
                                      archive_verifier=publish_evidence_digest.verify_archive,
                                      config_check=config_load if args.config_load else None,
                                      config_targets=tuple(args.config_load) or None)
    except (backup.BackupError, OSError, KeyError, json.JSONDecodeError) as exc:
        print(f"P3_BACKUP_ERROR: {exc}", file=sys.stderr)
        return 2
    if args.json:
        args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for name, check in report["checks"].items():
        print(f"  {name:32} {check['status']}")
    print(f"PLN_03_RESTORE_DRILL = {report['PLN_03_RESTORE_DRILL']}")
    return 0 if report["PLN_03_RESTORE_DRILL"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
