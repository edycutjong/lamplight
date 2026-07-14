"""Deterministic fixture replay (invariant I5) — the zero-key judge path.

Rebuilds the entire ward from committed fixtures in a throwaway database
(fake transport, sealing ON), regenerates the hero brief — Bed 9 at shift 15
(memory state after shift 14 closed) — and byte-compares it against the
committed expected JSON. Also verifies the op chain end-to-end.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from .chain import ChainReport
from .engine import LamplightEngine
from .transport.fake import FakeQwen
from .util import canonical_json

__all__ = ["replay", "ReplayResult", "HERO_BED", "HERO_BRIEF_SHIFT", "expected_brief_path"]

HERO_BED = 9
HERO_BRIEF_SHIFT = 15  # the incoming shift; memory state as of close of 14
N_SHIFTS = 15


def expected_brief_path(fixtures_root: Path) -> Path:
    return (
        fixtures_root
        / "expected"
        / f"brief_bed{HERO_BED}_shift{HERO_BRIEF_SHIFT}.json"
    )


@dataclass
class ReplayResult:
    ok: bool
    byte_identical: bool
    chain: ChainReport
    brief_bytes: bytes
    expected_path: Path
    detail: str


def build_ward(engine: LamplightEngine, fixtures_root: Path, n_shifts: int = N_SHIFTS) -> None:
    """Ingest every fixture shift into *engine* (shared by bench + replay)."""
    for shift in range(1, n_shifts + 1):
        notes_dir = fixtures_root / "notes" / f"shift_{shift:02d}"
        engine.ingest_shift(shift, notes_dir)


def replay(
    fixtures_root: Path,
    write_expected: bool = False,
    keep_db: str | Path | None = None,
) -> ReplayResult:
    exp_path = expected_brief_path(fixtures_root)
    with tempfile.TemporaryDirectory(prefix="lamplight-replay-") as tmp:
        db_path = Path(keep_db) if keep_db else Path(tmp) / "replay.db"
        engine = LamplightEngine(
            db_path, FakeQwen(fixtures_root=fixtures_root), seal=True
        )
        try:
            build_ward(engine, fixtures_root)
            brief = engine.brief(
                HERO_BED, as_of_shift=HERO_BRIEF_SHIFT - 1, save=False
            )
            brief_bytes = (canonical_json(brief.model_dump()) + "\n").encode("utf-8")
            chain = engine.verify_chain()
        finally:
            engine.close()

    if write_expected:
        exp_path.parent.mkdir(parents=True, exist_ok=True)
        exp_path.write_bytes(brief_bytes)
        return ReplayResult(
            ok=chain.ok,
            byte_identical=True,
            chain=chain,
            brief_bytes=brief_bytes,
            expected_path=exp_path,
            detail=f"expected brief written ({len(brief_bytes)} bytes)",
        )

    if not exp_path.exists():
        return ReplayResult(
            ok=False, byte_identical=False, chain=chain, brief_bytes=brief_bytes,
            expected_path=exp_path,
            detail="no committed expected brief — run replay --write-expected once",
        )
    expected = exp_path.read_bytes()
    identical = expected == brief_bytes
    ok = identical and chain.ok
    detail = (
        f"brief byte-identical ({len(brief_bytes)} bytes); chain ok "
        f"({chain.length} signed ops)"
        if ok
        else (
            ("brief DIFFERS from committed expected; " if not identical else "")
            + ("chain verification FAILED" if not chain.ok else "")
        )
    )
    return ReplayResult(
        ok=ok, byte_identical=identical, chain=chain,
        brief_bytes=brief_bytes, expected_path=exp_path, detail=detail,
    )
