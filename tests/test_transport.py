"""Transport plumbing: FakeQwen edge cases, the Transport ABC default, and
get_transport() dispatch — all offline, zero DASHSCOPE_API_KEY."""

from __future__ import annotations

import pytest

from lamplight_memory.schemas import Episode
from lamplight_memory.transport import Transport, get_transport
from lamplight_memory.transport.fake import FakeQwen

# --------------------------------------------------------------------------- #
# FakeQwen.rerank — empty query/document token sets score 0.0
# --------------------------------------------------------------------------- #


def test_rerank_empty_query_scores_zero():
    tr = FakeQwen(extraction_map={})
    scores = tr.rerank("", ["some real document text"])
    assert scores == [0.0]


def test_rerank_empty_document_scores_zero():
    tr = FakeQwen(extraction_map={})
    scores = tr.rerank("falls risk", ["   ", "falls risk unsteady to bathroom"])
    assert scores[0] == 0.0
    assert scores[1] > 0.0


# --------------------------------------------------------------------------- #
# FakeQwen.extract — extraction_map branch (inline unit-test transport)
# --------------------------------------------------------------------------- #


def test_extract_inline_map_success():
    ep = {
        "id": "ep-09-01-1", "bed": 9, "shift": 1, "ts": "2026-01-01T00:00:00Z",
        "type": "observation", "text": "hello", "entities": ["x"],
        "polarity": "neutral", "decay_class": "routine",
        "resolves": None, "why_hint": None,
    }
    tr = FakeQwen(extraction_map={(9, 1): [ep]})
    out = tr.extract("note text irrelevant for inline map", bed=9, shift=1)
    assert len(out) == 1
    assert isinstance(out[0], Episode)
    assert out[0].id == "ep-09-01-1"


def test_extract_inline_map_missing_key_raises():
    tr = FakeQwen(extraction_map={})
    with pytest.raises(KeyError):
        tr.extract("note", bed=9, shift=1)


def test_extract_no_fixtures_and_no_map_raises():
    tr = FakeQwen()
    with pytest.raises(RuntimeError):
        tr.extract("note", bed=9, shift=1)


def test_extract_missing_fixture_file_raises(fixtures_root):
    tr = FakeQwen(fixtures_root=fixtures_root)
    with pytest.raises(FileNotFoundError):
        tr.extract("note text", bed=99, shift=99)


def test_extract_fixture_drift_raises(fixtures_root):
    tr = FakeQwen(fixtures_root=fixtures_root)
    with pytest.raises(ValueError):
        # a real fixture exists for (9, 6) but the note text here does not
        # match the committed note's SHA-256 -> drift detected
        tr.extract("this note text was never seeded", bed=9, shift=6)


# --------------------------------------------------------------------------- #
# Transport ABC — default transcribe() is unimplemented for offline transports
# --------------------------------------------------------------------------- #


def test_base_transport_transcribe_not_implemented():
    tr = FakeQwen(extraction_map={})
    with pytest.raises(NotImplementedError):
        tr.transcribe("audio.wav")


def test_base_transport_brief_prose_defaults_none():
    tr = FakeQwen(extraction_map={})
    assert tr.brief_prose({"facts": "x"}) is None


# --------------------------------------------------------------------------- #
# get_transport() dispatch
# --------------------------------------------------------------------------- #


def test_get_transport_fake(fixtures_root):
    tr = get_transport("fake", fixtures_root=fixtures_root)
    assert isinstance(tr, FakeQwen)
    assert tr.name == "fake"


def test_get_transport_unknown_raises():
    with pytest.raises(ValueError):
        get_transport("carrier-pigeon")


def test_get_transport_live_constructs_without_network(monkeypatch):
    # LiveQwen's __init__ never touches the network (the OpenAI client is
    # lazy) — a fake key is enough to prove the dispatch wiring is correct.
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key-not-real")
    tr = get_transport("live")
    assert tr.name == "live"
    assert isinstance(tr, Transport)
