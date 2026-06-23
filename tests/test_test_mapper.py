from cli import show_tests_for
from test_mapper import suggest_tests_for_file, format_test_suggestions
from tests.helpers import capture_output, change_directory, temporary_repo


def test_mapper_graph() -> dict:
    return {
        "schema_version": 1,
        "root": "sample-root",
        "files": [
            {
                "path": "cli.py",
                "language": "python",
                "imports": [],
                "external_imports": [],
                "unresolved_imports": [],
                "unresolved_import_details": [],
                "classes": [],
                "functions": [],
            },
            {
                "path": "map_writer.py",
                "language": "python",
                "imports": [],
                "external_imports": [],
                "unresolved_imports": [],
                "unresolved_import_details": [],
                "classes": [],
                "functions": [],
            },
            {
                "path": "tests/test_map_writer.py",
                "language": "python",
                "imports": [],
                "external_imports": [],
                "unresolved_imports": [],
                "unresolved_import_details": [],
                "classes": [],
                "functions": [],
            },
            {
                "path": "impact.py",
                "language": "python",
                "imports": [],
                "external_imports": [],
                "unresolved_imports": [],
                "unresolved_import_details": [],
                "classes": [],
                "functions": [],
            },
            {
                "path": "tests/test_impact.py",
                "language": "python",
                "imports": [],
                "external_imports": [],
                "unresolved_imports": [],
                "unresolved_import_details": [],
                "classes": [],
                "functions": [],
            },
        ],
        "edges": [],
    }


def test_suggest_tests_for_map_writer():
    graph = test_mapper_graph()
    result = suggest_tests_for_file(graph, "map_writer.py")

    assert result["found"] is True
    assert result["target"].endswith("map_writer.py")
    assert "py tests.py" in result["recommended_commands"]
    assert any(command.startswith("py cli.py map") for command in result["recommended_commands"])
    assert any(path.endswith("test_map_writer.py") for path in result["related_test_files"])


def test_suggest_tests_for_impact():
    graph = test_mapper_graph()
    result = suggest_tests_for_file(graph, "impact.py")

    assert result["found"] is True
    assert result["target"].endswith("impact.py")
    assert "py tests.py" in result["recommended_commands"]
    assert any(command.startswith("py cli.py impact") for command in result["recommended_commands"])
    assert any(path.endswith("test_impact.py") for path in result["related_test_files"])


def test_suggest_tests_for_missing_file():
    graph = test_mapper_graph()
    result = suggest_tests_for_file(graph, "missing.py")

    assert result["found"] is False
    assert result["target"] == "missing.py"
    assert result["recommended_commands"] == ["py tests.py"]
    assert result["related_test_files"] == []
    assert "File not found in graph" in result["summary"]


def test_format_test_suggestions_includes_sections():
    graph = test_mapper_graph()
    result = suggest_tests_for_file(graph, "map_writer.py")
    output = format_test_suggestions(result)

    assert "Test suggestions" in output
    assert "Target:" in output
    assert "Found: True" in output
    assert "Recommended commands" in output
    assert "Likely related test files" in output
    assert "py cli.py map" in output
    assert "test_map_writer.py" in output


def test_cli_show_tests_for_displays_report():
    with temporary_repo(
        {
            "cli.py": "def main():\n    return 0\n",
            "map_writer.py": "def generate_project_map(graph):\n    return ''\n",
            "tests/test_map_writer.py": (
                "def test_cli_write_map_creates_project_map_file():\n"
                "    pass\n"
            ),
            "impact.py": "def analyze_impact(graph, target_path):\n    return {}\n",
            "tests/test_impact.py": "def test_cli_show_impact_displays_report():\n    pass\n",
        }
    ) as root:
        with change_directory(root):
            exit_code, output = capture_output(show_tests_for, ".", "map_writer.py")

    assert exit_code == 0
    assert "Test suggestions generated" in output
    assert "Test suggestions" in output
    assert "py cli.py map" in output
    assert "test_map_writer.py" in output


def test_cli_show_tests_for_returns_error_for_missing_file():
    with temporary_repo(
        {
            "cli.py": "def main():\n    return 0\n",
            "map_writer.py": "def generate_project_map(graph):\n    return ''\n",
        }
    ) as root:
        with change_directory(root):
            exit_code, output = capture_output(show_tests_for, ".", "missing.py")

    assert exit_code == 1
    assert "Test suggestion warning" in output
    assert "File not found in graph" in output


TESTS = [
    test_suggest_tests_for_map_writer,
    test_suggest_tests_for_impact,
    test_suggest_tests_for_missing_file,
    test_format_test_suggestions_includes_sections,
    test_cli_show_tests_for_displays_report,
    test_cli_show_tests_for_returns_error_for_missing_file,
]
