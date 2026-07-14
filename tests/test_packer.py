"""BudgetPacker — the token-budget knapsack. I3: never exceeds the budget."""

from __future__ import annotations

import random

import pytest

from lamplight_memory.packer import (
    BudgetPacker,
    BudgetViolation,
    PackCandidate,
    PackResult,
)


def C(id, value, tokens, label=""):
    return PackCandidate(id=id, value=value, tokens=tokens, label=label)


def test_basic_pack_within_budget():
    packer = BudgetPacker(budget=100)
    res = packer.pack([C("a", 3.0, 40), C("b", 2.0, 40), C("c", 1.0, 40)])
    assert [c.id for c in res.selected] == ["a", "b"]
    assert res.total_tokens == 80
    assert res.total_tokens <= res.budget


def test_descending_value_order():
    packer = BudgetPacker(budget=1000)
    res = packer.pack([C("low", 0.1, 10), C("high", 9.9, 10), C("mid", 5.0, 10)])
    assert [c.id for c in res.selected] == ["high", "mid", "low"]


def test_tie_break_fewer_tokens_then_id():
    packer = BudgetPacker(budget=1000)
    res = packer.pack([C("b", 1.0, 20), C("a", 1.0, 20), C("c", 1.0, 5)])
    # equal value -> fewer tokens first (c), then id (a before b)
    assert [c.id for c in res.selected] == ["c", "a", "b"]


def test_item_larger_than_budget_left_out():
    packer = BudgetPacker(budget=50)
    res = packer.pack([C("huge", 10.0, 500), C("ok", 1.0, 40)])
    assert [c.id for c in res.selected] == ["ok"]
    reasons = {pc.id: r for pc, r in res.left_out}
    assert reasons["huge"] == "item_exceeds_total_budget"


def test_budget_exhausted_reason():
    packer = BudgetPacker(budget=60)
    res = packer.pack([C("a", 3.0, 40), C("b", 2.0, 40)])
    assert [c.id for c in res.selected] == ["a"]
    reasons = {pc.id: r for pc, r in res.left_out}
    assert reasons["b"] == "budget_exhausted"


def test_max_items_cap():
    packer = BudgetPacker(budget=100000, max_items=2)
    res = packer.pack([C("a", 3, 1), C("b", 2, 1), C("c", 1, 1)])
    assert len(res.selected) == 2
    reasons = {pc.id: r for pc, r in res.left_out}
    assert reasons["c"] == "max_items_reached"


def test_zero_token_items_allowed():
    packer = BudgetPacker(budget=10)
    res = packer.pack([C("free1", 1.0, 0), C("free2", 0.5, 0)])
    assert len(res.selected) == 2
    assert res.total_tokens == 0


def test_exact_fit():
    packer = BudgetPacker(budget=80)
    res = packer.pack([C("a", 2.0, 40), C("b", 1.0, 40)])
    assert res.total_tokens == 80
    assert res.utilization == pytest.approx(1.0)


def test_empty_candidates():
    res = BudgetPacker(budget=2000).pack([])
    assert res.selected == []
    assert res.total_tokens == 0
    assert res.utilization == 0.0


def test_negative_budget_rejected():
    with pytest.raises(ValueError):
        BudgetPacker(budget=-1)


def test_negative_tokens_rejected_on_candidate():
    with pytest.raises(ValueError):
        PackCandidate(id="x", value=1.0, tokens=-5)


def test_zero_budget_takes_only_zero_token_items():
    res = BudgetPacker(budget=0).pack([C("free", 1.0, 0), C("paid", 5.0, 1)])
    assert [c.id for c in res.selected] == ["free"]


@pytest.mark.parametrize("seed", range(40))
def test_never_exceeds_budget_adversarial(seed):
    """Property: across randomized adversarial item sizes (including 0, giant,
    and exactly-budget items), the packed total NEVER exceeds the budget."""
    rng = random.Random(seed)
    budget = rng.choice([1, 7, 100, 2000])
    n = rng.randint(0, 60)
    cands = []
    for i in range(n):
        tokens = rng.choice(
            [0, 1, rng.randint(1, budget + 5), budget, budget * 3, rng.randint(1, 5000)]
        )
        cands.append(C(f"i{i}", rng.uniform(-2, 10), tokens))
    res = BudgetPacker(budget=budget, max_items=rng.choice([None, 5])).pack(cands)
    assert res.total_tokens <= budget
    assert res.total_tokens == sum(c.tokens for c in res.selected)
    # every candidate is either selected or explained
    assert len(res.selected) + len(res.left_out) == n


@pytest.mark.parametrize("budget", [2000])
def test_two_thousand_token_cap_holds(budget):
    """The clinical budget: many oversized cards, still <= 2000."""
    rng = random.Random(1234)
    cards = [C(f"c{i}", rng.uniform(0, 5), rng.randint(200, 900)) for i in range(50)]
    res = BudgetPacker(budget=budget, max_items=5).pack(cards)
    assert res.total_tokens <= 2000
    assert len(res.selected) <= 5


def test_defensive_budget_violation_is_assertion_error():
    assert issubclass(BudgetViolation, AssertionError)


def test_result_is_packresult():
    assert isinstance(BudgetPacker(10).pack([]), PackResult)
