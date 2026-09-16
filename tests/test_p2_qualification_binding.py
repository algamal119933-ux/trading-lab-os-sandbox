"""The S3b qualification binding — checkable from git, not taken on trust.

The binding is what lets a merge-gated Owner authorization refer to a runtime
artifact that is deliberately not in Git. It pins three things: the commit the
runtime-attached gates actually passed at (Mq), the sha256 of the certificate
those gates produced, and SEMANTIC_IDENTITY(Mq).

Two of the three are only as good as whoever typed them, unless something
recomputes them. The certificate's bytes live under ``artifacts/`` on the host
that sealed them and cannot be recomputed here — that is the whole reason its
digest is pinned, and ``freeze_t0`` is what compares the pin against the Owner's
authorization. Mq and the semantic identity, on the other hand, are statements
about git objects, so this file recomputes both from git and refuses a binding
that does not match. A record that merely asserted its own semantic identity
would be a record that could name any commit at all.

The binding binds. It does not authorize: authority is
``docs/p2/OWNER_T0_AUTHORIZATION.md`` on main by an Owner merge, and
``tests/test_p2_scope_audit.py`` holds the invariant that no T0 exists without
it. Where that authorization has been granted, it must name the run this binding
pins — an authorization for one qualification and a binding for another would be
two records that agree about nothing.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import jsonschema
import pytest

from fp import capability as fp_capability
from fp import semantic_identity as fp_semantic

BINDING_PATH = Path("research/fp/records/p2_qualification_binding.json")
SCHEMA_PATH = Path("research/schema/p2_qualification_binding.schema.json")

pytestmark = pytest.mark.skipif(
    not BINDING_PATH.exists(),
    reason="no qualification binding in this checkout; it does not exist before S3b",
)


@pytest.fixture(scope="module")
def binding() -> dict:
    return json.loads(BINDING_PATH.read_text(encoding="utf-8"))


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, text=True)


def test_the_binding_validates_against_its_schema(binding):
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = jsonschema.validators.validator_for(schema)(schema)
    assert not [e.message for e in validator.iter_errors(binding)]


def test_the_qualification_commit_is_a_real_commit_in_this_history(binding):
    """Mq must be reachable, or the freeze would pin a commit nobody can read."""
    mq = binding["qualification_commit"]
    kind = _git("cat-file", "-t", mq)
    assert kind.returncode == 0 and kind.stdout.strip() == "commit", mq
    ancestor = _git("merge-base", "--is-ancestor", mq, "HEAD")
    assert ancestor.returncode == 0, f"{mq[:8]} is not an ancestor of HEAD"


def test_the_semantic_identity_is_recomputed_and_matches(binding):
    """The one claim in the record that a later reader can verify unaided."""
    recomputed = fp_semantic.semantic_identity(binding["qualification_commit"], binding["role"])
    assert recomputed.digest == binding["semantic_identity_digest"], (
        f"the binding records {binding['semantic_identity_digest'][:12]}… for "
        f"{binding['qualification_commit'][:8]}, but that commit's semantic identity is "
        f"{recomputed.digest[:12]}…"
    )


def test_the_binding_records_the_nine_pre_t0_properties_and_no_lifecycle_one(binding):
    evidenced = binding["qualification_result"]["properties_evidenced"]
    assert sorted(evidenced) == sorted(fp_capability.PRE_T0_QUALIFIABLE)
    assert not set(evidenced) & set(fp_capability.POST_T0_LIFECYCLE)
    # The aggregate is reported beside the twelve and never counted among them,
    # so it must not appear here either.
    assert fp_capability.FULL_TRADE_LIFECYCLE not in evidenced


def test_the_binding_claims_a_passing_pre_t0_qualification_and_nothing_more(binding):
    result = binding["qualification_result"]
    assert result["preflight"] == "PASS"
    assert result["preflight_checks_passed"] == 16
    assert result["reconciliation"] == "PASS"
    assert binding["t0_relation_of_every_record"] == "T0_NOT_FROZEN"
    assert binding["prospective_evidence"] == "NONE"
    assert binding["real_money_authorized"] is False
    assert binding["role"] == "FP-CONTROL-2"


def test_the_binding_does_not_authorize(binding):
    """A binding that had grown authority would be a T0 nobody merged.

    The subject here is the binding, and the claim is that it carries no
    authority of its own. An earlier version also asserted that no Owner
    authorization existed anywhere — a fact about the repository on the day this
    was written, not a property of the binding, and one the Owner's lawful grant
    ends. Authority living in a separate merged file is the invariant; that file
    being absent is not.
    """
    for forbidden in ("t0_utc", "cohort_id", "authorization", "authorized",
                      "expires_utc", "owner", "approval"):
        assert forbidden not in binding, (
            f"the binding carries {forbidden!r}; authority is a merged Owner file, never a "
            "field in a record Claude Code writes"
        )
    # Authority is a different object at a different path. Where it exists, it
    # is read with the repository's own parser rather than a second one written
    # here, and it must name the run this binding pins.
    import freeze_t0

    authorization = Path("docs/p2/OWNER_T0_AUTHORIZATION.md")
    if authorization.exists():
        granted: dict[str, str] = {}
        for line in authorization.read_text(encoding="utf-8").splitlines():
            match = freeze_t0.AUTHORIZATION_LINE.match(line)
            if match and match.group(1) in freeze_t0.AUTHORIZATION_KEYS:
                granted[match.group(1)] = match.group(2)
        assert granted["ROLE"] == binding["role"]
        assert granted["QUALIFICATION_COMMIT"] == binding["qualification_commit"]
        assert granted["QUALIFICATION_CERTIFICATE_SHA256"] == binding["certificate_sha256"]


def test_the_certificate_is_pinned_by_digest_and_is_not_in_git(binding):
    """The certificate stays a runtime artifact; only its digest is tracked."""
    assert len(binding["certificate_sha256"]) == 64
    tracked = _git("ls-files").stdout.split()
    assert not any("certificate" in path for path in tracked)
    # And if this host still has the artifact, its bytes must be the pinned ones.
    certificate = Path("artifacts/p2-s3-qualification/certificate.json")
    if certificate.exists():
        import hashlib

        assert hashlib.sha256(certificate.read_bytes()).hexdigest() == \
            binding["certificate_sha256"]


def test_the_observations_are_class_o_only(binding):
    """Observations of a runtime, never instructions to one.

    This is why they are excluded from SEMANTIC_IDENTITY, and the exclusion is
    what lets the equivalence proof hold across S3b at all: binding them is a
    change to the record of what was seen, not to what the system does.
    """
    observations = binding["observations"]
    assert observations["image_digest"].startswith("sha256:")
    assert observations["python_version"]
    excluded = fp_semantic.REGISTRY_EXCLUDED_IDENTITY_FIELDS
    for field in ("image_digest", "python_version"):
        assert field in excluded, (
            f"{field} is bound as an observation but is not excluded from REGISTRY_SEMANTICS, "
            "so binding it would break the equivalence proof it is meant to survive"
        )
