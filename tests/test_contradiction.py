"""ContradictionResolver — conflicting reports become human-confirm flags."""

from __future__ import annotations

from conftest import add_ep, ep_dict, text_of_plain

from lamplight_memory.contradiction import WINDOW_SHIFTS, ContradictionResolver


def make(store):
    return ContradictionResolver(store, text_of=text_of_plain(store))


def seed_sleep_conflict(store, fake, pos_shift=10, neg_shift=12):
    add_ep(store, fake, ep_dict(5, pos_shift, 2, "reports slept well overnight", ["sleep"], polarity="pos"))
    add_ep(store, fake, ep_dict(5, neg_shift, 1, "up 4 times overnight, exhausted", ["sleep"], polarity="neg"))


def test_pos_neg_same_entity_flags(empty_store, fake):
    seed_sleep_conflict(empty_store, fake)
    flags = make(empty_store).detect(5, 12)
    assert len(flags) == 1
    assert flags[0].family == "mem-c-05-sleep"


def test_flag_needs_confirmation(empty_store, fake):
    seed_sleep_conflict(empty_store, fake)
    flag = make(empty_store).detect(5, 12)[0]
    assert flag.memory.needs_confirmation is True
    assert flag.memory.kind == "contradiction"


def test_flag_provenance_is_the_pair_sorted(empty_store, fake):
    seed_sleep_conflict(empty_store, fake, pos_shift=10, neg_shift=12)
    flag = make(empty_store).detect(5, 12)[0]
    assert flag.memory.provenance == ["ep-05-10-2", "ep-05-12-1"]


def test_flag_class_is_condition(empty_store, fake):
    seed_sleep_conflict(empty_store, fake)
    flag = make(empty_store).detect(5, 12)[0]
    assert flag.memory.decay_class.value == "condition"


def test_same_polarity_no_flag(empty_store, fake):
    add_ep(empty_store, fake, ep_dict(5, 10, 1, "slept well", ["sleep"], polarity="pos"))
    add_ep(empty_store, fake, ep_dict(5, 12, 1, "rested well again", ["sleep"], polarity="pos"))
    assert make(empty_store).detect(5, 12) == []


def test_neutral_ignored(empty_store, fake):
    add_ep(empty_store, fake, ep_dict(5, 10, 1, "slept", ["sleep"], polarity="neutral"))
    add_ep(empty_store, fake, ep_dict(5, 12, 1, "up all night", ["sleep"], polarity="neutral"))
    assert make(empty_store).detect(5, 12) == []


def test_outside_window_no_flag(empty_store, fake):
    # more than WINDOW_SHIFTS apart
    seed_sleep_conflict(empty_store, fake, pos_shift=1, neg_shift=1 + WINDOW_SHIFTS + 1)
    assert make(empty_store).detect(5, 1 + WINDOW_SHIFTS + 1) == []


def test_within_window_boundary_flags(empty_store, fake):
    seed_sleep_conflict(empty_store, fake, pos_shift=2, neg_shift=2 + WINDOW_SHIFTS)
    assert len(make(empty_store).detect(5, 2 + WINDOW_SHIFTS)) == 1


def test_entities_on_flag(empty_store, fake):
    seed_sleep_conflict(empty_store, fake)
    flag = make(empty_store).detect(5, 12)[0]
    assert flag.memory.entities == ["sleep"]


def test_flag_text_mentions_both(empty_store, fake):
    seed_sleep_conflict(empty_store, fake)
    flag = make(empty_store).detect(5, 12)[0]
    assert "CONFLICTING" in flag.memory.text
    assert "slept well" in flag.memory.text
    assert "up 4 times" in flag.memory.text


def test_second_open_flag_for_same_entity_is_suppressed(empty_store, fake):
    # "one open flag per entity": once a contradiction memory exists for a
    # family, a later conflicting pair on the same entity must not spawn a
    # second flag until a human resolves the first one.
    seed_sleep_conflict(empty_store, fake)
    resolver = make(empty_store)
    flags = resolver.detect(5, 12)
    assert len(flags) == 1
    flag = flags[0]

    # persist the flag exactly as the engine's _nightly() does
    vec = fake.embed([flag.memory.text])[0]
    empty_store.add_memory(flag.memory, vec, flag.memory.text, None, family=flag.family)
    empty_store.set_merged(list(flag.pair), flag.memory.id, 12)

    # a fresh conflicting pair for the SAME entity, well within the window
    add_ep(empty_store, fake, ep_dict(5, 13, 1, "slept fine tonight", ["sleep"], polarity="pos"))
    add_ep(empty_store, fake, ep_dict(5, 14, 1, "restless again overnight", ["sleep"], polarity="neg"))

    again = resolver.detect(5, 14)
    assert again == []
