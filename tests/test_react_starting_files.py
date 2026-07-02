from pathlib import Path
from unittest.mock import patch

from strata.core.inventory import InventoryRecord
from strata.core.react_starting_files import (
    DEFAULT_REACT_STARTING_FILE_LIMIT,
    ReactStartingFile,
    select_react_starting_files,
)


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


def test_login_ui_task_favors_page_component_and_form_files():
    records = [
        _record("src/hooks/useLogin.ts"),
        _record("src/api/authClient.ts"),
        _record("src/components/LoginButton.tsx"),
        _record("src/forms/LoginForm.tsx"),
        _record("src/pages/LoginPage.tsx"),
    ]

    selected = select_react_starting_files(records, "fix login button")

    assert isinstance(selected[0], ReactStartingFile)
    assert selected[0].role in {"page", "component", "form"}
    assert {item.role for item in selected[:3]} <= {"page", "component", "form"}
    assert any("React UI starting role" in reason for reason in selected[0].reasons)


def test_hook_task_favors_use_hook_file():
    selected = select_react_starting_files(
        [_record("src/components/AuthPanel.tsx"), _record("src/hooks/useAuth.ts")],
        "update auth hook",
    )

    assert selected[0].path == "src/hooks/useAuth.ts"
    assert selected[0].role == "hook"
    assert "React role 'hook' matches task (+6)" in selected[0].reasons


def test_api_client_task_favors_client_file():
    selected = select_react_starting_files(
        [_record("src/pages/AuthPage.tsx"), _record("src/api/authClient.ts")],
        "update auth api client",
    )

    assert selected[0].path == "src/api/authClient.ts"
    assert selected[0].role == "api_client"


def test_store_task_favors_state_store_file():
    selected = select_react_starting_files(
        [_record("src/components/UserPanel.tsx"), _record("src/store/userStore.ts")],
        "change user state store",
    )

    assert selected[0].path == "src/store/userStore.ts"
    assert selected[0].role == "state_store"


def test_tests_are_only_eligible_for_test_tasks():
    implementation = _record("src/components/Checkout.tsx")
    test_file = _record(
        "src/components/Checkout.test.tsx",
        is_test=True,
        folder_role="test",
    )

    normal = select_react_starting_files([test_file, implementation], "update checkout")
    testing = select_react_starting_files([implementation, test_file], "test checkout")

    assert [item.path for item in normal] == [implementation.path]
    assert test_file.path in {item.path for item in testing}


def test_generated_vendor_build_and_minified_records_are_excluded():
    source = _record("src/components/Button.tsx")
    excluded = [
        _record("dist/components/Button.tsx", is_generated=True, folder_role="generated"),
        _record("vendor/components/Button.tsx", is_generated=True, folder_role="vendor"),
        _record("build/components/Button.tsx", is_generated=True, folder_role="generated"),
        _record("src/components/Button.min.tsx", is_generated=True),
    ]

    selected = select_react_starting_files([*excluded, source], "update button")

    assert [item.path for item in selected] == [source.path]


def test_selection_respects_limit_and_default_is_bounded():
    records = [_record(f"src/components/Widget{index}.tsx") for index in range(25)]

    limited = select_react_starting_files(records, "update component", limit=3)
    default = select_react_starting_files(records, "update component")

    assert len(limited) == 3
    assert len(default) == DEFAULT_REACT_STARTING_FILE_LIMIT


def test_invalid_limits_raise_clear_errors():
    for invalid in (0, -1):
        try:
            select_react_starting_files([], "task", limit=invalid)
        except ValueError as error:
            assert str(error) == "limit must be greater than zero"
        else:
            raise AssertionError(f"limit {invalid!r} should be rejected")

    for invalid in (True, 1.5):
        try:
            select_react_starting_files([], "task", limit=invalid)
        except TypeError as error:
            assert str(error) == "limit must be an integer"
        else:
            raise AssertionError(f"limit {invalid!r} should be rejected")


def test_empty_input_returns_empty_tuple():
    assert select_react_starting_files([], "login button") == ()


def test_selection_does_not_read_or_stat_paths():
    records = [_record("missing/pages/LoginPage.tsx")]

    with (
        patch("builtins.open", side_effect=AssertionError("opened a path")),
        patch.object(Path, "read_text", side_effect=AssertionError("read a path")),
        patch.object(Path, "stat", side_effect=AssertionError("statted a path")),
    ):
        selected = select_react_starting_files(records, "login page")

    assert selected[0].path == records[0].path


def test_windows_paths_are_deterministic():
    windows = _record(r"src\pages\DashboardPage.tsx")
    posix = _record("src/pages/DashboardPage.tsx")

    windows_result = select_react_starting_files([windows], "dashboard page")[0]
    posix_result = select_react_starting_files([posix], "dashboard page")[0]

    assert windows_result.role == posix_result.role == "page"
    assert windows_result.score == posix_result.score
    assert windows_result.reasons == posix_result.reasons


TESTS = [
    test_login_ui_task_favors_page_component_and_form_files,
    test_hook_task_favors_use_hook_file,
    test_api_client_task_favors_client_file,
    test_store_task_favors_state_store_file,
    test_tests_are_only_eligible_for_test_tasks,
    test_generated_vendor_build_and_minified_records_are_excluded,
    test_selection_respects_limit_and_default_is_bounded,
    test_invalid_limits_raise_clear_errors,
    test_empty_input_returns_empty_tuple,
    test_selection_does_not_read_or_stat_paths,
    test_windows_paths_are_deterministic,
]
