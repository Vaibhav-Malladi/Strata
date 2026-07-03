import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from strata.core.candidate_baseline import (
    run_candidate_baseline_suite,
    run_candidate_baseline_task,
)
from strata.core.candidate_evaluation import load_candidate_evaluation_manifest


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "candidate_quality"
EXPECTED_FIXTURES = {
    "external_style_small",
    "messy_angular",
    "messy_python",
    "messy_react",
    "strata_smoke",
}


def _expect_error(error_type, function, *args, contains: str, **kwargs):
    try:
        function(*args, **kwargs)
    except error_type as error:
        assert contains in str(error)
    else:
        raise AssertionError(f"Expected {error_type.__name__}")


def _messy_python_task():
    manifest_path = FIXTURE_ROOT / "messy_python" / "manifest.json"
    manifest = load_candidate_evaluation_manifest(manifest_path)
    return manifest.tasks[0], manifest_path.parent / "repo"


def test_baseline_report_generation_is_deterministic():
    first = run_candidate_baseline_suite(FIXTURE_ROOT, 3).to_dict()
    second = run_candidate_baseline_suite(FIXTURE_ROOT, 3).to_dict()

    assert first == second


def test_baseline_report_includes_every_g3_fixture_task():
    report = run_candidate_baseline_suite(FIXTURE_ROOT, 3)

    assert {task.fixture_name for task in report.task_reports} == EXPECTED_FIXTURES
    assert len(report.task_reports) == 5
    assert report.to_dict()["task_count"] == 5


def test_task_reports_include_ranked_paths_and_g4_metrics():
    report = run_candidate_baseline_suite(FIXTURE_ROOT, 3)

    for task_report in report.task_reports:
        assert task_report.selected_paths
        assert task_report.metrics.task_id == task_report.task_id
        assert task_report.metrics.k == 3
        metric_payload = task_report.to_dict()["metrics"]
        assert "critical_recall_at_k" in metric_payload
        assert "useful_coverage_at_k" in metric_payload
        assert "distractor_rate_at_k" in metric_payload
        assert "missed_critical_count" in metric_payload
        assert "context_waste_at_k" in metric_payload


def test_task_reports_include_stage_and_cost_fields():
    report = run_candidate_baseline_suite(FIXTURE_ROOT, 3)

    for task_report in report.task_reports:
        stage = task_report.stage_report
        assert stage.stage_name == "candidate_baseline"
        assert stage.bytes_read == 0
        assert stage.files_touched > 0
        assert stage.elapsed_ms == 0.0
        assert stage.outputs["selected_paths"] == task_report.selected_paths
        assert stage.metrics["critical_recall_at_k"] == (
            task_report.metrics.critical_recall_at_k
        )


def test_optional_clock_records_elapsed_milliseconds():
    task, fixture_repo = _messy_python_task()
    readings = iter((1_000_000, 3_500_000))

    report = run_candidate_baseline_task(
        "messy_python",
        fixture_repo,
        task,
        3,
        clock_ns=lambda: next(readings),
    )

    assert report.stage_report.elapsed_ms == 2.5


def test_baseline_report_respects_k():
    report = run_candidate_baseline_suite(FIXTURE_ROOT, 2)

    for task_report in report.task_reports:
        assert len(task_report.selected_paths) <= 2
        assert task_report.k == 2
        assert task_report.metrics.k == 2
        assert task_report.metrics.evaluated_count <= 2


def test_missing_and_empty_fixture_directories_have_deterministic_errors():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        missing = root / "missing"
        _expect_error(
            FileNotFoundError,
            run_candidate_baseline_suite,
            missing,
            3,
            contains=f"candidate baseline fixture directory does not exist: {missing}",
        )
        _expect_error(
            ValueError,
            run_candidate_baseline_suite,
            root,
            3,
            contains=f"candidate baseline fixture directory contains no manifests: {root}",
        )


def test_baseline_candidate_stage_does_not_open_file_contents():
    task, fixture_repo = _messy_python_task()

    with patch.object(
        Path,
        "open",
        side_effect=AssertionError("baseline opened fixture content"),
    ):
        report = run_candidate_baseline_task(
            "messy_python",
            fixture_repo,
            task,
            3,
        )

    assert report.selected_paths
    assert report.stage_report.bytes_read == 0


def test_aggregate_baseline_report_is_json_serializable():
    payload = run_candidate_baseline_suite(FIXTURE_ROOT, 3).to_dict()

    serialized = json.dumps(payload, allow_nan=False)

    assert json.loads(serialized) == payload


TESTS = [
    test_baseline_report_generation_is_deterministic,
    test_baseline_report_includes_every_g3_fixture_task,
    test_task_reports_include_ranked_paths_and_g4_metrics,
    test_task_reports_include_stage_and_cost_fields,
    test_optional_clock_records_elapsed_milliseconds,
    test_baseline_report_respects_k,
    test_missing_and_empty_fixture_directories_have_deterministic_errors,
    test_baseline_candidate_stage_does_not_open_file_contents,
    test_aggregate_baseline_report_is_json_serializable,
]
