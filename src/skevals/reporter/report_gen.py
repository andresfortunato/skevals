"""Report generation: aggregate judgments into a comparison report."""

import statistics

from skevals.llm.client import structured_call
from skevals.models.judge import ScenarioJudgment
from skevals.models.report import (
    ComparisonReport,
    ConditionSummary,
    ContextHealthWarning,
    DimensionComparison,
    StatSummary,
)
from skevals.models.session import SessionResult


def _stat(values: list[float]) -> StatSummary:
    """Compute descriptive statistics."""
    if not values:
        return StatSummary(mean=0, stddev=0, min=0, max=0)
    return StatSummary(
        mean=statistics.mean(values),
        stddev=statistics.stdev(values) if len(values) > 1 else 0.0,
        min=min(values),
        max=max(values),
    )


def _condition_summary(
    condition: str, results: list[SessionResult], overall_scores: list[float]
) -> ConditionSummary:
    return ConditionSummary(
        condition=condition,
        overall_score=_stat(overall_scores),
        total_cost_usd=_stat([r.total_cost_usd for r in results]),
        total_duration_ms=_stat([float(r.total_duration_ms) for r in results]),
        input_tokens=_stat([float(r.total_usage.input_tokens) for r in results]),
        output_tokens=_stat([float(r.total_usage.output_tokens) for r in results]),
    )


def _detect_context_warnings(
    control_results: list[SessionResult],
    treatment_results: list[SessionResult],
) -> list[ContextHealthWarning]:
    """Detect context pressure indicators."""
    warnings: list[ContextHealthWarning] = []

    # Average skill overhead
    overheads = [
        r.skill_overhead_ratio for r in treatment_results
        if r.skill_overhead_ratio is not None
    ]
    if overheads:
        avg_overhead = statistics.mean(overheads)
        if avg_overhead > 0.30:
            warnings.append(ContextHealthWarning(
                indicator="skill_overhead_ratio",
                value=avg_overhead,
                threshold=0.30,
                recommendation=(
                    f"Skill consumes {avg_overhead:.0%} of input tokens on average. "
                    "Consider making SKILL.md more concise."
                ),
            ))

    # Reference load ratio
    for r in treatment_results:
        if r.reference_files_available > 0:
            ratio = r.reference_files_loaded / r.reference_files_available
            if ratio < 0.25:
                warnings.append(ContextHealthWarning(
                    indicator="reference_load_ratio",
                    value=ratio,
                    threshold=0.25,
                    recommendation=(
                        f"Only {r.reference_files_loaded}/{r.reference_files_available} "
                        "reference files were loaded. Consider removing unused references."
                    ),
                ))
                break  # One warning is enough

    # Output length comparison
    ctrl_output_tokens = [r.total_usage.output_tokens for r in control_results]
    treat_output_tokens = [r.total_usage.output_tokens for r in treatment_results]
    if ctrl_output_tokens and treat_output_tokens:
        ctrl_avg = statistics.mean(ctrl_output_tokens)
        treat_avg = statistics.mean(treat_output_tokens)
        if ctrl_avg > 0 and treat_avg < ctrl_avg * 0.80:
            warnings.append(ContextHealthWarning(
                indicator="output_truncation",
                value=treat_avg / ctrl_avg if ctrl_avg > 0 else 0,
                threshold=0.80,
                recommendation=(
                    "Treatment outputs are significantly shorter than control. "
                    "The skill may be crowding out working space."
                ),
            ))

    # Markdown-to-code ratio comparison
    ctrl_compositions = [r.output_composition for r in control_results if r.output_composition]
    treat_compositions = [r.output_composition for r in treatment_results if r.output_composition]
    if ctrl_compositions and treat_compositions:
        ctrl_ratio = _prose_ratio(ctrl_compositions)
        treat_ratio = _prose_ratio(treat_compositions)
        if treat_ratio > ctrl_ratio * 1.5 and treat_ratio > 0.6:
            warnings.append(ContextHealthWarning(
                indicator="prose_heavy_output",
                value=treat_ratio,
                threshold=ctrl_ratio * 1.5,
                recommendation=(
                    f"Treatment output is {treat_ratio:.0%} prose vs "
                    f"{ctrl_ratio:.0%} for control. Skill may cause over-explaining."
                ),
            ))

    return warnings


def _prose_ratio(compositions: list[dict[str, int]]) -> float:
    total_prose = sum(c.get("prose_lines", 0) for c in compositions)
    total_code = sum(c.get("code_lines", 0) for c in compositions)
    total = total_prose + total_code
    return total_prose / total if total > 0 else 0.0


def generate_report(
    judgments: list[ScenarioJudgment],
    control_results: list[SessionResult],
    treatment_results: list[SessionResult],
    skill_name: str,
    model: str = "sonnet",
) -> ComparisonReport:
    """Aggregate judgments and results into a final comparison report."""
    # Collect per-condition scores
    ctrl_scores = [j.control_rubric.weighted_overall for j in judgments]
    treat_scores = [j.treatment_rubric.weighted_overall for j in judgments]

    # Pairwise win counts
    wins = {"control": 0, "treatment": 0, "tie": 0}
    for j in judgments:
        wins[j.pairwise.winner] += 1

    # Per-dimension comparisons
    dimension_scores: dict[str, dict[str, list[float]]] = {}
    dimension_names: dict[str, str] = {}
    for j in judgments:
        for ds in j.control_rubric.scores:
            dimension_scores.setdefault(ds.dimension_id, {"control": [], "treatment": []})
            dimension_scores[ds.dimension_id]["control"].append(float(ds.score))
            dimension_names[ds.dimension_id] = ds.dimension_id
        for ds in j.treatment_rubric.scores:
            dimension_scores.setdefault(ds.dimension_id, {"control": [], "treatment": []})
            dimension_scores[ds.dimension_id]["treatment"].append(float(ds.score))

    dim_comparisons = [
        DimensionComparison(
            dimension_id=dim_id,
            dimension_name=dimension_names.get(dim_id, dim_id),
            control_stats=_stat(scores["control"]),
            treatment_stats=_stat(scores["treatment"]),
            delta=statistics.mean(scores["treatment"]) - statistics.mean(scores["control"])
            if scores["control"] and scores["treatment"] else 0.0,
        )
        for dim_id, scores in dimension_scores.items()
    ]

    # Context health
    context_warnings = _detect_context_warnings(control_results, treatment_results)

    # Build report
    report = ComparisonReport(
        skill_name=skill_name,
        num_scenarios=len(judgments),
        control_summary=_condition_summary("control", control_results, ctrl_scores),
        treatment_summary=_condition_summary("treatment", treatment_results, treat_scores),
        dimension_comparisons=dim_comparisons,
        pairwise_wins=wins,
        context_health_warnings=context_warnings,
    )

    # Generate verdict via LLM
    verdict_prompt = f"""Based on this A/B evaluation of the "{skill_name}" skill, write a brief verdict paragraph (3-5 sentences).

Results summary:
- Scenarios tested: {len(judgments)}
- Control avg score: {statistics.mean(ctrl_scores):.2f} vs Treatment avg: {statistics.mean(treat_scores):.2f}
- Pairwise: control won {wins['control']}, treatment won {wins['treatment']}, tied {wins['tie']}
- Context warnings: {len(context_warnings)}

Per-dimension deltas:
{chr(10).join(f'- {dc.dimension_name}: {dc.delta:+.2f}' for dc in dim_comparisons)}

Write a concise, honest assessment of whether the skill improves Claude's output and whether the cost/context overhead is justified.
"""

    from pydantic import BaseModel as BM

    class VerdictOutput(BM):
        verdict: str

    verdict_result = structured_call(verdict_prompt, VerdictOutput, model=model)
    report.verdict = verdict_result.verdict

    return report


def render_markdown(report: ComparisonReport) -> str:
    """Render a ComparisonReport as markdown."""
    lines = [
        f"# Skill Evaluation Report: {report.skill_name}",
        "",
        f"**Scenarios tested:** {report.num_scenarios}",
        "",
        "## Overall Scores",
        "",
        "| Metric | Control | Treatment | Delta |",
        "|--------|---------|-----------|-------|",
        f"| Overall Score | {report.control_summary.overall_score.mean:.2f} | {report.treatment_summary.overall_score.mean:.2f} | {report.treatment_summary.overall_score.mean - report.control_summary.overall_score.mean:+.2f} |",
        f"| Cost (USD) | ${report.control_summary.total_cost_usd.mean:.4f} | ${report.treatment_summary.total_cost_usd.mean:.4f} | ${report.treatment_summary.total_cost_usd.mean - report.control_summary.total_cost_usd.mean:+.4f} |",
        f"| Duration (ms) | {report.control_summary.total_duration_ms.mean:.0f} | {report.treatment_summary.total_duration_ms.mean:.0f} | {report.treatment_summary.total_duration_ms.mean - report.control_summary.total_duration_ms.mean:+.0f} |",
        f"| Input Tokens | {report.control_summary.input_tokens.mean:.0f} | {report.treatment_summary.input_tokens.mean:.0f} | {report.treatment_summary.input_tokens.mean - report.control_summary.input_tokens.mean:+.0f} |",
        "",
        "## Pairwise Results",
        "",
        f"- Treatment wins: **{report.pairwise_wins.get('treatment', 0)}**",
        f"- Control wins: **{report.pairwise_wins.get('control', 0)}**",
        f"- Ties: **{report.pairwise_wins.get('tie', 0)}**",
        "",
        "## Per-Dimension Comparison",
        "",
        "| Dimension | Control | Treatment | Delta |",
        "|-----------|---------|-----------|-------|",
    ]

    for dc in report.dimension_comparisons:
        lines.append(
            f"| {dc.dimension_name} | {dc.control_stats.mean:.2f} | {dc.treatment_stats.mean:.2f} | {dc.delta:+.2f} |"
        )

    if report.context_health_warnings:
        lines.extend([
            "",
            "## Context Health",
            "",
        ])
        for w in report.context_health_warnings:
            lines.append(f"- **{w.indicator}**: {w.recommendation}")

    lines.extend([
        "",
        "## Verdict",
        "",
        report.verdict,
        "",
    ])

    return "\n".join(lines)
