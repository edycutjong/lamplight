"""BudgetPacker — the brief is a token-budget knapsack (COMPLEXITY.md §3).

Items are priced in tokens and valued at

    value = rerank_score x decay_strength x criticality

The packer greedily fills the budget in descending value order (ties broken
by fewer tokens, then id — total determinism), skipping items that do not
fit and *logging why* ("left out, and why" is part of the product: budget
scarcity as UX). Greedy-by-value is deliberate: for a safety brief, the #1
item must never be dropped in favor of two cheaper #4s, so we do not solve
the optimal knapsack — we protect rank order under the cap.

Invariant I3: the packed total can never exceed the budget; a defensive
assertion raises BudgetViolation if it somehow would.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = ["PackCandidate", "PackResult", "BudgetPacker", "BudgetViolation"]


class BudgetViolation(AssertionError):
    """Raised if a pack would exceed its budget — must never happen."""


@dataclass(frozen=True)
class PackCandidate:
    id: str
    value: float
    tokens: int
    label: str = ""
    payload: Any = None

    def __post_init__(self) -> None:
        if self.tokens < 0:
            raise ValueError(f"negative token cost for {self.id}")


@dataclass
class PackResult:
    selected: list[PackCandidate] = field(default_factory=list)
    left_out: list[tuple[PackCandidate, str]] = field(default_factory=list)
    total_tokens: int = 0
    budget: int = 0

    @property
    def utilization(self) -> float:
        return self.total_tokens / self.budget if self.budget else 0.0


class BudgetPacker:
    def __init__(self, budget: int, max_items: int | None = None):
        if budget < 0:
            raise ValueError("budget must be >= 0")
        self.budget = budget
        self.max_items = max_items

    def pack(self, candidates: list[PackCandidate]) -> PackResult:
        result = PackResult(budget=self.budget)
        ordered = sorted(candidates, key=lambda c: (-c.value, c.tokens, c.id))
        used = 0
        for cand in ordered:
            if self.max_items is not None and len(result.selected) >= self.max_items:
                result.left_out.append((cand, "max_items_reached"))
                continue
            if cand.tokens > self.budget:
                result.left_out.append((cand, "item_exceeds_total_budget"))
                continue
            if used + cand.tokens > self.budget:
                result.left_out.append((cand, "budget_exhausted"))
                continue
            result.selected.append(cand)
            used += cand.tokens
        result.total_tokens = used
        if result.total_tokens > self.budget:  # pragma: no cover — I3 hard assert.
            # Provably unreachable: every accepted `cand` above passed
            # `used + cand.tokens > self.budget: continue`, so `used` can
            # never exceed `self.budget` after the loop. Kept as a hard
            # invariant guard against a future refactor breaking that
            # accounting, not exercised by design.
            raise BudgetViolation(
                f"packed {result.total_tokens} tokens > budget {self.budget}"
            )
        return result
