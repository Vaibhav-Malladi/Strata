import tempfile
from pathlib import Path

import commands.patch_command as old_patch_command
import strata.commands.patch_command as new_patch_command
from commands.patch_command import write_patch_command
from tests.helpers import capture_output, change_directory


def test_new_patch_command_import_matches_legacy_shim():
    assert new_patch_command.write_patch_command is old_patch_command.write_patch_command


def _create_patch_file(root: Path, content: str) -> Path:
    patch_path = root / ".aidc" / "agent_patch.diff"
    patch_path.parent.mkdir(parents=True, exist_ok=True)
    patch_path.write_text(content, encoding="utf-8")
    return patch_path


def test_patch_command_missing_returns_nonzero_and_does_not_create_aidc():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        with change_directory(root):
            exit_code, output = capture_output(write_patch_command, ".")

        assert exit_code == 1
        assert "Patch inspect" in output
        assert "missing" in output
        assert "Patch file not found." in output
        assert "Exists" in output
        assert "no" in output
        assert "0 bytes" in output
        assert ".aidc/agent_patch.diff" in output.replace("\\", "/")
        assert not (root / ".aidc").exists()


def test_patch_command_empty_returns_nonzero_and_prints_empty():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_patch_file(root, "")

        with change_directory(root):
            exit_code, output = capture_output(write_patch_command, ".")

        assert exit_code == 1
        assert "Patch inspect" in output
        assert "empty" in output
        assert "Patch file is empty." in output
        assert "yes" in output
        assert "0 bytes" in output
        assert ".aidc/agent_patch.diff" in output.replace("\\", "/")


def test_patch_command_ready_returns_zero_and_prints_ready():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        content = "diff --git a/main.py b/main.py\n+print('hello')\n"
        patch_path = _create_patch_file(root, content)

        with change_directory(root):
            exit_code, output = capture_output(write_patch_command, ".")

        assert exit_code == 0
        assert "Patch inspect" in output
        assert "ready" in output
        assert "Patch file is ready for review." in output
        assert "yes" in output
        assert f"{patch_path.stat().st_size} bytes" in output
        assert ".aidc/agent_patch.diff" in output.replace("\\", "/")
        assert content.strip() not in output
        assert "diff --git" not in output


def test_patch_command_optional_root_argument_works():
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        repo_root = temp_root / "repo"
        repo_root.mkdir()
        patch_path = _create_patch_file(repo_root, "diff --git a/a.py b/a.py\n")

        with change_directory(temp_root):
            exit_code, output = capture_output(write_patch_command, str(repo_root))

        assert exit_code == 0
        assert "Patch inspect" in output
        assert "ready" in output
        assert f"{patch_path.stat().st_size} bytes" in output
        assert ".aidc/agent_patch.diff" in output.replace("\\", "/")


TESTS = [
    test_new_patch_command_import_matches_legacy_shim,
    test_patch_command_missing_returns_nonzero_and_does_not_create_aidc,
    test_patch_command_empty_returns_nonzero_and_prints_empty,
    test_patch_command_ready_returns_zero_and_prints_ready,
    test_patch_command_optional_root_argument_works,
]
