"""Small shared utilities: canonical JSON and hashing.

Canonical JSON is the backbone of every determinism guarantee in Lamplight
(invariant I5: replayed fixtures produce byte-identical briefs; I4: the op
chain hashes are reproducible). One serializer, used everywhere.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

__all__ = ["canonical_json", "sha256_hex", "short_hash"]


def canonical_json(obj: Any) -> str:
    """Serialize *obj* to a canonical JSON string.

    Sorted keys, minimal separators, ASCII-only. Byte-identical for equal
    inputs across processes and platforms.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_hex(data: bytes | str) -> str:
    """SHA-256 hex digest of *data* (str is UTF-8 encoded first)."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def short_hash(data: bytes | str, n: int = 12) -> str:
    """Truncated SHA-256 hex digest — for human-facing IDs only."""
    return sha256_hex(data)[:n]
