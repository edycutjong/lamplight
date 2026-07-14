"""canonical_json + hashing — the backbone of every determinism guarantee."""

from __future__ import annotations

from lamplight_memory.util import canonical_json, sha256_hex, short_hash


def test_canonical_sorts_keys():
    assert canonical_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'


def test_canonical_minimal_separators():
    assert canonical_json([1, 2, 3]) == "[1,2,3]"
    assert canonical_json({"a": 1, "b": 2}) == '{"a":1,"b":2}'


def test_canonical_ascii_only():
    # em-dash escaped, not raw UTF-8
    out = canonical_json({"x": "IV — resolved"})
    assert "\\u2014" in out
    assert out.isascii()


def test_canonical_stable_across_input_order():
    a = canonical_json({"seq": 1, "op": "write", "ts": "t"})
    b = canonical_json({"ts": "t", "op": "write", "seq": 1})
    assert a == b


def test_canonical_nested_determinism():
    obj = {"z": [3, 2, 1], "a": {"n": 1, "m": 2}}
    assert canonical_json(obj) == canonical_json(obj)


def test_sha256_str_and_bytes_match():
    assert sha256_hex("hello") == sha256_hex(b"hello")


def test_sha256_known_value():
    assert sha256_hex("") == (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )


def test_sha256_length():
    assert len(sha256_hex("anything")) == 64


def test_short_hash_prefixes_full():
    full = sha256_hex("lamplight")
    assert short_hash("lamplight", 12) == full[:12]


def test_short_hash_default_length():
    assert len(short_hash("x")) == 12
