"""OpenAI usage-export CSV parser (best-effort convenience).

HEADER ASSUMPTIONS (real exports drift -- fix here if yours differ):
  This targets the per-request usage CSV exported from the OpenAI platform
  usage page, whose distinctive columns are the token totals
  ``n_context_tokens_total`` and ``n_generated_tokens_total``. We map:

    timestamp        <- "timestamp" | "date" | "start_time"
    caller           <- "api_key_name" | "project" | "project_name"  (fallback: "openai")
    model            <- "model"
    input_tokens     <- "n_context_tokens_total"  (fallback: "prompt_tokens")
    output_tokens    <- "n_generated_tokens_total" (fallback: "completion_tokens")

If OpenAI changes these headers, update SIGNATURE and the mapping below; the
generic path with --map is always available as a fallback.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..normalize import normalize

# Columns whose presence identifies an OpenAI usage export.
SIGNATURE = {"n_context_tokens_total", "n_generated_tokens_total"}
SIGNATURE_FALLBACK = {"prompt_tokens", "completion_tokens"}


def matches(columns: list[str]) -> bool:
    cols = {c.lower() for c in columns}
    return SIGNATURE.issubset(cols) or (
        SIGNATURE_FALLBACK.issubset(cols) and "model" in cols and "caller" not in cols
    )


def _first_present(cols: dict[str, str], *candidates: str) -> str | None:
    for c in candidates:
        if c in cols:
            return cols[c]
    return None


def load(path: Path, tz: str = "UTC") -> pd.DataFrame:
    raw = pd.read_csv(path)
    cols = {c.lower(): c for c in raw.columns}

    ts = _first_present(cols, "timestamp", "date", "start_time")
    model = _first_present(cols, "model")
    inp = _first_present(cols, "n_context_tokens_total", "prompt_tokens", "input_tokens")
    out = _first_present(
        cols, "n_generated_tokens_total", "completion_tokens", "output_tokens"
    )
    caller = _first_present(cols, "api_key_name", "project", "project_name")

    mapped = pd.DataFrame(
        {
            "timestamp": raw[ts],
            "model": raw[model],
            "input_tokens": raw[inp],
            "output_tokens": raw[out],
        }
    )
    # OpenAI exports don't carry a use-case label; fall back to a constant so
    # the caller-level analyzers still have something to group on.
    mapped["caller"] = raw[caller] if caller else "openai"
    return normalize(mapped, tz=tz)
