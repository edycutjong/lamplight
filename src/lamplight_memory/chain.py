"""Signed memory-op ledger (COMPLEXITY.md §2) + ChainAudit.

Every memory operation — write / consolidate / decay / contradict / pin /
expire — appends a hash-chained, Ed25519-signed entry:

    entry   = {seq, ts, op, payload_hash, prev_hash}
    sig     = Ed25519.sign(canonical_json(entry))
    payload_hash = sha256(canonical_json(payload))

so "the system forgot X at time T per policy P" is a signed fact. The chain
commits to payload *hashes*; for episode writes the payload carries the
episode's text SHA-256 rather than the text itself, so the ledger can be
published without leaking sealed content.

Determinism: Ed25519 signatures are deterministic (RFC 8032) and timestamps
come from the ward clock, so a replay regenerates a byte-identical chain.

Key handling: a committed *demo* key (derived from a public seed) keeps the
judge path zero-config. Production sets LAMPLIGHT_SIGNING_SEED_HEX (e.g. in
Function Compute env) and commits only the public key.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey

from .schemas import OpType
from .util import canonical_json, sha256_hex

__all__ = ["OpChain", "ChainAudit", "ChainReport", "demo_signing_key", "GENESIS_HASH"]

GENESIS_HASH = "0" * 64
_DEMO_SEED_LABEL = b"lamplight demo signing key v1"


def demo_signing_key() -> SigningKey:
    """Deterministic DEMO signing key (public seed — integrity demo only).

    Anyone can re-derive this key; it proves *tamper-evidence*, not identity.
    Set LAMPLIGHT_SIGNING_SEED_HEX for a real deployment key.
    """
    return SigningKey(hashlib.sha256(_DEMO_SEED_LABEL).digest())


def _resolve_signing_key(explicit: SigningKey | None) -> SigningKey:
    if explicit is not None:
        return explicit
    env = os.environ.get("LAMPLIGHT_SIGNING_SEED_HEX")
    if env:
        return SigningKey(bytes.fromhex(env))
    return demo_signing_key()


_CHAIN_SCHEMA = """
CREATE TABLE IF NOT EXISTS op_chain (
    seq INTEGER PRIMARY KEY,
    ts TEXT NOT NULL,
    op TEXT NOT NULL,
    payload TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    sig TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chain_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


@dataclass
class ChainReport:
    ok: bool
    length: int
    pubkey: str
    error: str | None = None
    bad_seq: int | None = None
    ops_by_type: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "length": self.length,
            "pubkey": self.pubkey,
            "error": self.error,
            "bad_seq": self.bad_seq,
            "ops_by_type": self.ops_by_type,
        }


class OpChain:
    """Append-only signed op ledger stored alongside the memory tables."""

    def __init__(self, db_path: str | Path, signing_key: SigningKey | None = None):
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_CHAIN_SCHEMA)
        self.signing_key = _resolve_signing_key(signing_key)
        pub = self.signing_key.verify_key.encode().hex()
        row = self.conn.execute(
            "SELECT value FROM chain_meta WHERE key='pubkey'"
        ).fetchone()
        if row is None:
            self.conn.execute(
                "INSERT INTO chain_meta (key, value) VALUES ('pubkey', ?)", (pub,)
            )
            self.conn.commit()
        elif row["value"] != pub:
            raise ValueError(
                "signing key does not match the chain's recorded public key"
            )
        self.pubkey_hex = pub

    def close(self) -> None:
        self.conn.close()

    # ------------------------------------------------------------------ #

    def _entry_message(self, entry: dict[str, Any]) -> bytes:
        return canonical_json(
            {k: entry[k] for k in ("seq", "ts", "op", "payload_hash", "prev_hash")}
        ).encode("utf-8")

    def append(self, op: OpType | str, payload: dict[str, Any], ts: str) -> dict[str, Any]:
        op = OpType(op)
        row = self.conn.execute(
            "SELECT seq, payload_hash, prev_hash, ts, op, sig FROM op_chain "
            "ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        if row is None:
            seq, prev_hash = 1, GENESIS_HASH
        else:
            seq = int(row["seq"]) + 1
            prev_hash = sha256_hex(
                canonical_json(
                    {
                        "seq": int(row["seq"]),
                        "ts": row["ts"],
                        "op": row["op"],
                        "payload_hash": row["payload_hash"],
                        "prev_hash": row["prev_hash"],
                        "sig": row["sig"],
                    }
                )
            )
        payload_json = canonical_json(payload)
        entry = {
            "seq": seq,
            "ts": ts,
            "op": op.value,
            "payload_hash": sha256_hex(payload_json),
            "prev_hash": prev_hash,
        }
        sig = self.signing_key.sign(self._entry_message(entry)).signature.hex()
        entry["sig"] = sig
        self.conn.execute(
            "INSERT INTO op_chain (seq, ts, op, payload, payload_hash, prev_hash, sig) "
            "VALUES (?,?,?,?,?,?,?)",
            (seq, ts, op.value, payload_json, entry["payload_hash"], prev_hash, sig),
        )
        self.conn.commit()
        return entry

    def entries(self, limit: int | None = None, tail: bool = False) -> list[dict[str, Any]]:
        q = "SELECT * FROM op_chain ORDER BY seq" + (" DESC" if tail else "")
        if limit:
            q += f" LIMIT {int(limit)}"
        rows = [dict(r) for r in self.conn.execute(q).fetchall()]
        if tail:
            rows.reverse()
        return rows

    def length(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) AS n FROM op_chain").fetchone()
        return int(row["n"])


class ChainAudit:
    """Verifies the full ledger: hash linkage, signatures, sequence
    contiguity, and payload integrity (invariant I4 — a 1-byte tamper fails)."""

    def __init__(self, db_path: str | Path, verify_key_hex: str | None = None):
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self._explicit_pubkey = verify_key_hex

    def close(self) -> None:
        self.conn.close()

    def verify(self) -> ChainReport:
        meta = self.conn.execute(
            "SELECT value FROM chain_meta WHERE key='pubkey'"
        ).fetchone()
        pubkey_hex = self._explicit_pubkey or (meta["value"] if meta else "")
        if not pubkey_hex:
            return ChainReport(ok=False, length=0, pubkey="", error="no public key recorded")
        verify_key = VerifyKey(bytes.fromhex(pubkey_hex))

        rows = self.conn.execute("SELECT * FROM op_chain ORDER BY seq").fetchall()
        ops_by_type: dict[str, int] = {}
        prev_hash = GENESIS_HASH
        expected_seq = 1
        for row in rows:
            seq = int(row["seq"])
            if seq != expected_seq:
                return ChainReport(
                    ok=False, length=len(rows), pubkey=pubkey_hex,
                    error=f"sequence gap: expected {expected_seq}, found {seq}",
                    bad_seq=seq, ops_by_type=ops_by_type,
                )
            # payload integrity
            if sha256_hex(row["payload"]) != row["payload_hash"]:
                return ChainReport(
                    ok=False, length=len(rows), pubkey=pubkey_hex,
                    error="payload hash mismatch", bad_seq=seq, ops_by_type=ops_by_type,
                )
            # linkage
            if row["prev_hash"] != prev_hash:
                return ChainReport(
                    ok=False, length=len(rows), pubkey=pubkey_hex,
                    error="broken hash link", bad_seq=seq, ops_by_type=ops_by_type,
                )
            # signature
            entry = {
                "seq": seq,
                "ts": row["ts"],
                "op": row["op"],
                "payload_hash": row["payload_hash"],
                "prev_hash": row["prev_hash"],
            }
            msg = canonical_json(entry).encode("utf-8")
            try:
                verify_key.verify(msg, bytes.fromhex(row["sig"]))
            except (BadSignatureError, ValueError):
                return ChainReport(
                    ok=False, length=len(rows), pubkey=pubkey_hex,
                    error="bad signature", bad_seq=seq, ops_by_type=ops_by_type,
                )
            ops_by_type[row["op"]] = ops_by_type.get(row["op"], 0) + 1
            entry["sig"] = row["sig"]
            prev_hash = sha256_hex(canonical_json(entry))
            expected_seq += 1

        # sanity: payload column must be valid JSON everywhere
        for row in rows:
            try:
                json.loads(row["payload"])
            except json.JSONDecodeError:
                return ChainReport(
                    ok=False, length=len(rows), pubkey=pubkey_hex,
                    error="payload not JSON", bad_seq=int(row["seq"]),
                    ops_by_type=ops_by_type,
                )
        return ChainReport(ok=True, length=len(rows), pubkey=pubkey_hex, ops_by_type=ops_by_type)
