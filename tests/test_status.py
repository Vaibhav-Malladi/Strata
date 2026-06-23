import tempfile
from pathlib import Path

from status import analyze_status, format_status_report


GENERATED_FILE_PATHS = [
    ".aidc/graph.json",
    ".aidc/project_map.md",
    ".aidc/task_brief.md",
    ".aidc/preflight.md",
    ".aidc/agent_prompt.md",
    ".aidc/routes.md",
    ".aidc/routes.json",
]


def write_generated_files(root: Path) -> None:
    aidc = root / ".aidc"
    aidc.mkdir(exist_ok=True)

    for relative_path in GENERATED_FILE_PATHS:
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("generated\n", encoding="utf-8")


def test_analyze_status_reports_missing_generated_files():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        (root / "main.py").write_text("print('hello')\n", encoding="utf-8")

        result = analyze_status(str(root))

        assert result["state"] == "incomplete"
        assert ".aidc/graph.json" in result["missing_files"]
        assert ".aidc/preflight.md" in result["missing_files"]
        assert ".aidc/routes.md" in result["missing_files"]
        assert ".aidc/routes.json" in result["missing_files"]


def test_analyze_status_reports_current_when_outputs_exist():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        (root / "main.py").write_text("print('hello')\n", encoding="utf-8")
        write_generated_files(root)

        result = analyze_status(str(root))

        assert result["state"] == "current"
        assert result["missing_files"] == []
        assert result["stale_files"] == []

        paths = [
            item["path"]
            for item in result["generated_files"]
        ]

        assert ".aidc/routes.md" in paths
        assert ".aidc/routes.json" in paths


def test_analyze_status_reports_stale_outputs():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        write_generated_files(root)

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
            },
            {
                "path": ".aidc/routes.md",
                "exists": False,
                "modified_time": None,
            },
            {
                "path": ".aidc/routes.json",
                "exists": False,
                "modified_time": None,
            },
        ],
        "missing_files": [
            ".aidc/graph.json",
            ".aidc/routes.md",
            ".aidc/routes.json",
        ],
        "stale_files": [],
        "newest_source_mtime": None,
    }

    report = format_status_report(status)

    assert "# Strata Status" in report
    assert "## Generated Files" in report
    assert "## Missing Outputs" in report
    assert "## Recommended Actions" in report
    assert ".aidc/routes.md" in report
    assert ".aidc/routes.json" in report
    assert "py cli.py routes" in report


TESTS = [
    test_analyze_status_reports_missing_generated_files,
    test_analyze_status_reports_current_when_outputs_exist,
    test_analyze_status_reports_stale_outputs,
    test_format_status_report_contains_sections,
]