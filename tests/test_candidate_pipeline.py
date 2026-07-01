from pathlib import Path
from unittest.mock import patch

from strata.core.candidate_pipeline import CandidateAnalysis, analyze_candidates_for_task
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


TESTS = [
    test_candidate_pipeline_ranks_likely_task_file_first,
    test_candidate_pipeline_respects_limits_and_reports_metadata,
    test_candidate_pipeline_handles_empty_directory,
    test_candidate_pipeline_does_not_open_file_contents,
]
