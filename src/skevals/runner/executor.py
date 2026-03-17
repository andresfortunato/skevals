"""Claude CLI subprocess management for running evaluation sessions."""

import json
import os
import subprocess
from pathlib import Path

from skevals.config import EvalMode, resolve_model
from skevals.models.session import ClaudeOutput, SessionResult, TokenUsage, Turn


def run_session(
    scenario_id: str,
    prompt: str,
    condition: str,
    workspace_path: Path,
    plugin_dir: Path | None,
    model: str = "sonnet",
    budget: float = 0.50,
    timeout: int = 300,
    mode: EvalMode = EvalMode.lite,
) -> SessionResult:
    """Run a single Claude session and return the parsed result.

    A/B control mechanism:
    - Control: --disable-slash-commands (no skills loaded)
    - Treatment: --plugin-dir <dir> (skill loaded via plugin wrapper)
    Both: --print --output-format json --no-session-persistence
    Lite mode adds: --max-turns 1 (single-turn, no multi-round tool calls)
    """
    resolved_model = resolve_model(model)

    cmd = [
        "claude",
        "--print",
        "--output-format", "json",
        "--no-session-persistence",
        "--model", resolved_model,
        "--max-budget-usd", str(budget),
        "-p", prompt,
    ]

    if mode == EvalMode.lite:
        cmd.extend(["--max-turns", "1"])

    if condition == "control":
        cmd.append("--disable-slash-commands")
    elif condition == "treatment" and plugin_dir is not None:
        cmd.extend(["--plugin-dir", str(plugin_dir)])

    # Strip CLAUDECODE env var to allow nesting claude inside Claude Code
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(workspace_path),
            env=env,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return SessionResult(
            scenario_id=scenario_id,
            condition=condition,
            turns=[Turn(prompt=prompt, output=ClaudeOutput(result_text="[TIMEOUT]"))],
        )

    output = _parse_claude_output(result.stdout)

    # If result_text is empty, Claude likely used tool calls to write files.
    # Collect workspace changes as the "output" for the judge to score.
    if not output.result_text.strip():
        output.result_text = _collect_workspace_output(workspace_path)

    turn = Turn(prompt=prompt, output=output)

    return SessionResult(
        scenario_id=scenario_id,
        condition=condition,
        turns=[turn],
        total_duration_ms=output.duration_ms,
        total_duration_api_ms=output.duration_api_ms,
        total_cost_usd=output.total_cost_usd,
        total_usage=output.usage,
        output_composition=_analyze_output_composition(output.result_text),
    )


def _parse_claude_output(stdout: str) -> ClaudeOutput:
    """Parse JSON output from claude --print --output-format json."""
    if not stdout.strip():
        return ClaudeOutput(result_text="[EMPTY OUTPUT]")

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        # If not valid JSON, treat raw text as result
        return ClaudeOutput(result_text=stdout.strip())

    # The JSON format from claude --output-format json
    # Token counts: modelUsage.<model>.* has accurate per-model totals (camelCase)
    # usage.* has aggregates but input_tokens is often near-zero
    model_usage = _extract_model_usage(data)
    return ClaudeOutput(
        result_text=data.get("result", data.get("text", "")),
        session_id=data.get("session_id", ""),
        duration_ms=data.get("duration_ms", 0),
        duration_api_ms=data.get("duration_api_ms", 0),
        total_cost_usd=data.get("total_cost_usd", data.get("cost_usd", 0.0)),
        usage=model_usage,
    )


def _extract_model_usage(data: dict) -> TokenUsage:
    """Extract token counts from modelUsage (accurate) or usage (fallback)."""
    model_usage = data.get("modelUsage", {})
    if model_usage:
        # Sum across all models (usually just one)
        total_input = sum(m.get("inputTokens", 0) for m in model_usage.values())
        total_output = sum(m.get("outputTokens", 0) for m in model_usage.values())
        total_cache_read = sum(m.get("cacheReadInputTokens", 0) for m in model_usage.values())
        total_cache_create = sum(m.get("cacheCreationInputTokens", 0) for m in model_usage.values())
        return TokenUsage(
            input_tokens=total_input,
            output_tokens=total_output,
            cache_read_tokens=total_cache_read,
            cache_creation_tokens=total_cache_create,
        )

    # Fallback to usage dict
    usage = data.get("usage", {})
    return TokenUsage(
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
        cache_read_tokens=usage.get("cache_read_input_tokens", 0),
        cache_creation_tokens=usage.get("cache_creation_input_tokens", 0),
    )


_SKIP_DIRS = {".claude", "__pycache__", ".git", "node_modules"}
_MAX_FILE_SIZE = 50_000  # chars


def _collect_workspace_output(workspace_path: Path) -> str:
    """Collect files created/modified in workspace as text for the judge.

    When Claude uses tool calls (Write/Edit) instead of producing text output,
    the result_text is empty. This collects the workspace files so the judge
    has something meaningful to score.
    """
    parts: list[str] = []
    ws = Path(workspace_path)

    for path in sorted(ws.rglob("*")):
        if path.is_dir():
            continue
        if any(skip in path.parts for skip in _SKIP_DIRS):
            continue
        rel = path.relative_to(ws)
        try:
            content = path.read_text(errors="replace")
        except (OSError, UnicodeDecodeError):
            continue
        if len(content) > _MAX_FILE_SIZE:
            content = content[:_MAX_FILE_SIZE] + "\n... [truncated]"
        parts.append(f"--- {rel} ---\n{content}")

    if not parts:
        return "[No files created in workspace]"
    return "[Claude wrote files via tool use]\n\n" + "\n\n".join(parts)


def _analyze_output_composition(text: str) -> dict[str, int]:
    """Heuristically classify output lines as code vs prose."""
    code_lines = 0
    prose_lines = 0
    in_code_block = False

    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if not stripped:
            continue
        if in_code_block:
            code_lines += 1
        else:
            prose_lines += 1

    return {"code_lines": code_lines, "prose_lines": prose_lines}
