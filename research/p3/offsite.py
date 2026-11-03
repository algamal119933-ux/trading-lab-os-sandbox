"""P3-PLN-05 evidence durability: push a verified backup set to an independent target and prove it there.

P3_CONTRACT.md §3 PLN-05. Acceptance: HOST_LOSS_REDUNDANCY = PROVEN by restoring from the
independent host. This module moves and verifies the copy. The acceptance itself needs a target on
**another host**, and that is an Owner-provided resource.

Reuse (§10): rsync for transfer and sha256sum for verification on the destination. A remote
target (``user@host:/path``) is verified by running ``sha256sum -c`` **on the remote host** over ssh.
A copy the destination has not re-read is an assumption, not a copy (the same rule as Tier 1).

Append-only: a set already present at the destination is re-verified, never overwritten. A
destination copy whose bytes differ is refused, not reconciled.

Client-side encryption (Owner decision 2026-11-03, PLN_05_DESTINATION_DECISIONS.md §8): a set holds the
runtime ``.env`` and service volumes, so **only a sealed set may leave the host**. ``seal`` streams
``tar | gpg --encrypt`` to one recipient (the Owner's public key) into a directory named like the set, so the
destination gate and its ``sha256sum -c`` work unchanged on ciphertext. No plaintext copy of the set is ever
written, and sealing refuses when the matching secret key is present in the keyring it uses: the decryption key
lives off the host and is brought only to a restore drill (``open_sealed``). A remote push of an unsealed set is
refused. Reuse: GnuPG ships with Ubuntu (WRAP_EXISTING; AUDIT_BEFORE_USE per T3-R8).

PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from p3 import backup

SEAL_VERSION = "P3_OFFSITE_SEAL_V1"
SEALED_PAYLOAD = "SET.tar.gpg"
SEAL_RECORD = "SEAL_RECORD.json"
_FPR = re.compile(r"^[0-9A-F]{40}$")

Runner = Callable[[list[str]], subprocess.CompletedProcess]


class OffsiteError(Exception):
    pass


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=7200)


def is_remote(dest: str) -> bool:
    head = dest.split("/", 1)[0]
    return ":" in head and not dest.startswith("/")


def is_sealed(path: Path) -> bool:
    return (Path(path) / SEAL_RECORD).is_file()


def push(set_dir: Path, dest: str, *, runner: Runner = _run) -> dict:
    set_dir = Path(set_dir)
    remote = is_remote(dest)
    sealed = is_sealed(set_dir)
    if remote and not sealed:
        raise OffsiteError(f"{set_dir.name} is not sealed; only an encrypted set may leave the host "
                           "(PLN_05_DESTINATION_DECISIONS.md §8). Run seal first")
    local = verify_sealed(set_dir) if sealed else backup.verify_backup(set_dir)
    if local["status"] != "PASS":
        raise OffsiteError(f"source set {set_dir.name} does not verify locally; it is not pushed")
    name = set_dir.name
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
            "action": "VERIFIED_EXISTING" if exists else "PUSHED", "remote": remote, "sealed": sealed,
            "destination_verify": "PASS" if ok else "FAIL", "detail": verify.stdout.strip()[:300] + verify.stderr.strip()[:300],
            "host_loss_redundancy": "CANDIDATE" if ok and remote else "NOT_PROVEN",
            "real_money_authorized": False}


# --- client-side encryption -----------------------------------------------------------------------------------

def _gpg(gnupghome: Path, *args: str) -> list[str]:
    return ["gpg", "--homedir", str(gnupghome), "--batch", "--no-tty", "--quiet", *args]


def _fingerprint(recipient: str) -> str:
    fpr = recipient.replace(" ", "").upper()
    if not _FPR.match(fpr):
        raise OffsiteError("the recipient must be a full 40-hex OpenPGP fingerprint, never a name or short id")
    return fpr


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def seal(set_dir: Path, out_root: Path, recipient: str, gnupghome: Path, *, runner: Runner = _run) -> dict:
    """Encrypt a verified set to one public key, into ``out_root/<set name>``. Never writes plaintext."""
    set_dir, out_root, gnupghome = Path(set_dir), Path(out_root), Path(gnupghome)
    fpr = _fingerprint(recipient)
    if backup.verify_backup(set_dir)["status"] != "PASS":
        raise OffsiteError(f"source set {set_dir.name} does not verify locally; it is not sealed")
    name = set_dir.name
    target = out_root / name
    if target.exists():
        check = verify_sealed(target)
        return {"seal_version": SEAL_VERSION, "set": name, "sealed_dir": str(target), "action": "VERIFIED_EXISTING",
                "status": check["status"], "detail": check.get("detail", ""), "real_money_authorized": False}
    if runner(_gpg(gnupghome, "--with-colons", "--list-keys", fpr)).returncode != 0:
        raise OffsiteError(f"recipient {fpr} is not in the keyring {gnupghome}")
    if runner(_gpg(gnupghome, "--with-colons", "--list-secret-keys", fpr)).returncode == 0:
        raise OffsiteError(f"the secret key for {fpr} is in {gnupghome}; the decryption key must stay off this host")
    staging = out_root / f".{name}.incoming"
    if staging.exists():
        raise OffsiteError(f"{staging} exists (an interrupted seal); inspect and remove it by hand")
    staging.mkdir(parents=True)
    payload = staging / SEALED_PAYLOAD
    tar = subprocess.Popen(["tar", "--numeric-owner", "-cf", "-", "-C", str(set_dir.parent), name],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    enc = subprocess.run(_gpg(gnupghome, "--trust-model", "always", "--compress-algo", "none", "--encrypt",
                              "--recipient", fpr, "--output", str(payload)),
                         stdin=tar.stdout, capture_output=True, timeout=7200)
    tar.stdout.close()
    tar_err = tar.stderr.read().decode(errors="replace").strip()
    tar.wait()
    if tar.returncode != 0 or enc.returncode != 0 or not payload.is_file():
        shutil.rmtree(staging)
        raise OffsiteError(f"seal failed: tar {tar.returncode} {tar_err[:200]}; "
                           f"gpg {enc.returncode} {enc.stderr.decode(errors='replace').strip()[:200]}")
    record = {
        "record_type": SEAL_VERSION,
        "set": name,
        "created_utc": _now(),
        "set_sha256sums_sha256": backup.sha256_file(set_dir / backup.SUMS),
        "set_record_sha256": backup.sha256_file(set_dir / backup.RECORD),
        "payload": SEALED_PAYLOAD,
        "payload_sha256": backup.sha256_file(payload),
        "payload_bytes": payload.stat().st_size,
        "cipher": "OpenPGP public-key encryption (gpg), one recipient",
        "recipient_fingerprint": fpr,
        "plaintext_written": False,
        "real_money_authorized": False,
    }
    (staging / SEAL_RECORD).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    backup._write_manifest({SEALED_PAYLOAD: record["payload_sha256"],
                            SEAL_RECORD: backup.sha256_file(staging / SEAL_RECORD)}, staging / backup.SUMS)
    staging.rename(target)
    return {"seal_version": SEAL_VERSION, "set": name, "sealed_dir": str(target), "action": "SEALED",
            "status": verify_sealed(target)["status"], "recipient_fingerprint": fpr,
            "payload_sha256": record["payload_sha256"], "real_money_authorized": False}


def verify_sealed(sealed_dir: Path) -> dict:
    """Self-consistency of a sealed directory: exactly the payload and the record, both matching SHA256SUMS."""
    sealed_dir = Path(sealed_dir)
    try:
        sums = backup._read_manifest(sealed_dir / backup.SUMS)
        record = json.loads((sealed_dir / SEAL_RECORD).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"status": "FAIL", "detail": f"unreadable sealed set: {exc}"}
    if set(sums) != {SEALED_PAYLOAD, SEAL_RECORD}:
        return {"status": "FAIL", "detail": f"SHA256SUMS must list exactly {SEALED_PAYLOAD} and {SEAL_RECORD}"}
    bad = [rel for rel, digest in sums.items()
           if not (sealed_dir / rel).is_file() or backup.sha256_file(sealed_dir / rel) != digest]
    if bad:
        return {"status": "FAIL", "detail": f"mismatched: {bad}"}
    if record.get("record_type") != SEAL_VERSION or record.get("set") != sealed_dir.name \
            or record.get("payload_sha256") != sums[SEALED_PAYLOAD]:
        return {"status": "FAIL", "detail": "the seal record disagrees with the directory or its payload"}
    return {"status": "PASS", "detail": ""}


def open_sealed(sealed_dir: Path, scratch: Path, gnupghome: Path) -> dict:
    """Restore-drill step: decrypt into an empty scratch and prove it is the set that was sealed.

    Run on the drill machine with the Owner's secret key in ``gnupghome`` (never on the destination). The
    decrypted set is then given to the unchanged ``backup.py verify`` and ``drill``.
    """
    sealed_dir, scratch = Path(sealed_dir), Path(scratch)
    out = {"seal_version": SEAL_VERSION, "set": sealed_dir.name, "real_money_authorized": False}
    check = verify_sealed(sealed_dir)
    if check["status"] != "PASS":
        return {**out, "status": "FAIL", "stage": "sealed_integrity", "detail": check["detail"]}
    if scratch.exists() and any(scratch.iterdir()):
        raise OffsiteError(f"scratch {scratch} is not empty; a drill never restores over anything")
    scratch.mkdir(parents=True, exist_ok=True)
    record = json.loads((sealed_dir / SEAL_RECORD).read_text(encoding="utf-8"))
    name = record["set"]
    # Not --batch: a passphrase-protected Owner key must be able to ask through the agent's pinentry.
    dec = subprocess.Popen(["gpg", "--homedir", str(gnupghome), "--quiet", "--decrypt",
                            str(sealed_dir / SEALED_PAYLOAD)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        with tarfile.open(fileobj=dec.stdout, mode="r|") as archive:
            for member in archive:
                if member.name != name and not member.name.startswith(name + "/"):
                    raise OffsiteError(f"unexpected member {member.name!r} outside {name}/")
                archive.extract(member, scratch, filter="data")
    except (tarfile.TarError, OffsiteError) as exc:
        dec.kill()
        dec.wait()
        return {**out, "status": "FAIL", "stage": "decrypt", "detail": str(exc)[:300]}
    finally:
        dec.stdout.close()
    err = dec.stderr.read().decode(errors="replace").strip()
    dec.wait()
    if dec.returncode != 0:
        return {**out, "status": "FAIL", "stage": "decrypt", "detail": err[:300]}
    restored = scratch / name
    try:
        sums_ok = backup.sha256_file(restored / backup.SUMS) == record["set_sha256sums_sha256"]
        record_ok = backup.sha256_file(restored / backup.RECORD) == record["set_record_sha256"]
        verify = backup.verify_backup(restored)
    except (OSError, ValueError, KeyError) as exc:
        return {**out, "status": "FAIL", "stage": "restored_set", "detail": str(exc)[:300]}
    ok = sums_ok and record_ok and verify["status"] == "PASS"
    return {**out, "status": "PASS" if ok else "FAIL", "stage": "restored_set", "restored_set": str(restored),
            "matches_sealed_sums": sums_ok, "matches_sealed_record": record_ok, "set_verify": verify["status"]}

