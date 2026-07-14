"""approx_tokens — the budget's ruler (I3)."""

from __future__ import annotations

import pytest

from lamplight_memory.tokens import CHARS_PER_TOKEN, approx_tokens


def test_empty_is_zero():
    assert approx_tokens("") == 0


def test_nonempty_is_at_least_one():
    assert approx_tokens("a") == 1
    assert approx_tokens("abc") == 1


def test_four_chars_per_token():
    assert approx_tokens("abcd") == 1
    assert approx_tokens("abcde") == 2
    assert approx_tokens("a" * 4 * CHARS_PER_TOKEN) == CHARS_PER_TOKEN


def test_deterministic():
    s = "rash onset 4h after cefazolin start"
    assert approx_tokens(s) == approx_tokens(s)


@pytest.mark.parametrize("n", [1, 5, 40, 400, 4000])
def test_monotonic_non_decreasing(n):
    assert approx_tokens("x" * n) <= approx_tokens("x" * (n + 1))


def test_ceil_behaviour():
    # 9 chars / 4 = 2.25 -> ceil 3
    assert approx_tokens("x" * 9) == 3


def test_conservative_vs_wordcount():
    # heuristic never returns 0 for real prose
    assert approx_tokens("the quick brown fox") >= 1
