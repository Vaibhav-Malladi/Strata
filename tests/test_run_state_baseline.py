import shutil
import subprocess
import tempfile
from pathlib import Path

from strata.core.context_artifacts import (
    BASELINE_STATUS_ATTACHED,
    BASELINE_STATUS_AVAILABLE,
    BASELINE_STATUS_DETACHED,
    BASELINE_STATUS_MISSING,
    BASELINE_STATUS_NO_COMMITS,
    build_run_state_for_repo,
    capture_git_baseline,
    validate_stored_baseline,
)


def test_capture_git_baseline_records_normal_attached_head():
    if not _git_available():
        return

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _init_repo(root)
        expected_commit = _commit_file(root, "app.py", "print('hi')\n")

        baseline = capture_git_baseline(root)
        state = build_run_state_for_repo(root, task="change app")

        assert baseline["baseline_commit"] == expected_commit
        assert baseline["baseline_commit_attached"] is True
        assert baseline["baseline_status"] == BASELINE_STATUS_ATTACHED
        assert baseline["baseline_warning"] is None
        assert state["baseline_commit"] == expected_commit
        assert state["baseline_commit_attached"] is True
        assert state["baseline_status"] == BASELINE_STATUS_ATTACHED
        assert state["task"] == "change app"


def test_capture_git_baseline_handles_repo_with_no_commits():
    if not _git_available():
        return

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _init_repo(root)

        baseline = capture_git_baseline(root)

        assert baseline["baseline_commit"] is None
        assert baseline["baseline_commit_attached"] is True
        assert baseline["baseline_status"] == BASELINE_STATUS_NO_COMMITS
        assert "disabled until the repository has at least one commit" in baseline["baseline_warning"]


def test_capture_git_baseline_records_detached_head_warning():
    if not _git_available():
        return

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _init_repo(root)
        expected_commit = _commit_file(root, "app.py", "print('hi')\n")
        _git(root, "checkout", "--detach", "HEAD")

        baseline = capture_git_baseline(root)

        assert baseline["baseline_commit"] == expected_commit
        assert baseline["baseline_commit_attached"] is False
        assert baseline["baseline_status"] == BASELINE_STATUS_DETACHED
        assert "review can compare against the captured commit" in baseline["baseline_warning"]


def test_validate_stored_baseline_handles_available_and_missing_commits():
    if not _git_available():
        return

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _init_repo(root)
        commit = _commit_file(root, "app.py", "print('hi')\n")

        available = validate_stored_baseline(root, commit)
        missing = validate_stored_baseline(root, "f" * 40)

        assert available["baseline_commit"] == commit
        assert available["baseline_available"] is True
        assert available["baseline_status"] == BASELINE_STATUS_AVAILABLE
        assert available["baseline_warning"] is None
        assert missing["baseline_available"] is False
        assert missing["baseline_status"] == BASELINE_STATUS_MISSING
        assert "re-run context before review diff" in missing["baseline_warning"]


def test_validate_stored_baseline_without_commit_is_safe():
    if not _git_available():
        return

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _init_repo(root)

        result = validate_stored_baseline(root, None)

        assert result["baseline_commit"] is None
        assert result["baseline_available"] is False
        assert "No stored baseline commit" in result["baseline_warning"]


def _git_available() -> bool:
    return shutil.which("git") is not None


def _init_repo(root: Path) -> None:
    _git(root, "init")
    _git(root, "config", "user.name", "Strata Test")
    _git(root, "config", "user.email", "strata@example.test")


def _commit_file(root: Path, relative_path: str, content: str) -> str:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    _git(root, "add", relative_path)
    _git(root, "commit", "-m", "test commit")
    return _git(root, "rev-parse", "HEAD").stdout.strip()


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result


TESTS = [
    test_capture_git_baseline_records_normal_attached_head,
    test_capture_git_baseline_handles_repo_with_no_commits,
    test_capture_git_baseline_records_detached_head_warning,
    test_validate_stored_baseline_handles_available_and_missing_commits,
    test_validate_stored_baseline_without_commit_is_safe,
]
