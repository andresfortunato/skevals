"""Thin wrapper around the Anthropic SDK for structured LLM calls."""

import json

import anthropic
from dotenv import load_dotenv
from pydantic import BaseModel

from skevals.config import resolve_model

load_dotenv()

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def structured_call(
    prompt: str,
    output_type: type[BaseModel],
    *,
    model: str = "sonnet",
    system: str | None = None,
    max_tokens: int = 16384,
) -> BaseModel:
    """Make an LLM call and parse the response into a Pydantic model.

    Uses anthropic's messages.parse() which handles structured output
    via tool_use under the hood — we get back a validated Pydantic instance.
    """
    client = _get_client()
    resolved = resolve_model(model)

    message = client.messages.create(
        model=resolved,
        max_tokens=max_tokens,
        system=system or "You are a helpful assistant. Respond with valid JSON matching the requested schema.",
        messages=[{"role": "user", "content": prompt}],
        tools=[
            {
                "name": "structured_output",
                "description": f"Output structured data as {output_type.__name__}",
                "input_schema": output_type.model_json_schema(),
            }
        ],
        tool_choice={"type": "tool", "name": "structured_output"},
    )

    # Extract the tool use block
    for block in message.content:
        if block.type == "tool_use" and block.name == "structured_output":
            raw = block.input
            # block.input may be a dict or a JSON string
            if isinstance(raw, str):
                raw = json.loads(raw)
            data = _fix_stringified_json(raw)
            try:
                return output_type.model_validate(data)
            except Exception:
                # Last resort: try json_loads on all string values recursively
                data = _deep_fix_json_strings(data)
                return output_type.model_validate(data)

    raise ValueError("No structured output block found in response")


def _deep_fix_json_strings(obj: object) -> object:
    """Aggressively try to parse any string that looks like JSON, recursively."""
    if isinstance(obj, dict):
        return {k: _deep_fix_json_strings(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_deep_fix_json_strings(item) for item in obj]
    if isinstance(obj, str):
        stripped = obj.strip()
        if stripped and stripped[0] in ("[", "{", '"') and len(stripped) > 1:
            try:
                parsed = json.loads(stripped)
                return _deep_fix_json_strings(parsed)
            except (json.JSONDecodeError, ValueError):
                pass
    return obj


def _fix_stringified_json(data: dict) -> dict:
    """Fix fields where a model returned JSON-as-string instead of actual JSON.

    Smaller models (haiku) sometimes serialize lists/dicts as JSON strings
    within tool_use input, e.g. "scores": "[{...}]" instead of "scores": [{...}].
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
        else:
            fixed[k] = v
    return fixed
