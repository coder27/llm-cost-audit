"""over_modeling -- frontier-tier models doing work that looks small enough
for a cheaper model."""

from __future__ import annotations

import pandas as pd

from ..pricing import Pricing
from .base import AnalyzerConfig, Finding, monthly

name = "over_modeling"


def run(df: pd.DataFrame, pricing: Pricing, config: AnalyzerConfig) -> list[Finding]:
    findings: list[Finding] = []

    for caller, cdf in df.groupby("caller"):
        # Evaluate the caller's primary (most-called) model.
        primary_model = cdf["model"].value_counts().idxmax()
        price = pricing.get(primary_model)
        if price is None or price.tier != "frontier":
            continue

        alt = price.cheaper_alternative
        alt_price = pricing.get(alt) if alt else None
        if alt_price is None:
            # Nothing concrete to recommend; skip rather than guess.
            continue

        rows = cdf[cdf["model"] == primary_model]
        total_tokens = rows["input_tokens"] + rows["output_tokens"]
        median_total = float(total_tokens.median())
        p90_output = float(rows["output_tokens"].quantile(0.90))

        small_total = median_total < config.over_median_total_tokens
        classification_shaped = p90_output < config.over_p90_output_tokens
        if not (small_total or classification_shaped):
            continue

        current_cost = float(rows["cost_usd"].sum(skipna=True))
        alt_cost = float(
            (rows["input_tokens"] / 1e6 * alt_price.input_per_mtok).sum()
            + (rows["output_tokens"] / 1e6 * alt_price.output_per_mtok).sum()
        )
        monthly_current = monthly(current_cost, config.window_days)
        monthly_alt = monthly(alt_cost, config.window_days)
        savings = monthly_current - monthly_alt
        if savings <= 0:
            continue

        if savings > 100:
            severity = "high"
        elif savings > 10:
            severity = "medium"
        else:
            severity = "low"

        reasons = []
        if small_total:
            reasons.append(f"median request is only {median_total:,.0f} tokens")
        if classification_shaped:
            reasons.append(
                f"90th-percentile output is just {p90_output:,.0f} tokens "
                f"(classification-shaped)"
            )

        detail = (
            f"'{caller}' runs on the frontier-tier model '{primary_model}' but "
            f"{' and '.join(reasons)}. Work this small rarely needs a frontier "
            f"model. Over the {config.window_days:.0f}-day window it cost "
            f"${monthly_current:,.2f}/month; the same volume on "
            f"'{alt}' would cost about ${monthly_alt:,.2f}/month. "
            f"Verify quality with an eval before switching -- token size is a "
            f"proxy for task difficulty, not a guarantee."
        )
        findings.append(
            Finding(
                analyzer=name,
                severity=severity,
                caller=str(caller),
                title=(
                    f"{caller}: over-modeled on {primary_model} "
                    f"(~${savings:,.0f}/mo recoverable)"
                ),
                detail=detail,
                est_monthly_waste_usd=savings,
                recommendation=(
                    f"Trial '{alt}' for '{caller}'. Estimated new cost "
                    f"~${monthly_alt:,.2f}/month (down from ${monthly_current:,.2f}), "
                    f"saving ~${savings:,.2f}/month. Gate the switch on an eval."
                ),
            )
        )

    return findings
