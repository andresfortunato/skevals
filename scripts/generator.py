"""Scenario generation from skill analysis.

Takes a skill analysis dict and produces a scenario set dict with
evaluation scenarios tailored to test the skill's impact.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from backend import structured_call
from schemas import SCENARIO_SET_SCHEMA

_SCENARIO_CONSTRAINTS = """
## Scenario design constraints:
- Each scenario should be a **small, focused, controlled task** — a single function, a short script,
  a specific refactor, a targeted bug fix. NOT "build me a project" or "create an app."
- ground_files: include realistic but concise content. Each file should be under 1000 characters.
  Provide just enough context for the task — a small module, a config snippet, a test file.
- max_turns: use 1 for tasks answerable in a single response. Use 2-3 only if the skill specifically
  adds multi-turn value (e.g., iterative refinement, test-then-fix cycles).
- The goal is to test whether the skill changes Claude's **approach and quality**, not whether
  Claude can complete a large project. Keep output naturally bounded.
- Prompts should be what a real user would type, not meta-instructions about skills.
"""


def generate_scenarios(
    analysis: dict,
    count: int = 6,
    model: str = "sonnet",
) -> dict:
    """Generate evaluation scenarios from a skill analysis.

    Returns dict matching SCENARIO_SET_SCHEMA.
    """
    dimensions_desc = "\n".join(
        f"- {d['id']}: {d['name']} — {d['description']}"
        for d in analysis["dimensions"]
    )

    capabilities_desc = "\n".join(
        f"- {c}" for c in analysis["capabilities"]
    )

    # The LLM only needs to generate the scenarios list — we add skill_name ourselves
    scenarios_schema = {
        "type": "object",
        "required": ["scenarios"],
        "additionalProperties": False,
        "properties": {
            "scenarios": SCENARIO_SET_SCHEMA["properties"]["scenarios"],
        },
    }

    prompt = f"""Generate {count} evaluation scenarios to test whether the skill "{analysis['manifest']['name']}" improves Claude's output.

## Skill capabilities:
{capabilities_desc}

## Evaluation dimensions:
{dimensions_desc}

## Requirements for each scenario:
- **id**: unique identifier like "scenario_01"
- **dimension_id**: which dimension this primarily tests (distribute across dimensions)
- **prompt**: a realistic user prompt that exercises the skill's domain. Be specific and concrete.
- **expectations**: 2-4 verifiable things the output should contain or achieve
{_SCENARIO_CONSTRAINTS}
## Key principles:
- Scenarios should be tasks where a skilled Claude would differ noticeably from an unskilled one
- Include both "the skill should clearly help" and "edge case" scenarios
"""

    result = structured_call(prompt, scenarios_schema, model=model)

    return {
        "skill_name": analysis["manifest"]["name"],
        "scenarios": result["scenarios"],
    }


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys as _sys

    if len(_sys.argv) < 2:
        print("Usage: python scripts/generator.py <analysis.json> [--count N] [--model MODEL]")
        _sys.exit(1)

    with open(_sys.argv[1]) as f:
        analysis_data = json.load(f)

    count_arg = 6
    model_arg = "sonnet"
    args = _sys.argv[2:]
    for i, arg in enumerate(args):
        if arg == "--count" and i + 1 < len(args):
            count_arg = int(args[i + 1])
        elif arg == "--model" and i + 1 < len(args):
            model_arg = args[i + 1]

    scenarios = generate_scenarios(analysis_data, count=count_arg, model=model_arg)
    print(json.dumps(scenarios, indent=2))
