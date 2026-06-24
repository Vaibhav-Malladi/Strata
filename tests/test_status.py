import json
import os
import tempfile
from pathlib import Path

from commands.status_command import show_status
from status import analyze_status, format_status_report
from tests.helpers import capture_output, change_directory


GENERATED_FILE_PATHS = [
    ".aidc/graph.json",
    ".aidc/project_map.md",
    ".aidc/task_brief.md",
    ".aidc/preflight.md",
    ".aidc/context_pack.md",
    ".aidc/agent_prompt.md",
    ".aidc/routes.md",
    ".aidc/routes.json",
    ".aidc/diff_report.md",
    ".aidc/diff_report.json",
    ".aidc/verification_report.md",
    ".aidc/verification_report.json",
    ".aidc/gate_report.md",
    ".aidc/gate_report.json",
    ".aidc/snapshots/latest.txt",
    ".aidc/cache/repo_snapshot.json",
    ".aidc/cache/repo_scan.json",
]


def write_generated_files(root: Path) -> None:
    aidc = root / ".aidc"
    aidc.mkdir(exist_ok=True)

    for relative_path in GENERATED_FILE_PATHS:
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("generated\n", encoding="utf-8")


def set_mtime(path: Path, timestamp: float) -> None:
    os.utime(path, (timestamp, timestamp))


def test_analyze_status_reports_missing_generated_files():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        (root / "main.py").write_text("print('hello')\n", encoding="utf-8")

        result = analyze_status(str(root))

        assert result["state"] == "incomplete"
        assert ".aidc/graph.json" in result["missing_files"]
        assert ".aidc/preflight.md" in result["missing_files"]
        assert ".aidc/context_pack.md" in result["missing_files"]
        assert ".aidc/routes.md" in result["missing_files"]
        assert ".aidc/routes.json" in result["missing_files"]
        assert ".aidc/diff_report.md" in result["missing_files"]
        assert ".aidc/diff_report.json" in result["missing_files"]
        assert ".aidc/verification_report.md" in result["missing_files"]
        assert ".aidc/verification_report.json" in result["missing_files"]
        assert ".aidc/gate_report.md" in result["missing_files"]
        assert ".aidc/gate_report.json" in result["missing_files"]
        assert ".aidc/snapshots/latest.txt" in result["missing_files"]
        assert ".aidc/cache/repo_snapshot.json" in result["missing_files"]
        assert ".aidc/cache/repo_scan.json" in result["missing_files"]


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
        assert ".aidc/context_pack.md" in paths
        assert ".aidc/routes.json" in paths
        assert ".aidc/diff_report.md" in paths
        assert ".aidc/diff_report.json" in paths
        assert ".aidc/verification_report.md" in paths
        assert ".aidc/verification_report.json" in paths
        assert ".aidc/gate_report.md" in paths
        assert ".aidc/gate_report.json" in paths
        assert ".aidc/snapshots/latest.txt" in paths
        assert ".aidc/cache/repo_snapshot.json" in paths
        assert ".aidc/cache/repo_scan.json" in paths


def test_analyze_status_reports_stale_outputs():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        older_time = 1_700_000_000
        newer_time = older_time + 10

        write_generated_files(root)

        source = root / "main.py"
        source.write_text("print('newer source')\n", encoding="utf-8")
        set_mtime(source, newer_time)

        for relative_path in GENERATED_FILE_PATHS:
            set_mtime(root / relative_path, older_time)

        result = analyze_status(str(root))
        normalized_stale = {
            str(path).replace("\\", "/")
            for path in result["stale_files"]
        }

        assert result["state"] == "stale"
        assert ".aidc/graph.json" in normalized_stale
        assert ".aidc/snapshots/latest.txt" in normalized_stale
        assert ".aidc/cache/repo_snapshot.json" in normalized_stale
        assert ".aidc/cache/repo_scan.json" in normalized_stale


def test_analyze_status_tracks_latest_snapshot_indicator_only():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        (root / "main.py").write_text("print('hello')\n", encoding="utf-8")
        write_generated_files(root)

        snapshot_dir = root / ".aidc" / "snapshots" / "20240102_030405"
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        (snapshot_dir / "graph.json").write_text("snapshot\n", encoding="utf-8")
        (root / ".aidc" / "snapshots" / "latest.txt").write_text(
            "20240102_030405\n",
            encoding="utf-8",
        )

        result = analyze_status(str(root))
        paths = [item["path"] for item in result["generated_files"]]

        assert ".aidc/snapshots/latest.txt" in paths
        assert ".aidc/cache/repo_snapshot.json" in paths
        assert ".aidc/cache/repo_scan.json" in paths
        assert ".aidc/snapshots/20240102_030405/graph.json" not in paths


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
                "path": ".aidc/diff_report.md",
                "exists": False,
                "modified_time": None,
            },
            {
                "path": ".aidc/context_pack.md",
                "exists": False,
                "modified_time": None,
            },
            {
                "path": ".aidc/routes.json",
                "exists": False,
                "modified_time": None,
            },
            {
                "path": ".aidc/snapshots/latest.txt",
                "exists": False,
                "modified_time": None,
            },
            {
                "path": ".aidc/cache/repo_snapshot.json",
                "exists": False,
                "modified_time": None,
            },
            {
                "path": ".aidc/cache/repo_scan.json",
                "exists": False,
                "modified_time": None,
            },
        ],
        "missing_files": [
            ".aidc/graph.json",
            ".aidc/routes.md",
            ".aidc/diff_report.md",
            ".aidc/context_pack.md",
            ".aidc/routes.json",
            ".aidc/snapshots/latest.txt",
            ".aidc/cache/repo_snapshot.json",
            ".aidc/cache/repo_scan.json",
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
    assert ".aidc/diff_report.md" in report
    assert ".aidc/context_pack.md" in report
    assert ".aidc/routes.json" in report
    assert ".aidc/snapshots/latest.txt" in report
    assert ".aidc/cache/repo_snapshot.json" in report
    assert ".aidc/cache/repo_scan.json" in report
    assert "strata routes" in report
    assert "strata snapshot" in report


def test_format_status_report_mentions_interrupted_full_scan():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        (root / "main.py").write_text("print('hello')\n", encoding="utf-8")
        write_generated_files(root)

        temp_scan = root / ".aidc" / "cache" / "repo_scan.tmp.json"
        temp_scan.parent.mkdir(parents=True, exist_ok=True)
        temp_scan.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "status": "scanning",
                    "root": str(root),
                    "file_count": 2,
                }
            ),
            encoding="utf-8",
        )

        result = analyze_status(str(root))
        report = format_status_report(result)

        assert result["full_scan"]["status"] == "interrupted"
        assert "Full scan" in report
        assert "interrupted" in report.lower()


def test_show_status_displays_repo_intelligence_when_graph_exists():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        aidc = root / ".aidc"
        aidc.mkdir(parents=True, exist_ok=True)

        graph = {
            "schema_version": 1,
            "root": str(root),
            "files": [
                {
                    "path": "src/App.tsx",
                    "language": "typescript",
                    "framework": "react",
                    "frameworks": ["react"],
                    "imports": [],
                    "external_imports": [],
                    "unresolved_imports": [],
                    "path_alias_imports": [],
                    "unresolved_import_details": [],
                    "classes": [],
                    "functions": [],
                    "components": [
                        {
                            "name": "App",
                        }
                    ],
                    "hooks": [
                        {
                            "name": "useState",
                        }
                    ],
                    "angular": {
                        "components": [],
                        "services": [],
                        "modules": [],
                        "routes": [],
                    },
                },
                {
                    "path": "src/app.component.ts",
                    "language": "typescript",
                    "framework": "angular",
                    "frameworks": ["angular"],
                    "imports": [],
                    "external_imports": [],
                    "unresolved_imports": [],
                    "path_alias_imports": [],
                    "unresolved_import_details": [],
                    "classes": [],
                    "functions": [],
                    "components": [],
                    "hooks": [],
                    "angular": {
                        "components": [
                            {
                                "name": "AppComponent",
                            }
                        ],
                        "services": [],
                        "modules": [
                            {
                                "name": "AppModule",
                            }
                        ],
                        "routes": [
                            {
                                "name": "home",
                                "path": "home",
                            }
                        ],
                    },
                },
            ],
            "edges": [],
        }

        (aidc / "graph.json").write_text(json.dumps(graph), encoding="utf-8")
        (root / "main.py").write_text("print('hello')\n", encoding="utf-8")

        with change_directory(root):
            exit_code, output = capture_output(show_status, ".")

        assert exit_code is None
        assert "Repo intelligence" in output
        assert "React" in output
        assert "Angular" in output
        assert "Components" in output
        assert "Angular routes" in output
        assert "Strata status" in output


TESTS = [
    test_analyze_status_reports_missing_generated_files,
    test_analyze_status_reports_current_when_outputs_exist,
    test_analyze_status_reports_stale_outputs,
    test_analyze_status_tracks_latest_snapshot_indicator_only,
    test_format_status_report_contains_sections,
    test_format_status_report_mentions_interrupted_full_scan,
    test_show_status_displays_repo_intelligence_when_graph_exists,
]
