"""Models for evaluation scenarios."""

from pydantic import BaseModel, Field


class GroundFile(BaseModel):
    """A file to place in the workspace before running a scenario."""

    path: str = Field(description="Relative path within workspace")
    content: str = Field(description="File content")


class Scenario(BaseModel):
    """A single evaluation scenario — a task to run with and without the skill."""

    id: str = Field(description="Unique scenario identifier")
    dimension_id: str = Field(description="Which eval dimension this primarily tests")
    prompt: str = Field(description="The user prompt to send to Claude")
    ground_files: list[GroundFile] = Field(
        default_factory=list, description="Files to create in workspace before running"
    )
    expectations: list[str] = Field(
        default_factory=list,
        description="Verifiable expectations for the output",
    )
    max_turns: int = Field(1, description="Max conversation turns (1 = single-turn)")
    follow_up_strategy: str | None = Field(
        None, description="How to generate follow-up prompts (for multi-turn)"
    )


class ScenarioSet(BaseModel):
    """A collection of scenarios for an eval run."""

    skill_name: str
    scenarios: list[Scenario]
