"""P3-PLN-05 Tier-3 transport: the forced-command gate in docs/p3/PLN_05_TIER3_PROCEDURE.md §4 (T3-R2, T3-R3).

The gate is documented, not installed (the procedure is NOT_RUN). Its text is the Owner's install source, so the
test runs exactly that block, extracted from the procedure, with only ``BASE`` pointed at a temporary directory.
It must refuse every way a compromised workstation could delete, overwrite, inject or escape, and it must accept
exactly the commands ``scripts/p3/offsite.py`` and the §6 pull issue. The injection that the first draft of the gate
allowed (``cd …; <cmd>; cd … && sha256sum …`` run through ``sh -c``) is kept as a negative control.
Local and synthetic: no ssh, no destination. PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "research"))

from p3 import backup, offsite  # noqa: E402

PROCEDURE = REPO / "docs" / "p3" / "PLN_05_TIER3_PROCEDURE.md"
STAMP = "20261026T033318Z"


def gate_source() -> str:
    text = PROCEDURE.read_text(encoding="utf-8")
    section = text[text.index("## 4. Authenticated transport"):text.index("## 5. Push and integrity")]
    blocks = re.findall(r"^   ```sh\n(.*?)^   ```$", section, flags=re.S | re.M)
    assert len(blocks) == 1, "§4 must hold exactly one gate block"
    return "\n".join(line[3:] if line.startswith("   ") else line for line in blocks[0].splitlines()) + "\n"


@pytest.fixture
def env(tmp_path):
    base = tmp_path / "srv" / "tlos-offsite"
    source = gate_source()
    assert source.count("BASE=/srv/tlos-offsite\n") == 1
    gate = tmp_path / "gate.sh"
    gate.write_text(source.replace("BASE=/srv/tlos-offsite\n", f"BASE={base}\n"), encoding="utf-8")
    return {"base": base, "gate": gate, "tmp": tmp_path}


def run(env, command: str) -> subprocess.CompletedProcess:
    return subprocess.run(["sh", str(env["gate"])], env={"SSH_ORIGINAL_COMMAND": command, "PATH": "/usr/bin:/bin"},
                          stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60, cwd=env["tmp"])


def make_set(env) -> Path:
    target = env["base"] / STAMP
    target.mkdir(parents=True)
    (target / "a.bin").write_bytes(b"artifact\n")
    digest = hashlib.sha256(b"artifact\n").hexdigest()
    (target / backup.SUMS).write_text(f"{digest}  a.bin\n")
    return target


def snapshot(directory: Path) -> dict[str, str]:
    return {p.relative_to(directory).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in directory.rglob("*") if p.is_file()}


def test_the_procedure_holds_one_gate_written_for_sh():
    assert gate_source().startswith("#!/bin/sh\n")
    assert "sh -c" not in gate_source(), "nothing in the gate may reach a shell"


def test_the_injection_the_first_draft_allowed_is_refused_and_runs_nothing(env):
    set_dir = make_set(env)
    marker = env["tmp"] / "PWNED"
    for command in (
        f"cd {env['base']}/x; touch {marker}; cd {set_dir} && sha256sum -c --quiet SHA256SUMS",
        f"cd {set_dir} && touch {marker} && cd {set_dir} && sha256sum -c --quiet SHA256SUMS",
        f"cd $(touch {marker}){set_dir} && sha256sum -c --quiet SHA256SUMS",
        f"test -d {set_dir} `touch {marker}`",
        f"test -d {set_dir} | touch {marker}",
        f"test -d {set_dir}\ntouch {marker}",
    ):
        result = run(env, command)
        assert result.returncode != 0 and "refused" in result.stderr, command
    assert not marker.exists()


@pytest.mark.parametrize("command", [
    "rm -rf {base}",
    "sh",
    "",
    "test -d {base}/../../etc",
    "test -d /etc",
    "test -d {base}/not-a-stamp",
    "mkdir -p /tmp/elsewhere",
    "mkdir -p {base}/{stamp}/../../x",
    "cd /etc && sha256sum -c --quiet SHA256SUMS",
    "rsync --server -logDtpre.iLsfxCIvu . {base}/{stamp}/",                          # push that may overwrite
    "rsync --server -logDtpre.iLsfxCIvu --ignore-existing --delete-during . {base}/{stamp}/",
    "rsync --server -logDtpre.iLsfxCIvu --delete-during . {base}/{stamp}/",
    "rsync --server --sender -logDtpre.iLsfxCIvu --remove-source-files . {base}/{stamp}/",
    "rsync --server -logDtpre.iLsfxCIvu --ignore-existing . /tmp/elsewhere/",
    "rsync --server --sender -logDtpre.iLsfxCIvu . {base}/../{stamp}/",
    "rsync --server --log-file=/tmp/x --ignore-existing . {base}/{stamp}/",
    "rsync --server --sender --server . {base}/{stamp}/",
])
def test_every_destructive_or_foreign_form_is_refused(env, command):
    set_dir = make_set(env)
    before = snapshot(env["base"])
    result = run(env, command.format(base=env["base"], stamp=STAMP))
    assert result.returncode != 0 and "refused" in result.stderr, (command, result.stderr)
    assert snapshot(env["base"]) == before
    assert set_dir.is_dir()


def test_the_verify_form_checks_the_set_and_reports_tampering(env):
    set_dir = make_set(env)
    command = f"cd {set_dir} && sha256sum -c --quiet SHA256SUMS"
    assert run(env, command).returncode == 0
    (set_dir / "a.bin").write_bytes(b"tampered\n")
    assert run(env, command).returncode != 0


def test_the_commands_offsite_push_issues_are_the_ones_the_gate_accepts(env, tmp_path):
    """Drive offsite.push with a runner that sends every ssh command through the gate, and every rsync through
    the local rsync with the gate standing in for the remote side, as ``command=`` would."""
    if shutil.which("rsync") is None:
        pytest.skip("rsync is not installed here")
    root = tmp_path / "root"
    root.mkdir()
    (root / "f.txt").write_text("x\n")
    backup.create_backup(tmp_path / "sets", roots={"r": root}, repos={}, stamp=STAMP)
    source = tmp_path / "sets" / STAMP
    rsh = tmp_path / "rsh.sh"   # ssh stand-in: drop the host, hand the remote command to the gate
    rsh.write_text(f'#!/bin/sh\nshift\nSSH_ORIGINAL_COMMAND="$*" exec sh {env["gate"]}\n')
    rsh.chmod(0o755)
    seen = []

    def runner(cmd):
        if cmd[0] == "ssh":
            seen.append(" ".join(cmd[2:]))
            return run(env, " ".join(cmd[2:]))
        assert cmd[0] == "rsync"
        seen.append(" ".join(cmd))
        return subprocess.run([cmd[0], "-e", str(rsh), *cmd[1:]], capture_output=True, text=True, timeout=120)

    first = offsite.push(source, f"h:{env['base']}", runner=runner)
    assert first["action"] == "PUSHED" and first["destination_verify"] == "PASS", (first, seen)
    again = offsite.push(source, f"h:{env['base']}", runner=runner)
    assert again["action"] == "VERIFIED_EXISTING" and again["destination_verify"] == "PASS"
    assert snapshot(env["base"] / STAMP) == snapshot(source)

    # §6 pull back into an empty scratch, through the gate (the --sender form)
    scratch = tmp_path / "scratch"
    pulled = subprocess.run(["rsync", "-a", "-e", str(rsh), f"h:{env['base']}/{STAMP}/", f"{scratch}/"],
                            capture_output=True, text=True, timeout=120)
    assert pulled.returncode == 0, pulled.stderr
    assert backup.verify_backup(scratch)["status"] == "PASS"


def test_a_push_cannot_overwrite_an_existing_artifact(env, tmp_path):
    if shutil.which("rsync") is None:
        pytest.skip("rsync is not installed here")
    set_dir = make_set(env)
    before = snapshot(set_dir)
    rogue = tmp_path / "rogue"
    rogue.mkdir()
    (rogue / "a.bin").write_bytes(b"replaced by a compromised workstation\n")
    rsh = tmp_path / "rsh.sh"
    rsh.write_text(f'#!/bin/sh\nshift\nSSH_ORIGINAL_COMMAND="$*" exec sh {env["gate"]}\n')
    rsh.chmod(0o755)
    forced = subprocess.run(["rsync", "-a", "-e", str(rsh), f"{rogue}/", f"h:{set_dir}/"],
                            capture_output=True, text=True, timeout=120)
    assert forced.returncode != 0 and "refused" in forced.stderr
    polite = subprocess.run(["rsync", "-a", "--ignore-existing", "-e", str(rsh), f"{rogue}/", f"h:{set_dir}/"],
                            capture_output=True, text=True, timeout=120)
    assert polite.returncode == 0, polite.stderr
    assert snapshot(set_dir) == before
