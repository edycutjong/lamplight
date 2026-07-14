"""Sealer — ECIES payload sealing (episode text encrypted at rest)."""

from __future__ import annotations

from nacl.public import PrivateKey

from lamplight_memory.sealed import Sealer, demo_private_key


def test_roundtrip():
    s = Sealer()
    blob = s.seal("rash began 4h after cefazolin")
    assert s.unseal(blob) == "rash began 4h after cefazolin"


def test_ciphertext_is_bytes_and_not_plaintext():
    s = Sealer()
    blob = s.seal("penicillin allergy")
    assert isinstance(blob, bytes)
    assert b"penicillin" not in blob


def test_ciphertext_nondeterministic():
    s = Sealer()
    a = s.seal("same text")
    b = s.seal("same text")
    assert a != b  # ephemeral keys -> different ciphertext
    assert s.unseal(a) == s.unseal(b) == "same text"


def test_demo_key_is_deterministic():
    assert demo_private_key().encode() == demo_private_key().encode()


def test_demo_public_key_hex_stable():
    assert Sealer().public_key_hex == Sealer().public_key_hex


def test_explicit_key_roundtrip():
    key = PrivateKey.generate()
    s = Sealer(key)
    blob = s.seal("unsteady to the bathroom")
    assert s.unseal(blob) == "unsteady to the bathroom"


def test_env_override(monkeypatch):
    key = PrivateKey.generate()
    monkeypatch.setenv("LAMPLIGHT_SEAL_SEED_HEX", key.encode().hex())
    s = Sealer()
    assert s.public_key_hex == key.public_key.encode().hex()


def test_unicode_roundtrip():
    s = Sealer()
    txt = "IV site concern — resolved (strikethrough)"
    assert s.unseal(s.seal(txt)) == txt
