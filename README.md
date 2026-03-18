# skevals

> **Status: Experimental — results inconclusive.** The synthetic A/B testing approach described below does not produce reliable signal. See [Findings](#findings) for details. The next iteration will use a trace-based monitoring approach instead.

An experiment in evaluating Claude Code skills. Attempts to measure whether skills actually improve output quality by running identical tasks with and without a skill loaded, then using LLM-as-judge to score results.

## Findings

After building and testing the full pipeline, we found that **synthetic A/B evals don't work for skills**:

1. **`claude --print` doesn't match real usage.** Skills are designed for interactive sessions — Claude asks questions, the user responds, work evolves. In `--print` mode there's no user to interact with. Treatment Claude (with skill) asks for permission and clarification. Control Claude (no skill) just does the work. We end up measuring "which Claude performs better non-interactively" — which is irrelevant.

2. **The A/B comparison is structurally unfair.** Skills that make Claude more collaborative (asking before writing, checking understanding) get penalized because there's nobody to collaborate with. Well-designed skills score *worse* than no skill.

3. **Triple-LLM noise.** LLM generates scenarios → LLM runs them → LLM judges results. Each layer adds noise. Signal-to-noise ratio is poor.

4. **Concrete example:** Evaluating the TDD skill, control scored 4.13 vs treatment 1.77. Treatment Claude spent its response asking "Should I proceed?" while control Claude dove straight into comprehensive TDD planning. The skill was penalized for being interactive.

### What might actually work

**Trace-based monitoring**: Instead of synthetic evals, capture real Claude Code session traces during normal usage. Run with and without skills over time, then analyze traces post-factum. This evaluates skills in the environment they're designed for — real interactive sessions with real users.

## Install

### As a Claude Code plugin

```bash
claude plugin install github:andresfortunato/skevals
```

### Standalone

```bash
git clone https://github.com/andresfortunato/skevals.git
cd skevals
```

No dependencies required — runs with Python stdlib only.

## Usage

```bash
# Full pipeline (3 scenarios by default)
python3 scripts/skevals.py eval <skill-path> --scenarios 3

# Individual steps
python3 scripts/skevals.py analyze <skill-path>
python3 scripts/skevals.py generate analysis.json --count 3
python3 scripts/skevals.py run scenarios.json <skill-path>
python3 scripts/skevals.py judge results/ --analysis-path analysis.json
python3 scripts/skevals.py report judgments.json results/
```

### Options

| Flag | Description |
|------|-------------|
| `--model <model>` | Model alias: sonnet, opus, haiku (default: sonnet) |
| `--judge-model <model>` | Override judge model |
| `--budget <usd>` | Max budget per CLI session (default: 0.50) |
| `--scenarios <n>` | Number of test scenarios (default: 3) |
| `--backend api\|cli` | Force LLM backend (default: auto-detect) |

## Architecture

```
skevals eval <skill-path>
  │
  ├─ 1. Analyze ─── parse SKILL.md + LLM → capabilities + eval dimensions
  ├─ 2. Generate ── LLM → N scenarios with prompts + workspace files
  ├─ 3. Run ─────── claude CLI × 2N sessions (control + treatment)
  ├─ 4. Judge ───── combined rubric + blind pairwise (1 call per scenario)
  └─ 5. Report ──── stats + context health + LLM verdict → report.md
```

## Project structure

```
scripts/
├── skevals.py      # argparse CLI, 6 subcommands
├── backend.py      # Dual LLM backend (urllib API / claude CLI)
├── schemas.py      # JSON Schema definitions for structured output
├── analyzer.py     # Skill parsing + LLM analysis
├── generator.py    # Scenario generation
├── runner.py       # Workspace creation + Claude CLI execution + orchestrator
├── judge.py        # Combined rubric scoring + blind pairwise comparison
└── reporter.py     # Stats aggregation + context health + markdown report
```

Zero external dependencies. All stdlib Python.

## Development

```bash
uv run pytest tests/ -v    # 25 unit tests
python3 scripts/skevals.py --help
```
