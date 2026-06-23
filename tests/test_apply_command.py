import contextlib
import re
import sys
import tempfile
from pathlib import Path

from cli import main as cli_main
from tests.helpers import capture_output, change_directory


def _create_patch_file(root: Path, content: str) -> Path:
    patch_path = root / ".aidc" / "agent_patch.diff"
    patch_path.parent.mkdir(parents=True, exist_ok=True)
    patch_path.write_text(content, encoding="utf-8")
    return patch_path


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


def test_apply_dry_run_missing_returns_nonzero_and_prints_missing():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        exit_code, output = _run_apply_cli(root, "--dry-run")

        assert exit_code == 1
        assert "Apply dry-run" in output
        assert "missing" in output
        assert "Patch file not found." in output
        assert "Applies patch" in output
        assert re.search(r"Applies patch\s+no", output)
        assert not (root / ".aidc").exists()


def test_apply_dry_run_empty_returns_nonzero_and_prints_empty():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_patch_file(root, "")

        exit_code, output = _run_apply_cli(root, "--dry-run")

        assert exit_code == 1
        assert "Apply dry-run" in output
        assert "empty" in output
        assert "Patch file is empty." in output
        assert re.search(r"Applies patch\s+no", output)


def test_apply_dry_run_ready_returns_zero_and_prints_ready():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        content = "diff --git a/main.py b/main.py\n+print('hello')\n"
        _create_patch_file(root, content)

        exit_code, output = _run_apply_cli(root, "--dry-run")

        assert exit_code == 0
        assert "Apply dry-run" in output
        assert "ready" in output
        assert "Patch file is ready for apply dry-run." in output
        assert re.search(r"Applies patch\s+no", output)
        assert content.strip() not in output
        assert "diff --git" not in output


def test_apply_dry_run_optional_root_argument_works():
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        repo_root = temp_root / "repo"
        repo_root.mkdir()
        _create_patch_file(repo_root, "diff --git a/a.py b/a.py\n")

        exit_code, output = _run_apply_cli(temp_root, "--dry-run", str(repo_root))

        assert exit_code == 0
        assert "Apply dry-run" in output
        assert "ready" in output
        assert re.search(r"Applies patch\s+no", output)


def test_apply_dry_run_missing_does_not_create_aidc():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        exit_code, output = _run_apply_cli(root, "--dry-run")

        assert exit_code == 1
        assert not (root / ".aidc").exists()
        assert "Patch file not found." in output


def test_apply_without_dry_run_returns_nonzero_and_says_not_implemented():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        exit_code, output = _run_apply_cli(root)

        assert exit_code == 1
        assert "Apply" in output
        assert "real apply is not implemented yet" in output


def test_apply_unknown_flag_returns_nonzero_and_shows_usage():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        exit_code, output = _run_apply_cli(root, "--bogus")

        assert exit_code == 1
        assert "Usage:" in output
        assert "strata apply --dry-run" in output


TESTS = [
    test_apply_dry_run_missing_returns_nonzero_and_prints_missing,
    test_apply_dry_run_empty_returns_nonzero_and_prints_empty,
    test_apply_dry_run_ready_returns_zero_and_prints_ready,
    test_apply_dry_run_optional_root_argument_works,
    test_apply_dry_run_missing_does_not_create_aidc,
    test_apply_without_dry_run_returns_nonzero_and_says_not_implemented,
    test_apply_unknown_flag_returns_nonzero_and_shows_usage,
]
