"""Tests for skill analyzer."""

from pathlib import Path

from analyzer import parse_skill_dir


def test_parse_skill_dir(sample_skill_path: Path) -> None:
    """parse_skill_dir extracts name, description, files from a skill directory."""
    manifest = parse_skill_dir(str(sample_skill_path))

    assert manifest["name"] == "sample-skill"
    assert manifest["description"] == "A sample skill for testing skevals"
    assert "SKILL.md" in manifest["files"]
    assert manifest["estimated_context_tokens"] > 0
    assert manifest["skill_md_content"].startswith("---")


def test_parse_skill_dir_missing(tmp_path: Path) -> None:
    """parse_skill_dir raises FileNotFoundError for missing SKILL.md."""
    import pytest
    with pytest.raises(FileNotFoundError):
        parse_skill_dir(str(tmp_path))
