import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from strata.core.candidate_evaluation import load_candidate_evaluation_manifest
from strata.core.candidate_pipeline import analyze_candidates_for_task
from strata.core.content_probe import probe_content
from strata.core.inventory import collect_inventory
from strata.core.probe_evaluation import (
    STRATEGIES,
    evaluate_probe_strategies_for_task,
    run_probe_evaluation_suite,
    score_probe_pool_entries,
)
from strata.core.probe_pool import build_probe_pool


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "candidate_quality"
EXPECTED_FIXTURES = {
    "external_style_small",
    "messy_angular",
    "messy_python",
    "messy_react",
    "strata_smoke",
}


def _fixture_task(name: str):
    manifest_path = FIXTURE_ROOT / name / "manifest.json"
    manifest = load_candidate_evaluation_manifest(manifest_path)
    return manifest.tasks[0], manifest_path.parent / "repo"


def test_comparison_includes_all_g3_fixture_tasks():
    report = run_probe_evaluation_suite(FIXTURE_ROOT, 3)

    assert {item.fixture_name for item in report.task_reports} == EXPECTED_FIXTURES
    assert len(report.task_reports) == 15
    assert report.to_dict()["task_count"] == 5


def test_all_three_strategies_are_present_for_each_task():
    report = run_probe_evaluation_suite(FIXTURE_ROOT, 3)
    by_task: dict[tuple[str, str], set[str]] = {}
    for item in report.task_reports:
        by_task.setdefault((item.fixture_name, item.task_id), set()).add(item.strategy)

    assert all(strategies == set(STRATEGIES) for strategies in by_task.values())


def test_each_strategy_report_includes_g4_metrics():
    report = run_probe_evaluation_suite(FIXTURE_ROOT, 3)

    for item in report.task_reports:
        payload = item.metrics.to_dict()
        assert "critical_recall_at_k" in payload
        assert "useful_coverage_at_k" in payload
        assert "distractor_rate_at_k" in payload
        assert "missed_critical_count" in payload
        assert "context_waste_at_k" in payload


def test_each_strategy_report_includes_stage_cost_fields():
    report = run_probe_evaluation_suite(FIXTURE_ROOT, 3)

    for item in report.task_reports:
        stage = item.stage_report.to_dict()
        assert "elapsed_ms" in stage
        assert "bytes_read" in stage
        assert "files_touched" in stage
        assert "warnings" in stage
        assert "skipped_items" in stage


def test_probe_strategy_records_read_cost_and_other_strategies_do_not():
    report = run_probe_evaluation_suite(FIXTURE_ROOT, 3)

    for item in report.task_reports:
        if item.strategy == "mixed_pool_probe":
            assert item.stage_report.bytes_read > 0
            assert item.stage_report.files_touched > 0
        else:
            assert item.stage_report.bytes_read == 0


def test_only_probe_stage_opens_fixture_content():
    task, fixture_repo = _fixture_task("messy_python")
    original_open = Path.open
    observed_modes: list[str] = []

    def guarded_open(path, mode="r", *args, **kwargs):
        if mode != "rb":
            raise AssertionError(f"unexpected content read mode: {mode}")
        observed_modes.append(mode)
        return original_open(path, mode, *args, **kwargs)

    with patch.object(Path, "open", new=guarded_open):
        reports = evaluate_probe_strategies_for_task(
            "messy_python",
            fixture_repo,
            task,
            3,
        )

    assert observed_modes
    assert {report.strategy for report in reports} == set(STRATEGIES)


def test_comparison_respects_k_for_every_strategy():
    report = run_probe_evaluation_suite(FIXTURE_ROOT, 2)

    for item in report.task_reports:
        assert item.k == 2
        assert len(item.selected_paths) <= 2
        assert item.metrics.k == 2
        assert item.metrics.evaluated_count <= 2


def test_aggregate_summary_is_deterministic_and_complete():
    first = run_probe_evaluation_suite(FIXTURE_ROOT, 3).to_dict()
    second = run_probe_evaluation_suite(FIXTURE_ROOT, 3).to_dict()

    assert first == second
    assert [summary["strategy"] for summary in first["strategy_summaries"]] == list(
        STRATEGIES
    )
    for summary in first["strategy_summaries"]:
        assert "average_critical_recall" in summary
        assert "total_missed_critical_count" in summary
        assert "average_useful_coverage" in summary
        assert "average_distractor_rate" in summary
        assert "average_context_waste" in summary
        assert "total_bytes_read" in summary
        assert "total_files_touched" in summary
    assert first["probe_cost_assessment"]["compared_to"] == "mixed_pool"


def test_comparison_output_is_json_serializable_without_custom_encoders():
    payload = run_probe_evaluation_suite(FIXTURE_ROOT, 3).to_dict()

    serialized = json.dumps(payload, allow_nan=False)

    assert json.loads(serialized) == payload


def test_comparison_does_not_mutate_current_candidate_selection():
    task, fixture_repo = _fixture_task("messy_python")
    before = analyze_candidates_for_task(fixture_repo, task.task_text, candidate_limit=3)

    evaluate_probe_strategies_for_task(
        "messy_python",
        fixture_repo,
        task,
        3,
    )
    after = analyze_candidates_for_task(fixture_repo, task.task_text, candidate_limit=3)

    assert before.selection == after.selection


def test_confidence_metadata_does_not_change_probe_scores_or_order():
    task, fixture_repo = _fixture_task("messy_python")
    records = collect_inventory(fixture_repo)
    pool = build_probe_pool(records, task.task_text, ["app/auth/service.py"])
    content = probe_content(fixture_repo, pool, task.task_text)
    low = replace(
        content,
        files=tuple(replace(item, confidence="low") for item in content.files),
    )
    high = replace(
        content,
        files=tuple(replace(item, confidence="high") for item in content.files),
    )

    low_scores = score_probe_pool_entries(pool, low)
    high_scores = score_probe_pool_entries(pool, high)

    assert [(item.path, item.final_score) for item in low_scores] == [
        (item.path, item.final_score) for item in high_scores
    ]


def test_mixed_pool_evaluation_includes_generic_rescue_candidates():
    task, fixture_repo = _fixture_task("messy_python")

    reports = evaluate_probe_strategies_for_task(
        "messy_python",
        fixture_repo,
        task,
        6,
    )
    mixed = next(report for report in reports if report.strategy == "mixed_pool")

    assert "app/auth/helpers.py" in mixed.selected_paths
    assert "app/auth/api.py" in mixed.selected_paths


TESTS = [
    test_comparison_includes_all_g3_fixture_tasks,
    test_all_three_strategies_are_present_for_each_task,
    test_each_strategy_report_includes_g4_metrics,
    test_each_strategy_report_includes_stage_cost_fields,
    test_probe_strategy_records_read_cost_and_other_strategies_do_not,
    test_only_probe_stage_opens_fixture_content,
    test_comparison_respects_k_for_every_strategy,
    test_aggregate_summary_is_deterministic_and_complete,
    test_comparison_output_is_json_serializable_without_custom_encoders,
    test_comparison_does_not_mutate_current_candidate_selection,
    test_confidence_metadata_does_not_change_probe_scores_or_order,
    test_mixed_pool_evaluation_includes_generic_rescue_candidates,
]
