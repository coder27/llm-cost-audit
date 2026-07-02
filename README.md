# llm-cost-audit

**`llm-cost-audit usage.csv` → "You're wasting ~$2,300/month. Here's exactly where."**

A one-shot command-line auditor for LLM usage logs. It reads a file, finds the
waste, prints a ranked report, and exits. No dashboard, no daemon, no API keys,
no data leaving your machine.

![demo](docs/demo.gif)

<!-- Record this GIF with vhs (https://github.com/charmbracelet/vhs):
     `vhs docs/demo.tape` running `llm-cost-audit tests/fixtures/synthetic_usage.csv`. -->

## Why

You can't fix what you can't attribute. Most teams know their total LLM bill and
almost nothing about *where* it goes. Attribution has to come before
optimization: which workflow, which model, which forgotten cron. This tool does
the attribution and points at the three most common, most recoverable patterns —
so the first optimization you make is the one that actually moves the bill.

## Quickstart

```bash
pip install llm-cost-audit

# Run it against the bundled synthetic dataset:
llm-cost-audit tests/fixtures/synthetic_usage.csv
```

That fixture is 90 days of realistic, seeded usage across ~15 callers with a
few deliberately planted problems — the fastest way to see what the report
looks like before pointing it at your own data.

## Bring your own data

The **generic CSV** path is the first-class citizen. Give it these columns:

| column | type | required | notes |
|---|---|---|---|
| `timestamp` | datetime | yes | any parseable format; UTC assumed for naive values (`--tz` to override) |
| `caller` | string | yes | service / workflow / use-case identifier — the unit of attribution |
| `model` | string | yes | normalized model id, e.g. `claude-sonnet-4-6`, `gpt-4o` |
| `input_tokens` | int | yes | |
| `output_tokens` | int | yes | |
| `cost_usd` | float | no | if absent, computed from `pricing.yaml`; if present, kept — and a >10% divergence from the table is flagged |
| `prompt_hash` | string | no | reserved for a future duplicate-detection analyzer |

Already have logs with different column names? Map them with repeatable
`--map source=canonical` flags:

```bash
llm-cost-audit logs.csv \
  --map service=caller \
  --map ts=timestamp \
  --map prompt_tokens=input_tokens \
  --map completion_tokens=output_tokens \
  --tz America/New_York
```

**Provider exports** are best-effort conveniences, auto-detected by header:

```bash
llm-cost-audit openai_usage.csv        # auto-detected
llm-cost-audit anthropic_cost.csv      # auto-detected
llm-cost-audit weird.csv --format generic --map ...   # force a parser
```

Provider export headers drift; each parser documents its header assumptions at
the top of its module (`src/llm_cost_audit/ingest/`). If yours differ, fix the
parser or fall back to the always-available generic `--map` path.

### Other useful flags

```
--window 30d          restrict to a trailing window (default: whole file)
--min-spend 1.00      ignore callers below this monthly-spend floor (noise gate)
--threshold KEY=VAL   override an analyzer threshold, e.g. dead_days=45 (repeatable)
--config audit.yaml   load thresholds from YAML instead
--json report.json    also write machine-readable JSON (stable schema; CI-friendly)
--html report.html    also write a single self-contained HTML file
```

## What it checks

**1. Dead callers.** Flags callers that look abandoned — a cron nobody reviews.
The signal is flat daily volume (coefficient of variation below 0.05 over a
window of at least 14 days) or a call-count pattern that hasn't changed for more
than `dead_days` (default 30). Severity is high when the caller's monthly spend
tops $100. The estimated waste is that caller's full extrapolated monthly spend —
if it's abandoned, all of it is recoverable.

**2. Over-modeling.** Flags callers running a frontier-tier model on work that
looks small: a median request under 1,500 tokens, or a 90th-percentile output
under 200 tokens (classification-shaped). The estimated waste is the difference
between the current monthly cost and the cost of the same volume on the
`cheaper_alternative` named in `pricing.yaml`, and the recommendation names that
model and the estimated new bill. Always gate the switch on an eval — token size
is a proxy for task difficulty, not a guarantee.

**3. Concentration.** A Pareto view of spend across callers. It reports the top-5
callers by share and flags any single caller above 30% of total spend (high above
50%). This is a *visibility* finding, not a savings claim — the spend may be
entirely justified — but concentrated spend is where an efficiency win, or a
single retry storm, moves the whole bill.

Every dollar figure is extrapolated from the analysis window to 30 days, and each
finding states the window it used.

## What it will never do

These are permanent non-goals, and we're proud of them:

- **No dashboard or web UI.** It prints to your terminal and exits.
- **No live API polling** or provider integrations that call APIs.
- **No background daemon, scheduler, or watch mode.**
- **No auto-remediation.** It tells you where the waste is; you decide what to do.
- **No database and no state between runs.** Every run is a clean read of one file.

It is a scalpel, not a platform. If you want continuous monitoring, this
deliberately isn't it.

## Pricing table

Costs come from a versioned `src/llm_cost_audit/data/pricing.yaml` (per-model
input/output price per million tokens, a tier, and a suggested cheaper
alternative), stamped with a `pricing_as_of` date. Prices drift constantly —
**PRs that correct or extend the table are very welcome.** Update `pricing_as_of`
in the same change. Unknown models are warned about once, excluded from savings
estimates, and still counted in spend totals when a `cost_usd` column was
provided.

## JSON output schema

`--json` emits a stable, documented shape for CI use (`schema_version: "0.1"`):

```json
{
  "schema_version": "0.1",
  "pricing_as_of": "2026-07-01",
  "summary": {
    "total_spend_usd": 0.0, "monthly_spend_usd": 0.0,
    "recoverable_monthly_usd": 0.0, "window_days": 90.0,
    "window_start": "…", "window_end": "…",
    "caller_count": 0, "model_count": 0
  },
  "warnings": ["…"],
  "findings": [
    {
      "analyzer": "dead_callers", "severity": "high", "caller": "…",
      "title": "…", "detail": "…",
      "est_monthly_waste_usd": 0.0, "recommendation": "…"
    }
  ]
}
```

The process always exits 0 in v0.1.

## Roadmap

- **Analyzer #4 — trend anomalies:** catch a caller whose spend suddenly spikes
  (the bundled fixture already plants one for this).
- **Analyzer #5 — duplicate burn:** use `prompt_hash` to find repeated identical
  prompts that should be cached.
- **Bedrock CUR ingestion:** read AWS Cost and Usage Report exports directly.
- **`--fail-over $X`:** a nonzero exit when recoverable spend crosses a threshold,
  for use as a CI gate.

## License

MIT. See [LICENSE](LICENSE).
