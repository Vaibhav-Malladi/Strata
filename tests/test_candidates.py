from pathlib import Path
from unittest.mock import patch

from strata.core.candidates import (
    DEFAULT_SHORTLIST_LIMIT,
    compute_value_score,
    estimate_analysis_cost,
    normalize_task_tokens,
    rank_candidates,
    rank_candidates_by_value,
    score_candidate,
    score_candidate_value,
    shortlist_candidates,
)
from strata.core.inventory import InventoryRecord


def _record(
    path: str,
    *,
    folder_role: str = "source",
    language: str | None = "typescript",
    extension: str = ".ts",
    size: int = 100,
    is_test: bool = False,
    is_generated: bool = False,
) -> InventoryRecord:
    return InventoryRecord(
        path=path,
        extension=extension,
        size=size,
        mtime=1_700_000_000,
        is_test=is_test,
        is_generated_guess=is_generated,
        folder_role=folder_role,
        language_guess=language,
    )


def test_filename_keyword_match_ranks_above_unrelated_file():
    auth_service = _record("src/services/auth_service.ts")
    unrelated = _record("src/utils/format_date.ts")

    ranked = rank_candidates([unrelated, auth_service], "fix auth service bug")

    assert ranked[0].path == auth_service.path
    assert ranked[0].score > ranked[1].score
    assert any("filename matches task keyword 'auth'" in reason for reason in ranked[0].reasons)


def test_folder_segment_match_contributes_an_explainable_reason():
    result = score_candidate(
        _record("features/checkout/client.ts", folder_role="other"),
        "checkout flow",
    )

    assert result.score > 0
    assert "folder matches task keyword 'checkout' (+3)" in result.reasons


def test_generated_vendor_build_and_minified_records_are_strongly_demoted():
    source = _record("src/auth/client.js", language="javascript", extension=".js")
    cheap_matches = [
        _record(
            "dist/auth/client.js",
            folder_role="generated",
            language="javascript",
            extension=".js",
            is_generated=True,
        ),
        _record(
            "vendor/auth/client.js",
            folder_role="vendor",
            language="javascript",
            extension=".js",
            is_generated=True,
        ),
        _record(
            "build/auth/client.js",
            folder_role="generated",
            language="javascript",
            extension=".js",
            is_generated=True,
        ),
        _record(
            "src/auth/client.min.js",
            language="javascript",
            extension=".js",
            is_generated=True,
        ),
    ]

    source_score = score_candidate(source, "auth client").score
    for record in cheap_matches:
        result = score_candidate(record, "auth client")
        assert result.score < source_score
        assert any("generated or vendor path" in reason for reason in result.reasons)


def test_test_files_are_demoted_for_implementation_tasks():
    implementation = _record("src/checkout.ts")
    test_file = _record(
        "tests/checkout.spec.ts",
        folder_role="test",
        is_test=True,
    )

    ranked = rank_candidates([test_file, implementation], "change checkout flow")

    assert ranked[0].path == implementation.path
    test_result = next(item for item in ranked if item.path == test_file.path)
    assert "test file for implementation task (-12)" in test_result.reasons


def test_test_files_are_boosted_when_task_asks_for_tests():
    implementation = _record("src/checkout.ts")
    test_file = _record(
        "tests/checkout.spec.ts",
        folder_role="test",
        is_test=True,
    )

    ranked = rank_candidates([implementation, test_file], "add tests for checkout")

    assert ranked[0].path == test_file.path
    assert "task asks for tests (+8)" in ranked[0].reasons
    assert "test file for implementation task (-12)" not in ranked[0].reasons


def test_language_and_extension_relevance_are_transparent():
    result = score_candidate(
        _record("src/component.tsx", extension=".tsx"),
        "update typescript tsx component",
    )

    assert "language 'typescript' matches task (+2)" in result.reasons
    assert "extension '.tsx' matches task (+2)" in result.reasons


def test_scoring_does_not_stat_or_open_inventory_paths():
    record = _record("missing/auth_service.ts")

    with (
        patch.object(Path, "open", side_effect=AssertionError("opened candidate")),
        patch.object(Path, "stat", side_effect=AssertionError("statted candidate")),
    ):
        result = score_candidate(record, "auth service")

    assert result.path == record.path
    assert result.score > 0


def test_task_normalization_removes_stopwords_and_duplicates():
    assert normalize_task_tokens("Fix the Auth auth service bug") == ("auth", "service")


def test_shortlist_returns_highest_scores_first_and_preserves_reasons():
    records = [
        _record("src/zeta.ts"),
        _record("src/auth_service.ts"),
        _record("src/alpha.ts"),
    ]

    shortlist = shortlist_candidates(records, "fix auth service bug")

    assert [candidate.path for candidate in shortlist.candidates] == [
        "src/auth_service.ts",
        "src/alpha.ts",
        "src/zeta.ts",
    ]
    expected = score_candidate(records[1], "fix auth service bug")
    assert shortlist.candidates[0].reasons == expected.reasons


def test_shortlist_respects_cap_and_reports_truncation():
    records = [
        _record("src/auth_service.ts"),
        _record("src/auth_controller.ts"),
        _record("src/auth_model.ts"),
    ]

    shortlist = shortlist_candidates(records, "auth", limit=2)

    assert len(shortlist.candidates) == 2
    assert shortlist.files_considered == 3
    assert shortlist.candidates_returned == 2
    assert shortlist.cap == 2
    assert shortlist.truncated is True


def test_empty_shortlist_has_complete_summary_metadata():
    shortlist = shortlist_candidates([], "auth")

    assert shortlist.candidates == ()
    assert shortlist.files_considered == 0
    assert shortlist.candidates_returned == 0
    assert shortlist.cap == DEFAULT_SHORTLIST_LIMIT
    assert shortlist.truncated is False


def test_shortlist_rejects_invalid_limits():
    for invalid_limit in (0, -1):
        try:
            shortlist_candidates([], "auth", limit=invalid_limit)
        except ValueError as error:
            assert str(error) == "limit must be greater than zero"
        else:
            raise AssertionError(f"limit {invalid_limit} should be rejected")

    for invalid_limit in (True, 1.5):
        try:
            shortlist_candidates([], "auth", limit=invalid_limit)
        except TypeError as error:
            assert str(error) == "limit must be an integer"
        else:
            raise AssertionError(f"limit {invalid_limit!r} should be rejected")


def test_shortlist_does_not_stat_or_open_inventory_paths():
    records = [_record("missing/auth_service.ts"), _record("missing/routes.ts")]

    with (
        patch.object(Path, "open", side_effect=AssertionError("opened candidate")),
        patch.object(Path, "stat", side_effect=AssertionError("statted candidate")),
    ):
        shortlist = shortlist_candidates(records, "auth service", limit=1)

    assert shortlist.files_considered == 2
    assert shortlist.candidates[0].path == records[0].path


def test_analysis_cost_is_always_positive():
    assert estimate_analysis_cost(_record("src/empty.ts", size=0)) == 1
    assert compute_value_score(10, 1) == 10


def test_large_files_have_higher_analysis_cost_than_small_files():
    small = _record("src/auth_service.ts", size=4_000)
    large = _record("src/auth_service.ts", size=3 * 1024 * 1024)

    assert estimate_analysis_cost(large) > estimate_analysis_cost(small)


def test_generated_vendor_build_and_minified_records_have_low_value():
    source = _record("src/auth/client.ts")
    source_value = score_candidate_value(source, "auth client")
    low_value_records = [
        _record("dist/auth/client.ts", folder_role="generated", is_generated=True),
        _record("vendor/auth/client.ts", folder_role="vendor", is_generated=True),
        _record("build/auth/client.ts", folder_role="generated", is_generated=True),
        _record("src/auth/client.min.ts", is_generated=True),
    ]

    for record in low_value_records:
        candidate = score_candidate_value(record, "auth client")
        assert candidate.analysis_cost >= 20
        assert candidate.value_score < source_value.value_score
        assert "generated or vendor path (+20 cost)" in candidate.reasons


def test_value_ranking_prefers_similarly_relevant_smaller_file():
    huge = _record("src/huge/auth_service.ts", size=3 * 1024 * 1024)
    small = _record("src/small/auth_service.ts", size=4_000)

    ranked = rank_candidates_by_value([huge, small], "auth service")

    assert ranked[0].path == small.path
    assert ranked[0].cheap_score == ranked[1].cheap_score
    assert ranked[0].analysis_cost < ranked[1].analysis_cost


def test_value_ranking_keeps_tests_viable_when_task_asks_for_tests():
    implementation = _record("src/checkout.ts")
    test_file = _record(
        "tests/checkout.spec.ts",
        folder_role="test",
        is_test=True,
    )

    ranked = rank_candidates_by_value(
        [implementation, test_file],
        "add tests for checkout",
    )

    assert ranked[0].path == test_file.path
    assert "task asks for tests (+8)" in ranked[0].reasons


def test_value_ranking_is_deterministic_for_equal_candidates():
    alpha = _record("src/alpha.ts")
    zeta = _record("src/zeta.ts")

    ranked = rank_candidates_by_value([zeta, alpha], "unrelated task")

    assert [candidate.path for candidate in ranked] == [alpha.path, zeta.path]


def test_cost_value_layer_does_not_stat_or_open_inventory_paths():
    records = [
        _record("missing/auth_service.ts", size=4_000),
        _record("missing/auth_controller.ts", size=3 * 1024 * 1024),
    ]

    with (
        patch.object(Path, "open", side_effect=AssertionError("opened candidate")),
        patch.object(Path, "stat", side_effect=AssertionError("statted candidate")),
    ):
        ranked = rank_candidates_by_value(records, "auth", limit=1)

    assert ranked[0].path == records[0].path


TESTS = [
    test_filename_keyword_match_ranks_above_unrelated_file,
    test_folder_segment_match_contributes_an_explainable_reason,
    test_generated_vendor_build_and_minified_records_are_strongly_demoted,
    test_test_files_are_demoted_for_implementation_tasks,
    test_test_files_are_boosted_when_task_asks_for_tests,
    test_language_and_extension_relevance_are_transparent,
    test_scoring_does_not_stat_or_open_inventory_paths,
    test_task_normalization_removes_stopwords_and_duplicates,
    test_shortlist_returns_highest_scores_first_and_preserves_reasons,
    test_shortlist_respects_cap_and_reports_truncation,
    test_empty_shortlist_has_complete_summary_metadata,
    test_shortlist_rejects_invalid_limits,
    test_shortlist_does_not_stat_or_open_inventory_paths,
    test_analysis_cost_is_always_positive,
    test_large_files_have_higher_analysis_cost_than_small_files,
    test_generated_vendor_build_and_minified_records_have_low_value,
    test_value_ranking_prefers_similarly_relevant_smaller_file,
    test_value_ranking_keeps_tests_viable_when_task_asks_for_tests,
    test_value_ranking_is_deterministic_for_equal_candidates,
    test_cost_value_layer_does_not_stat_or_open_inventory_paths,
]
