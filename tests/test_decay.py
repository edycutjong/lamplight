"""DecayPolicy — timely forgetting as math:  strength(t) = s0 * 2^(-dt/lambda).

Covers every decay class, status overrides, the confirmation bump, clock-skew
clamping, criticality multipliers, and the expiry-sweep rule.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from lamplight_memory.clock import iso, shift_start
from lamplight_memory.decay import DecayPolicy
from lamplight_memory.schemas import DecayClass, Status

T0 = iso(shift_start(1))


def at(hours: float) -> str:
    return iso(shift_start(1) + timedelta(hours=hours))


@pytest.fixture
def policy() -> DecayPolicy:
    return DecayPolicy()


# --------------------------------------------------------------------------- #
# half-life formula
# --------------------------------------------------------------------------- #


def test_condition_half_life_is_72h(policy):
    assert policy.strength(DecayClass.CONDITION, 1.0, T0, at(72)) == pytest.approx(0.5)


def test_condition_two_half_lives(policy):
    assert policy.strength(DecayClass.CONDITION, 1.0, T0, at(144)) == pytest.approx(0.25)


def test_routine_half_life_is_8h(policy):
    assert policy.strength(DecayClass.ROUTINE, 1.0, T0, at(8)) == pytest.approx(0.5)


def test_routine_two_half_lives(policy):
    assert policy.strength(DecayClass.ROUTINE, 1.0, T0, at(16)) == pytest.approx(0.25)


@pytest.mark.parametrize("hours", [0, 1, 4, 8, 24, 72, 100])
def test_formula_matches_closed_form(policy, hours):
    s0, lam = 0.8, 72.0
    expected = s0 * 2.0 ** (-hours / lam)
    assert policy.strength(DecayClass.CONDITION, s0, T0, at(hours)) == pytest.approx(
        expected
    )


def test_strength_monotonic_decreasing_over_time(policy):
    prev = 2.0
    for h in range(0, 80, 4):
        cur = policy.strength(DecayClass.ROUTINE, 1.0, T0, at(h))
        assert cur <= prev
        prev = cur


def test_at_zero_elapsed_returns_s0(policy):
    assert policy.strength(DecayClass.CONDITION, 0.7, T0, T0) == pytest.approx(0.7)


# --------------------------------------------------------------------------- #
# critical never decays
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("hours", [0, 8, 72, 1000])
def test_critical_never_decays(policy, hours):
    assert policy.strength(DecayClass.CRITICAL, 1.0, T0, at(hours)) == 1.0


def test_critical_holds_partial_s0(policy):
    assert policy.strength(DecayClass.CRITICAL, 0.6, T0, at(500)) == pytest.approx(0.6)


# --------------------------------------------------------------------------- #
# resolved / status overrides
# --------------------------------------------------------------------------- #


def test_resolved_class_is_zero(policy):
    assert policy.strength(DecayClass.RESOLVED, 1.0, T0, at(1)) == 0.0


def test_status_resolved_overrides_to_zero(policy):
    assert policy.strength(DecayClass.CRITICAL, 1.0, T0, at(1), status=Status.RESOLVED) == 0.0


def test_status_expired_overrides_to_zero(policy):
    assert policy.strength(DecayClass.CRITICAL, 1.0, T0, at(1), status=Status.EXPIRED) == 0.0


def test_status_pinned_holds_one(policy):
    # even a routine item pinned holds full strength regardless of elapsed time
    assert policy.strength(DecayClass.ROUTINE, 0.2, T0, at(1000), status=Status.PINNED) == 1.0


def test_status_accepts_string(policy):
    assert policy.strength("critical", 1.0, T0, at(5), status="pinned") == 1.0


# --------------------------------------------------------------------------- #
# clamping
# --------------------------------------------------------------------------- #


def test_negative_elapsed_clamps_to_zero(policy):
    # now BEFORE t0 (clock skew) -> no negative decay, returns s0
    assert policy.strength(DecayClass.ROUTINE, 1.0, at(8), T0) == pytest.approx(1.0)


def test_s0_clamped_high(policy):
    assert policy.strength(DecayClass.CRITICAL, 5.0, T0, at(1)) == 1.0


def test_s0_clamped_low(policy):
    assert policy.strength(DecayClass.CONDITION, -3.0, T0, at(1)) == 0.0


# --------------------------------------------------------------------------- #
# confirmation bump
# --------------------------------------------------------------------------- #


def test_confirm_bumps_by_quarter(policy):
    assert policy.confirm(0.5) == pytest.approx(0.75)


def test_confirm_caps_at_one(policy):
    assert policy.confirm(0.9) == 1.0
    assert policy.confirm(1.0) == 1.0


def test_confirm_bump_constant(policy):
    assert policy.CONFIRM_BUMP == 0.25


# --------------------------------------------------------------------------- #
# criticality multipliers
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "klass,mult",
    [
        (DecayClass.CRITICAL, 3.0),
        (DecayClass.CONDITION, 1.5),
        (DecayClass.ROUTINE, 1.0),
        (DecayClass.RESOLVED, 0.0),
    ],
)
def test_multiplier_by_class(policy, klass, mult):
    assert policy.multiplier(klass) == mult


def test_unconfirmed_contradiction_is_critical_weight(policy):
    # a routine-classed contradiction flag must be priced as critical
    assert policy.multiplier(DecayClass.ROUTINE, needs_confirmation=True) == 3.0


# --------------------------------------------------------------------------- #
# expiry sweep rule
# --------------------------------------------------------------------------- #


def test_is_expired_below_threshold(policy):
    assert policy.is_expired(0.04, DecayClass.ROUTINE) is True


def test_is_expired_at_threshold_is_false(policy):
    assert policy.is_expired(0.05, DecayClass.ROUTINE) is False


def test_is_expired_condition(policy):
    assert policy.is_expired(0.01, DecayClass.CONDITION) is True


def test_critical_never_expires_by_decay(policy):
    assert policy.is_expired(0.0, DecayClass.CRITICAL) is False


def test_routine_expires_after_enough_shifts(policy):
    # routine s0=1, half-life 8h; after ~5 half-lives (40h) strength < 0.05
    strength = policy.strength(DecayClass.ROUTINE, 1.0, T0, at(40))
    assert policy.is_expired(strength, DecayClass.ROUTINE) is True


def test_half_life_table(policy):
    assert policy.HALF_LIFE_HOURS[DecayClass.CRITICAL] is None
    assert policy.HALF_LIFE_HOURS[DecayClass.CONDITION] == 72.0
    assert policy.HALF_LIFE_HOURS[DecayClass.ROUTINE] == 8.0
    assert policy.HALF_LIFE_HOURS[DecayClass.RESOLVED] == 0.0
