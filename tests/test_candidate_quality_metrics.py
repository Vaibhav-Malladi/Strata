import json
from pathlib import Path

from strata.core.candidate_evaluation import (
    load_candidate_evaluation_manifest,
    validate_candidate_evaluation_manifest,
)
from strata.core.candidate_metrics import calculate_candidate_quality_metrics


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "candidate_quality"


def _task(*, empty_tiers: tuple[str, ...] = ()):
    tiers = {
        "critical": [{"path": "src/critical_a.py"}, {"path": "src/critical_b.py"}],
        "useful": [{"path": "src/useful_a.py"}, {"path": "src/useful_b.py"}],
        "distractor": [{"path": "src/distractor.py"}],
        "irrelevant": [{"path": "docs/irrelevant.md"}],
    }
    for tier in empty_tiers:
        tiers[tier] = []
    manifest = validate_candidate_evaluation_manifest(
        {
            "schema_version": 1,
            "tasks": [
                {
                    "id": "quality-task",
                    "task": "Fix critical behavior",
                    "fixture_path": "repo",
                    "tags": {
                        "stacks": ["test"],
                        "languages": ["python"],
                        "frameworks": [],
                    },
                    "expected_files": tiers,
                }
            ],
        }
    )
    return manifest.tasks[0]


def _expect_error(error_type, function, *args, contains: str, **kwargs):
    try:
        function(*args, **kwargs)
    except error_type as error:
        assert contains in str(error)
    else:
        raise AssertionError(f"Expected {error_type.__name__}")


def test_perfect_critical_recall_at_k():
    result = calculate_candidate_quality_metrics(
        _task(),
        ["src/critical_a.py", "src/critical_b.py"],
        2,
    )

    assert result.critical_recall_at_k == 1.0
    assert result.missed_critical_count == 0


def test_missed_critical_files_are_counted_at_k():
    result = calculate_candidate_quality_metrics(
        _task(),
        ["src/critical_a.py", "src/useful_a.py"],
        2,
    )

    assert result.critical_recall_at_k == 0.5
    assert result.missed_critical_count == 1


def test_useful_coverage_at_k():
    result = calculate_candidate_quality_metrics(
        _task(),
        ["src/useful_a.py", "src/critical_a.py"],
        2,
    )

    assert result.useful_coverage_at_k == 0.5


def test_distractor_rate_uses_evaluated_selection_count():
    result = calculate_candidate_quality_metrics(
        _task(),
        ["src/distractor.py", "src/critical_a.py"],
        2,
    )

    assert result.distractor_rate_at_k == 0.5


def test_context_waste_counts_distractor_and_irrelevant_paths():
    result = calculate_candidate_quality_metrics(
        _task(),
        ["src/distractor.py", "docs/irrelevant.md", "src/critical_a.py"],
        3,
    )

    assert result.context_waste_at_k == 2 / 3


def test_duplicate_and_equivalent_paths_do_not_inflate_or_consume_k():
    result = calculate_candidate_quality_metrics(
        _task(),
        ["src/critical_a.py", ".\\src\\critical_a.py", "src/critical_b.py"],
        2,
    )

    assert result.evaluated_count == 2
    assert result.critical_recall_at_k == 1.0


def test_k_smaller_than_selection_evaluates_only_top_k():
    result = calculate_candidate_quality_metrics(
        _task(),
        ["src/critical_a.py", "../outside-top-k.py"],
        1,
    )

    assert result.evaluated_count == 1
    assert result.critical_recall_at_k == 0.5
    assert result.useful_coverage_at_k == 0.0


def test_k_larger_than_selection_uses_selected_count_for_rates():
    result = calculate_candidate_quality_metrics(
        _task(),
        ["src/distractor.py"],
        10,
    )

    assert result.evaluated_count == 1
    assert result.distractor_rate_at_k == 1.0
    assert result.context_waste_at_k == 1.0


def test_empty_tiers_have_deterministic_metric_values():
    result = calculate_candidate_quality_metrics(
        _task(empty_tiers=("critical", "useful", "distractor", "irrelevant")),
        [],
        5,
    )

    assert result.critical_recall_at_k == 1.0
    assert result.useful_coverage_at_k == 1.0
    assert result.distractor_rate_at_k == 0.0
    assert result.missed_critical_count == 0
    assert result.context_waste_at_k == 0.0


def test_unknown_selected_paths_count_as_context_waste_only():
    result = calculate_candidate_quality_metrics(
        _task(empty_tiers=("distractor", "irrelevant")),
        ["src/unclassified.py", "src/critical_a.py"],
        2,
    )

    assert result.distractor_rate_at_k == 0.0
    assert result.context_waste_at_k == 0.5


def test_metrics_load_and_grade_a_g3_fixture_manifest():
    manifest = load_candidate_evaluation_manifest(
        FIXTURE_ROOT / "messy_python" / "manifest.json"
    )

    result = calculate_candidate_quality_metrics(
        manifest,
        ["app\\auth\\service.py", "app/auth/api.py", "app/auth/helpers.py"],
        3,
    )

    assert result.task_id == "python-auth-token-refresh"
    assert result.critical_recall_at_k == 1.0
    assert result.useful_coverage_at_k == 0.5
    assert result.context_waste_at_k == 0.0


def test_metric_result_has_stable_json_ready_shape():
    result = calculate_candidate_quality_metrics(
        _task(),
        ["src/critical_a.py"],
        1,
    )

    payload = result.to_dict()

    assert list(payload) == [
        "task_id",
        "k",
        "evaluated_count",
        "critical_recall_at_k",
        "useful_coverage_at_k",
        "distractor_rate_at_k",
        "missed_critical_count",
        "context_waste_at_k",
    ]
    assert json.loads(json.dumps(payload)) == payload


def test_invalid_k_and_unsafe_selected_paths_are_rejected():
    for invalid_k in (0, -1):
        _expect_error(
            ValueError,
            calculate_candidate_quality_metrics,
            _task(),
            [],
            invalid_k,
            contains="k",
        )
    for invalid_k in (True, 1.5):
        _expect_error(
            TypeError,
            calculate_candidate_quality_metrics,
            _task(),
            [],
            invalid_k,
            contains="k",
        )

    _expect_error(
        ValueError,
        calculate_candidate_quality_metrics,
        _task(),
        ["../outside.py"],
        1,
        contains="must not escape",
    )


TESTS = [
    test_perfect_critical_recall_at_k,
    test_missed_critical_files_are_counted_at_k,
    test_useful_coverage_at_k,
    test_distractor_rate_uses_evaluated_selection_count,
    test_context_waste_counts_distractor_and_irrelevant_paths,
    test_duplicate_and_equivalent_paths_do_not_inflate_or_consume_k,
    test_k_smaller_than_selection_evaluates_only_top_k,
    test_k_larger_than_selection_uses_selected_count_for_rates,
    test_empty_tiers_have_deterministic_metric_values,
    test_unknown_selected_paths_count_as_context_waste_only,
    test_metrics_load_and_grade_a_g3_fixture_manifest,
    test_metric_result_has_stable_json_ready_shape,
    test_invalid_k_and_unsafe_selected_paths_are_rejected,
]
