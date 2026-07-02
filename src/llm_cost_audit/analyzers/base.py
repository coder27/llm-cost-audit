"""Analyzer contract: the Finding dataclass, config, and shared helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import pandas as pd

from ..pricing import Pricing

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


@dataclass
class Finding:
    analyzer: str
    severity: str  # "high" | "medium" | "low"
    caller: str
    title: str
    detail: str
    est_monthly_waste_usd: float | None
    recommendation: str


@dataclass
class AnalyzerConfig:
    """All tunable thresholds live here; the CLI overrides fields by name."""

    # dead_callers
    dead_days: int = 30
    dead_cv_threshold: float = 0.05
    dead_min_window_days: int = 14
    dead_high_spend_usd: float = 100.0

    # over_modeling
    over_median_total_tokens: int = 1500
    over_p90_output_tokens: int = 200

    # concentration
    concentration_medium_pct: float = 30.0
    concentration_high_pct: float = 50.0

    # pipeline-wide
    min_spend_usd: float = 1.0

    # Set at runtime from the data span; analyzers read it for extrapolation.
    window_days: float = field(default=30.0)


class Analyzer(Protocol):
    name: str

    def run(
        self, df: pd.DataFrame, pricing: Pricing, config: AnalyzerConfig
    ) -> list[Finding]: ...


def window_days(df: pd.DataFrame) -> float:
    """Span of the data in days (inclusive of both endpoints, min 1 day)."""
    if df.empty:
        return 1.0
    span = (df["timestamp"].max() - df["timestamp"].min()).total_seconds() / 86_400.0
    # +1 so a single day of data reads as one day, not zero.
    return max(span + 1.0, 1.0)


def monthly(value: float, days: float) -> float:
    """Extrapolate a window total to a 30-day month."""
    if days <= 0:
        return value
    return value * 30.0 / days


def daily_call_counts(caller_df: pd.DataFrame) -> pd.Series:
    """Calls per calendar (UTC) day for one caller, zero-filled across the span."""
    days = caller_df["timestamp"].dt.floor("D")
    counts = days.value_counts().sort_index()
    full = pd.date_range(counts.index.min(), counts.index.max(), freq="D", tz="UTC")
    return counts.reindex(full, fill_value=0)
