"""Verification tests for Phase 1: backend.py + schemas.py

Tests the JSON fixup logic, backend selection, schema structure,
and (when credentials are available) live API/CLI calls.

Run: python scripts/test_backend.py
"""

from __future__ import annotations

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.backend import (
    _fix_stringified_json,
    get_backend,
    resolve_model,
    set_backend,
    structured_call,
)
from scripts.schemas import (
    COMPARISON_REPORT_SCHEMA,
    PAIRWISE_RESULT_SCHEMA,
    RUBRIC_RESULT_SCHEMA,
    SCENARIO_JUDGMENT_SCHEMA,
    SCENARIO_SET_SCHEMA,
    SKILL_ANALYSIS_SCHEMA,
    VERDICT_SCHEMA,
)


class TestModelAliases(unittest.TestCase):
    def test_known_aliases(self):
        assert "sonnet" in resolve_model("sonnet")
        assert "opus" in resolve_model("opus")
        assert "haiku" in resolve_model("haiku")

    def test_passthrough(self):
        assert resolve_model("claude-custom-model-id") == "claude-custom-model-id"


class TestBackendSelection(unittest.TestCase):
    def setUp(self):
        set_backend(None)  # reset to auto

    def tearDown(self):
        set_backend(None)

    def test_force_api(self):
        set_backend("api")
        assert get_backend() == "api"

    def test_force_cli(self):
        set_backend("cli")
        assert get_backend() == "cli"

    def test_invalid_backend(self):
        with self.assertRaises(ValueError):
            set_backend("invalid")

    def test_auto_detect_cli(self):
        # Temporarily remove API key
        key = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            set_backend(None)
            assert get_backend() == "cli"
        finally:
            if key:
                os.environ["ANTHROPIC_API_KEY"] = key

    def test_auto_detect_api(self):
        os.environ["ANTHROPIC_API_KEY"] = "test-key"
        try:
            set_backend(None)
            assert get_backend() == "api"
        finally:
            if os.environ.get("ANTHROPIC_API_KEY") == "test-key":
                del os.environ["ANTHROPIC_API_KEY"]


class TestJsonFixup(unittest.TestCase):
    def test_stringified_list(self):
        data = {"scores": '[{"a": 1}]'}
        fixed = _fix_stringified_json(data)
        assert fixed["scores"] == [{"a": 1}]

    def test_stringified_dict(self):
        data = {"nested": '{"key": "value"}'}
        fixed = _fix_stringified_json(data)
        assert fixed["nested"] == {"key": "value"}

    def test_plain_string_untouched(self):
        data = {"name": "hello world"}
        fixed = _fix_stringified_json(data)
        assert fixed["name"] == "hello world"

    def test_nested_dict_recursion(self):
        data = {"outer": {"inner": '[1,2,3]'}}
        fixed = _fix_stringified_json(data)
        assert fixed["outer"]["inner"] == [1, 2, 3]

    def test_list_of_dicts_recursion(self):
        data = {"items": [{"val": '{"a":1}'}, {"val": "plain"}]}
        fixed = _fix_stringified_json(data)
        assert fixed["items"][0]["val"] == {"a": 1}
        assert fixed["items"][1]["val"] == "plain"


class TestSchemaStructure(unittest.TestCase):
    """Validate that all schemas are well-formed JSON Schema objects."""

    SCHEMAS = {
        "SKILL_ANALYSIS_SCHEMA": SKILL_ANALYSIS_SCHEMA,
        "SCENARIO_SET_SCHEMA": SCENARIO_SET_SCHEMA,
        "RUBRIC_RESULT_SCHEMA": RUBRIC_RESULT_SCHEMA,
        "PAIRWISE_RESULT_SCHEMA": PAIRWISE_RESULT_SCHEMA,
        "SCENARIO_JUDGMENT_SCHEMA": SCENARIO_JUDGMENT_SCHEMA,
        "COMPARISON_REPORT_SCHEMA": COMPARISON_REPORT_SCHEMA,
        "VERDICT_SCHEMA": VERDICT_SCHEMA,
    }

    def test_all_are_objects(self):
        for name, schema in self.SCHEMAS.items():
            assert schema["type"] == "object", f"{name} is not type:object"

    def test_all_have_required(self):
        for name, schema in self.SCHEMAS.items():
            assert "required" in schema, f"{name} missing 'required'"
            assert len(schema["required"]) > 0, f"{name} has empty 'required'"

    def test_all_have_properties(self):
        for name, schema in self.SCHEMAS.items():
            assert "properties" in schema, f"{name} missing 'properties'"

    def test_serializable_to_json(self):
        for name, schema in self.SCHEMAS.items():
            try:
                json.dumps(schema)
            except (TypeError, ValueError) as e:
                self.fail(f"{name} is not JSON-serializable: {e}")


class TestLiveAPI(unittest.TestCase):
    """Live integration tests — only run when credentials are available."""

    def test_api_backend(self):
        if not os.environ.get("ANTHROPIC_API_KEY"):
            self.skipTest("ANTHROPIC_API_KEY not set")

        set_backend("api")
        try:
            result = structured_call(
                "Return a verdict saying 'test passed'.",
                VERDICT_SCHEMA,
                model="haiku",
                max_tokens=256,
            )
            assert isinstance(result, dict)
            assert "verdict" in result
            assert isinstance(result["verdict"], str)
            print(f"  API result: {result}")
        finally:
            set_backend(None)

    def test_cli_backend(self):
        # Check if claude CLI is available
        import shutil
        if not shutil.which("claude"):
            self.skipTest("claude CLI not found on PATH")

        set_backend("cli")
        try:
            result = structured_call(
                "Return a verdict saying 'test passed'.",
                VERDICT_SCHEMA,
                model="haiku",
                max_tokens=256,
            )
            assert isinstance(result, dict)
            assert "verdict" in result
            assert isinstance(result["verdict"], str)
            print(f"  CLI result: {result}")
        finally:
            set_backend(None)


if __name__ == "__main__":
    unittest.main(verbosity=2)
