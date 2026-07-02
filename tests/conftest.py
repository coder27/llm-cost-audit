"""Shared test fixtures: the synthetic dataset run through the real pipeline."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from llm_cost_audit import ingest
from llm_cost_audit.analyzers import AnalyzerConfig, run_all
from llm_cost_audit.analyzers.base import Finding, monthly, window_days
from llm_cost_audit.pricing import Pricing, compute_costs

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_usage.csv"


@pytest.fixture(scope="session")
def fixture_path() -> Path:
    return FIXTURE


@pytest.fixture(scope="session")
def pricing() -> Pricing:
    return Pricing.load()


@pytest.fixture(scope="session")
def raw_df() -> pd.DataFrame:
    df, _ = ingest.load(FIXTURE)
    return df


@pytest.fixture(scope="session")
def costed_df(raw_df, pricing) -> pd.DataFrame:
    df, _ = compute_costs(raw_df, pricing)
    return df


@pytest.fixture(scope="session")
def config(costed_df) -> AnalyzerConfig:
    cfg = AnalyzerConfig()
    cfg.window_days = window_days(costed_df)
    return cfg


@pytest.fixture(scope="session")
def analyzed_df(costed_df, config) -> pd.DataFrame:
    """Costed df with the same min-spend gate the CLI applies."""
    by_caller = costed_df.groupby("caller")["cost_usd"].sum(min_count=1).fillna(0.0)
    keep = {
        c
        for c, cost in by_caller.items()
        if monthly(float(cost), config.window_days) >= config.min_spend_usd
    }
    return costed_df[costed_df["caller"].isin(keep)].reset_index(drop=True)


@pytest.fixture(scope="session")
def findings(analyzed_df, pricing, config) -> list[Finding]:
    return run_all(analyzed_df, pricing, config)
