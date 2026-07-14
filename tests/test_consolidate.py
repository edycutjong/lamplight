"""Consolidator — nightly semantic merge with provenance lists (SPEC §5)."""

from __future__ import annotations

from conftest import add_ep, ep_dict, text_of_plain

from lamplight_memory.consolidate import Consolidator, entity_slug


def make(store, fake):
    return Consolidator(store, text_of=text_of_plain(store))


def persist(store, fake, result):
    """Write a consolidation result back like the engine does."""
    vec = fake.embed([result.memory.text])[0]
    store.add_memory(
        result.memory, vec, result.memory.text, None,
        family=result.family, supersedes=result.supersedes,
    )
    store.set_merged(result.newly_merged, result.memory.id, result.memory.created_shift)


def test_entity_slug():
    assert entity_slug("Skin Reaction") == "skin_reaction"
    assert entity_slug(" cefazolin ") == "cefazolin"


def test_two_episodes_same_entity_merge(empty_store, fake):
    add_ep(empty_store, fake, ep_dict(9, 4, 1, "cefazolin started for cellulitis", ["cefazolin"], decay_class="condition", type="order"))
    add_ep(empty_store, fake, ep_dict(9, 6, 1, "erythema forearm possibly antibiotic", ["cefazolin"], decay_class="critical"))
    results = make(empty_store, fake).run(9, 6)
    fams = {r.family for r in results}
    assert "mem-09-cefazolin" in fams
    mem = next(r.memory for r in results if r.family == "mem-09-cefazolin")
    assert mem.provenance == ["ep-09-04-1", "ep-09-06-1"]


def test_merged_class_is_max_criticality(empty_store, fake):
    add_ep(empty_store, fake, ep_dict(9, 4, 1, "cef order", ["cefazolin"], decay_class="condition", type="order"))
    add_ep(empty_store, fake, ep_dict(9, 6, 1, "reaction", ["cefazolin"], decay_class="critical"))
    mem = next(r.memory for r in make(empty_store, fake).run(9, 6) if r.family == "mem-09-cefazolin")
    assert mem.decay_class.value == "critical"


def test_provenance_sorted_by_shift(empty_store, fake):
    add_ep(empty_store, fake, ep_dict(9, 6, 1, "later", ["cefazolin"], decay_class="critical"))
    add_ep(empty_store, fake, ep_dict(9, 4, 1, "earlier", ["cefazolin"], decay_class="condition", type="order"))
    mem = next(r.memory for r in make(empty_store, fake).run(9, 6) if r.family == "mem-09-cefazolin")
    assert mem.provenance == ["ep-09-04-1", "ep-09-06-1"]


def test_single_episode_does_not_form_memory(empty_store, fake):
    add_ep(empty_store, fake, ep_dict(3, 7, 1, "unsteady to bathroom", ["falls_risk"], decay_class="critical"))
    results = make(empty_store, fake).run(3, 7)
    assert all(r.family != "mem-03-falls_risk" for r in results)


def test_existing_memory_extends_with_one_new(empty_store, fake):
    cons = make(empty_store, fake)
    add_ep(empty_store, fake, ep_dict(9, 4, 1, "cef order", ["cefazolin"], decay_class="condition", type="order"))
    add_ep(empty_store, fake, ep_dict(9, 6, 1, "erythema", ["cefazolin"], decay_class="critical"))
    for r in cons.run(9, 6):
        persist(empty_store, fake, r)
    # a third, later episode extends the family with a single new member
    add_ep(empty_store, fake, ep_dict(9, 12, 1, "red patches again", ["cefazolin"], decay_class="critical"))
    results = cons.run(9, 12)
    ext = next(r for r in results if r.family == "mem-09-cefazolin")
    assert ext.supersedes == "mem-09-cefazolin-s06"
    assert ext.memory.provenance == ["ep-09-04-1", "ep-09-06-1", "ep-09-12-1"]
    assert ext.newly_merged == ["ep-09-12-1"]


def test_provenance_never_empty(empty_store, fake):
    add_ep(empty_store, fake, ep_dict(11, 1, 1, "weight 82", ["fluid_status"], decay_class="condition"))
    add_ep(empty_store, fake, ep_dict(11, 4, 1, "weight 81", ["fluid_status"], decay_class="condition"))
    for r in make(empty_store, fake).run(11, 4):
        assert r.memory.provenance  # MemoryItem enforces >=1


def test_results_are_entity_sorted(empty_store, fake):
    add_ep(empty_store, fake, ep_dict(5, 1, 1, "cough thick", ["cough"], decay_class="condition"))
    add_ep(empty_store, fake, ep_dict(5, 2, 1, "cough looser", ["cough"], decay_class="condition"))
    add_ep(empty_store, fake, ep_dict(5, 1, 2, "sats 93", ["oxygen"], decay_class="condition"))
    add_ep(empty_store, fake, ep_dict(5, 2, 2, "sats 94", ["oxygen"], decay_class="condition"))
    fams = [r.family for r in make(empty_store, fake).run(5, 2)]
    assert fams == sorted(fams)


def test_episode_claimed_once(empty_store, fake):
    # an episode with two entities seeds only one memory (first sorted entity)
    add_ep(empty_store, fake, ep_dict(9, 4, 1, "aaa", ["alpha", "cefazolin"], decay_class="condition"))
    add_ep(empty_store, fake, ep_dict(9, 6, 1, "bbb", ["alpha"], decay_class="condition"))
    add_ep(empty_store, fake, ep_dict(9, 6, 2, "ccc", ["cefazolin"], decay_class="condition"))
    results = make(empty_store, fake).run(9, 6)
    claimed = [mid for r in results for mid in r.newly_merged]
    # ep-09-04-1 appears as newly_merged for at most one family
    assert claimed.count("ep-09-04-1") == 1
