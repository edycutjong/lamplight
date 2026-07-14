"""Citation validator — clinical-grade honesty as architecture (SPEC §2).

Every brief card must cite >= 1 source episode, every cited episode must
exist, and every cited episode must be ACTIVE (or pinned) at the brief's
`as_of` point. Cards that fail are *mechanically rejected* — an uncited
claim never reaches a nurse. This enforces invariants:

    I1 — every brief item cites >= 1 existing, active episode ID
    I2 — zero resolved/expired items in any brief

The validator is deliberately dumb: no model in the loop, pure lookups.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from .schemas import BriefCard, Status

__all__ = ["CitationValidator", "ValidationResult", "RejectedCard"]

# resolver(citation_id) -> Status at the brief's as_of, or None if the id
# does not exist (or did not exist yet) at that point.
StatusResolver = Callable[[str], Status | None]


@dataclass(frozen=True)
class RejectedCard:
    card: BriefCard
    reason: str


@dataclass
class ValidationResult:
    valid: list[BriefCard] = field(default_factory=list)
    rejected: list[RejectedCard] = field(default_factory=list)

    @property
    def all_valid(self) -> bool:
        return not self.rejected


class CitationValidator:
    ALLOWED = (Status.ACTIVE, Status.PINNED)

    def __init__(self, resolver: StatusResolver):
        self._resolve = resolver

    def validate_card(self, card: BriefCard) -> str | None:
        """Return a rejection reason, or None if the card is valid."""
        if not card.citations:
            return "uncited"
        for cid in card.citations:
            status = self._resolve(cid)
            if status is None:
                return f"unknown_citation:{cid}"
            if status is Status.RESOLVED:
                return f"cited_source_resolved:{cid}"
            if status is Status.EXPIRED:
                return f"cited_source_expired:{cid}"
            if status not in self.ALLOWED:
                return f"cited_source_not_active:{cid}"
        if not card.sbar.strip():
            return "empty_sbar"
        return None

    def validate(self, cards: list[BriefCard]) -> ValidationResult:
        result = ValidationResult()
        for card in cards:
            reason = self.validate_card(card)
            if reason is None:
                result.valid.append(card)
            else:
                result.rejected.append(RejectedCard(card=card, reason=reason))
        return result
