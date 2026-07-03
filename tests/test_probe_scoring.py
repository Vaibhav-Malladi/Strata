import json
import math
from pathlib import Path
from unittest.mock import patch

from strata.core.probe_scoring import (
    DEFAULT_PROBE_SCORE_WEIGHTS,
    ProbeScoreWeights,
    score_probe_entry,
    sort_probe_scores,
)


def _score(path: str = "src/service.py", **overrides):
    values = {
        "cheap_relevance": 0.8,
        "probe_relevance": 0.6,
        "structural_relevance": 0.5,
        "normalized_cost": 0.2,
        "confidence": "medium",
    }
    values.update(overrides)
    return score_probe_entry(path, **values)


def _expect_error(error_type, function, *args, contains: str, **kwargs):
    try:
        function(*args, **kwargs)
    except error_type as error:
        assert contains in str(error)
    else:
        raise AssertionError(f"Expected {error_type.__name__}")


def test_default_probe_score_formula_is_exact():
    result = _score()
    expected = 0.35 * 0.8 + 0.30 * 0.6 + 0.20 * 0.5 - 0.15 * 0.2

    assert result.final_score == expected
    assert result.weights is DEFAULT_PROBE_SCORE_WEIGHTS


def test_all_probe_components_must_be_normalized():
    component_names = (
        "cheap_relevance",
        "probe_relevance",
        "structural_relevance",
        "normalized_cost",
    )
    for component_name in component_names:
        for invalid_value in (-0.01, 1.01, float("inf"), float("nan")):
            _expect_error(
                ValueError,
                _score,
                **{component_name: invalid_value},
                contains=component_name,
            )
        for invalid_value in (True, "0.5", None):
            _expect_error(
                TypeError,
                _score,
                **{component_name: invalid_value},
                contains=component_name,
            )


def test_normalized_cost_subtracts_from_final_score():
    free = _score(normalized_cost=0.0)
    expensive = _score(normalized_cost=1.0)

    assert math.isclose(
        free.final_score - expensive.final_score,
        0.15,
        rel_tol=0.0,
        abs_tol=1e-12,
    )


def test_confidence_is_metadata_only():
    results = [
        _score(confidence=confidence)
        for confidence in ("unknown", "low", "medium", "high")
    ]

    assert {result.final_score for result in results} == {results[0].final_score}
    assert [result.confidence for result in results] == [
        "unknown",
        "low",
        "medium",
        "high",
    ]


def test_invalid_confidence_is_rejected():
    _expect_error(
        ValueError,
        _score,
        confidence="certain",
        contains="confidence must be one of",
    )


def test_probe_scores_sort_deterministically_by_score_then_path():
    low = _score("src/z.py", cheap_relevance=0.1)
    tied_z = _score("src/z.py")
    tied_a = _score("src/a.py")

    ordered = sort_probe_scores([low, tied_z, tied_a])

    assert ordered == (tied_a, tied_z, low)


def test_probe_score_output_is_json_ready_and_stable():
    payload = _score().to_dict()

    assert list(payload) == [
        "path",
        "cheap_relevance",
        "probe_relevance",
        "structural_relevance",
        "normalized_cost",
        "final_score",
        "confidence",
        "weights",
    ]
    assert json.loads(json.dumps(payload, allow_nan=False)) == payload


def test_custom_weights_are_validated_and_applied():
    weights = ProbeScoreWeights(
        cheap_weight=0.4,
        probe_weight=0.3,
        structural_weight=0.2,
        cost_weight=0.1,
    )
    result = _score(weights=weights)
    expected = 0.4 * 0.8 + 0.3 * 0.6 + 0.2 * 0.5 - 0.1 * 0.2

    assert result.final_score == expected
    assert result.weights == weights

    _expect_error(
        ValueError,
        ProbeScoreWeights,
        cheap_weight=0.5,
        probe_weight=0.5,
        structural_weight=0.5,
        cost_weight=0.5,
        contains="sum to 1.0",
    )


def test_probe_score_paths_use_portable_relative_normalization():
    result = _score(".\\src\\feature\\service.py")

    assert result.path == "src/feature/service.py"

    _expect_error(
        ValueError,
        _score,
        "../outside.py",
        contains="must not escape",
    )


def test_probe_scoring_does_not_access_filesystem_content_or_metadata():
    with (
        patch("builtins.open", side_effect=AssertionError("opened file")),
        patch.object(Path, "read_text", side_effect=AssertionError("read file")),
        patch.object(Path, "stat", side_effect=AssertionError("statted file")),
    ):
        result = _score("src/service.py")
        ordered = sort_probe_scores([result])

    assert ordered == (result,)


TESTS = [
    test_default_probe_score_formula_is_exact,
    test_all_probe_components_must_be_normalized,
    test_normalized_cost_subtracts_from_final_score,
    test_confidence_is_metadata_only,
    test_invalid_confidence_is_rejected,
    test_probe_scores_sort_deterministically_by_score_then_path,
    test_probe_score_output_is_json_ready_and_stable,
    test_custom_weights_are_validated_and_applied,
    test_probe_score_paths_use_portable_relative_normalization,
    test_probe_scoring_does_not_access_filesystem_content_or_metadata,
]
