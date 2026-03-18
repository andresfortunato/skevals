---
name: skevals
description: >
  Run A/B evaluations of Claude Code skills to measure whether they improve
  output quality and at what token/cost overhead. Use when the user wants to
  evaluate a skill, test a skill, benchmark a skill, compare skill performance,
  or measure skill impact. Also use when the user says "evaluate", "eval",
  "benchmark", or "test" in the context of Claude Code skills.
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/*)
---

# skevals — Skill Evaluation

Run A/B evaluations of Claude Code skills. Compares Claude's output with and without a skill loaded, using LLM-as-judge scoring.

No setup required — zero dependencies, runs with Python stdlib only.

## Commands

### Full pipeline (most common)

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/skevals.py eval <skill-path> [options]
```

**Options:**
- `--scenarios N` — Number of test scenarios (default: 3)
- `--model <model>` — Model alias: sonnet, opus, haiku (default: sonnet)
- `--judge-model <model>` — Override judge model (default: same as --model)
- `--budget <usd>` — Max budget per CLI session (default: 0.50)
- `--output-dir <path>` — Where to save artifacts (default: ./eval-output)
- `--backend api|cli` — Force LLM backend (default: auto-detect from ANTHROPIC_API_KEY)

### Individual steps

```bash
# Analyze skill and generate eval dimensions
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/skevals.py analyze <skill-path>

# Generate test scenarios from analysis
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/skevals.py generate analysis.json --count 3

# Run A/B sessions (control vs treatment)
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/skevals.py run scenarios.json <skill-path>

# Judge session results
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/skevals.py judge results/ --analysis-path analysis.json

# Generate comparison report
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/skevals.py report judgments.json results/
```

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
# Standard eval (3 scenarios)
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/skevals.py eval ~/.claude/skills/web-scraping/ --scenarios 3

# Larger eval for higher confidence
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/skevals.py eval ~/.claude/skills/web-scraping/ --scenarios 6

# Eval with specific model
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/skevals.py eval ~/.claude/skills/my-skill/ --model sonnet --scenarios 3
```

After the eval completes, read `eval-output/report.md` and present the key findings to the user:
1. Overall score delta (treatment vs control)
2. Pairwise win/loss/tie counts
3. Any context health warnings
4. The verdict paragraph
