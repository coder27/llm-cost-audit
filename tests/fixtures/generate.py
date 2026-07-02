"""Deterministic synthetic LLM-usage generator.

Produces ``synthetic_usage.csv``: 90 days of usage across ~15 callers with
realistic daily patterns and noise. The dataset deliberately plants a known
set of issues so the analyzers and their tests have exact, hand-checkable
ground truth. Run it with::

    python tests/fixtures/generate.py

It is seeded, so the output is byte-for-byte reproducible.

Planted ground truth (see individual caller comments below):
  1. legacy-summarizer  -> dead caller, HIGH severity (flat 240 calls/day)
  2. ticket-classifier  -> over-modeled (frontier model, tiny payloads)
  3. alert-enricher     -> concentration hit (~55% of total spend)
  4. runaway-batch      -> 6x cost spike in the final week (fixture for the
                           future trend-anomaly analyzer #4 -- INVISIBLE to
                           the v0.1 analyzers on purpose)
  5. six healthy callers that must produce ZERO findings (false-positive guard)
"""

from __future__ import annotations

import csv
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

# --- reproducibility ---------------------------------------------------------
SEED = 20260703
random.seed(SEED)

# --- analysis window ---------------------------------------------------------
DAYS = 90
# Fix "now" so timestamps are deterministic (no wall-clock calls).
END = datetime(2026, 7, 1, tzinfo=UTC)
START = END - timedelta(days=DAYS)

OUT_PATH = Path(__file__).with_name("synthetic_usage.csv")


def jitter(base: float, frac: float) -> float:
    """Return ``base`` scaled by +/- ``frac`` uniform noise."""
    return base * (1.0 + random.uniform(-frac, frac))


def spread_within_day(day: datetime, n: int) -> list[datetime]:
    """Spread ``n`` calls across a UTC day at pseudo-random second offsets."""
    out = []
    for _ in range(n):
        secs = random.randint(0, 86_399)
        out.append(day + timedelta(seconds=secs))
    return out


Row = tuple[datetime, str, str, int, int]  # ts, caller, model, in_tok, out_tok


def gen_caller(
    caller: str,
    model: str,
    days_active: range,
    calls_per_day,
    in_tok,
    out_tok,
) -> list[Row]:
    """Generate rows for one caller.

    ``calls_per_day``/``in_tok``/``out_tok`` may each be an int (fixed) or a
    zero-arg callable returning an int (per-call / per-day sampling).
    """
    rows: list[Row] = []
    for d in days_active:
        day = START + timedelta(days=d)
        n = calls_per_day() if callable(calls_per_day) else int(calls_per_day)
        for ts in spread_within_day(day, n):
            it = in_tok() if callable(in_tok) else int(in_tok)
            ot = out_tok() if callable(out_tok) else int(out_tok)
            rows.append((ts, caller, model, it, ot))
    return rows


def build_rows() -> list[Row]:
    rows: list[Row] = []
    full = range(DAYS)

    # -- 1. legacy-summarizer: DEAD caller ------------------------------------
    # Perfectly flat 240 calls/day on gpt-4o for the whole 90 days. Zero
    # variation -> coefficient of variation of daily counts is 0 -> tripped as
    # a robotic/abandoned cron. Payloads are large enough that it is NOT
    # over-modeled, isolating the dead-caller signal.
    rows += gen_caller(
        "legacy-summarizer",
        "gpt-4o",
        full,
        calls_per_day=240,
        in_tok=lambda: random.randint(3800, 4200),
        out_tok=lambda: random.randint(700, 900),
    )

    # -- 2. ticket-classifier: OVER-MODELED -----------------------------------
    # High volume on a frontier model (claude-opus-4-6) doing classification:
    # median total tokens ~600, p90 output ~80. Healthy day-to-day variance so
    # it does NOT also trip the dead-caller analyzer.
    rows += gen_caller(
        "ticket-classifier",
        "claude-opus-4-6",
        full,
        calls_per_day=lambda: random.randint(90, 130),
        in_tok=lambda: random.randint(480, 540),
        out_tok=lambda: random.randint(40, 90),
    )

    # -- 3. alert-enricher: CONCENTRATION -------------------------------------
    # Deliberately the whale: ~55% of total spend. Big frontier calls, high
    # volume. Large payloads so it is not over-modeled; noisy so not dead.
    rows += gen_caller(
        "alert-enricher",
        "claude-sonnet-4-6",
        full,
        # Wide day-to-day variance -- a live, human-driven workload, NOT a
        # flat cron. Mean stays ~170/day so its ~55% spend share holds, but the
        # noise keeps it clear of the dead-caller analyzer.
        calls_per_day=lambda: random.randint(80, 260),
        in_tok=lambda: random.randint(9000, 11000),
        out_tok=lambda: random.randint(1800, 2200),
    )

    # -- 4. runaway-batch: FUTURE analyzer #4 fixture --------------------------
    # Steady low spend for 83 days then a 6x cost spike in the final week.
    # v0.1 has no trend/anomaly analyzer, so this MUST produce zero findings
    # today. It exists so analyzer #4 (trend anomalies) has ground truth.
    rows += gen_caller(
        "runaway-batch",
        "gpt-4o",
        range(0, DAYS - 7),
        calls_per_day=lambda: random.randint(9, 11),
        in_tok=lambda: random.randint(2000, 2400),
        out_tok=lambda: random.randint(400, 600),
    )
    rows += gen_caller(
        "runaway-batch",
        "gpt-4o",
        range(DAYS - 7, DAYS),
        calls_per_day=lambda: random.randint(56, 64),  # ~6x volume
        in_tok=lambda: random.randint(2000, 2400),
        out_tok=lambda: random.randint(400, 600),
    )

    # -- 5. healthy callers: FALSE-POSITIVE GUARD -----------------------------
    # Six well-behaved callers. Each must yield ZERO findings:
    #  * noisy volume (CV well above the dead-caller threshold)
    #  * mid/small-tier models, or frontier with genuinely large payloads
    #  * none exceeds 30% of total spend
    rows += gen_caller(
        "doc-search",
        "gpt-4o-mini",
        full,
        calls_per_day=lambda: random.randint(40, 200),
        in_tok=lambda: random.randint(1200, 3000),
        out_tok=lambda: random.randint(200, 600),
    )
    rows += gen_caller(
        "code-review-bot",
        "claude-sonnet-4-6",
        full,
        calls_per_day=lambda: random.randint(5, 40),
        in_tok=lambda: random.randint(6000, 20000),
        out_tok=lambda: random.randint(1500, 4000),
    )
    rows += gen_caller(
        "onboarding-assistant",
        "gpt-4o",
        full,
        calls_per_day=lambda: random.randint(3, 30),
        in_tok=lambda: random.randint(3000, 9000),
        out_tok=lambda: random.randint(800, 2500),
    )
    rows += gen_caller(
        "sentiment-tagger",
        "claude-haiku-4-5",
        full,
        calls_per_day=lambda: random.randint(30, 150),
        in_tok=lambda: random.randint(400, 1200),
        out_tok=lambda: random.randint(20, 120),
    )
    rows += gen_caller(
        "report-writer",
        "gemini-2.5-pro",
        full,
        calls_per_day=lambda: random.randint(2, 15),
        in_tok=lambda: random.randint(8000, 30000),
        out_tok=lambda: random.randint(2000, 6000),
    )
    rows += gen_caller(
        "translation-svc",
        "gpt-4o-mini",
        full,
        calls_per_day=lambda: random.randint(20, 160),
        in_tok=lambda: random.randint(500, 2500),
        out_tok=lambda: random.randint(400, 2000),
    )

    # A couple more small healthy callers to reach ~15 total and add texture.
    rows += gen_caller(
        "spam-filter",
        "gpt-4o-mini",
        full,
        calls_per_day=lambda: random.randint(50, 250),
        in_tok=lambda: random.randint(300, 900),
        out_tok=lambda: random.randint(5, 40),
    )
    rows += gen_caller(
        "meeting-notes",
        "claude-haiku-4-5",
        full,
        calls_per_day=lambda: random.randint(2, 20),
        in_tok=lambda: random.randint(4000, 12000),
        out_tok=lambda: random.randint(600, 2000),
    )
    rows += gen_caller(
        "faq-router",
        "gemini-2.5-flash",
        full,
        calls_per_day=lambda: random.randint(30, 180),
        in_tok=lambda: random.randint(200, 800),
        out_tok=lambda: random.randint(10, 60),
    )

    return rows


def main() -> None:
    rows = build_rows()
    rows.sort(key=lambda r: r[0])  # chronological
    with OUT_PATH.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "caller", "model", "input_tokens", "output_tokens"])
        for ts, caller, model, it, ot in rows:
            w.writerow([ts.isoformat(), caller, model, it, ot])
    print(f"wrote {len(rows):,} rows across 90 days -> {OUT_PATH}")


if __name__ == "__main__":
    main()
