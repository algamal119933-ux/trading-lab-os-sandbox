"""P3-PLN-05 client-side encryption before upload (Owner decision 2026-11-03, PLN_05_DESTINATION_DECISIONS.md §8).

Synthetic and offline. Two throwaway GnuPG homes stand in for the two machines: ``owner`` holds the secret key
(off the host), ``host`` holds only the public key. The properties under test:

- only a sealed set may go to a remote destination, and sealing never writes plaintext;
- sealing refuses when the decryption key is on the host, or the recipient is not a full fingerprint;
- the destination's ``sha256sum -c`` verifies the ciphertext unchanged;
- a drill opens the sealed set with the Owner's key and proves it is the set that was sealed;
- tampering, a wrong key or a foreign member is FAIL, never PASS; nothing is overwritten.

PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "research"))

from p3 import backup, offsite  # noqa: E402

STAMP = "20261103T120000Z"
CLI = REPO / "scripts" / "p3" / "offsite.py"


def _gpg(home: Path, *args: str, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(["gpg", "--homedir", str(home), "--batch", "--no-tty", "--quiet", *args],
                          capture_output=True, timeout=120, **kw)


def make_keys() -> dict:
    """An Owner keypair in ``owner`` and its public key alone in ``host``. Short paths: the agent socket has a limit."""
    homes = {}
    for role in ("owner", "host", "stranger"):
        home = Path(tempfile.mkdtemp(prefix=f"g{role[0]}", dir="/tmp"))
        home.chmod(0o700)
        homes[role] = home
    for role in ("owner", "stranger"):
        made = _gpg(homes[role], "--passphrase", "", "--pinentry-mode", "loopback", "--quick-gen-key",
                    f"tlos test {role} <{role}@example.invalid>", "default", "default", "never")
        assert made.returncode == 0, made.stderr
    listing = _gpg(homes["owner"], "--with-colons", "--list-keys").stdout.decode()
    fpr = next(line.split(":")[9] for line in listing.splitlines() if line.startswith("fpr:"))
    exported = _gpg(homes["owner"], "--export", fpr).stdout
    assert _gpg(homes["host"], "--import", input=exported).returncode == 0
    return {**homes, "fpr": fpr}


def drop_keys(keys: dict) -> None:
    for role in ("owner", "host", "stranger"):
        subprocess.run(["gpgconf", "--homedir", str(keys[role]), "--kill", "gpg-agent"], capture_output=True)
        shutil.rmtree(keys[role], ignore_errors=True)


@pytest.fixture(scope="module")
def keys():
    k = make_keys()
    yield k
    drop_keys(k)


@pytest.fixture
def backup_set(tmp_path) -> Path:
    root = tmp_path / "root"
    root.mkdir()
    (root / "runtime.env").write_text("SECRET_MARKER_7f3a=paper-only\n")
    backup.create_backup(tmp_path / "sets", roots={"r": root}, repos={}, stamp=STAMP)
    return tmp_path / "sets" / STAMP


def test_a_sealed_set_holds_only_ciphertext_and_verifies_with_the_unchanged_destination_check(tmp_path, keys,
                                                                                              backup_set):
    report = offsite.seal(backup_set, tmp_path / "sealed", keys["fpr"], keys["host"])
    sealed = tmp_path / "sealed" / STAMP
    assert report["action"] == "SEALED" and report["status"] == "PASS"
    assert sorted(p.name for p in sealed.iterdir()) == sorted([backup.SUMS, offsite.SEAL_RECORD, offsite.SEALED_PAYLOAD])
    payload = (sealed / offsite.SEALED_PAYLOAD).read_bytes()
    assert b"SECRET_MARKER_7f3a" not in payload and b"BACKUP_RECORD" not in payload
    record = json.loads((sealed / offsite.SEAL_RECORD).read_text())
    assert b"SECRET_MARKER_7f3a" not in (sealed / offsite.SEAL_RECORD).read_bytes()
    assert record["set_sha256sums_sha256"] == backup.sha256_file(backup_set / backup.SUMS)
    assert record["plaintext_written"] is False and record["real_money_authorized"] is False
    assert not list((tmp_path / "sealed").glob("*.incoming")) and not list((tmp_path / "sealed").rglob("*.tar"))
    # the destination runs exactly this (PLN_05_TIER3_PROCEDURE.md §4 gate, verify form)
    assert subprocess.run(["sha256sum", "-c", "--quiet", backup.SUMS], cwd=sealed).returncode == 0


def test_an_unsealed_set_never_goes_to_a_remote_destination(backup_set):
    calls = []
    with pytest.raises(offsite.OffsiteError, match="not sealed"):
        offsite.push(backup_set, "u@h:/srv/off", runner=lambda cmd: calls.append(cmd))
    assert calls == []


def test_a_sealed_set_is_pushed_with_the_commands_the_gate_accepts(tmp_path, keys, backup_set):
    offsite.seal(backup_set, tmp_path / "sealed", keys["fpr"], keys["host"])
    sealed = tmp_path / "sealed" / STAMP
    calls = []

    def runner(cmd):
        calls.append(cmd)
        rc = 1 if cmd[:2] == ["ssh", "u@h"] and cmd[2:4] == ["test", "-d"] else 0
        return subprocess.CompletedProcess(cmd, rc, "", "")
    report = offsite.push(sealed, "u@h:/srv/off", runner=runner)
    assert report["sealed"] is True and report["host_loss_redundancy"] == "CANDIDATE"
    assert ["rsync", "-a", "--ignore-existing", f"{sealed}/", f"u@h:/srv/off/{STAMP}/"] in calls
    assert calls[-1] == ["ssh", "u@h", f"cd /srv/off/{STAMP} && sha256sum -c --quiet SHA256SUMS"]


def test_sealing_refuses_when_the_decryption_key_is_on_the_host(tmp_path, keys, backup_set):
    with pytest.raises(offsite.OffsiteError, match="must stay off this host"):
        offsite.seal(backup_set, tmp_path / "sealed", keys["fpr"], keys["owner"])
    assert not (tmp_path / "sealed" / STAMP).exists()


@pytest.mark.parametrize("recipient", ["tlos test owner", "0xDEADBEEF", "", "G" * 40])
def test_the_recipient_must_be_a_full_fingerprint(tmp_path, keys, backup_set, recipient):
    with pytest.raises(offsite.OffsiteError, match="40-hex"):
        offsite.seal(backup_set, tmp_path / "sealed", recipient, keys["host"])


def test_an_unknown_recipient_or_an_unverified_set_is_never_sealed(tmp_path, keys, backup_set):
    with pytest.raises(offsite.OffsiteError, match="not in the keyring"):
        offsite.seal(backup_set, tmp_path / "sealed", "A" * 40, keys["host"])
    (backup_set / backup.SUMS).write_text("")
    with pytest.raises(offsite.OffsiteError, match="does not verify"):
        offsite.seal(backup_set, tmp_path / "sealed", keys["fpr"], keys["host"])
    assert not (tmp_path / "sealed" / STAMP).exists()


def test_an_existing_sealed_set_is_reverified_never_overwritten(tmp_path, keys, backup_set):
    offsite.seal(backup_set, tmp_path / "sealed", keys["fpr"], keys["host"])
    payload = tmp_path / "sealed" / STAMP / offsite.SEALED_PAYLOAD
    before = payload.read_bytes()
    again = offsite.seal(backup_set, tmp_path / "sealed", keys["fpr"], keys["host"])
    assert again["action"] == "VERIFIED_EXISTING" and again["status"] == "PASS"
    payload.write_bytes(before + b"x")
    tampered = offsite.seal(backup_set, tmp_path / "sealed", keys["fpr"], keys["host"])
    assert tampered["status"] == "FAIL" and payload.read_bytes() == before + b"x"


def test_the_drill_opens_the_sealed_set_with_the_owner_key_and_proves_it_is_the_same_set(tmp_path, keys,
                                                                                         backup_set):
    offsite.seal(backup_set, tmp_path / "sealed", keys["fpr"], keys["host"])
    opened = offsite.open_sealed(tmp_path / "sealed" / STAMP, tmp_path / "scratch", keys["owner"])
    assert opened["status"] == "PASS", opened
    assert opened["matches_sealed_sums"] and opened["matches_sealed_record"] and opened["set_verify"] == "PASS"
    restored = Path(opened["restored_set"])
    assert backup.verify_backup(restored)["status"] == "PASS"
    assert (restored / backup.SUMS).read_bytes() == (backup_set / backup.SUMS).read_bytes()


def test_the_host_keyring_cannot_open_its_own_seal(tmp_path, keys, backup_set):
    offsite.seal(backup_set, tmp_path / "sealed", keys["fpr"], keys["host"])
    for home in ("host", "stranger"):
        opened = offsite.open_sealed(tmp_path / "sealed" / STAMP, tmp_path / f"scratch-{home}", keys[home])
        assert opened["status"] == "FAIL" and opened["stage"] == "decrypt"


@pytest.mark.parametrize("what", ["payload", "record", "extra_file"])
def test_a_tampered_sealed_set_fails_before_decryption(tmp_path, keys, backup_set, what):
    offsite.seal(backup_set, tmp_path / "sealed", keys["fpr"], keys["host"])
    sealed = tmp_path / "sealed" / STAMP
    if what == "payload":
        data = bytearray((sealed / offsite.SEALED_PAYLOAD).read_bytes())
        data[len(data) // 2] ^= 0xFF
        (sealed / offsite.SEALED_PAYLOAD).write_bytes(bytes(data))
    elif what == "record":
        record = json.loads((sealed / offsite.SEAL_RECORD).read_text())
        record["set"] = "20990101T000000Z"
        (sealed / offsite.SEAL_RECORD).write_text(json.dumps(record))
    else:
        (sealed / backup.SUMS).write_text((sealed / backup.SUMS).read_text() + f"{'0' * 64}  extra.bin\n")
    assert offsite.verify_sealed(sealed)["status"] == "FAIL"
    opened = offsite.open_sealed(sealed, tmp_path / "scratch", keys["owner"])
    assert opened["status"] == "FAIL" and opened["stage"] == "sealed_integrity"
    assert not (tmp_path / "scratch").exists()


def test_a_consistently_rewritten_payload_is_caught_by_decryption_or_the_record(tmp_path, keys, backup_set):
    """An attacker who also rewrites SHA256SUMS and the record still cannot pass: the ciphertext's own integrity
    check (gpg MDC/AEAD) or the original-set hashes in the record stop it."""
    offsite.seal(backup_set, tmp_path / "sealed", keys["fpr"], keys["host"])
    sealed = tmp_path / "sealed" / STAMP
    data = bytearray((sealed / offsite.SEALED_PAYLOAD).read_bytes())
    data[-40] ^= 0x01
    (sealed / offsite.SEALED_PAYLOAD).write_bytes(bytes(data))
    record = json.loads((sealed / offsite.SEAL_RECORD).read_text())
    record["payload_sha256"] = backup.sha256_file(sealed / offsite.SEALED_PAYLOAD)
    (sealed / offsite.SEAL_RECORD).write_text(json.dumps(record))
    backup._write_manifest({offsite.SEALED_PAYLOAD: record["payload_sha256"],
                            offsite.SEAL_RECORD: backup.sha256_file(sealed / offsite.SEAL_RECORD)}, sealed / backup.SUMS)
    assert offsite.verify_sealed(sealed)["status"] == "PASS"   # self-consistent by construction
    assert offsite.open_sealed(sealed, tmp_path / "scratch", keys["owner"])["status"] == "FAIL"


def test_a_drill_never_restores_over_anything(tmp_path, keys, backup_set):
    offsite.seal(backup_set, tmp_path / "sealed", keys["fpr"], keys["host"])
    (tmp_path / "scratch").mkdir()
    (tmp_path / "scratch" / "keep.txt").write_text("x")
    with pytest.raises(offsite.OffsiteError, match="not empty"):
        offsite.open_sealed(tmp_path / "sealed" / STAMP, tmp_path / "scratch", keys["owner"])


def test_cli_exit_codes(tmp_path, keys, backup_set):
    def cli(*args):
        return subprocess.run([sys.executable, str(CLI), *map(str, args)], capture_output=True, text=True, timeout=300)
    sealed_root = tmp_path / "sealed"
    ok = cli("--seal", "--set", backup_set, "--out-root", sealed_root, "--recipient", keys["fpr"],
             "--gnupghome", keys["host"])
    assert ok.returncode == 0 and json.loads(ok.stdout)["status"] == "PASS", ok.stderr
    refused = cli("--seal", "--set", backup_set, "--out-root", tmp_path / "s2", "--recipient", keys["fpr"],
                  "--gnupghome", keys["owner"])
    assert refused.returncode == 2 and "off this host" in refused.stderr
    assert cli("--set", backup_set, "--dest", "u@h:/srv/off").returncode == 2
    opened = cli("--open", "--sealed", sealed_root / STAMP, "--scratch", tmp_path / "o", "--gnupghome", keys["owner"])
    assert opened.returncode == 0, opened.stderr
    wrong = cli("--open", "--sealed", sealed_root / STAMP, "--scratch", tmp_path / "w", "--gnupghome", keys["stranger"])
    assert wrong.returncode == 1
    assert cli("--seal", "--set", backup_set).returncode == 2   # missing arguments
