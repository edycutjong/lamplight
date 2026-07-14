"""CostLedger — the $/patient-day estimate (placeholder prices, disclosed)."""

from __future__ import annotations

import pytest

from lamplight_memory.pricing import (
    ASSUMED_PRICES_PER_MTOK,
    BATCH_DISCOUNT,
    CostLedger,
)


def test_add_and_total():
    led = CostLedger()
    led.add("text-embedding-v4", 1_000_000)
    assert led.total_usd() == pytest.approx(ASSUMED_PRICES_PER_MTOK["text-embedding-v4"])


def test_add_accumulates():
    led = CostLedger()
    led.add("qwen3-rerank", 500_000)
    led.add("qwen3-rerank", 500_000)
    assert led.tokens["qwen3-rerank"] == 1_000_000


def test_batch_discount_halves_cost():
    led = CostLedger()
    led.add("qwen3.7-plus:input", 1_000_000, batch=True)
    expected = ASSUMED_PRICES_PER_MTOK["qwen3.7-plus:input"] * BATCH_DISCOUNT
    assert led.total_usd() == pytest.approx(expected)


def test_unknown_surface_priced_zero_in_total():
    led = CostLedger()
    led.add("mystery-model", 1_000_000)
    assert led.total_usd() == 0.0


def test_negative_tokens_clamped():
    led = CostLedger()
    led.add("qwen3-rerank", -5)
    assert led.tokens["qwen3-rerank"] == 0


def test_per_patient_day_divides():
    led = CostLedger()
    led.add("text-embedding-v4", 6_000_000)
    total = led.total_usd()
    assert led.per_patient_day(patients=6, days=5.0) == pytest.approx(total / 30.0)


def test_per_patient_day_rejects_nonpositive():
    led = CostLedger()
    with pytest.raises(ValueError):
        led.per_patient_day(patients=0, days=5)
    with pytest.raises(ValueError):
        led.per_patient_day(patients=6, days=0)


def test_breakdown_sorted_and_complete():
    led = CostLedger()
    led.add("text-embedding-v4", 100)
    led.add("qwen3-rerank", 200)
    rows = led.breakdown()
    surfaces = [r[0] for r in rows]
    assert surfaces == sorted(surfaces)
    assert len(rows) == 2


def test_breakdown_batch_discounted():
    led = CostLedger()
    led.add("qwen3.7-plus:output", 1_000_000, batch=True)
    _, n, usd = led.breakdown()[0]
    assert n == 1_000_000
    assert usd == pytest.approx(
        ASSUMED_PRICES_PER_MTOK["qwen3.7-plus:output"] * BATCH_DISCOUNT
    )
