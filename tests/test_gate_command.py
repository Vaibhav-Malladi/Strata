import contextlib
import json
import sys
import tempfile
from pathlib import Path

from cli import main as cli_main
from commands.gate_command import write_gate_command
from tests.helpers import capture_output


@contextlib.contextmanager
def change_argv(args: list[str]):
    original = sys.argv[:]
    sys.argv = args
    try:
        yield
    finally:
        sys.argv = original


def create_gate_repo(
    root: Path,
    *,
    unresolved: bool = False,
    with_routes: bool = False,
) -> None:
    (root / "src").mkdir(parents=True, exist_ok=True)

    if unresolved:
        source = "import missing_module\n\n\ndef run():\n    return 1\n"
    elif with_routes:
        source = (
            '@app.get("/health")\n\n'
            "def run():\n"
            "    return 1\n"
        )
    else:
        source = "def run():\n    return 1\n"

    (root / "src" / "main.py").write_text(source, encoding="utf-8")

    if with_routes:
        (root / "src" / "helper.py").write_text(
            "def helper():\n"
            "    return 2\n",
            encoding="utf-8",
        )


def run_gate_via_cli(root: Path):
    with change_argv(["cli.py", "gate", str(root)]):
        return capture_output(cli_main)


def test_gate_command_writes_reports():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        root.mkdir()
        create_gate_repo(root)

        exit_code, _ = capture_output(write_gate_command, str(root))

        assert exit_code == 0
        assert (root / ".aidc" / "gate_report.md").exists()
        assert (root / ".aidc" / "gate_report.json").exists()


def test_gate_command_markdown_contains_required_sections():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        root.mkdir()
        create_gate_repo(root)

        exit_code, _ = capture_output(write_gate_command, str(root))
        markdown = (root / ".aidc" / "gate_report.md").read_text(encoding="utf-8")

        assert exit_code == 0
        assert "# Strata Gate Report" in markdown
        assert "Status" in markdown
        assert "Recommended Verification" in markdown


def test_gate_command_json_contains_expected_fields():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        root.mkdir()
        create_gate_repo(root)

        exit_code, _ = capture_output(write_gate_command, str(root))
        payload = json.loads(
            (root / ".aidc" / "gate_report.json").read_text(encoding="utf-8")
        )

        assert exit_code == 0
        assert "status" in payload
        assert "summary" in payload
        assert "failures" in payload
        assert "warnings" in payload


def test_gate_command_clean_repo_reports_pass_or_warn_without_crashing():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        root.mkdir()
        create_gate_repo(root)

        exit_code, _ = run_gate_via_cli(root)
        payload = json.loads(
            (root / ".aidc" / "gate_report.json").read_text(encoding="utf-8")
        )

        assert exit_code == 0
        assert payload["status"] in {"PASS", "WARN"}


def test_gate_command_reports_fail_for_unresolved_imports():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        root.mkdir()
        create_gate_repo(root, unresolved=True)

        exit_code, _ = capture_output(write_gate_command, str(root))
        payload = json.loads(
            (root / ".aidc" / "gate_report.json").read_text(encoding="utf-8")
        )

        assert exit_code == 1
        assert payload["status"] == "FAIL"
        assert payload["failures"]


def test_gate_command_works_with_no_backend_routes():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        root.mkdir()
        create_gate_repo(root, with_routes=False)

        exit_code, _ = capture_output(write_gate_command, str(root))
        payload = json.loads(
            (root / ".aidc" / "gate_report.json").read_text(encoding="utf-8")
        )

        assert exit_code == 0
        assert payload["summary"]["route_count"] == 0
        assert (root / ".aidc" / "gate_report.md").exists()
        assert (root / ".aidc" / "gate_report.json").exists()


def test_gate_command_invalid_root_prints_clear_message_and_does_not_crash():
    with tempfile.TemporaryDirectory() as temp_dir:
        missing_root = Path(temp_dir) / "missing"

        exit_code, output = capture_output(write_gate_command, str(missing_root))

        assert exit_code == 1
        assert "Scan failed" in output
        assert "path does not exist" in output


TESTS = [
    test_gate_command_writes_reports,
    test_gate_command_markdown_contains_required_sections,
    test_gate_command_json_contains_expected_fields,
    test_gate_command_clean_repo_reports_pass_or_warn_without_crashing,
    test_gate_command_reports_fail_for_unresolved_imports,
    test_gate_command_works_with_no_backend_routes,
    test_gate_command_invalid_root_prints_clear_message_and_does_not_crash,
]
