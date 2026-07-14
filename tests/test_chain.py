"""OpChain + ChainAudit — signed hash-chained op ledger (I4)."""

from __future__ import annotations

import sqlite3

import pytest

from lamplight_memory.chain import (
    GENESIS_HASH,
    ChainAudit,
    OpChain,
    demo_signing_key,
)
from lamplight_memory.clock import iso, shift_close
from lamplight_memory.schemas import OpType


def make_chain(path, n=5):
    chain = OpChain(path)
    for i in range(1, n + 1):
        chain.append(
            OpType.WRITE, {"id": f"ep-{i}", "n": i}, ts=iso(shift_close(i))
        )
    chain.close()
    return path


def verify(path):
    audit = ChainAudit(path)
    try:
        return audit.verify()
    finally:
        audit.close()


def test_fresh_chain_verifies_empty(tmp_path):
    db = tmp_path / "c.db"
    OpChain(db).close()
    rep = verify(db)
    assert rep.ok is True
    assert rep.length == 0


def test_append_increments_seq_and_links(tmp_path):
    db = tmp_path / "c.db"
    chain = OpChain(db)
    e1 = chain.append(OpType.WRITE, {"a": 1}, ts=iso(shift_close(1)))
    e2 = chain.append(OpType.DECAY, {"b": 2}, ts=iso(shift_close(1)))
    chain.close()
    assert e1["seq"] == 1
    assert e1["prev_hash"] == GENESIS_HASH
    assert e2["seq"] == 2
    assert e2["prev_hash"] != GENESIS_HASH


def test_full_chain_verifies(tmp_path):
    db = make_chain(tmp_path / "c.db", 8)
    rep = verify(db)
    assert rep.ok is True
    assert rep.length == 8
    assert rep.ops_by_type == {"write": 8}


def test_ops_by_type_counts(tmp_path):
    db = tmp_path / "c.db"
    chain = OpChain(db)
    chain.append(OpType.WRITE, {}, ts=iso(shift_close(1)))
    chain.append(OpType.DECAY, {}, ts=iso(shift_close(1)))
    chain.append(OpType.DECAY, {}, ts=iso(shift_close(1)))
    chain.close()
    rep = verify(db)
    assert rep.ops_by_type == {"write": 1, "decay": 2}


def test_tamper_payload_fails(tmp_path):
    db = make_chain(tmp_path / "c.db", 5)
    con = sqlite3.connect(db)
    row = con.execute("SELECT payload FROM op_chain WHERE seq=3").fetchone()
    tampered = row[0].replace("3", "4", 1)
    con.execute("UPDATE op_chain SET payload=? WHERE seq=3", (tampered,))
    con.commit()
    con.close()
    rep = verify(db)
    assert rep.ok is False
    assert rep.error == "payload hash mismatch"
    assert rep.bad_seq == 3


def test_tamper_signature_fails(tmp_path):
    db = make_chain(tmp_path / "c.db", 5)
    con = sqlite3.connect(db)
    sig = con.execute("SELECT sig FROM op_chain WHERE seq=2").fetchone()[0]
    flipped = ("ff" if sig[:2] != "ff" else "00") + sig[2:]
    con.execute("UPDATE op_chain SET sig=? WHERE seq=2", (flipped,))
    con.commit()
    con.close()
    rep = verify(db)
    assert rep.ok is False
    assert rep.error == "bad signature"


def test_tamper_prev_hash_breaks_link(tmp_path):
    db = make_chain(tmp_path / "c.db", 5)
    con = sqlite3.connect(db)
    con.execute("UPDATE op_chain SET prev_hash=? WHERE seq=4", ("0" * 64,))
    con.commit()
    con.close()
    rep = verify(db)
    assert rep.ok is False
    # a mutated prev_hash breaks either the signature or the linkage check
    assert rep.error in ("broken hash link", "bad signature")
    assert rep.bad_seq == 4


def test_deleted_row_creates_sequence_gap(tmp_path):
    db = make_chain(tmp_path / "c.db", 5)
    con = sqlite3.connect(db)
    con.execute("DELETE FROM op_chain WHERE seq=3")
    con.commit()
    con.close()
    rep = verify(db)
    assert rep.ok is False
    assert "sequence gap" in rep.error


def test_signatures_deterministic_across_builds(tmp_path):
    a = make_chain(tmp_path / "a.db", 5)
    b = make_chain(tmp_path / "b.db", 5)
    con_a = sqlite3.connect(a)
    con_b = sqlite3.connect(b)
    sigs_a = [r[0] for r in con_a.execute("SELECT sig FROM op_chain ORDER BY seq")]
    sigs_b = [r[0] for r in con_b.execute("SELECT sig FROM op_chain ORDER BY seq")]
    con_a.close()
    con_b.close()
    assert sigs_a == sigs_b  # Ed25519 is deterministic (RFC 8032) + ward clock


def test_reopen_with_wrong_key_rejected(tmp_path):
    db = tmp_path / "c.db"
    OpChain(db).close()
    from nacl.signing import SigningKey

    with pytest.raises(ValueError):
        OpChain(db, signing_key=SigningKey(b"\x01" * 32))


def test_demo_key_is_deterministic():
    assert demo_signing_key().encode() == demo_signing_key().encode()


def test_pubkey_recorded_in_report(tmp_path):
    db = make_chain(tmp_path / "c.db", 2)
    rep = verify(db)
    assert rep.pubkey == demo_signing_key().verify_key.encode().hex()


def test_entries_and_length(tmp_path):
    db = tmp_path / "c.db"
    chain = OpChain(db)
    for i in range(1, 4):
        chain.append(OpType.PIN, {"i": i}, ts=iso(shift_close(i)))
    assert chain.length() == 3
    entries = chain.entries()
    assert [e["seq"] for e in entries] == [1, 2, 3]
    tail = chain.entries(limit=2, tail=True)
    assert [e["seq"] for e in tail] == [2, 3]
    chain.close()


# --------------------------------------------------------------------------- #
# signing key resolution + defensive audit paths
# --------------------------------------------------------------------------- #


def test_signing_seed_env_var_used(tmp_path, monkeypatch):
    from nacl.signing import SigningKey

    seed_hex = "11" * 32
    monkeypatch.setenv("LAMPLIGHT_SIGNING_SEED_HEX", seed_hex)
    db = tmp_path / "c.db"
    chain = OpChain(db)
    expected = SigningKey(bytes.fromhex(seed_hex))
    assert chain.signing_key.encode() == expected.encode()
    assert chain.pubkey_hex == expected.verify_key.encode().hex()
    chain.close()


def test_audit_no_pubkey_recorded(tmp_path):
    import sqlite3

    from lamplight_memory.chain import _CHAIN_SCHEMA

    db = tmp_path / "bare.db"
    con = sqlite3.connect(db)
    con.executescript(_CHAIN_SCHEMA)  # tables exist, but chain_meta is empty
    con.commit()
    con.close()

    rep = verify(db)
    assert rep.ok is False
    assert rep.length == 0
    assert rep.pubkey == ""
    assert rep.error == "no public key recorded"


def test_tamper_payload_to_invalid_json_but_consistent_hash(tmp_path):
    """A payload rewritten to non-JSON text, with payload_hash re-derived and
    the entry re-signed with the same (demo) key so linkage/signature checks
    still pass, must still fail the final JSON sanity pass."""
    import sqlite3

    from lamplight_memory.util import canonical_json, sha256_hex

    db = tmp_path / "c.db"
    chain = OpChain(db)
    entry = chain.append(OpType.WRITE, {"a": 1}, ts=iso(shift_close(1)))
    chain.close()

    bad_payload = "not actually json"
    bad_hash = sha256_hex(bad_payload)
    new_entry = {
        "seq": entry["seq"],
        "ts": entry["ts"],
        "op": entry["op"],
        "payload_hash": bad_hash,
        "prev_hash": entry["prev_hash"],
    }
    msg = canonical_json(new_entry).encode("utf-8")
    new_sig = demo_signing_key().sign(msg).signature.hex()

    con = sqlite3.connect(db)
    con.execute(
        "UPDATE op_chain SET payload=?, payload_hash=?, sig=? WHERE seq=1",
        (bad_payload, bad_hash, new_sig),
    )
    con.commit()
    con.close()
    rep = verify(db)
    assert rep.ok is False
    assert rep.error == "payload not JSON"
    assert rep.bad_seq == 1
