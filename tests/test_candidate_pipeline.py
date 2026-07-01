from pathlib import Path
from unittest.mock import patch

from strata.core.candidate_pipeline import (
    CandidateAnalysis,
    CandidateAnalysisSummary,
    analyze_candidates_for_task,
    summarize_candidate_analysis,
)
from tests.helpers import temporary_repo


def test_candidate_pipeline_ranks_likely_task_file_first():
    with temporary_repo(
        {
            "src/auth_service.ts": "export const auth = true;\n",
            "src/format_date.ts": "export const formatDate = true;\n",
        }
    ) as root:
        analysis = analyze_candidates_for_task(root, "fix auth service bug")

    assert isinstance(analysis, CandidateAnalysis)
    assert analysis.selection.candidates[0].path.endswith("auth_service.ts")


def test_candidate_pipeline_respects_limits_and_reports_metadata():
    with temporary_repo(
        {
            "a_auth_service.ts": "a\n",
            "b_auth_model.ts": "b\n",
            "c_other.ts": "c\n",
        }
    ) as root:
        analysis = analyze_candidates_for_task(
            root,
            "auth",
            inventory_limit=2,
            candidate_limit=1,
        )

    assert analysis.inventory_records_count == 2
    assert analysis.inventory_limit == 2
    assert analysis.truncated_inventory is True
    assert analysis.candidate_limit == 1
    assert analysis.selection.files_considered == 2
    assert analysis.selection.candidates_returned == 1
    assert analysis.selection.truncated is True
    assert analysis.summary.candidates_selected == 1


def test_candidate_pipeline_handles_empty_directory():
    with temporary_repo() as root:
        analysis = analyze_candidates_for_task(root, "auth")

    assert analysis.inventory_records_count == 0
    assert analysis.truncated_inventory is False
    assert analysis.selection.candidates == ()
    assert analysis.summary.top_candidates == ()


def test_candidate_pipeline_does_not_open_file_contents():
    with temporary_repo(
        {
            "src/auth_service.ts": "content must remain unread\n",
            "src/auth_model.ts": "content must remain unread\n",
        }
    ) as root:
        with patch.object(Path, "open", side_effect=AssertionError("pipeline opened file")):
            analysis = analyze_candidates_for_task(root, "auth", candidate_limit=1)

    assert analysis.inventory_records_count == 2
    assert analysis.selection.candidates_returned == 1


def test_candidate_analysis_summary_reports_inventory_and_candidate_metadata():
    with temporary_repo(
        {
            "a_auth_service.ts": "a\n",
            "b_auth_model.ts": "b\n",
            "c_other.ts": "c\n",
        }
    ) as root:
        analysis = analyze_candidates_for_task(
            root,
            "auth",
            inventory_limit=2,
            candidate_limit=1,
        )

    summary = summarize_candidate_analysis(analysis)

    assert isinstance(summary, CandidateAnalysisSummary)
    assert summary.files_considered == 2
    assert summary.inventory_cap == 2
    assert summary.inventory_truncated is True
    assert summary.candidate_cap == 1
    assert summary.candidates_selected == 1
    assert summary.candidate_selection_truncated is True


def test_candidate_analysis_summary_caps_candidates_and_reasons():
    with temporary_repo(
        {
            "src/auth_service.ts": "service\n",
            "src/auth_controller.ts": "controller\n",
            "src/auth_model.ts": "model\n",
        }
    ) as root:
        analysis = analyze_candidates_for_task(root, "typescript auth service")

    summary = summarize_candidate_analysis(
        analysis,
        top_n=2,
        reasons_per_candidate=2,
    )

    assert len(summary.top_candidates) == 2
    assert all(len(candidate.reasons) <= 2 for candidate in summary.top_candidates)
    assert [candidate.path for candidate in summary.top_candidates] == [
        candidate.path for candidate in analysis.selection.candidates[:2]
    ]


def test_empty_candidate_analysis_has_valid_summary():
    with temporary_repo() as root:
        analysis = analyze_candidates_for_task(root, "auth")

    summary = summarize_candidate_analysis(analysis)

    assert summary.files_considered == 0
    assert summary.inventory_cap is None
    assert summary.inventory_truncated is False
    assert summary.candidate_cap == analysis.candidate_limit
    assert summary.candidates_selected == 0
    assert summary.candidate_selection_truncated is False
    assert summary.top_candidates == ()


def test_candidate_analysis_summary_rejects_invalid_top_n():
    with temporary_repo() as root:
        analysis = analyze_candidates_for_task(root, "auth")

    for invalid_value in (0, -1, True, 1.5):
        try:
            summarize_candidate_analysis(analysis, top_n=invalid_value)
        except (TypeError, ValueError):
            pass
        else:
            raise AssertionError(f"top_n {invalid_value!r} should be rejected")


def test_candidate_analysis_summary_rejects_invalid_reason_limit():
    with temporary_repo() as root:
        analysis = analyze_candidates_for_task(root, "auth")

    for invalid_value in (0, -1, True, 1.5):
        try:
            summarize_candidate_analysis(
                analysis,
                reasons_per_candidate=invalid_value,
            )
        except (TypeError, ValueError):
            pass
        else:
            raise AssertionError(
                f"reasons_per_candidate {invalid_value!r} should be rejected"
            )


def test_candidate_analysis_summary_does_not_access_paths():
    with temporary_repo({"missing-by-summary/auth_service.ts": "content\n"}) as root:
        analysis = analyze_candidates_for_task(root, "auth")

        with (
            patch.object(Path, "open", side_effect=AssertionError("summary opened file")),
            patch.object(Path, "stat", side_effect=AssertionError("summary statted file")),
        ):
            summary = summarize_candidate_analysis(analysis)

    assert summary.top_candidates[0].path.endswith("auth_service.ts")


TESTS = [
    test_candidate_pipeline_ranks_likely_task_file_first,
    test_candidate_pipeline_respects_limits_and_reports_metadata,
    test_candidate_pipeline_handles_empty_directory,
    test_candidate_pipeline_does_not_open_file_contents,
    test_candidate_analysis_summary_reports_inventory_and_candidate_metadata,
    test_candidate_analysis_summary_caps_candidates_and_reasons,
    test_empty_candidate_analysis_has_valid_summary,
    test_candidate_analysis_summary_rejects_invalid_top_n,
    test_candidate_analysis_summary_rejects_invalid_reason_limit,
    test_candidate_analysis_summary_does_not_access_paths,
]
