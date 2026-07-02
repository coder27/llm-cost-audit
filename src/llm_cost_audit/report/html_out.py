"""Self-contained single-file HTML report (inline CSS, no external assets).

Clean enough to attach to an email to a CFO.
"""

from __future__ import annotations

from html import escape
from pathlib import Path

from ..analyzers.base import Finding
from . import Summary

_SEV_COLOR = {"high": "#c0392b", "medium": "#b7791f", "low": "#2b6cb0"}


def _money(x: float) -> str:
    return f"${x:,.2f}"


def _finding_rows(findings: list[Finding]) -> str:
    rows = []
    for f in findings:
        color = _SEV_COLOR.get(f.severity, "#555")
        waste = _money(f.est_monthly_waste_usd) if f.est_monthly_waste_usd else "—"
        rows.append(
            f"""<tr>
  <td><span class="pill" style="background:{color}">{escape(f.severity.upper())}</span></td>
  <td class="mono">{escape(f.analyzer)}</td>
  <td>{escape(f.caller)}</td>
  <td class="num">{escape(waste)}</td>
  <td>{escape(f.title)}</td>
</tr>"""
        )
    return "\n".join(rows)


def _detail_cards(findings: list[Finding]) -> str:
    cards = []
    for i, f in enumerate(findings, 1):
        color = _SEV_COLOR.get(f.severity, "#555")
        cards.append(
            f"""<div class="card" style="border-left:5px solid {color}">
  <div class="card-head">
    <span class="pill" style="background:{color}">{escape(f.severity.upper())}</span>
    <strong>{i}. {escape(f.title)}</strong>
  </div>
  <p>{escape(f.detail)}</p>
  <p class="rec"><strong>Recommendation:</strong> {escape(f.recommendation)}</p>
</div>"""
        )
    return "\n".join(cards)


def _warnings_block(summary: Summary) -> str:
    if not summary.warnings:
        return ""
    items = "\n".join(f"<li>{escape(w)}</li>" for w in summary.warnings)
    return f'<div class="warnings"><strong>Notes</strong><ul>{items}</ul></div>'


def build_html(summary: Summary, findings: list[Finding]) -> str:
    no_findings = (
        ""
        if findings
        else '<p class="empty">No findings. Nothing obviously wasteful in this window.</p>'
    )
    table = (
        f"""<table>
<thead><tr><th>Severity</th><th>Analyzer</th><th>Caller</th>
<th class="num">Recoverable / mo</th><th>Summary</th></tr></thead>
<tbody>
{_finding_rows(findings)}
</tbody></table>"""
        if findings
        else ""
    )
    details = (
        f'<h2>Details</h2>{_detail_cards(findings)}' if findings else ""
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LLM Cost Audit</title>
<style>
  :root {{ color-scheme: light; }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
         margin: 0; background: #f5f6f8; color: #1a202c; line-height: 1.5; }}
  .wrap {{ max-width: 900px; margin: 0 auto; padding: 32px 20px 64px; }}
  h1 {{ font-size: 26px; margin: 0 0 4px; }}
  .sub {{ color: #718096; font-size: 13px; margin-bottom: 24px; }}
  .cards {{ display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 20px; }}
  .stat {{ flex: 1 1 140px; background: #fff; border: 1px solid #e2e8f0; border-radius: 10px; padding: 14px 16px; }}
  .stat .label {{ color: #718096; font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }}
  .stat .value {{ font-size: 20px; font-weight: 700; margin-top: 4px; }}
  .headline {{ background: #f0fff4; border: 2px solid #38a169; border-radius: 12px;
              text-align: center; padding: 26px; margin: 8px 0 28px; }}
  .headline .label {{ color: #276749; text-transform: uppercase; letter-spacing: .05em; font-size: 13px; }}
  .headline .value {{ font-size: 42px; font-weight: 800; color: #22863a; margin-top: 6px; }}
  .headline .per {{ color: #276749; font-size: 16px; }}
  table {{ width: 100%; border-collapse: collapse; background: #fff; border-radius: 10px;
          overflow: hidden; border: 1px solid #e2e8f0; }}
  th, td {{ text-align: left; padding: 10px 12px; border-bottom: 1px solid #edf2f7; font-size: 14px; vertical-align: top; }}
  th {{ background: #f7fafc; font-size: 12px; text-transform: uppercase; letter-spacing: .03em; color: #4a5568; }}
  td.num, th.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; color: #4a5568; }}
  .pill {{ color: #fff; font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 999px; }}
  h2 {{ margin: 32px 0 12px; font-size: 18px; }}
  .card {{ background: #fff; border: 1px solid #e2e8f0; border-radius: 10px; padding: 16px 18px; margin-bottom: 12px; }}
  .card-head {{ display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }}
  .card p {{ margin: 8px 0 0; }}
  .rec {{ background: #f7fafc; border-radius: 8px; padding: 10px 12px; }}
  .warnings {{ margin-top: 28px; background: #fffaf0; border: 1px solid #f6e05e; border-radius: 10px; padding: 12px 16px; font-size: 13px; }}
  .empty {{ background: #f0fff4; border: 1px solid #9ae6b4; border-radius: 10px; padding: 16px; text-align: center; }}
  .foot {{ margin-top: 40px; color: #a0aec0; font-size: 12px; text-align: center; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>LLM Cost Audit</h1>
  <div class="sub">Window {summary.window_days:.0f} days
    ({escape(summary.window_start[:10])} → {escape(summary.window_end[:10])}) ·
    pricing as of {escape(summary.pricing_as_of)}</div>

  <div class="cards">
    <div class="stat"><div class="label">Spend (window)</div><div class="value">{_money(summary.total_spend_usd)}</div></div>
    <div class="stat"><div class="label">Spend (monthly est.)</div><div class="value">{_money(summary.monthly_spend_usd)}</div></div>
    <div class="stat"><div class="label">Callers</div><div class="value">{summary.caller_count}</div></div>
    <div class="stat"><div class="label">Models</div><div class="value">{summary.model_count}</div></div>
  </div>

  <div class="headline">
    <div class="label">Estimated recoverable spend</div>
    <div class="value">{_money(summary.recoverable_monthly_usd)}<span class="per"> / month</span></div>
  </div>

  {no_findings}
  {table}
  {details}
  {_warnings_block(summary)}

  <div class="foot">Generated by llm-cost-audit · one-shot audit, no data leaves your machine</div>
</div>
</body>
</html>
"""


def render(summary: Summary, findings: list[Finding], path: Path) -> None:
    Path(path).write_text(build_html(summary, findings))
