"""Token counting for the brief budget.

Lamplight enforces a hard token budget (default 2,000) on every brief
(invariant I3). Offline we cannot call a model tokenizer, so we use the
standard English heuristic of ~4 characters per token:

    tokens(text) = max(1, ceil(len(text) / 4))

Documented properties (tested):
- deterministic (pure function of the string),
- monotonic non-decreasing in text length,
- >= 1 for any non-empty text (so no item is ever "free"),
- conservative for typical clinical English (real tokenizers usually count
  FEWER tokens for the same prose, so a brief that passes this budget also
  passes the real one; live mode can substitute exact counts later without
  changing the packer contract).
"""

from __future__ import annotations

import math

__all__ = ["approx_tokens", "CHARS_PER_TOKEN"]

CHARS_PER_TOKEN = 4


def approx_tokens(text: str) -> int:
    """Approximate token count for *text* (see module docstring)."""
    if not text:
        return 0
    return max(1, math.ceil(len(text) / CHARS_PER_TOKEN))
