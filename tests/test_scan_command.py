import contextlib
import json
import tempfile
from pathlib import Path

from cli import write_graph
from tests.helpers import capture_output


@contextlib.contextmanager
def change_directory(path: Path):
    import os

    original = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(original)


def _create_repo(root: Path, *, unresolved: bool = False) -> None:
    root.mkdir(parents=True, exist_ok=True)

    (root / "helper.py").write_text(
        "def helper():\n"
        "    return True\n",
        encoding="utf-8",
    )

    if unresolved:
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

    (root / "main.py").write_text(main_source, encoding="utf-8")


def _create_frontend_repo(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)

    (root / "src").mkdir(parents=True, exist_ok=True)
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
        'import { Injectable } from "@angular/core";\n'
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

    (root / "src" / "app.routes.ts").write_text(
        'import { RouterModule } from "@angular/router";\n'
        '\n'
        "export const routes = [\n"
        '    { path: "home", component: AppComponent },\n'
        "];\n",
        encoding="utf-8",
    )


def _add_generated_dirs(root: Path) -> None:
    for ignored_root in [
        "pkg.egg-info",
        "build",
        "dist",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
    ]:
        ignored_dir = root / ignored_root
        ignored_dir.mkdir(parents=True, exist_ok=True)
        (ignored_dir / "ignored.py").write_text("print('ignored')\n", encoding="utf-8")


def test_scan_command_writes_graph_and_formats_terminal_output():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        _create_repo(root)

        with change_directory(root):
            exit_code, output = capture_output(write_graph, ".")

        payload = json.loads((root / ".aidc" / "graph.json").read_text(encoding="utf-8"))
        scan_payload = json.loads((root / ".aidc" / "cache" / "repo_scan.json").read_text(encoding="utf-8"))
        normalized_output = output.replace("\\", "/")

        assert exit_code == 0
        assert (root / ".aidc" / "graph.json").exists()
        assert (root / ".aidc" / "cache" / "repo_scan.json").exists()
        assert not (root / ".aidc" / "cache" / "repo_scan.tmp.json").exists()
        assert "Strata" in output
        assert "Full repo intelligence mode" in output
        assert "Scan phases" in output
        assert "Discovering files" in output
        assert "Fingerprinting" in output
        assert "Parsing source files" in output
        assert "Detecting changes during scan" in output
        assert "Saving cache" in output
        assert "Full scan complete" in output
        assert ".aidc" in normalized_output
        assert "graph.json" in output
        assert "repo_scan.json" in output
        assert "Nodes" in output
        assert "Edges" in output
        assert "Warnings" in output
        assert "Repo intelligence" in output
        assert "Languages" in output
        assert payload["schema_version"] == 1
        assert payload["root"] == "."
        assert len(payload["files"]) == 2
        assert len(payload["edges"]) == 1
        assert scan_payload["schema_version"] == 1
        assert scan_payload["status"] in {"fresh", "partial", "stale"}
        assert scan_payload["graph_path"].replace("\\", "/").endswith(".aidc/graph.json")
        assert scan_payload["file_count"] == 2
        assert scan_payload["scanned_count"] == 2


def test_scan_command_reports_unresolved_imports():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        _create_repo(root, unresolved=True)

        with change_directory(root):
            exit_code, output = capture_output(write_graph, ".")

        payload = json.loads((root / ".aidc" / "graph.json").read_text(encoding="utf-8"))
        main_file = next(
            file_info
            for file_info in payload["files"]
            if file_info["path"].endswith("main.py")
        )

        assert exit_code == 0
        assert "Warnings" in output
        assert "missing_module" in main_file["unresolved_imports"]
        assert "Repo intelligence" in output
        assert "Frameworks" not in output


def test_scan_command_ignores_generated_directories_and_egg_info():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        _create_repo(root)
        _add_generated_dirs(root)

        with change_directory(root):
            exit_code, output = capture_output(write_graph, ".")

        payload = json.loads((root / ".aidc" / "graph.json").read_text(encoding="utf-8"))
        paths = {file_info["path"] for file_info in payload["files"]}

        assert exit_code == 0
        assert payload["schema_version"] == 1
        assert payload["root"] == "."
        assert len(payload["files"]) == 2
        assert "main.py" in paths
        assert "helper.py" in paths
        assert not any(path.startswith("pkg.egg-info/") for path in paths)
        assert not any(path.startswith("build/") for path in paths)
        assert not any(path.startswith("dist/") for path in paths)
        assert "Full scan complete" in output


def test_scan_command_reports_frontend_repo_intelligence():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        _create_frontend_repo(root)

        with change_directory(root):
            exit_code, output = capture_output(write_graph, ".")

        assert exit_code == 0
        assert "Repo intelligence" in output
        assert "React" in output
        assert "Angular" in output
        assert "Components" in output
        assert "Hooks" in output
        assert "Angular services" in output
        assert "Angular routes" in output
        assert "full scan" in output.lower()


def test_scan_command_recovery_clears_interrupted_marker():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        _create_repo(root)
        temp_scan = root / ".aidc" / "cache" / "repo_scan.tmp.json"
        temp_scan.parent.mkdir(parents=True, exist_ok=True)
        temp_scan.write_text(
            '{"schema_version":1,"status":"scanning","root":"%s"}' % root.as_posix(),
            encoding="utf-8",
        )

        with change_directory(root):
            exit_code, output = capture_output(write_graph, ".")

        assert exit_code == 0
        assert "previous scan did not finish" in output.lower()
        assert "Interrupted scan recovered." in output
        assert (root / ".aidc" / "cache" / "repo_scan.json").exists()
        assert not temp_scan.exists()


def test_scan_command_force_reports_forced_rescan():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        _create_repo(root)

        with change_directory(root):
            first_exit_code, _ = capture_output(write_graph, ".")
            second_exit_code, output = capture_output(write_graph, ".", True)

        assert first_exit_code == 0
        assert second_exit_code == 0
        assert "forced rescan requested" in output.lower()
        assert "Full scan complete" in output
        assert (root / ".aidc" / "cache" / "repo_scan.json").exists()
        assert not (root / ".aidc" / "cache" / "repo_scan.tmp.json").exists()


TESTS = [
    test_scan_command_writes_graph_and_formats_terminal_output,
    test_scan_command_reports_unresolved_imports,
    test_scan_command_ignores_generated_directories_and_egg_info,
    test_scan_command_reports_frontend_repo_intelligence,
    test_scan_command_recovery_clears_interrupted_marker,
    test_scan_command_force_reports_forced_rescan,
]
