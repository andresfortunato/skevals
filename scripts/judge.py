"""Judging: rubric scoring and blind pairwise A/B comparison.

Merges the old rubric.py + pairwise.py into a single zero-dep module.
"""

from __future__ import annotations

import os
import random
import sys

sys.path.insert(0, os.path.dirname(__file__))

from backend import structured_call
from schemas import RUBRIC_RESULT_SCHEMA


# ---------------------------------------------------------------------------
# Rubric scoring
# ---------------------------------------------------------------------------

def score_session(
    result: dict,
    dimensions: list[dict],
    expectations: list[str],
    prompt: str,
    model: str = "sonnet",
    max_output_chars: int = 0,
    max_tokens: int = 16384,
) -> dict:
    """Score a session's output against rubric dimensions.

    Returns dict matching RUBRIC_RESULT_SCHEMA.
    """
    full_output = "\n\n---\n\n".join(
        t["output"]["result_text"] for t in result["turns"]
    )
    if max_output_chars > 0 and len(full_output) > max_output_chars:
        full_output = full_output[:max_output_chars] + "\n\n[... truncated for judging ...]"

    dimensions_text = ""
    for d in dimensions:
        dimensions_text += f"\n### {d['name']} ({d['id']})\n{d['description']}\n"
        rubric = d.get("rubric", {})
        for score_key in sorted(rubric.keys(), key=lambda x: int(x)):
            dimensions_text += f"  {score_key}: {rubric[score_key]}\n"

    expectations_text = "\n".join(f"- {e}" for e in expectations) if expectations else "None specified"

    judge_prompt = f"""You are an expert evaluator. Score the following Claude output on each dimension using the rubrics provided.

## Original user prompt:
{prompt}

## Claude's output:
{full_output}

## Scoring dimensions:
{dimensions_text}

## Expectations to check (pass/fail each):
{expectations_text}

For each dimension, provide a score (1-5) based strictly on the rubric definitions. Give honest, critical scores — don't default to high scores.
Also check each expectation and return true/false for whether the output satisfies it.
Provide overall reasoning explaining your scoring.
"""

    llm_result = structured_call(judge_prompt, RUBRIC_RESULT_SCHEMA, model=model, max_tokens=max_tokens)

    # Compute weighted average
    score_map = {s["dimension_id"]: s["score"] for s in llm_result["scores"]}
    total_weight = sum(d.get("weight", 1.0) for d in dimensions)
    weighted_sum = sum(
        score_map.get(d["id"], 3) * d.get("weight", 1.0) for d in dimensions
    )
    llm_result["weighted_overall"] = weighted_sum / total_weight if total_weight > 0 else 0.0

    return llm_result


# ---------------------------------------------------------------------------
# Pairwise comparison
# ---------------------------------------------------------------------------

# Schema for the LLM output — winner is A/B (not control/treatment)
_PAIRWISE_LLM_SCHEMA: dict = {
    "type": "object",
    "required": ["winner", "reasoning"],
    "additionalProperties": False,
    "properties": {
        "winner": {
            "type": "string",
            "enum": ["A", "B", "tie"],
        },
        "reasoning": {"type": "string"},
        "strengths_a": {"type": "array", "items": {"type": "string"}},
        "weaknesses_a": {"type": "array", "items": {"type": "string"}},
        "strengths_b": {"type": "array", "items": {"type": "string"}},
        "weaknesses_b": {"type": "array", "items": {"type": "string"}},
    },
}


def compare_pair(
    control: dict,
    treatment: dict,
    prompt: str,
    model: str = "sonnet",
    max_output_chars: int = 0,
    max_tokens: int = 16384,
) -> dict:
    """Compare control and treatment outputs blind, picking a winner.

    Returns dict matching PAIRWISE_RESULT_SCHEMA (winner is control/treatment/tie).
    """
    control_output = "\n\n---\n\n".join(
        t["output"]["result_text"] for t in control["turns"]
    )
    treatment_output = "\n\n---\n\n".join(
        t["output"]["result_text"] for t in treatment["turns"]
    )

    if max_output_chars > 0:
        if len(control_output) > max_output_chars:
            control_output = control_output[:max_output_chars] + "\n\n[... truncated ...]"
        if len(treatment_output) > max_output_chars:
            treatment_output = treatment_output[:max_output_chars] + "\n\n[... truncated ...]"

    # Randomly assign A/B labels to prevent position bias
    if random.random() < 0.5:
        a_output, b_output = control_output, treatment_output
        label_map = {"A": "control", "B": "treatment"}
    else:
        a_output, b_output = treatment_output, control_output
        label_map = {"A": "treatment", "B": "control"}

    judge_prompt = f"""You are an expert code reviewer comparing two outputs from an AI assistant for the same task. Determine which is better.

## Original user prompt:
{prompt}

## Output A:
{a_output}

## Output B:
{b_output}

## Instructions:
- Compare both outputs on: correctness, completeness, code quality, clarity, and usefulness
- Pick a winner: "A", "B", or "tie" (only if genuinely equivalent)
- List specific strengths and weaknesses of each
- Be critical and specific in your reasoning
"""

    llm_result = structured_call(judge_prompt, _PAIRWISE_LLM_SCHEMA, model=model, max_tokens=max_tokens)

    # Fix string-to-list coercion for haiku
    for key in ("strengths_a", "weaknesses_a", "strengths_b", "weaknesses_b"):
        val = llm_result.get(key, [])
        if isinstance(val, str):
            llm_result[key] = [
                line.lstrip("- ").strip()
                for line in val.strip().split("\n")
                if line.strip()
            ]

    # Map winner back from A/B to control/treatment
    raw_winner = llm_result["winner"]
    if raw_winner == "tie":
        actual_winner = "tie"
    else:
        actual_winner = label_map.get(raw_winner, "tie")

    return {
        "winner": actual_winner,
        "label_map": label_map,
        "reasoning": llm_result["reasoning"],
        "strengths_a": llm_result.get("strengths_a", []),
        "weaknesses_a": llm_result.get("weaknesses_a", []),
        "strengths_b": llm_result.get("strengths_b", []),
        "weaknesses_b": llm_result.get("weaknesses_b", []),
    }


# ---------------------------------------------------------------------------
# Combined judgment for a scenario
# ---------------------------------------------------------------------------

def judge_scenario(
    scenario: dict,
    control_result: dict,
    treatment_result: dict,
    dimensions: list[dict],
    model: str = "sonnet",
    max_output_chars: int = 0,
    max_tokens: int = 16384,
) -> dict:
    """Run rubric scoring + pairwise comparison for a single scenario.

    Returns dict matching SCENARIO_JUDGMENT_SCHEMA.
    """
    expectations = scenario.get("expectations", [])
    prompt = scenario["prompt"]

    control_rubric = score_session(
        control_result, dimensions, expectations, prompt,
        model=model, max_output_chars=max_output_chars, max_tokens=max_tokens,
    )
    treatment_rubric = score_session(
        treatment_result, dimensions, expectations, prompt,
        model=model, max_output_chars=max_output_chars, max_tokens=max_tokens,
    )
    pairwise = compare_pair(
        control_result, treatment_result, prompt,
        model=model, max_output_chars=max_output_chars, max_tokens=max_tokens,
    )

    return {
        "scenario_id": scenario["id"],
        "control_rubric": control_rubric,
        "treatment_rubric": treatment_rubric,
        "pairwise": pairwise,
    }
