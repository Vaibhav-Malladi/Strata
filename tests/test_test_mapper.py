from cli import show_tests_for
from scanner import scan_repo
from test_mapper import suggest_tests_for_file, format_test_suggestions
from tests.helpers import capture_output


def test_suggest_tests_for_map_writer():
    graph = scan_repo(".")
    result = suggest_tests_for_file(graph, "map_writer.py")

    assert result["found"] is True
    assert result["target"].endswith("map_writer.py")
    assert "py tests.py" in result["recommended_commands"]
    assert "py cli.py map tmp_repo" in result["recommended_commands"]
    assert any(path.endswith("test_map_writer.py") for path in result["related_test_files"])


def test_suggest_tests_for_impact():
    graph = scan_repo(".")
    result = suggest_tests_for_file(graph, "impact.py")

    assert result["found"] is True
    assert result["target"].endswith("impact.py")
    assert "py tests.py" in result["recommended_commands"]
    assert "py cli.py impact tmp_repo helper.py" in result["recommended_commands"]
    assert any(path.endswith("test_impact.py") for path in result["related_test_files"])


def test_suggest_tests_for_missing_file():
    graph = scan_repo(".")
    result = suggest_tests_for_file(graph, "missing.py")

    assert result["found"] is False
    assert result["target"] == "missing.py"
    assert result["recommended_commands"] == ["py tests.py"]
    assert result["related_test_files"] == []
    assert "File not found in graph" in result["summary"]


def test_format_test_suggestions_includes_sections():
    graph = scan_repo(".")
    result = suggest_tests_for_file(graph, "map_writer.py")
    output = format_test_suggestions(result)

    assert "Test suggestions" in output
    assert "Target:" in output
    assert "Found: True" in output
    assert "Recommended commands" in output
    assert "Likely related test files" in output
    assert "py cli.py map tmp_repo" in output
    assert "test_map_writer.py" in output


def test_cli_show_tests_for_displays_report():
    exit_code, output = capture_output(show_tests_for, ".", "map_writer.py")

    assert exit_code == 0
    assert "Test suggestions generated" in output
    assert "Test suggestions" in output
    assert "py cli.py map tmp_repo" in output
    assert "test_map_writer.py" in output


def test_cli_show_tests_for_returns_error_for_missing_file():
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