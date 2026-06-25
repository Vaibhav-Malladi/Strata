import contextlib
import os
import tempfile
from pathlib import Path

from commands.context_command import write_context
from tests.helpers import capture_output


@contextlib.contextmanager
def change_directory(path: Path):
    original = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(original)


def create_context_repo(root: Path, with_routes: bool = False) -> None:
    (root / "src" / "api").mkdir(parents=True, exist_ok=True)
    (root / "src" / "auth").mkdir(parents=True, exist_ok=True)
    (root / "tests").mkdir(parents=True, exist_ok=True)

    route_prefix = '@app.post("/users/login")\n' if with_routes else ""

    (root / "src" / "api" / "user_login.py").write_text(
        "from src.auth.users import find_user\n\n"
        f"{route_prefix}"
        "def login_user():\n"
        "    return find_user()\n",
        encoding="utf-8",
    )

    (root / "src" / "auth" / "users.py").write_text(
        "def find_user():\n"
        "    return None\n",
        encoding="utf-8",
    )

    (root / "tests" / "test_user_login.py").write_text(
        "from src.api.user_login import login_user\n",
        encoding="utf-8",
    )


def create_frontend_context_repo(root: Path) -> None:
    (root / "src" / "components").mkdir(parents=True, exist_ok=True)
    (root / "src" / "shared").mkdir(parents=True, exist_ok=True)

    (root / "src" / "components" / "Button.tsx").write_text(
        'import React, { useState } from "react";\n'
        '\n'
        'export function Button() {\n'
        "    useState(0);\n"
        "    return <button />;\n"
        "}\n",
        encoding="utf-8",
    )

    (root / "src" / "user.service.ts").write_text(
        'import { Injectable } from "@angular/core";\n'
        '\n'
        '@Injectable({ providedIn: "root" })\n'
        "export class UserService {}\n",
        encoding="utf-8",
    )

    (root / "src" / "app.module.ts").write_text(
        'import { NgModule } from "@angular/core";\n'
        '\n'
        "@NgModule({})\n"
        "export class AppModule {}\n",
        encoding="utf-8",
    )

    (root / "src" / "shared" / "app.routes.ts").write_text(
        'import { RouterModule } from "@angular/router";\n'
        '\n'
        "export const routes = [\n"
        '    { path: "home", component: AppComponent },\n'
        "];\n",
        encoding="utf-8",
    )


def test_write_context_creates_context_pack_file():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        create_context_repo(root, with_routes=True)

        with change_directory(root):
            exit_code, output = capture_output(
                write_context,
                str(root),
                "change user login API",
            )

        output_path = root / ".aidc" / "context_pack.md"

        assert exit_code == 0
        assert output_path.exists()
        content = output_path.read_text(encoding="utf-8")
        assert "# Strata Context Pack" in content
        assert "change user login API" in content
        assert "AI Editing Instructions" in content
        assert "Strata" in output
        assert "Context complete" in output
        assert "change user login API" in output
        assert ".aidc" in output.replace("\\", "/")
        assert "context_pack.md" in output
        assert "graph.json" in output
        assert "Files" in output
        assert "Symbols" in output
        assert "Routes" in output
        assert "Relevant files" in output
        assert "Repo intelligence" in output
        assert "user_login.py" in content


def test_write_context_prints_usage_when_task_missing():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        create_context_repo(root)

        with change_directory(root):
            exit_code, output = capture_output(write_context, str(root))

        assert exit_code == 1
        assert 'Usage: strata context [--budget <preset|tokens>] "<task>" [root]' in output


def test_write_context_reports_budget_summary_when_budget_is_tight():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        create_context_repo(root)

        with change_directory(root):
            exit_code, output = capture_output(
                write_context,
                str(root),
                "--budget",
                "1",
                "change user login API",
            )

        content = (root / ".aidc" / "context_pack.md").read_text(encoding="utf-8")

        assert exit_code == 0
        assert "Budget Summary" in output
        assert "Budget mode" in output
        assert "Files included" in output
        assert "Files skipped by budget" in output
        assert "## Context Budget" in content
        assert "## Included Context" in content
        assert "## Excluded Context" in content


def test_write_context_still_works_when_routes_are_missing():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        create_context_repo(root)

        with change_directory(root):
            exit_code, output = capture_output(
                write_context,
                str(root),
                "change user login API",
            )

        output_path = root / ".aidc" / "context_pack.md"
        content = output_path.read_text(encoding="utf-8")

        assert exit_code == 0
        assert output_path.exists()
        assert "No relevant backend routes found." in content
        assert "Context complete" in output
        assert "Routes" in output
        assert "Repo intelligence" in output


def test_write_context_reports_counts_for_simple_task_case():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        create_context_repo(root)

        with change_directory(root):
            exit_code, output = capture_output(
                write_context,
                str(root),
                "fix helper bug",
            )

        content = (root / ".aidc" / "context_pack.md").read_text(encoding="utf-8")

        assert exit_code == 0
        assert "Context complete" in output
        assert "Task" in output
        assert "Output" in output
        assert "Graph" in output
        assert "Files" in output
        assert "Symbols" in output
        assert "Routes" in output
        assert "Repo intelligence" in output
        assert "fix helper bug" in content


def test_write_context_reports_frontend_repo_intelligence():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        create_frontend_context_repo(root)

        with change_directory(root):
            exit_code, output = capture_output(
                write_context,
                str(root),
                "update button service module",
            )

        content = (root / ".aidc" / "context_pack.md").read_text(encoding="utf-8")

        assert exit_code == 0
        assert "Repo intelligence" in output
        assert "Frameworks" in output
        assert "React" in output
        assert "Angular" in output
        assert "Frameworks detected:" in content
        assert "React" in content
        assert "Angular" in content
        assert "Relevant frontend symbols:" in content
        assert "Button" in content
        assert "UserService" in content
        assert "AppModule" in content


TESTS = [
    test_write_context_creates_context_pack_file,
    test_write_context_prints_usage_when_task_missing,
    test_write_context_reports_budget_summary_when_budget_is_tight,
    test_write_context_still_works_when_routes_are_missing,
    test_write_context_reports_counts_for_simple_task_case,
    test_write_context_reports_frontend_repo_intelligence,
]
