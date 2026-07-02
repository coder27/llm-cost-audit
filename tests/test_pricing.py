"""Pricing table loading, cost computation, divergence warning, and an exact
hand-computed savings check for the over-modeling case."""

from __future__ import annotations

import pandas as pd
import pytest

from llm_cost_audit.analyzers import over_modeling
from llm_cost_audit.analyzers.base import monthly
from llm_cost_audit.pricing import Pricing, compute_costs


def test_pricing_loads_expected_models(pricing):
    assert pricing.pricing_as_of == "2026-07-01"
    opus = pricing.get("claude-opus-4-6")
    assert opus is not None
    assert opus.tier == "frontier"
    assert opus.cheaper_alternative == "claude-haiku-4-5"
    assert pricing.get("claude-haiku-4-5").tier == "small"


def test_cost_for_single_call(pricing):
    # 1M input + 1M output on gpt-4o = $2.50 + $10.00.
    assert pricing.cost_for("gpt-4o", 1_000_000, 1_000_000) == pytest.approx(12.50)


def test_unknown_model_warns_and_excludes():
    p = Pricing.load()
    df = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2026-01-01"], utc=True),
            "caller": ["x"],
            "model": ["totally-made-up-model"],
            "input_tokens": [100],
            "output_tokens": [100],
        }
    )
    out, warnings = compute_costs(df, p)
    assert any("No pricing" in w for w in warnings)
    assert out["computed_cost_usd"].isna().all()


def test_provided_cost_divergence_warns():
    p = Pricing.load()
    # gpt-4o 1M/1M ~ $12.50 computed; provide a wildly different $99.
    df = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2026-01-01"], utc=True),
            "caller": ["x"],
            "model": ["gpt-4o"],
            "input_tokens": [1_000_000],
            "output_tokens": [1_000_000],
            "cost_usd": [99.0],
        }
    )
    _, warnings = compute_costs(df, p)
    assert any("diverges" in w for w in warnings)


def test_provided_cost_within_tolerance_no_warning():
    p = Pricing.load()
    df = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2026-01-01"], utc=True),
            "caller": ["x"],
            "model": ["gpt-4o"],
            "input_tokens": [1_000_000],
            "output_tokens": [1_000_000],
            "cost_usd": [12.60],  # ~0.8% off computed 12.50
        }
    )
    _, warnings = compute_costs(df, p)
    assert not any("diverges" in w for w in warnings)


def test_over_modeling_savings_math_is_exact(analyzed_df, pricing, config):
    """Hand-compute ticket-classifier's savings straight from the dataframe and
    pricing table, and assert the analyzer matches to the cent."""
    rows = analyzed_df[
        (analyzed_df["caller"] == "ticket-classifier")
        & (analyzed_df["model"] == "claude-opus-4-6")
    ]
    haiku = pricing.get("claude-haiku-4-5")

    current = float(rows["cost_usd"].sum())
    alt = float(
        (rows["input_tokens"] / 1e6 * haiku.input_per_mtok).sum()
        + (rows["output_tokens"] / 1e6 * haiku.output_per_mtok).sum()
    )
    expected = monthly(current - alt, config.window_days)

    out = over_modeling.run(analyzed_df, pricing, config)
    finding = next(f for f in out if f.caller == "ticket-classifier")
    assert finding.est_monthly_waste_usd == pytest.approx(expected, abs=1e-9)
