"""Fixture replay — the zero-key judge path and its committed hero brief."""

from __future__ import annotations

import json

from lamplight_memory.replay import (
    HERO_BED,
    HERO_BRIEF_SHIFT,
    expected_brief_path,
    replay,
)


def test_replay_passes(fixtures_root):
    r = replay(fixtures_root)
    assert r.ok is True
    assert r.byte_identical is True
    assert r.chain.ok is True
    assert r.chain.length > 100


def test_hero_constants():
    assert HERO_BED == 9
    assert HERO_BRIEF_SHIFT == 15


def test_expected_brief_committed(fixtures_root):
    path = expected_brief_path(fixtures_root)
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["bed"] == 9
    assert data["as_of_shift"] == 14
    assert data["for_shift"] == 15


def test_hero_brief_leads_with_cefazolin(fixtures_root):
    data = json.loads(expected_brief_path(fixtures_root).read_text())
    top = data["cards"][0]
    assert top["source_id"] == "mem-09-cefazolin-s12"
    assert set(top["citations"]) == {"ep-09-04-1", "ep-09-06-1", "ep-09-12-1"}


def test_hero_brief_retires_iv(fixtures_root):
    data = json.loads(expected_brief_path(fixtures_root).read_text())
    retired = {r["id"]: r for r in data["retired"]}
    assert "ep-09-01-2" in retired
    assert retired["ep-09-01-2"]["reason"] == "resolved"


def test_hero_brief_within_budget(fixtures_root):
    data = json.loads(expected_brief_path(fixtures_root).read_text())
    assert data["token_count"] <= data["budget"] == 2000


def test_replay_detail_string(fixtures_root):
    r = replay(fixtures_root)
    assert "byte-identical" in r.detail
    assert "chain ok" in r.detail


# --------------------------------------------------------------------------- #
# maintainer path (--write-expected) + missing-committed-expected fallback
#
# Both mutate/inspect the fixtures directory's "expected/" folder, so each
# runs against its own throwaway copy of fixtures_root — the real committed
# fixtures/ward_5day/expected/*.json is never touched.
# --------------------------------------------------------------------------- #


def test_write_expected_freezes_current_output(tmp_path, fixtures_root):
    import shutil

    copy_root = tmp_path / "fixtures_copy"
    shutil.copytree(fixtures_root, copy_root)
    target = expected_brief_path(copy_root)
    assert target.exists()  # committed copy already has one
    target.unlink()  # simulate "first ever run" for this fixtures copy

    r = replay(copy_root, write_expected=True)
    assert r.byte_identical is True
    assert r.expected_path == target
    assert target.exists()
    assert "expected brief written" in r.detail
    assert f"{len(r.brief_bytes)} bytes" in r.detail

    # and a normal (non-write) replay against the just-frozen file now passes
    r2 = replay(copy_root)
    assert r2.ok is True
    assert r2.byte_identical is True


def test_replay_without_committed_expected_reports_missing(tmp_path, fixtures_root):
    import shutil

    copy_root = tmp_path / "fixtures_copy_no_expected"
    shutil.copytree(fixtures_root, copy_root)
    expected_brief_path(copy_root).unlink()

    r = replay(copy_root)
    assert r.ok is False
    assert r.byte_identical is False
    assert "no committed expected brief" in r.detail
