"""P3-PLN-05 evidence durability: push a verified backup set to an independent target and prove it there.

P3_CONTRACT.md §3 PLN-05. Acceptance: HOST_LOSS_REDUNDANCY = PROVEN by restoring from the
independent host. This module moves and verifies the copy. The acceptance itself needs a target on
**another host**, and that is an Owner-provided resource.

Reuse (§10): rsync for transfer and sha256sum for verification on the destination. A remote
target (``user@host:/path``) is verified by running ``sha256sum -c`` **on the remote host** over ssh.
A copy the destination has not re-read is an assumption, not a copy (the same rule as Tier 1).

Append-only: a set already present at the destination is re-verified, never overwritten. A
destination copy whose bytes differ is refused, not reconciled.

PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

from p3 import backup

Runner = Callable[[list[str]], subprocess.CompletedProcess]


class OffsiteError(Exception):
    pass


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=7200)


def is_remote(dest: str) -> bool:
    head = dest.split("/", 1)[0]
    return ":" in head and not dest.startswith("/")


def push(set_dir: Path, dest: str, *, runner: Runner = _run) -> dict:
    set_dir = Path(set_dir)
    local = backup.verify_backup(set_dir)
    if local["status"] != "PASS":
        raise OffsiteError(f"source set {set_dir.name} does not verify locally; it is not pushed")
    name = set_dir.name
    remote = is_remote(dest)
    host, _, base = dest.partition(":") if remote else ("", "", dest)
    target = f"{base.rstrip('/')}/{name}"
    exists = (runner(["ssh", host, "test", "-d", target]).returncode == 0) if remote else Path(target).is_dir()
    if not exists:
        if remote:
            mk = runner(["ssh", host, "mkdir", "-p", base])
        else:
            Path(base).mkdir(parents=True, exist_ok=True)
            mk = subprocess.CompletedProcess([], 0, "", "")
        if mk.returncode != 0:
            raise OffsiteError(f"cannot create {base}: {mk.stderr.strip()[:200]}")
        sync = runner(["rsync", "-a", "--ignore-existing", f"{set_dir}/", f"{dest.rstrip('/')}/{name}/"])
        if sync.returncode != 0:
            raise OffsiteError(f"rsync failed: {sync.stderr.strip()[:300]}")
    check_cmd = ["sha256sum", "-c", "--quiet", backup.SUMS]
    if remote:
        verify = runner(["ssh", host, f"cd {target} && " + " ".join(check_cmd)])
    else:
        verify = subprocess.run(check_cmd, cwd=target, capture_output=True, text=True)
    ok = verify.returncode == 0
    return {"offsite_version": "P3_OFFSITE_V1", "set": name, "destination": f"{dest.rstrip('/')}/{name}",
            "action": "VERIFIED_EXISTING" if exists else "PUSHED", "remote": remote,
            "destination_verify": "PASS" if ok else "FAIL", "detail": verify.stdout.strip()[:300] + verify.stderr.strip()[:300],
            "host_loss_redundancy": "CANDIDATE" if ok and remote else "NOT_PROVEN",
            "real_money_authorized": False}
