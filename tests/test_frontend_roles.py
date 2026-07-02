from pathlib import Path
from unittest.mock import patch

from strata.core.frontend_roles import (
    FRONTEND_ROLES,
    infer_frontend_role_from_path,
    is_frontend_candidate,
)


def test_react_roles_are_inferred_from_path_signals():
    expected_roles = {
        "src/pages/HomePage.tsx": "page",
        "src/components/LoginForm.tsx": "component",
        "src/hooks/useAuth.ts": "hook",
        "src/api/authClient.ts": "api_client",
        "src/store/userStore.ts": "state_store",
        "src/routes/AppRoutes.tsx": "route",
    }

    for path, expected_role in expected_roles.items():
        assert infer_frontend_role_from_path(path) == expected_role


def test_angular_roles_are_inferred_from_path_signals():
    expected_roles = {
        "src/app/login/login.component.ts": "component",
        "src/app/login/login.component.html": "template",
        "src/app/login/login.component.scss": "style",
        "src/app/auth/auth.service.ts": "service",
        "src/app/app.routes.ts": "route",
        "src/app/app-routing.module.ts": "route",
        "src/app/auth/auth.guard.ts": "service",
        "src/app/login/login.component.spec.ts": "test",
    }

    for path, expected_role in expected_roles.items():
        assert infer_frontend_role_from_path(path) == expected_role


def test_unknown_and_non_frontend_paths_are_rejected():
    for path in ("README.md", "backend/models/user.py", "src/data.bin", "package.json"):
        assert infer_frontend_role_from_path(path) == "unknown"
        assert is_frontend_candidate(path) is False


def test_frontend_candidate_recognizes_supported_extensions():
    for path in (
        "src/app.js",
        "src/app.ts",
        "src/App.jsx",
        "src/App.tsx",
        "src/index.html",
        "src/site.css",
        "src/site.scss",
    ):
        assert is_frontend_candidate(path) is True


def test_helpers_do_not_read_or_stat_paths():
    with (
        patch("builtins.open", side_effect=AssertionError("opened a path")),
        patch.object(Path, "read_text", side_effect=AssertionError("read a path")),
        patch.object(Path, "stat", side_effect=AssertionError("statted a path")),
    ):
        assert infer_frontend_role_from_path("src/components/Button.tsx") == "component"
        assert is_frontend_candidate("src/styles/button.css") is True


def test_windows_paths_are_deterministic():
    windows_path = r"src\app\login\login.component.spec.ts"
    posix_path = "src/app/login/login.component.spec.ts"

    assert infer_frontend_role_from_path(windows_path) == "test"
    assert infer_frontend_role_from_path(windows_path) == infer_frontend_role_from_path(
        posix_path
    )
    assert is_frontend_candidate(windows_path) is True


def test_role_taxonomy_is_stable_and_complete():
    assert FRONTEND_ROLES == (
        "page",
        "component",
        "template",
        "style",
        "hook",
        "service",
        "api_client",
        "route",
        "state_store",
        "form",
        "test",
        "config",
        "asset",
        "unknown",
    )


TESTS = [
    test_react_roles_are_inferred_from_path_signals,
    test_angular_roles_are_inferred_from_path_signals,
    test_unknown_and_non_frontend_paths_are_rejected,
    test_frontend_candidate_recognizes_supported_extensions,
    test_helpers_do_not_read_or_stat_paths,
    test_windows_paths_are_deterministic,
    test_role_taxonomy_is_stable_and_complete,
]
