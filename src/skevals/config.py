"""Default configuration and config loading."""

from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field


class EvalMode(str, Enum):
    """Evaluation mode controlling token usage vs depth tradeoff."""

    lite = "lite"  # Single-turn, text-only, haiku judge — fast and cheap
    full = "full"  # Multi-turn, tool use, sonnet judge — thorough but expensive

# Model aliases → full Anthropic model IDs
MODEL_ALIASES: dict[str, str] = {
    "sonnet": "claude-sonnet-4-20250514",
    "opus": "claude-opus-4-20250514",
    "haiku": "claude-haiku-4-5-20251001",
}

DEFAULT_MODEL = "sonnet"
DEFAULT_SCENARIOS = 6
DEFAULT_BUDGET_USD = 0.50
DEFAULT_SESSION_TIMEOUT = 300
DEFAULT_PARALLELISM = 2


class SkevalsConfig(BaseModel):
    """Runtime configuration."""

    model: str = Field(DEFAULT_MODEL, description="Model alias or full ID for judging/analysis")
    runner_model: str = Field(DEFAULT_MODEL, description="Model alias or full ID for Claude sessions")
    scenarios: int = DEFAULT_SCENARIOS
    budget_usd: float = DEFAULT_BUDGET_USD
    session_timeout_seconds: int = DEFAULT_SESSION_TIMEOUT
    parallelism: int = DEFAULT_PARALLELISM


def load_config(config_path: Path | None = None) -> SkevalsConfig:
    """Load config from file, falling back to defaults."""
    paths = [
        config_path,
        Path("skevals.json"),
        Path.home() / ".config" / "skevals" / "config.json",
    ]
    for p in paths:
        if p and p.exists():
            return SkevalsConfig.model_validate_json(p.read_text())
    return SkevalsConfig()


def resolve_model(alias: str) -> str:
    """Resolve a model alias to a full model ID."""
    return MODEL_ALIASES.get(alias, alias)
