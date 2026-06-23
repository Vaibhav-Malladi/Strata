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


def test_apply_dry_run_missing_returns_nonzero_and_prints_missing():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        exit_code, output = _run_apply_cli(root, "--dry-run")

        assert exit_code == 1
        assert "Apply dry-run" in output
        assert "missing" in output
        assert "Validation" in output
        assert re.search(r"Validation\s+.*missing", output)
        assert re.search(r"Targets\s+-", output)
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
        assert re.search(r"Validation\s+.*empty", output)
        assert re.search(r"Targets\s+-", output)
        assert "Patch file is empty." in output
        assert re.search(r"Applies patch\s+no", output)


def test_apply_dry_run_ready_returns_zero_and_prints_ready():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        content = (
            "diff --git a/main.py b/main.py\n"
            "--- a/main.py\n"
            "+++ b/main.py\n"
            "@@ -1 +1 @@\n"
            "-print('old')\n"
            "+print('hello')\n"
        )
        _create_patch_file(root, content)

        exit_code, output = _run_apply_cli(root, "--dry-run")

        assert exit_code == 0
        assert "Apply dry-run" in output
        assert "ready" in output
        assert re.search(r"Validation\s+.*valid", output)
        assert re.search(r"Targets\s+main.py", output)
        assert "Patch format looks safe for dry-run validation." in output
        assert re.search(r"Applies patch\s+no", output)
        assert content.strip() not in output
        assert "diff --git" not in output


def test_apply_dry_run_ready_invalid_returns_nonzero_and_prints_validation_invalid():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        content = (
            "diff --git a/.env b/.env\n"
            "--- a/.env\n"
            "+++ b/.env\n"
            "@@ -1 +1 @@\n"
            "-SECRET=old\n"
            "+SECRET=new\n"
        )
        _create_patch_file(root, content)

        exit_code, output = _run_apply_cli(root, "--dry-run")

        assert exit_code == 1
        assert "Apply dry-run" in output
        assert "invalid" in output
        assert re.search(r"Status\s+.*invalid", output)
        assert re.search(r"Validation\s+.*invalid", output)
        assert re.search(r"Targets\s+-", output)
        assert "Patch failed validation." in output
        assert "Errors" in output
        assert ".env" in output
        assert content.strip() not in output


def test_apply_dry_run_invalid_patch_prints_errors():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _create_patch_file(root, "this is not a diff\n")

        exit_code, output = _run_apply_cli(root, "--dry-run")

        assert exit_code == 1
        assert "Patch does not contain a unified diff header." in output
        assert "Errors" in output
        assert re.search(r"Validation\s+.*invalid", output)


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


def test_apply_returns_zero_and_prints_changed_files_for_valid_patch():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_file(root, "main.py", 'print("old")\n')
        _create_patch_file(
            root,
            (
                "diff --git a/main.py b/main.py\n"
                "--- a/main.py\n"
                "+++ b/main.py\n"
                "@@ -1 +1 @@\n"
                '-print("old")\n'
                '+print("new")\n'
            ),
        )

        exit_code, output = _run_apply_cli(root)

        assert exit_code == 0
        assert "Apply patch" in output
        assert re.search(r"Status\s+.*applied", output)
        assert re.search(r"Validation\s+.*valid", output)
        assert re.search(r"Targets\s+main.py", output)
        assert re.search(r"Changed files\s+main.py", output)
        assert re.search(r"Applies patch\s+yes", output)
        assert "Patch applied successfully." in output
        assert "diff --git" not in output
        assert 'print("old")' not in output
        assert 'print("new")' not in output
        assert (root / "main.py").read_text(encoding="utf-8") == 'print("new")\n'


def test_apply_dry_run_real_patch_still_does_not_modify_files():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_file(root, "main.py", 'print("old")\n')
        _create_patch_file(
            root,
            (
                "diff --git a/main.py b/main.py\n"
                "--- a/main.py\n"
                "+++ b/main.py\n"
                "@@ -1 +1 @@\n"
                '-print("old")\n'
                '+print("new")\n'
            ),
        )

        exit_code, output = _run_apply_cli(root, "--dry-run")

        assert exit_code == 0
        assert "Apply dry-run" in output
        assert re.search(r"Applies patch\s+no", output)
        assert (root / "main.py").read_text(encoding="utf-8") == 'print("old")\n'


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
    test_apply_dry_run_ready_invalid_returns_nonzero_and_prints_validation_invalid,
    test_apply_dry_run_invalid_patch_prints_errors,
    test_apply_dry_run_optional_root_argument_works,
    test_apply_dry_run_missing_does_not_create_aidc,
    test_apply_returns_zero_and_prints_changed_files_for_valid_patch,
    test_apply_dry_run_real_patch_still_does_not_modify_files,
    test_apply_unknown_flag_returns_nonzero_and_shows_usage,
]
