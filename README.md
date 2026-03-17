# skevals

A/B testing CLI for Claude Code skills. Measures whether skills actually improve output quality, and at what token/cost overhead.

## What it does

skevals runs identical tasks through Claude with and without a skill loaded, then uses LLM-as-judge to score the results. It produces a comparison report with per-dimension rubric scores, blind pairwise rankings, and context health analysis.

## Install

```bash
uv sync
```

Requires `ANTHROPIC_API_KEY` in `.env` or environment.

## Usage

### Full pipeline (recommended)

```bash
# Lite mode (default) — fast, cheap, single-turn text evaluation
skevals eval ~/.claude/skills/web-scraping/ --scenarios 3

# Full mode — multi-turn with tool use, thorough but expensive
skevals eval ~/.claude/skills/web-scraping/ --scenarios 3 --full
```

### Step-by-step

```bash
skevals analyze <skill-path>                      # -> analysis.json
skevals generate analysis.json --count 6          # -> scenarios.json
skevals run scenarios.json <skill-path>           # -> results/
skevals judge results/ --analysis-path analysis.json  # -> judgments.json
skevals report judgments.json results/             # -> report.md
```

### Key options

| Flag | Description |
|------|-------------|
| `--lite` | Single-turn, text-only, haiku judge (default) |
| `--full` | Multi-turn, tool use, sonnet judge |
| `--judge-model <model>` | Override judge model (sonnet/haiku/opus) |
| `--model <model>` | Model for analysis, generation, and CLI sessions |
| `--budget <usd>` | Max budget per CLI session (default: 0.50) |
| `--scenarios <n>` | Number of test scenarios to generate |

## Evaluation modes

### Lite mode (default)

- `--max-turns 1` on Claude CLI sessions — single-turn text responses only
- Scenarios constrained to questions answerable without file creation
- Judge uses haiku with truncated outputs and capped tokens
- Tests **knowledge and approach quality**

### Full mode

- Unrestricted Claude CLI sessions with tool use
- Scenarios can involve file creation, multi-step workflows
- Judge uses sonnet with full outputs
- Tests **execution quality and tool-use behavior**

## Baseline results

### web-scraping skill (3 scenarios, sonnet runner)

**Lite mode:**

| Metric | Control | Treatment | Delta |
|--------|---------|-----------|-------|
| Overall Score | 1.30 | 1.45 | +0.15 |
| Cost (USD) | $0.050 | $0.077 | +$0.027 |
| CLI tokens | ~47K/session | ~24K/session | -49% |
| Pairwise | 0 wins | 0 wins | 3 ties |

Total CLI tokens: 142,644. Total cost: ~$0.38.

**Full mode:**

| Metric | Control | Treatment | Delta |
|--------|---------|-----------|-------|
| Overall Score | 1.84 | 1.74 | -0.10 |
| Cost (USD) | $0.265 | $0.239 | -$0.026 |
| CLI tokens | ~154K/session | ~154K/session | ~0% |
| Pairwise | 1 win | 1 win | 1 tie |

Total CLI tokens: 921,670. Total cost: ~$1.49.

Context health warning in full mode: "Treatment output is 100% prose vs 64% for control — skill may cause over-explaining."

## Architecture

```
skevals eval <skill-path>
  │
  ├─ 1. Analyze ─── parse SKILL.md + LLM → capabilities + eval dimensions
  ├─ 2. Generate ── LLM → N scenarios with prompts + workspace files
  ├─ 3. Run ─────── claude CLI × 2N sessions (control + treatment)
  ├─ 4. Judge ───── rubric scoring (per-dimension 1-5) + pairwise A/B
  └─ 5. Report ──── stats + context health + LLM verdict → report.md
```

**A/B control mechanism:**
- Control: `claude --print --disable-slash-commands` (no skills)
- Treatment: `claude --print --plugin-dir <wrapped-skill>` (skill loaded)
- Both strip `CLAUDECODE` env var to allow nesting inside Claude Code

## Project structure

```
src/skevals/
├── cli.py              # Typer app with 6 commands
├── config.py           # EvalMode enum, model aliases, defaults
├── models/             # Pydantic models (skill, scenario, session, judge, report)
├── analyzer/           # Skill parsing + LLM analysis
├── generator/          # Scenario generation
├── runner/             # Workspace, executor (Claude CLI subprocess), orchestrator
├── judge/              # Rubric scoring + blind pairwise comparison
├── reporter/           # Stats aggregation + markdown report
└── llm/                # Anthropic SDK wrapper with structured output
```

## Development

```bash
uv run pytest           # 9 unit tests
uv run skevals --help   # all commands
```
