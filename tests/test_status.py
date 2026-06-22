import tempfile
from pathlib import Path

from status import analyze_status, format_status_report


def test_analyze_status_reports_missing_generated_files():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        (root / "main.py").write_text("print('hello')\n", encoding="utf-8")

        result = analyze_status(str(root))

        assert result["state"] == "incomplete"
        assert ".aidc/graph.json" in result["missing_files"]
        assert ".aidc/preflight.md" in result["missing_files"]


def test_analyze_status_reports_current_when_outputs_exist():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        aidc = root / ".aidc"
        aidc.mkdir()

        (root / "main.py").write_text("print('hello')\n", encoding="utf-8")

        for relative_path in [
            ".aidc/graph.json",
            ".aidc/project_map.md",
            ".aidc/task_brief.md",
            ".aidc/preflight.md",
            ".aidc/agent_prompt.md",
        ]:
            path = root / relative_path
            path.write_text("generated\n", encoding="utf-8")

        result = analyze_status(str(root))

        assert result["state"] == "current"
        assert result["missing_files"] == []
        assert result["stale_files"] == []


def test_analyze_status_reports_stale_outputs():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        aidc = root / ".aidc"
        aidc.mkdir()

        for relative_path in [
            ".aidc/graph.json",
            ".aidc/project_map.md",
            ".aidc/task_brief.md",
            ".aidc/preflight.md",
            ".aidc/agent_prompt.md",
        ]:
            path = root / relative_path
            path.write_text("generated\n", encoding="utf-8")

        source = root / "main.py"
        source.write_text("print('newer source')\n", encoding="utf-8")

        result = analyze_status(str(root))

        assert result["state"] == "stale"
        assert ".aidc/graph.json" in result["stale_files"]


def test_format_status_report_contains_sections():
    status = {
        "root": ".",
        "state": "incomplete",
        "generated_files": [
            {
                "path": ".aidc/graph.json",
                "exists": False,
                "modified_time": None,
            }
        ],
        "missing_files": [".aidc/graph.json"],
        "stale_files": [],
        "newest_source_mtime": None,
    }

    report = format_status_report(status)

    assert "# Strata Status" in report
    assert "## Generated Files" in report
    assert "## Missing Outputs" in report
    assert "## Recommended Actions" in report


TESTS = [
    test_analyze_status_reports_missing_generated_files,
    test_analyze_status_reports_current_when_outputs_exist,
    test_analyze_status_reports_stale_outputs,
    test_format_status_report_contains_sections,
]