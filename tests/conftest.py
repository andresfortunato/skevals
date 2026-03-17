"""Shared test fixtures for skevals."""

import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_skill_path() -> Path:
    return FIXTURES_DIR / "sample_skill"


@pytest.fixture
def sample_claude_output() -> dict:
    return json.loads((FIXTURES_DIR / "sample_claude_output.json").read_text())
