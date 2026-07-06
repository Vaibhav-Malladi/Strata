import json
import tempfile
from pathlib import Path

from strata.core.candidate_baseline import run_candidate_baseline_suite
from strata.core.dependency_trace_evaluation import evaluate_dependency_tracing


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "candidate_quality"


def _write_no_edge_fixture(root: Path) -> None:
    fixture = root / "no_edges"
    repo = fixture / "repo"
    repo.mkdir(parents=True)
    (repo / "main.py").write_text("VALUE = 1\n", encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "tasks": [
            {
                "id": "no-edge-task",
                "task": "Update the main value",
                "fixture_path": "repo",
                "tags": {
                    "stacks": ["library"],
                    "languages": ["python"],
                    "frameworks": [],
                },
                "expected_files": {
                    "critical": [{"path": "main.py"}],
                    "useful": [],
                    "distractor": [],
                    "irrelevant": [],
                },
            }
        ],
    }
    (fixture / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )


def test_evaluation_includes_all_part_g_fixture_tasks():
    report = evaluate_dependency_tracing(FIXTURE_ROOT)
    expected = {
        path.parent.name
        for path in FIXTURE_ROOT.glob("*/manifest.json")
    }

    assert {task.fixture_name for task in report.task_reports} == expected
    assert len(report.task_reports) == 5


def test_before_after_metrics_and_deltas_are_present_and_deterministic():
    first = evaluate_dependency_tracing(FIXTURE_ROOT)
    second = evaluate_dependency_tracing(FIXTURE_ROOT)

    assert first.to_dict() == second.to_dict()
    for task in first.task_reports:
        assert task.metrics_before.task_id == task.task_id
        assert task.metrics_after.task_id == task.task_id
        assert task.deltas.critical_recall_at_k == (
            task.metrics_after.critical_recall_at_k
            - task.metrics_before.critical_recall_at_k
        )


def test_aggregate_summary_is_json_ready_and_measures_cost():
    report = evaluate_dependency_tracing(FIXTURE_ROOT)
    payload = report.to_dict()

    assert payload["summary"]["total_files_touched"] > 0
    assert payload["summary"]["total_estimated_cost"] >= 0
    assert json.loads(json.dumps(payload, allow_nan=False)) == payload


def test_evaluation_does_not_mutate_candidate_selection_behavior():
    before = run_candidate_baseline_suite(FIXTURE_ROOT, 3).to_dict()

    evaluate_dependency_tracing(FIXTURE_ROOT)

    after = run_candidate_baseline_suite(FIXTURE_ROOT, 3).to_dict()
    assert after == before


def test_fixture_without_trace_edges_honestly_reports_no_improvement():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_no_edge_fixture(root)

        report = evaluate_dependency_tracing(root)

        assert report.task_reports[0].traced_edges == ()
        assert report.summary.tracing_improved_quality is False
        assert report.summary.tracing_appears_to_earn_cost is False
        assert report.summary.conclusion == "tracing_did_not_improve_fixture_quality"


def test_task_reports_record_baseline_seeds_edges_cost_and_skips():
    report = evaluate_dependency_tracing(FIXTURE_ROOT)

    for task in report.task_reports:
        assert task.baseline_selected_paths
        assert task.seed_files
        assert task.stage_report.files_touched >= 0
        assert task.stage_report.metrics["estimated_edge_cost"] >= 0
        assert task.stage_report.skipped_items == task.skipped_items


TESTS = [
    test_evaluation_includes_all_part_g_fixture_tasks,
    test_before_after_metrics_and_deltas_are_present_and_deterministic,
    test_aggregate_summary_is_json_ready_and_measures_cost,
    test_evaluation_does_not_mutate_candidate_selection_behavior,
    test_fixture_without_trace_edges_honestly_reports_no_improvement,
    test_task_reports_record_baseline_seeds_edges_cost_and_skips,
]
