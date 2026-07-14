"""Shared pytest fixtures and helpers for the Lamplight test suite.

Everything here runs on the deterministic offline FakeQwen transport — no
network, no DASHSCOPE_API_KEY, no sockets. The full ward is built once per
session (15 shifts x 6 beds) and shared by the read-only brief/invariant
tests; mutation tests build their own throwaway ward.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lamplight_memory.clock import iso, shift_start  # noqa: E402
from lamplight_memory.engine import LamplightEngine  # noqa: E402
from lamplight_memory.paths import find_fixtures  # noqa: E402
from lamplight_memory.replay import build_ward  # noqa: E402
from lamplight_memory.schemas import Episode  # noqa: E402
from lamplight_memory.store import MemoryStore  # noqa: E402
from lamplight_memory.transport.fake import FakeQwen  # noqa: E402


@pytest.fixture(scope="session")
def fixtures_root() -> Path:
    return find_fixtures(None)


@pytest.fixture(scope="session")
def ward_engine(fixtures_root, tmp_path_factory):
    """A fully-ingested 15-shift ward on the fake transport (sealed at rest).

    Session-scoped for speed; read-only consumers only (briefs with save=False,
    chain verification). Never mutate the store through this fixture.
    """
    db = tmp_path_factory.mktemp("ward") / "ward.db"
    engine = LamplightEngine(db, FakeQwen(fixtures_root=fixtures_root), seal=True)
    build_ward(engine, fixtures_root)
    yield engine
    engine.close()


@pytest.fixture
def fresh_ward(fixtures_root, tmp_path):
    """A throwaway fully-ingested ward for tests that mutate (feedback/pin)."""
    db = tmp_path / "fresh.db"
    engine = LamplightEngine(db, FakeQwen(fixtures_root=fixtures_root), seal=True)
    build_ward(engine, fixtures_root)
    yield engine
    engine.close()


@pytest.fixture
def fake() -> FakeQwen:
    """A FakeQwen with no fixtures — embeddings/rerank only (unit tests)."""
    return FakeQwen(extraction_map={})


@pytest.fixture
def empty_store(tmp_path) -> MemoryStore:
    store = MemoryStore(tmp_path / "unit.db")
    yield store
    store.close()


# --------------------------------------------------------------------------- #
# small builders
# --------------------------------------------------------------------------- #


def ep_dict(
    bed: int,
    shift: int,
    k: int,
    text: str,
    entities: list[str],
    *,
    decay_class: str = "routine",
    type: str = "observation",
    polarity: str = "neutral",
    resolves: str | None = None,
    why_hint: str | None = None,
    ts: str | None = None,
) -> dict:
    """Build a raw episode dict (validates against Episode)."""
    return {
        "id": f"ep-{bed:02d}-{shift:02d}-{k}",
        "bed": bed,
        "shift": shift,
        "ts": ts or iso(shift_start(shift)),
        "type": type,
        "text": text,
        "entities": entities,
        "polarity": polarity,
        "decay_class": decay_class,
        "resolves": resolves,
        "why_hint": why_hint,
    }


def add_ep(store: MemoryStore, fake: FakeQwen, d: dict) -> Episode:
    """Insert an episode dict into a store (unsealed plaintext)."""
    ep = Episode.model_validate(d)
    vec = fake.embed([ep.text])[0]
    store.add_episode(ep, vec, ep.text, None)
    return ep


def text_of_plain(store: MemoryStore):
    """text_of resolver for an unsealed store (plaintext column present)."""

    def _resolve(item_id: str) -> str:
        got = store.get_row(item_id)
        if got is None:
            raise KeyError(item_id)
        return got[1]["text"]

    return _resolve
