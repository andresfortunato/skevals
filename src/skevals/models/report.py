"""Models for the final comparison report."""

from pydantic import BaseModel, Field


class StatSummary(BaseModel):
    """Descriptive statistics for a metric."""

    mean: float
    stddev: float
    min: float
    max: float


class DimensionComparison(BaseModel):
    """Side-by-side comparison for one eval dimension."""

    dimension_id: str
    dimension_name: str
    control_stats: StatSummary
    treatment_stats: StatSummary
    delta: float = Field(description="treatment mean - control mean")


class ConditionSummary(BaseModel):
    """Aggregate stats for one condition (control or treatment)."""

    condition: str
    overall_score: StatSummary
    total_cost_usd: StatSummary
    total_duration_ms: StatSummary
    input_tokens: StatSummary
    output_tokens: StatSummary


class ContextHealthWarning(BaseModel):
    """A context management warning with recommendation."""

    indicator: str
    value: float
    threshold: float
    recommendation: str


class ComparisonReport(BaseModel):
    """The final report comparing control vs treatment."""

    skill_name: str
    num_scenarios: int
    control_summary: ConditionSummary
    treatment_summary: ConditionSummary
    dimension_comparisons: list[DimensionComparison] = Field(default_factory=list)
    pairwise_wins: dict[str, int] = Field(
        default_factory=dict,
        description="Counts: {'control': N, 'treatment': N, 'tie': N}",
    )
    context_health_warnings: list[ContextHealthWarning] = Field(default_factory=list)
    verdict: str = Field("", description="LLM-generated verdict paragraph")
