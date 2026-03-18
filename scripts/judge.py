"""Judging: combined rubric scoring + blind pairwise comparison in one LLM call.

For each scenario, presents both outputs as "Output 1" and "Output 2"
(randomly shuffled to prevent position bias), scores each on all dimensions,
and picks a pairwise winner — all in a single structured call.
"""

from __future__ import annotations

import os
import random
import sys

sys.path.insert(0, os.path.dirname(__file__))

from backend import structured_call
from schemas import COMBINED_JUDGMENT_SCHEMA


def judge_scenario(
    scenario: dict,
    control_result: dict,
    treatment_result: dict,
    dimensions: list[dict],
    model: str = "sonnet",
) -> dict:
    """Score both outputs and pick a pairwise winner in one LLM call.

    Returns dict with: scenario_id, control_rubric, treatment_rubric, pairwise.
    """
    prompt = scenario["prompt"]
    expectations = scenario.get("expectations", [])

    # Extract outputs
    control_output = "\n\n---\n\n".join(
        t["output"]["result_text"] for t in control_result["turns"]
    )
    treatment_output = "\n\n---\n\n".join(
        t["output"]["result_text"] for t in treatment_result["turns"]
    )

    # Randomly assign Output 1 / Output 2 to prevent position bias
    if random.random() < 0.5:
        out_1, out_2 = control_output, treatment_output
        label_map = {"output_1": "control", "output_2": "treatment"}
    else:
        out_1, out_2 = treatment_output, control_output
        label_map = {"output_1": "treatment", "output_2": "control"}

    # Build dimensions text with rubrics
    dimensions_text = ""
    for d in dimensions:
        dimensions_text += f"\n### {d['name']} ({d['id']})\n{d['description']}\n"
        rubric = d.get("rubric", {})
        for score_key in sorted(rubric.keys(), key=lambda x: int(x)):
            dimensions_text += f"  {score_key}: {rubric[score_key]}\n"

    expectations_text = (
        "\n".join(f"- {e}" for e in expectations) if expectations else "None specified"
    )

    judge_prompt = f"""You are an expert evaluator comparing two AI assistant outputs for the same task.

## Original user prompt:
{prompt}

## Output 1:
{out_1}

## Output 2:
{out_2}

## Scoring dimensions (score each output 1-5 on each dimension):
{dimensions_text}

## Expectations to check (pass/fail each, for both outputs):
{expectations_text}

## Instructions:
1. Score Output 1 on every dimension using the rubrics. Be honest and critical — don't default to high scores.
2. Score Output 2 on every dimension using the same rubrics.
3. Check expectations for both outputs.
4. Compare the two outputs and pick a winner: "output_1", "output_2", or "tie" (only if genuinely equivalent).
5. Explain your comparison reasoning — what makes the winner better?
"""

    llm_result = structured_call(judge_prompt, COMBINED_JUDGMENT_SCHEMA, model=model)

    # Compute weighted averages for both rubrics
    for rubric_key in ("output_1_rubric", "output_2_rubric"):
        rubric = llm_result[rubric_key]
        score_map = {s["dimension_id"]: s["score"] for s in rubric["scores"]}
        total_weight = sum(d.get("weight", 1.0) for d in dimensions)
        weighted_sum = sum(
            score_map.get(d["id"], 3) * d.get("weight", 1.0) for d in dimensions
        )
        rubric["weighted_overall"] = weighted_sum / total_weight if total_weight > 0 else 0.0

    # Map output_1/output_2 back to control/treatment
    raw_winner = llm_result["winner"]
    if raw_winner == "tie":
        actual_winner = "tie"
    else:
        actual_winner = label_map.get(raw_winner, "tie")

    # Assign rubrics to control/treatment based on label_map
    if label_map["output_1"] == "control":
        control_rubric = llm_result["output_1_rubric"]
        treatment_rubric = llm_result["output_2_rubric"]
    else:
        control_rubric = llm_result["output_2_rubric"]
        treatment_rubric = llm_result["output_1_rubric"]

    return {
        "scenario_id": scenario["id"],
        "control_rubric": control_rubric,
        "treatment_rubric": treatment_rubric,
        "pairwise": {
            "winner": actual_winner,
            "label_map": label_map,
            "reasoning": llm_result["comparison_reasoning"],
        },
    }
