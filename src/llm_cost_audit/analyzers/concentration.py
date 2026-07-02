"""concentration -- Pareto analysis of spend across callers (visibility only)."""

from __future__ import annotations

import pandas as pd

from ..pricing import Pricing
from .base import AnalyzerConfig, Finding

name = "concentration"


def run(df: pd.DataFrame, pricing: Pricing, config: AnalyzerConfig) -> list[Finding]:
    by_caller = df.groupby("caller")["cost_usd"].sum(min_count=1).fillna(0.0)
    total = float(by_caller.sum())
    if total <= 0:
        return []

    shares = (by_caller / total * 100.0).sort_values(ascending=False)
    top5 = shares.head(5)
    top5_str = "; ".join(f"{c} {pct:.1f}%" for c, pct in top5.items())

    findings: list[Finding] = []
    for caller, pct in shares.items():
        if pct <= config.concentration_medium_pct:
            continue
        severity = "high" if pct > config.concentration_high_pct else "medium"
        detail = (
            f"'{caller}' accounts for {pct:.1f}% of total spend across the "
            f"{config.window_days:.0f}-day window. Spend this concentrated means "
            f"one workflow's efficiency (or a single bug or retry storm there) "
            f"dominates the whole bill. Top callers by share: {top5_str}. This is "
            f"a visibility finding, not a waste estimate -- the spend may be "
            f"entirely justified."
        )
        findings.append(
            Finding(
                analyzer=name,
                severity=severity,
                caller=str(caller),
                title=f"{caller}: {pct:.0f}% of all spend is concentrated in one caller",
                detail=detail,
                est_monthly_waste_usd=None,
                recommendation=(
                    f"Prioritize '{caller}' for review: prompt-caching, batching, "
                    f"and model-tier checks here move the total bill more than "
                    f"anywhere else. Add per-request cost alerting so a regression "
                    f"is caught early."
                ),
            )
        )
    return findings
