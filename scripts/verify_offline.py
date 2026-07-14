#!/usr/bin/env python3
"""verify_offline.py — the zero-key judge path, with the network physically off.

Proves Lamplight's core claims WITHOUT a DASHSCOPE_API_KEY and WITHOUT any
network access:

  1. install a hard socket guard — any attempt to open a network socket raises;
  2. rebuild the entire 5-day ward from committed fixtures (fake transport,
     sealed at rest) and regenerate the hero brief (Bed 9, incoming shift 15);
  3. byte-compare it to the committed expected brief (invariant I5);
  4. verify the Ed25519 hash-chained op ledger end-to-end (invariant I4).

Exit 0 iff the brief is byte-identical AND the chain verifies, with zero
sockets opened along the way.

    python scripts/verify_offline.py
"""

from __future__ import annotations

import socket
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))


class NetworkBlocked(RuntimeError):
    pass


def _install_socket_guard() -> None:
    """Replace socket.socket with a stub that refuses to construct — any
    outbound call (OpenAI, httpx, DashScope) fails loudly instead of leaking."""

    def _blocked(*_args, **_kwargs):
        raise NetworkBlocked(
            "network access attempted during offline verification — "
            "Lamplight's judge path must run with zero sockets"
        )

    socket.socket = _blocked  # type: ignore[assignment]
    # also neuter the convenience connectors
    socket.create_connection = _blocked  # type: ignore[assignment]


def main() -> int:
    _install_socket_guard()

    # imported AFTER the guard so any accidental import-time socket use trips it
    from lamplight_memory.paths import find_fixtures
    from lamplight_memory.replay import replay

    fixtures_root = find_fixtures(None)
    print(f"fixtures: {fixtures_root}")
    print("network:  BLOCKED (socket guard installed)")

    result = replay(fixtures_root)

    print(
        f"chain:    {'OK' if result.chain.ok else 'FAIL'} "
        f"({result.chain.length} signed ops, pubkey {result.chain.pubkey[:16]}...)"
    )
    print(
        f"brief:    {'byte-identical' if result.byte_identical else 'MISMATCH'} "
        f"vs {result.expected_path.name}"
    )
    print(result.detail)

    if not result.ok:
        print("\nOFFLINE VERIFY FAILED", file=sys.stderr)
        return 1
    print("\nOFFLINE VERIFY PASS — replay byte-identical + chain verified, zero network")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
