import tempfile
from pathlib import Path

import scanner as old_scanner
import strata.core.scanner as new_scanner
from scanner import scan_repo


def _write_file(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def _create_symlink(link: Path, target: Path, *, target_is_directory: bool) -> bool:
    try:
        link.symlink_to(target, target_is_directory=target_is_directory)
    except (NotImplementedError, OSError) as error:
        print(f"SKIP: symlink creation is not permitted on this platform: {error}")
        return False
    return True


def _create_scanner_repo(root: Path, *, include_unresolved: bool = True) -> None:
    root.mkdir(parents=True, exist_ok=True)

    _write_file(
        root / "helper.py",
        "def helper():\n"
        "    return True\n",
    )

    if include_unresolved:
        main_source = (
            "import os\n"
            "import helper\n"
            "import missing_module\n\n"
            "def run():\n"
            "    return helper()\n"
        )
    else:
        main_source = (
            "import os\n"
            "import helper\n\n"
            "def run():\n"
            "    return helper()\n"
        )

    _write_file(root / "main.py", main_source)


def _scan_temp_repo_result(*, include_unresolved: bool = True) -> dict:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        _create_scanner_repo(root, include_unresolved=include_unresolved)
        return scan_repo(str(root))


def _main_file(result: dict) -> dict | None:
    for file_info in result.get("files", []):
        if file_info["path"].endswith("main.py"):
            return file_info

    return None


def get_file_by_name(graph: dict, file_name: str) -> dict:
    for file_info in graph["files"]:
        if file_info["path"].endswith(file_name):
            return file_info

    raise AssertionError(f"File not found in graph: {file_name}")


def test_scanner_core_import_matches_compatibility_shim():
    assert old_scanner.scan_repo is new_scanner.scan_repo


def test_scan_repo_finds_python_files():
    result = _scan_temp_repo_result()

    paths = [file["path"] for file in result["files"]]

    assert result["root"].endswith("repo")
    assert len(result["files"]) == 2
    assert any(path.endswith("main.py") for path in paths)
    assert any(path.endswith("helper.py") for path in paths)


def test_scan_repo_detects_imports():
    result = _scan_temp_repo_result()

    main_file = _main_file(result)

    assert main_file is not None
    assert "helper" in main_file["imports"]


def test_scan_repo_creates_import_edges():
    result = _scan_temp_repo_result()

    assert "edges" in result
    assert len(result["edges"]) == 1

    edge = result["edges"][0]

    assert edge["type"] == "imports"
    assert edge["import"] == "helper"
    assert edge["from"].endswith("main.py")
    assert edge["to"].endswith("helper.py")


def test_scan_repo_resolves_same_folder_imports_from_project_root():
    result = _scan_temp_repo_result()

    matching_edges = []

    for edge in result["edges"]:
        if (
            edge["from"].endswith("main.py")
            and edge["to"].endswith("helper.py")
            and edge["import"] == "helper"
        ):
            matching_edges.append(edge)

    assert len(matching_edges) == 1


def test_scan_repo_includes_schema_version():
    result = _scan_temp_repo_result()

    assert result["schema_version"] == 1


def test_scan_repo_skips_symlinked_external_directory_and_file():
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        root = temp_root / "repo"
        outside = temp_root / "outside"
        root.mkdir()
        outside.mkdir()
        _write_file(root / "normal.py", "value = 'inside'\n")
        _write_file(outside / "external.py", "value = 'outside'\n")
        if not _create_symlink(root / "linked_dir", outside, target_is_directory=True):
            return
        if not _create_symlink(
            root / "linked_file.py",
            outside / "external.py",
            target_is_directory=False,
        ):
            return

        result = new_scanner.scan_repo(str(root))
        paths = [Path(file_info["path"]).name for file_info in result["files"]]

        assert paths == ["normal.py"]


def test_scan_repo_classifies_imports():
    result = _scan_temp_repo_result()
    main_file = _main_file(result)

    assert main_file is not None

    assert "os" in main_file["imports"]
    assert "helper" in main_file["imports"]
    assert "missing_module" in main_file["imports"]

    assert "os" in main_file["external_imports"]
    assert "missing_module" in main_file["unresolved_imports"]

    assert "helper" not in main_file["external_imports"]
    assert "helper" not in main_file["unresolved_imports"]


def test_scan_repo_records_unresolved_import_line_number():
    result = _scan_temp_repo_result()
    main_file = _main_file(result)

    assert main_file is not None

    matching_details = []

    for import_detail in main_file["unresolved_import_details"]:
        if import_detail["name"] == "missing_module":
            matching_details.append(import_detail)

    assert len(matching_details) == 1
    assert matching_details[0]["line"] == 3


def test_scanner_records_frontend_framework_signals():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        (root / "src" / "components").mkdir(parents=True, exist_ok=True)

        (root / "src" / "App.tsx").write_text(
            'import React, { useState } from "react";\n'
            'import { Button } from "./components/Button";\n'
            '\n'
            'export function App() {\n'
            "    useState(0);\n"
            "    return <Button />;\n"
            "}\n",
            encoding="utf-8",
        )

        (root / "src" / "components" / "Button.tsx").write_text(
            'import React from "react";\n'
            '\n'
            'export const Button = () => <button />;\n',
            encoding="utf-8",
        )

        (root / "src" / "app.component.ts").write_text(
            'import { Component } from "@angular/core";\n'
            '\n'
            '@Component({ selector: "app-root" })\n'
            "export class AppComponent {}\n",
            encoding="utf-8",
        )

        (root / "src" / "user.service.ts").write_text(
            'import { Injectable } from "@angular/core";\n'
            '\n'
            '@Injectable({ providedIn: "root" })\n'
            "export class UserService {}\n",
            encoding="utf-8",
        )

        graph = scan_repo(str(root))
        app = get_file_by_name(graph, "App.tsx")
        component = get_file_by_name(graph, "app.component.ts")
        service = get_file_by_name(graph, "user.service.ts")

        assert "react" in app["frameworks"]
        assert any(item["name"] == "App" for item in app["components"])
        assert any(item["kind"] == "call" for item in app["hooks"])
        assert "angular" in component["frameworks"]
        assert any(item["name"] == "AppComponent" for item in component["angular"]["components"])
        assert any(item["name"] == "UserService" for item in service["angular"]["services"])


TESTS = [
    test_scanner_core_import_matches_compatibility_shim,
    test_scan_repo_finds_python_files,
    test_scan_repo_detects_imports,
    test_scan_repo_creates_import_edges,
    test_scan_repo_resolves_same_folder_imports_from_project_root,
    test_scan_repo_includes_schema_version,
    test_scan_repo_skips_symlinked_external_directory_and_file,
    test_scan_repo_classifies_imports,
    test_scan_repo_records_unresolved_import_line_number,
    test_scanner_records_frontend_framework_signals,
]
