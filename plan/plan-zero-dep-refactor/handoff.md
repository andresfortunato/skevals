# Handoff — Zero Dep Refactor

## Status

| Phase | Status |
|-------|--------|
| Phase 1: Backend + schemas | Done |
| Phase 2: Pipeline stages | Done |
| Phase 3: CLI + plugin integration | Done |
| Phase 4: Tests + cleanup | **Next** |

### Files created/modified in Phase 3:
- `scripts/skevals.py` — argparse CLI with 6 subcommands (eval, analyze, generate, run, judge, report) + --backend flag
- `skills/skevals/SKILL.md` — updated: uv run → python3, removed setup section, updated allowed-tools

### Verified:
- `python3 scripts/skevals.py --help` shows all 6 subcommands
- `python3 scripts/skevals.py eval --help` shows all options
- `python3 scripts/skevals.py analyze skills/skevals/` — end-to-end success, produced analysis.json with 10 capabilities, 6 dimensions
- One transient CLI error observed (response without structured_output) — resolved on retry. Added `is_error` check to backend.py for better error reporting.

## Read Order

1. This file
2. `plan.md` — Phase 4 section for tests + cleanup details

## Start At

Phase 4: Tests + cleanup
- Update tests in `tests/` to import from `scripts/` instead of `src/skevals/`
- Remove `src/skevals/` directory
- Simplify or remove `pyproject.toml`
- Run `claude plugin validate .` to verify plugin structure

## Key Constraints

- **Pyright warnings are expected**: `scripts/` uses `sys.path.insert()` for sibling imports which Pyright can't resolve statically. These work at runtime.
- **`--json-schema` needs `--max-turns 2`**: The CLI backend sets this automatically. Transient failures can occur; consider adding retry logic in Phase 4 if they persist.
- **`allowed-tools` in SKILL.md**: Changed to `Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/*)` — this pattern must match the actual invocation.
