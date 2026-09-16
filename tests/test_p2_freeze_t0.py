"""freeze_t0: the one act that turns a registered instance into a cohort.

Contract section 6 puts T0 authority in a **merged record**, not a token, and
the reasoning is the whole design: a secret can be guessed, leaked, copied out
of a transcript, or supplied by whoever is sitting at the keyboard; a merge
cannot. ``docs/p2/OWNER_T0_AUTHORIZATION.md`` is therefore read from git at HEAD
rather than from the working tree, and its absence is the default — which makes
refusal the default.

Its absence was also, for the whole of S1-S3b, a *fact about this repository*,
and several tests here asserted that fact as though it were the law. It is not:
the Owner granting authority is the lawful end of that default, and a test that
fails the moment the mechanism it guards is lawfully used was describing the day
it was written. What is durable is the shape of authority, not its absence — so
the negative controls below construct the absence they need in a disposable
clone, and the assertion against this repository asks whether any authorization
at HEAD is *lawful*, not whether one exists.

Every test here drives the real decision function. The git layer is scripted so
that each test moves exactly one fact and everything else stays lawful;
otherwise a refusal could come from the wrong condition and the test would still
be green. And after each refusal the committed registry is compared byte for
byte, because contract section 13 requires it of every authority-bearing
mechanism: a gate that refuses but leaves a half-written registry behind has
done more damage than one that never ran.
"""

from __future__ import annotations

import copy
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import freeze_t0
from fp import registry_law as fp_law
from fp import semantic_identity as fp_semantic

REGISTRY_PATH = Path("research/fp/records/forward_paper_cohort_registry.json")
ROLE = "FP-CONTROL-2"
HEAD = "a" * 40
PARENT_ONE, PARENT_TWO = "b" * 40, "c" * 40
MQ = "d" * 40
CERT = "e" * 64
T0 = "2026-09-20T14:00:00Z"


def _future(days: int = 3) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _past() -> str:
    return (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")


def authorization(**overrides) -> str:
    values = {
        "ROLE": ROLE,
        "QUALIFICATION_COMMIT": MQ,
        "QUALIFICATION_CERTIFICATE_SHA256": CERT,
        "REAL_MONEY_AUTHORIZED": "NO",
        "EXPIRES_UTC": _future(),
    }
    values.update(overrides)
    body = ["# Owner T0 authorization", "", "```text"]
    body += [f"{key} = {value}" for key, value in values.items()]
    body += ["```", ""]
    return "\n".join(body)


def binding(**overrides) -> str:
    record = {
        "schema_version": "1.0.0",
        "binding_version": "FP_P2_QUALIFICATION_BINDING_V1",
        "role": ROLE,
        "qualification_commit": MQ,
        "certificate_sha256": CERT,
        "observations": {"image_digest": "sha256:" + "f" * 64, "python_version": "3.14.6"},
        "qualification_result": {
            "preflight": "PASS",
            "reconciliation": "PASS",
            "properties_evidenced": ["real_market_input"],
        },
        "real_money_authorized": False,
    }
    record.update(overrides)
    return json.dumps(record, indent=2)


class ScriptedGit:
    """A git that answers exactly what the test decided it should answer."""

    def __init__(self, **overrides):
        self.status = overrides.get("status", "")
        self.parents = overrides.get("parents", f"{HEAD} {PARENT_ONE} {PARENT_TWO}")
        self.on_main = overrides.get("on_main", True)
        self.authorization = overrides.get("authorization", authorization())
        self.binding = overrides.get("binding", binding())
        self.mq_is_ancestor = overrides.get("mq_is_ancestor", True)
        self.calls: list[list[str]] = []

    def __call__(self, args, *, check=True):
        self.calls.append(list(args))
        out, rc = "", 0
        if args[:1] == ["status"]:
            out = self.status
        elif args[:2] == ["rev-parse", "HEAD"]:
            out = HEAD
        elif args[:1] == ["rev-list"]:
            out = self.parents
        elif args[:1] == ["fetch"]:
            out = ""
        elif args[:2] == ["merge-base", "--is-ancestor"]:
            ok = self.on_main if args[2] == HEAD else self.mq_is_ancestor
            rc = 0 if ok else 1
        elif args[:1] == ["show"]:
            target = args[1].split(":", 1)[1]
            if target == freeze_t0.AUTHORIZATION_PATH:
                out, rc = (self.authorization, 0) if self.authorization is not None else ("", 128)
            elif target == freeze_t0.BINDING_PATH:
                out, rc = (self.binding, 0) if self.binding is not None else ("", 128)
            else:
                rc = 128
        else:
            rc = 0
        if check and rc != 0:
            raise freeze_t0.FreezeRefused(f"git {' '.join(args)} failed")
        return subprocess.CompletedProcess(args, rc, stdout=out, stderr="")


@pytest.fixture
def lawful(monkeypatch):
    """Everything lawful, so a test that moves one fact tests that fact."""
    scripted = ScriptedGit()
    monkeypatch.setattr(freeze_t0, "_git", scripted)
    monkeypatch.setattr(freeze_t0.fp_archive, "lane_is_empty",
                        lambda role, registry=None: (True, "empty"))
    monkeypatch.setattr(
        freeze_t0.fp_semantic, "compare",
        lambda left, right, role, **kw: {
            "result": fp_semantic.EQUIVALENT,
            "detail": "identical",
            "left": {"digest": "9" * 64},
            "right": {"digest": "9" * 64},
            "differences": [],
        },
    )
    return scripted


@pytest.fixture(autouse=True)
def registry_is_untouched():
    """Contract section 13: every refusal leaves the registry byte-identical."""
    before = REGISTRY_PATH.read_bytes()
    manifest_before = Path("MANIFEST.txt").read_bytes()
    yield
    assert REGISTRY_PATH.read_bytes() == before, "a refusal modified the cohort registry"
    assert Path("MANIFEST.txt").read_bytes() == manifest_before


def freeze(**overrides):
    return freeze_t0.check_preconditions(ROLE, overrides.pop("t0", T0))


# -- the headline refusal, against the real repository ---------------------


def test_the_authorization_at_this_head_is_absent_or_lawful():
    """Either state is lawful; a third state — present and malformed — is not.

    Before the Owner grants authority the file is absent and the tool refuses.
    After the Owner merges it the file is present, and what must then be true is
    that it parses, names this role, and names the same qualification run the
    merged S3b binding pins. Asserting absence instead would make the Owner's
    own lawful act fail the suite.

    Neither branch asserts a T0: an authorization permits the freeze, and the
    freeze is a separate transaction, so the registry is checked to be untouched
    under both.
    """
    head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                          check=True).stdout.strip()
    try:
        granted = freeze_t0.read_authorization(head)
    except freeze_t0.FreezeRefused as refusal:
        assert "does not exist at" in str(refusal)
    else:
        merged_binding = json.loads(
            subprocess.run(["git", "show", f"{head}:{freeze_t0.BINDING_PATH}"],
                           capture_output=True, text=True, check=True).stdout
        )
        assert granted["ROLE"] == ROLE == merged_binding["role"]
        assert granted["QUALIFICATION_COMMIT"] == merged_binding["qualification_commit"]
        assert granted["QUALIFICATION_CERTIFICATE_SHA256"] == merged_binding["certificate_sha256"]
        assert granted["REAL_MONEY_AUTHORIZED"].strip().upper() == "NO"
        # An expiry that has already passed is a refusal, not a pass; that it
        # parses at all is what this layer checks.
        freeze_t0._parse_utc(granted["EXPIRES_UTC"], "EXPIRES_UTC")
        # The qualification it names has to be in the history it authorizes.
        assert subprocess.run(["git", "merge-base", "--is-ancestor",
                               granted["QUALIFICATION_COMMIT"], head]).returncode == 0

    row = next(r for r in json.loads(
        subprocess.run(["git", "show", f"{head}:{freeze_t0.REGISTRY_PATH}"],
                       capture_output=True, text=True, check=True).stdout
    )["instances"] if r["role"] == ROLE)
    assert row["t0_utc"] is None and row["cohort_id"] is None
    assert row["status"] == "NOT_STARTED"


def test_the_authorization_is_read_from_git_not_the_working_tree(clone):
    """A working-tree read would let anyone with write access here grant T0.

    Exercised in a disposable clone. The earlier version of this test planted the
    file in THIS repository and unlinked it afterwards, which was harmless only
    while the path was guaranteed empty; against a merged authorization it would
    have deleted the Owner's record to run.
    """
    root, head = clone
    head = _remove_authorization(root, head)
    planted = root / freeze_t0.AUTHORIZATION_PATH
    planted.parent.mkdir(parents=True, exist_ok=True)
    planted.write_text(authorization(), encoding="utf-8")
    assert planted.is_file()
    with pytest.raises(freeze_t0.FreezeRefused, match="does not exist at"):
        freeze_t0.read_authorization(head)


def test_freeze_t0_takes_no_authorization_token():
    """A token is a downgrade: it can be guessed, leaked or copied. A merge cannot."""
    source = Path("scripts/freeze_t0.py").read_text(encoding="utf-8")
    for forbidden in ("--token", "--authorization", "--owner-key", "--secret", "--approve"):
        assert forbidden not in source, forbidden


# -- the lawful path -------------------------------------------------------


def test_every_precondition_holding_produces_the_freeze_facts(lawful):
    facts = freeze()
    assert facts["m1"] == HEAD
    assert facts["mq"] == MQ
    assert facts["t0_utc"] == T0
    assert facts["cohort_id"] == fp_law.cohort_id_for(ROLE, T0)
    assert facts["certificate_sha256"] == CERT


# -- the authorization itself ----------------------------------------------


def test_an_absent_authorization_refuses(lawful, monkeypatch):
    monkeypatch.setattr(freeze_t0, "_git", ScriptedGit(authorization=None))
    with pytest.raises(freeze_t0.FreezeRefused, match="does not exist at"):
        freeze()


def test_an_expired_authorization_refuses(lawful, monkeypatch):
    monkeypatch.setattr(freeze_t0, "_git",
                        ScriptedGit(authorization=authorization(EXPIRES_UTC=_past())))
    with pytest.raises(freeze_t0.FreezeRefused, match="expired"):
        freeze()


def test_an_authorization_for_another_role_refuses(lawful, monkeypatch):
    monkeypatch.setattr(freeze_t0, "_git",
                        ScriptedGit(authorization=authorization(ROLE="FP-CANDIDATE-A")))
    with pytest.raises(freeze_t0.FreezeRefused, match="names role"):
        freeze()


def test_real_money_yes_refuses(lawful, monkeypatch):
    monkeypatch.setattr(freeze_t0, "_git",
                        ScriptedGit(authorization=authorization(REAL_MONEY_AUTHORIZED="YES")))
    with pytest.raises(freeze_t0.FreezeRefused, match="PAPER / RESEARCH ONLY"):
        freeze()


def test_an_authorization_missing_a_field_refuses(lawful, monkeypatch):
    text = "\n".join(
        line for line in authorization().splitlines() if not line.startswith("EXPIRES_UTC")
    )
    monkeypatch.setattr(freeze_t0, "_git", ScriptedGit(authorization=text))
    with pytest.raises(freeze_t0.FreezeRefused, match="EXPIRES_UTC"):
        freeze()


def test_an_authorization_declaring_a_field_twice_refuses(lawful, monkeypatch):
    """Resolving an ambiguity here would mean choosing on the Owner's behalf."""
    text = authorization() + f"\nROLE = FP-CANDIDATE-B\n"
    monkeypatch.setattr(freeze_t0, "_git", ScriptedGit(authorization=text))
    with pytest.raises(freeze_t0.FreezeRefused, match="more than once"):
        freeze()


# -- the S3b binding -------------------------------------------------------


def test_an_absent_binding_refuses(lawful, monkeypatch):
    monkeypatch.setattr(freeze_t0, "_git", ScriptedGit(binding=None))
    with pytest.raises(freeze_t0.FreezeRefused, match="p2_qualification_binding"):
        freeze()


def test_a_certificate_the_binding_does_not_pin_refuses(lawful, monkeypatch):
    """The Owner authorized a different qualification run than the one on main."""
    monkeypatch.setattr(freeze_t0, "_git",
                        ScriptedGit(binding=binding(certificate_sha256="0" * 64)))
    with pytest.raises(freeze_t0.FreezeRefused, match="authorized a different qualification"):
        freeze()


def test_a_binding_for_another_qualification_commit_refuses(lawful, monkeypatch):
    monkeypatch.setattr(freeze_t0, "_git",
                        ScriptedGit(binding=binding(qualification_commit="1" * 40)))
    with pytest.raises(freeze_t0.FreezeRefused, match="but the binding records"):
        freeze()


# -- ancestry and equivalence ----------------------------------------------


def test_a_single_parent_head_refuses(lawful, monkeypatch):
    """M1 is a merged main, which is a two-parent merge the Owner performed."""
    monkeypatch.setattr(freeze_t0, "_git", ScriptedGit(parents=f"{HEAD} {PARENT_ONE}"))
    with pytest.raises(freeze_t0.FreezeRefused, match="parent"):
        freeze()


def test_a_head_that_is_not_on_main_refuses(lawful, monkeypatch):
    monkeypatch.setattr(freeze_t0, "_git", ScriptedGit(on_main=False))
    with pytest.raises(freeze_t0.FreezeRefused, match="not an ancestor of origin/main"):
        freeze()


def test_a_qualification_commit_outside_the_history_refuses(lawful, monkeypatch):
    monkeypatch.setattr(freeze_t0, "_git", ScriptedGit(mq_is_ancestor=False))
    with pytest.raises(freeze_t0.FreezeRefused, match="not an ancestor"):
        freeze()


def test_a_dirty_tree_refuses(lawful, monkeypatch):
    monkeypatch.setattr(freeze_t0, "_git", ScriptedGit(status=" M research/fp/capture.py"))
    with pytest.raises(freeze_t0.FreezeRefused, match="differ from HEAD"):
        freeze()


def test_non_equivalent_commits_refuse(lawful, monkeypatch):
    monkeypatch.setattr(
        freeze_t0.fp_semantic, "compare",
        lambda left, right, role, **kw: {
            "result": fp_semantic.DIFFERENT, "detail": "strategy moved",
            "left": {"digest": "9" * 64}, "right": {"digest": "8" * 64}, "differences": [{}],
        },
    )
    with pytest.raises(freeze_t0.FreezeRefused, match="not SEMANTIC_IDENTITY"):
        freeze()


def test_unproven_equivalence_refuses(lawful, monkeypatch):
    """UNPROVEN blocks exactly as FAIL does; there is no override anywhere."""
    monkeypatch.setattr(
        freeze_t0.fp_semantic, "compare",
        lambda left, right, role, **kw: {
            "result": fp_semantic.UNPROVEN, "detail": "git unavailable",
            "left": {"digest": "9" * 64}, "right": {"digest": "9" * 64}, "differences": [],
        },
    )
    with pytest.raises(freeze_t0.FreezeRefused, match="UNPROVEN"):
        freeze()


def test_a_binding_semantic_digest_that_no_longer_computes_refuses(lawful, monkeypatch):
    monkeypatch.setattr(freeze_t0, "_git",
                        ScriptedGit(binding=binding(semantic_identity_digest="7" * 64)))
    with pytest.raises(freeze_t0.FreezeRefused, match="but it computes to"):
        freeze()


# -- the lane and the registry ---------------------------------------------


def test_a_non_empty_lane_refuses(lawful, monkeypatch):
    """A cohort frozen over an existing lane carries pre-T0 state into evidence."""
    monkeypatch.setattr(freeze_t0.fp_archive, "lane_is_empty",
                        lambda role, registry=None: (False, "holds 7 files"))
    with pytest.raises(freeze_t0.FreezeRefused, match="lane is not empty"):
        freeze()


def test_an_already_started_row_refuses(lawful, monkeypatch):
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    row = next(item for item in registry["instances"] if item["role"] == ROLE)
    row["status"] = "RUNNING"
    row["t0_utc"] = "2026-01-01T00:00:00Z"
    row["cohort_id"] = fp_law.cohort_id_for(ROLE, "2026-01-01T00:00:00Z")
    row["runtime_identity"]["source_commit"] = "2" * 40
    registry["fp_run_active"] = True
    monkeypatch.setattr(freeze_t0.fp_law, "load_registry", lambda path=None: registry)
    with pytest.raises(freeze_t0.FreezeRefused, match="not NOT_STARTED"):
        freeze()


def test_an_unlawful_registry_refuses(lawful, monkeypatch):
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    registry["fp_run_active"] = True
    monkeypatch.setattr(freeze_t0.fp_law, "load_registry", lambda path=None: registry)
    with pytest.raises(freeze_t0.FreezeRefused, match="not lawful"):
        freeze()


def test_a_non_empty_change_log_refuses(lawful, monkeypatch):
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    row = next(item for item in registry["instances"] if item["role"] == ROLE)
    row["change_log"] = [{"utc": "2026-09-01T00:00:00Z", "class": "O", "description": "earlier"}]
    monkeypatch.setattr(freeze_t0.fp_law, "load_registry", lambda path=None: registry)
    with pytest.raises(freeze_t0.FreezeRefused, match="change_log is not empty"):
        freeze()


# -- T0 itself -------------------------------------------------------------


def test_a_back_dated_t0_refuses(lawful):
    """It would convert warm-up already on disk into prospective evidence."""
    with pytest.raises(freeze_t0.FreezeRefused, match="not in the future"):
        freeze_t0.check_preconditions(ROLE, _past())


def test_a_t0_far_in_the_future_refuses(lawful):
    far = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    with pytest.raises(freeze_t0.FreezeRefused, match="days ahead"):
        freeze_t0.check_preconditions(ROLE, far)


def test_a_malformed_t0_refuses(lawful):
    with pytest.raises(freeze_t0.FreezeRefused, match="not YYYY"):
        freeze_t0.check_preconditions(ROLE, "2026-09-20 14:00")


# =========================================================================
# The transaction itself, applied to a real repository.
#
# Every test above proves a refusal. None of them proves the freeze can
# SUCCEED, and that gap hid a defect that would only have surfaced the one time
# the tool is ever run: `verify_repo.py --fix` hashes each tracked file as it
# stands in the git INDEX, so regenerating the manifest before staging the
# registry produced a manifest built from the pre-freeze registry — byte
# identical to the committed one — and the transaction failed its own two-file
# check every time. A freeze tool that can never succeed is worse than one that
# fails loudly.
#
# So the transaction is applied to a disposable clone of this repository at its
# own HEAD, and the result is required to be exactly what the CI gate will
# demand of it.
# =========================================================================


@pytest.fixture
def clone(tmp_path, monkeypatch):
    from conftest import clone_at_head

    destination, head = clone_at_head(tmp_path / "clone")
    monkeypatch.setattr(freeze_t0, "REPO_ROOT", destination)
    return destination, head


def facts_for(clone_root: Path, head: str) -> dict:
    return {
        "role": ROLE,
        "head": head,
        "m1": head,
        "mq": MQ,
        "t0_utc": T0,
        "cohort_id": fp_law.cohort_id_for(ROLE, T0),
        "certificate_sha256": CERT,
        "semantic_identity_digest": "9" * 64,
        "expires_utc": _future(),
        "registry": None,
    }


def test_the_freeze_transaction_produces_exactly_two_staged_files(clone):
    root, head = clone
    freeze_t0.apply_freeze(facts_for(root, head))

    staged = sorted(
        subprocess.run(["git", "-C", str(root), "diff", "--cached", "--name-only"],
                       capture_output=True, text=True, check=True).stdout.split()
    )
    assert staged == sorted([freeze_t0.MANIFEST_PATH, freeze_t0.REGISTRY_PATH])
    unstaged = subprocess.run(["git", "-C", str(root), "diff", "--name-only"],
                              capture_output=True, text=True, check=True).stdout.split()
    assert unstaged == []


def test_the_frozen_registry_carries_the_seven_values(clone):
    root, head = clone
    freeze_t0.apply_freeze(facts_for(root, head))

    registry = json.loads(
        (root / freeze_t0.REGISTRY_PATH).read_text(encoding="utf-8")
    )
    row = next(item for item in registry["instances"] if item["role"] == ROLE)
    assert row["t0_utc"] == T0
    assert row["cohort_id"] == fp_law.cohort_id_for(ROLE, T0)
    assert row["status"] == "RUNNING"
    assert row["runtime_identity"]["source_commit"] == head
    assert len(row["change_log"]) == 1 and row["change_log"][0]["class"] == "O"
    assert registry["fp_run_active"] is True
    assert registry["registry_updated_utc"] != "2026-09-14T00:00:00Z"
    assert fp_law.check_registry(registry) == []


def test_the_closed_row_is_byte_identical_after_the_freeze(clone):
    root, head = clone
    before = json.loads((root / freeze_t0.REGISTRY_PATH).read_text(encoding="utf-8"))
    closed_before = next(i for i in before["instances"] if i["role"] == "FP-CONTROL-1")
    freeze_t0.apply_freeze(facts_for(root, head))
    after = json.loads((root / freeze_t0.REGISTRY_PATH).read_text(encoding="utf-8"))
    closed_after = next(i for i in after["instances"] if i["role"] == "FP-CONTROL-1")
    assert closed_before == closed_after


def test_the_repository_still_verifies_after_the_freeze(clone):
    """The manifest must describe the registry the freeze actually wrote."""
    import sys as _sys

    root, head = clone
    freeze_t0.apply_freeze(facts_for(root, head))
    verify = subprocess.run(
        [_sys.executable, str(root / "scripts" / "verify_repo.py")],
        capture_output=True, text=True, cwd=str(root),
    )
    assert verify.returncode == 0, verify.stdout + verify.stderr
    assert "REPO_CHECK_PASS" in verify.stdout


def test_the_freeze_candidate_passes_the_ci_gate_it_will_face(clone):
    """The tool and the gate must agree, or the Owner is asked to merge a refusal."""
    import check_freeze_candidate as gate

    root, head = clone
    subprocess.run(["git", "-C", str(root), "checkout", "--quiet", "-b", "claude/p2-freeze"],
                   check=True)
    freeze_t0.apply_freeze(facts_for(root, head))
    subprocess.run(["git", "-C", str(root), "-c", "user.email=t@example.invalid",
                    "-c", "user.name=t", "commit", "--quiet", "-m", "Freeze T0"], check=True)

    report = gate.check(head, "HEAD", repo_root=root)
    assert report["classification"] == gate.FREEZE_CANDIDATE
    assert report["result"] == "PASS", report["problems"]
    assert report["cohort_id"] == fp_law.cohort_id_for(ROLE, T0)


def test_an_unlawful_freeze_rolls_back_completely(clone):
    """All-or-nothing, index included."""
    root, head = clone
    registry_before = (root / freeze_t0.REGISTRY_PATH).read_bytes()
    manifest_before = (root / freeze_t0.MANIFEST_PATH).read_bytes()

    broken = facts_for(root, head)
    broken["cohort_id"] = "FP-CONTROL-2-NOT-DERIVED-FROM-T0"
    with pytest.raises(freeze_t0.FreezeRefused, match="not lawful"):
        freeze_t0.apply_freeze(broken)

    assert (root / freeze_t0.REGISTRY_PATH).read_bytes() == registry_before
    assert (root / freeze_t0.MANIFEST_PATH).read_bytes() == manifest_before
    staged = subprocess.run(["git", "-C", str(root), "diff", "--cached", "--name-only"],
                            capture_output=True, text=True, check=True).stdout.split()
    assert staged == []
    unstaged = subprocess.run(["git", "-C", str(root), "diff", "--name-only"],
                              capture_output=True, text=True, check=True).stdout.split()
    assert unstaged == []


# =========================================================================
# Authorization provenance: the committed git object, not a file on disk.
#
# "The Owner authorized this" must be a statement about history, not about the
# current contents of a directory. Everything below is driven against a real
# repository in which the authorization is genuinely committed, so the
# distinction is exercised rather than asserted: the worktree copy is then
# deleted, emptied and forged in turn, and the authority must come back
# unchanged from the object every time.
# =========================================================================


def _commit_authorization(root: Path, text: str, message: str = "Owner: authorize T0") -> str:
    path = root / freeze_t0.AUTHORIZATION_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "--", freeze_t0.AUTHORIZATION_PATH], check=True)
    subprocess.run(["git", "-C", str(root), "-c", "user.email=owner@example.invalid",
                    "-c", "user.name=owner", "commit", "--quiet", "-m", message], check=True)
    return subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()


def _remove_authorization(root: Path, head: str) -> str:
    """A clone HEAD that carries no authorization, whatever main carries.

    The three controls below prove that an uncommitted, a staged, and an
    off-branch authorization each grant nothing. Each needs a HEAD where the
    real thing is absent, and once the Owner has merged one, this repository is
    no longer such a HEAD. Constructing the absence is the repair: the controls
    then keep testing what they were written to test, in a clone, for as long as
    the mechanism exists — rather than only until it was first used.
    """
    path = root / freeze_t0.AUTHORIZATION_PATH
    if not path.exists():
        return head
    subprocess.run(["git", "-C", str(root), "rm", "--quiet", "--",
                    freeze_t0.AUTHORIZATION_PATH], check=True)
    subprocess.run(["git", "-C", str(root), "-c", "user.email=owner@example.invalid",
                    "-c", "user.name=owner", "commit", "--quiet", "-m",
                    "the state before authority was granted"], check=True)
    return subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()


def test_authority_comes_from_the_committed_object_not_the_worktree(clone):
    """The load-bearing distinction, exercised against a real commit."""
    root, _ = clone
    head = _commit_authorization(root, authorization())
    committed = freeze_t0.read_authorization(head)
    assert committed["ROLE"] == ROLE
    assert committed["QUALIFICATION_CERTIFICATE_SHA256"] == CERT

    worktree_copy = root / freeze_t0.AUTHORIZATION_PATH

    # Deleted from the worktree: authority is unchanged, because it never lived there.
    worktree_copy.unlink()
    assert freeze_t0.read_authorization(head) == committed

    # Emptied: same.
    worktree_copy.write_text("", encoding="utf-8")
    assert freeze_t0.read_authorization(head) == committed

    # Forged in place, naming a different role, a different certificate and no
    # expiry. A filesystem read would take every one of these.
    worktree_copy.write_text(
        authorization(ROLE="FP-CANDIDATE-A", QUALIFICATION_CERTIFICATE_SHA256="0" * 64,
                      EXPIRES_UTC=_future(3650)),
        encoding="utf-8",
    )
    forged = freeze_t0.read_authorization(head)
    assert forged == committed
    assert forged["ROLE"] == ROLE
    assert forged["QUALIFICATION_CERTIFICATE_SHA256"] == CERT


def test_an_untracked_authorization_grants_no_authority(clone):
    """Writing the file and never committing it is the obvious attempt."""
    root, head = clone
    head = _remove_authorization(root, head)
    path = root / freeze_t0.AUTHORIZATION_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(authorization(), encoding="utf-8")
    assert path.is_file()
    with pytest.raises(freeze_t0.FreezeRefused, match="does not exist at"):
        freeze_t0.read_authorization(head)


def test_a_staged_but_uncommitted_authorization_grants_no_authority(clone):
    """Staging is not history either: `git show HEAD:` reads the commit."""
    root, head = clone
    head = _remove_authorization(root, head)
    path = root / freeze_t0.AUTHORIZATION_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(authorization(), encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "--", freeze_t0.AUTHORIZATION_PATH], check=True)
    with pytest.raises(freeze_t0.FreezeRefused, match="does not exist at"):
        freeze_t0.read_authorization(head)


def test_an_authorization_on_another_branch_is_not_authority_at_this_head(clone):
    root, head = clone
    head = _remove_authorization(root, head)
    subprocess.run(["git", "-C", str(root), "checkout", "--quiet", "-b", "side"], check=True)
    _commit_authorization(root, authorization())
    subprocess.run(["git", "-C", str(root), "checkout", "--quiet", head], check=True)
    with pytest.raises(freeze_t0.FreezeRefused, match="does not exist at"):
        freeze_t0.read_authorization(head)


def test_a_dirty_worktree_copy_cannot_reach_the_freeze_at_all(clone, lawful, monkeypatch):
    """Two independent barriers, and the outer one is the clean-tree gate.

    Even if the committed authorization is lawful, a modified worktree means the
    frozen source commit would not describe what runs — so the freeze refuses
    before the authorization is consulted at all.
    """
    monkeypatch.setattr(freeze_t0, "_git", ScriptedGit(status=" M docs/p2/OWNER_T0_AUTHORIZATION.md"))
    with pytest.raises(freeze_t0.FreezeRefused, match="differ from HEAD"):
        freeze()


def test_freeze_t0_never_reads_the_authorization_from_the_filesystem():
    """No filesystem read of that path exists anywhere in the tool."""
    source = Path("scripts/freeze_t0.py").read_text(encoding="utf-8")
    assert 'git", "show"' not in source  # it goes through _git, which is scripted in tests
    assert '_git(["show", f"{head}:{AUTHORIZATION_PATH}"]' in source
    for forbidden in (
        "Path(AUTHORIZATION_PATH).read_text",
        "open(AUTHORIZATION_PATH",
        "REPO_ROOT / AUTHORIZATION_PATH",
    ):
        assert forbidden not in source, forbidden
