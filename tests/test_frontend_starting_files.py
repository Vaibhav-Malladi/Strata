from pathlib import Path
from unittest.mock import patch

from strata.core.frontend_starting_files import (
    DEFAULT_FRONTEND_STARTING_FILE_LIMIT,
    FrontendStartingFileSelection,
    select_frontend_starting_files,
)
from strata.core.inventory import InventoryRecord


def _record(
    path: str,
    *,
    is_test: bool = False,
    is_generated: bool = False,
    folder_role: str = "source",
) -> InventoryRecord:
    extension = "." + path.replace("\\", "/").rsplit(".", 1)[-1].lower()
    return InventoryRecord(
        path=path,
        extension=extension,
        size=100,
        mtime=1_700_000_000,
        is_test=is_test,
        is_generated_guess=is_generated,
        folder_role=folder_role,
        language_guess="typescript",
    )


def test_combined_selection_returns_react_and_angular_candidates():
    selection = select_frontend_starting_files(
        [
            _record("src/pages/LoginPage.tsx"),
            _record("src/app/login/login.component.html"),
        ],
        "fix login button",
    )

    assert isinstance(selection, FrontendStartingFileSelection)
    assert {item.framework for item in selection.files} == {"react", "angular"}
    assert selection.frameworks_considered == ("react", "angular")
    assert selection.files_considered == 2


def test_react_framework_filter_returns_only_react_results():
    selection = select_frontend_starting_files(
        [_record("src/pages/DashboardPage.tsx")],
        "dashboard page",
        frameworks="react",
    )

    assert selection.frameworks_considered == ("react",)
    assert selection.files
    assert {item.framework for item in selection.files} == {"react"}


def test_angular_framework_filter_returns_only_angular_results():
    selection = select_frontend_starting_files(
        [_record("src/app/dashboard/dashboard.component.html")],
        "dashboard page",
        frameworks=("angular",),
    )

    assert selection.frameworks_considered == ("angular",)
    assert selection.files
    assert {item.framework for item in selection.files} == {"angular"}


def test_auto_mode_selects_react_from_detected_signals():
    selection = select_frontend_starting_files(
        [_record("next.config.js"), _record("src/App.tsx")],
        "update app component",
        frameworks="auto",
    )

    assert selection.frameworks_considered == ("react",)
    assert selection.files
    assert {item.framework for item in selection.files} == {"react"}


def test_auto_mode_selects_angular_from_detected_signals():
    selection = select_frontend_starting_files(
        [_record("angular.json"), _record("src/app/login/login.component.html")],
        "update login button",
        frameworks=("auto",),
    )

    assert selection.frameworks_considered == ("angular",)
    assert selection.files
    assert {item.framework for item in selection.files} == {"angular"}


def test_auto_mode_selects_both_frameworks_in_monorepo():
    selection = select_frontend_starting_files(
        [
            _record("packages/web/next.config.js"),
            _record("packages/web/src/App.tsx"),
            _record("packages/admin/angular.json"),
            _record("packages/admin/src/app/login/login.component.html"),
        ],
        "update login app",
        frameworks="auto",
    )

    assert selection.frameworks_considered == ("react", "angular")
    assert {item.framework for item in selection.files} == {"react", "angular"}


def test_auto_mode_returns_empty_selection_when_nothing_is_detected():
    selection = select_frontend_starting_files(
        [_record("src/utils/date.ts")],
        "update date",
        frameworks="auto",
    )

    assert selection.files == ()
    assert selection.frameworks_considered == ()
    assert selection.files_considered == 1
    assert selection.truncated is False


def test_auto_mode_cannot_be_mixed_with_explicit_frameworks():
    try:
        select_frontend_starting_files(
            [],
            "task",
            frameworks=("auto", "react"),
        )
    except ValueError as error:
        assert str(error) == (
            "auto framework mode cannot be combined with explicit frameworks"
        )
    else:
        raise AssertionError("mixed auto and explicit frameworks should be rejected")


def test_duplicate_path_keeps_higher_score_with_framework_note():
    record = _record("src/app/login/login.component.ts")

    first = select_frontend_starting_files([record], "login component")
    second = select_frontend_starting_files(
        [record],
        "login component",
        frameworks=("angular", "react"),
    )

    assert len(first.files) == 1
    assert first.files == second.files
    assert any("also selected by" in reason for reason in first.files[0].reasons)


def test_limit_and_truncation_metadata_are_correct():
    records = [_record(f"src/pages/Page{index}.tsx") for index in range(5)]

    selection = select_frontend_starting_files(
        records,
        "update page",
        frameworks="react",
        limit=2,
    )

    assert len(selection.files) == 2
    assert selection.limit == 2
    assert selection.truncated is True
    assert selection.files_considered == 5


def test_default_limit_is_bounded():
    records = [_record(f"src/pages/Page{index}.tsx") for index in range(25)]

    selection = select_frontend_starting_files(records, "update page", frameworks="react")

    assert len(selection.files) == DEFAULT_FRONTEND_STARTING_FILE_LIMIT
    assert selection.truncated is True


def test_invalid_limits_raise_clear_errors():
    for invalid in (0, -1):
        try:
            select_frontend_starting_files([], "task", limit=invalid)
        except ValueError as error:
            assert str(error) == "limit must be greater than zero"
        else:
            raise AssertionError(f"limit {invalid!r} should be rejected")

    for invalid in (True, 1.5):
        try:
            select_frontend_starting_files([], "task", limit=invalid)
        except TypeError as error:
            assert str(error) == "limit must be an integer"
        else:
            raise AssertionError(f"limit {invalid!r} should be rejected")


def test_invalid_framework_raises_clear_error():
    try:
        select_frontend_starting_files([], "task", frameworks=("react", "vue"))
    except ValueError as error:
        assert str(error) == "unsupported frontend framework(s): vue"
    else:
        raise AssertionError("unsupported frontend framework should be rejected")


def test_empty_input_returns_valid_empty_selection():
    selection = select_frontend_starting_files([], "login button")

    assert selection.files == ()
    assert selection.frameworks_considered == ("react", "angular")
    assert selection.files_considered == 0
    assert selection.limit == DEFAULT_FRONTEND_STARTING_FILE_LIMIT
    assert selection.truncated is False


def test_pipeline_does_not_read_or_stat_paths():
    records = [_record("missing/pages/LoginPage.tsx")]

    with (
        patch("builtins.open", side_effect=AssertionError("opened a path")),
        patch.object(Path, "read_text", side_effect=AssertionError("read a path")),
        patch.object(Path, "stat", side_effect=AssertionError("statted a path")),
    ):
        selection = select_frontend_starting_files(records, "login page")

    assert selection.files


def test_auto_mode_does_not_read_or_stat_paths():
    records = [_record("missing/angular.json"), _record("missing/src/App.tsx")]

    with (
        patch("builtins.open", side_effect=AssertionError("opened a path")),
        patch.object(Path, "read_text", side_effect=AssertionError("read a path")),
        patch.object(Path, "stat", side_effect=AssertionError("statted a path")),
    ):
        selection = select_frontend_starting_files(
            records,
            "update app",
            frameworks="auto",
        )

    assert selection.frameworks_considered == ("react", "angular")


def test_windows_paths_are_deterministic():
    windows = _record(r"src\pages\DashboardPage.tsx")
    posix = _record("src/pages/DashboardPage.tsx")

    windows_result = select_frontend_starting_files(
        [windows], "dashboard page", frameworks="react"
    ).files[0]
    posix_result = select_frontend_starting_files(
        [posix], "dashboard page", frameworks="react"
    ).files[0]

    assert windows_result.framework == posix_result.framework == "react"
    assert windows_result.role == posix_result.role
    assert windows_result.score == posix_result.score
    assert windows_result.reasons == posix_result.reasons


def test_auto_mode_ordering_is_deterministic():
    records = [
        _record("packages/web/next.config.js"),
        _record("packages/web/src/App.tsx"),
        _record("packages/admin/angular.json"),
        _record("packages/admin/src/app/app.component.html"),
    ]

    forward = select_frontend_starting_files(records, "update app", frameworks="auto")
    reverse = select_frontend_starting_files(
        reversed(records),
        "update app",
        frameworks="auto",
    )

    assert forward == reverse


def test_generated_paths_are_excluded_by_underlying_selectors():
    selection = select_frontend_starting_files(
        [
            _record("dist/pages/LoginPage.tsx"),
            _record("src/pages/LoginPage.tsx"),
            _record("build/app/login.component.html"),
        ],
        "login page",
    )

    assert {item.path for item in selection.files} == {"src/pages/LoginPage.tsx"}


def test_test_file_behavior_matches_underlying_selectors():
    implementation = _record("src/pages/CheckoutPage.tsx")
    test_file = _record(
        "src/pages/CheckoutPage.test.tsx",
        is_test=True,
        folder_role="test",
    )

    normal = select_frontend_starting_files(
        [test_file, implementation], "update checkout", frameworks="react"
    )
    testing = select_frontend_starting_files(
        [implementation, test_file], "test checkout", frameworks="react"
    )

    assert [item.path for item in normal.files] == [implementation.path]
    assert test_file.path in {item.path for item in testing.files}


TESTS = [
    test_combined_selection_returns_react_and_angular_candidates,
    test_react_framework_filter_returns_only_react_results,
    test_angular_framework_filter_returns_only_angular_results,
    test_auto_mode_selects_react_from_detected_signals,
    test_auto_mode_selects_angular_from_detected_signals,
    test_auto_mode_selects_both_frameworks_in_monorepo,
    test_auto_mode_returns_empty_selection_when_nothing_is_detected,
    test_auto_mode_cannot_be_mixed_with_explicit_frameworks,
    test_duplicate_path_keeps_higher_score_with_framework_note,
    test_limit_and_truncation_metadata_are_correct,
    test_default_limit_is_bounded,
    test_invalid_limits_raise_clear_errors,
    test_invalid_framework_raises_clear_error,
    test_empty_input_returns_valid_empty_selection,
    test_pipeline_does_not_read_or_stat_paths,
    test_auto_mode_does_not_read_or_stat_paths,
    test_windows_paths_are_deterministic,
    test_auto_mode_ordering_is_deterministic,
    test_generated_paths_are_excluded_by_underlying_selectors,
    test_test_file_behavior_matches_underlying_selectors,
]
