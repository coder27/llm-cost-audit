"""Analyzer tests: every planted issue is found with the right severity, and
healthy callers produce zero findings (the false-positive guard)."""

from __future__ import annotations

from llm_cost_audit.analyzers import concentration, dead_callers, over_modeling

# Callers the fixture deliberately makes healthy -- these must NEVER be flagged.
HEALTHY = {
    "doc-search",
    "code-review-bot",
    "onboarding-assistant",
    "sentiment-tagger",
    "report-writer",
    "translation-svc",
    "spam-filter",
    "meeting-notes",
    "faq-router",
}


def _by_analyzer(findings, name):
    return [f for f in findings if f.analyzer == name]


def _callers(findings):
    return {f.caller for f in findings}


# --- planted issue #1: dead caller ------------------------------------------
def test_legacy_summarizer_flagged_dead_high(findings):
    dead = _by_analyzer(findings, "dead_callers")
    match = [f for f in dead if f.caller == "legacy-summarizer"]
    assert len(match) == 1
    assert match[0].severity == "high"  # monthly spend > $100
    assert match[0].est_monthly_waste_usd > 100


# --- planted issue #2: over-modeling ----------------------------------------
def test_ticket_classifier_flagged_over_modeled(findings):
    om = _by_analyzer(findings, "over_modeling")
    match = [f for f in om if f.caller == "ticket-classifier"]
    assert len(match) == 1
    # Recommendation must name the concrete cheaper model.
    assert "claude-haiku-4-5" in match[0].recommendation
    assert "eval" in match[0].detail.lower()  # honest caveat present
    assert match[0].est_monthly_waste_usd > 0


# --- planted issue #3: concentration ----------------------------------------
def test_alert_enricher_flagged_concentration_high(findings):
    conc = _by_analyzer(findings, "concentration")
    match = [f for f in conc if f.caller == "alert-enricher"]
    assert len(match) == 1
    assert match[0].severity == "high"  # > 50% of spend
    assert match[0].est_monthly_waste_usd is None  # visibility, not savings


# --- planted issue #4: future-analyzer fixture is INVISIBLE to v0.1 ----------
def test_runaway_batch_produces_no_findings(findings):
    # The 6x final-week spike is for the future trend analyzer; v0.1 must be silent.
    assert "runaway-batch" not in _callers(findings)


# --- false-positive guard ---------------------------------------------------
def test_healthy_callers_have_zero_findings(findings):
    flagged = _callers(findings)
    assert HEALTHY.isdisjoint(flagged), f"false positives: {HEALTHY & flagged}"


def test_only_expected_callers_flagged(findings):
    assert _callers(findings) == {
        "legacy-summarizer",
        "ticket-classifier",
        "alert-enricher",
    }


# --- direct analyzer behavior -----------------------------------------------
def test_dead_caller_not_triggered_on_noisy_caller(analyzed_df, pricing, config):
    out = dead_callers.run(analyzed_df, pricing, config)
    assert "alert-enricher" not in {f.caller for f in out}


def test_concentration_thresholds(analyzed_df, pricing, config):
    out = concentration.run(analyzed_df, pricing, config)
    # Only alert-enricher clears the 30% bar in this dataset.
    assert {f.caller for f in out} == {"alert-enricher"}


def test_over_modeling_ignores_non_frontier(analyzed_df, pricing, config):
    out = over_modeling.run(analyzed_df, pricing, config)
    # legacy-summarizer runs on gpt-4o with large payloads -> not over-modeled.
    assert "legacy-summarizer" not in {f.caller for f in out}


def test_threshold_override_changes_results(analyzed_df, pricing, config):
    import dataclasses

    # Drop the concentration bar to 10% -> more callers flagged.
    loose = dataclasses.replace(config, concentration_medium_pct=10.0)
    out = concentration.run(analyzed_df, pricing, loose)
    assert len(out) >= 1
    assert len(out) > len(concentration.run(analyzed_df, pricing, config))
