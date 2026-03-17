"""Scenario generation from skill analysis."""

from pydantic import BaseModel, Field

from skevals.config import EvalMode
from skevals.llm.client import structured_call
from skevals.models.scenario import Scenario, ScenarioSet
from skevals.models.skill import SkillAnalysis


class _ScenarioList(BaseModel):
    scenarios: list[Scenario] = Field(description="Generated evaluation scenarios")


_LITE_CONSTRAINTS = """
## IMPORTANT constraints for this eval:
- Scenarios MUST be answerable in a single text response — no file creation, no multi-step tool use
- Prompts should ask for code snippets, explanations, analysis, or advice — NOT "build me a project"
- ground_files: max 2 files, each under 500 characters. Use small representative samples, not full files.
- max_turns: always 1
- The goal is to test knowledge and approach quality, not tool-use behavior
"""

_FULL_CONSTRAINTS = """
## Constraints:
- ground_files: include realistic content, not stubs. Each has a path and content.
- max_turns: 1 for single-turn (default), >1 only if the skill specifically adds multi-turn value
- follow_up_strategy: null for single-turn
"""


def generate_scenarios(
    analysis: SkillAnalysis,
    count: int = 6,
    model: str = "sonnet",
    mode: EvalMode = EvalMode.lite,
) -> ScenarioSet:
    """Generate evaluation scenarios from a skill analysis."""

    dimensions_desc = "\n".join(
        f"- {d.id}: {d.name} — {d.description}" for d in analysis.dimensions
    )

    mode_constraints = _LITE_CONSTRAINTS if mode == EvalMode.lite else _FULL_CONSTRAINTS

    prompt = f"""Generate {count} evaluation scenarios to test whether the skill "{analysis.manifest.name}" improves Claude's output.

## Skill capabilities:
{chr(10).join(f'- {c}' for c in analysis.capabilities)}

## Evaluation dimensions:
{dimensions_desc}

## Requirements for each scenario:
- **id**: unique identifier like "scenario_01"
- **dimension_id**: which dimension this primarily tests (distribute across dimensions)
- **prompt**: a realistic user prompt that exercises the skill's domain. Be specific and concrete.
- **expectations**: 2-4 verifiable things the output should contain or achieve
{mode_constraints}
## Key principles:
- Scenarios should be tasks where a skilled Claude would differ noticeably from an unskilled one
- Include both "the skill should clearly help" and "edge case" scenarios
- Prompts should be what a real user would type, not meta-instructions about skills
"""

    result = structured_call(prompt, _ScenarioList, model=model)

    return ScenarioSet(
        skill_name=analysis.manifest.name,
        scenarios=result.scenarios,
    )
