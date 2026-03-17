---
name: skevals
description: >
  Run A/B evaluations of Claude Code skills to measure whether they improve
  output quality and at what token/cost overhead. Use when the user wants to
  evaluate a skill, test a skill, benchmark a skill, compare skill performance,
  or measure skill impact. Also use when the user says "evaluate", "eval",
  "benchmark", or "test" in the context of Claude Code skills.
allowed-tools: Bash(uv run --directory *)
---

# skevals — Skill Evaluation

Run A/B evaluations of Claude Code skills. Compares Claude's output with and without a skill loaded, using LLM-as-judge scoring.

## Setup (first run only)

Before first use, ensure dependencies are installed:

```bash
uv sync --directory ${CLAUDE_PLUGIN_ROOT}
```

The user must have `ANTHROPIC_API_KEY` set in their environment or in a `.env` file in their working directory.

## Commands

### Full pipeline (most common)

```bash
uv run --directory ${CLAUDE_PLUGIN_ROOT} skevals eval <skill-path> [options]
```

**Options:**
- `--scenarios N` — Number of test scenarios (default: 6)
- `--lite` — Single-turn text evaluation, fast and cheap (default)
- `--full` — Multi-turn with tool use, thorough but expensive
- `--model <model>` — Model alias: sonnet, opus, haiku (default: sonnet)
- `--judge-model <model>` — Override judge model (default: same as --model)
- `--budget <usd>` — Max budget per CLI session (default: 0.50)
- `--output-dir <path>` — Where to save artifacts (default: ./eval-output)

### Individual steps

```bash
# Analyze skill and generate eval dimensions
uv run --directory ${CLAUDE_PLUGIN_ROOT} skevals analyze <skill-path>

# Generate test scenarios from analysis
uv run --directory ${CLAUDE_PLUGIN_ROOT} skevals generate analysis.json --count 6

# Run A/B sessions (control vs treatment)
uv run --directory ${CLAUDE_PLUGIN_ROOT} skevals run scenarios.json <skill-path>

# Judge session results
uv run --directory ${CLAUDE_PLUGIN_ROOT} skevals judge results/ --analysis-path analysis.json

# Generate comparison report
uv run --directory ${CLAUDE_PLUGIN_ROOT} skevals report judgments.json results/
```

## When to use which mode

- **`--lite`** (default): Quick feedback on whether a skill adds value. Single-turn, text-only responses. ~$0.60 for 3 scenarios. Use for iterating on skill design.
- **`--full`**: Thorough evaluation with tool use. ~$1.50+ for 3 scenarios. Use for final validation before publishing a skill.

## Interpreting results

The report (`report.md`) contains:
- **Overall scores**: Weighted average across rubric dimensions (1-5 scale)
- **Per-dimension comparison**: Where the skill helps vs hurts
- **Pairwise results**: Blind A/B winner counts (treatment wins / control wins / ties)
- **Context health**: Warnings about token overhead, unused references, output truncation
- **Verdict**: LLM-generated summary of findings

**Key signals:**
- Treatment overall score > control = skill improves quality
- Pairwise treatment wins > control wins = skill consistently preferred
- Context health warnings = skill may need optimization (e.g., trim SKILL.md, remove unused references)

## Example usage

When the user asks to evaluate a skill:

```bash
# Quick eval of a skill
uv run --directory ${CLAUDE_PLUGIN_ROOT} skevals eval ~/.claude/skills/web-scraping/ --scenarios 3 --lite

# Thorough eval
uv run --directory ${CLAUDE_PLUGIN_ROOT} skevals eval ~/.claude/skills/web-scraping/ --scenarios 6 --full

# Eval with specific model
uv run --directory ${CLAUDE_PLUGIN_ROOT} skevals eval ~/.claude/skills/my-skill/ --model sonnet --scenarios 3
```

After the eval completes, read `eval-output/report.md` and present the key findings to the user:
1. Overall score delta (treatment vs control)
2. Pairwise win/loss/tie counts
3. Any context health warnings
4. The verdict paragraph
