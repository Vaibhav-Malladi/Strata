import os
import sys
import json
import contextlib
import io

from cli import write_graph, show_file
from languages import detect_language, parse_source_file
from python_parser import parse_file
from scanner import scan_repo
from graph import validate_graph


def test_python_version():
    assert sys.version_info >= (3, 10), "Strata requires Python 3.10 or newer"

def write_file(path, content):
    with open(path, "w", encoding="utf-8") as file:
        file.write(content)


def test_parse_current_parser_file():
    result = parse_file("python_parser.py")

    assert result["path"] == "python_parser.py"
    assert result["language"] == "python"
    assert "ast" in result["imports"]
    assert result["classes"] == []

    function_names = [function["name"] for function in result["functions"]]
    assert "parse_file" in function_names

    assert "error" not in result

def test_parse_source_file_routes_python_file():
    result = parse_source_file("python_parser.py")

    assert result is not None
    assert result["path"] == "python_parser.py"
    assert result["language"] == "python"

    function_names = [function["name"] for function in result["functions"]]
    assert "parse_file" in function_names

def test_parse_syntax_error_file():
    test_path = "tmp_syntax_error.py"

    try:
        write_file(test_path, "def broken(:\n    pass\n")

        result = parse_file(test_path)

        assert result["path"] == test_path
        assert result["imports"] == []
        assert result["classes"] == []
        assert result["functions"] == []

        assert result["error"]["type"] == "syntax_error"
        assert result["error"]["line"] == 1

    finally:
        if os.path.exists(test_path):
            os.remove(test_path)

def test_scan_repo_finds_python_files():
    result = scan_repo("tmp_repo")

    paths = [file["path"] for file in result["files"]]

    assert result["root"] == "tmp_repo"
    assert len(result["files"]) == 2
    assert any(path.endswith("main.py") for path in paths)
    assert any(path.endswith("helper.py") for path in paths)

def test_language_detection():
    assert detect_language("main.py") == "python"
    assert detect_language("app.js") is None
    assert detect_language("README.md") is None

def test_validate_scanned_graph():
    result = scan_repo(".")
    problems = validate_graph(result)
    assert problems == []

def test_scan_repo_detects_imports():
    result = scan_repo("tmp_repo")

    main_file = None

    for file in result["files"]:
        if file["path"].endswith("main.py"):
            main_file = file

    assert main_file is not None
    assert "helper" in main_file["imports"]

def test_scan_repo_creates_import_edges():
    result = scan_repo("tmp_repo")

    assert "edges" in result
    assert len(result["edges"]) == 1

    edge = result["edges"][0]

    assert edge["type"] == "imports"
    assert edge["import"] == "helper"
    assert edge["from"].endswith("main.py")
    assert edge["to"].endswith("helper.py")

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
    exit_code = run_silently(write_graph, "tmp_repo")

    assert exit_code == 0
    assert os.path.exists(".aidc/graph.json")

    with open(".aidc/graph.json", "r", encoding="utf-8") as file:
        graph = json.load(file)

    assert graph["root"] == "tmp_repo"
    assert len(graph["files"]) == 2
    assert len(graph["edges"]) == 1

    paths = [file_info["path"] for file_info in graph["files"]]
    assert any(path.endswith("main.py") for path in paths)
    assert any(path.endswith("helper.py") for path in paths)

    edge = graph["edges"][0]
    assert edge["from"].endswith("main.py")
    assert edge["to"].endswith("helper.py")
    assert edge["import"] == "helper"

def test_scan_repo_resolves_same_folder_imports_from_project_root():
    result = scan_repo(".")

    matching_edges = []

    for edge in result["edges"]:
        if (
            edge["from"].endswith("tmp_repo\\main.py")
            and edge["to"].endswith("tmp_repo\\helper.py")
            and edge["import"] == "helper"
        ):
            matching_edges.append(edge)

    assert len(matching_edges) == 1

def test_cli_show_file_finds_saved_file():
    run_silently(write_graph, ".")

    exit_code = run_silently(show_file, "tmp_repo/main.py")

    assert exit_code == 0

def run_silently(function, *args):
    output = io.StringIO()

    with contextlib.redirect_stdout(output):
        result = function(*args)

    return result


def capture_output(function, *args):
    output = io.StringIO()

    with contextlib.redirect_stdout(output):
        result = function(*args)

    return result, output.getvalue()

def test_cli_show_file_returns_error_for_missing_file():
    run_silently(write_graph, ".")

    exit_code = run_silently(show_file, "missing.py")

    assert exit_code == 1

def test_scan_repo_includes_schema_version():
    result = scan_repo("tmp_repo")

    assert result["schema_version"] == 1

def test_validate_graph_requires_schema_version():
    graph = {
        "root": "tmp_repo",
        "files": [],
        "edges": [],
    }

    problems = validate_graph(graph)

    assert "graph is missing schema_version" in problems

def test_validate_graph_rejects_wrong_schema_version():
    graph = {
        "schema_version": 999,
        "root": "tmp_repo",
        "files": [],
        "edges": [],
    }

    problems = validate_graph(graph)

    assert "graph schema_version must be 1" in problems

def test_scan_repo_classifies_imports():
    result = scan_repo("tmp_repo")

    main_file = None

    for file_info in result["files"]:
        if file_info["path"].endswith("main.py"):
            main_file = file_info

    assert main_file is not None

    assert "os" in main_file["imports"]
    assert "helper" in main_file["imports"]
    assert "missing_module" in main_file["imports"]

    assert "os" in main_file["external_imports"]
    assert "missing_module" in main_file["unresolved_imports"]

    assert "helper" not in main_file["external_imports"]
    assert "helper" not in main_file["unresolved_imports"]

def test_scan_repo_records_unresolved_import_line_number():
    result = scan_repo("tmp_repo")

    main_file = None

    for file_info in result["files"]:
        if file_info["path"].endswith("main.py"):
            main_file = file_info

    assert main_file is not None

    matching_details = []

    for import_detail in main_file["unresolved_import_details"]:
        if import_detail["name"] == "missing_module":
            matching_details.append(import_detail)

    assert len(matching_details) == 1
    assert matching_details[0]["line"] == 3

def test_cli_show_file_displays_unresolved_import_line_number():
    run_silently(write_graph, ".")

    exit_code, output = capture_output(show_file, "tmp_repo/main.py")

    assert exit_code == 0
    assert "Warnings" in output
    assert "Unresolved imports found in tmp_repo\\main.py:" in output
    assert "missing_module" in output
    assert "at line" in output
    assert "3" in output

def main():
    test_python_version()
    test_parse_current_parser_file()
    test_parse_syntax_error_file()
    test_language_detection()
    test_parse_source_file_routes_python_file()
    test_scan_repo_finds_python_files()
    test_validate_scanned_graph()
    test_scan_repo_detects_imports()
    test_scan_repo_creates_import_edges()
    test_cli_write_graph_creates_output_file()
    test_scan_repo_resolves_same_folder_imports_from_project_root()
    test_cli_show_file_finds_saved_file()
    test_cli_show_file_returns_error_for_missing_file()
    test_scan_repo_includes_schema_version()
    test_validate_graph_requires_schema_version()
    test_validate_graph_rejects_wrong_schema_version()
    test_scan_repo_classifies_imports()
    test_scan_repo_records_unresolved_import_line_number()
    test_cli_show_file_displays_unresolved_import_line_number()
    print("All tests passed.")

if __name__ == "__main__":
    main()