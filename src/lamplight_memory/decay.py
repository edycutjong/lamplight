"""DecayPolicy — timely forgetting as math (SPEC §5, COMPLEXITY §4).

    strength(t) = s0 * 2^(-Δt / λ_class)

Half-lives (λ):
    critical  — none (no decay until explicitly resolved + confirmed)
    condition — 72 h (3 days)
    routine   — 8 h (1 shift)
    resolved  — retired immediately (strength 0; history only)

Status overrides class: resolved/expired items have strength 0, pinned items
hold strength 1.0. A human confirmation bumps s0 by +0.25 (capped at 1.0)
and resets the decay clock — memory that a nurse vouches for lives longer.
Items whose strength falls below EXPIRY_THRESHOLD are expired by the nightly
sweep (an auditable, signed `expire` op — forgetting is a fact, not a shrug).
"""

from __future__ import annotations

from .clock import hours_between
from .schemas import DecayClass, Status

__all__ = ["DecayPolicy"]


class DecayPolicy:
    HALF_LIFE_HOURS: dict[DecayClass, float | None] = {
        DecayClass.CRITICAL: None,  # no decay
        DecayClass.CONDITION: 72.0,  # 3 days
        DecayClass.ROUTINE: 8.0,  # 1 shift
        DecayClass.RESOLVED: 0.0,  # retired immediately
    }
    EXPIRY_THRESHOLD = 0.05
    CONFIRM_BUMP = 0.25

    # Criticality multipliers for brief packing value
    # (rerank_score x decay_strength x criticality — SPEC §5).
    CRITICALITY = {
        DecayClass.CRITICAL: 3.0,
        DecayClass.CONDITION: 1.5,
        DecayClass.ROUTINE: 1.0,
        DecayClass.RESOLVED: 0.0,
    }

    def strength(
        self,
        decay_class: DecayClass | str,
        s0: float,
        t0: str,
        now: str,
        status: Status | str = Status.ACTIVE,
    ) -> float:
        """Current strength of a memory item.

        *t0* is the last confirmation (or write) timestamp; *now* is when the
        brief is built. Negative elapsed time clamps to 0 (clock skew guard).
        """
        status = Status(status)
        if status in (Status.RESOLVED, Status.EXPIRED):
            return 0.0
        if status is Status.PINNED:
            return 1.0

        decay_class = DecayClass(decay_class)
        if decay_class is DecayClass.RESOLVED:
            return 0.0

        s0 = min(max(s0, 0.0), 1.0)
        half_life = self.HALF_LIFE_HOURS[decay_class]
        if half_life is None:
            return s0  # critical: no decay until resolved+confirmed

        dt = max(0.0, hours_between(t0, now))
        return s0 * 2.0 ** (-dt / half_life)

    def multiplier(
        self, decay_class: DecayClass | str, needs_confirmation: bool = False
    ) -> float:
        """Criticality multiplier for packing value.

        Unconfirmed contradictions are treated as critical: a conflict about a
        patient's state must never silently decay out of the brief.
        """
        if needs_confirmation:
            return self.CRITICALITY[DecayClass.CRITICAL]
        return self.CRITICALITY[DecayClass(decay_class)]

    def confirm(self, s0: float) -> float:
        """Confirmation bump: s0 -> min(1.0, s0 + 0.25). Caller resets t0."""
        return min(1.0, s0 + self.CONFIRM_BUMP)

    def is_expired(self, strength: float, decay_class: DecayClass | str) -> bool:
        """Sweep rule: routine/condition items expire below the threshold.
        Critical items never expire by decay — only by explicit resolution."""
        decay_class = DecayClass(decay_class)
        if decay_class is DecayClass.CRITICAL:
            return False
        return strength < self.EXPIRY_THRESHOLD
