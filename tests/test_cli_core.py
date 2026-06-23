import json
import os

from cli import write_graph, show_file
from tests.helpers import run_silently, capture_output


def test_cli_write_graph_creates_output_file():
    exit_code = run_silently(write_graph, "tmp_repo")

    assert exit_code == 0
    assert os.path.exists(".aidc/graph.json")

    with open(".aidc/graph.json", "r", encoding="utf-8") as file:
        graph = json.load(file)

    assert graph["schema_version"] == 1
    assert graph["root"] == "tmp_repo"
    assert len(graph["files"]) == 2
    assert len(graph["edges"]) == 1

    paths = [file_info["path"] for file_info in graph["files"]]

    assert any(path.endswith("main.py") for path in paths)
    assert any(path.endswith("helper.py") for path in paths)

    main_file = None

    for file_info in graph["files"]:
        if file_info["path"].endswith("main.py"):
            main_file = file_info

    assert main_file is not None
    assert "os" in main_file["external_imports"]
    assert "missing_module" in main_file["unresolved_imports"]
    assert "helper" not in main_file["external_imports"]
    assert "helper" not in main_file["unresolved_imports"]

    edge = graph["edges"][0]

    assert edge["from"].endswith("main.py")
    assert edge["to"].endswith("helper.py")
    assert edge["import"] == "helper"


def test_cli_show_file_finds_saved_file():
    run_silently(write_graph, ".")

    exit_code = run_silently(show_file, "tmp_repo/main.py")

    assert exit_code == 0


def test_cli_show_file_returns_error_for_missing_file():
    run_silently(write_graph, ".")

    exit_code = run_silently(show_file, "missing.py")

    assert exit_code == 1


def test_cli_show_file_displays_unresolved_import_line_number():
    run_silently(write_graph, ".")

    exit_code, output = capture_output(show_file, "tmp_repo/main.py")

    assert exit_code == 0
    assert "Warnings" in output
    assert "Unresolved imports found in tmp_repo\\main.py:" in output
    assert "missing_module" in output
    assert "at line" in output
    assert "3" in output

def test_cli_show_file_displays_backend_routes():
    graph = {
        "schema_version": 1,
        "root": ".",
        "files": [
            {
                "path": "api.py",
                "language": "python",
                "imports": [],
                "external_imports": [],
                "unresolved_imports": [],
                "unresolved_import_details": [],
                "classes": [],
                "functions": [],
                "routes": [
                    {
                        "method": "GET",
                        "path": "/health",
                        "line": 1,
                        "source": "@app.get",
                    },
                    {
                        "method": "POST",
                        "path": "/users",
                        "line": 5,
                        "source": "@router.post",
                    },
                ],
            }
        ],
        "edges": [],
    }

    os.makedirs(".aidc", exist_ok=True)

    with open(".aidc/graph.json", "w", encoding="utf-8") as file:
        json.dump(graph, file)

    exit_code, output = capture_output(show_file, "api.py")

    assert exit_code == 0
    assert "Backend routes" in output
    assert "GET" in output
    assert "/health" in output
    assert "POST" in output
    assert "/users" in output
    assert "@app.get" in output
    assert "@router.post" in output

def test_cli_agent_prompt_command_smoke():
    import os
    import subprocess
    import sys
    from pathlib import Path

    project_root = Path(__file__).resolve().parents[1]
    cli_path = project_root / "cli.py"
    output_path = project_root / ".aidc" / "agent_prompt.md"

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    result = subprocess.run(
        [
            sys.executable,
            str(cli_path),
            "agent-prompt",
            "add agent prompt command",
            "local",
        ],
        cwd=project_root,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode == 0, result.stderr
    assert "Agent prompt generated" in result.stdout
    assert "Agent" in result.stdout
    assert "local" in result.stdout
    assert output_path.exists()

def test_cli_status_command_smoke():
    import os
    import subprocess
    import sys
    from pathlib import Path

    project_root = Path(__file__).resolve().parents[1]
    cli_path = project_root / "cli.py"

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    result = subprocess.run(
        [
            sys.executable,
            str(cli_path),
            "status",
        ],
        cwd=project_root,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode == 0, result.stderr
    assert "Strata status" in result.stdout
    assert "# Strata Status" in result.stdout
    assert "## Generated Files" in result.stdout
    assert "## Recommended Actions" in result.stdout

TESTS = [
    test_cli_write_graph_creates_output_file,
    test_cli_show_file_finds_saved_file,
    test_cli_show_file_returns_error_for_missing_file,
    test_cli_show_file_displays_unresolved_import_line_number,
    test_cli_show_file_displays_backend_routes,
    test_cli_agent_prompt_command_smoke,
    test_cli_status_command_smoke,
]