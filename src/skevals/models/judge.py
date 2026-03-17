"""Models for judging results."""

from typing import Literal

from pydantic import BaseModel, Field


class DimensionScore(BaseModel):
    """Score for a single dimension."""

    dimension_id: str
    score: int = Field(ge=1, le=5)
    reasoning: str


class RubricResult(BaseModel):
    """Absolute rubric scoring of a single session output."""

    scores: list[DimensionScore]
    expectation_results: list[bool] = Field(
        default_factory=list, description="Pass/fail for each expectation"
    )
    weighted_overall: float = Field(description="Weighted average score")
    reasoning: str


class PairwiseResult(BaseModel):
    """Blind A/B comparison of control vs treatment."""

    winner: Literal["control", "treatment", "tie"]
    label_map: dict[str, str] = Field(
        description="Maps 'A'/'B' to 'control'/'treatment'"
    )
    reasoning: str
    strengths_a: list[str] = Field(default_factory=list)
    weaknesses_a: list[str] = Field(default_factory=list)
    strengths_b: list[str] = Field(default_factory=list)
    weaknesses_b: list[str] = Field(default_factory=list)


class ScenarioJudgment(BaseModel):
    """Combined judgment for a single scenario."""

    scenario_id: str
    control_rubric: RubricResult
    treatment_rubric: RubricResult
    pairwise: PairwiseResult
