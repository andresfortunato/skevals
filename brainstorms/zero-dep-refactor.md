# Zero-Dependency Refactor — Brainstorming Summary

## Problem

skevals currently requires PyPI dependencies (anthropic, pydantic, typer, rich, python-dotenv) which makes it impossible to distribute as a native Claude Code plugin. The plugin ecosystem expects zero-dep scripts that run directly with `python`. We need to eliminate all external dependencies while maintaining structured output quality.

## Decisions Made

- **Replace Anthropic SDK with `claude --print --json-schema`**: The Claude CLI's `--json-schema` flag produces validated structured output in a `structured_output` field of the JSON response. This is functionally equivalent to the SDK's `tool_use` structured output. Tested and confirmed working — see below.
  - `claude --print --output-format json --json-schema '{...}' -p "prompt"` returns `{"structured_output": {...}}` matching the schema.
  - This eliminates the `anthropic` and `python-dotenv` dependencies entirely.
  - It uses whatever auth the user already has in Claude Code — no separate `ANTHROPIC_API_KEY` needed.

- **Replace Pydantic with plain dicts + dataclasses**: The structured output from `--json-schema` returns plain JSON. We validate with JSON Schema at the CLI level, then work with dicts or stdlib `dataclasses` in Python. No Pydantic needed.
  - Trade-off: we lose Pydantic's validation/serialization niceties, but for this use case (passing data between pipeline stages via JSON files), dicts are fine.

- **Replace Typer with argparse**: stdlib `argparse` provides the same CLI functionality. We lose Typer's auto-generated help formatting and type coercion, but the CLI is simple enough (6 commands, ~5 options each) that argparse handles it cleanly.

- **Replace Rich with plain print**: Progress bars and colored output are nice-to-have, not essential. Plain `print()` with simple formatting works. We can add ANSI colors manually if needed (they're just escape codes, no library required).

- **All LLM calls go through `claude --print`**: Both the A/B test sessions AND the analyzer/generator/judge calls use the same mechanism. This means:
  - One subprocess interface, not two (SDK + CLI)
  - Consistent auth (Claude Code's built-in auth)
  - Consistent model resolution
  - The `CLAUDECODE` env stripping pattern applies to all calls uniformly

## Research Findings

- **`--json-schema` test result**: `claude --print --output-format json --json-schema '{"type":"object",...}' -p "prompt"` successfully returns structured output in `response["structured_output"]`. The schema is enforced by the CLI. Requires `--max-turns` > 1 (Claude needs a turn to produce the structured output after its text response).
- **`--max-turns 1` issue**: With `--max-turns 1`, structured output sometimes fails with "Reached max turns" because Claude uses one turn for text and needs another for the structured output tool call. Need `--max-turns 2` minimum for json-schema calls.
- **Official plugins pattern**: All 13 official Anthropic plugins and community plugins use zero external dependencies. Scripts use stdlib + assume basic tools are available.
- **Budget overhead**: Each `claude --print` call has ~20-30K tokens of system prompt overhead. This was already the dominant cost. Replacing SDK calls with CLI calls means the judge/analyzer calls will be more expensive per-call (CLI overhead vs direct API), but we save the setup friction entirely.

## Open Questions

- **Cost increase from CLI overhead on judge calls**: Currently SDK judge calls are ~3K input tokens. CLI calls will be ~25K+ (system prompt). For 10 judge calls that's 250K extra tokens. Is this acceptable given the UX improvement of zero deps?
- **`--max-turns` for structured output**: Need to verify the minimum turns needed. If it's always 2, we need to account for that in timeout and budget calculations.

## Constraints Identified

- **No pip dependencies**: Plugin must run with `python script.py` using only stdlib.
- **JSON Schema instead of Pydantic**: All structured output schemas must be expressed as JSON Schema (which `--json-schema` accepts), not Pydantic models.
- **CLI calls are more expensive**: Each `claude --print` call costs ~20-30K tokens of overhead vs ~0 for a direct API call. This is the trade-off for zero-dep distribution.
- **Auth is implicit**: No API key management needed — but the user must have Claude Code authenticated.
