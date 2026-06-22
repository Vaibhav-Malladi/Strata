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


TESTS = [
    test_cli_write_graph_creates_output_file,
    test_cli_show_file_finds_saved_file,
    test_cli_show_file_returns_error_for_missing_file,
    test_cli_show_file_displays_unresolved_import_line_number,
]