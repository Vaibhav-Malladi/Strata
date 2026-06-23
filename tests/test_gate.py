import json
import tempfile
from pathlib import Path

from gate import build_gate_markdown, evaluate_gate, write_gate_report


def clean_gate_graph() -> dict:
    return {
        "schema_version": 1,
        "root": "sample-root",
        "files": [
            {
                "path": "src/app.py",
                "language": "python",
                "imports": [],
                "external_imports": [],
                "unresolved_imports": [],
                "unresolved_import_details": [],
                "classes": [],
                "functions": [],
            }
        ],
        "edges": [],
    }


def test_clean_fake_graph_produces_pass():
    report = evaluate_gate(clean_gate_graph(), {"routes": []})

    assert report["status"] == "PASS"
    assert report["failures"] == []
    assert report["warnings"] == []
    assert report["summary"]["file_count"] == 1
    assert report["summary"]["edge_count"] == 0
    assert report["summary"]["route_count"] == 0


def test_graph_with_unresolved_imports_produces_fail():
    graph = clean_gate_graph()
    graph["files"][0]["unresolved_imports"] = ["missing_module"]

    report = evaluate_gate(graph, {"routes": []})

    assert report["status"] == "FAIL"
    assert any("unresolved imports" in failure for failure in report["failures"])


def test_graph_with_file_error_field_produces_fail():
    graph = clean_gate_graph()
    graph["files"][0]["error"] = "parse error"

    report = evaluate_gate(graph, {"routes": []})

    assert report["status"] == "FAIL"
    assert any("syntax/error fields" in failure for failure in report["failures"])


def test_empty_no_source_graph_does_not_crash():
    graph = {
        "schema_version": 1,
        "root": "sample-root",
        "files": [],
        "edges": [],
    }

    report = evaluate_gate(graph, {"routes": []})

    assert report["status"] in {"WARN", "FAIL"}
    assert report["summary"]["file_count"] == 0


def test_routes_data_with_duplicate_warnings_produces_warn():
    routes_data = {
        "routes": [
            {"method": "GET", "path": "/health"},
            {"method": "GET", "path": "/health"},
        ]
    }

    report = evaluate_gate(clean_gate_graph(), routes_data)

    assert report["status"] == "WARN"
    assert report["summary"]["duplicate_route_warning_count"] == 1
    assert any("duplicate route warnings" in warning for warning in report["warnings"])


def test_routes_data_with_import_risks_produces_warn():
    routes_data = {
        "routes": [],
        "route_import_risks": [
            {
                "file": "src/app.py",
                "unresolved_imports": [
                    {
                        "name": "missing_service",
                        "line": 3,
                    }
                ],
            }
        ],
    }

    report = evaluate_gate(clean_gate_graph(), routes_data)

    assert report["status"] == "WARN"
    assert report["summary"]["route_import_risk_count"] == 1
    assert any("route import risks" in warning for warning in report["warnings"])


def test_malformed_graph_produces_fail_and_does_not_crash():
    graph = {
        "schema_version": 1,
        "root": "sample-root",
        "files": "bad",
        "edges": None,
    }

    report = evaluate_gate(graph, {"routes": []})

    assert report["status"] == "FAIL"
    assert report["failures"]


def test_gate_markdown_includes_required_sections():
    markdown = build_gate_markdown(evaluate_gate(clean_gate_graph(), {"routes": []}))

    assert "# Strata Gate Report" in markdown
    assert "Status" in markdown
    assert "Recommended Verification" in markdown


def test_write_gate_report_writes_json_and_markdown():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        root.mkdir()

        report = evaluate_gate(clean_gate_graph(), {"routes": []})
        result = write_gate_report(root, report)

        json_path = root / ".aidc" / "gate_report.json"
        markdown_path = root / ".aidc" / "gate_report.md"

        assert json_path.exists()
        assert markdown_path.exists()
        assert Path(result["json_path"]) == json_path
        assert Path(result["markdown_path"]) == markdown_path

        payload = json.loads(json_path.read_text(encoding="utf-8"))

        assert payload["status"] == "PASS"
        assert markdown_path.read_text(encoding="utf-8").startswith(
            "# Strata Gate Report"
        )


TESTS = [
    test_clean_fake_graph_produces_pass,
    test_graph_with_unresolved_imports_produces_fail,
    test_graph_with_file_error_field_produces_fail,
    test_empty_no_source_graph_does_not_crash,
    test_routes_data_with_duplicate_warnings_produces_warn,
    test_routes_data_with_import_risks_produces_warn,
    test_malformed_graph_produces_fail_and_does_not_crash,
    test_gate_markdown_includes_required_sections,
    test_write_gate_report_writes_json_and_markdown,
]
