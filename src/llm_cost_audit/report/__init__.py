"""Report models shared by the terminal, JSON, and HTML renderers."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from ..analyzers.base import Finding, monthly


@dataclass
class Summary:
    total_spend_usd: float  # over the analysis window
    monthly_spend_usd: float  # extrapolated to 30 days
    window_days: float
    window_start: str  # ISO
    window_end: str  # ISO
    caller_count: int
    model_count: int
    recoverable_monthly_usd: float
    pricing_as_of: str
    warnings: list[str] = field(default_factory=list)


def build_summary(
    df: pd.DataFrame,
    findings: list[Finding],
    window_days: float,
    pricing_as_of: str,
    warnings: list[str],
) -> Summary:
    total = float(df["cost_usd"].sum(skipna=True))
    recoverable = sum(
        f.est_monthly_waste_usd for f in findings if f.est_monthly_waste_usd
    )
    return Summary(
        total_spend_usd=total,
        monthly_spend_usd=monthly(total, window_days),
        window_days=window_days,
        window_start=df["timestamp"].min().isoformat(),
        window_end=df["timestamp"].max().isoformat(),
        caller_count=int(df["caller"].nunique()),
        model_count=int(df["model"].nunique()),
        recoverable_monthly_usd=recoverable,
        pricing_as_of=pricing_as_of,
        warnings=warnings,
    )
