from pathlib import Path
from unittest.mock import patch

from strata.core.angular_starting_files import (
    DEFAULT_ANGULAR_STARTING_FILE_LIMIT,
    AngularStartingFile,
    select_angular_starting_files,
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


def test_login_ui_task_favors_component_template_and_typescript():
    records = [
        _record("src/app/auth/auth.service.ts"),
        _record("src/app/login/login.component.ts"),
        _record("src/app/login/login.component.html"),
    ]

    selected = select_angular_starting_files(records, "fix login button")

    assert isinstance(selected[0], AngularStartingFile)
    assert {item.path for item in selected[:2]} == {
        "src/app/login/login.component.ts",
        "src/app/login/login.component.html",
    }
    assert {item.role for item in selected[:2]} == {"component", "template"}


def test_auth_service_task_favors_service_file():
    selected = select_angular_starting_files(
        [
            _record("src/app/auth/auth.component.ts"),
            _record("src/app/auth/auth.service.ts"),
        ],
        "update auth service",
    )

    assert selected[0].path == "src/app/auth/auth.service.ts"
    assert selected[0].role == "service"
    assert "Angular service matches task (+6)" in selected[0].reasons


def test_route_task_favors_routes_and_routing_module():
    records = [
        _record("src/app/dashboard/dashboard.component.ts"),
        _record("src/app/app.routes.ts"),
        _record("src/app/app-routing.module.ts"),
    ]

    selected = select_angular_starting_files(records, "change dashboard navigation route")

    assert selected[0].role == "route"
    assert selected[0].path in {"src/app/app.routes.ts", "src/app/app-routing.module.ts"}


def test_style_task_favors_component_style_file():
    selected = select_angular_starting_files(
        [
            _record("src/app/card/card.component.ts"),
            _record("src/app/card/card.component.scss"),
        ],
        "update component style layout",
    )

    assert selected[0].path == "src/app/card/card.component.scss"
    assert selected[0].role == "style"
    assert "Angular style matches task (+7)" in selected[0].reasons


def test_guard_task_favors_guard_file():
    selected = select_angular_starting_files(
        [_record("src/app/auth/auth.service.ts"), _record("src/app/auth/auth.guard.ts")],
        "update auth guard",
    )

    assert selected[0].path == "src/app/auth/auth.guard.ts"
    assert selected[0].role == "service"
    assert "Angular guard matches task (+7)" in selected[0].reasons


def test_interceptor_task_favors_interceptor_file():
    selected = select_angular_starting_files(
        [
            _record("src/app/api/api.service.ts"),
            _record("src/app/api/auth.interceptor.ts"),
        ],
        "change auth interceptor",
    )

    assert selected[0].path == "src/app/api/auth.interceptor.ts"
    assert selected[0].role == "service"
    assert "Angular interceptor matches task (+7)" in selected[0].reasons


def test_tests_are_only_eligible_for_test_tasks():
    implementation = _record("src/app/login/login.component.ts")
    test_file = _record(
        "src/app/login/login.component.spec.ts",
        is_test=True,
        folder_role="test",
    )

    normal = select_angular_starting_files([test_file, implementation], "update login")
    testing = select_angular_starting_files([implementation, test_file], "test login")

    assert [item.path for item in normal] == [implementation.path]
    assert test_file.path in {item.path for item in testing}


def test_generated_vendor_build_and_minified_records_are_excluded():
    source = _record("src/app/button/button.component.ts")
    excluded = [
        _record("dist/app/button.component.ts"),
        _record("vendor/app/button.component.ts"),
        _record("build/app/button.component.ts"),
        _record("src/app/button.component.min.ts"),
    ]

    selected = select_angular_starting_files([*excluded, source], "update button")

    assert [item.path for item in selected] == [source.path]


def test_selection_respects_limit_and_default_is_bounded():
    records = [
        _record(f"src/app/widget-{index}/widget-{index}.component.ts")
        for index in range(25)
    ]

    limited = select_angular_starting_files(records, "update component", limit=3)
    default = select_angular_starting_files(records, "update component")

    assert len(limited) == 3
    assert len(default) == DEFAULT_ANGULAR_STARTING_FILE_LIMIT


def test_invalid_limits_raise_clear_errors():
    for invalid in (0, -1):
        try:
            select_angular_starting_files([], "task", limit=invalid)
        except ValueError as error:
            assert str(error) == "limit must be greater than zero"
        else:
            raise AssertionError(f"limit {invalid!r} should be rejected")

    for invalid in (True, 1.5):
        try:
            select_angular_starting_files([], "task", limit=invalid)
        except TypeError as error:
            assert str(error) == "limit must be an integer"
        else:
            raise AssertionError(f"limit {invalid!r} should be rejected")


def test_empty_input_returns_empty_tuple():
    assert select_angular_starting_files([], "login button") == ()


def test_selection_does_not_read_or_stat_paths():
    records = [_record("missing/app/login/login.component.html")]

    with (
        patch("builtins.open", side_effect=AssertionError("opened a path")),
        patch.object(Path, "read_text", side_effect=AssertionError("read a path")),
        patch.object(Path, "stat", side_effect=AssertionError("statted a path")),
    ):
        selected = select_angular_starting_files(records, "login button")

    assert selected[0].path == records[0].path


def test_windows_paths_are_deterministic():
    windows = _record(r"src\app\dashboard\dashboard.component.scss")
    posix = _record("src/app/dashboard/dashboard.component.scss")

    windows_result = select_angular_starting_files([windows], "dashboard style")[0]
    posix_result = select_angular_starting_files([posix], "dashboard style")[0]

    assert windows_result.role == posix_result.role == "style"
    assert windows_result.score == posix_result.score
    assert windows_result.reasons == posix_result.reasons


TESTS = [
    test_login_ui_task_favors_component_template_and_typescript,
    test_auth_service_task_favors_service_file,
    test_route_task_favors_routes_and_routing_module,
    test_style_task_favors_component_style_file,
    test_guard_task_favors_guard_file,
    test_interceptor_task_favors_interceptor_file,
    test_tests_are_only_eligible_for_test_tasks,
    test_generated_vendor_build_and_minified_records_are_excluded,
    test_selection_respects_limit_and_default_is_bounded,
    test_invalid_limits_raise_clear_errors,
    test_empty_input_returns_empty_tuple,
    test_selection_does_not_read_or_stat_paths,
    test_windows_paths_are_deterministic,
]
