"""Dual LLM backend — routes structured calls to Anthropic API or Claude CLI.

Backend selection:
  1. Explicit --backend api|cli  (set via set_backend())
  2. Auto-detect: ANTHROPIC_API_KEY present → api, absent → cli

API path:  urllib POST to api.anthropic.com/v1/messages with tool_use
CLI path:  claude --print --output-format json --json-schema '...'
"""

from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request

# ---------------------------------------------------------------------------
# Model aliases
# ---------------------------------------------------------------------------

MODEL_ALIASES: dict[str, str] = {
    "sonnet": "claude-sonnet-4-20250514",
    "opus": "claude-opus-4-20250514",
    "haiku": "claude-haiku-4-5-20251001",
}


def resolve_model(alias: str) -> str:
    """Resolve a short alias to a full Anthropic model ID."""
    return MODEL_ALIASES.get(alias, alias)


# ---------------------------------------------------------------------------
# Backend state
# ---------------------------------------------------------------------------

_forced_backend: str | None = None  # "api" | "cli" | None (auto)


def set_backend(backend: str | None) -> None:
    """Force a specific backend. Pass None to revert to auto-detection."""
    global _forced_backend
    if backend is not None and backend not in ("api", "cli"):
        raise ValueError(f"Invalid backend {backend!r} — must be 'api', 'cli', or None")
    _forced_backend = backend


def get_backend() -> str:
    """Return the active backend name ('api' or 'cli')."""
    if _forced_backend:
        return _forced_backend
    return "api" if os.environ.get("ANTHROPIC_API_KEY") else "cli"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def structured_call(
    prompt: str,
    schema: dict,
    *,
    model: str = "sonnet",
    system: str | None = None,
    max_tokens: int = 16384,
) -> dict:
    """Make an LLM call and return a dict conforming to *schema*.

    Routes to API or CLI backend based on configuration.
    """
    backend = get_backend()
    if backend == "api":
        return _api_call(prompt, schema, model=model, system=system, max_tokens=max_tokens)
    return _cli_call(prompt, schema, model=model, system=system, max_tokens=max_tokens)


# ---------------------------------------------------------------------------
# API backend  (urllib → api.anthropic.com)
# ---------------------------------------------------------------------------

_API_URL = "https://api.anthropic.com/v1/messages"
_API_VERSION = "2023-06-01"

_DEFAULT_SYSTEM = "You are a helpful assistant. Respond with valid JSON matching the requested schema."


def _api_call(
    prompt: str,
    schema: dict,
    *,
    model: str,
    system: str | None,
    max_tokens: int,
) -> dict:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY not set — cannot use API backend")

    resolved = resolve_model(model)
    tool_name = "structured_output"

    body = {
        "model": resolved,
        "max_tokens": max_tokens,
        "system": system or _DEFAULT_SYSTEM,
        "messages": [{"role": "user", "content": prompt}],
        "tools": [
            {
                "name": tool_name,
                "description": "Output structured data matching the schema",
                "input_schema": schema,
            }
        ],
        "tool_choice": {"type": "tool", "name": tool_name},
    }

    data = json.dumps(body).encode()
    req = urllib.request.Request(
        _API_URL,
        data=data,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": api_key,
            "Anthropic-Version": _API_VERSION,
        },
    )

    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        err_body = e.read().decode() if e.fp else ""
        raise RuntimeError(f"Anthropic API error {e.code}: {err_body}") from e

    # Extract tool_use block
    for block in result.get("content", []):
        if block.get("type") == "tool_use" and block.get("name") == tool_name:
            raw = block.get("input", {})
            if isinstance(raw, str):
                raw = json.loads(raw)
            return _fix_stringified_json(raw)

    raise ValueError(
        f"No structured output in API response. Content types: "
        f"{[b.get('type') for b in result.get('content', [])]}"
    )


# ---------------------------------------------------------------------------
# CLI backend  (claude --print --json-schema)
# ---------------------------------------------------------------------------

def _cli_call(
    prompt: str,
    schema: dict,
    *,
    model: str,
    system: str | None,
    max_tokens: int,  # noqa: ARG001 — accepted for interface parity with API backend
) -> dict:
    resolved = resolve_model(model)
    schema_str = json.dumps(schema, separators=(",", ":"))

    cmd = [
        "claude",
        "--print",
        "--output-format", "json",
        "--model", resolved,
        "--max-turns", "2",
        "--json-schema", schema_str,
        "-p", prompt,
    ]
    if system:
        cmd.extend(["--system-prompt", system])

    # Strip CLAUDE* env vars so the subprocess doesn't inherit plugin context
    env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE")}
    # Ensure PATH is preserved
    if "PATH" not in env:
        env["PATH"] = os.environ.get("PATH", "/usr/bin:/bin")

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"claude CLI failed (exit {result.returncode}):\n{result.stderr[:500]}"
        )

    response = json.loads(result.stdout)

    # Check for errors in the response
    if response.get("is_error"):
        errors = response.get("errors") or response.get("result", "Unknown error")
        raise RuntimeError(f"claude CLI returned an error: {errors}")

    # --json-schema puts validated output in "structured_output"
    structured = response.get("structured_output")
    if structured is not None:
        if isinstance(structured, str):
            structured = json.loads(structured)
        return _fix_stringified_json(structured)

    # Fallback: try to parse result_text as JSON
    result_text = response.get("result", "")
    if result_text:
        try:
            return _fix_stringified_json(json.loads(result_text))
        except (json.JSONDecodeError, ValueError):
            pass

    raise ValueError(
        f"No structured output in CLI response. Keys: {list(response.keys())}"
    )


# ---------------------------------------------------------------------------
# JSON fixup helpers  (ported from src/skevals/llm/client.py)
# ---------------------------------------------------------------------------

def _fix_stringified_json(data: dict) -> dict:
    """Fix fields where a model returned JSON-as-string instead of actual JSON.

    Smaller models sometimes serialize lists/dicts as JSON strings within
    tool_use input, e.g. "scores": "[{...}]" instead of "scores": [{...}].
    """
    fixed = {}
    for k, v in data.items():
        if isinstance(v, str) and v.strip() and v.strip()[0] in ("[", "{"):
            try:
                fixed[k] = json.loads(v)
            except (json.JSONDecodeError, ValueError):
                fixed[k] = v
        elif isinstance(v, dict):
            fixed[k] = _fix_stringified_json(v)
        elif isinstance(v, list):
            fixed[k] = [
                _fix_stringified_json(item) if isinstance(item, dict) else item
                for item in v
            ]
        else:
            fixed[k] = v
    return fixed
