"""Absolute rubric scoring of session outputs."""

from pydantic import BaseModel, Field

from skevals.llm.client import structured_call
from skevals.models.judge import DimensionScore, RubricResult
from skevals.models.session import SessionResult
from skevals.models.skill import EvalDimension


class _RubricLLMOutput(BaseModel):
    scores: list[DimensionScore]
    expectation_results: list[bool] = Field(default_factory=list)
    reasoning: str


def score_session(
    result: SessionResult,
    dimensions: list[EvalDimension],
    expectations: list[str],
    prompt: str,
    model: str = "sonnet",
    max_output_chars: int = 0,
    max_tokens: int = 16384,
) -> RubricResult:
    """Score a session's output against the rubric dimensions.

    Args:
        max_output_chars: If >0, truncate output before sending to judge.
        max_tokens: Max output tokens for the judge LLM call.
    """
    # Combine all turn outputs
    full_output = "\n\n---\n\n".join(
        t.output.result_text for t in result.turns
    )
    if max_output_chars > 0 and len(full_output) > max_output_chars:
        full_output = full_output[:max_output_chars] + "\n\n[... truncated for judging ...]"

    dimensions_text = ""
    for d in dimensions:
        dimensions_text += f"\n### {d.name} ({d.id})\n{d.description}\n"
        for score, desc in sorted(d.rubric.items()):
            dimensions_text += f"  {score}: {desc}\n"

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

    llm_result = structured_call(judge_prompt, _RubricLLMOutput, model=model, max_tokens=max_tokens)

    # Compute weighted average
    score_map = {s.dimension_id: s.score for s in llm_result.scores}
    total_weight = sum(d.weight for d in dimensions)
    weighted_sum = sum(
        score_map.get(d.id, 3) * d.weight for d in dimensions
    )
    weighted_overall = weighted_sum / total_weight if total_weight > 0 else 0.0

    return RubricResult(
        scores=llm_result.scores,
        expectation_results=llm_result.expectation_results,
        weighted_overall=weighted_overall,
        reasoning=llm_result.reasoning,
    )
