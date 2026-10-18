#!/usr/bin/env python3
"""H1 host placement check at T0: no P2 cohort may be running on the H1 host.

    python3 research/paper/h1/launch/h1_host_placement.py [--ref origin/main] [--json out.json]

It prints one verdict, and its exit code matches:

    HOST_PLACEMENT = PASS      0   no P2 container is running here; the H1 name, port and network are free
    HOST_PLACEMENT = BLOCKED   20  a P2 container is running (with no Owner exception), or H1's own
                                   container, network or port 127.0.0.1:8181 already exists
    HOST_PLACEMENT = UNPROVEN  30  the Docker daemon could not be read. UNPROVEN blocks exactly as
                                   BLOCKED does

The only exception is a separate, explicit Owner decision recorded at
``research/paper/h1/amendments/ISOLATED_SAME_HOST_AFTER_OWNER_APPROVAL.md`` on the
ref, brought in by a two-parent merge. This tool never writes that record, and no
flag stands in for it. With the record present, a running P2 container is reported
and the verdict is ``PASS_ISOLATED_SAME_HOST``. Every other check still applies.

It reads ``docker ps -a`` and ``docker network ls``, and probes 127.0.0.1:8181. It
starts, stops and edits nothing. PAPER / RESEARCH ONLY.
"""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import h1_p2_entry_gate as gate  # noqa: E402

EXCEPTION_RECORD = "research/paper/h1/amendments/ISOLATED_SAME_HOST_AFTER_OWNER_APPROVAL.md"
# A container is P2's if its name or compose project contains one of these
# (cohort.json forbidden_identity_reuse, and the P2 runtime checkout's compose project).
P2_MARKERS = ("fp-control", "trading-lab-paper", "trading_lab_os_final", "trading-lab-os-final")
H1_CONTAINER = "tlos-h1-paper-cohort-1-freqtrade"
H1_NETWORK = "tlos-h1-paper-cohort-1-net"
H1_PORT = 8181


def docker_lines(*args: str) -> list[str] | None:
    try:
        result = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.splitlines() if result.returncode == 0 else None


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", port)) == 0


def evaluate(ps_lines: list[str] | None, networks: list[str] | None, port_busy: bool,
             exception_merged: bool) -> dict:
    """ps_lines: ``docker ps -a --format '{{.Names}}|{{.State}}|{{.Label "com.docker.compose.project"}}'``."""
    reasons: list[str] = []
    out = {"check": "H1_HOST_PLACEMENT", "reasons": reasons, "exception_record_merged": exception_merged}
    if ps_lines is None or networks is None:
        reasons.append("the Docker daemon could not be read")
        return {**out, "verdict": "UNPROVEN"}
    p2_running, h1_existing = [], []
    for line in ps_lines:
        name, state, project = (line.split("|") + ["", "", ""])[:3]
        ident = f"{name} {project}".lower()
        if name == H1_CONTAINER:
            h1_existing.append(f"{name} ({state})")
        elif state == "running" and any(m in ident for m in P2_MARKERS):
            p2_running.append(name)
    out["p2_running"], out["h1_existing"] = p2_running, h1_existing
    if h1_existing:
        reasons.append(f"H1's container already exists: {h1_existing}; a cohort starts once, on a fresh lane")
    if H1_NETWORK in networks:
        reasons.append(f"H1's network {H1_NETWORK} already exists")
    if port_busy:
        reasons.append(f"127.0.0.1:{H1_PORT} is already in use")
    if p2_running and not exception_merged:
        reasons.append(f"a P2 cohort is running on this host: {p2_running}; no Owner exception is merged")
    if reasons:
        return {**out, "verdict": "BLOCKED"}
    return {**out, "verdict": "PASS_ISOLATED_SAME_HOST" if p2_running else "PASS"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ref", default="origin/main")
    ap.add_argument("--json", type=Path)
    args = ap.parse_args(argv)
    exception_merged = (gate.show(args.ref, EXCEPTION_RECORD) is not None
                        and gate.first_parent_merge_introducing(args.ref, EXCEPTION_RECORD) is not None)
    result = evaluate(
        docker_lines("ps", "-a", "--format", '{{.Names}}|{{.State}}|{{.Label "com.docker.compose.project"}}'),
        docker_lines("network", "ls", "--format", "{{.Name}}"),
        port_in_use(H1_PORT), exception_merged)
    if args.json:
        args.json.write_text(json.dumps(result, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    for reason in result["reasons"]:
        print(f"  - {reason}", file=sys.stderr)
    verdict = result["verdict"]
    print(f"HOST_PLACEMENT = {verdict}")
    return 0 if verdict.startswith("PASS") else (30 if verdict == "UNPROVEN" else 20)


if __name__ == "__main__":
    sys.exit(main())
