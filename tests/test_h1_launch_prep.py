"""H1 launch preparation: materialisation, the P2 entry gate, host placement, the launch card.

Nothing here starts a container, contacts an exchange, reads market data or touches P2.
The materialiser is exercised on synthetic bytes under synthetic pins, because the GPL
source is never in this repository. Its real pins are checked against both records.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
LAUNCH = REPO / "research" / "paper" / "h1" / "launch"
sys.path.insert(0, str(LAUNCH))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, LAUNCH / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mat = _load("h1_materialise")
gate = _load("h1_p2_entry_gate")
placement = _load("h1_host_placement")
card = _load("h1_launch_card")

CLEAN_ENV = {"PATH": "/usr/bin:/bin"}
NOW = datetime(2026, 10, 25, 0, 0, 0, tzinfo=timezone.utc)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# -- materialisation --------------------------------------------------------


def test_the_materialiser_pins_equal_upstream_pins_and_cohort():
    pins = json.loads((REPO / "research/external/upstream_pins.json").read_text())["sources"]["btc_strategy_lab"]
    by_path = {f["path"]: f for f in pins["files"]}
    cohort = json.loads((REPO / "research/paper/h1/package/cohort.json").read_text())
    assert pins["commit"] == mat.UPSTREAM_COMMIT == cohort["strategy"]["upstream_commit"]
    for name, (rel, digest, size) in mat.PINNED.items():
        assert by_path[rel]["sha256"] == digest and by_path[rel]["size_bytes"] == size, name
    assert mat.PINNED["EmaCross.py"][1] == cohort["strategy"]["sha256"]
    assert mat.PINNED["EmaCross.json"][1] == cohort["strategy"]["params_sha256"]
    assert mat.PINNED["LICENSE"][1] == cohort["strategy"]["license"]["license_sha256"]
    assert set(mat.PINNED) == {"EmaCross.py", "EmaCross.json", "LICENSE"}


@pytest.fixture
def source(tmp_path):
    """A synthetic btc_strategy_lab tree with an H2 file beside H1's, as on the host."""
    root = tmp_path / "src" / "btc_strategy_lab"
    (root / "user_data" / "strategies").mkdir(parents=True)
    contents = {"user_data/strategies/EmaCross.py": b"class EmaCross: pass\n",
                "user_data/strategies/EmaCross.json": b'{"ema_period": 600}\n',
                "LICENSE": b"GPL-3.0 synthetic\n",
                "user_data/strategies/EmaCrossFunding.py": b"h2\n"}
    for rel, data in contents.items():
        (root / rel).write_bytes(data)
    pinned = {Path(rel).name: (rel, sha(data), len(data)) for rel, data in contents.items()
              if "Funding" not in rel}
    return root, pinned


def test_materialisation_copies_exactly_three_verified_files(source, tmp_path):
    root, pinned = source
    record = mat.materialise(root, tmp_path / "ws", pinned=pinned, environ=CLEAN_ENV, now=NOW)
    strategy = Path(record["H1_PAPER_STRATEGY_DIR"])
    assert sorted(p.name for p in strategy.iterdir()) == ["EmaCross.json", "EmaCross.py", "LICENSE"]
    assert strategy == tmp_path / "ws" / "h1-materialise-20261025T000000Z" / "btc_strategy_lab/user_data/strategies"
    for name, (_rel, digest, _size) in pinned.items():
        assert record["files"][name]["sha256"] == digest == sha((strategy / name).read_bytes())
    on_disk = json.loads((strategy.parents[2] / mat.RECORD_NAME).read_text())
    assert on_disk == record and record["real_money_authorized"] is False
    assert record["gpl_vendored_into_tlos"] is False


def test_a_mismatched_source_fails_closed_and_leaves_nothing(source, tmp_path):
    root, pinned = source
    (root / "LICENSE").write_bytes(b"tampered\n")
    with pytest.raises(mat.MaterialisationError, match="LICENSE"):
        mat.materialise(root, tmp_path / "ws", pinned=pinned, environ=CLEAN_ENV, now=NOW)
    assert not (tmp_path / "ws").exists() or not any((tmp_path / "ws").iterdir())


def test_a_symlinked_source_is_refused(source, tmp_path):
    root, pinned = source
    real = tmp_path / "elsewhere.py"
    real.write_bytes((root / "user_data/strategies/EmaCross.py").read_bytes())
    (root / "user_data/strategies/EmaCross.py").unlink()
    (root / "user_data/strategies/EmaCross.py").symlink_to(real)
    with pytest.raises(mat.MaterialisationError, match="symlink"):
        mat.materialise(root, tmp_path / "ws", pinned=pinned, environ=CLEAN_ENV, now=NOW)


def test_a_credentialed_environment_is_refused(source, tmp_path):
    root, pinned = source
    with pytest.raises(mat.MaterialisationError, match="credential-free"):
        mat.materialise(root, tmp_path / "ws", pinned=pinned,
                        environ={**CLEAN_ENV, "GITHUB_TOKEN": "x"}, now=NOW)  # allowlist-secret


def test_a_workspace_is_never_reused(source, tmp_path):
    root, pinned = source
    mat.materialise(root, tmp_path / "ws", pinned=pinned, environ=CLEAN_ENV, now=NOW)
    with pytest.raises(mat.MaterialisationError, match="never reused"):
        mat.materialise(root, tmp_path / "ws", pinned=pinned, environ=CLEAN_ENV, now=NOW)


def test_a_workspace_inside_a_git_worktree_or_a_p2_path_is_refused(source, tmp_path):
    root, pinned = source
    with pytest.raises(mat.MaterialisationError, match="git worktree"):
        mat.materialise(root, REPO / "tmp-never-created", pinned=pinned, environ=CLEAN_ENV, now=NOW)
    with pytest.raises(mat.MaterialisationError, match="P2 path"):
        mat.materialise(root, tmp_path / "fp-control-3", pinned=pinned, environ=CLEAN_ENV, now=NOW)


def test_the_real_pins_refuse_synthetic_bytes(source, tmp_path):
    root, _ = source
    with pytest.raises(mat.MaterialisationError, match="source verification failed"):
        mat.materialise(root, tmp_path / "ws", environ=CLEAN_ENV, now=NOW)


def test_the_cli_refuses_without_env_i(source, tmp_path):
    root, _ = source
    result = subprocess.run([sys.executable, "-I", str(LAUNCH / "h1_materialise.py"), "--source", str(root),
                             "--workspace-root", str(tmp_path / "ws")],
                            capture_output=True, text=True, env={**CLEAN_ENV, "SOME_TOKEN": "x"})
    assert result.returncode == 1 and "H1_MATERIALISATION = FAIL" in result.stdout
    assert "credential-free" in result.stderr


def test_the_materialiser_uses_the_standard_library_only():
    text = (LAUNCH / "h1_materialise.py").read_text()
    imports = {line.split()[1].split(".")[0] for line in text.splitlines()
               if line.startswith(("import ", "from ")) and "__future__" not in line}
    assert imports <= {"argparse", "hashlib", "json", "os", "shutil", "subprocess", "sys", "datetime", "pathlib"}


# -- the P2 entry gate, on a synthetic repository -----------------------------


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                          capture_output=True, text=True, check=True).stdout.strip()


CLOSED_ROW = {"role": "FP-CONTROL-3", "cohort_id": "FP-CONTROL-3-X", "status": "CLOSED",
              "closed_utc": "2026-10-24T12:01:14Z"}
RUNNING_ROW = {**CLOSED_ROW, "status": "RUNNING", "closed_utc": None}


def closure_text(**overrides) -> str:
    fields = {"P2_TERMINAL_STATUS": "INCONCLUSIVE / INSUFFICIENT", "COHORT_ID": "FP-CONTROL-3-X",
              "EVIDENCE_VALID": "YES", "EVIDENCE_CHAINS": "INTACT", "RECONCILIATION": "PASS",
              "UNRESOLVED_INTEGRITY_DEFECTS": "NONE", "UNRESOLVED_TECHNICAL_DEFECTS": "NONE",
              "SAFETY_FAILURES": "NONE", "REAL_MONEY_AUTHORIZED": "NO", **overrides}
    body = "\n".join(f"{k} = {v}" for k, v in fields.items() if v is not None)
    return f"# P2 closure\n\n```text\n{body}\n```\n"


class Repo:
    """main, with each change brought in by a two-parent merge from a side branch."""

    def __init__(self, path: Path):
        self.path = path
        path.mkdir()
        _git(path, "init", "-q", "-b", "main")
        self.write({gate.PACKAGE_MANIFEST: (REPO / gate.PACKAGE_MANIFEST).read_bytes(),
                    gate.REGISTRY: self.registry(RUNNING_ROW, active=True),
                    gate.DIGESTS: json.dumps({"archives": []}).encode()}, merge=False)

    @staticmethod
    def registry(row: dict, active: bool) -> bytes:
        return json.dumps({"instances": [row], "fp_run_active": active, "real_money_authorized": False}).encode()

    def write(self, files: dict[str, bytes], merge: bool = True) -> None:
        if merge:
            _git(self.path, "checkout", "-q", "-b", "side")
        for rel, data in files.items():
            target = self.path / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        _git(self.path, "add", "-A")
        _git(self.path, "commit", "-q", "-m", "change")
        if merge:
            _git(self.path, "checkout", "-q", "main")
            _git(self.path, "merge", "-q", "--no-ff", "-m", "merge", "side")
            _git(self.path, "branch", "-q", "-D", "side")

    def amend_g6(self) -> None:
        self.write({gate.AMENDMENTS: (REPO / gate.AMENDMENTS).read_bytes()})

    def close_p2(self, text: str | None = None, row: dict = CLOSED_ROW, archive: bool = True) -> None:
        self.write({gate.CLOSURE: (text or closure_text()).encode(),
                    gate.REGISTRY: self.registry(row, active=row["status"] != "CLOSED"),
                    gate.DIGESTS: json.dumps({"archives": [{"cohort_id": "FP-CONTROL-3-X"}] if archive else []}).encode()})

    def evaluate(self) -> dict:
        return gate.evaluate("main", repo=self.path)


@pytest.fixture
def repo(tmp_path):
    return Repo(tmp_path / "repo")


def test_this_repository_is_waiting_until_a_closure_record_exists():
    result = gate.evaluate("HEAD")
    if not (REPO / gate.CLOSURE).exists():
        assert result["verdict"] == gate.WAITING, result["reasons"]
    else:
        assert result["verdict"] in (gate.ELIGIBLE, gate.BLOCKED)


def test_no_closure_record_is_waiting(repo):
    assert repo.evaluate()["verdict"] == gate.WAITING


def test_closed_pass_is_eligible_without_the_amendment(repo):
    repo.close_p2(closure_text(P2_TERMINAL_STATUS="CLOSED / PASS"))
    result = repo.evaluate()
    assert result["verdict"] == gate.ELIGIBLE, result["reasons"]


def test_inconclusive_is_eligible_only_with_the_amendment_merged_first(repo):
    repo.amend_g6()
    repo.close_p2()
    result = repo.evaluate()
    assert result["verdict"] == gate.ELIGIBLE, result["reasons"]


def test_inconclusive_without_the_amendment_is_blocked(repo):
    repo.close_p2()
    assert repo.evaluate()["verdict"] == gate.BLOCKED


def test_an_amendment_merged_after_the_closure_is_blocked(repo):
    repo.close_p2()
    repo.amend_g6()
    result = repo.evaluate()
    assert result["verdict"] == gate.BLOCKED and any("before the P2 closure" in r for r in result["reasons"])


def test_closed_fail_is_blocked(repo):
    repo.amend_g6()
    repo.close_p2(closure_text(P2_TERMINAL_STATUS="CLOSED / FAIL"))
    assert repo.evaluate()["verdict"] == gate.BLOCKED


@pytest.mark.parametrize("field,value", [
    ("EVIDENCE_VALID", "NO"), ("EVIDENCE_CHAINS", "BROKEN"), ("RECONCILIATION", "FAIL"),
    ("UNRESOLVED_INTEGRITY_DEFECTS", "1"), ("UNRESOLVED_TECHNICAL_DEFECTS", "1"),
    ("SAFETY_FAILURES", "1"), ("REAL_MONEY_AUTHORIZED", "YES"), ("RECONCILIATION", None),
    ("P2_TERMINAL_STATUS", "PASS-ISH"), ("COHORT_ID", "FP-CONTROL-9-Y"),
])
def test_every_failing_or_missing_closure_field_blocks(repo, field, value):
    repo.amend_g6()
    repo.close_p2(closure_text(**{field: value}))
    assert repo.evaluate()["verdict"] == gate.BLOCKED


def test_a_closure_committed_without_a_merge_is_blocked(repo):
    repo.amend_g6()
    repo.write({gate.CLOSURE: closure_text().encode(), gate.REGISTRY: Repo.registry(CLOSED_ROW, False),
                gate.DIGESTS: json.dumps({"archives": [{"cohort_id": "FP-CONTROL-3-X"}]}).encode()}, merge=False)
    result = repo.evaluate()
    assert result["verdict"] == gate.BLOCKED and any("Owner-merged" in r for r in result["reasons"])


def test_a_closure_edited_after_its_merge_is_blocked(repo):
    repo.amend_g6()
    repo.close_p2()
    repo.write({gate.CLOSURE: (closure_text() + "\nlater edit\n").encode()}, merge=False)
    assert repo.evaluate()["verdict"] == gate.BLOCKED


def test_a_closure_while_the_registry_still_runs_is_blocked(repo):
    repo.amend_g6()
    repo.close_p2(row=RUNNING_ROW)
    assert repo.evaluate()["verdict"] == gate.BLOCKED


def test_an_unpublished_archive_is_blocked(repo):
    repo.amend_g6()
    repo.close_p2(archive=False)
    assert repo.evaluate()["verdict"] == gate.BLOCKED


def test_a_moved_h1_package_blocks_even_while_waiting(repo):
    repo.write({gate.PACKAGE_MANIFEST: b"moved\n"})
    assert repo.evaluate()["verdict"] == gate.BLOCKED


def test_conflicting_duplicate_fields_block(repo):
    repo.amend_g6()
    text = closure_text().replace("RECONCILIATION = PASS", "RECONCILIATION = PASS\nRECONCILIATION = FAIL")
    repo.close_p2(text)
    assert repo.evaluate()["verdict"] == gate.BLOCKED


def test_the_gate_pins_the_merged_records():
    assert sha((REPO / gate.PACKAGE_MANIFEST).read_bytes()) == gate.H1_PACKAGE_DIGEST
    assert sha((REPO / gate.AMENDMENTS).read_bytes()) == gate.G6_AMENDMENTS_SHA256
    for path, digest in card.G11_RECORDS.items():
        assert sha((REPO / path).read_bytes()) == digest, path
    assert sha((REPO / card.WINDOW_AMENDMENT).read_bytes()) == card.WINDOW_AMENDMENT_SHA256


def test_the_window_amendment_is_operational_only_and_leaves_the_package_frozen():
    text = (REPO / card.WINDOW_AMENDMENT).read_text()
    assert "END_UTC              = ACTIVATION_UTC + 10 days" in text
    assert "EDGE_EVIDENCE is\n                              NOT_EVALUATED" in text
    assert gate.H1_PACKAGE_DIGEST in text and "REAL_MONEY_AUTHORIZED = NO" in text
    assert sha((REPO / gate.PACKAGE_MANIFEST).read_bytes()) == gate.H1_PACKAGE_DIGEST


def test_an_unmerged_window_amendment_is_not_adopted():
    built = card.build_card("HEAD", None, None, None)
    row = built["rows"]["H1_WINDOW_AMENDMENT"]
    assert row["value"] == "NOT_ADOPTED" and not row["pass"] and "H1_WINDOW_AMENDMENT" in built["not_pass"]


# -- host placement -----------------------------------------------------------


def test_placement_passes_on_a_quiet_host():
    assert placement.evaluate(["other|running|misc"], ["bridge"], False, False)["verdict"] == "PASS"


def test_a_running_p2_container_blocks_without_the_exception():
    for line in ("fp-control-3-freqtrade|running|", "freqtrade|running|trading_lab_os_final"):
        result = placement.evaluate([line], ["bridge"], False, False)
        assert result["verdict"] == "BLOCKED", line


def test_a_stopped_p2_container_does_not_block():
    assert placement.evaluate(["fp-control-3-freqtrade|exited|"], [], False, False)["verdict"] == "PASS"


def test_the_exception_only_applies_when_merged_and_never_clears_other_checks():
    p2 = ["fp-control-3-freqtrade|running|"]
    assert placement.evaluate(p2, [], False, True)["verdict"] == "PASS_ISOLATED_SAME_HOST"
    assert placement.evaluate(p2, [], True, True)["verdict"] == "BLOCKED"


def test_an_existing_h1_runtime_or_busy_port_blocks():
    assert placement.evaluate([f"{placement.H1_CONTAINER}|exited|"], [], False, False)["verdict"] == "BLOCKED"
    assert placement.evaluate([], [placement.H1_NETWORK], False, False)["verdict"] == "BLOCKED"
    assert placement.evaluate([], [], True, False)["verdict"] == "BLOCKED"


def test_an_unreadable_daemon_is_unproven():
    assert placement.evaluate(None, [], False, False)["verdict"] == "UNPROVEN"


# -- the launch card ----------------------------------------------------------


def test_the_card_defaults_to_deny_here():
    built = card.build_card("HEAD", None, None, None)
    assert built["OWNER_DECISION_DEFAULT"] == "DENY"
    assert built["REAL_MONEY_AUTHORIZED"] == "NO"
    assert {"P2_TERMINAL_STATUS", "SOURCE_SHA256_STATUS", "MATERIALISATION_PREFLIGHT",
            "SECOND_EVIDENCE_STORE", "H1_WINDOW_AMENDMENT"} <= set(built["not_pass"])
    assert built["rows"]["H1_PACKAGE_DIGEST"]["pass"] and built["rows"]["DRY_RUN"]["pass"]


def test_one_failing_row_is_enough_to_deny(monkeypatch):
    rows_pass = {"verdict": gate.ELIGIBLE, "reasons": [], "p2_terminal_status": "CLOSED / PASS",
                 "h1_package_digest": gate.H1_PACKAGE_DIGEST}
    built = card.build_card("HEAD", None, None, None, entry=rows_pass,
                            host={"verdict": "PASS", "reasons": []})
    assert built["OWNER_DECISION_DEFAULT"] == "DENY" and "P2_TERMINAL_STATUS" not in built["not_pass"]


def test_the_launch_command_is_dry_run_paper_only():
    text = card.launch_command("/s", "/l")
    assert "docker-compose.h1-paper.yml" in text and "env -i" in text and "COHORT_START" in text
    for forbidden in ("dry_run=false", "--dry-run false", "key=", "secret=", "live"):
        assert forbidden not in text.lower()


def test_nothing_in_the_launch_dir_starts_a_runtime():
    for path in LAUNCH.glob("*.py"):
        text = path.read_text()
        assert '"up"' not in text and "'up'" not in text and "subprocess.run([\"docker\", \"compose\"" not in text, path
