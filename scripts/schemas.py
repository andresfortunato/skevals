"""JSON Schema definitions for all structured outputs.

Each schema is a plain dict suitable for both:
- Anthropic API tool_use  (tools[].input_schema)
- Claude CLI --json-schema flag
"""

# ---------------------------------------------------------------------------
# Skill analysis
# ---------------------------------------------------------------------------

SKILL_ANALYSIS_SCHEMA: dict = {
    "type": "object",
    "required": ["manifest", "capabilities", "dimensions"],
    "additionalProperties": False,
    "properties": {
        "manifest": {
            "type": "object",
            "required": ["name", "description", "skill_md_content"],
            "additionalProperties": False,
            "properties": {
                "name": {"type": "string"},
                "description": {"type": "string"},
                "skill_md_content": {"type": "string"},
                "files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Relative paths of all files in skill dir",
                },
                "estimated_context_tokens": {
                    "type": "integer",
                    "description": "Rough token estimate (chars/4)",
                },
            },
        },
        "capabilities": {
            "type": "array",
            "items": {"type": "string"},
            "description": "What the skill enables Claude to do",
        },
        "dimensions": {
            "type": "array",
            "description": "3-6 eval dimensions with rubrics",
            "items": {
                "type": "object",
                "required": ["id", "name", "description", "rubric"],
                "additionalProperties": False,
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Short slug, e.g. 'code_quality'",
                    },
                    "name": {"type": "string", "description": "Human-readable name"},
                    "description": {
                        "type": "string",
                        "description": "What this dimension measures",
                    },
                    "weight": {
                        "type": "number",
                        "description": "Relative importance weight",
                    },
                    "rubric": {
                        "type": "object",
                        "description": "Mapping of score (1-5) to description of that level",
                        "additionalProperties": {"type": "string"},
                    },
                },
            },
        },
    },
}

# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

_GROUND_FILE_SCHEMA: dict = {
    "type": "object",
    "required": ["path", "content"],
    "additionalProperties": False,
    "properties": {
        "path": {
            "type": "string",
            "description": "Relative path within workspace",
        },
        "content": {"type": "string", "description": "File content"},
    },
}

SCENARIO_SET_SCHEMA: dict = {
    "type": "object",
    "required": ["skill_name", "scenarios"],
    "additionalProperties": False,
    "properties": {
        "skill_name": {"type": "string"},
        "scenarios": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "dimension_id", "prompt"],
                "additionalProperties": False,
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Unique scenario identifier",
                    },
                    "dimension_id": {
                        "type": "string",
                        "description": "Which eval dimension this primarily tests",
                    },
                    "prompt": {
                        "type": "string",
                        "description": "The user prompt to send to Claude",
                    },
                    "ground_files": {
                        "type": "array",
                        "items": _GROUND_FILE_SCHEMA,
                        "description": "Files to create in workspace before running",
                    },
                    "expectations": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Verifiable expectations for the output",
                    },
                    "max_turns": {
                        "type": "integer",
                        "description": "Max conversation turns (1 = single-turn)",
                    },
                    "follow_up_strategy": {
                        "type": ["string", "null"],
                        "description": "How to generate follow-up prompts (for multi-turn)",
                    },
                },
            },
        },
    },
}

# ---------------------------------------------------------------------------
# Judging  (combined: rubric scoring + pairwise in a single LLM call)
# ---------------------------------------------------------------------------

_DIMENSION_SCORE_SCHEMA: dict = {
    "type": "object",
    "required": ["dimension_id", "score", "reasoning"],
    "additionalProperties": False,
    "properties": {
        "dimension_id": {"type": "string"},
        "score": {"type": "integer", "minimum": 1, "maximum": 5},
        "reasoning": {"type": "string"},
    },
}

_RUBRIC_RESULT_SCHEMA: dict = {
    "type": "object",
    "required": ["scores", "reasoning"],
    "additionalProperties": False,
    "properties": {
        "scores": {
            "type": "array",
            "items": _DIMENSION_SCORE_SCHEMA,
        },
        "expectation_results": {
            "type": "array",
            "items": {"type": "boolean"},
            "description": "Pass/fail for each expectation",
        },
        "reasoning": {"type": "string"},
    },
}

# The LLM sees Output 1 and Output 2 (randomly shuffled).
# It scores both on rubrics, then picks a pairwise winner.
COMBINED_JUDGMENT_SCHEMA: dict = {
    "type": "object",
    "required": ["output_1_rubric", "output_2_rubric", "winner", "comparison_reasoning"],
    "additionalProperties": False,
    "properties": {
        "output_1_rubric": _RUBRIC_RESULT_SCHEMA,
        "output_2_rubric": _RUBRIC_RESULT_SCHEMA,
        "winner": {
            "type": "string",
            "enum": ["output_1", "output_2", "tie"],
            "description": "Which output is better overall, or tie",
        },
        "comparison_reasoning": {
            "type": "string",
            "description": "Why the winner was chosen (or why it's a tie)",
        },
    },
}

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

_STAT_SUMMARY_SCHEMA: dict = {
    "type": "object",
    "required": ["mean", "stddev", "min", "max"],
    "additionalProperties": False,
    "properties": {
        "mean": {"type": "number"},
        "stddev": {"type": "number"},
        "min": {"type": "number"},
        "max": {"type": "number"},
    },
}

_CONDITION_SUMMARY_SCHEMA: dict = {
    "type": "object",
    "required": ["condition", "overall_score", "total_cost_usd", "total_duration_ms",
                  "input_tokens", "output_tokens"],
    "additionalProperties": False,
    "properties": {
        "condition": {"type": "string"},
        "overall_score": _STAT_SUMMARY_SCHEMA,
        "total_cost_usd": _STAT_SUMMARY_SCHEMA,
        "total_duration_ms": _STAT_SUMMARY_SCHEMA,
        "input_tokens": _STAT_SUMMARY_SCHEMA,
        "output_tokens": _STAT_SUMMARY_SCHEMA,
    },
}

_CONTEXT_HEALTH_WARNING_SCHEMA: dict = {
    "type": "object",
    "required": ["indicator", "value", "threshold", "recommendation"],
    "additionalProperties": False,
    "properties": {
        "indicator": {"type": "string"},
        "value": {"type": "number"},
        "threshold": {"type": "number"},
        "recommendation": {"type": "string"},
    },
}

COMPARISON_REPORT_SCHEMA: dict = {
    "type": "object",
    "required": ["skill_name", "num_scenarios", "control_summary", "treatment_summary"],
    "additionalProperties": False,
    "properties": {
        "skill_name": {"type": "string"},
        "num_scenarios": {"type": "integer"},
        "control_summary": _CONDITION_SUMMARY_SCHEMA,
        "treatment_summary": _CONDITION_SUMMARY_SCHEMA,
        "dimension_comparisons": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["dimension_id", "dimension_name", "control_stats",
                             "treatment_stats", "delta"],
                "additionalProperties": False,
                "properties": {
                    "dimension_id": {"type": "string"},
                    "dimension_name": {"type": "string"},
                    "control_stats": _STAT_SUMMARY_SCHEMA,
                    "treatment_stats": _STAT_SUMMARY_SCHEMA,
                    "delta": {
                        "type": "number",
                        "description": "treatment mean - control mean",
                    },
                },
            },
        },
        "pairwise_wins": {
            "type": "object",
            "description": "Counts: {'control': N, 'treatment': N, 'tie': N}",
            "additionalProperties": {"type": "integer"},
        },
        "context_health_warnings": {
            "type": "array",
            "items": _CONTEXT_HEALTH_WARNING_SCHEMA,
        },
        "verdict": {
            "type": "string",
            "description": "LLM-generated verdict paragraph",
        },
    },
}

# ---------------------------------------------------------------------------
# Verdict (standalone — used by reporter for the final LLM call)
# ---------------------------------------------------------------------------

VERDICT_SCHEMA: dict = {
    "type": "object",
    "required": ["verdict"],
    "additionalProperties": False,
    "properties": {
        "verdict": {
            "type": "string",
            "description": "A concise paragraph summarizing whether the skill helps, hurts, or is neutral",
        },
    },
}
