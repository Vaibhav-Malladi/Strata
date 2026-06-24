import contextlib
import sys
import tempfile
import textwrap
from pathlib import Path

from cli import main as cli_main
from direct_edit import detect_direct_edits, snapshot_working_files, write_direct_edit_diff
from snapshot import write_snapshot
from tests.helpers import capture_output, change_directory
from workflow_config import default_config, save_config
from cli_core import build_graph
from routes import collect_routes


@contextlib.contextmanager
def change_argv(args: list[str]):
    original = sys.argv[:]
    sys.argv = args
    try:
        yield
    finally:
        sys.argv = original


def _create_repo(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "helper.py").write_text(
        "def helper():\n"
        "    return True\n",
        encoding="utf-8",
    )
    (root / "main.py").write_text("print('hello')\n", encoding="utf-8")


def _create_review_snapshot(root: Path) -> None:
    with change_directory(root):
        graph = build_graph(".")

    assert graph is not None
    write_snapshot(root, graph, collect_routes(graph))


def _run_cli(root: Path, *args: str):
    with change_directory(root):
        with change_argv(["cli.py", *args]):
            return capture_output(cli_main)


def _write_prompt(root: Path) -> Path:
    prompt_path = root / ".aidc" / "agent_prompt.md"
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text("prompt", encoding="utf-8")
    return prompt_path


def _save_config(root: Path, **overrides) -> None:
    config = default_config()
    config.update(overrides)
    save_config(config, root)


def _write_script(root: Path, name: str, body: str) -> Path:
    script_path = root / name
    script_path.write_text(textwrap.dedent(body).lstrip(), encoding="utf-8")
    return script_path


def _python_command(script_path: Path) -> str:
    return f'"{sys.executable}" "{script_path}"'


def test_snapshot_working_files_ignores_generated_dirs_and_is_stable():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)

        first_snapshot = snapshot_working_files(root)

        (root / "build").mkdir(parents=True, exist_ok=True)
        (root / "build" / "cache.txt").write_text("generated", encoding="utf-8")
        (root / ".aidc").mkdir(parents=True, exist_ok=True)
        (root / ".aidc" / "direct_edit.diff").write_text("generated diff", encoding="utf-8")

        second_snapshot = snapshot_working_files(root)

        assert first_snapshot == second_snapshot


def test_detect_direct_edits_detects_modified_file():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        before = snapshot_working_files(root)

        (root / "main.py").write_text("print('goodbye')\n", encoding="utf-8")

        assert detect_direct_edits(before, root) == ["main.py"]


def test_detect_direct_edits_detects_new_file():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        before = snapshot_working_files(root)

        (root / "new_file.py").write_text("print('new')\n", encoding="utf-8")

        assert detect_direct_edits(before, root) == ["new_file.py"]


def test_detect_direct_edits_detects_deleted_file():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        before = snapshot_working_files(root)

        (root / "helper.py").unlink()

        assert detect_direct_edits(before, root) == ["helper.py"]


def test_write_direct_edit_diff_writes_report():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)

        report_path = write_direct_edit_diff(root, ["main.py", "new_file.py"])
        content = report_path.read_text(encoding="utf-8")

        assert report_path == root / ".aidc" / "direct_edit.diff"
        assert report_path.exists()
        assert "Direct edit detected" in content
        assert "main.py" in content


def test_review_output_mentions_direct_edit_report_if_present():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        _create_repo(root)
        _create_review_snapshot(root)
        (root / ".aidc").mkdir(parents=True, exist_ok=True)
        (root / ".aidc" / "direct_edit.diff").write_text("report", encoding="utf-8")

        exit_code, output = _run_cli(root, "review")

        assert exit_code == 0
        assert "Direct edit report found" in output
        assert ".aidc/direct_edit.diff" in output.replace("\\", "/")


def test_execute_reports_direct_edit_when_adapter_changes_files_directly():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _write_prompt(root)

        script_path = _write_script(
            root,
            "fake_ai.py",
            """
            from pathlib import Path

            Path("main.py").write_text("print('edited')\\n", encoding="utf-8")
            """,
        )
        _save_config(
            root,
            mode="hybrid",
            agent="local",
            adapter="command",
            prompt_path=".aidc/agent_prompt.md",
            command=_python_command(script_path),
        )

        exit_code, output = _run_cli(root, "execute")

        assert exit_code == 1
        assert "Direct edit detected" in output
        assert ".aidc/direct_edit.diff" in output.replace("\\", "/")
        assert (root / ".aidc" / "direct_edit.diff").exists()
        assert (root / "main.py").read_text(encoding="utf-8") == "print('edited')\n"
        assert not (root / ".aidc" / "agent_patch.diff").exists()


def test_ask_reports_direct_edit_when_adapter_changes_files_directly():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_repo(root)
        _save_config(
            root,
            mode="hybrid",
            agent="local",
            adapter="command",
            prompt_path=".aidc/agent_prompt.md",
            command=_python_command(
                _write_script(
                    root,
                    "fake_ai.py",
                    """
                    from pathlib import Path

                    Path("main.py").write_text("print('ask edit')\\n", encoding="utf-8")
                    """,
                )
            ),
        )

        exit_code, output = _run_cli(root, "ask", "fix the login bug")

        assert exit_code == 1
        assert "Direct edit detected" in output
        assert ".aidc/direct_edit.diff" in output.replace("\\", "/")
        assert "Inline review" not in output
        assert (root / ".aidc" / "direct_edit.diff").exists()
        assert (root / "main.py").read_text(encoding="utf-8") == "print('ask edit')\n"


TESTS = [
    test_snapshot_working_files_ignores_generated_dirs_and_is_stable,
    test_detect_direct_edits_detects_modified_file,
    test_detect_direct_edits_detects_new_file,
    test_detect_direct_edits_detects_deleted_file,
    test_write_direct_edit_diff_writes_report,
    test_review_output_mentions_direct_edit_report_if_present,
    test_execute_reports_direct_edit_when_adapter_changes_files_directly,
    test_ask_reports_direct_edit_when_adapter_changes_files_directly,
]
