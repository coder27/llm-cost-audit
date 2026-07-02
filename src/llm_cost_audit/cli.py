"""llm-cost-audit command-line interface."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pandas as pd
import typer
import yaml
from rich.console import Console

from . import ingest
from .analyzers import AnalyzerConfig, run_all, sort_findings, window_days
from .analyzers.base import monthly
from .normalize import IngestionError
from .pricing import Pricing, compute_costs
from .report import build_summary, html_out, json_out, terminal

app = typer.Typer(
    add_completion=False,
    help="Audit an LLM usage log and print a ranked waste report. One shot: "
    "read a file, analyze it, print, exit. No daemon, no API calls, no state.",
)
err_console = Console(stderr=True)


def _parse_window(window: str | None) -> int | None:
    """Parse '30d' / '6w' / '30' into a day count (None = whole file)."""
    if not window:
        return None
    w = window.strip().lower()
    try:
        if w.endswith("d"):
            return int(w[:-1])
        if w.endswith("w"):
            return int(w[:-1]) * 7
        return int(w)
    except ValueError as exc:
        raise typer.BadParameter(f"Could not parse --window '{window}' (try '30d').") from exc


def _parse_map(pairs: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for pair in pairs or []:
        if "=" not in pair:
            raise typer.BadParameter(f"--map expects source=canonical, got '{pair}'.")
        src, canon = pair.split("=", 1)
        mapping[src.strip()] = canon.strip()
    return mapping


def _build_config(
    config_path: Path | None, thresholds: list[str], min_spend: float
) -> AnalyzerConfig:
    cfg = AnalyzerConfig()
    field_types = {f.name: f.type for f in dataclasses.fields(AnalyzerConfig)}

    def _coerce(key: str, raw: str):
        # dataclass field types resolve to real types at runtime here.
        target = AnalyzerConfig.__dataclass_fields__[key].type
        as_int = target in (int, "int")
        try:
            return int(raw) if as_int else float(raw)
        except ValueError as exc:
            raise typer.BadParameter(f"--threshold {key}: '{raw}' is not a number.") from exc

    if config_path:
        data = yaml.safe_load(Path(config_path).read_text()) or {}
        for key, value in data.items():
            if key not in field_types:
                raise typer.BadParameter(f"Unknown config key '{key}' in {config_path}.")
            setattr(cfg, key, value)

    for item in thresholds or []:
        if "=" not in item:
            raise typer.BadParameter(f"--threshold expects key=value, got '{item}'.")
        key, raw = item.split("=", 1)
        key = key.strip()
        if key not in field_types:
            raise typer.BadParameter(
                f"Unknown threshold '{key}'. Valid keys: {', '.join(sorted(field_types))}."
            )
        setattr(cfg, key, _coerce(key, raw.strip()))

    cfg.min_spend_usd = min_spend
    return cfg


def _apply_window(df: pd.DataFrame, days: int | None) -> pd.DataFrame:
    if days is None:
        return df
    cutoff = df["timestamp"].max() - pd.Timedelta(days=days)
    return df[df["timestamp"] >= cutoff].reset_index(drop=True)


def _apply_min_spend(df: pd.DataFrame, cfg: AnalyzerConfig) -> pd.DataFrame:
    """Drop callers whose extrapolated monthly spend is below the floor."""
    if cfg.min_spend_usd <= 0:
        return df
    by_caller = df.groupby("caller")["cost_usd"].sum(min_count=1).fillna(0.0)
    keep = {
        caller
        for caller, cost in by_caller.items()
        if monthly(float(cost), cfg.window_days) >= cfg.min_spend_usd
    }
    return df[df["caller"].isin(keep)].reset_index(drop=True)


@app.command()
def audit(
    audit_file: Path = typer.Argument(..., help="Path to the usage CSV to audit."),
    fmt: str = typer.Option(
        None, "--format", help="Force a parser: generic | openai | anthropic."
    ),
    map_: list[str] = typer.Option(
        None, "--map", help="Map a source column to a canonical one, e.g. service=caller. Repeatable."
    ),
    tz: str = typer.Option("UTC", "--tz", help="Timezone for naive timestamps."),
    window: str = typer.Option(
        None, "--window", help="Restrict to a trailing window, e.g. 30d (default: whole file)."
    ),
    json_path: Path = typer.Option(None, "--json", help="Also write machine-readable JSON here."),
    html_path: Path = typer.Option(None, "--html", help="Also write a self-contained HTML report here."),
    threshold: list[str] = typer.Option(
        None, "--threshold", help="Override an analyzer threshold, e.g. dead_days=45. Repeatable."
    ),
    config: Path = typer.Option(None, "--config", help="YAML file of analyzer thresholds."),
    min_spend: float = typer.Option(
        1.0, "--min-spend", help="Ignore callers below this monthly-spend floor (USD)."
    ),
    pricing_file: Path = typer.Option(
        None, "--pricing", help="Override the packaged pricing.yaml.", hidden=True
    ),
) -> None:
    """Audit AUDIT_FILE and print a ranked waste report."""
    try:
        window_arg = _parse_window(window)
        column_map = _parse_map(map_)
        pricing = Pricing.load(pricing_file)

        df, resolved_fmt = ingest.load(audit_file, fmt=fmt, column_map=column_map, tz=tz)
        df, cost_warnings = compute_costs(df, pricing)
        df = _apply_window(df, window_arg)

        if df.empty:
            err_console.print("[yellow]No rows in the selected window.[/yellow]")
            raise typer.Exit(code=0)

        cfg = _build_config(config, threshold, min_spend)
        cfg.window_days = window_days(df)
        df = _apply_min_spend(df, cfg)

        findings = sort_findings(run_all(df, pricing, cfg))
        summary = build_summary(
            df, findings, cfg.window_days, pricing.pricing_as_of, cost_warnings
        )

        terminal.render(summary, findings)

        if json_path:
            json_out.render(summary, findings, json_path)
            err_console.print(f"[dim]JSON written to {json_path}[/dim]")
        if html_path:
            html_out.render(summary, findings, html_path)
            err_console.print(f"[dim]HTML written to {html_path}[/dim]")

    except IngestionError as exc:
        err_console.print(f"[red]Could not read the usage file.[/red]\n\n{exc}")
        raise typer.Exit(code=1) from exc

    raise typer.Exit(code=0)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
