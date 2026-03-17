"""Blind pairwise A/B comparison of control vs treatment outputs."""

import random
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from skevals.llm.client import structured_call
from skevals.models.judge import PairwiseResult
from skevals.models.session import SessionResult


def _coerce_str_to_list(v: object) -> list[str]:
    """Coerce a string into a list by splitting on newlines.

    Smaller models (haiku) sometimes return list fields as newline-delimited
    strings instead of JSON arrays.
    """
    if isinstance(v, str):
        return [line.lstrip("- ").strip() for line in v.strip().split("\n") if line.strip()]
    if isinstance(v, list):
        return v
    return []


class _PairwiseLLMOutput(BaseModel):
    winner: Literal["A", "B", "tie"]
    reasoning: str
    strengths_a: list[str] = Field(default_factory=list)
    weaknesses_a: list[str] = Field(default_factory=list)
    strengths_b: list[str] = Field(default_factory=list)
    weaknesses_b: list[str] = Field(default_factory=list)

    @field_validator("strengths_a", "weaknesses_a", "strengths_b", "weaknesses_b", mode="before")
    @classmethod
    def coerce_lists(cls, v: object) -> list[str]:
        return _coerce_str_to_list(v)


def compare_pair(
    control: SessionResult,
    treatment: SessionResult,
    prompt: str,
    model: str = "sonnet",
    max_output_chars: int = 0,
    max_tokens: int = 16384,
) -> PairwiseResult:
    """Compare control and treatment outputs blind, picking a winner.

    Args:
        max_output_chars: If >0, truncate each output before sending to judge.
        max_tokens: Max output tokens for the judge LLM call.
    """
    control_output = "\n\n---\n\n".join(t.output.result_text for t in control.turns)
    treatment_output = "\n\n---\n\n".join(t.output.result_text for t in treatment.turns)

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

    llm_result = structured_call(judge_prompt, _PairwiseLLMOutput, model=model, max_tokens=max_tokens)

    # Map winner back from A/B labels to control/treatment
    if llm_result.winner == "tie":
        actual_winner = "tie"
    else:
        actual_winner = label_map[llm_result.winner]

    return PairwiseResult(
        winner=actual_winner,
        label_map=label_map,
        reasoning=llm_result.reasoning,
        strengths_a=llm_result.strengths_a,
        weaknesses_a=llm_result.weaknesses_a,
        strengths_b=llm_result.strengths_b,
        weaknesses_b=llm_result.weaknesses_b,
    )
