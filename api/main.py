"""Lamplight API — FastAPI app for Alibaba Function Compute (STATUS: runnable
locally; FC deployment is scaffolded, not performed — see infra/fc/PROOF.md).

Stateless by design: at cold start the worker rebuilds the synthetic ward from
committed fixtures (offline fake transport, sealed at rest), so every endpoint
is a pure function of the frozen fixtures + signed op-chain. In production the
transport swaps to LiveQwen behind DASHSCOPE_API_KEY and the store points at
Supabase/pgvector; the HTTP surface is identical.

    uvicorn api.main:app --reload        # from the build/ directory

Endpoints (ARCHITECTURE.md §API):
    GET  /                        service info + synthetic-data disclaimer
    GET  /healthz                 liveness
    GET  /briefs/{bed}            SBAR handover brief (?shift=&budget=)
    GET  /audit/chain             recent signed memory ops (?limit=)
    GET  /integrations/verify     chain verification + bench summary (judge page)
    POST /feedback                confirm | correct | dismiss a brief card
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from lamplight_memory.engine import LamplightEngine  # noqa: E402
from lamplight_memory.paths import find_fixtures  # noqa: E402
from lamplight_memory.replay import build_ward  # noqa: E402
from lamplight_memory.transport.fake import FakeQwen  # noqa: E402

DISCLAIMER = (
    "SYNTHETIC DATA ONLY — no real patients, no PHI. Lamplight is a research "
    "prototype, not a medical device."
)

app = FastAPI(
    title="Lamplight",
    description="Cross-shift clinical memory agent. " + DISCLAIMER,
    version="0.1.0",
)

_engine: LamplightEngine | None = None
_tmpdir: tempfile.TemporaryDirectory | None = None


def engine() -> LamplightEngine:
    """Lazily build the ward once per worker (stateless cold-start rebuild)."""
    global _engine, _tmpdir
    if _engine is None:
        _tmpdir = tempfile.TemporaryDirectory(prefix="lamplight-api-")
        fixtures_root = find_fixtures(None)
        eng = LamplightEngine(
            Path(_tmpdir.name) / "ward.db",
            FakeQwen(fixtures_root=fixtures_root),
            seal=True,
        )
        build_ward(eng, fixtures_root)
        _engine = eng
    return _engine


class FeedbackIn(BaseModel):
    brief_id: int
    card_ix: int
    action: str  # confirm | correct | dismiss


@app.get("/")
def root() -> dict:
    return {
        "service": "lamplight",
        "version": "0.1.0",
        "track": "MemoryAgent (Track 1)",
        "disclaimer": DISCLAIMER,
        "endpoints": ["/briefs/{bed}", "/audit/chain", "/integrations/verify", "/feedback"],
    }


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.get("/briefs/{bed}")
def get_brief(bed: int, shift: int | None = None, budget: int = 2000) -> dict:
    eng = engine()
    as_of = (shift - 1) if shift is not None else None
    try:
        brief = eng.brief(bed, as_of_shift=as_of, budget=budget, save=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return brief.model_dump()


@app.get("/audit/chain")
def audit_chain(limit: int = 20) -> dict:
    eng = engine()
    return {
        "pubkey": eng.chain.pubkey_hex,
        "length": eng.chain.length(),
        "ops": eng.chain.entries(limit=limit, tail=True),
    }


@app.get("/integrations/verify")
def integrations_verify() -> dict:
    """The judge page: chain verification + the committed bench summary."""
    eng = engine()
    report = eng.verify_chain()
    bench_path = REPO / "bench_results" / "summary.json"
    bench = json.loads(bench_path.read_text()) if bench_path.exists() else None
    return {
        "disclaimer": DISCLAIMER,
        "chain": report.as_dict(),
        "bench": bench,
    }


@app.post("/feedback")
def post_feedback(body: FeedbackIn) -> dict:
    eng = engine()
    try:
        return eng.feedback(body.brief_id, body.card_ix, body.action)
    except (KeyError, IndexError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
