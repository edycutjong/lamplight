"""Ward clock: deterministic shift-based time.

The synthetic ward runs 15 shifts of 8 hours (5 days x day/evening/night).
All timestamps that enter the store, the op chain, or a brief come from this
clock — never from wall time — so replays are byte-identical (invariant I5).

Shift s (1-based) starts at T0 + (s-1)*8h. Day shift 07:00-15:00, evening
15:00-23:00, night 23:00-07:00.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

__all__ = [
    "T0",
    "SHIFT_HOURS",
    "shift_start",
    "shift_close",
    "shift_kind",
    "iso",
    "parse_iso",
    "hours_between",
]

T0 = datetime(2026, 6, 1, 7, 0, 0, tzinfo=UTC)
SHIFT_HOURS = 8

_KINDS = ("day", "evening", "night")


def shift_start(shift: int) -> datetime:
    """Start of *shift* (1-based)."""
    if shift < 1:
        raise ValueError(f"shift must be >= 1, got {shift}")
    return T0 + timedelta(hours=SHIFT_HOURS * (shift - 1))


def shift_close(shift: int) -> datetime:
    """End of *shift* — the moment handover happens and decay is measured."""
    return shift_start(shift) + timedelta(hours=SHIFT_HOURS)


def shift_kind(shift: int) -> str:
    """'day' / 'evening' / 'night' for a 1-based shift number."""
    return _KINDS[(shift - 1) % 3]


def iso(dt: datetime) -> str:
    """Canonical ISO-8601 string (UTC, seconds precision)."""
    return dt.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def hours_between(t0: str | datetime, t1: str | datetime) -> float:
    """Hours from t0 to t1 (may be negative)."""
    a = parse_iso(t0) if isinstance(t0, str) else t0
    b = parse_iso(t1) if isinstance(t1, str) else t1
    return (b - a).total_seconds() / 3600.0
