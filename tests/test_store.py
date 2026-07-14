"""MemoryStore — episodic + semantic store with as-of time travel."""

from __future__ import annotations

import pytest
from conftest import add_ep, ep_dict, text_of_plain

from lamplight_memory.schemas import MemoryItem, Status
from lamplight_memory.store import cosine

# --------------------------------------------------------------------------- #
# cosine
# --------------------------------------------------------------------------- #


def test_cosine_identical():
    assert cosine([1.0, 0.0, 0.0], [1.0, 0.0, 0.0]) == pytest.approx(1.0)


def test_cosine_orthogonal():
    assert cosine([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_cosine_zero_vector():
    assert cosine([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_cosine_dimension_mismatch():
    with pytest.raises(ValueError):
        cosine([1.0], [1.0, 2.0])


def test_cosine_normalizes():
    assert cosine([2.0, 0.0], [5.0, 0.0]) == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# writes + status
# --------------------------------------------------------------------------- #


def test_add_and_exists(empty_store, fake):
    add_ep(empty_store, fake, ep_dict(9, 4, 1, "cefazolin started", ["cefazolin"], decay_class="condition", type="order"))
    assert empty_store.exists("ep-09-04-1")
    assert empty_store.get_row("ep-09-04-1")[0] == "episode"


def test_duplicate_id_rejected(empty_store, fake):
    d = ep_dict(9, 4, 1, "cefazolin", ["cefazolin"])
    add_ep(empty_store, fake, d)
    with pytest.raises(ValueError):
        add_ep(empty_store, fake, d)


def test_resolution_episode_retires_immediately(empty_store, fake):
    add_ep(
        empty_store, fake,
        ep_dict(9, 2, 1, "IV concern resolved", ["iv_site"],
                decay_class="resolved", type="resolution", resolves="iv_site"),
    )
    assert empty_store.status_at("ep-09-02-1", 2) is Status.RESOLVED


def test_status_time_travel(empty_store, fake):
    add_ep(empty_store, fake, ep_dict(3, 5, 1, "warfarin", ["warfarin"], decay_class="critical"))
    assert empty_store.status_at("ep-03-05-1", 4) is None  # not yet created
    assert empty_store.status_at("ep-03-05-1", 5) is Status.ACTIVE


def test_mark_resolved_sets_shift(empty_store, fake):
    add_ep(empty_store, fake, ep_dict(3, 5, 1, "iv", ["iv_site"], decay_class="condition"))
    changed = empty_store.mark_resolved(["ep-03-05-1"], 7)
    assert changed == ["ep-03-05-1"]
    assert empty_store.status_at("ep-03-05-1", 6) is Status.ACTIVE
    assert empty_store.status_at("ep-03-05-1", 7) is Status.RESOLVED


def test_mark_expired(empty_store, fake):
    add_ep(empty_store, fake, ep_dict(3, 5, 1, "routine", ["meals"]))
    empty_store.mark_expired(["ep-03-05-1"], 6)
    assert empty_store.status_at("ep-03-05-1", 6) is Status.EXPIRED


def test_pin_sets_pinned(empty_store, fake):
    add_ep(empty_store, fake, ep_dict(3, 5, 1, "x", ["meals"]))
    assert empty_store.pin("ep-03-05-1") is True
    assert empty_store.status_at("ep-03-05-1", 5) is Status.PINNED


def test_pin_only_active(empty_store, fake):
    add_ep(empty_store, fake, ep_dict(3, 5, 1, "x", ["meals"]))
    empty_store.mark_resolved(["ep-03-05-1"], 6)
    assert empty_store.pin("ep-03-05-1") is False


def test_update_strength(empty_store, fake):
    add_ep(empty_store, fake, ep_dict(3, 5, 1, "x", ["meals"]))
    assert empty_store.update_strength("ep-03-05-1", 0.5) is True
    _, row = empty_store.get_row("ep-03-05-1")
    assert row["s0"] == 0.5


# --------------------------------------------------------------------------- #
# retrieval views
# --------------------------------------------------------------------------- #


def test_active_episode_rows_for_brief_excludes_resolution(empty_store, fake):
    add_ep(empty_store, fake, ep_dict(9, 1, 1, "leg cellulitis", ["cellulitis"]))
    add_ep(
        empty_store, fake,
        ep_dict(9, 2, 1, "iv resolved", ["iv_site"],
                decay_class="resolved", type="resolution", resolves="iv_site"),
    )
    rows = empty_store.active_episode_rows(9, 5, for_brief=True)
    ids = {r["id"] for r in rows}
    assert "ep-09-01-1" in ids
    assert "ep-09-02-1" not in ids  # resolution filtered from brief candidates


def test_all_episode_rows_is_naive_view(empty_store, fake):
    # baseline view returns raw episodes regardless of status
    add_ep(empty_store, fake, ep_dict(9, 1, 1, "leg", ["cellulitis"]))
    add_ep(
        empty_store, fake,
        ep_dict(9, 2, 1, "iv resolved", ["iv_site"],
                decay_class="resolved", type="resolution", resolves="iv_site"),
    )
    rows = empty_store.all_episode_rows(9, 15)
    assert len(rows) == 2  # includes the resolved one — naive RAG never forgets


def test_brief_candidates_sorted_by_id(empty_store, fake):
    add_ep(empty_store, fake, ep_dict(9, 3, 1, "b", ["cellulitis"]))
    add_ep(empty_store, fake, ep_dict(9, 1, 1, "a", ["cellulitis"]))
    cands = empty_store.brief_candidates(9, 5)
    assert [c.id for c in cands] == sorted(c.id for c in cands)


def test_top_k_returns_scored(empty_store, fake):
    add_ep(empty_store, fake, ep_dict(9, 1, 1, "falls risk unsteady", ["falls_risk"]))
    add_ep(empty_store, fake, ep_dict(9, 2, 1, "ate lunch meals", ["meals"]))
    cands = empty_store.brief_candidates(9, 5)
    qvec = fake.embed(["falls risk"])[0]
    ranked = empty_store.top_k(qvec, cands, 2)
    assert len(ranked) == 2
    # the falls episode should out-score the meals episode for a falls query
    assert ranked[0][0].entities == ["falls_risk"]


def test_episode_shifts(empty_store, fake):
    add_ep(empty_store, fake, ep_dict(9, 4, 1, "x", ["cefazolin"]))
    add_ep(empty_store, fake, ep_dict(9, 6, 1, "y", ["skin_reaction"]))
    got = empty_store.episode_shifts(["ep-09-04-1", "ep-09-06-1", "nope"])
    assert got == {"ep-09-04-1": 4, "ep-09-06-1": 6}


# --------------------------------------------------------------------------- #
# memories / versioning
# --------------------------------------------------------------------------- #


def _mem(store, fake, family, created_shift, provenance, mid=None):
    mem = MemoryItem(
        id=mid or f"{family}-s{created_shift:02d}",
        bed=9, kind="consolidated", text=f"{family} thread",
        decay_class="critical", provenance=provenance, created_shift=created_shift,
    )
    return mem


def test_add_memory_and_latest_version(empty_store, fake):
    add_ep(empty_store, fake, ep_dict(9, 4, 1, "x", ["cefazolin"]))
    add_ep(empty_store, fake, ep_dict(9, 6, 1, "y", ["cefazolin"]))
    m = _mem(empty_store, fake, "mem-09-cefazolin", 6, ["ep-09-04-1", "ep-09-06-1"])
    empty_store.add_memory(m, fake.embed([m.text])[0], m.text, None, family="mem-09-cefazolin")
    latest = empty_store.latest_memory_version("mem-09-cefazolin", 6)
    assert latest["id"] == "mem-09-cefazolin-s06"


def test_duplicate_memory_id_rejected(empty_store, fake):
    add_ep(empty_store, fake, ep_dict(9, 4, 1, "x", ["cefazolin"]))
    add_ep(empty_store, fake, ep_dict(9, 6, 1, "y", ["cefazolin"]))
    m = _mem(empty_store, fake, "mem-09-cefazolin", 6, ["ep-09-04-1", "ep-09-06-1"])
    empty_store.add_memory(m, fake.embed([m.text])[0], m.text, None, family="mem-09-cefazolin")
    with pytest.raises(ValueError):
        empty_store.add_memory(m, fake.embed([m.text])[0], m.text, None, family="mem-09-cefazolin")


def test_status_at_unknown_item_is_none(empty_store, fake):
    assert empty_store.status_at("ep-99-99-9", 5) is None


def test_memory_supersede(empty_store, fake):
    add_ep(empty_store, fake, ep_dict(9, 4, 1, "x", ["cefazolin"]))
    add_ep(empty_store, fake, ep_dict(9, 6, 1, "y", ["cefazolin"]))
    add_ep(empty_store, fake, ep_dict(9, 12, 1, "z", ["cefazolin"]))
    m1 = _mem(empty_store, fake, "mem-09-cefazolin", 6, ["ep-09-04-1", "ep-09-06-1"])
    empty_store.add_memory(m1, fake.embed([m1.text])[0], m1.text, None, family="mem-09-cefazolin")
    m2 = _mem(empty_store, fake, "mem-09-cefazolin", 12, ["ep-09-04-1", "ep-09-06-1", "ep-09-12-1"])
    empty_store.add_memory(
        m2, fake.embed([m2.text])[0], m2.text, None,
        family="mem-09-cefazolin", supersedes="mem-09-cefazolin-s06",
    )
    # as of shift 9 the v6 memory is active; as of shift 12 the v12 one is
    assert len(empty_store.active_memory_rows(9, 9)) == 1
    active12 = empty_store.active_memory_rows(9, 13)
    assert [r["id"] for r in active12] == ["mem-09-cefazolin-s12"]


# --------------------------------------------------------------------------- #
# retired panel + counts
# --------------------------------------------------------------------------- #


def test_retired_rows_lists_resolved_critical(empty_store, fake):
    add_ep(empty_store, fake, ep_dict(9, 1, 1, "iv site red", ["iv_site"], decay_class="condition"))
    empty_store.mark_resolved(["ep-09-01-1"], 2)
    retired = empty_store.retired_rows(9, 5)
    assert any(r["id"] == "ep-09-01-1" for r in retired)


def test_routine_expired_count(empty_store, fake):
    add_ep(empty_store, fake, ep_dict(9, 1, 1, "meal", ["meals"]))
    add_ep(empty_store, fake, ep_dict(9, 1, 2, "vitals", ["vitals"]))
    empty_store.mark_expired(["ep-09-01-1", "ep-09-01-2"], 3)
    assert empty_store.routine_expired_count(9, 5) == 2


def test_counts_and_max_shift(empty_store, fake):
    add_ep(empty_store, fake, ep_dict(9, 1, 1, "a", ["x"]))
    add_ep(empty_store, fake, ep_dict(9, 7, 1, "b", ["y"]))
    counts = empty_store.counts()
    assert counts["episodes"] == 2
    assert empty_store.max_ingested_shift() == 7


def test_text_of_plain_helper(empty_store, fake):
    add_ep(empty_store, fake, ep_dict(9, 1, 1, "hello world", ["x"]))
    assert text_of_plain(empty_store)("ep-09-01-1") == "hello world"
