#!/usr/bin/env python3
"""Is there a second physical device on this host, and is it healthy enough to use?

    scripts/second_device_discovery.py
    scripts/second_device_discovery.py --json -o artifacts/second-device.json

P2 contract section 8. Tier 1 puts a lane out of container reach; Tier 2 makes a
loss provable and bounded. Neither survives the loss of a single drive, and this
workstation already has a second one — so when it is available and healthy, the
sealed evidence is copied onto it.

WHAT THAT IS, AND WHAT IT IS NOT. Two drives in one chassis share a power
supply, a room, and a thief. A copy on the second device survives the failure of
either single drive and nothing else, so every record it produces carries, on
its face:

    SAME_HOST_SECOND_DEVICE = YES
    HOST_LOSS_REDUNDANCY    = NOT_PROVEN

It is **not called Tier 3**, here or anywhere. Independent-host storage, restore
qualification and disaster recovery are P3 operational-hardening scope, and no
cloud or NAS provisioning is required for P2.

This tool DISCOVERS. It does not format, mount, unmount, partition, purchase,
provision, create credentials, or contact any remote service. It reports what is
already present, and an unavailable or unhealthy device is a recorded fact
rather than a blocker: Tier 1 and Tier 2 are unconditional and the cohort
proceeds on them.

Exit code is always 0. Discovery that found nothing is a finding, not an error.

PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

AVAILABLE = "AVAILABLE"
UNAVAILABLE = "UNAVAILABLE"
UNHEALTHY = "UNHEALTHY"

SAME_HOST_SECOND_DEVICE_LABEL = "SAME_HOST_SECOND_DEVICE"
HOST_LOSS_REDUNDANCY = "NOT_PROVEN"

# Enough room to hold a cohort's sealed evidence several times over. An evidence
# lane is ledgers, logs and a small sqlite file; a gigabyte is generous, and a
# device with less than that is not somewhere to put evidence.
MIN_FREE_BYTES = 1 * 1024**3

# Filesystem types that are views onto kernel state or onto the same storage,
# never a second physical device.
VIRTUAL_FSTYPES = frozenset({
    "proc", "sysfs", "devtmpfs", "devpts", "tmpfs", "cgroup", "cgroup2", "pstore",
    "bpf", "securityfs", "debugfs", "tracefs", "configfs", "fusectl", "mqueue",
    "hugetlbfs", "autofs", "binfmt_misc", "efivarfs", "ramfs", "squashfs", "overlay",
    "nsfs", "fuse.portal", "fuse.gvfsd-fuse",
})


def _block_device_of(source: str) -> str | None:
    """The whole-disk name behind a partition, e.g. /dev/sda2 -> sda.

    Read from /sys, because that is where the kernel says which partitions
    belong to which physical disk. Two partitions of ONE disk are two
    filesystems and one device, and treating them as two would be exactly the
    conflation this whole section exists to prevent.
    """
    if not source.startswith("/dev/"):
        return None
    name = source[len("/dev/"):]
    for disk in sorted(Path("/sys/block").iterdir()) if Path("/sys/block").is_dir() else []:
        if disk.name == name:
            return disk.name
        if (disk / name).is_dir():
            return disk.name
    return None


def _device_model(disk: str | None) -> str:
    if not disk:
        return ""
    for attribute in ("device/model", "device/name"):
        path = Path("/sys/block") / disk / attribute
        if path.is_file():
            try:
                return path.read_text(encoding="utf-8", errors="replace").strip()
            except OSError:
                continue
    return ""


def _is_rotational(disk: str | None) -> bool | None:
    if not disk:
        return None
    path = Path("/sys/block") / disk / "queue/rotational"
    try:
        return path.read_text(encoding="utf-8").strip() == "1"
    except OSError:
        return None


def _read_only(disk: str | None) -> bool | None:
    if not disk:
        return None
    path = Path("/sys/block") / disk / "ro"
    try:
        return path.read_text(encoding="utf-8").strip() == "1"
    except OSError:
        return None


def _writable(target: Path) -> tuple[bool, str]:
    """Can this process actually create a file here? Asked, never assumed.

    A mount can be present, have free space, and still be read-only or owned by
    someone else — and an evidence copy that silently fails to be written is
    worse than one that was never attempted.
    """
    probe = target / f".fp_write_probe_{os.getpid()}"
    try:
        probe.write_text("probe\n", encoding="utf-8")
        probe.unlink()
        return True, "a test file was created and removed"
    except OSError as exc:
        return False, str(exc)[:200]


def _mounts() -> list[dict]:
    try:
        text = Path("/proc/self/mounts").read_text(encoding="utf-8")
    except OSError:
        return []
    out = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        source, target, fstype = parts[0], parts[1].replace("\\040", " "), parts[2]
        if fstype in VIRTUAL_FSTYPES or not source.startswith("/dev/"):
            continue
        out.append({"source": source, "target": target, "fstype": fstype})
    return out


def discover(repo_root: Path | None = None) -> dict:
    root = Path(repo_root or REPO_ROOT)
    try:
        repo_stat = os.stat(root)
    except OSError:
        repo_stat = None

    repo_mount, candidates = None, []
    for mount in _mounts():
        try:
            stat = os.stat(mount["target"])
            usage = shutil.disk_usage(mount["target"])
        except OSError:
            continue
        disk = _block_device_of(mount["source"])
        entry = {
            **mount,
            "block_device": disk,
            "model": _device_model(disk),
            "rotational": _is_rotational(disk),
            "device_read_only": _read_only(disk),
            "free_bytes": usage.free,
            "total_bytes": usage.total,
            "st_dev": stat.st_dev,
        }
        if repo_stat is not None and stat.st_dev == repo_stat.st_dev:
            repo_mount = entry
        candidates.append(entry)

    repo_disk = repo_mount["block_device"] if repo_mount else None

    # Fail closed. If the repository's own physical disk cannot be identified,
    # nothing can be shown to be a DIFFERENT one — and offering a candidate
    # anyway could hand back the repository's own drive as its own redundancy,
    # which is precisely the conflation this whole section exists to prevent.
    # This is the normal case when the checkout sits on tmpfs or an overlay,
    # e.g. a reproduction clone under /tmp.
    if repo_disk is None:
        return _report(
            root, repo_disk, [], None,
            unresolved=(
                "the repository's physical disk could not be identified from /proc/self/mounts "
                f"and /sys/block ({root}); no device can be shown to be a different one, so none "
                "is offered"
            ),
        )

    seconds = []
    for entry in candidates:
        if entry["block_device"] == repo_disk:
            continue  # same physical disk, however many partitions it has
        if entry["block_device"] is None:
            continue
        writable, detail = _writable(Path(entry["target"]))
        problems = []
        if entry["device_read_only"]:
            problems.append("the kernel reports the device read-only")
        if not writable:
            problems.append(f"not writable by this process: {detail}")
        if entry["free_bytes"] < MIN_FREE_BYTES:
            problems.append(
                f"only {entry['free_bytes'] // (1024**2)} MiB free; at least "
                f"{MIN_FREE_BYTES // (1024**3)} GiB is required"
            )
        seconds.append({
            **entry,
            "writable": writable,
            "write_probe": detail,
            "health": UNHEALTHY if problems else AVAILABLE,
            "problems": problems,
        })

    usable = [entry for entry in seconds if entry["health"] == AVAILABLE]
    chosen = max(usable, key=lambda e: e["free_bytes"]) if usable else None
    return _report(root, repo_disk, seconds, chosen)


def _report(root: Path, repo_disk: str | None, seconds: list[dict], chosen: dict | None,
            *, unresolved: str = "") -> dict:
    return {
        "second_device_discovery_version": "FP_SECOND_DEVICE_V1",
        "observed_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "host": os.uname().nodename if hasattr(os, "uname") else "",
        "repository": str(root),
        "repository_block_device": repo_disk,
        "repository_model": _device_model(repo_disk),
        "candidates": seconds,
        "selected": chosen,
        "status": AVAILABLE if chosen else UNAVAILABLE,
        "unresolved": unresolved,
        SAME_HOST_SECOND_DEVICE_LABEL: "YES" if chosen else "NO",
        "host_loss_redundancy": HOST_LOSS_REDUNDANCY,
        "provisioned": False,
        "actions_taken": (
            "NONE. This tool discovers. Formatting, mounting, partitioning, purchasing, "
            "provisioning, credential creation and any outbound transfer were not performed "
            "and are not P2 scope."
        ),
        "claim": (
            "A copy on this device survives the failure of either single drive and nothing "
            "else. Two drives in one chassis share a power supply, a room, and a thief."
        ),
        "may_not_claim": (
            "host loss · workstation destruction · theft · host-wide filesystem or OS "
            "catastrophe. Independent-host storage, restore qualification and disaster "
            "recovery are P3 operational-hardening scope."
        ),
        "blocks_t0": False,
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
        print(f"SECOND-DEVICE DISCOVERY — {report['host']}")
        print(f"  repository on   {report['repository_block_device']} "
              f"({report['repository_model']})")
        for entry in report["candidates"]:
            print(f"  [{entry['health']:>11}] {entry['target']}  "
                  f"{entry['block_device']} ({entry['model']}, {entry['fstype']}, "
                  f"{entry['free_bytes'] // (1024**3)} GiB free)")
            for problem in entry["problems"]:
                print(f"        {problem}")
        print()
        if report["selected"]:
            print(f"SELECTED  {report['selected']['target']} on "
                  f"{report['selected']['block_device']}")
        print(f"{SAME_HOST_SECOND_DEVICE_LABEL} = {report[SAME_HOST_SECOND_DEVICE_LABEL]}")
        print(f"HOST_LOSS_REDUNDANCY = {report['host_loss_redundancy']}")
        print(f"  {report['may_not_claim']}")
        print(f"  {report['actions_taken']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
