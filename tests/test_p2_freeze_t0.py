"""freeze_t0: the one act that turns a registered instance into a cohort.

Contract section 6 puts T0 authority in a **merged record**, not a token, and
the reasoning is the whole design: a secret can be guessed, leaked, copied out
of a transcript, or supplied by whoever is sitting at the keyboard; a merge
cannot. ``docs/p2/OWNER_T0_AUTHORIZATION.md`` therefore does not exist, is read
from git at HEAD rather than from the working tree, and its absence is the
default — which makes refusal the default.

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


def test_the_authorization_does_not_exist_on_main():
    """The default state of this repository, and the default is refusal."""
    head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                          check=True).stdout.strip()
    with pytest.raises(freeze_t0.FreezeRefused, match="does not exist at"):
        freeze_t0.read_authorization(head)


def test_the_authorization_is_read_from_git_not_the_working_tree(tmp_path, monkeypatch):
    """A working-tree read would let anyone with write access here grant T0."""
    planted = Path("docs/p2") / "OWNER_T0_AUTHORIZATION.md"
    assert not planted.exists()
    planted.write_text(authorization(), encoding="utf-8")
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                              check=True).stdout.strip()
        with pytest.raises(freeze_t0.FreezeRefused, match="does not exist at"):
            freeze_t0.read_authorization(head)
    finally:
        planted.unlink()


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
