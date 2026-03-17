"""Models for Claude session execution results."""

from typing import Literal

from pydantic import BaseModel, Field


class TokenUsage(BaseModel):
    """Token counts from a Claude session."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0


class ClaudeOutput(BaseModel):
    """Parsed output from `claude --print --output-format json`."""

    result_text: str = ""
    session_id: str = ""
    duration_ms: int = 0
    duration_api_ms: int = 0
    total_cost_usd: float = 0.0
    usage: TokenUsage = Field(default_factory=TokenUsage)


class Turn(BaseModel):
    """A single turn in a conversation."""

    prompt: str
    output: ClaudeOutput


class SessionResult(BaseModel):
    """Full result of running a scenario under one condition."""

    scenario_id: str
    condition: Literal["control", "treatment"]
    turns: list[Turn] = Field(default_factory=list)
    total_duration_ms: int = 0
    total_duration_api_ms: int = 0
    total_cost_usd: float = 0.0
    total_usage: TokenUsage = Field(default_factory=TokenUsage)
    # Context management metrics
    skill_overhead_ratio: float | None = Field(
        None, description="(treatment_input - control_input) / treatment_input"
    )
    output_composition: dict[str, int] | None = Field(
        None, description="Counts of code_lines vs prose_lines"
    )
    reference_files_available: int = 0
    reference_files_loaded: int = 0
