# Handoff — Zero Dep Refactor

## Status

| Phase | Status |
|-------|--------|
| Phase 1: Backend + schemas | Done |
| Phase 2: Pipeline stages | Done |
| Phase 3: CLI + plugin integration | **Next** |
| Phase 4: Tests + cleanup | Pending |

### Files created (all in `scripts/`):
- `schemas.py` — 7 JSON Schema dicts (skill analysis, scenarios, rubric, pairwise, judgment, report, verdict)
- `backend.py` — dual LLM backend: API (urllib) or CLI (claude --print --json-schema), auto-detects based on ANTHROPIC_API_KEY
- `analyzer.py` — parse_skill_dir() + analyze_skill()
- `generator.py` — generate_scenarios() with lite/full mode constraints
- `runner.py` — merged executor + orchestrator + workspace (run_session, run_all_scenarios, create_workspace)
- `judge.py` — score_session() + compare_pair() + judge_scenario()
- `reporter.py` — generate_report() + render_markdown() with context health detection
- `test_backend.py` — 18 tests, all passing (CLI live test confirmed working)

### Verified:
- All modules import cleanly with zero pip dependencies
- parse_skill_dir() tested on `skills/skevals/` — correct output
- reporter._stat() and render_markdown() tested with mock data — correct output
- Backend CLI live test returns `{'verdict': 'test passed'}` via claude --json-schema

## Read Order

1. This file
2. `plan.md` — Phase 3 section for CLI + plugin integration details

## Start At

Phase 3: CLI + plugin integration
- Create `scripts/skevals.py` — argparse CLI with 6 subcommands (eval, analyze, generate, run, judge, report)
- Update `skills/skevals/SKILL.md` — change invocation from `uv run` to `python scripts/skevals.py`
- Update `README.md`

## Key Constraints

- **All modules use `sys.path.insert(0, os.path.dirname(__file__))` for imports** — this lets them import sibling modules (backend, schemas) without being a proper package. Phase 3's CLI entry point must also do this.
- **EvalMode is now a string literal** ("lite" or "full"), not an enum. The CLI should accept `--lite` / `--full` flags and pass the string.
- **Pydantic → dict throughout** — all pipeline functions take/return plain dicts. JSON serialization is `json.dumps(data, indent=2)`.
- **The reporter needs a `judge_scenario()` function** — it was added to judge.py as a convenience that combines rubric + pairwise for one scenario. The CLI's `eval` subcommand should use it.
- **SKILL.md description is multi-line YAML** — parse_skill_dir() intentionally skips multi-line descriptions (">", "|"). The LLM reads the full SKILL.md content anyway.
