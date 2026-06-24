import contextlib
import sys
import tempfile
from pathlib import Path

from cli import main as cli_main
from patch_validator import validate_patch_file
from tests.helpers import capture_output, change_directory


def _write_patch_file(root: Path, content: str) -> Path:
    patch_path = root / ".aidc" / "agent_patch.diff"
    patch_path.parent.mkdir(parents=True, exist_ok=True)
    patch_path.write_text(content, encoding="utf-8")
    return patch_path


def _write_file(root: Path, relative_path: str, content: str) -> Path:
    file_path = root / relative_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    return file_path


@contextlib.contextmanager
def change_argv(args: list[str]):
    original = sys.argv[:]
    sys.argv = args
    try:
        yield
    finally:
        sys.argv = original


def _run_apply_cli(root: Path, *args: str):
    with change_directory(root):
        with change_argv(["cli.py", "apply", *args]):
            return capture_output(cli_main)


def _create_patch_text(target: str, new_text: str = '+print("hello")\n') -> str:
    return (
        f"diff --git a/{target} b/{target}\n"
        "new file mode 100644\n"
        "index 0000000..1111111\n"
        "--- /dev/null\n"
        f"+++ b/{target}\n"
        "@@ -0,0 +1 @@\n"
        f"{new_text}"
    )


def _modify_patch_text(target: str) -> str:
    return (
        f"diff --git a/{target} b/{target}\n"
        f"--- a/{target}\n"
        f"+++ b/{target}\n"
        "@@ -1 +1 @@\n"
        '-print("old")\n'
        '+print("new")\n'
    )


def test_create_file_patch_to_missing_file_is_valid_in_dry_run():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_patch_file(root, _create_patch_text("new_file.py"))

        result = validate_patch_file(root=root)

        assert result["status"] == "valid"
        assert result["valid"] is True
        assert result["targets"] == ["new_file.py"]
        assert result["errors"] == []


def test_create_file_patch_to_existing_file_is_invalid_in_dry_run():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_file(root, "new_file.py", 'print("existing")\n')
        _write_patch_file(root, _create_patch_text("new_file.py"))

        result = validate_patch_file(root=root)

        assert result["status"] == "invalid"
        assert result["valid"] is False
        assert result["errors"]
        assert "Target file already exists for creation: new_file.py" in result["errors"][0]


def test_modify_existing_file_patch_still_valid_in_dry_run():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_file(root, "main.py", 'print("old")\n')
        _write_patch_file(root, _modify_patch_text("main.py"))

        result = validate_patch_file(root=root)

        assert result["status"] == "valid"
        assert result["valid"] is True
        assert result["targets"] == ["main.py"]
        assert result["errors"] == []


def test_apply_dry_run_reports_create_target_exists_failure():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_file(root, "ollama_test.txt", "already here\n")
        _write_patch_file(root, _create_patch_text("ollama_test.txt", '+hello\n'))

        exit_code, output = _run_apply_cli(root, "--dry-run")

        assert exit_code == 1
        assert "Apply dry-run" in output
        assert "invalid" in output
        assert "Target file already exists for creation: ollama_test.txt" in output
        assert "Patch failed validation." in output


TESTS = [
    test_create_file_patch_to_missing_file_is_valid_in_dry_run,
    test_create_file_patch_to_existing_file_is_invalid_in_dry_run,
    test_modify_existing_file_patch_still_valid_in_dry_run,
    test_apply_dry_run_reports_create_target_exists_failure,
]
