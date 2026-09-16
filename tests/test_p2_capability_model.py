"""One property model, twelve properties, two buckets, and an aggregate outside.

The P2 contract originally described the split as "eight non-lifecycle" plus
"four lifecycle", where the fourth was the completed
entry→fill→position→exit→realised-PnL chain. Three of the twelve are lifecycle
properties, so twelve minus three is nine — the arithmetic never closed, and the
reason it never closed is that the aggregate was being counted as a property.

That is not a cosmetic error. Folding the aggregate into the count would let a
cohort reach `12/12` with a genuine property unevidenced and the aggregate
standing in for it; and it would collapse the one distinction
`P2 INCONCLUSIVE / INSUFFICIENT` rests on, because a quiet window can leave the
lifecycle unobserved while every capability is intact. These tests make the
model machine-checkable so it cannot drift back.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from fp import capability as cap

ACTIVATION_PACK = Path("docs/fp-boot-1/FP_CONTROL_1_ACTIVATION_PACK.md")
CONTRACT = Path("docs/p2/P2_CONTRACT.md")
BINDING_SCHEMA = Path("research/schema/p2_qualification_binding.schema.json")
REGISTRY_SCHEMA = Path("research/schema/forward_paper_cohort_registry.schema.json")


# -- the four invariants ---------------------------------------------------


def test_there_are_exactly_twelve_unique_properties():
    assert cap.PROPERTY_COUNT == 12
    assert len(cap.PROPERTIES) == 12
    assert len(set(cap.PROPERTIES)) == 12
    assert len(set(cap.PROPERTIES.values())) == 12


def test_every_property_belongs_to_exactly_one_bucket():
    pre, post = set(cap.PRE_T0_QUALIFIABLE), set(cap.POST_T0_LIFECYCLE)
    assert pre & post == set(), "a property in both buckets could be counted twice"
    assert pre | post == set(cap.PROPERTIES)
    for name in cap.PROPERTIES:
        assert cap.classify(name) in ("PRE_T0", "POST_T0")


def test_the_bucket_counts_sum_to_twelve():
    assert len(cap.PRE_T0_QUALIFIABLE) == 9
    assert len(cap.POST_T0_LIFECYCLE) == 3
    assert len(cap.PRE_T0_QUALIFIABLE) + len(cap.POST_T0_LIFECYCLE) == cap.PROPERTY_COUNT


def test_the_aggregate_cannot_silently_enter_or_leave_the_count():
    """full_trade_lifecycle has no bucket, and asking for one is an error."""
    assert cap.FULL_TRADE_LIFECYCLE not in cap.PROPERTIES
    assert cap.FULL_TRADE_LIFECYCLE not in cap.PRE_T0_QUALIFIABLE
    assert cap.FULL_TRADE_LIFECYCLE not in cap.POST_T0_LIFECYCLE
    with pytest.raises(ValueError, match="aggregate status"):
        cap.classify(cap.FULL_TRADE_LIFECYCLE)
    # And it is a status in its own right, with its own enum, on the registry row.
    schema = json.loads(REGISTRY_SCHEMA.read_text(encoding="utf-8"))
    outcome = (
        schema["properties"]["instances"]["items"]["properties"]["outcome"]["properties"]
    )
    assert cap.FULL_TRADE_LIFECYCLE in outcome
    assert "OBSERVED" in outcome[cap.FULL_TRADE_LIFECYCLE]["enum"]


def test_an_unknown_name_is_refused():
    with pytest.raises(ValueError, match="not one of the 12"):
        cap.classify("prospective_paper_edge")


# -- the model matches the authority that first named the properties -------


def test_the_twelve_match_the_activation_packs_enumeration():
    """docs/fp-boot-1/FP_CONTROL_1_ACTIVATION_PACK.md is where these come from."""
    text = ACTIVATION_PACK.read_text(encoding="utf-8")
    start = text.index("PAPER_TRADING_OPERATIONAL_CAPABILITY = PROVEN` requires all of:")
    passage = text[start : text.index("48-hour window rule")]
    listed = [
        item.strip().rstrip(".")
        for item in passage.split("requires all of:", 1)[1].replace("\n", " ").split(",")
    ]
    listed = [item for item in listed if item]
    assert len(listed) == 12, listed
    assert listed == list(cap.PROPERTIES.values()), (listed, list(cap.PROPERTIES.values()))


def test_the_pack_reports_the_lifecycle_separately_from_the_twelve():
    """Evidence that the aggregate was always outside the count, not added by P2."""
    text = ACTIVATION_PACK.read_text(encoding="utf-8")
    assert "FULL_TRADE_LIFECYCLE = NOT_YET_OBSERVED" in text
    passage = text[
        text.index("requires all of:") : text.index("48-hour window rule")
    ]
    assert "lifecycle" not in passage.lower()


# -- every derived surface agrees with the model ---------------------------


def test_the_binding_schema_enum_is_the_pre_t0_nine():
    schema = json.loads(BINDING_SCHEMA.read_text(encoding="utf-8"))
    field = schema["properties"]["qualification_result"]["properties"]["properties_evidenced"]
    assert field["items"]["enum"] == list(cap.PRE_T0_QUALIFIABLE)
    assert field["minItems"] == field["maxItems"] == len(cap.PRE_T0_QUALIFIABLE)


def test_the_sealing_tool_derives_rather_than_restates():
    import seal_pre_t0_qualification as sealer

    assert sealer.NON_LIFECYCLE_PROPERTIES is cap.PRE_T0_QUALIFIABLE
    source = Path("scripts/seal_pre_t0_qualification.py").read_text(encoding="utf-8")
    for name in cap.PRE_T0_QUALIFIABLE:
        assert f'"{name}"' not in source, f"{name} is restated instead of derived"


def test_the_contract_states_the_corrected_model_and_only_that():
    """No surface may still assert the arithmetic that does not close."""
    contract = CONTRACT.read_text(encoding="utf-8")
    assert "9 + 3 = 12 / 12" in contract
    assert "the NINE pre-T0 qualifiable properties" in contract
    assert "the THREE lifecycle properties" in contract
    assert "`FULL_TRADE_LIFECYCLE` is not one of the twelve" in contract


@pytest.mark.parametrize(
    "path",
    [
        "docs/p2/P2_CONTRACT.md",
        "docs/p2/S2_PRE_T0_IMPLEMENTATION.md",
        "research/schema/p2_qualification_binding.schema.json",
        "scripts/seal_pre_t0_qualification.py",
        "research/fp/capability.py",
    ],
)
def test_no_surface_asserts_the_old_split_as_current(path):
    """The old wording may be described as superseded, never asserted as the rule.

    A live claim is a sentence in the present tense; the correction has to be
    able to explain what it corrected, so the discussion of the old split is
    allowed exactly where it is labelled as history.
    """
    text = Path(path).read_text(encoding="utf-8")
    forbidden = (
        "the eight non-lifecycle properties",
        "prove the eight at Mq",
        "the four lifecycle properties",
        "the eight from S3",
        "the four from credited",
    )
    for claim in forbidden:
        assert claim not in text, f"{path} still asserts {claim!r}"
