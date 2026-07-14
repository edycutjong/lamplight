"""ECIES payload sealing (COMPLEXITY.md §2): episode text encrypted at rest.

PyNaCl SealedBox = ephemeral X25519 + XSalsa20-Poly1305 (an ECIES scheme):
anyone with the public key can seal; only the private key opens. The store
keeps embeddings and metadata queryable while the prose itself is ciphertext;
plaintext is materialized only inside the worker at brief-build time.

Ciphertext is intentionally non-deterministic (ephemeral keys). Determinism
guarantees (I5) apply to *decrypted* content and briefs, never to blobs.

Key handling mirrors chain.py: committed demo seed for the zero-key judge
path; LAMPLIGHT_SEAL_SEED_HEX overrides for real deployments. [stretch]
cryptographic deletion (per-episode envelope keys destroyed on expiry) is
documented in docs/SPEC-MEMORY.md and not implemented in this timebox.
"""

from __future__ import annotations

import hashlib
import os

from nacl.public import PrivateKey, PublicKey, SealedBox

__all__ = ["Sealer", "demo_private_key"]

_DEMO_SEED_LABEL = b"lamplight demo sealing key v1"


def demo_private_key() -> PrivateKey:
    """Deterministic DEMO sealing key (public seed — see module docstring)."""
    return PrivateKey(hashlib.sha256(_DEMO_SEED_LABEL).digest())


class Sealer:
    """Seal/unseal episode payloads. Constructed once per engine."""

    def __init__(self, private_key: PrivateKey | None = None):
        if private_key is None:
            env = os.environ.get("LAMPLIGHT_SEAL_SEED_HEX")
            private_key = (
                PrivateKey(bytes.fromhex(env)) if env else demo_private_key()
            )
        self._private = private_key
        self._public: PublicKey = private_key.public_key
        self._seal_box = SealedBox(self._public)
        self._open_box = SealedBox(self._private)

    @property
    def public_key_hex(self) -> str:
        return self._public.encode().hex()

    def seal(self, text: str) -> bytes:
        return self._seal_box.encrypt(text.encode("utf-8"))

    def unseal(self, blob: bytes) -> str:
        return self._open_box.decrypt(blob).decode("utf-8")
