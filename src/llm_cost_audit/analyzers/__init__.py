"""Analyzer registry.

Adding analyzer #4 later is one new module plus one line in REGISTRY.
"""

from __future__ import annotations

import pandas as pd

from ..pricing import Pricing
from . import concentration, dead_callers, over_modeling
from .base import SEVERITY_ORDER, Analyzer, AnalyzerConfig, Finding, window_days

# Order here is only the default run order; report output is re-sorted by waste.
REGISTRY: list[Analyzer] = [dead_callers, over_modeling, concentration]


def run_all(
    df: pd.DataFrame, pricing: Pricing, config: AnalyzerConfig
) -> list[Finding]:
    findings: list[Finding] = []
    for analyzer in REGISTRY:
        findings.extend(analyzer.run(df, pricing, config))
    return findings


def sort_findings(findings: list[Finding]) -> list[Finding]:
    """Rank by estimated monthly waste desc; None (visibility) sinks below
    dollar findings but is broken by severity."""
    def key(f: Finding):
        has_waste = f.est_monthly_waste_usd is not None
        waste = f.est_monthly_waste_usd or 0.0
        return (not has_waste, -waste, SEVERITY_ORDER.get(f.severity, 9))

    return sorted(findings, key=key)


__all__ = [
    "REGISTRY",
    "run_all",
    "sort_findings",
    "Analyzer",
    "AnalyzerConfig",
    "Finding",
    "window_days",
]
