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
    select_candidates,
    shortlist_candidates,
    summarize_candidate_selection,
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


def test_frontend_roles_add_bounded_task_match_reasons():
    cases = {
        "src/pages/DashboardPage.tsx": ("change dashboard page", "page"),
        "src/components/Nav.tsx": ("update component", "component"),
        "src/auth/auth.service.ts": ("update auth service", "service"),
        "src/hooks/useAuth.ts": ("change auth hook", "hook"),
        "src/api/authClient.ts": ("update auth api", "api_client"),
        "src/routes/AppRoutes.tsx": ("change app route", "route"),
        "src/store/userStore.ts": ("update user store", "state_store"),
        "src/forms/Login.tsx": ("update login form", "form"),
        "src/app/card/card.component.scss": ("update component style", "style"),
        "src/app/card/card.component.html": ("update card template", "template"),
    }

    for path, (task, role) in cases.items():
        result = score_candidate(_record(path), task)
        assert f"frontend role '{role}' matches task (+4)" in result.reasons


def test_ui_button_task_favors_recognized_frontend_role():
    frontend = _record(
        "src/app/login/login.component.html",
        language="html",
        extension=".html",
    )
    backend = _record(
        "backend/models/login.py",
        folder_role="other",
        language="python",
        extension=".py",
    )

    ranked = rank_candidates([backend, frontend], "fix login button")

    assert ranked[0].path == frontend.path
    assert "frontend role 'template' is relevant to task (+2)" in ranked[0].reasons


def test_frontend_role_boost_does_not_overcome_generated_demotion():
    source = _record("src/components/Button.tsx", extension=".tsx")
    generated = _record(
        "dist/components/Button.tsx",
        folder_role="generated",
        extension=".tsx",
        is_generated=True,
    )

    ranked = rank_candidates_by_value([generated, source], "update button component")

    assert ranked[0].path == source.path
    assert ranked[1].value_score < ranked[0].value_score
    assert "generated or vendor path (-100)" in ranked[1].reasons


def test_frontend_integration_preserves_test_task_behavior():
    implementation = _record("src/components/Checkout.tsx", extension=".tsx")
    test_file = _record(
        "src/components/Checkout.spec.tsx",
        folder_role="test",
        extension=".tsx",
        is_test=True,
    )

    implementation_ranked = rank_candidates(
        [test_file, implementation],
        "update checkout component",
    )
    test_ranked = rank_candidates([implementation, test_file], "test checkout component")

    assert implementation_ranked[0].path == implementation.path
    assert "test file for implementation task (-12)" in implementation_ranked[1].reasons
    assert test_ranked[0].path == test_file.path
    assert "task asks for tests (+8)" in test_ranked[0].reasons


def test_scoring_does_not_stat_or_open_inventory_paths():
    record = _record("missing/auth_service.ts")

    with (
        patch("builtins.open", side_effect=AssertionError("opened candidate")),
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


def test_select_candidates_returns_value_ranked_candidates():
    huge = _record("src/huge/auth_service.ts", size=3 * 1024 * 1024)
    small = _record("src/small/auth_service.ts", size=4_000)

    selection = select_candidates([huge, small], "auth service")

    assert [candidate.path for candidate in selection.candidates] == [
        small.path,
        huge.path,
    ]


def test_select_candidates_applies_cap_and_reports_summary():
    records = (
        _record(path)
        for path in ("src/auth_service.ts", "src/auth_model.ts", "src/other.ts")
    )

    selection = select_candidates(records, "auth", limit=2)

    assert selection.candidates_returned == 2
    assert selection.files_considered == 3
    assert selection.cap == 2
    assert selection.truncated is True


def test_select_candidates_accepts_empty_inventory():
    selection = select_candidates([], "auth")

    assert selection.candidates == ()
    assert selection.candidates_returned == 0
    assert selection.files_considered == 0
    assert selection.cap == DEFAULT_SHORTLIST_LIMIT
    assert selection.truncated is False


def test_select_candidates_rejects_limits_like_cheap_shortlist():
    invalid_limits = (
        (0, ValueError),
        (-1, ValueError),
        (True, TypeError),
        (1.5, TypeError),
    )
    for invalid_limit, error_type in invalid_limits:
        try:
            select_candidates([], "auth", limit=invalid_limit)
        except error_type:
            pass
        else:
            raise AssertionError(f"limit {invalid_limit!r} should be rejected")


def test_select_candidates_preserves_cheap_cost_and_value_reasons():
    selection = select_candidates(
        [_record("src/auth_service.ts", size=3 * 1024 * 1024)],
        "auth service",
    )

    candidate = selection.candidates[0]
    assert "filename matches task keyword 'auth' (+6)" in candidate.reasons
    assert "size above 2 MiB (cost 16)" in candidate.reasons
    assert any(reason.startswith("value score ") for reason in candidate.reasons)


def test_select_candidates_keeps_generated_records_eligible_but_low_value():
    source = _record("src/auth/client.ts")
    low_value_records = [
        _record("dist/auth/client.ts", folder_role="generated", is_generated=True),
        _record("vendor/auth/client.ts", folder_role="vendor", is_generated=True),
        _record("build/auth/client.ts", folder_role="generated", is_generated=True),
        _record("src/auth/client.min.ts", is_generated=True),
    ]

    selection = select_candidates(
        [*low_value_records, source],
        "auth client",
        limit=5,
    )

    assert selection.candidates[0].path == source.path
    assert {candidate.path for candidate in selection.candidates[1:]} == {
        record.path for record in low_value_records
    }
    assert all(candidate.analysis_cost >= 20 for candidate in selection.candidates[1:])


def test_select_candidates_does_not_stat_or_open_inventory_paths():
    records = [
        _record("missing/auth_service.ts", size=4_000),
        _record("missing/auth_model.ts", size=128_000),
    ]

    with (
        patch.object(Path, "open", side_effect=AssertionError("opened candidate")),
        patch.object(Path, "stat", side_effect=AssertionError("statted candidate")),
    ):
        selection = select_candidates(records, "auth", limit=1)

    assert selection.candidates_returned == 1
    assert selection.files_considered == 2


def test_candidate_summary_includes_selection_metadata():
    selection = select_candidates(
        [_record("src/auth_service.ts"), _record("src/auth_model.ts")],
        "auth",
        limit=1,
    )

    summary = summarize_candidate_selection(selection)

    assert summary.files_considered == 2
    assert summary.candidates_selected == 1
    assert summary.cap == 1
    assert summary.truncated is True


def test_candidate_summary_caps_candidates_and_reasons():
    selection = select_candidates(
        [
            _record("src/auth_service.ts"),
            _record("src/auth_controller.ts"),
            _record("src/auth_model.ts"),
        ],
        "typescript auth service",
    )

    summary = summarize_candidate_selection(
        selection,
        top_n=2,
        reasons_per_candidate=2,
    )

    assert len(summary.top_candidates) == 2
    assert all(len(candidate.reasons) <= 2 for candidate in summary.top_candidates)
    assert [candidate.path for candidate in summary.top_candidates] == [
        candidate.path for candidate in selection.candidates[:2]
    ]


def test_empty_candidate_selection_has_valid_summary():
    selection = select_candidates([], "auth")

    summary = summarize_candidate_selection(selection)

    assert summary.files_considered == 0
    assert summary.candidates_selected == 0
    assert summary.cap == DEFAULT_SHORTLIST_LIMIT
    assert summary.truncated is False
    assert summary.top_candidates == ()


def test_candidate_summary_rejects_invalid_bounds():
    selection = select_candidates([], "auth")
    invalid_values = (0, -1, True, 1.5)

    for invalid_value in invalid_values:
        try:
            summarize_candidate_selection(selection, top_n=invalid_value)
        except (TypeError, ValueError):
            pass
        else:
            raise AssertionError(f"top_n {invalid_value!r} should be rejected")

        try:
            summarize_candidate_selection(
                selection,
                reasons_per_candidate=invalid_value,
            )
        except (TypeError, ValueError):
            pass
        else:
            raise AssertionError(
                f"reasons_per_candidate {invalid_value!r} should be rejected"
            )


def test_candidate_summary_preserves_scores_and_bounded_reasons():
    selection = select_candidates(
        [_record("src/auth_service.ts", size=3 * 1024 * 1024)],
        "typescript auth service",
    )

    summary = summarize_candidate_selection(
        selection,
        reasons_per_candidate=2,
    )
    source = selection.candidates[0]
    item = summary.top_candidates[0]

    assert item.path == source.path
    assert item.cheap_score == source.cheap_score
    assert item.analysis_cost == source.analysis_cost
    assert item.value_score == source.value_score
    assert item.reasons == source.reasons[:2]


def test_candidate_summary_does_not_stat_or_open_paths():
    selection = select_candidates([_record("missing/auth_service.ts")], "auth")

    with (
        patch.object(Path, "open", side_effect=AssertionError("opened candidate")),
        patch.object(Path, "stat", side_effect=AssertionError("statted candidate")),
    ):
        summary = summarize_candidate_selection(selection)

    assert summary.top_candidates[0].path == "missing/auth_service.ts"


TESTS = [
    test_filename_keyword_match_ranks_above_unrelated_file,
    test_folder_segment_match_contributes_an_explainable_reason,
    test_generated_vendor_build_and_minified_records_are_strongly_demoted,
    test_test_files_are_demoted_for_implementation_tasks,
    test_test_files_are_boosted_when_task_asks_for_tests,
    test_language_and_extension_relevance_are_transparent,
    test_frontend_roles_add_bounded_task_match_reasons,
    test_ui_button_task_favors_recognized_frontend_role,
    test_frontend_role_boost_does_not_overcome_generated_demotion,
    test_frontend_integration_preserves_test_task_behavior,
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
    test_select_candidates_returns_value_ranked_candidates,
    test_select_candidates_applies_cap_and_reports_summary,
    test_select_candidates_accepts_empty_inventory,
    test_select_candidates_rejects_limits_like_cheap_shortlist,
    test_select_candidates_preserves_cheap_cost_and_value_reasons,
    test_select_candidates_keeps_generated_records_eligible_but_low_value,
    test_select_candidates_does_not_stat_or_open_inventory_paths,
    test_candidate_summary_includes_selection_metadata,
    test_candidate_summary_caps_candidates_and_reasons,
    test_empty_candidate_selection_has_valid_summary,
    test_candidate_summary_rejects_invalid_bounds,
    test_candidate_summary_preserves_scores_and_bounded_reasons,
    test_candidate_summary_does_not_stat_or_open_paths,
]
