"""BriefBuilder — retrieval -> rerank -> knapsack -> validated SBAR brief.

Runs against the real 15-shift ward (session fixture, fake transport).
"""

from __future__ import annotations

import pytest
from conftest import add_ep, ep_dict

from lamplight_memory.brief import DEFAULT_BUDGET, MAX_CARDS, BriefBuilder, handover_query
from lamplight_memory.schemas import MemoryItem
from lamplight_memory.transport.fake import FakeQwen

BEDS = [3, 5, 7, 9, 11, 12]


def test_handover_query_is_bed_specific():
    assert "bed 9" in handover_query(9)
    assert "bed 3" in handover_query(3)


@pytest.mark.parametrize("bed", BEDS)
@pytest.mark.parametrize("as_of", [3, 6, 9, 12, 14])
def test_brief_within_budget(ward_engine, bed, as_of):
    b = ward_engine.brief(bed, as_of_shift=as_of, save=False)
    assert b.token_count <= b.budget == DEFAULT_BUDGET


@pytest.mark.parametrize("bed", BEDS)
def test_brief_never_more_than_max_cards(ward_engine, bed):
    b = ward_engine.brief(bed, as_of_shift=14, save=False)
    assert len(b.cards) <= MAX_CARDS


@pytest.mark.parametrize("bed", BEDS)
def test_every_card_is_cited(ward_engine, bed):
    b = ward_engine.brief(bed, as_of_shift=14, save=False)
    for card in b.cards:
        assert card.citations, f"uncited card on bed {bed}: {card.sbar[:40]}"


def test_cards_priority_is_sequential(ward_engine):
    b = ward_engine.brief(9, as_of_shift=14, save=False)
    assert [c.priority for c in b.cards] == list(range(1, len(b.cards) + 1))


def test_brief_metadata(ward_engine):
    b = ward_engine.brief(9, as_of_shift=14, save=False)
    assert b.bed == 9
    assert b.as_of_shift == 14
    assert b.for_shift == 15
    assert b.engine == "fake"
    assert b.generated_at.endswith("Z")


# --------------------------------------------------------------------------- #
# the hero demo: bed 9, incoming shift 15 (memory as of close of shift 14)
# --------------------------------------------------------------------------- #


def test_hero_card_is_cefazolin_thread(ward_engine):
    b = ward_engine.brief(9, as_of_shift=14, save=False)
    top = b.cards[0]
    assert top.source_id == "mem-09-cefazolin-s12"
    assert set(top.citations) == {"ep-09-04-1", "ep-09-06-1", "ep-09-12-1"}
    assert "cefazolin" in top.sbar.lower()


def test_hero_retires_the_iv_red_herring(ward_engine):
    b = ward_engine.brief(9, as_of_shift=14, save=False)
    retired_ids = {r.id for r in b.retired}
    assert "ep-09-01-2" in retired_ids
    iv = next(r for r in b.retired if r.id == "ep-09-01-2")
    assert iv.reason == "resolved"
    assert iv.citation == "ep-09-02-1"  # cites the resolution episode


def test_hero_never_cites_the_resolved_iv(ward_engine):
    b = ward_engine.brief(9, as_of_shift=14, save=False)
    all_citations = {c for card in b.cards for c in card.citations}
    assert "ep-09-01-2" not in all_citations
    assert "ep-09-02-1" not in all_citations


def test_hero_reports_routine_decay(ward_engine):
    b = ward_engine.brief(9, as_of_shift=14, save=False)
    assert b.routine_expired_count > 0  # routine notes decayed out on schedule


# --------------------------------------------------------------------------- #
# contradiction surfacing (bed 5 sleep conflict, flagged at night shift 12)
# --------------------------------------------------------------------------- #


def test_contradiction_card_flagged(ward_engine):
    # detected at night shift 12; surfaces in the incoming-14 brief (as_of 13)
    b = ward_engine.brief(5, as_of_shift=13, save=False)
    conflict = [c for c in b.cards if c.needs_confirmation]
    assert conflict, "expected an unconfirmed sleep-conflict card on bed 5"
    assert conflict[0].source_id.startswith("mem-c-05-sleep")
    assert set(conflict[0].citations) == {"ep-05-10-2", "ep-05-12-1"}


# --------------------------------------------------------------------------- #
# budget scarcity as UX
# --------------------------------------------------------------------------- #


def test_tiny_budget_enforced(ward_engine):
    b = ward_engine.brief(9, as_of_shift=14, budget=120, save=False)
    assert b.token_count <= 120
    assert b.budget == 120


def test_tiny_budget_logs_left_out(ward_engine):
    b = ward_engine.brief(9, as_of_shift=14, budget=120, save=False)
    # things that didn't fit are explained, not silently dropped
    assert b.left_out
    reasons = {lo.reason for lo in b.left_out}
    assert reasons & {"budget_exhausted", "max_items_reached", "duplicate_thread", "item_exceeds_total_budget"}


def test_zero_shift_brief_rejected(ward_engine):
    with pytest.raises(ValueError):
        ward_engine.brief(9, as_of_shift=0, save=False)


# --------------------------------------------------------------------------- #
# default text_of (_plain_text) — the unsealer used when no engine override
# is supplied (documented in BriefBuilder.__init__)
# --------------------------------------------------------------------------- #


def test_default_text_of_unknown_item_raises(empty_store, fake):
    builder = BriefBuilder(empty_store, fake)
    with pytest.raises(KeyError):
        builder.text_of("ep-99-99-9")


def test_default_text_of_sealed_without_unsealer_raises(empty_store, fake):
    ep = add_ep(empty_store, fake, ep_dict(9, 1, 1, "hidden text", ["x"]))
    # rewrite the row to look sealed-at-rest (text NULL) without a real
    # unsealer wired up, mirroring what happens when a caller reuses
    # BriefBuilder's default text_of against a sealed store.
    empty_store.conn.execute("UPDATE episodes SET text=NULL WHERE id=?", (ep.id,))
    empty_store.conn.commit()
    builder = BriefBuilder(empty_store, fake)
    with pytest.raises(RuntimeError):
        builder.text_of(ep.id)


# --------------------------------------------------------------------------- #
# duplicate-thread suppression — a candidate whose citations are a strict
# subset of a stronger candidate's is dropped, not double-counted.
#
# Consolidation's "claim" rule keeps this from happening in the real 15-shift
# ward (an episode belongs to at most one family, ever), so this exercises
# the builder's own defensive rendering logic directly against a hand-built
# store state.
# --------------------------------------------------------------------------- #


def test_duplicate_thread_suppressed_in_left_out(empty_store, fake):
    e1 = add_ep(
        empty_store, fake,
        ep_dict(9, 1, 1, "falls risk unsteady to the bathroom", ["falls_risk"], decay_class="routine"),
    )
    e2 = add_ep(
        empty_store, fake,
        ep_dict(9, 1, 2, "falls risk unsteady overnight", ["falls_risk"], decay_class="routine"),
    )
    mem = MemoryItem(
        id="mem-09-falls_risk-s01", bed=9, kind="consolidated",
        text="falls risk — thread across 2 notes: unsteady to the bathroom, unsteady overnight",
        entities=["falls_risk"], decay_class="critical",
        provenance=[e1.id, e2.id], created_shift=1,
    )
    empty_store.add_memory(
        mem, fake.embed([mem.text])[0], mem.text, None, family="mem-09-falls_risk",
    )
    # NOTE: unlike real consolidation, e1/e2 are deliberately left unmerged
    # (no set_merged call) so they remain candidates alongside `mem`.

    builder = BriefBuilder(empty_store, fake)
    brief = builder.build(9, as_of_shift=1)

    dup_ids = {lo.id for lo in brief.left_out if lo.reason == "duplicate_thread"}
    assert dup_ids == {e1.id, e2.id}
    # the stronger (critical, superset-citations) memory wins the slot
    assert any(c.source_id == mem.id for c in brief.cards)
    for c in brief.cards:
        assert c.source_id not in dup_ids


# --------------------------------------------------------------------------- #
# live-LLM prose rewrite: the template SBAR/why_tonight are replaced when the
# transport supplies brief_prose(); citations/budget accounting stay intact.
# --------------------------------------------------------------------------- #


def test_brief_prose_rewrite_applied_when_transport_supplies_it(fresh_ward, monkeypatch):
    def fake_brief_prose(self, context):
        return {"sbar": "REWRITTEN: " + context["facts"][:40], "why_tonight": "rewritten why"}

    monkeypatch.setattr(FakeQwen, "brief_prose", fake_brief_prose)
    brief = fresh_ward.brief(9, as_of_shift=14, save=False)
    assert brief.cards, "expected at least one card to rewrite"
    assert any(c.sbar.startswith("REWRITTEN: ") for c in brief.cards)
    assert any(c.why_tonight == "rewritten why" for c in brief.cards)
    assert brief.token_count <= brief.budget  # I3 still holds after the rewrite


def test_brief_prose_rewrite_skipped_when_it_would_bust_budget(fresh_ward, monkeypatch):
    huge = "x " * 5000  # far too many tokens for even the whole budget

    def fake_brief_prose(self, context):
        return {"sbar": huge, "why_tonight": "why"}

    monkeypatch.setattr(FakeQwen, "brief_prose", fake_brief_prose)
    brief = fresh_ward.brief(9, as_of_shift=14, budget=200, save=False)
    assert not any(c.sbar == huge for c in brief.cards)
    assert brief.token_count <= 200


# --------------------------------------------------------------------------- #
# no candidates at all (bed never ingested) -> empty brief, no crash
# --------------------------------------------------------------------------- #


def test_brief_with_no_candidates_is_empty(ward_engine):
    brief = ward_engine.brief(99, as_of_shift=3, save=False)
    assert brief.cards == []
    assert brief.token_count == 0
