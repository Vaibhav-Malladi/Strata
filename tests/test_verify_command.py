import contextlib
import json
import os
import tempfile
from pathlib import Path

from cli_core import build_graph
import commands.verify_command as old_verify_command
from commands.verify_command import write_verify_command
from routes import collect_routes
import strata.commands.verify_command as new_verify_command
from tests.helpers import capture_output


@contextlib.contextmanager
def change_directory(path: Path):
    original = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(original)


def _file_entry(path: str, imports: list[str] | None = None) -> dict:
    return {
        "path": path,
        "language": "python",
        "imports": imports or [],
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


def test_verify_command_shim_exports_new_implementation():
    assert old_verify_command.write_verify_command is new_verify_command.write_verify_command


def _create_repo(root: Path, *, add_file: bool = False, unresolved: bool = False) -> None:
    src = root / "src"
    src.mkdir(parents=True, exist_ok=True)

    if unresolved:
        main_source = "import missing_module\n\n\ndef run():\n    return 1\n"
    else:
        main_source = "def run():\n    return 1\n"

    (src / "main.py").write_text(main_source, encoding="utf-8")

    if add_file:
        (src / "new_file.py").write_text(
            "def added():\n    return 2\n",
            encoding="utf-8",
        )


def _write_snapshot_state(
    root: Path,
    *,
    timestamp: str,
    graph: dict,
    routes: dict | list | None = None,
    include_routes_file: bool = True,
) -> None:
    snapshot_dir = root / ".aidc" / "snapshots" / timestamp
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    (snapshot_dir / "graph.json").write_text(
        json.dumps(graph, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    if include_routes_file:
        payload = routes if routes is not None else {"routes": []}
        (snapshot_dir / "routes.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    (root / ".aidc" / "snapshots" / "latest.txt").write_text(
        timestamp,
        encoding="utf-8",
    )


def _base_graph(root: Path, *, include_new_file: bool = False, unresolved: bool = False) -> dict:
    files = [_file_entry("src/main.py", ["missing_module"] if unresolved else [])]

    if include_new_file:
        files.append(_file_entry("src/new_file.py"))

    return {
        "schema_version": 1,
        "root": str(root),
        "files": files,
        "edges": [],
    }


def test_verify_command_missing_snapshot_prints_clear_message_and_does_not_crash():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        root.mkdir()
        _create_repo(root)

        with change_directory(root):
            exit_code, output = capture_output(write_verify_command, ".")

        assert exit_code == 1
        assert "No snapshot found" in output
        assert "strata snapshot" in output


def test_verify_command_writes_reports_from_latest_snapshot():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        root.mkdir()
        _create_repo(root)

        with change_directory(root):
            current_graph = build_graph(".")
            assert current_graph is not None

            _write_snapshot_state(
                root,
                timestamp="20240102_030405",
                graph=current_graph,
                routes=collect_routes(current_graph),
            )

            exit_code, output = capture_output(write_verify_command, ".")

        payload = json.loads(
            (root / ".aidc" / "verification_report.json").read_text(
                encoding="utf-8"
            )
        )
        normalized_output = output.replace("\\", "/")

        assert exit_code == 0
        assert (root / ".aidc" / "verification_report.md").exists()
        assert (root / ".aidc" / "verification_report.json").exists()
        assert "Strata" in output
        assert "Verification complete" in output
        assert "PASS" in output
        assert "✓" in output
        assert "Failures" in output
        assert "Warnings" in output
        assert ".aidc/verification_report.md" in normalized_output
        assert ".aidc/verification_report.json" in normalized_output
        assert payload["status"] == "PASS"
        assert payload["failures"] == []
        assert payload["warnings"] == []
        recommended_commands = [
            command.replace("\\", "/")
            for command in payload["recommended_commands"]
        ]
        assert recommended_commands == [
            "py tests.py",
            "py tests/run.py",
        ]


def test_verify_command_markdown_contains_required_sections():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        root.mkdir()
        _create_repo(root)
        _write_snapshot_state(
            root,
            timestamp="20240102_030405",
            graph=_base_graph(root),
        )

        with change_directory(root):
            exit_code, _ = capture_output(write_verify_command, ".")

        markdown = (root / ".aidc" / "verification_report.md").read_text(
            encoding="utf-8"
        )

        assert exit_code == 0
        assert "# Strata Verification Report" in markdown
        assert "Status" in markdown


def test_verify_command_json_contains_expected_fields():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        root.mkdir()
        _create_repo(root)
        _write_snapshot_state(
            root,
            timestamp="20240102_030405",
            graph=_base_graph(root),
        )

        with change_directory(root):
            exit_code, _ = capture_output(write_verify_command, ".")

        payload = json.loads(
            (root / ".aidc" / "verification_report.json").read_text(
                encoding="utf-8"
            )
        )

        assert exit_code == 0
        assert "status" in payload
        assert "summary" in payload
        assert "failures" in payload
        assert "warnings" in payload


def test_verify_command_works_when_routes_json_is_missing_or_empty():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        root.mkdir()
        _create_repo(root)
        _write_snapshot_state(
            root,
            timestamp="20240102_030405",
            graph=_base_graph(root),
            include_routes_file=False,
        )

        with change_directory(root):
            exit_code, _ = capture_output(write_verify_command, ".")

        assert exit_code == 0
        assert (root / ".aidc" / "verification_report.md").exists()
        assert (root / ".aidc" / "verification_report.json").exists()

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        root.mkdir()
        _create_repo(root)
        _write_snapshot_state(
            root,
            timestamp="20240102_030405",
            graph=_base_graph(root),
            routes={"routes": []},
        )

        with change_directory(root):
            exit_code, _ = capture_output(write_verify_command, ".")

        assert exit_code == 0
        assert (root / ".aidc" / "verification_report.md").exists()
        assert (root / ".aidc" / "verification_report.json").exists()


def test_verify_command_reports_warn_when_file_added_after_snapshot():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        root.mkdir()
        _create_repo(root, add_file=True)
        _write_snapshot_state(
            root,
            timestamp="20240102_030405",
            graph=_base_graph(root),
        )

        with change_directory(root):
            exit_code, _ = capture_output(write_verify_command, ".")

        payload = json.loads(
            (root / ".aidc" / "verification_report.json").read_text(
                encoding="utf-8"
            )
        )

        assert exit_code == 0
        assert payload["status"] == "WARN"
        assert payload["summary"]["files_added"] == 1


def test_verify_command_reports_fail_when_unresolved_imports_are_added():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        root.mkdir()
        _create_repo(root, unresolved=True)
        _write_snapshot_state(
            root,
            timestamp="20240102_030405",
            graph=_base_graph(root),
        )

        with change_directory(root):
            exit_code, _ = capture_output(write_verify_command, ".")

        payload = json.loads(
            (root / ".aidc" / "verification_report.json").read_text(
                encoding="utf-8"
            )
        )

        assert exit_code == 1
        assert payload["status"] == "FAIL"
        assert payload["failures"]


TESTS = [
    test_verify_command_shim_exports_new_implementation,
    test_verify_command_missing_snapshot_prints_clear_message_and_does_not_crash,
    test_verify_command_writes_reports_from_latest_snapshot,
    test_verify_command_markdown_contains_required_sections,
    test_verify_command_json_contains_expected_fields,
    test_verify_command_works_when_routes_json_is_missing_or_empty,
    test_verify_command_reports_warn_when_file_added_after_snapshot,
    test_verify_command_reports_fail_when_unresolved_imports_are_added,
]
