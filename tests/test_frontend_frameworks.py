from pathlib import Path
from unittest.mock import patch

from strata.core.frontend_frameworks import (
    MAX_FRAMEWORK_REASONS,
    FrontendFrameworkDetection,
    detect_frontend_frameworks,
)
from strata.core.inventory import InventoryRecord


def _record(path: str) -> InventoryRecord:
    filename = path.replace("\\", "/").rsplit("/", 1)[-1]
    extension = f".{filename.rsplit('.', 1)[-1].lower()}" if "." in filename else ""
    return InventoryRecord(
        path=path,
        extension=extension,
        size=100,
        mtime=1_700_000_000,
        is_test=False,
        is_generated_guess=False,
        folder_role="source",
        language_guess="typescript",
    )


def _signal(detection: FrontendFrameworkDetection, framework: str):
    return next(signal for signal in detection.signals if signal.framework == framework)


def test_detects_angular_from_config_and_conventional_files():
    detection = detect_frontend_frameworks(
        [
            _record("angular.json"),
            _record("src/app/app.module.ts"),
            _record("src/app/app.routes.ts"),
            _record("src/app/login/login.component.ts"),
            _record("src/app/login/login.component.html"),
        ]
    )

    angular = _signal(detection, "angular")
    assert detection.frameworks == ("angular",)
    assert angular.confidence == "high"
    assert any("Angular config filename" in reason for reason in angular.reasons)
    assert any("Angular app module filename" in reason for reason in angular.reasons)


def test_detects_react_from_config_entrypoints_pages_hooks_and_components():
    detection = detect_frontend_frameworks(
        [
            _record("vite.config.ts"),
            _record("next.config.js"),
            _record("src/App.tsx"),
            _record("src/pages/HomePage.tsx"),
            _record("src/hooks/useAuth.tsx"),
            _record("src/components/Button.jsx"),
        ]
    )

    react = _signal(detection, "react")
    assert detection.frameworks == ("react",)
    assert react.confidence == "high"
    assert any("Next config filename" in reason for reason in react.reasons)
    assert any("use-prefixed file under hooks" in reason for reason in react.reasons)


def test_generic_typescript_does_not_imply_a_framework():
    detection = detect_frontend_frameworks(
        [_record("src/utils/date.ts"), _record("server/models/user.ts")]
    )

    assert detection.frameworks == ()
    assert detection.signals == ()


def test_generic_html_and_css_do_not_imply_angular():
    detection = detect_frontend_frameworks(
        [_record("public/index.html"), _record("public/site.css")]
    )

    assert detection.frameworks == ()


def test_workspace_config_with_app_folder_is_low_confidence_angular_evidence():
    detection = detect_frontend_frameworks(
        [_record("workspace.json"), _record("src/app/utils/date.ts")]
    )

    assert detection.frameworks == ("angular",)
    assert _signal(detection, "angular").confidence == "low"


def test_detects_react_and_angular_in_one_inventory():
    detection = detect_frontend_frameworks(
        [
            _record("packages/web/next.config.js"),
            _record("packages/web/src/App.tsx"),
            _record("packages/admin/angular.json"),
            _record("packages/admin/src/app/app.module.ts"),
        ]
    )

    assert set(detection.frameworks) == {"react", "angular"}
    assert {signal.framework for signal in detection.signals} == {"react", "angular"}


def test_empty_input_returns_empty_detection():
    detection = detect_frontend_frameworks([])

    assert detection == FrontendFrameworkDetection(
        frameworks=(),
        signals=(),
        files_considered=0,
    )


def test_confidence_and_reason_bounds_are_deterministic():
    records = [
        _record("vite.config.ts"),
        _record("package-lock.json"),
        _record("src/App.tsx"),
        _record("src/pages/HomePage.tsx"),
        _record("src/app/Shell.tsx"),
        _record("src/components/Button.tsx"),
        _record("src/hooks/useAuth.tsx"),
    ]

    forward = detect_frontend_frameworks(records)
    reverse = detect_frontend_frameworks(reversed(records))

    assert forward == reverse
    assert _signal(forward, "react").confidence == "high"
    assert len(_signal(forward, "react").reasons) <= MAX_FRAMEWORK_REASONS


def test_vite_and_lockfile_names_alone_are_not_enough():
    detection = detect_frontend_frameworks(
        [_record("vite.config.ts"), _record("package-lock.json")]
    )

    assert detection.frameworks == ()
    assert detection.signals == ()


def test_detection_does_not_read_or_stat_paths():
    records = [_record("missing/angular.json"), _record("missing/src/App.tsx")]

    with (
        patch("builtins.open", side_effect=AssertionError("opened a path")),
        patch.object(Path, "read_text", side_effect=AssertionError("read a path")),
        patch.object(Path, "stat", side_effect=AssertionError("statted a path")),
    ):
        detection = detect_frontend_frameworks(records)

    assert set(detection.frameworks) == {"react", "angular"}


def test_windows_paths_match_posix_detection():
    windows_records = [
        _record(r"src\app\app.module.ts"),
        _record(r"src\app\login\login.component.html"),
    ]
    posix_records = [
        _record("src/app/app.module.ts"),
        _record("src/app/login/login.component.html"),
    ]

    windows = detect_frontend_frameworks(windows_records)
    posix = detect_frontend_frameworks(posix_records)

    assert windows.frameworks == posix.frameworks == ("angular",)
    assert windows.signals == posix.signals
    assert windows.files_considered == posix.files_considered == 2


TESTS = [
    test_detects_angular_from_config_and_conventional_files,
    test_detects_react_from_config_entrypoints_pages_hooks_and_components,
    test_generic_typescript_does_not_imply_a_framework,
    test_generic_html_and_css_do_not_imply_angular,
    test_workspace_config_with_app_folder_is_low_confidence_angular_evidence,
    test_detects_react_and_angular_in_one_inventory,
    test_empty_input_returns_empty_detection,
    test_confidence_and_reason_bounds_are_deterministic,
    test_vite_and_lockfile_names_alone_are_not_enough,
    test_detection_does_not_read_or_stat_paths,
    test_windows_paths_match_posix_detection,
]
