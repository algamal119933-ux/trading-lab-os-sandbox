#!/usr/bin/env python3
"""Tier-3 DISCOVERY: what independent storage, if any, this host already has.

    scripts/tier3_discovery.py
    scripts/tier3_discovery.py --json -o artifacts/tier3-discovery.json

Contract section 8. Tier 1 puts a lane out of container reach; Tier 2 makes a
loss provable and bounded. Neither survives this machine. Only Tier 3 —
evidence storage outside the active workstation's FAILURE DOMAIN — may claim
host-loss redundancy, and the project has already paid once for conflating a
same-host copy with one, under the closure reason
``EVIDENCE_LANE_LOST_IN_HOST_MIGRATION``.

This tool DISCOVERS. It does not provision, purchase, create credentials, mount
anything, upload anything, or contact any remote service. Those are Owner
authority, explicitly, and the difference between "I found a USB disk" and "I
copied your evidence onto a USB disk" is the whole boundary. It reports what is
*already lawfully available* and leaves the decision where it belongs:

    TIER3_DESTINATION = OPEN_OWNER_DECISION

A candidate here is a candidate, never a destination. Nothing below has been
verified to be writable, durable, or actually in a different failure domain —
a second partition on the same disk is a different filesystem and the same
failure domain, and this tool says so rather than counting it.

Exit code is always 0: discovery that found nothing is a finding, not an error.
Whether the absence of a destination blocks T0 is the contract's question, not
this tool's.

PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

SAME_FAILURE_DOMAIN = "SAME_FAILURE_DOMAIN"
POSSIBLY_INDEPENDENT = "POSSIBLY_INDEPENDENT"
UNKNOWN = "UNKNOWN"

TIER3_DESTINATION = "OPEN_OWNER_DECISION"

# Filesystem types that are, by construction, not a separate failure domain:
# they are views onto kernel state or onto the same storage.
VIRTUAL_FSTYPES = frozenset({
    "proc", "sysfs", "devtmpfs", "devpts", "tmpfs", "cgroup", "cgroup2", "pstore",
    "bpf", "securityfs", "debugfs", "tracefs", "configfs", "fusectl", "mqueue",
    "hugetlbfs", "autofs", "binfmt_misc", "efivarfs", "ramfs", "squashfs", "overlay",
    "nsfs", "fuse.portal", "fuse.gvfsd-fuse",
})
# Filesystem types that cross a machine boundary. Reaching one of these is the
# only shape of local discovery that can honestly be called independent.
NETWORK_FSTYPES = frozenset({"nfs", "nfs4", "cifs", "smb3", "sshfs", "fuse.sshfs", "glusterfs", "ceph"})


def _repo_device() -> int | None:
    try:
        return os.stat(REPO_ROOT).st_dev
    except OSError:
        return None


def _mounts() -> list[dict]:
    """Every mounted filesystem, classified. Reads /proc/self/mountinfo only."""
    repo_dev = _repo_device()
    out: list[dict] = []
    try:
        text = Path("/proc/self/mounts").read_text(encoding="utf-8")
    except OSError:
        return out
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        source, target, fstype = parts[0], parts[1].replace("\\040", " "), parts[2]
        if fstype in VIRTUAL_FSTYPES:
            continue
        try:
            stat = os.stat(target)
            usage = shutil.disk_usage(target)
        except OSError:
            continue
        if fstype in NETWORK_FSTYPES:
            domain = POSSIBLY_INDEPENDENT
            reason = f"{fstype} crosses a machine boundary; the storage is not this host's disk"
        elif repo_dev is not None and stat.st_dev == repo_dev:
            domain = SAME_FAILURE_DOMAIN
            reason = "same device as the repository: one disk failure takes both"
        elif source.startswith("/dev/") and any(
            token in target for token in ("/media/", "/mnt/", "/run/media/")
        ):
            domain = UNKNOWN
            reason = (
                "a separate block device mounted as removable media. Whether it is a different "
                "failure domain depends on whether it is a different physical disk, and on whether "
                "it leaves this desk — neither of which this tool can determine"
            )
        else:
            domain = UNKNOWN
            reason = (
                "a separate device on this host. A second partition or a second disk in the same "
                "machine is a different filesystem and the SAME failure domain: a theft, a fire, a "
                "PSU failure or a decommission takes both"
            )
        out.append({
            "target": target,
            "source": source,
            "fstype": fstype,
            "free_bytes": usage.free,
            "total_bytes": usage.total,
            "failure_domain": domain,
            "reason": reason,
        })
    return out


def _git_remotes() -> list[dict]:
    """Configured git remotes — reported, never as an evidence destination.

    A git remote is the one genuinely off-host destination this repository
    already has, and it is exactly the wrong place for evidence: the ledgers are
    gitignored by design, the worktree must stay clean for the whole window, and
    committing evidence is the tempting fix the repository's own integrity gate
    exists to prevent. Listed so the Owner can see what exists, marked so nobody
    reads it as a proposal.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "remote", "-v"],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []
    seen: dict[str, str] = {}
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            seen[parts[0]] = parts[1]
    return [
        {
            "name": name,
            "url": url,
            "failure_domain": POSSIBLY_INDEPENDENT,
            "eligible_as_evidence_destination": False,
            "reason": (
                "off-host, but NOT an evidence destination: the evidence lane is gitignored by "
                "design, the worktree must stay clean for the whole window, and committing "
                "evidence is precisely what the repository's integrity gate exists to prevent. "
                "Tier 2 already publishes digests through this remote, and digests are not a backup"
            ),
        }
        for name, url in sorted(seen.items())
    ]


def discover() -> dict:
    mounts = _mounts()
    candidates = [m for m in mounts if m["failure_domain"] != SAME_FAILURE_DOMAIN]
    independent = [m for m in mounts if m["failure_domain"] == POSSIBLY_INDEPENDENT]
    return {
        "tier3_discovery_version": "FP_TIER3_DISCOVERY_V1",
        "observed_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "host": os.uname().nodename if hasattr(os, "uname") else "",
        "repository": str(REPO_ROOT),
        "mounts": mounts,
        "candidates": candidates,
        "git_remotes": _git_remotes(),
        "provisioned": False,
        "actions_taken": (
            "NONE. This tool discovers. Provisioning, purchase, credential creation and any "
            "outbound transfer are Owner authority and were not performed."
        ),
        "tier3_destination": TIER3_DESTINATION,
        # Three verdicts, not two. "Nothing found" and "something found whose
        # independence nobody has established" are different facts, and
        # collapsing them would either hide a usable destination or promote an
        # unproven one — and promoting an unproven one is how a same-host copy
        # came to be treated as redundancy the first time.
        "verdict": (
            "CANDIDATE_FOUND_PENDING_OWNER_DECISION" if independent else
            "CANDIDATE_FOUND_INDEPENDENCE_UNPROVEN" if candidates else
            "NO_CANDIDATE_FOUND"
        ),
        "note": (
            "A candidate is a candidate. Nothing here has been verified writable, durable, or "
            "genuinely outside this workstation's failure domain. A same-host copy is never "
            "described as host-loss redundancy, in any record, at any time."
        ),
        "real_money_authorized": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("-o", "--out", default=None)
    args = parser.parse_args(argv)

    report = discover()
    text = json.dumps(report, indent=2) + "\n"

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    if args.json:
        sys.stdout.write(text)
    elif not args.out:
        print(f"TIER-3 DISCOVERY — {report['host']}")
        for mount in report["mounts"]:
            print(f"  [{mount['failure_domain']:>20}] {mount['target']}  ({mount['fstype']}, "
                  f"{mount['free_bytes'] // (1024**3)} GiB free)")
            print(f"        {mount['reason']}")
        for remote in report["git_remotes"]:
            print(f"  [{remote['failure_domain']:>20}] git remote {remote['name']} — "
                  f"eligible: {remote['eligible_as_evidence_destination']}")
            print(f"        {remote['reason']}")
        print()
        print(f"VERDICT = {report['verdict']}")
        print(f"TIER3_DESTINATION = {report['tier3_destination']}")
        print(f"  {report['actions_taken']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
