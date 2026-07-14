"""CitationValidator — I1/I2: uncited or dead-source cards are rejected."""

from __future__ import annotations

from lamplight_memory.schemas import BriefCard, Status
from lamplight_memory.validator import CitationValidator, RejectedCard


def card(citations, sbar="S: rash onset 4h after cefazolin", source_id="mem-x"):
    return BriefCard(
        bed=9, priority=1, sbar=sbar, why_tonight="dose due 0200",
        citations=citations, source_id=source_id,
    )


def resolver_from(mapping):
    return lambda cid: mapping.get(cid)


def test_uncited_card_rejected():
    v = CitationValidator(resolver_from({}))
    assert v.validate_card(card([])) == "uncited"


def test_unknown_citation_rejected():
    v = CitationValidator(resolver_from({}))  # every lookup -> None
    reason = v.validate_card(card(["ep-999"]))
    assert reason == "unknown_citation:ep-999"


def test_resolved_source_rejected():
    v = CitationValidator(resolver_from({"ep-09-02-1": Status.RESOLVED}))
    reason = v.validate_card(card(["ep-09-02-1"]))
    assert reason == "cited_source_resolved:ep-09-02-1"


def test_expired_source_rejected():
    v = CitationValidator(resolver_from({"ep-r": Status.EXPIRED}))
    assert v.validate_card(card(["ep-r"])) == "cited_source_expired:ep-r"


def test_active_source_accepted():
    v = CitationValidator(resolver_from({"ep-1": Status.ACTIVE}))
    assert v.validate_card(card(["ep-1"])) is None


def test_pinned_source_accepted():
    v = CitationValidator(resolver_from({"ep-1": Status.PINNED}))
    assert v.validate_card(card(["ep-1"])) is None


def test_empty_sbar_rejected_when_citations_ok():
    v = CitationValidator(resolver_from({"ep-1": Status.ACTIVE}))
    assert v.validate_card(card(["ep-1"], sbar="   ")) == "empty_sbar"


def test_one_bad_citation_among_good_rejects_whole_card():
    v = CitationValidator(
        resolver_from({"ep-1": Status.ACTIVE, "ep-2": Status.RESOLVED})
    )
    assert v.validate_card(card(["ep-1", "ep-2"])) == "cited_source_resolved:ep-2"


def test_validate_partitions_valid_and_rejected():
    v = CitationValidator(
        resolver_from({"ep-good": Status.ACTIVE, "ep-dead": Status.EXPIRED})
    )
    good = card(["ep-good"], source_id="m1")
    bad = card(["ep-dead"], source_id="m2")
    result = v.validate([good, bad])
    assert result.valid == [good]
    assert len(result.rejected) == 1
    assert isinstance(result.rejected[0], RejectedCard)
    assert result.rejected[0].reason == "cited_source_expired:ep-dead"


def test_all_valid_property_true():
    v = CitationValidator(resolver_from({"ep-1": Status.ACTIVE}))
    assert v.validate([card(["ep-1"])]).all_valid is True


def test_all_valid_property_false():
    v = CitationValidator(resolver_from({}))
    assert v.validate([card([])]).all_valid is False


def test_unrecognized_status_value_rejected():
    # StatusResolver is a bare Callable — nothing stops a caller from
    # returning something outside the Status enum (a future status value,
    # or a bug upstream). The validator must fail closed, not crash or
    # silently accept it.
    v = CitationValidator(resolver_from({"ep-mystery": "quarantined"}))
    reason = v.validate_card(card(["ep-mystery"]))
    assert reason == "cited_source_not_active:ep-mystery"


def test_multi_citation_all_active_ok():
    v = CitationValidator(
        resolver_from(
            {"ep-1": Status.ACTIVE, "ep-2": Status.ACTIVE, "ep-3": Status.PINNED}
        )
    )
    assert v.validate_card(card(["ep-1", "ep-2", "ep-3"])) is None
