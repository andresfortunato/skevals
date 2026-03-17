# Token Reduction Plan: Lite Mode

## Goal

Add `--lite` / `--full` mode selection to skevals eval. Lite mode targets <500K tokens for 3 scenarios (vs ~1M in full mode) by constraining CLI sessions to single-turn text responses and using haiku for judging.

## Decisions Made

1. **Two modes, not a rewrite** -- `--full` is the existing behavior (multi-turn, tool use, file output). `--lite` constrains to single-turn text responses and cheaper judging. Default is `--lite`.
2. **Lite mode differences from full:**
   - `--max-turns 1` on CLI sessions (no multi-round tool calls)
   - Scenario gen produces text-response tasks (no file creation prompts)
   - Ground files capped: max 2 files, 500 chars each
   - Judge output truncated to ~2K tokens before scoring
   - Judge uses haiku by default (overridable with `--judge-model`)
   - `max_tokens=2048` on judge SDK calls
3. **Full mode is unchanged** -- existing behavior, same code paths, no regressions.
4. **`--judge-model` is independent** -- works with both modes.

## Constraints

- No changes to existing full mode behavior
- A/B validity maintained in both modes
- Mode selection flows through the entire pipeline: scenario gen, executor, judge

## File Manifest

| File | Intent |
|------|--------|
| `config.py` | Add `EvalMode` enum (lite/full), `judge_model` field |
| `cli.py` | Add `--lite`/`--full` flag and `--judge-model` option to `eval` command |
| `generator/scenario_gen.py` | Accept `mode` param, constrain lite scenarios |
| `runner/executor.py` | Accept `mode` param, add `--max-turns 1` for lite |
| `runner/orchestrator.py` | Pass mode through to executor |
| `judge/rubric.py` | Accept `max_output_chars` param, truncate output |
| `judge/pairwise.py` | Accept `max_output_chars` param, truncate outputs |

## Phases

### Phase 1: Config + CLI plumbing
- Add `EvalMode` to config, wire `--lite`/`--full` and `--judge-model` into CLI
- Verification: `skevals eval --help` shows the new options

### Phase 2: Lite executor + scenario gen
- `executor.py`: add `--max-turns 1` when mode=lite
- `scenario_gen.py`: constrain prompt to text-response tasks, cap ground_files
- Verification: lite scenarios generate simpler tasks, CLI sessions complete faster

### Phase 3: Judge truncation + haiku default
- Truncate output before sending to judges, cap `max_tokens=2048`
- Lite mode defaults `judge_model` to haiku
- Verification: run full eval in lite mode, compare token count to previous ~1M baseline
