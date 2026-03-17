"""Tests for the reporter."""

from skevals.models.report import (
    ComparisonReport,
    ConditionSummary,
    ContextHealthWarning,
    DimensionComparison,
    StatSummary,
)
from skevals.reporter.report_gen import render_markdown


def _make_stat(mean: float) -> StatSummary:
    return StatSummary(mean=mean, stddev=0.1, min=mean - 0.5, max=mean + 0.5)


def test_render_markdown() -> None:
    """render_markdown produces valid markdown with tables."""
    report = ComparisonReport(
        skill_name="test-skill",
        num_scenarios=3,
        control_summary=ConditionSummary(
            condition="control",
            overall_score=_make_stat(3.0),
            total_cost_usd=_make_stat(0.01),
            total_duration_ms=_make_stat(5000),
            input_tokens=_make_stat(1000),
            output_tokens=_make_stat(500),
        ),
        treatment_summary=ConditionSummary(
            condition="treatment",
            overall_score=_make_stat(4.0),
            total_cost_usd=_make_stat(0.015),
            total_duration_ms=_make_stat(6000),
            input_tokens=_make_stat(1500),
            output_tokens=_make_stat(600),
        ),
        dimension_comparisons=[
            DimensionComparison(
                dimension_id="quality",
                dimension_name="Code Quality",
                control_stats=_make_stat(3.0),
                treatment_stats=_make_stat(4.0),
                delta=1.0,
            ),
        ],
        pairwise_wins={"control": 1, "treatment": 2, "tie": 0},
        context_health_warnings=[
            ContextHealthWarning(
                indicator="skill_overhead_ratio",
                value=0.35,
                threshold=0.30,
                recommendation="Skill consumes 35% of input tokens.",
            ),
        ],
        verdict="The skill improves code quality meaningfully.",
    )

    md = render_markdown(report)

    assert "# Skill Evaluation Report: test-skill" in md
    assert "Control" in md
    assert "Treatment" in md
    assert "Code Quality" in md
    assert "Context Health" in md
    assert "skill_overhead_ratio" in md
    assert "Verdict" in md
