"""Tests for judge data structures (dict-based)."""


def test_rubric_result_structure() -> None:
    """Rubric result dicts have the expected shape."""
    result = {
        "scores": [
            {"dimension_id": "quality", "score": 4, "reasoning": "Good quality"},
            {"dimension_id": "clarity", "score": 3, "reasoning": "Adequate clarity"},
        ],
        "expectation_results": [True, False],
        "weighted_overall": 3.5,
        "reasoning": "Overall decent output",
    }
    assert result["weighted_overall"] == 3.5
    assert len(result["scores"]) == 2
    assert result["expectation_results"] == [True, False]


def test_pairwise_result_structure() -> None:
    """Pairwise result dicts track winner and label mapping."""
    result = {
        "winner": "treatment",
        "label_map": {"A": "control", "B": "treatment"},
        "reasoning": "B was better because...",
        "strengths_a": ["concise"],
        "weaknesses_a": ["incomplete"],
        "strengths_b": ["thorough", "well-structured"],
        "weaknesses_b": [],
    }
    assert result["winner"] == "treatment"
    assert result["label_map"]["A"] == "control"
