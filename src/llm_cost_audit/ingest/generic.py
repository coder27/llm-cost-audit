"""Generic CSV ingestion -- the tier-1, first-class path.

Expects the canonical columns (timestamp, caller, model, input_tokens,
output_tokens; optional cost_usd, prompt_hash). Arbitrary logs are adapted
with repeatable ``--map source=canonical`` flags. Everything else in the
project is built on top of what this produces.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..normalize import apply_column_map, normalize


def load(path: Path, column_map: dict[str, str], tz: str = "UTC") -> pd.DataFrame:
    raw = pd.read_csv(path)
    raw = apply_column_map(raw, column_map)
    return normalize(raw, tz=tz)
