"""Skill analysis: parse skill directories and generate eval dimensions.

Two-step process:
  1. parse_skill_dir() — pure filesystem parsing, no LLM
  2. analyze_skill() — LLM call to generate capabilities + eval dimensions
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from backend import structured_call
from schemas import SKILL_ANALYSIS_SCHEMA


def parse_skill_dir(path: str) -> dict:
    """Parse a skill directory into a manifest dict. Pure parsing, no LLM.

    Returns dict with keys: name, description, skill_md_content, files,
    estimated_context_tokens.
    """
    skill_md = os.path.join(path, "SKILL.md")
    if not os.path.isfile(skill_md):
        raise FileNotFoundError(f"No SKILL.md found at {path}")

    with open(skill_md) as f:
        content = f.read()

    # Parse YAML frontmatter
    name = os.path.basename(path)
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
    for root, _dirs, filenames in sorted(os.walk(path)):
        for fname in sorted(filenames):
            full = os.path.join(root, fname)
            rel = os.path.relpath(full, path)
            files.append(rel)
            try:
                with open(full) as f:
                    total_chars += len(f.read())
            except (UnicodeDecodeError, PermissionError, OSError):
                total_chars += os.path.getsize(full)

    return {
        "name": name,
        "description": description,
        "skill_md_content": content,
        "files": files,
        "estimated_context_tokens": total_chars // 4,
    }


def analyze_skill(manifest: dict, model: str = "sonnet") -> dict:
    """Use an LLM to analyze a skill and generate eval dimensions.

    Takes a manifest dict (from parse_skill_dir), returns a full analysis dict
    matching SKILL_ANALYSIS_SCHEMA.
    """
    # We only need the LLM to generate capabilities + dimensions.
    # Build a schema for just those fields.
    llm_schema = {
        "type": "object",
        "required": ["capabilities", "dimensions"],
        "additionalProperties": False,
        "properties": {
            "capabilities": SKILL_ANALYSIS_SCHEMA["properties"]["capabilities"],
            "dimensions": SKILL_ANALYSIS_SCHEMA["properties"]["dimensions"],
        },
    }

    file_list = "\n".join(f"- {f}" for f in manifest["files"])
    prompt = f"""Analyze this Claude Code skill and determine:
1. What capabilities it gives Claude (list of short descriptions)
2. 3-6 evaluation dimensions to measure the skill's impact, each with:
   - id: short slug (e.g., "code_quality")
   - name: human-readable name
   - description: what this dimension measures
   - weight: relative importance (1.0 = normal)
   - rubric: mapping of scores 1-5 to descriptions of what that score means

Focus on dimensions where the skill should make a measurable difference vs Claude without the skill.

## Skill: {manifest['name']}

### SKILL.md content:
{manifest['skill_md_content']}

### Files in skill directory:
{file_list}

### Estimated context tokens: {manifest['estimated_context_tokens']}
"""

    result = structured_call(prompt, llm_schema, model=model)

    return {
        "manifest": manifest,
        "capabilities": result["capabilities"],
        "dimensions": result["dimensions"],
    }


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys as _sys

    if len(_sys.argv) < 2:
        print("Usage: python scripts/analyzer.py <skill-path> [--model MODEL]")
        _sys.exit(1)

    skill_path = _sys.argv[1]
    model_arg = "sonnet"
    if "--model" in _sys.argv:
        idx = _sys.argv.index("--model")
        model_arg = _sys.argv[idx + 1]

    manifest = parse_skill_dir(skill_path)
    print(f"Parsed skill: {manifest['name']} ({len(manifest['files'])} files, ~{manifest['estimated_context_tokens']} tokens)")

    analysis = analyze_skill(manifest, model=model_arg)
    print(json.dumps(analysis, indent=2))
