"""Anthropic Console usage/cost CSV parser (best-effort convenience).

HEADER ASSUMPTIONS (real exports drift -- fix here if yours differ):
  This targets the Console usage/cost CSV export, whose distinctive columns
  are a workspace label plus explicit ``input_tokens`` / ``output_tokens``
  (and often a ``cost_usd`` / ``cost`` column). We map:

    timestamp        <- "usage_date_utc" | "date" | "usage_date"
    caller           <- "workspace" | "workspace_name" | "api_key"  (fallback: "anthropic")
    model            <- "model"
    input_tokens     <- "input_tokens"  (fallback: "uncached_input_tokens")
    output_tokens    <- "output_tokens"
    cost_usd         <- "cost_usd" | "cost" | "amount_usd"  (optional)

If Anthropic changes these headers, update SIGNATURE and the mapping below;
the generic path with --map is always available as a fallback.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..normalize import normalize

# A workspace column alongside token counts identifies an Anthropic export.
_WORKSPACE_KEYS = {"workspace", "workspace_name"}
_TOKEN_KEYS = {"input_tokens", "output_tokens"}


def matches(columns: list[str]) -> bool:
    cols = {c.lower() for c in columns}
    has_workspace = bool(_WORKSPACE_KEYS & cols)
    return has_workspace and _TOKEN_KEYS.issubset(cols)


def _first_present(cols: dict[str, str], *candidates: str) -> str | None:
    for c in candidates:
        if c in cols:
            return cols[c]
    return None


def load(path: Path, tz: str = "UTC") -> pd.DataFrame:
    raw = pd.read_csv(path)
    cols = {c.lower(): c for c in raw.columns}

    ts = _first_present(cols, "usage_date_utc", "date", "usage_date", "timestamp")
    model = _first_present(cols, "model")
    inp = _first_present(cols, "input_tokens", "uncached_input_tokens")
    out = _first_present(cols, "output_tokens")
    caller = _first_present(cols, "workspace", "workspace_name", "api_key")
    cost = _first_present(cols, "cost_usd", "cost", "amount_usd")

    mapped = pd.DataFrame(
        {
            "timestamp": raw[ts],
            "model": raw[model],
            "input_tokens": raw[inp],
            "output_tokens": raw[out],
        }
    )
    mapped["caller"] = raw[caller] if caller else "anthropic"
    if cost:
        mapped["cost_usd"] = raw[cost]
    return normalize(mapped, tz=tz)
