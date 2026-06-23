from cli import show_impact
from impact import analyze_impact, format_impact_report
from scanner import scan_repo
from tests.helpers import capture_output, change_directory, temporary_repo


def _impact_repo():
    return temporary_repo(
        {
            "helper.py": "def helper():\n    return True\n",
            "main.py": "import helper\n",
        }
    )


def test_analyze_impact_reports_helper_dependents():
    with _impact_repo() as root:
        graph = scan_repo(str(root))
        impact = analyze_impact(graph, "helper.py")

    assert impact["found"] is True
    assert impact["target"].endswith("helper.py")
    assert impact["risk_level"] == "medium"
    assert len(impact["direct_dependents"]) == 1
    assert impact["direct_dependents"][0].endswith("main.py")
    assert impact["direct_dependencies"] == []
    assert len(impact["transitive_dependents"]) == 1
    assert impact["transitive_dependents"][0].endswith("main.py")


def test_analyze_impact_reports_main_dependencies():
    with _impact_repo() as root:
        graph = scan_repo(str(root))
        impact = analyze_impact(graph, "main.py")

    assert impact["found"] is True
    assert impact["target"].endswith("main.py")
    assert impact["risk_level"] == "low"
    assert impact["direct_dependents"] == []
    assert len(impact["direct_dependencies"]) == 1
    assert impact["direct_dependencies"][0].endswith("helper.py")
    assert impact["transitive_dependents"] == []


def test_analyze_impact_reports_missing_file():
    with _impact_repo() as root:
        graph = scan_repo(str(root))
        impact = analyze_impact(graph, "missing.py")

    assert impact["found"] is False
    assert impact["target"] == "missing.py"
    assert impact["risk_level"] == "unknown"
    assert "File not found in graph" in impact["summary"]


def test_format_impact_report_includes_sections():
    with _impact_repo() as root:
        graph = scan_repo(str(root))
        impact = analyze_impact(graph, "helper.py")

    output = format_impact_report(impact)

    assert "Impact analysis" in output
    assert "Found: True" in output
    assert "Risk level: medium" in output
    assert "Direct dependents" in output
    assert "Direct dependencies" in output
    assert "Transitive dependents" in output
    assert "main.py" in output


def test_cli_show_impact_displays_report():
    with _impact_repo() as root:
        with change_directory(root):
            exit_code, output = capture_output(show_impact, str(root), "helper.py")

    assert exit_code == 0
    assert "Impact analysis warning" in output
    assert "Impact analysis" in output
    assert "Risk level: medium" in output
    assert "main.py" in output


def test_cli_show_impact_returns_error_for_missing_file():
    with _impact_repo() as root:
        with change_directory(root):
            exit_code, output = capture_output(show_impact, str(root), "missing.py")

    assert exit_code == 1
    assert "Impact analysis failed" in output
    assert "File not found in graph" in output


TESTS = [
    test_analyze_impact_reports_helper_dependents,
    test_analyze_impact_reports_main_dependencies,
    test_analyze_impact_reports_missing_file,
    test_format_impact_report_includes_sections,
    test_cli_show_impact_displays_report,
    test_cli_show_impact_returns_error_for_missing_file,
]
