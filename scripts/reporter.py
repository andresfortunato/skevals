"""Report generation: aggregate judgments into a comparison report.

Computes statistics, detects context health issues, generates verdict
via LLM, and renders a markdown report.
"""

from __future__ import annotations

import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(__file__))

from backend import structured_call
from schemas import VERDICT_SCHEMA


# ---------------------------------------------------------------------------
# Statistics helpers
# ---------------------------------------------------------------------------

def _stat(values: list[float]) -> dict:
    """Compute descriptive statistics."""
    if not values:
        return {"mean": 0.0, "stddev": 0.0, "min": 0.0, "max": 0.0}
    return {
        "mean": statistics.mean(values),
        "stddev": statistics.stdev(values) if len(values) > 1 else 0.0,
        "min": min(values),
        "max": max(values),
    }


def _condition_summary(
    condition: str, results: list[dict], overall_scores: list[float]
) -> dict:
    return {
        "condition": condition,
        "overall_score": _stat(overall_scores),
        "total_cost_usd": _stat([r["total_cost_usd"] for r in results]),
        "total_duration_ms": _stat([float(r["total_duration_ms"]) for r in results]),
        "input_tokens": _stat([float(r["total_usage"]["input_tokens"]) for r in results]),
        "output_tokens": _stat([float(r["total_usage"]["output_tokens"]) for r in results]),
    }


# ---------------------------------------------------------------------------
# Context health detection
# ---------------------------------------------------------------------------

def _detect_context_warnings(
    control_results: list[dict],
    treatment_results: list[dict],
) -> list[dict]:
    """Detect context pressure indicators."""
    warnings: list[dict] = []

    # Average skill overhead
    overheads = [
        r["skill_overhead_ratio"] for r in treatment_results
        if r.get("skill_overhead_ratio") is not None
    ]
    if overheads:
        avg_overhead = statistics.mean(overheads)
        if avg_overhead > 0.30:
            warnings.append({
                "indicator": "skill_overhead_ratio",
                "value": avg_overhead,
                "threshold": 0.30,
                "recommendation": (
                    f"Skill consumes {avg_overhead:.0%} of input tokens on average. "
                    "Consider making SKILL.md more concise."
                ),
            })

    # Reference load ratio
    for r in treatment_results:
        avail = r.get("reference_files_available", 0)
        if avail > 0:
            ratio = r.get("reference_files_loaded", 0) / avail
            if ratio < 0.25:
                warnings.append({
                    "indicator": "reference_load_ratio",
                    "value": ratio,
                    "threshold": 0.25,
                    "recommendation": (
                        f"Only {r.get('reference_files_loaded', 0)}/{avail} "
                        "reference files were loaded. Consider removing unused references."
                    ),
                })
                break

    # Output length comparison
    ctrl_output = [r["total_usage"]["output_tokens"] for r in control_results]
    treat_output = [r["total_usage"]["output_tokens"] for r in treatment_results]
    if ctrl_output and treat_output:
        ctrl_avg = statistics.mean(ctrl_output)
        treat_avg = statistics.mean(treat_output)
        if ctrl_avg > 0 and treat_avg < ctrl_avg * 0.80:
            warnings.append({
                "indicator": "output_truncation",
                "value": treat_avg / ctrl_avg if ctrl_avg > 0 else 0,
                "threshold": 0.80,
                "recommendation": (
                    "Treatment outputs are significantly shorter than control. "
                    "The skill may be crowding out working space."
                ),
            })

    # Prose-heavy output
    ctrl_comps = [r["output_composition"] for r in control_results if r.get("output_composition")]
    treat_comps = [r["output_composition"] for r in treatment_results if r.get("output_composition")]
    if ctrl_comps and treat_comps:
        ctrl_ratio = _prose_ratio(ctrl_comps)
        treat_ratio = _prose_ratio(treat_comps)
        if treat_ratio > ctrl_ratio * 1.5 and treat_ratio > 0.6:
            warnings.append({
                "indicator": "prose_heavy_output",
                "value": treat_ratio,
                "threshold": ctrl_ratio * 1.5,
                "recommendation": (
                    f"Treatment output is {treat_ratio:.0%} prose vs "
                    f"{ctrl_ratio:.0%} for control. Skill may cause over-explaining."
                ),
            })

    return warnings


def _prose_ratio(compositions: list[dict]) -> float:
    total_prose = sum(c.get("prose_lines", 0) for c in compositions)
    total_code = sum(c.get("code_lines", 0) for c in compositions)
    total = total_prose + total_code
    return total_prose / total if total > 0 else 0.0


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report(
    judgments: list[dict],
    control_results: list[dict],
    treatment_results: list[dict],
    skill_name: str,
    model: str = "sonnet",
) -> dict:
    """Aggregate judgments and results into a final comparison report dict."""
    ctrl_scores = [j["control_rubric"]["weighted_overall"] for j in judgments]
    treat_scores = [j["treatment_rubric"]["weighted_overall"] for j in judgments]

    # Pairwise win counts
    wins = {"control": 0, "treatment": 0, "tie": 0}
    for j in judgments:
        winner = j["pairwise"]["winner"]
        wins[winner] = wins.get(winner, 0) + 1

    # Per-dimension comparisons
    dim_scores: dict[str, dict[str, list[float]]] = {}
    for j in judgments:
        for ds in j["control_rubric"]["scores"]:
            did = ds["dimension_id"]
            dim_scores.setdefault(did, {"control": [], "treatment": []})
            dim_scores[did]["control"].append(float(ds["score"]))
        for ds in j["treatment_rubric"]["scores"]:
            did = ds["dimension_id"]
            dim_scores.setdefault(did, {"control": [], "treatment": []})
            dim_scores[did]["treatment"].append(float(ds["score"]))

    dim_comparisons = []
    for dim_id, scores in dim_scores.items():
        ctrl = scores["control"]
        treat = scores["treatment"]
        dim_comparisons.append({
            "dimension_id": dim_id,
            "dimension_name": dim_id,
            "control_stats": _stat(ctrl),
            "treatment_stats": _stat(treat),
            "delta": statistics.mean(treat) - statistics.mean(ctrl) if ctrl and treat else 0.0,
        })

    context_warnings = _detect_context_warnings(control_results, treatment_results)

    report = {
        "skill_name": skill_name,
        "num_scenarios": len(judgments),
        "control_summary": _condition_summary("control", control_results, ctrl_scores),
        "treatment_summary": _condition_summary("treatment", treatment_results, treat_scores),
        "dimension_comparisons": dim_comparisons,
        "pairwise_wins": wins,
        "context_health_warnings": context_warnings,
        "verdict": "",
    }

    # Generate verdict via LLM
    dim_deltas = "\n".join(
        f"- {dc['dimension_name']}: {dc['delta']:+.2f}" for dc in dim_comparisons
    )
    verdict_prompt = f"""Based on this A/B evaluation of the "{skill_name}" skill, write a brief verdict paragraph (3-5 sentences).

Results summary:
- Scenarios tested: {len(judgments)}
- Control avg score: {statistics.mean(ctrl_scores):.2f} vs Treatment avg: {statistics.mean(treat_scores):.2f}
- Pairwise: control won {wins['control']}, treatment won {wins['treatment']}, tied {wins['tie']}
- Context warnings: {len(context_warnings)}

Per-dimension deltas:
{dim_deltas}

Write a concise, honest assessment of whether the skill improves Claude's output and whether the cost/context overhead is justified.
"""

    verdict_result = structured_call(verdict_prompt, VERDICT_SCHEMA, model=model)
    report["verdict"] = verdict_result["verdict"]

    return report


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

def render_markdown(report: dict) -> str:
    """Render a report dict as markdown."""
    cs = report["control_summary"]
    ts = report["treatment_summary"]

    lines = [
        f"# Skill Evaluation Report: {report['skill_name']}",
        "",
        f"**Scenarios tested:** {report['num_scenarios']}",
        "",
        "## Overall Scores",
        "",
        "| Metric | Control | Treatment | Delta |",
        "|--------|---------|-----------|-------|",
        f"| Overall Score | {cs['overall_score']['mean']:.2f} | {ts['overall_score']['mean']:.2f} | {ts['overall_score']['mean'] - cs['overall_score']['mean']:+.2f} |",
        f"| Cost (USD) | ${cs['total_cost_usd']['mean']:.4f} | ${ts['total_cost_usd']['mean']:.4f} | ${ts['total_cost_usd']['mean'] - cs['total_cost_usd']['mean']:+.4f} |",
        f"| Duration (ms) | {cs['total_duration_ms']['mean']:.0f} | {ts['total_duration_ms']['mean']:.0f} | {ts['total_duration_ms']['mean'] - cs['total_duration_ms']['mean']:+.0f} |",
        f"| Input Tokens | {cs['input_tokens']['mean']:.0f} | {ts['input_tokens']['mean']:.0f} | {ts['input_tokens']['mean'] - cs['input_tokens']['mean']:+.0f} |",
        "",
        "## Pairwise Results",
        "",
        f"- Treatment wins: **{report['pairwise_wins'].get('treatment', 0)}**",
        f"- Control wins: **{report['pairwise_wins'].get('control', 0)}**",
        f"- Ties: **{report['pairwise_wins'].get('tie', 0)}**",
        "",
        "## Per-Dimension Comparison",
        "",
        "| Dimension | Control | Treatment | Delta |",
        "|-----------|---------|-----------|-------|",
    ]

    for dc in report.get("dimension_comparisons", []):
        lines.append(
            f"| {dc['dimension_name']} | {dc['control_stats']['mean']:.2f} | {dc['treatment_stats']['mean']:.2f} | {dc['delta']:+.2f} |"
        )

    warnings = report.get("context_health_warnings", [])
    if warnings:
        lines.extend(["", "## Context Health", ""])
        for w in warnings:
            lines.append(f"- **{w['indicator']}**: {w['recommendation']}")

    lines.extend([
        "",
        "## Verdict",
        "",
        report.get("verdict", ""),
        "",
    ])

    return "\n".join(lines)
