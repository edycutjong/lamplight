"""Alibaba Function Compute 3.0 — MANAGED python runtime entrypoint (EVENT handler).

No container / no ACR: FC installs requirements.txt and invokes this event
`handler(event, context)` for the HTTP trigger (an HTTP trigger delivers the
request as a JSON event and expects {statusCode, headers, body} back — a WSGI
callable would 502 with 'FCContext' not callable). Lamplight targets 3.12 and
uses enum.StrEnum (3.11+); the managed runtime is 3.10, so we shim StrEnum
BEFORE importing the package (StrEnum is just str+Enum — byte-identical).

Endpoints (anonymous HTTP trigger, offline / zero-key / zero-network):
  GET /         service info
  GET /health   liveness -> {"status": "ok"}
  GET /verify   socket-guarded byte-identical replay of the committed ward
                fixtures + Ed25519 op-chain verify (invariants I4 + I5)
  GET /run      one deterministic offline handover brief (FakeQwen, no key)
                ?bed=9&shift=15&budget=2000
"""

from __future__ import annotations

import datetime as _datetime
import enum
import json
import os
import sys

# --- 3.10 compat shims: must run before any lamplight_memory import ----------
# enum.StrEnum (3.11+): str+Enum, byte-identical behaviour.
if not hasattr(enum, "StrEnum"):
    class StrEnum(str, enum.Enum):  # noqa: D401 - drop-in for 3.11 enum.StrEnum
        def __str__(self) -> str:
            return str(self.value)
    enum.StrEnum = StrEnum  # type: ignore[attr-defined]

# datetime.UTC (3.11+): alias of timezone.utc — clock.py does `from datetime import UTC`.
if not hasattr(_datetime, "UTC"):
    _datetime.UTC = _datetime.timezone.utc  # type: ignore[attr-defined]

# The package ships under src/ in the deployed code bundle.
_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(_HERE, "..", "..", "src")
if os.path.isdir(_SRC):
    sys.path.insert(0, os.path.abspath(_SRC))


def _verify() -> dict:
    """Zero-key judge path: install a hard socket guard, rebuild the ward from
    committed fixtures on the offline FakeQwen transport, byte-compare the hero
    brief to the committed expected JSON (I5), and verify the signed op ledger
    (I4). The socket guard is installed only for the replay and then restored."""
    import socket

    from lamplight_memory.paths import find_fixtures
    from lamplight_memory.replay import replay as run_replay

    fixtures = find_fixtures(None)

    def _blocked(*_a, **_k):
        raise RuntimeError(
            "network access attempted during offline verify — "
            "Lamplight's judge path must run with zero sockets"
        )

    _orig_socket = socket.socket
    _orig_conn = getattr(socket, "create_connection", None)
    socket.socket = _blocked  # type: ignore[assignment]
    socket.create_connection = _blocked  # type: ignore[assignment]
    try:
        result = run_replay(fixtures)
    finally:
        socket.socket = _orig_socket  # type: ignore[assignment]
        if _orig_conn is not None:
            socket.create_connection = _orig_conn  # type: ignore[assignment]

    chain = result.chain
    return {
        "overall": "PASS" if result.ok else "FAILED",
        "network": "BLOCKED (socket guard installed for replay)",
        "invariants": {
            "I4_signed_op_chain": chain.ok,
            "I5_byte_identical_replay": result.byte_identical,
        },
        "byte_identical": result.byte_identical,
        "expected": result.expected_path.name,
        "chain": {
            "ok": chain.ok,
            "signed_ops": chain.length,
            "pubkey": chain.pubkey[:16] + "...",
            "ops_by_type": chain.ops_by_type,
        },
        "detail": result.detail,
        "source": "offline FakeQwen replay of committed ward fixtures "
                  "(zero key, zero network)",
    }


def _run(bed: int, shift: int, budget: int) -> dict:
    """Deterministic offline handover demo (the `lamplight demo` equivalent):
    ingest all 15 fixture shifts into a throwaway ward, then build the SBAR
    brief for one bed — cited, budgeted, with resolved items visibly retired."""
    import tempfile

    from lamplight_memory.brief import DEFAULT_BUDGET
    from lamplight_memory.engine import LamplightEngine
    from lamplight_memory.paths import find_fixtures
    from lamplight_memory.replay import build_ward
    from lamplight_memory.transport import get_transport

    if budget <= 0:
        budget = DEFAULT_BUDGET
    fixtures = find_fixtures(None)
    with tempfile.TemporaryDirectory(prefix="lamplight-run-") as tmp:
        db_path = os.path.join(tmp, "run.db")
        engine = LamplightEngine(
            db_path, get_transport("fake", fixtures_root=fixtures), seal=True
        )
        try:
            build_ward(engine, fixtures)  # ingest all 15 shifts + nightly lifecycle
            b = engine.brief(bed, as_of_shift=shift - 1, budget=budget, save=False)
            chain = engine.verify_chain()
        finally:
            engine.close()

    return {
        "transport": "FakeQwen (offline deterministic — no key required)",
        "bed": b.bed,
        "for_shift": b.for_shift,
        "as_of_shift": b.as_of_shift,
        "engine": b.engine,
        "budget": b.budget,
        "token_count": b.token_count,
        "signed_ops": chain.length,
        "cards": [
            {
                "priority": c.priority,
                "sbar": c.sbar,
                "why_tonight": c.why_tonight,
                "citations": c.citations,
                "needs_confirmation": c.needs_confirmation,
            }
            for c in b.cards
        ],
        "retired": [
            {"label": r.label, "reason": r.reason, "at_shift": r.at_shift,
             "citation": r.citation}
            for r in b.retired
        ],
        "routine_expired_count": b.routine_expired_count,
    }


def _route(path: str, qs: dict) -> tuple[int, dict]:
    path = path.rstrip("/") or "/"
    if path == "/":
        return 200, {
            "service": "lamplight — cross-shift handover memory engine (Qwen Cloud)",
            "note": "SYNTHETIC DATA ONLY. No real patients, no PHI.",
            "endpoints": {
                "/health": "liveness",
                "/verify": "socket-guarded byte-identical replay + signed op-chain verify (I4/I5)",
                "/run": "one deterministic offline handover brief (?bed=&shift=&budget=)",
            },
            "repo": "https://github.com/edycutjong/lamplight",
        }
    if path == "/health":
        return 200, {"status": "ok"}
    if path == "/verify":
        return 200, _verify()
    if path == "/run":
        return 200, _run(
            int(qs.get("bed", ["9"])[0]),
            int(qs.get("shift", ["15"])[0]),
            int(qs.get("budget", ["2000"])[0]),
        )
    return 404, {"error": f"no route {path}"}


def handler(event, context):
    """FC 3.0 event handler for an HTTP trigger.

    `event` is the HTTP request as JSON bytes; return {statusCode, headers, body}.
    """
    from urllib.parse import parse_qs
    try:
        req = json.loads(event) if isinstance(event, (bytes, bytearray, str)) else (event or {})
    except Exception:
        req = {}
    rc_http = (req.get("requestContext") or {}).get("http") or {}
    path = req.get("rawPath") or req.get("path") or rc_http.get("path") or "/"
    # queryParameters may be a flat dict, or fall back to parsing rawQueryString
    qp = req.get("queryParameters") or req.get("queryStringParameters")
    if qp:
        qs = {k: (v if isinstance(v, list) else [v]) for k, v in qp.items()}
    else:
        qs = parse_qs(req.get("rawQueryString", "") or "")
    try:
        code, payload = _route(path, qs)
    except Exception as exc:  # never 500 opaque
        code, payload = 500, {"error": type(exc).__name__, "detail": str(exc)[:400]}
    return {
        "statusCode": code,
        "headers": {"Content-Type": "application/json"},
        "isBase64Encoded": False,
        "body": json.dumps(payload, sort_keys=True, indent=2),
    }
