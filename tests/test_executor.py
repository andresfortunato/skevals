"""Tests for the session executor (now in runner.py)."""

from runner import _analyze_output_composition, _parse_claude_output


def test_parse_claude_output(sample_claude_output: dict) -> None:
    """_parse_claude_output correctly parses claude JSON output."""
    import json
    output = _parse_claude_output(json.dumps(sample_claude_output))

    assert "sample output" in output["result_text"]
    assert output["session_id"] == "test-session-123"
    assert output["duration_ms"] == 5000
    assert output["total_cost_usd"] == 0.0123
    assert output["usage"]["input_tokens"] == 1500
    assert output["usage"]["output_tokens"] == 200
    assert output["usage"]["cache_read_tokens"] == 500
    assert output["usage"]["cache_creation_tokens"] == 0


def test_parse_claude_output_empty() -> None:
    """_parse_claude_output handles empty input."""
    output = _parse_claude_output("")
    assert output["result_text"] == "[EMPTY OUTPUT]"


def test_parse_claude_output_plain_text() -> None:
    """_parse_claude_output handles non-JSON text."""
    output = _parse_claude_output("Just some plain text")
    assert output["result_text"] == "Just some plain text"


def test_analyze_output_composition() -> None:
    """_analyze_output_composition classifies code vs prose lines."""
    text = """Here is some explanation.

```python
def hello():
    print("hi")
```

And more text here.
Another line."""

    result = _analyze_output_composition(text)
    assert result["code_lines"] == 2  # def hello, print
    assert result["prose_lines"] == 3  # explanation, more text, another line
