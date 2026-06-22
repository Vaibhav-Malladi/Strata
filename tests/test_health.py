from cli import show_health
from health import analyze_health, format_health_report
from scanner import scan_repo
from tests.helpers import capture_output


def test_analyze_health_reports_tmp_repo_warnings():
    graph = scan_repo("tmp_repo")
    health = analyze_health(graph)

    assert health["root"] == "tmp_repo"
    assert health["file_count"] == 2
    assert health["edge_count"] == 1
    assert health["unresolved_import_count"] == 1
    assert health["cycle_count"] == 0
    assert health["status"] == "warning: unresolved imports found"

    unresolved = health["unresolved_imports"]

    assert len(unresolved) == 1
    assert unresolved[0]["path"].endswith("main.py")
    assert unresolved[0]["name"] == "missing_module"
    assert unresolved[0]["line"] == 3


def test_analyze_health_reports_cycle_warning():
    graph = {
        "schema_version": 1,
        "root": "cycle_repo",
        "files": [],
        "edges": [
            {
                "from": "a.py",
                "to": "b.py",
                "type": "imports",
                "import": "b",
            },
            {
                "from": "b.py",
                "to": "a.py",
                "type": "imports",
                "import": "a",
            },
        ],
    }

    health = analyze_health(graph)

    assert health["root"] == "cycle_repo"
    assert health["edge_count"] == 2
    assert health["cycle_count"] == 1
    assert health["status"] == "warning: circular dependencies found"


def test_format_health_report_includes_summary_and_warnings():
    graph = scan_repo("tmp_repo")
    health = analyze_health(graph)
    output = format_health_report(health)

    assert "Dependency health summary" in output
    assert "Root: tmp_repo" in output
    assert "Files: 2" in output
    assert "Dependency edges: 1" in output
    assert "Status: warning: unresolved imports found" in output
    assert "Warnings" in output
    assert "Unresolved imports: 1" in output
    assert "missing_module at line 3" in output
    assert "Files with most incoming dependencies" in output
    assert "Files with most outgoing dependencies" in output


def test_cli_show_health_displays_report():
    exit_code, output = capture_output(show_health, "tmp_repo")

    assert exit_code == 0
    assert "Dependency health warnings" in output
    assert "Dependency health summary" in output
    assert "Root: tmp_repo" in output
    assert "Unresolved imports: 1" in output
    assert "missing_module" in output


TESTS = [
    test_analyze_health_reports_tmp_repo_warnings,
    test_analyze_health_reports_cycle_warning,
    test_format_health_report_includes_summary_and_warnings,
    test_cli_show_health_displays_report,
]