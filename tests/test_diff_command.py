import contextlib
import json
import os
import tempfile
from pathlib import Path

from cli_core import build_graph
from commands.diff_command import write_diff_command
from routes import collect_routes
from tests.helpers import capture_output


@contextlib.contextmanager
def change_directory(path: Path):
    original = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(original)


def create_repo(root: Path, include_new_file: bool = False) -> None:
    src = root / "src"
    src.mkdir(parents=True, exist_ok=True)

    (src / "main.py").write_text(
        "from helper import helper\n\n"
        "def run():\n"
        "    return helper()\n",
        encoding="utf-8",
    )

    (src / "helper.py").write_text(
        "def helper():\n"
        "    return True\n",
        encoding="utf-8",
    )

    if include_new_file:
        (src / "new_file.py").write_text(
            "def added():\n"
            "    return 1\n",
            encoding="utf-8",
        )


def write_snapshot_state(root: Path, *, timestamp: str, graph: dict, routes=None, include_routes_file: bool = True) -> None:
    snapshot_dir = root / ".aidc" / "snapshots" / timestamp
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    (snapshot_dir / "graph.json").write_text(
        json.dumps(graph, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (snapshot_dir / "latest-marker.txt").write_text("unused", encoding="utf-8")

    if include_routes_file:
        routes_payload = routes if routes is not None else {"routes": []}
        (snapshot_dir / "routes.json").write_text(
            json.dumps(routes_payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    latest_path = root / ".aidc" / "snapshots" / "latest.txt"
    latest_path.write_text(timestamp, encoding="utf-8")


def test_diff_command_missing_snapshot_prints_clear_message():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        create_repo(root)

        with change_directory(root):
            exit_code, output = capture_output(write_diff_command, ".")

        assert exit_code == 1
        assert "No snapshot found" in output
        assert "strata snapshot" in output


def test_diff_command_writes_diff_reports_from_latest_snapshot():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        create_repo(root)

        with change_directory(root):
            graph = build_graph(".")
            assert graph is not None

            write_snapshot_state(
                root,
                timestamp="20240102_030405",
                graph=graph,
                routes=collect_routes(graph),
            )

            exit_code, output = capture_output(write_diff_command, ".")

        payload = json.loads(
            (root / ".aidc" / "diff_report.json").read_text(encoding="utf-8")
        )
        normalized_output = output.replace("\\", "/")

        assert exit_code == 0
        assert (root / ".aidc" / "diff_report.md").exists()
        assert (root / ".aidc" / "diff_report.json").exists()
        assert "# Strata Structural Diff" in (
            root / ".aidc" / "diff_report.md"
        ).read_text(encoding="utf-8")
        assert "Strata" in output
        assert "Diff complete" in output
        assert ".aidc" in normalized_output
        assert "diff_report.md" in output
        assert "diff_report.json" in output
        assert "Snapshot" in output
        assert "Files added" in output
        assert "Files removed" in output
        assert "Edges added" in output
        assert "Edges removed" in output
        assert "Routes added" in output
        assert "Routes removed" in output
        assert "Unresolved added" in output
        assert "Unresolved removed" in output
        assert "Symbols added" in output
        assert "Symbols removed" in output
        assert payload["summary"]["files_added"] == 0
        assert payload["summary"]["files_removed"] == 0
        assert payload["summary"]["edges_added"] == 0
        assert payload["summary"]["edges_removed"] == 0
        assert payload["summary"]["routes_added"] == 0
        assert payload["summary"]["routes_removed"] == 0
        assert payload["summary"]["unresolved_imports_added"] == 0
        assert payload["summary"]["unresolved_imports_removed"] == 0
        assert payload["summary"]["symbols_added"] == 0
        assert payload["summary"]["symbols_removed"] == 0


def test_diff_command_handles_missing_routes_json():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        create_repo(root)

        write_snapshot_state(
            root,
            timestamp="20240102_030405",
            graph={
                "schema_version": 1,
                "root": str(root),
                "files": [],
                "edges": [],
            },
            include_routes_file=False,
        )

        with change_directory(root):
            exit_code, output = capture_output(write_diff_command, ".")

        assert exit_code == 0
        assert "Diff complete" in output
        assert (root / ".aidc" / "diff_report.md").exists()
        assert (root / ".aidc" / "diff_report.json").exists()


def test_diff_command_detects_added_file_after_snapshot():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        create_repo(root, include_new_file=True)

        write_snapshot_state(
            root,
            timestamp="20240102_030405",
            graph={
                "schema_version": 1,
                "root": str(root),
                "files": [
                    {
                        "path": "src/main.py",
                        "language": "python",
                        "imports": [],
                        "external_imports": [],
                        "unresolved_imports": [],
                        "unresolved_import_details": [],
                        "classes": [],
                        "functions": [],
                        "interfaces": [],
                        "types": [],
                        "enums": [],
                        "exports": [],
                    },
                    {
                        "path": "src/helper.py",
                        "language": "python",
                        "imports": [],
                        "external_imports": [],
                        "unresolved_imports": [],
                        "unresolved_import_details": [],
                        "classes": [],
                        "functions": [],
                        "interfaces": [],
                        "types": [],
                        "enums": [],
                        "exports": [],
                    }
                ],
                "edges": [],
            },
            routes={"routes": []},
        )

        with change_directory(root):
            exit_code, _ = capture_output(write_diff_command, ".")

        payload = json.loads((root / ".aidc" / "diff_report.json").read_text(encoding="utf-8"))

        assert exit_code == 0
        assert payload["summary"]["files_added"] == 1
        assert os.path.normpath("src/new_file.py") in payload["files_added"]


TESTS = [
    test_diff_command_missing_snapshot_prints_clear_message,
    test_diff_command_writes_diff_reports_from_latest_snapshot,
    test_diff_command_handles_missing_routes_json,
    test_diff_command_detects_added_file_after_snapshot,
]
