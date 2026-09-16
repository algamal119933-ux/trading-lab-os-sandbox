"""Cross-cutting invariants the S2 tool set must hold as a set, not one by one.

Three of these are stated by the contract as properties of the whole gate set
rather than of any single gate, which means no individual tool's test can cover
them:

* **no override flag exists anywhere, and a test asserts that none appears**
  (section 1). Fail-closed is only a default if there is no documented way
  around it; one ``--force`` added in a hurry converts every gate below it into
  advice.
* **a same-host copy is never described as host-loss redundancy, in any record,
  at any time** (section 8). The project has already paid once for conflating
  the two, and the conflation is a sentence, not a code path — so the assertion
  has to be made against the text the tools emit.
* **no P2 outcome may be reported as an edge claim** (section 2), favourable or
  unfavourable, because a prospective edge requires a paper-admissible survivor
  and entry state is C.

The rest pin the durability tiers to what each may truthfully claim, and pin
Tier-3 discovery to discovery.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import second_device_discovery

S2_TOOLS = (
    "scripts/archive_fp_lane.py",
    "scripts/check_freeze_candidate.py",
    "scripts/fp_watch.py",
    "scripts/freeze_t0.py",
    "scripts/prove_semantic_equivalence.py",
    "scripts/publish_evidence_digest.py",
    "scripts/seal_pre_t0_qualification.py",
    "scripts/second_device_discovery.py",
    "scripts/replicate_to_second_device.py",
    "scripts/validate_activation.py",
    "research/fp/archive.py",
    "research/fp/capability.py",
    "research/fp/registry_law.py",
    "research/fp/semantic_identity.py",
)

# Vocabulary that would let a caller proceed past a gate that did not pass.
# Deliberately not a substring scan for the word "force": a report-only or
# scope-limiting flag is not an override, and conflating the two would make this
# test noise. These are the shapes that actually bypass.
OVERRIDE_FLAGS = (
    "--force", "--override", "--skip-gate", "--skip-checks", "--ignore-failures",
    "--no-verify", "--allow-fail", "--allow-unproven", "--yes-i-am-sure",
    "--bypass", "--disable-gate", "--assume-pass",
)


def _source(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


# -- no override exists anywhere in the gate set ---------------------------


@pytest.mark.parametrize("path", S2_TOOLS)
def test_no_tool_offers_a_way_past_a_failed_gate(path):
    source = _source(path)
    for flag in OVERRIDE_FLAGS:
        assert flag not in source, f"{path} offers {flag}"


@pytest.mark.parametrize("path", S2_TOOLS)
def test_no_tool_reads_an_override_from_the_environment(path):
    """An environment variable is an override with the argument parser removed."""
    source = _source(path)
    for needle in ("FP_FORCE", "FP_SKIP", "FP_OVERRIDE", "FP_ALLOW", "SKIP_GATE"):
        assert needle not in source, f"{path} reads {needle}"


def test_unproven_blocks_exactly_as_fail_does():
    """Three independent gates, one rule. A check that could not run did not pass."""
    from fp import reconcile, semantic_identity
    import validate_activation

    assert reconcile.UNPROVEN == "UNPROVEN"
    assert semantic_identity.UNPROVEN == "UNPROVEN"
    assert validate_activation.UNPROVEN == "UNPROVEN"

    # reconcile withholds PASS on any non-PASS finding, UNPROVEN included.
    source = _source("research/fp/reconcile.py")
    assert 'status = PASS if all(item.result == PASS for item in findings) else FAIL' in source
    # validate_activation does the same.
    activation_source = _source("scripts/validate_activation.py")
    assert "all(c.result == PASS for c in checks)" in activation_source
    # the equivalence CLI exits 2 on UNPROVEN as on DIFFERENT.
    cli = _source("scripts/prove_semantic_equivalence.py")
    assert 'report["result"] != si.EQUIVALENT' in cli


# -- durability: each tier claims what it may, and nothing more ------------


def test_tier_1_never_claims_host_loss_redundancy():
    from fp import archive

    assert archive.TIER1_CLAIM.startswith("TIER_1_SAME_HOST_ARCHIVAL")
    assert "does NOT establish survival of host loss" in archive.TIER1_DISCLAIMER
    assert "decommissioned" in archive.TIER1_DISCLAIMER


def test_tier_2_never_claims_anything_is_recoverable():
    document = json.loads(
        Path("research/fp/records/evidence_digest_publication.json").read_text(encoding="utf-8")
    )
    assert document["durability_tier"] == 2
    assert document["host_loss_redundancy"] is False
    assert "not a backup" in document["tier_2_disclaimer"]
    assert "bounded" in document["tier_2_disclaimer"]


def test_the_tier_2_schema_forbids_a_host_loss_claim():
    schema = json.loads(
        Path("research/schema/evidence_digest_publication.schema.json").read_text(encoding="utf-8")
    )
    assert schema["properties"]["host_loss_redundancy"] == {
        "description": schema["properties"]["host_loss_redundancy"]["description"],
        "const": False,
    }
    assert schema["properties"]["durability_tier"]["const"] == 2


def test_no_tool_describes_a_same_host_copy_as_redundancy():
    """The conflation is a sentence, not a code path, so it is checked as text.

    Claim-shaped rather than vocabulary-shaped: a tool must be able to say
    "disaster recovery is P3 scope", which is the disclaimer doing its job.
    """
    for path in S2_TOOLS:
        text = _source(path).lower()
        for claim in ("host-loss redundancy is provided", "survives host loss",
                      "is an offsite copy", "provides disaster recovery",
                      "host_loss_redundancy = yes"):
            assert claim not in text, f"{path} claims {claim!r}"


# -- Tier 3 discovers. It does not provision. ------------------------------


def test_second_device_discovery_provisions_nothing():
    report = second_device_discovery.discover()
    assert report["provisioned"] is False
    assert report["actions_taken"].startswith("NONE")
    assert report["real_money_authorized"] is False
    assert report["host_loss_redundancy"] == "NOT_PROVEN"


def test_second_device_discovery_makes_no_outbound_call():
    source = _source("scripts/second_device_discovery.py")
    for needle in ("urllib", "requests", "socket.create_connection", "boto3", "rclone",
                   "scp ", "rsync", "curl"):
        assert needle not in source, f"tier3_discovery reaches for {needle}"


def test_a_second_device_on_this_host_is_never_host_loss_redundancy():
    """A theft, a fire, a PSU failure or a decommission takes both drives."""
    report = second_device_discovery.discover()
    assert report["host_loss_redundancy"] == "NOT_PROVEN"
    assert report["status"] in (second_device_discovery.AVAILABLE,
                                second_device_discovery.UNAVAILABLE)


# -- P2 never converts a measurement into an edge claim --------------------


def test_no_p2_tool_can_report_a_prospective_edge():
    import validate_activation

    report = validate_activation.validate("FP-CONTROL-2")
    assert report["prospective_paper_edge"] == "NOT_EVALUATED"
    for path in S2_TOOLS:
        text = _source(path)
        assert "PROSPECTIVE_PAPER_EDGE = PROVEN" not in text
        assert '"prospective_paper_edge": "PROVEN"' not in text


def test_every_operator_facing_tool_declares_paper_only():
    """Scoped to the scripts a human runs — that is where the declaration is read.

    The library modules are not exempt by oversight: semantic_identity.py
    compares git objects and has no money surface at all, and requiring it to
    recite a boundary it cannot cross would make the assertion decorative
    everywhere it appears.
    """
    for path in S2_TOOLS:
        if not path.startswith("scripts/"):
            continue
        text = _source(path)
        assert "REAL_MONEY_AUTHORIZED = NO" in text, path


# -- the tools are wired into the repository's own integrity gates ---------

def test_every_new_tool_is_tracked_and_manifested():
    tracked = set(
        subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True)
        .stdout.split()
    )
    manifest = {
        line.split(None, 1)[1].strip()
        for line in Path("MANIFEST.txt").read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    }
    for path in S2_TOOLS:
        assert path in tracked, f"{path} is untracked"
        assert path in manifest, f"{path} is not in MANIFEST.txt"
