"""Ingestion dispatch: format auto-detection with an explicit override."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..normalize import IngestionError
from . import anthropic_export, generic, openai_export

FORMATS = ("generic", "openai", "anthropic")


def detect_format(path: Path) -> str:
    """Inspect the header row and guess the source format."""
    try:
        header = pd.read_csv(path, nrows=0)
    except Exception as exc:  # noqa: BLE001 - surface a friendly message
        raise IngestionError(f"Could not read '{path}': {exc}") from exc
    columns = list(header.columns)
    if openai_export.matches(columns):
        return "openai"
    if anthropic_export.matches(columns):
        return "anthropic"
    return "generic"


def load(
    path: Path,
    fmt: str | None = None,
    column_map: dict[str, str] | None = None,
    tz: str = "UTC",
) -> tuple[pd.DataFrame, str]:
    """Load ``path`` into the canonical schema.

    Returns ``(dataframe, resolved_format)``. ``fmt`` forces a parser; when
    omitted the format is auto-detected from the header.
    """
    path = Path(path)
    if not path.exists():
        raise IngestionError(f"File not found: {path}")

    resolved = fmt or detect_format(path)
    if resolved == "openai":
        return openai_export.load(path, tz=tz), resolved
    if resolved == "anthropic":
        return anthropic_export.load(path, tz=tz), resolved
    if resolved == "generic":
        return generic.load(path, column_map or {}, tz=tz), resolved
    raise IngestionError(f"Unknown format '{resolved}'. Choose one of: {', '.join(FORMATS)}")
