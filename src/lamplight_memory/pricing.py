"""Cost model for the bench's $/patient-day estimate.

IMPORTANT — these unit prices are PLACEHOLDER ASSUMPTIONS for an order-of-
magnitude estimate, not quoted Qwen Cloud prices. Before submission, replace
them with the numbers shown in your DashScope console (Model Studio ->
billing). The bench prints this disclaimer next to every $ figure.

Token counts come from the same documented approximation as the budget
packer (tokens ~= chars/4). Consolidation is priced at the Batch API's -50%
because it is a nightly offline job (SPEC §6).
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["ASSUMED_PRICES_PER_MTOK", "BATCH_DISCOUNT", "CostLedger"]

# USD per 1M tokens — ASSUMPTIONS, see module docstring.
ASSUMED_PRICES_PER_MTOK = {
    "qwen3.7-plus:input": 0.40,
    "qwen3.7-plus:output": 1.20,
    "text-embedding-v4": 0.07,
    "qwen3-rerank": 0.05,
}
BATCH_DISCOUNT = 0.5  # nightly consolidation runs on the Batch API (-50%)


@dataclass
class CostLedger:
    """Accumulates token usage by surface, then prices it."""

    tokens: dict[str, int] = field(default_factory=dict)
    batch_surfaces: set[str] = field(default_factory=set)

    def add(self, surface: str, n_tokens: int, batch: bool = False) -> None:
        self.tokens[surface] = self.tokens.get(surface, 0) + max(0, n_tokens)
        if batch:
            self.batch_surfaces.add(surface)

    def total_usd(self) -> float:
        usd = 0.0
        for surface, n in self.tokens.items():
            price = ASSUMED_PRICES_PER_MTOK.get(surface)
            if price is None:
                continue
            cost = n / 1_000_000 * price
            if surface in self.batch_surfaces:
                cost *= BATCH_DISCOUNT
            usd += cost
        return usd

    def per_patient_day(self, patients: int, days: float) -> float:
        if patients <= 0 or days <= 0:
            raise ValueError("patients and days must be positive")
        return self.total_usd() / (patients * days)

    def breakdown(self) -> list[tuple[str, int, float]]:
        rows = []
        for surface in sorted(self.tokens):
            n = self.tokens[surface]
            price = ASSUMED_PRICES_PER_MTOK.get(surface, 0.0)
            cost = n / 1_000_000 * price
            if surface in self.batch_surfaces:
                cost *= BATCH_DISCOUNT
            rows.append((surface, n, cost))
        return rows
