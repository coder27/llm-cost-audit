"""Ingestion, normalization, format detection, and --map round-trip tests."""

from __future__ import annotations

import pandas as pd
import pytest

from llm_cost_audit import ingest
from llm_cost_audit.ingest import anthropic_export, generic, openai_export
from llm_cost_audit.normalize import CANONICAL_COLUMNS, IngestionError, normalize


def test_generic_fixture_loads_canonical(raw_df):
    for col in ("timestamp", "caller", "model", "input_tokens", "output_tokens"):
        assert col in raw_df.columns
    assert str(raw_df["timestamp"].dt.tz) == "UTC"
    assert raw_df["input_tokens"].dtype.kind == "i"
    assert len(raw_df) > 10_000


def test_fixture_autodetects_as_generic(fixture_path):
    assert ingest.detect_format(fixture_path) == "generic"


def test_map_round_trip(tmp_path):
    """A file with non-canonical headers round-trips via --map."""
    src = tmp_path / "weird.csv"
    pd.DataFrame(
        {
            "ts": ["2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z"],
            "service": ["svc-a", "svc-b"],
            "engine": ["gpt-4o", "gpt-4o"],
            "prompt_tokens": [100, 200],
            "completion_tokens": [10, 20],
        }
    ).to_csv(src, index=False)

    mapping = {
        "ts": "timestamp",
        "service": "caller",
        "engine": "model",
        "prompt_tokens": "input_tokens",
        "completion_tokens": "output_tokens",
    }
    df = generic.load(src, mapping)
    assert list(df["caller"]) == ["svc-a", "svc-b"]
    assert list(df["input_tokens"]) == [100, 200]
    assert str(df["timestamp"].dt.tz) == "UTC"


def test_missing_columns_error_is_helpful():
    bad = pd.DataFrame({"caller": ["x"], "model": ["gpt-4o"]})
    with pytest.raises(IngestionError) as exc:
        normalize(bad)
    msg = str(exc.value)
    assert "Missing required column(s)" in msg
    assert "--map" in msg  # shows an example invocation


def test_naive_timestamp_respects_tz():
    df = normalize(
        pd.DataFrame(
            {
                "timestamp": ["2026-01-01 12:00:00"],
                "caller": ["a"],
                "model": ["gpt-4o"],
                "input_tokens": [1],
                "output_tokens": [1],
            }
        ),
        tz="America/New_York",
    )
    # Noon in New York (EST, -05:00) is 17:00 UTC.
    assert df["timestamp"].iloc[0].hour == 17


def test_openai_detection_and_load(tmp_path):
    src = tmp_path / "openai.csv"
    pd.DataFrame(
        {
            "timestamp": ["2026-01-01T00:00:00Z"],
            "model": ["gpt-4o"],
            "n_context_tokens_total": [500],
            "n_generated_tokens_total": [50],
            "api_key_name": ["proj-x"],
        }
    ).to_csv(src, index=False)

    assert openai_export.matches(list(pd.read_csv(src, nrows=0).columns))
    df, fmt = ingest.load(src)
    assert fmt == "openai"
    assert df["caller"].iloc[0] == "proj-x"
    assert df["input_tokens"].iloc[0] == 500


def test_anthropic_detection_and_load(tmp_path):
    src = tmp_path / "anthropic.csv"
    pd.DataFrame(
        {
            "usage_date_utc": ["2026-01-01"],
            "workspace": ["default"],
            "model": ["claude-sonnet-4-6"],
            "input_tokens": [1000],
            "output_tokens": [200],
            "cost_usd": [0.006],
        }
    ).to_csv(src, index=False)

    assert anthropic_export.matches(list(pd.read_csv(src, nrows=0).columns))
    df, fmt = ingest.load(src)
    assert fmt == "anthropic"
    assert df["caller"].iloc[0] == "default"
    assert "cost_usd" in df.columns


def test_canonical_columns_constant():
    assert CANONICAL_COLUMNS[:5] == [
        "timestamp",
        "caller",
        "model",
        "input_tokens",
        "output_tokens",
    ]
