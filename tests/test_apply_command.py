import contextlib
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import commands.apply_command as old_apply_command
import strata.commands.apply_command as new_apply_command
from cli import main as cli_main
from tests.helpers import capture_output, change_directory


def test_new_apply_command_import_matches_legacy_shim():
    assert new_apply_command.write_apply_command is old_apply_command.write_apply_command
    assert new_apply_command.write_apply_dry_run_command is old_apply_command.write_apply_dry_run_command


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


def _run_git(root: Path, *args: str) -> None:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert result.returncode == 0, result.stderr


def _initialize_git_repo(root: Path, tracked_paths: list[str]) -> None:
    _run_git(root, "init", "--quiet")
    _run_git(root, "config", "user.name", "Strata Tests")
    _run_git(root, "config", "user.email", "strata-tests@example.invalid")
    for tracked_path in tracked_paths:
        _run_git(root, "add", "--", tracked_path)
    _run_git(root, "commit", "--quiet", "-m", "test setup")


def _valid_main_patch() -> str:
    return (
        "diff --git a/main.py b/main.py\n"
        "--- a/main.py\n"
        "+++ b/main.py\n"
        "@@ -1 +1 @@\n"
        '-print("old")\n'
        '+print("new")\n'
    )


def test_apply_dry_run_missing_returns_nonzero_and_prints_missing():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        exit_code, output = _run_apply_cli(root, "--dry-run")

        assert exit_code == 1
        assert "Apply dry-run" in output
        assert "missing" in output
        assert "Validation" in output
        assert re.search(r"Validation\s+.*missing", output)
        assert len(re.findall(r"^Status\s+", output, re.MULTILINE)) == 1
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


def test_apply_dry_run_rejects_paths_outside_repository():
    unsafe_paths = [
        "../../outside.txt",
        "..\\..\\outside.txt",
        "/absolute/path.txt",
        "C:\\Users\\someone\\outside.txt",
    ]

    for unsafe_path in unsafe_paths:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            root = temp_root / "level1" / "repo"
            root.mkdir(parents=True)
            outside_path = temp_root / "outside.txt"
            patch = (
                f"diff --git {unsafe_path} {unsafe_path}\n"
                f"--- {unsafe_path}\n"
                f"+++ {unsafe_path}\n"
                "@@ -0,0 +1 @@\n"
                "+unsafe\n"
            )
            _create_patch_file(root, patch)

            exit_code, output = _run_apply_cli(root, "--dry-run")

            assert exit_code == 1
            assert "Unsafe patch path" in output
            assert "must stay inside the repository" in output
            assert re.search(r"Applies patch\s+no", output)
            assert not outside_path.exists()


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

        exit_code, output = _run_apply_cli(root, "--yes")

        assert exit_code == 0
        assert "Apply patch" in output
        assert "Apply complete" in output
        assert re.search(r"Status\s+.*applied", output)
        assert re.search(r"Validation\s+.*valid", output)
        assert re.search(r"Targets\s+main.py", output)
        assert re.search(r"Changed files\s+main.py", output)
        assert re.search(r"Applies patch\s+yes", output)
        assert "Patch applied successfully." in output
        assert "Strata did not commit or push anything." in output
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


def test_apply_blocks_dirty_git_working_tree_even_with_yes():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_file(root, ".gitignore", ".aidc/\n")
        _write_file(root, "main.py", 'print("old")\n')
        _write_file(root, "notes.txt", "clean\n")
        _initialize_git_repo(root, [".gitignore", "main.py", "notes.txt"])
        _write_file(root, "notes.txt", "dirty\n")
        _create_patch_file(root, _valid_main_patch())

        exit_code, output = _run_apply_cli(root, "--yes")

        assert exit_code == 1
        assert "uncommitted changes" in output
        assert "Commit, stash, or revert" in output
        assert "Patch not applied" in output
        assert (root / "main.py").read_text(encoding="utf-8") == 'print("old")\n'


def test_apply_dry_run_warns_for_dirty_tree_without_writing():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_file(root, ".gitignore", ".aidc/\n")
        _write_file(root, "main.py", 'print("old")\n')
        _write_file(root, "notes.txt", "clean\n")
        _initialize_git_repo(root, [".gitignore", "main.py", "notes.txt"])
        _write_file(root, "notes.txt", "dirty\n")
        _create_patch_file(root, _valid_main_patch())

        exit_code, output = _run_apply_cli(root, "--dry-run")

        assert exit_code == 0
        assert "uncommitted changes" in output
        assert re.search(r"Applies patch\s+no", output)
        assert (root / "main.py").read_text(encoding="utf-8") == 'print("old")\n'


def test_apply_dry_run_warns_when_context_is_newer_than_patch():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_file(root, "main.py", 'print("old")\n')
        patch_path = _create_patch_file(root, _valid_main_patch())
        markdown_context_path = _write_file(
            root, ".aidc/context_pack.md", "new context\n"
        )
        json_context_path = _write_file(
            root, ".aidc/context_pack.json", '{"task": "new context"}\n'
        )
        os.utime(patch_path, ns=(1_000_000_000, 1_000_000_000))
        os.utime(markdown_context_path, ns=(2_000_000_000, 2_000_000_000))
        os.utime(json_context_path, ns=(3_000_000_000, 3_000_000_000))

        exit_code, output = _run_apply_cli(root, "--dry-run")

        assert exit_code == 0
        assert "Patch may be stale" in output
        assert "older than generated context or source files" in output
        assert ".aidc/context_pack.md" in output.replace("\\", "/")
        assert ".aidc/context_pack.json" in output.replace("\\", "/")


def test_apply_dry_run_warns_when_target_file_is_newer_than_patch():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        target_path = _write_file(root, "main.py", 'print("old")\n')
        patch_path = _create_patch_file(root, _valid_main_patch())
        os.utime(patch_path, ns=(1_000_000_000, 1_000_000_000))
        os.utime(target_path, ns=(2_000_000_000, 2_000_000_000))

        exit_code, output = _run_apply_cli(root, "--dry-run")

        assert exit_code == 0
        assert "Patch may be stale" in output
        assert "main.py" in output


def test_apply_dry_run_warns_when_aidc_is_tracked_by_git():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_file(root, "main.py", 'print("old")\n')
        _write_file(root, ".aidc/tracked.txt", "tracked generated output\n")
        _create_patch_file(root, _valid_main_patch())
        _initialize_git_repo(
            root,
            ["main.py", ".aidc/tracked.txt", ".aidc/agent_patch.diff"],
        )

        exit_code, output = _run_apply_cli(root, "--dry-run")

        assert exit_code == 0
        assert "tracking files under `.aidc/`" in output
        assert "Add `.aidc/` to `.gitignore`" in output
        assert "uncommitted changes" not in output
        assert (root / "main.py").read_text(encoding="utf-8") == 'print("old")\n'


def test_apply_unknown_flag_returns_nonzero_and_shows_usage():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        exit_code, output = _run_apply_cli(root, "--bogus")

        assert exit_code == 1
        assert "Usage:" in output
        assert "strata apply --dry-run" in output


TESTS = [
    test_new_apply_command_import_matches_legacy_shim,
    test_apply_dry_run_missing_returns_nonzero_and_prints_missing,
    test_apply_dry_run_empty_returns_nonzero_and_prints_empty,
    test_apply_dry_run_ready_returns_zero_and_prints_ready,
    test_apply_dry_run_ready_invalid_returns_nonzero_and_prints_validation_invalid,
    test_apply_dry_run_rejects_paths_outside_repository,
    test_apply_dry_run_invalid_patch_prints_errors,
    test_apply_dry_run_optional_root_argument_works,
    test_apply_dry_run_missing_does_not_create_aidc,
    test_apply_returns_zero_and_prints_changed_files_for_valid_patch,
    test_apply_dry_run_real_patch_still_does_not_modify_files,
    test_apply_blocks_dirty_git_working_tree_even_with_yes,
    test_apply_dry_run_warns_for_dirty_tree_without_writing,
    test_apply_dry_run_warns_when_context_is_newer_than_patch,
    test_apply_dry_run_warns_when_target_file_is_newer_than_patch,
    test_apply_dry_run_warns_when_aidc_is_tracked_by_git,
    test_apply_unknown_flag_returns_nonzero_and_shows_usage,
]
