"""Machine-readable JSON output with a stable, documented schema (CI use)."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from ..analyzers.base import Finding
from . import Summary

SCHEMA_VERSION = "0.1"


def to_dict(summary: Summary, findings: list[Finding]) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "pricing_as_of": summary.pricing_as_of,
        "summary": {
            "total_spend_usd": round(summary.total_spend_usd, 6),
            "monthly_spend_usd": round(summary.monthly_spend_usd, 6),
            "recoverable_monthly_usd": round(summary.recoverable_monthly_usd, 6),
            "window_days": summary.window_days,
            "window_start": summary.window_start,
            "window_end": summary.window_end,
            "caller_count": summary.caller_count,
            "model_count": summary.model_count,
        },
        "warnings": summary.warnings,
        "findings": [
            {
                **dataclasses.asdict(f),
                "est_monthly_waste_usd": (
                    round(f.est_monthly_waste_usd, 6)
                    if f.est_monthly_waste_usd is not None
                    else None
                ),
            }
            for f in findings
        ],
    }


def render(summary: Summary, findings: list[Finding], path: Path | None = None) -> str:
    payload = json.dumps(to_dict(summary, findings), indent=2)
    if path is not None:
        Path(path).write_text(payload + "\n")
    return payload
