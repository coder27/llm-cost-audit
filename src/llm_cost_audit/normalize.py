"""Canonical data model and normalization of ingested frames.

Every ingestion path produces a raw DataFrame that this module turns into the
single canonical schema the analyzers rely on:

    timestamp (datetime, UTC) | caller (str) | model (str) |
    input_tokens (int) | output_tokens (int) | cost_usd (float, optional) |
    prompt_hash (str, optional)
"""

from __future__ import annotations

import pandas as pd

REQUIRED_COLUMNS = ["timestamp", "caller", "model", "input_tokens", "output_tokens"]
OPTIONAL_COLUMNS = ["cost_usd", "prompt_hash"]
CANONICAL_COLUMNS = REQUIRED_COLUMNS + OPTIONAL_COLUMNS


class IngestionError(ValueError):
    """Raised when a source file can't be mapped to the canonical schema."""


def _example_map_hint(missing: list[str], present: list[str]) -> str:
    """Build a friendly ``--map`` suggestion from what's missing vs present."""
    lines = [
        f"Missing required column(s): {', '.join(missing)}.",
        f"Columns found in the file: {', '.join(present) or '(none)'}.",
        "",
        "If your file uses different names, map them with --map, e.g.:",
        "  llm-cost-audit usage.csv \\",
    ]
    guesses = {
        "caller": ["service", "workflow", "use_case", "app", "team"],
        "timestamp": ["ts", "time", "date", "created_at"],
        "model": ["model_name", "engine", "deployment"],
        "input_tokens": ["prompt_tokens", "input"],
        "output_tokens": ["completion_tokens", "output"],
    }
    present_lower = {c.lower(): c for c in present}
    for canon in missing:
        picked = next(
            (present_lower[g] for g in guesses.get(canon, []) if g in present_lower),
            f"<your-{canon}-column>",
        )
        lines.append(f"    --map {picked}={canon} \\")
    lines[-1] = lines[-1].rstrip(" \\")
    return "\n".join(lines)


def apply_column_map(df: pd.DataFrame, mapping: dict[str, str]) -> pd.DataFrame:
    """Rename columns per a ``{source_name: canonical_name}`` mapping."""
    if not mapping:
        return df
    return df.rename(columns=mapping)


def normalize(df: pd.DataFrame, tz: str = "UTC") -> pd.DataFrame:
    """Validate and coerce a raw frame into the canonical schema.

    ``tz`` is applied to naive timestamps before conversion to UTC.
    """
    present = list(df.columns)
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise IngestionError(_example_map_hint(missing, present))

    out = pd.DataFrame()

    # Timestamps -> tz-aware UTC. Naive values are localized to `tz` first.
    ts = pd.to_datetime(df["timestamp"], errors="coerce", utc=False)
    if ts.isna().all():
        raise IngestionError(
            "Could not parse any values in the 'timestamp' column as dates."
        )
    if getattr(ts.dtype, "tz", None) is None:
        ts = ts.dt.tz_localize(tz, ambiguous="NaT", nonexistent="NaT")
    out["timestamp"] = ts.dt.tz_convert("UTC")

    out["caller"] = df["caller"].astype(str).str.strip()
    out["model"] = df["model"].astype(str).str.strip()
    out["input_tokens"] = (
        pd.to_numeric(df["input_tokens"], errors="coerce").fillna(0).astype("int64")
    )
    out["output_tokens"] = (
        pd.to_numeric(df["output_tokens"], errors="coerce").fillna(0).astype("int64")
    )

    if "cost_usd" in df.columns:
        out["cost_usd"] = pd.to_numeric(df["cost_usd"], errors="coerce")
    if "prompt_hash" in df.columns:
        out["prompt_hash"] = df["prompt_hash"].astype(str)

    out = out.dropna(subset=["timestamp"]).reset_index(drop=True)
    if out.empty:
        raise IngestionError("No usable rows after parsing timestamps.")
    return out.sort_values("timestamp").reset_index(drop=True)
