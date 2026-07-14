"""LamplightEngine — full ingest -> consolidate/decay -> brief lifecycle."""

from __future__ import annotations

import pytest

from lamplight_memory.clock import iso, shift_start
from lamplight_memory.engine import LamplightEngine
from lamplight_memory.schemas import Status
from lamplight_memory.transport.fake import FakeQwen


@pytest.fixture
def engine(fixtures_root, tmp_path):
    e = LamplightEngine(tmp_path / "e.db", FakeQwen(fixtures_root=fixtures_root), seal=True)
    yield e
    e.close()


def ingest(engine, fixtures_root, shift):
    return engine.ingest_shift(shift, fixtures_root / "notes" / f"shift_{shift:02d}")


def test_ingest_summary_shape(engine, fixtures_root):
    summary = ingest(engine, fixtures_root, 1)
    assert summary["shift"] == 1
    assert summary["episodes"] > 0
    assert set(summary["ops"]) == {"write", "expire", "decay", "contradict", "consolidate"}


def test_write_ops_equal_episode_count(engine, fixtures_root):
    summary = ingest(engine, fixtures_root, 1)
    assert summary["ops"]["write"] == summary["episodes"]


def test_decay_op_every_shift(engine, fixtures_root):
    summary = ingest(engine, fixtures_root, 1)
    assert summary["ops"]["decay"] >= 1  # a signed decay sweep runs at every close


def test_resolution_retires_target(engine, fixtures_root):
    ingest(engine, fixtures_root, 1)
    ingest(engine, fixtures_root, 2)  # bed 9 IV concern resolved this shift
    assert engine.store.status_at("ep-09-01-2", 2) is Status.RESOLVED


def test_nightly_consolidation_builds_memories(engine, fixtures_root):
    for s in range(1, 7):
        ingest(engine, fixtures_root, s)
    assert engine.store.counts()["memories"] > 0


def test_cefazolin_memory_family_forms(engine, fixtures_root):
    for s in range(1, 13):
        ingest(engine, fixtures_root, s)
    latest = engine.store.latest_memory_version("mem-09-cefazolin", 12)
    assert latest is not None
    assert "ep-09-12-1" in latest["provenance"]


def test_verify_chain_ok(fresh_ward):
    rep = fresh_ward.verify_chain()
    assert rep.ok is True
    assert rep.length > 100


def test_chain_has_all_op_types(fresh_ward):
    rep = fresh_ward.verify_chain()
    for op in ("write", "decay", "expire", "consolidate", "contradict"):
        assert rep.ops_by_type.get(op, 0) > 0, f"no {op} ops recorded"


def test_missing_notes_dir_raises(engine, tmp_path):
    with pytest.raises(FileNotFoundError):
        engine.ingest_shift(1, tmp_path / "does_not_exist")


# --------------------------------------------------------------------------- #
# sealed-at-rest materialization
# --------------------------------------------------------------------------- #


def test_text_of_unseals(fresh_ward):
    # with sealing on, the plaintext column is NULL but text_of recovers it
    _, row = fresh_ward.store.get_row("ep-09-06-1")
    assert row["text"] is None
    assert "erythema" in fresh_ward.text_of("ep-09-06-1")


def test_text_of_unknown_raises(fresh_ward):
    with pytest.raises(KeyError):
        fresh_ward.text_of("ep-99-99-9")


# --------------------------------------------------------------------------- #
# pin + feedback ops
# --------------------------------------------------------------------------- #


def test_pin_holds_and_signs(fresh_ward):
    before = fresh_ward.chain.length()
    assert fresh_ward.pin("ep-03-01-2") is True
    assert fresh_ward.store.status_at("ep-03-01-2", 15) is Status.PINNED
    assert fresh_ward.chain.length() == before + 1
    assert fresh_ward.verify_chain().ok


def test_feedback_correct_halves_strength(fresh_ward):
    brief = fresh_ward.brief(9, as_of_shift=14, save=False)
    bid = fresh_ward.store.save_brief(brief)
    src = brief.cards[0].source_id
    _, row = fresh_ward.store.get_row(src)
    assert row["s0"] == 1.0
    fresh_ward.feedback(bid, 0, "correct")
    _, row2 = fresh_ward.store.get_row(src)
    assert row2["s0"] == pytest.approx(0.5)


def test_feedback_confirm_signs_and_returns(fresh_ward):
    brief = fresh_ward.brief(9, as_of_shift=14, save=False)
    bid = fresh_ward.store.save_brief(brief)
    result = fresh_ward.feedback(bid, 0, "confirm")
    assert result["action"] == "confirm"
    assert fresh_ward.verify_chain().ok


def test_feedback_confirm_clears_contradiction(fresh_ward):
    brief = fresh_ward.brief(5, as_of_shift=13, save=False)
    bid = fresh_ward.store.save_brief(brief)
    ix = next(i for i, c in enumerate(brief.cards) if c.needs_confirmation)
    src = brief.cards[ix].source_id
    fresh_ward.feedback(bid, ix, "confirm")
    _, row = fresh_ward.store.get_row(src)
    assert row["needs_confirmation"] == 0


def test_feedback_dismiss_expires(fresh_ward):
    brief = fresh_ward.brief(9, as_of_shift=14, save=False)
    bid = fresh_ward.store.save_brief(brief)
    src = brief.cards[0].source_id
    fresh_ward.feedback(bid, 0, "dismiss")
    assert fresh_ward.store.status_at(src, 15) is Status.EXPIRED


def test_feedback_unknown_action_raises(fresh_ward):
    brief = fresh_ward.brief(9, as_of_shift=14, save=False)
    bid = fresh_ward.store.save_brief(brief)
    with pytest.raises(ValueError):
        fresh_ward.feedback(bid, 0, "shrug")


def test_feedback_bad_brief_id_raises(fresh_ward):
    with pytest.raises(KeyError):
        fresh_ward.feedback(99999, 0, "confirm")


# --------------------------------------------------------------------------- #
# small synthetic-ward helpers (extraction_map transport, no clinical
# fixtures needed) — for lifecycle edge cases the real 15-shift ward
# doesn't happen to exercise
# --------------------------------------------------------------------------- #


def _mini_engine(tmp_path, extraction_map, seal=True, db_name="mini.db"):
    return LamplightEngine(tmp_path / db_name, FakeQwen(extraction_map=extraction_map), seal=seal)


def _write_notes(tmp_path, shift, beds, subdir="notes"):
    notes_dir = tmp_path / subdir / f"shift_{shift:02d}"
    notes_dir.mkdir(parents=True, exist_ok=True)
    for bed in beds:
        (notes_dir / f"bed_{bed:02d}.txt").write_text("dummy note text")
    return notes_dir


# --------------------------------------------------------------------------- #
# live-transport-shaped episode (empty ts) -> engine assigns the ward-clock ts
# --------------------------------------------------------------------------- #


def test_ingest_assigns_ts_when_transport_leaves_it_empty(tmp_path):
    extraction_map = {
        (9, 1): [
            {
                "id": "ep-09-01-1", "bed": 9, "shift": 1, "ts": "",
                "type": "observation", "text": "hello", "entities": ["x"],
                "polarity": "neutral", "decay_class": "routine",
                "resolves": None, "why_hint": None,
            },
            {
                "id": "ep-09-01-2", "bed": 9, "shift": 1, "ts": "",
                "type": "observation", "text": "world", "entities": ["y"],
                "polarity": "neutral", "decay_class": "routine",
                "resolves": None, "why_hint": None,
            },
        ]
    }
    notes_dir = _write_notes(tmp_path, 1, [9])
    engine = _mini_engine(tmp_path, extraction_map)
    try:
        engine.ingest_shift(1, notes_dir)
        _, row1 = engine.store.get_row("ep-09-01-1")
        _, row2 = engine.store.get_row("ep-09-01-2")
        assert row1["ts"] and row1["ts"] != ""
        assert row2["ts"] and row2["ts"] != ""
        # the k-th episode's offset is deterministic and strictly increasing
        assert row2["ts"] > row1["ts"]
    finally:
        engine.close()


# --------------------------------------------------------------------------- #
# ingest_shift: empty (but existing) notes dir
# --------------------------------------------------------------------------- #


def test_ingest_shift_empty_notes_dir_raises(tmp_path):
    empty_dir = tmp_path / "empty_notes"
    empty_dir.mkdir()
    engine = _mini_engine(tmp_path, {})
    try:
        with pytest.raises(FileNotFoundError):
            engine.ingest_shift(1, empty_dir)
    finally:
        engine.close()


# --------------------------------------------------------------------------- #
# text_of / sealing edge cases
# --------------------------------------------------------------------------- #


def test_text_of_unsealed_engine_reads_plaintext_column(tmp_path):
    extraction_map = {
        (9, 1): [{
            "id": "ep-09-01-1", "bed": 9, "shift": 1, "ts": "2026-01-01T00:00:00Z",
            "type": "observation", "text": "plaintext note", "entities": ["x"],
            "polarity": "neutral", "decay_class": "routine",
            "resolves": None, "why_hint": None,
        }]
    }
    notes_dir = _write_notes(tmp_path, 1, [9])
    engine = _mini_engine(tmp_path, extraction_map, seal=False)
    try:
        engine.ingest_shift(1, notes_dir)
        _, row = engine.store.get_row("ep-09-01-1")
        assert row["text"] == "plaintext note"  # never sealed
        assert engine.text_of("ep-09-01-1") == "plaintext note"
    finally:
        engine.close()


def test_text_of_sealed_row_with_no_envelope_raises(tmp_path):
    # a malformed store state: text NULL, no sealed blob either
    from lamplight_memory.schemas import DecayClass, Episode, EpisodeType

    engine = _mini_engine(tmp_path, {}, seal=True)
    try:
        ep = Episode(
            id="ep-09-01-1", bed=9, shift=1, ts="2026-01-01T00:00:00Z",
            type=EpisodeType.OBSERVATION, text="ghost", entities=["x"],
            decay_class=DecayClass.ROUTINE,
        )
        vec = engine.transport.embed([ep.text])[0]
        engine.store.add_episode(ep, vec, None, None)  # neither plaintext nor sealed blob
        with pytest.raises(RuntimeError):
            engine.text_of("ep-09-01-1")
    finally:
        engine.close()


def test_text_of_sealed_row_without_sealer_raises(tmp_path):
    # write with a sealing engine, then reopen the same db without a sealer
    extraction_map = {
        (9, 1): [{
            "id": "ep-09-01-1", "bed": 9, "shift": 1, "ts": "2026-01-01T00:00:00Z",
            "type": "observation", "text": "secret note", "entities": ["x"],
            "polarity": "neutral", "decay_class": "routine",
            "resolves": None, "why_hint": None,
        }]
    }
    notes_dir = _write_notes(tmp_path, 1, [9])
    engine1 = _mini_engine(tmp_path, extraction_map, seal=True, db_name="sealed.db")
    engine1.ingest_shift(1, notes_dir)
    engine1.close()

    engine2 = LamplightEngine(tmp_path / "sealed.db", FakeQwen(extraction_map={}), seal=False)
    try:
        with pytest.raises(RuntimeError):
            engine2.text_of("ep-09-01-1")
    finally:
        engine2.close()


# --------------------------------------------------------------------------- #
# resolution targeting: memories (not just episodes), and untracked entities
# --------------------------------------------------------------------------- #


def test_resolution_retires_consolidated_memory_and_ignores_untracked_entity(tmp_path):
    extraction_map = {
        (9, 1): [
            {
                "id": "ep-09-01-1", "bed": 9, "shift": 1, "ts": iso(shift_start(1)),
                "type": "observation", "text": "rash noted", "entities": ["rash"],
                "polarity": "neutral", "decay_class": "condition",
                "resolves": None, "why_hint": None,
            },
            {
                "id": "ep-09-01-2", "bed": 9, "shift": 1, "ts": iso(shift_start(1)),
                "type": "observation", "text": "rash still present", "entities": ["rash"],
                "polarity": "neutral", "decay_class": "condition",
                "resolves": None, "why_hint": None,
            },
        ],
        (9, 2): [],
        (9, 3): [],  # night close -> consolidates the two rash episodes
        (9, 4): [
            {
                "id": "ep-09-04-1", "bed": 9, "shift": 4, "ts": iso(shift_start(4)),
                "type": "resolution", "text": "rash resolved", "entities": ["rash"],
                "polarity": "neutral", "decay_class": "resolved",
                "resolves": "rash", "why_hint": None,
            },
            {
                # resolves an entity nothing has ever tracked -> empty targets
                "id": "ep-09-04-2", "bed": 9, "shift": 4, "ts": iso(shift_start(4)),
                "type": "resolution", "text": "ghost entity resolved", "entities": [],
                "polarity": "neutral", "decay_class": "resolved",
                "resolves": "ghost_entity_never_tracked", "why_hint": None,
            },
        ],
    }
    engine = _mini_engine(tmp_path, extraction_map)
    try:
        for shift in (1, 2, 3):
            engine.ingest_shift(shift, _write_notes(tmp_path, shift, [9]))
        assert engine.store.counts()["memories"] == 1
        family = engine.store.latest_memory_version("mem-09-rash", 3)
        assert family is not None
        mem_id = family["id"]

        summary = engine.ingest_shift(4, _write_notes(tmp_path, 4, [9]))
        assert summary["ops"]["expire"] >= 1  # the rash resolution fired a signed op

        # the consolidated memory itself was retired, via the active_memory_rows
        # scan in _process_resolutions (not just the underlying episodes)
        _, mem_row = engine.store.get_row(mem_id)
        assert mem_row["resolved_shift"] == 4

        # the untracked "ghost" resolution found no targets and was a no-op
        # (no exception, no extra expire op attributable to it)
        assert engine.store.status_at("ep-09-04-2", 4).value == "resolved"  # resolution itself
    finally:
        engine.close()


# --------------------------------------------------------------------------- #
# brief() default as_of_shift
# --------------------------------------------------------------------------- #


def test_brief_defaults_as_of_to_max_ingested_shift(fresh_ward):
    # fresh_ward has all 15 shifts ingested -> max_ingested_shift() == 15
    b_explicit = fresh_ward.brief(9, as_of_shift=15, save=False)
    b_default = fresh_ward.brief(9, save=False)
    assert b_default.as_of_shift == 15 == b_explicit.as_of_shift


def test_brief_on_nothing_ingested_raises(tmp_path):
    engine = _mini_engine(tmp_path, {})
    try:
        with pytest.raises(ValueError):
            engine.brief(9)  # as_of_shift=None -> max_ingested_shift() == 0
    finally:
        engine.close()


def test_brief_default_save_true_persists(fresh_ward):
    before = fresh_ward.store.counts()["briefs"]
    fresh_ward.brief(9, as_of_shift=14)  # save defaults to True
    after = fresh_ward.store.counts()["briefs"]
    assert after == before + 1


# --------------------------------------------------------------------------- #
# feedback() defensive paths
# --------------------------------------------------------------------------- #


def test_feedback_bad_card_index_raises(fresh_ward):
    brief = fresh_ward.brief(9, as_of_shift=14, save=False)
    bid = fresh_ward.store.save_brief(brief)
    with pytest.raises(IndexError):
        fresh_ward.feedback(bid, 999, "confirm")


def test_feedback_missing_source_row_raises(fresh_ward):
    brief = fresh_ward.brief(9, as_of_shift=14, save=False)
    bid = fresh_ward.store.save_brief(brief)
    src = brief.cards[0].source_id
    table = "episodes" if src.startswith("ep-") else "memories"
    fresh_ward.store.conn.execute(f"DELETE FROM {table} WHERE id=?", (src,))
    fresh_ward.store.conn.commit()
    with pytest.raises(KeyError):
        fresh_ward.feedback(bid, 0, "confirm")
