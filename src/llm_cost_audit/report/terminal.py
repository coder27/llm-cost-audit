"""Rich terminal report -- the default output, and the screenshot moment."""

from __future__ import annotations

from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ..analyzers.base import Finding
from . import Summary

SEVERITY_STYLE = {"high": "bold red", "medium": "bold yellow", "low": "cyan"}
SEVERITY_LABEL = {"high": "HIGH", "medium": "MED", "low": "LOW"}


def _money(x: float) -> str:
    return f"${x:,.2f}"


def render(summary: Summary, findings: list[Finding], console: Console | None = None) -> None:
    console = console or Console()

    # --- header -------------------------------------------------------------
    header = Table.grid(padding=(0, 3))
    header.add_column(justify="right", style="dim")
    header.add_column(style="bold")
    header.add_row("Spend (window)", f"{_money(summary.total_spend_usd)}")
    header.add_row("Spend (monthly est.)", f"{_money(summary.monthly_spend_usd)}")
    header.add_row(
        "Window",
        f"{summary.window_days:.0f} days  "
        f"({summary.window_start[:10]} → {summary.window_end[:10]})",
    )
    header.add_row("Callers", str(summary.caller_count))
    header.add_row("Models", str(summary.model_count))
    console.print(
        Panel(
            header,
            title="[bold]llm-cost-audit[/bold]",
            subtitle=f"pricing as of {summary.pricing_as_of}",
            border_style="blue",
            box=box.ROUNDED,
        )
    )

    # --- the headline number ------------------------------------------------
    big = Text(justify="center")
    big.append("Estimated recoverable spend\n", style="dim")
    big.append(f"{_money(summary.recoverable_monthly_usd)}", style="bold green")
    big.append(" / month", style="green")
    console.print(
        Panel(
            big,
            border_style="green",
            box=box.DOUBLE,
            padding=(1, 4),
        )
    )

    if not findings:
        console.print(
            Panel(
                Text("No findings. Nothing obviously wasteful in this window.",
                     justify="center"),
                border_style="green",
                box=box.ROUNDED,
            )
        )
        _print_warnings(console, summary)
        return

    # --- findings table -----------------------------------------------------
    table = Table(
        title="Findings (ranked by recoverable spend)",
        box=box.SIMPLE_HEAVY,
        expand=True,
        title_style="bold",
    )
    table.add_column("Sev", justify="center", no_wrap=True)
    table.add_column("Analyzer", style="dim", no_wrap=True)
    table.add_column("Caller", no_wrap=True)
    table.add_column("Recoverable/mo", justify="right", no_wrap=True)
    table.add_column("Summary", ratio=1)

    for f in findings:
        style = SEVERITY_STYLE.get(f.severity, "white")
        waste = _money(f.est_monthly_waste_usd) if f.est_monthly_waste_usd else "—"
        table.add_row(
            Text(SEVERITY_LABEL.get(f.severity, f.severity), style=style),
            f.analyzer,
            f.caller,
            Text(waste, style="green" if f.est_monthly_waste_usd else "dim"),
            f.title,
        )
    console.print(table)

    # --- per-finding detail -------------------------------------------------
    console.print()
    console.print(Text("Details", style="bold underline"))
    for i, f in enumerate(findings, 1):
        style = SEVERITY_STYLE.get(f.severity, "white")
        body = Group(
            Text(f.detail),
            Text(""),
            Text.assemble(("→ ", style), ("Recommendation: ", "bold"), f.recommendation),
        )
        console.print(
            Panel(
                body,
                title=Text.assemble(
                    (f"{i}. [{SEVERITY_LABEL.get(f.severity, f.severity)}] ", style),
                    (f.title, "bold"),
                ),
                border_style=style.split()[-1],
                box=box.ROUNDED,
                padding=(1, 2),
            )
        )

    _print_warnings(console, summary)


def _print_warnings(console: Console, summary: Summary) -> None:
    for w in summary.warnings:
        console.print(Text.assemble(("⚠  ", "yellow"), (w, "dim")))
