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


def test_scan_command_writes_graph_and_formats_terminal_output():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        _create_repo(root)

        with change_directory(root):
            exit_code, output = capture_output(write_graph, ".")

        payload = json.loads((root / ".aidc" / "graph.json").read_text(encoding="utf-8"))
        normalized_output = output.replace("\\", "/")

        assert exit_code == 0
        assert (root / ".aidc" / "graph.json").exists()
        assert "Strata" in output
        assert "Scan complete" in output
        assert ".aidc" in normalized_output
        assert "graph.json" in output
        assert "Nodes" in output
        assert "Edges" in output
        assert "Warnings" in output
        assert "Repo intelligence" in output
        assert "Languages" in output
        assert payload["schema_version"] == 1
        assert payload["root"] == "."
        assert len(payload["files"]) == 2
        assert len(payload["edges"]) == 1


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
        assert "unresolved import" in output
        assert "missing_module" in main_file["unresolved_imports"]
        assert "Repo intelligence" in output
        assert "Frameworks" not in output


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


TESTS = [
    test_scan_command_writes_graph_and_formats_terminal_output,
    test_scan_command_reports_unresolved_imports,
    test_scan_command_reports_frontend_repo_intelligence,
]
