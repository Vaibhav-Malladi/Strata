import tempfile
from datetime import datetime
from pathlib import Path

from snapshot import (
    build_snapshot_summary_markdown,
    make_snapshot_timestamp,
    summarize_snapshot,
    write_snapshot,
)


def snapshot_graph() -> dict:
    return {
        "schema_version": 1,
        "root": "sample-root",
        "files": [
            {
                "path": "src/app.py",
                "language": "python",
                "framework": "fastapi",
                "imports": [],
                "external_imports": [],
                "unresolved_imports": ["missing_service"],
                "unresolved_import_details": [
                    {
                        "name": "missing_service",
                        "line": 4,
                    }
                ],
                "classes": [],
                "functions": [],
            },
            {
                "path": "src/web.ts",
                "language": "typescript",
                "framework": "next",
                "imports": [],
                "external_imports": [],
                "unresolved_imports": ["../db/client"],
                "unresolved_import_details": [
                    {
                        "name": "../db/client",
                        "line": 8,
                    }
                ],
                "classes": [],
                "functions": [],
                "error": "parse warning",
            },
        ],
        "edges": [
            {
                "from": "src/app.py",
                "to": "src/web.ts",
                "type": "imports",
                "import": "web",
            }
        ],
    }


def test_make_snapshot_timestamp_uses_windows_safe_format():
    timestamp = make_snapshot_timestamp(datetime(2024, 1, 2, 3, 4, 5))

    assert timestamp == "20240102_030405"


def test_summarize_snapshot_counts_core_metadata():
    summary = summarize_snapshot(
        snapshot_graph(),
        {
            "routes": [
                {"method": "GET", "path": "/health"},
                {"method": "POST", "path": "/users"},
            ]
        },
    )

    assert summary["file_count"] == 2
    assert summary["edge_count"] == 1
    assert summary["route_count"] == 2
    assert summary["unresolved_import_count"] == 2
    assert summary["language_counts"] == {
        "python": 1,
        "typescript": 1,
    }
    assert summary["framework_counts"] == {
        "fastapi": 1,
        "next": 1,
    }
    assert summary["error_count"] == 1


def test_write_snapshot_writes_core_files_and_summary():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        root.mkdir()

        result = write_snapshot(
            root,
            snapshot_graph(),
            {
                "routes": [
                    {"method": "GET", "path": "/health"},
                ]
            },
            timestamp="20240102_030405",
        )

        snapshot_dir = root / ".aidc" / "snapshots" / "20240102_030405"

        assert snapshot_dir.exists()
        assert (snapshot_dir / "graph.json").exists()
        assert (snapshot_dir / "routes.json").exists()
        assert (snapshot_dir / "summary.md").exists()
        assert (root / ".aidc" / "snapshots" / "latest.txt").exists()
        assert result["timestamp"] == "20240102_030405"
        assert Path(result["graph_path"]).exists()
        assert Path(result["routes_path"]).exists()
        assert Path(result["summary_path"]).exists()


def test_latest_txt_contains_timestamp():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        root.mkdir()

        write_snapshot(
            root,
            snapshot_graph(),
            {"routes": []},
            timestamp="20240102_030405",
        )

        latest_text = (root / ".aidc" / "snapshots" / "latest.txt").read_text(
            encoding="utf-8",
        )

        assert latest_text == "20240102_030405"


def test_summary_markdown_contains_expected_sections():
    summary = summarize_snapshot(snapshot_graph(), {"routes": []})
    summary["timestamp"] = "20240102_030405"
    summary["root"] = "sample-root"

    markdown = build_snapshot_summary_markdown(summary)

    assert "# Strata Snapshot Summary" in markdown
    assert "Files" in markdown
    assert "Edges" in markdown
    assert "Routes" in markdown
    assert "Unresolved Imports" in markdown
    assert "Languages" in markdown
    assert "Frameworks" in markdown
    assert "Errors" in markdown


def test_write_snapshot_handles_routes_data_none():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        root.mkdir()

        result = write_snapshot(
            root,
            snapshot_graph(),
            None,
            timestamp="20240102_030405",
        )

        assert result["summary"]["route_count"] == 0
        assert (root / ".aidc" / "snapshots" / "20240102_030405" / "routes.json").exists()


def test_write_snapshot_handles_routes_data_list():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        root.mkdir()

        result = write_snapshot(
            root,
            snapshot_graph(),
            [
                {"method": "GET", "path": "/health"},
                {"method": "POST", "path": "/users"},
            ],
            timestamp="20240102_030405",
        )

        assert result["summary"]["route_count"] == 2
        assert (root / ".aidc" / "snapshots" / "20240102_030405" / "routes.json").exists()


TESTS = [
    test_make_snapshot_timestamp_uses_windows_safe_format,
    test_summarize_snapshot_counts_core_metadata,
    test_write_snapshot_writes_core_files_and_summary,
    test_latest_txt_contains_timestamp,
    test_summary_markdown_contains_expected_sections,
    test_write_snapshot_handles_routes_data_none,
    test_write_snapshot_handles_routes_data_list,
]
