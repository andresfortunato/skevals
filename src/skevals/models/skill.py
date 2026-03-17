"""Models for skill analysis."""

from pydantic import BaseModel, Field


class SkillManifest(BaseModel):
    """Parsed representation of a skill directory."""

    name: str
    description: str
    skill_md_content: str
    files: list[str] = Field(default_factory=list, description="Relative paths of all files in skill dir")
    estimated_context_tokens: int = Field(0, description="Rough token estimate (chars/4)")


class EvalDimension(BaseModel):
    """A dimension along which to evaluate skill impact."""

    id: str = Field(description="Short slug, e.g. 'code_quality'")
    name: str = Field(description="Human-readable name")
    description: str = Field(description="What this dimension measures")
    weight: float = Field(1.0, description="Relative importance weight")
    rubric: dict[int, str] = Field(
        description="Mapping of score (1-5) to description of that level"
    )


class SkillAnalysis(BaseModel):
    """LLM-generated analysis of a skill's capabilities and eval dimensions."""

    manifest: SkillManifest
    capabilities: list[str] = Field(description="What the skill enables Claude to do")
    dimensions: list[EvalDimension] = Field(description="3-6 eval dimensions with rubrics")
