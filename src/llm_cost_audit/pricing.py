"""Model pricing: load ``pricing.yaml``, compute and validate per-row costs."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from pathlib import Path

import pandas as pd
import yaml

# How far computed and provided costs may diverge before we warn (fraction).
COST_DIVERGENCE_THRESHOLD = 0.10


@dataclass(frozen=True)
class ModelPrice:
    model: str
    input_per_mtok: float
    output_per_mtok: float
    tier: str  # "frontier" | "mid" | "small"
    cheaper_alternative: str | None


class Pricing:
    """In-memory view of ``pricing.yaml`` with cost helpers."""

    def __init__(self, models: dict[str, ModelPrice], pricing_as_of: str):
        self._models = models
        self.pricing_as_of = pricing_as_of

    @classmethod
    def load(cls, path: Path | None = None) -> Pricing:
        """Load the packaged ``pricing.yaml`` or an explicit override path."""
        if path is not None:
            raw = yaml.safe_load(Path(path).read_text())
        else:
            data = resources.files("llm_cost_audit.data").joinpath("pricing.yaml")
            raw = yaml.safe_load(data.read_text())

        models: dict[str, ModelPrice] = {}
        for name, spec in (raw.get("models") or {}).items():
            models[name] = ModelPrice(
                model=name,
                input_per_mtok=float(spec["input_per_mtok"]),
                output_per_mtok=float(spec["output_per_mtok"]),
                tier=str(spec["tier"]),
                cheaper_alternative=spec.get("cheaper_alternative"),
            )
        return cls(models, str(raw.get("pricing_as_of", "unknown")))

    def known(self, model: str) -> bool:
        return model in self._models

    def get(self, model: str) -> ModelPrice | None:
        return self._models.get(model)

    def cost_for(self, model: str, input_tokens: int, output_tokens: int) -> float | None:
        """Cost in USD for one call, or ``None`` if the model is unpriced."""
        mp = self._models.get(model)
        if mp is None:
            return None
        return (
            input_tokens / 1e6 * mp.input_per_mtok
            + output_tokens / 1e6 * mp.output_per_mtok
        )

    def unknown_models(self, models: list[str]) -> list[str]:
        return sorted({m for m in models if m not in self._models})


def compute_costs(df: pd.DataFrame, pricing: Pricing) -> tuple[pd.DataFrame, list[str]]:
    """Attach a ``computed_cost_usd`` column and reconcile with any provided costs.

    Returns the augmented dataframe and a list of human-readable warning
    strings (unknown models, and cost columns that diverge from the pricing
    table by more than ``COST_DIVERGENCE_THRESHOLD``).
    """
    df = df.copy()
    warnings: list[str] = []

    price_in = df["model"].map(
        lambda m: mp.input_per_mtok if (mp := pricing.get(m)) else float("nan")
    )
    price_out = df["model"].map(
        lambda m: mp.output_per_mtok if (mp := pricing.get(m)) else float("nan")
    )
    df["computed_cost_usd"] = (
        df["input_tokens"] / 1e6 * price_in + df["output_tokens"] / 1e6 * price_out
    )

    unknown = pricing.unknown_models(df["model"].unique().tolist())
    if unknown:
        warnings.append(
            "No pricing for model(s): "
            + ", ".join(unknown)
            + ". Excluded from savings estimates."
        )

    # If the source provided its own cost_usd, keep it but flag large drift.
    if "cost_usd" in df.columns and df["cost_usd"].notna().any():
        priced = df["computed_cost_usd"].notna() & df["cost_usd"].notna()
        provided = df.loc[priced, "cost_usd"].sum()
        computed = df.loc[priced, "computed_cost_usd"].sum()
        if computed > 0:
            drift = abs(provided - computed) / computed
            if drift > COST_DIVERGENCE_THRESHOLD:
                warnings.append(
                    f"Provided cost_usd (${provided:,.2f}) diverges "
                    f"{drift:.0%} from pricing.yaml (${computed:,.2f}). "
                    "Using provided values for spend totals."
                )
        df["cost_usd"] = df["cost_usd"].where(df["cost_usd"].notna(), df["computed_cost_usd"])
    else:
        df["cost_usd"] = df["computed_cost_usd"]

    return df, warnings
