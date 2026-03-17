"""Skill analysis: parse skill directories and generate eval dimensions."""

from pathlib import Path

from skevals.llm.client import structured_call
from skevals.models.skill import EvalDimension, SkillAnalysis, SkillManifest


def parse_skill_dir(path: Path) -> SkillManifest:
    """Parse a skill directory into a SkillManifest. Pure parsing, no LLM."""
    skill_md = path / "SKILL.md"
    if not skill_md.exists():
        raise FileNotFoundError(f"No SKILL.md found at {path}")

    content = skill_md.read_text()

    # Parse YAML frontmatter
    name = path.name
    description = ""
    if content.startswith("---"):
        lines = content.split("\n")
        end_idx = None
        for i, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                end_idx = i
                break
        if end_idx:
            for line in lines[1:end_idx]:
                if line.startswith("name:"):
                    name = line[len("name:"):].strip().strip("\"'")
                elif line.startswith("description:"):
                    value = line[len("description:"):].strip()
                    if value not in (">", "|", ">-", "|-"):
                        description = value.strip("\"'")

    # Collect all files
    files: list[str] = []
    total_chars = 0
    for f in sorted(path.rglob("*")):
        if f.is_file():
            rel = str(f.relative_to(path))
            files.append(rel)
            try:
                total_chars += len(f.read_text())
            except (UnicodeDecodeError, PermissionError):
                total_chars += f.stat().st_size

    return SkillManifest(
        name=name,
        description=description,
        skill_md_content=content,
        files=files,
        estimated_context_tokens=total_chars // 4,
    )


def analyze_skill(manifest: SkillManifest, model: str = "sonnet") -> SkillAnalysis:
    """Use an LLM to analyze a skill and generate eval dimensions."""

    # Build a model for just the LLM-generated fields
    from pydantic import BaseModel, Field

    class AnalysisLLMOutput(BaseModel):
        capabilities: list[str] = Field(description="What the skill enables Claude to do")
        dimensions: list[EvalDimension] = Field(description="3-6 eval dimensions with 5-point rubrics")

    prompt = f"""Analyze this Claude Code skill and determine:
1. What capabilities it gives Claude (list of short descriptions)
2. 3-6 evaluation dimensions to measure the skill's impact, each with:
   - id: short slug (e.g., "code_quality")
   - name: human-readable name
   - description: what this dimension measures
   - weight: relative importance (1.0 = normal)
   - rubric: mapping of scores 1-5 to descriptions of what that score means

Focus on dimensions where the skill should make a measurable difference vs Claude without the skill.

## Skill: {manifest.name}

### SKILL.md content:
{manifest.skill_md_content}

### Files in skill directory:
{chr(10).join(f'- {f}' for f in manifest.files)}

### Estimated context tokens: {manifest.estimated_context_tokens}
"""

    result = structured_call(prompt, AnalysisLLMOutput, model=model)

    return SkillAnalysis(
        manifest=manifest,
        capabilities=result.capabilities,
        dimensions=result.dimensions,
    )
