#!/usr/bin/env python3
"""H1_LAUNCH_AUTHORIZATION card: every launch condition in one place. The default is DENY.

    python3 research/paper/h1/launch/h1_launch_card.py \
        --materialisation-record <workspace>/MATERIALISATION_RECORD.json \
        --lane-dir /home/hamza/tlos-paper/h1-paper-cohort-1 \
        --second-store <a durable location on another device> \
        [--ref origin/main] [--json card.json]

It assembles the card the Owner decides on, and nothing more. It never launches,
never sets T0, and never writes outside ``--json``. Each row is PASS or not PASS:

    P2_TERMINAL_STATUS / P2_CLOSURE_DIGEST   H1_P2_ENTRY_GATE = H1_ENTRY_ELIGIBLE
    G11_RECORDS_PR_STATUS                    G5 and G6 records on the ref through a two-parent merge
    H1_WINDOW_AMENDMENT                      the 10-day window record, adopted, on the ref through a merge
    H1_PACKAGE_DIGEST                        h1_paper.py verify = PASS and digest = ef9a3d0c…bc43c
    SOURCE_SHA256_STATUS                     the materialised files equal the three pins
    MATERIALISATION_PREFLIGHT                h1_paper.py preflight = PASS on the materialised dir and the lane
    PAPER_GUARD / DRY_RUN                    paper_guard on the package config; dry_run is true
    HOST_PLACEMENT                           h1_host_placement = PASS (or PASS_ISOLATED_SAME_HOST)
    SECOND_EVIDENCE_STORE                    an existing directory, writable, on a different device from the lane
    REAL_MONEY_AUTHORIZED                    NO, always

``OWNER_DECISION_DEFAULT = DENY`` unless every row is PASS. When every row is PASS,
the card reads ``READY_FOR_OWNER_AUTHORIZATION``. That is still not an authorization:
only the Owner's own decision, naming the package digest, starts the cohort.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(HERE))
import h1_host_placement as placement  # noqa: E402
import h1_materialise as mat  # noqa: E402
import h1_p2_entry_gate as gate  # noqa: E402

PACKAGE = REPO / "research" / "paper" / "h1" / "package"
G11_RECORDS = {
    "research/paper/h1/amendments/G5_HOST_CHECK.md": "2870d7dc6ca812342b040e3864dfdf0b5151c9cf876483eeaa7f79ed909159f9",
    gate.AMENDMENTS: gate.G6_AMENDMENTS_SHA256,
}
WINDOW_AMENDMENT = "research/paper/h1/amendments/H1_WINDOW_AMENDMENT_10D.md"
WINDOW_AMENDMENT_SHA256 = "9283a848f5a8205ff8a811b3ae8d1c4635ed0ef8c7e986955b8bf0f24aa35f4b"
COMPOSE_REL = "research/paper/h1/package/docker-compose.h1-paper.yml"
API_ENV_FILE = "<operator-local env file, outside git: H1_PAPER_API_USER, H1_PAPER_API_PASSWORD, " \
               "H1_PAPER_JWT_SECRET, H1_PAPER_WS_TOKEN — API-server login only, never an exchange key>"


def launch_command(strategy_dir: str, lane_dir: str) -> str:
    """The exact launch command, rendered for the Owner to read. This tool never runs it."""
    return (
        f"cd <a clean checkout of the merged main named on this card> && "
        f"env -i PATH=/usr/bin:/bin HOME=/nonexistent "
        f"H1_PAPER_STRATEGY_DIR={shlex.quote(strategy_dir)} H1_PAPER_LANE_DIR={shlex.quote(lane_dir)} "
        f"docker compose --env-file {API_ENV_FILE} -f {COMPOSE_REL} up -d "
        f"&& python3 research/paper/h1/package/h1_paper.py incident --lane-dir {shlex.quote(lane_dir)} "
        f"--type COHORT_START --detail '<MATERIALISATION_RECORD.json + package digest + host bindings>'"
    )


def run_h1_paper(*args: str) -> tuple[bool, str]:
    result = subprocess.run([sys.executable, str(PACKAGE / "h1_paper.py"), *args],
                            capture_output=True, text=True, cwd=REPO)
    return result.returncode == 0, (result.stdout + result.stderr).strip()


def same_device(a: Path, b: Path) -> bool:
    probe_a = a if a.exists() else a.parent
    while not probe_a.exists():
        probe_a = probe_a.parent
    return os.stat(probe_a).st_dev == os.stat(b).st_dev


def build_card(ref: str, record_path: Path | None, lane_dir: Path | None, second_store: Path | None,
               *, entry: dict | None = None, host: dict | None = None) -> dict:
    rows: dict[str, dict] = {}

    entry = entry or gate.evaluate(ref)
    rows["P2_TERMINAL_STATUS"] = {"value": entry.get("p2_terminal_status"), "verdict": entry["verdict"],
                                  "pass": entry["verdict"] == gate.ELIGIBLE, "reasons": entry["reasons"]}
    rows["P2_CLOSURE_DIGEST"] = {"value": entry.get("p2_closure_sha256"), "merge": entry.get("p2_closure_merge"),
                                 "pass": entry["verdict"] == gate.ELIGIBLE}

    g11 = {}
    for path, digest in G11_RECORDS.items():
        blob = gate.show(ref, path)
        g11[path] = {"sha256_ok": blob is not None and hashlib.sha256(blob).hexdigest() == digest,
                     "merged": blob is not None and gate.first_parent_merge_introducing(ref, path) is not None}
    rows["G11_RECORDS_PR_STATUS"] = {"value": "MERGED" if all(v["sha256_ok"] and v["merged"] for v in g11.values())
                                     else "NOT_MERGED", "records": g11}
    rows["G11_RECORDS_PR_STATUS"]["pass"] = rows["G11_RECORDS_PR_STATUS"]["value"] == "MERGED"

    blob = gate.show(ref, WINDOW_AMENDMENT)
    sha_ok = blob is not None and hashlib.sha256(blob).hexdigest() == WINDOW_AMENDMENT_SHA256
    adopted = sha_ok and b"DECISION    PENDING" not in blob
    merged = blob is not None and gate.first_parent_merge_introducing(ref, WINDOW_AMENDMENT) is not None
    rows["H1_WINDOW_AMENDMENT"] = {"value": "ADOPTED" if adopted and merged else "NOT_ADOPTED",
                                   "sha256_ok": sha_ok, "merged": merged, "pass": adopted and merged}

    ok, text = run_h1_paper("verify")
    digest = hashlib.sha256((PACKAGE / "PACKAGE_MANIFEST.sha256").read_bytes()).hexdigest()
    rows["H1_PACKAGE_DIGEST"] = {"value": digest, "verify": "PASS" if ok else "FAIL",
                                 "pass": ok and digest == gate.H1_PACKAGE_DIGEST == entry.get("h1_package_digest")}

    record = None
    if record_path and record_path.is_file():
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            record = None
    strategy_dir = Path(record["H1_PAPER_STRATEGY_DIR"]) if record else None
    src_ok = False
    if strategy_dir and strategy_dir.is_dir():
        src_ok = all((strategy_dir / name).is_file() and mat.sha256_file(strategy_dir / name) == pin
                     for name, (_r, pin, _s) in mat.PINNED.items())
    rows["SOURCE_SHA256_STATUS"] = {"value": "MATCH" if src_ok else "NOT_VERIFIED",
                                    "record": str(record_path) if record_path else None, "pass": src_ok}

    if strategy_dir and lane_dir:
        ok, text = run_h1_paper("preflight", "--lane-dir", str(lane_dir), "--strategy-dir", str(strategy_dir))
        rows["MATERIALISATION_PREFLIGHT"] = {"value": "PASS" if ok else "FAIL", "output": text, "pass": ok}
    else:
        rows["MATERIALISATION_PREFLIGHT"] = {"value": "NOT_RUN", "pass": False}

    sys.path.insert(0, str(REPO / "scripts"))
    import paper_guard
    violations = paper_guard.Violations()
    paper_guard.check_config(PACKAGE / "config.h1-paper.json", violations)
    rows["PAPER_GUARD"] = {"value": "PASS" if not list(violations) else "FAIL",
                           "violations": [str(v) for v in violations], "pass": not list(violations)}
    config = json.loads((PACKAGE / "config.h1-paper.json").read_text(encoding="utf-8"))
    rows["DRY_RUN"] = {"value": config.get("dry_run"), "pass": config.get("dry_run") is True}

    host = host or placement.evaluate(
        placement.docker_lines("ps", "-a", "--format", '{{.Names}}|{{.State}}|{{.Label "com.docker.compose.project"}}'),
        placement.docker_lines("network", "ls", "--format", "{{.Name}}"),
        placement.port_in_use(placement.H1_PORT),
        gate.show(ref, placement.EXCEPTION_RECORD) is not None
        and gate.first_parent_merge_introducing(ref, placement.EXCEPTION_RECORD) is not None)
    rows["HOST_PLACEMENT"] = {"value": host["verdict"], "reasons": host["reasons"],
                              "pass": host["verdict"].startswith("PASS")}

    store_ok = bool(second_store and second_store.is_dir() and os.access(second_store, os.W_OK)
                    and lane_dir and not same_device(lane_dir, second_store))
    rows["SECOND_EVIDENCE_STORE"] = {"value": str(second_store) if second_store else None, "pass": store_ok}
    rows["REAL_MONEY_AUTHORIZED"] = {"value": "NO", "pass": True}

    all_pass = all(r["pass"] for r in rows.values())
    return {
        "card": "H1_LAUNCH_AUTHORIZATION",
        "ref": ref,
        "ref_commit": entry.get("ref_commit"),
        "rows": rows,
        "EXACT_LAUNCH_COMMAND": launch_command(str(strategy_dir or "<H1_PAPER_STRATEGY_DIR>"),
                                               str(lane_dir or "<H1_PAPER_LANE_DIR>")),
        "EXPECTED_T0_EFFECT": (
            "one container tlos-h1-paper-cohort-1-freqtrade starts in dry-run on Binance spot BTC/USDT 1h with a "
            "100 USDT simulated wallet; the COHORT_START incident's recorded_utc becomes PAPER_T0; the frozen "
            "10-day operational window (H1-WINDOW-AMENDMENT-1) runs from the close of the first processed 1h "
            "candle (ACTIVATION_UTC); no edge verdict is drawn from it; the freeze law (PREREGISTRATION.md §6) binds from T0; no real order, key or money is involved"),
        "REAL_MONEY_AUTHORIZED": "NO",
        "OWNER_DECISION_DEFAULT": "READY_FOR_OWNER_AUTHORIZATION" if all_pass else "DENY",
        "not_pass": [k for k, r in rows.items() if not r["pass"]],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ref", default="origin/main")
    ap.add_argument("--materialisation-record", type=Path)
    ap.add_argument("--lane-dir", type=Path)
    ap.add_argument("--second-store", type=Path)
    ap.add_argument("--json", type=Path)
    args = ap.parse_args(argv)
    card = build_card(args.ref, args.materialisation_record, args.lane_dir, args.second_store)
    if args.json:
        args.json.write_text(json.dumps(card, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    for key, row in card["rows"].items():
        print(f"{key:28} {'PASS' if row['pass'] else 'NOT PASS':9} {row.get('value')}")
    print(f"EXACT_LAUNCH_COMMAND         {card['EXACT_LAUNCH_COMMAND']}")
    print(f"OWNER_DECISION_DEFAULT = {card['OWNER_DECISION_DEFAULT']}")
    return 0 if card["OWNER_DECISION_DEFAULT"] != "DENY" else 1


if __name__ == "__main__":
    sys.exit(main())
