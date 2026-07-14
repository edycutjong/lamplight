"""Invariants I1-I5 (COMPLEXITY.md §2), asserted end-to-end on the real ward.

    I1  every brief item cites >= 1 existing, ACTIVE episode ID
    I2  zero resolved/expired items in any brief (forgetting precision = 1.0)
    I3  brief <= 2,000 tokens, hard-asserted
    I4  op-chain verifies; any 1-byte tamper fails
    I5  replayed fixture -> byte-identical briefs
"""

from __future__ import annotations

import sqlite3

from lamplight_memory.engine import LamplightEngine
from lamplight_memory.replay import (
    HERO_BED,
    HERO_BRIEF_SHIFT,
    build_ward,
    expected_brief_path,
    replay,
)
from lamplight_memory.schemas import Status
from lamplight_memory.transport.fake import FakeQwen
from lamplight_memory.util import canonical_json

BEDS = [3, 5, 7, 9, 11, 12]
AS_OF = range(2, 15)  # briefs for incoming shifts 3..15

# every episode the ground truth says must be forgotten from shift 3 on
RETIRED_FOREVER = {"ep-09-01-2", "ep-09-02-1"}


def all_briefs(engine):
    for bed in BEDS:
        for as_of in AS_OF:
            yield bed, as_of, engine.brief(bed, as_of_shift=as_of, save=False)


# --------------------------------------------------------------------------- #
# I1 — every card cites an existing, active episode
# --------------------------------------------------------------------------- #


def test_I1_every_card_cites_existing_active(ward_engine):
    checked = 0
    for bed, as_of, brief in all_briefs(ward_engine):
        for card in brief.cards:
            assert card.citations, f"uncited card bed{bed} s{as_of}"
            for cid in card.citations:
                assert ward_engine.store.exists(cid), f"{cid} does not exist"
                status = ward_engine.store.status_at(cid, as_of)
                assert status in (Status.ACTIVE, Status.PINNED), (
                    f"bed{bed} s{as_of} cites {cid} with status {status}"
                )
                checked += 1
    assert checked > 0


# --------------------------------------------------------------------------- #
# I2 — zero resolved/expired items in any brief (forgetting precision 1.0)
# --------------------------------------------------------------------------- #


def test_I2_no_resolved_or_expired_cited(ward_engine):
    for _bed, as_of, brief in all_briefs(ward_engine):
        for card in brief.cards:
            for cid in card.citations:
                status = ward_engine.store.status_at(cid, as_of)
                assert status not in (Status.RESOLVED, Status.EXPIRED)


def test_I2_iv_red_herring_never_surfaces(ward_engine):
    for bed, as_of, brief in all_briefs(ward_engine):
        cited = {c for card in brief.cards for c in card.citations}
        assert not (cited & RETIRED_FOREVER), (
            f"retired IV episode surfaced in bed{bed} s{as_of}"
        )


def test_I2_forgetting_precision_is_one(ward_engine):
    violations = 0
    total = 0
    for _, as_of, brief in all_briefs(ward_engine):
        for card in brief.cards:
            for cid in card.citations:
                total += 1
                st = ward_engine.store.status_at(cid, as_of)
                if st in (Status.RESOLVED, Status.EXPIRED):
                    violations += 1
    precision = 1.0 - violations / total
    assert precision == 1.0


# --------------------------------------------------------------------------- #
# I3 — every brief within the hard 2,000-token budget
# --------------------------------------------------------------------------- #


def test_I3_all_briefs_within_budget(ward_engine):
    for bed, as_of, brief in all_briefs(ward_engine):
        assert brief.token_count <= 2000, f"bed{bed} s{as_of} over budget"


def test_I3_holds_under_stress_budget(ward_engine):
    for bed in BEDS:
        b = ward_engine.brief(bed, as_of_shift=14, budget=300, save=False)
        assert b.token_count <= 300


# --------------------------------------------------------------------------- #
# I4 — op-chain verifies; a 1-byte tamper fails
# --------------------------------------------------------------------------- #


def test_I4_chain_verifies(fresh_ward):
    assert fresh_ward.verify_chain().ok is True


def test_I4_one_byte_tamper_fails(fresh_ward):
    # flip a single character in an arbitrary payload row
    con = sqlite3.connect(fresh_ward.db_path)
    seq, payload = con.execute(
        "SELECT seq, payload FROM op_chain ORDER BY seq LIMIT 1"
    ).fetchone()
    tampered = ("Z" + payload[1:]) if payload[0] != "Z" else ("Y" + payload[1:])
    con.execute("UPDATE op_chain SET payload=? WHERE seq=?", (tampered, seq))
    con.commit()
    con.close()
    report = fresh_ward.verify_chain()
    assert report.ok is False
    assert report.bad_seq == seq


# --------------------------------------------------------------------------- #
# I5 — replayed fixture -> byte-identical briefs
# --------------------------------------------------------------------------- #


def _hero_brief_bytes(fixtures_root, db_path):
    engine = LamplightEngine(db_path, FakeQwen(fixtures_root=fixtures_root), seal=True)
    try:
        build_ward(engine, fixtures_root)
        brief = engine.brief(HERO_BED, as_of_shift=HERO_BRIEF_SHIFT - 1, save=False)
        return (canonical_json(brief.model_dump()) + "\n").encode("utf-8")
    finally:
        engine.close()


def test_I5_two_independent_builds_identical(fixtures_root, tmp_path):
    a = _hero_brief_bytes(fixtures_root, tmp_path / "a.db")
    b = _hero_brief_bytes(fixtures_root, tmp_path / "b.db")
    assert a == b


def test_I5_matches_committed_expected(fixtures_root, tmp_path):
    exp = expected_brief_path(fixtures_root)
    assert exp.exists(), "committed expected brief missing (run `lamplight replay --write-expected`)"
    built = _hero_brief_bytes(fixtures_root, tmp_path / "c.db")
    assert built == exp.read_bytes()


def test_I5_replay_helper_passes(fixtures_root):
    result = replay(fixtures_root)
    assert result.ok is True
    assert result.byte_identical is True
    assert result.chain.ok is True


def test_I5_replay_is_repeatable(fixtures_root):
    r1 = replay(fixtures_root)
    r2 = replay(fixtures_root)
    assert r1.brief_bytes == r2.brief_bytes
    assert r1.chain.length == r2.chain.length
