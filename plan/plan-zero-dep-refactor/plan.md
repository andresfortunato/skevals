# Zero-Dep Refactor — Implementation Plan

## Goal

Rewrite skevals to use only Python stdlib (no pip dependencies), support dual LLM backends (Anthropic API via urllib OR Claude CLI), and restructure as a native Claude Code plugin that works immediately after install.

## Constraints

- **Zero pip dependencies** — only stdlib imports. No anthropic, pydantic, typer, rich, python-dotenv.
- **Preserve all existing functionality** — analyze, generate, run, judge, report, eval commands. Lite/full modes. Context health detection.
- **Don't break the standalone CLI** — it should still work via `python -m skevals eval ...` from the repo root.
- **Dual backend is transparent** — the pipeline code doesn't care which backend is used. The backend selection happens once at startup.
- **JSON files between stages are backward-compatible** — same structure as current Pydantic model dumps (dicts with same keys).
- **This is a rewrite, not a patch** — new files in `scripts/`, old `src/skevals/` is replaced. Clean break.

## Decisions Made (from brainstorming — don't re-debate)

1. **Dual LLM backend**: `ANTHROPIC_API_KEY` present -> urllib direct API calls (~400 tokens overhead). No key -> `claude --print --json-schema` (~23K tokens overhead). User can also force a backend with `--backend api|cli`.
2. **urllib.request for API calls**: POST to `api.anthropic.com/v1/messages` with tool_use for structured output. Tested and working. Zero deps.
3. **`claude --print --json-schema` for CLI backend**: Returns `structured_output` field in JSON response. Needs `--max-turns 2+`. Tested and working.
4. **argparse replaces Typer**: 6 subcommands via `argparse` subparsers.
5. **dataclasses replace Pydantic**: For internal data passing. JSON files are plain dicts.
6. **print() replaces Rich**: Simple ANSI escape codes for color if needed.
7. **Plugin invocation**: `python ${CLAUDE_PLUGIN_ROOT}/scripts/skevals.py eval <skill-path>` — no uv, no pip.

## File Manifest

### New files (plugin-native structure)

| File | Intent |
|------|--------|
| `scripts/skevals.py` | Main entry point — argparse CLI, subcommand dispatch |
| `scripts/backend.py` | Dual LLM backend: `structured_call()` that routes to API or CLI |
| `scripts/analyzer.py` | Skill parsing + LLM analysis (merge current analyzer/) |
| `scripts/generator.py` | Scenario generation |
| `scripts/runner.py` | Workspace creation + Claude CLI executor + orchestrator (merge current runner/) |
| `scripts/judge.py` | Rubric scoring + pairwise comparison (merge current judge/) |
| `scripts/reporter.py` | Stats, context health, markdown report |
| `scripts/schemas.py` | JSON Schema definitions for all structured outputs |

### Modified files

| File | Intent |
|------|--------|
| `skills/skevals/SKILL.md` | Update invocation from `uv run` to `python scripts/skevals.py` |
| `.claude-plugin/plugin.json` | Update if needed |
| `README.md` | Update install/usage instructions for both plugin and standalone |

### Files to delete

| File | Reason |
|------|--------|
| `src/skevals/` (entire directory) | Replaced by `scripts/` |
| `pyproject.toml` | No longer a pip package (keep only if we want standalone `uv run` too) |

### Files to keep as-is

| File | Reason |
|------|--------|
| `tests/` | Update to import from scripts/ instead |
| `.claude-plugin/` | Already correct |
| `brainstorms/`, `plan/` | Reference material |

## Repo Context

- Current code is 2,121 lines across 24 Python files in `src/skevals/`
- The pipeline stages are cleanly separated: analyzer -> generator -> runner -> judge -> reporter
- Each stage reads/writes JSON files — this stays the same
- The `llm/client.py` module is the only file that calls the Anthropic SDK — this becomes `backend.py`
- `runner/executor.py` already shells out to `claude --print` — that pattern stays
- `config.py` has model aliases and EvalMode enum — absorbed into `skevals.py`
- Tests are lightweight (9 tests) and mostly test parsing/model creation — easy to adapt

## Integration Seams

1. **backend.py <-> every pipeline stage**: All LLM calls go through `structured_call(prompt, schema, model)`. Backend selection is transparent.
2. **scripts/skevals.py <-> SKILL.md**: The skill invokes `python ${CLAUDE_PLUGIN_ROOT}/scripts/skevals.py`. This path must be correct.
3. **JSON files between stages**: analysis.json, scenarios.json, sessions/*.json, judgments.json, report.json. Same dict structure as current Pydantic dumps.

## Phases

### Phase 1: Backend + schemas
- **Intent**: Build the foundation — dual LLM backend and JSON schema definitions. Everything else depends on these.
- **Files**: `scripts/backend.py`, `scripts/schemas.py`
- **Verification**: Unit test that `structured_call()` returns valid dicts via both backends. Test API path with ANTHROPIC_API_KEY, test CLI path without.
- **Estimated context**: 20%

### Phase 2: Pipeline stages
- **Intent**: Port all 5 pipeline stages (analyzer, generator, runner, judge, reporter) to zero-dep scripts using the new backend.
- **Files**: `scripts/analyzer.py`, `scripts/generator.py`, `scripts/runner.py`, `scripts/judge.py`, `scripts/reporter.py`
- **Verification**: Each stage can be called standalone and produces correct JSON output. `python scripts/analyzer.py ~/.claude/skills/web-scraping/` works.
- **Estimated context**: 40%

### Phase 3: CLI + plugin integration
- **Intent**: Wire everything together with argparse CLI, update SKILL.md invocation, update README.
- **Files**: `scripts/skevals.py`, `skills/skevals/SKILL.md`, `README.md`
- **Verification**: `python scripts/skevals.py eval ~/.claude/skills/web-scraping/ --scenarios 3 --lite` runs end-to-end. `claude --plugin-dir . --print -p "evaluate web-scraping skill"` triggers the skill correctly.
- **Estimated context**: 20%

### Phase 4: Tests + cleanup
- **Intent**: Update tests, remove old src/skevals/, clean up pyproject.toml.
- **Files**: `tests/`, `src/` (delete), `pyproject.toml` (simplify or remove)
- **Verification**: All tests pass. `claude plugin validate .` passes.
- **Estimated context**: 15%
