"""Typed schemas — Episode / MemoryItem / BriefCard validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from lamplight_memory.schemas import (
    EXTRACTION_JSON_SCHEMA,
    Brief,
    BriefCard,
    DecayClass,
    Episode,
    EpisodeType,
    MemoryItem,
    OpType,
    Status,
)


def _ep(**over):
    base = dict(
        id="ep-09-06-1",
        bed=9,
        shift=6,
        ts="2026-06-03T00:30:00Z",
        type="observation",
        text="Faint erythema across the right forearm.",
        entities=["skin_reaction", "cefazolin"],
        decay_class="critical",
    )
    base.update(over)
    return Episode.model_validate(base)


def test_episode_valid():
    ep = _ep()
    assert ep.type is EpisodeType.OBSERVATION
    assert ep.decay_class is DecayClass.CRITICAL
    assert ep.polarity == "neutral"


def test_episode_entities_sorted_unique():
    ep = _ep(entities=["cefazolin", "skin_reaction", "cefazolin", "cefazolin"])
    assert ep.entities == ["cefazolin", "skin_reaction"]


def test_episode_text_must_be_nonempty():
    with pytest.raises(ValidationError):
        _ep(text="   ")


def test_episode_shift_ge_one():
    with pytest.raises(ValidationError):
        _ep(shift=0)


def test_episode_bad_decay_class_rejected():
    with pytest.raises(ValidationError):
        _ep(decay_class="urgent")


def test_episode_bad_type_rejected():
    with pytest.raises(ValidationError):
        _ep(type="vibes")


@pytest.mark.parametrize("pol", ["pos", "neg", "neutral"])
def test_episode_polarity_values(pol):
    assert _ep(polarity=pol).polarity == pol


def test_episode_bad_polarity_rejected():
    with pytest.raises(ValidationError):
        _ep(polarity="mixed")


def test_memory_provenance_must_be_nonempty():
    with pytest.raises(ValidationError):
        MemoryItem(
            id="mem-09-x-s12",
            bed=9,
            kind="consolidated",
            text="thread",
            decay_class="critical",
            provenance=[],
            created_shift=12,
        )


def test_memory_valid_with_provenance():
    m = MemoryItem(
        id="mem-09-cefazolin-s12",
        bed=9,
        kind="consolidated",
        text="cefazolin thread",
        decay_class="critical",
        provenance=["ep-09-04-1", "ep-09-06-1"],
        created_shift=12,
    )
    assert m.needs_confirmation is False
    assert m.kind == "consolidated"


def test_briefcard_requires_citations_field():
    with pytest.raises(ValidationError):
        BriefCard(bed=9, priority=1, sbar="S:", why_tonight="w", source_id="x")


def test_briefcard_priority_ge_one():
    with pytest.raises(ValidationError):
        BriefCard(
            bed=9, priority=0, sbar="S:", why_tonight="w",
            citations=["ep-1"], source_id="x",
        )


def test_briefcard_ok():
    c = BriefCard(
        bed=9, priority=1, sbar="S: rash", why_tonight="dose due",
        citations=["ep-09-06-1"], source_id="mem-09-cefazolin-s12",
    )
    assert c.decay_note is None
    assert c.needs_confirmation is False


def test_brief_defaults():
    b = Brief(
        bed=9, as_of_shift=14, for_shift=15, generated_at="2026-06-05T23:00:00Z",
        engine="fake", budget=2000, token_count=334, cards=[],
    )
    assert b.retired == []
    assert b.left_out == []
    assert b.routine_expired_count == 0


@pytest.mark.parametrize(
    "enum,expected",
    [
        (Status, {"active", "resolved", "expired", "pinned"}),
        (DecayClass, {"critical", "condition", "routine", "resolved"}),
        (EpisodeType, {"observation", "action", "resolution", "order"}),
        (OpType, {"write", "consolidate", "decay", "contradict", "pin", "expire"}),
    ],
)
def test_enum_membership(enum, expected):
    assert {e.value for e in enum} == expected


def test_extraction_schema_is_strict():
    assert EXTRACTION_JSON_SCHEMA["strict"] is True
    assert "episodes" in EXTRACTION_JSON_SCHEMA["schema"]["properties"]
