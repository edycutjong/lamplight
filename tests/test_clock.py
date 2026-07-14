"""Ward clock — deterministic shift-based time (drives I5)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from lamplight_memory.clock import (
    SHIFT_HOURS,
    T0,
    hours_between,
    iso,
    parse_iso,
    shift_close,
    shift_kind,
    shift_start,
)


def test_t0_is_utc_and_fixed():
    assert iso(T0) == "2026-06-01T07:00:00Z"


@pytest.mark.parametrize("shift", range(1, 16))
def test_shift_start_is_eight_hours_apart(shift):
    delta = shift_start(shift) - T0
    assert delta == timedelta(hours=SHIFT_HOURS * (shift - 1))


@pytest.mark.parametrize("shift", range(1, 16))
def test_shift_close_is_start_plus_eight(shift):
    assert shift_close(shift) - shift_start(shift) == timedelta(hours=8)


def test_shift_close_equals_next_shift_start():
    for s in range(1, 15):
        assert shift_close(s) == shift_start(s + 1)


def test_shift_below_one_raises():
    with pytest.raises(ValueError):
        shift_start(0)
    with pytest.raises(ValueError):
        shift_start(-3)


@pytest.mark.parametrize(
    "shift,kind",
    [(1, "day"), (2, "evening"), (3, "night"), (4, "day"), (6, "night"), (15, "night")],
)
def test_shift_kind_cycles(shift, kind):
    assert shift_kind(shift) == kind


def test_iso_roundtrip():
    for s in range(1, 16):
        dt = shift_start(s)
        assert parse_iso(iso(dt)) == dt


def test_iso_is_z_suffixed_no_microseconds():
    s = iso(shift_start(4))
    assert s.endswith("Z")
    assert "." not in s


def test_hours_between_forward_and_back():
    a = iso(shift_start(1))
    b = iso(shift_close(1))
    assert hours_between(a, b) == pytest.approx(8.0)
    assert hours_between(b, a) == pytest.approx(-8.0)


def test_hours_between_accepts_datetimes():
    assert hours_between(shift_start(1), shift_start(4)) == pytest.approx(24.0)


def test_hours_between_zero():
    t = iso(shift_start(2))
    assert hours_between(t, t) == 0.0
