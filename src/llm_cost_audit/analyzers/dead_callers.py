"""dead_callers -- flag callers that look abandoned (robotic or stale volume)."""

from __future__ import annotations

import pandas as pd

from ..pricing import Pricing
from .base import AnalyzerConfig, Finding, daily_call_counts, monthly

name = "dead_callers"


def _cv(counts: pd.Series) -> float:
    """Coefficient of variation of a daily-count series (0 when perfectly flat)."""
    mean = counts.mean()
    if mean == 0:
        return float("inf")
    return float(counts.std(ddof=0) / mean)


def run(df: pd.DataFrame, pricing: Pricing, config: AnalyzerConfig) -> list[Finding]:
    findings: list[Finding] = []

    for caller, cdf in df.groupby("caller"):
        counts = daily_call_counts(cdf)
        active_days = len(counts)
        cv = _cv(counts)

        # Robotic: essentially flat volume over a meaningful window -> a cron
        # nobody reviews.
        robotic = active_days >= config.dead_min_window_days and cv < config.dead_cv_threshold

        # Stale: the recent stretch (longer than dead_days) hasn't changed.
        stale = False
        if active_days > config.dead_days:
            trailing = counts.iloc[-config.dead_days :]
            stale = _cv(trailing) < config.dead_cv_threshold

        if not (robotic or stale):
            continue

        window_cost = float(cdf["cost_usd"].sum(skipna=True))
        monthly_spend = monthly(window_cost, config.window_days)
        severity = "high" if monthly_spend > config.dead_high_spend_usd else "medium"

        signals = []
        if robotic:
            signals.append(
                f"daily call volume is essentially flat (coefficient of "
                f"variation {cv:.3f} over {active_days} days)"
            )
        if stale:
            signals.append(
                f"volume has been unchanged for the trailing {config.dead_days} days"
            )

        avg_per_day = counts.mean()
        detail = (
            f"'{caller}' shows {'; '.join(signals)}. Over the {config.window_days:.0f}-day "
            f"analysis window it ran ~{avg_per_day:,.0f} calls/day for an "
            f"estimated ${monthly_spend:,.2f}/month, with no sign of human "
            f"review. Automated jobs that outlive their purpose are a common "
            f"source of silent spend."
        )
        findings.append(
            Finding(
                analyzer=name,
                severity=severity,
                caller=str(caller),
                title=f"{caller}: looks like an abandoned automated job (~${monthly_spend:,.0f}/mo)",
                detail=detail,
                est_monthly_waste_usd=monthly_spend,
                recommendation=(
                    f"Confirm whether '{caller}' is still needed. If it is an "
                    f"orphaned cron or deprecated workflow, decommission it to "
                    f"recover ~${monthly_spend:,.2f}/month."
                ),
            )
        )

    return findings
