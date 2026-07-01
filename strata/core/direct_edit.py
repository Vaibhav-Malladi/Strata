from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

from strata.utils.shell import run_argv
from strata.utils.artifacts import write_artifact_text

DIRECT_EDIT_REPORT_PATH = Path(".aidc") / "direct_edit.diff"

_IGNORED_DIRECTORY_NAMES = {
    ".git",
    ".aidc",
    ".cache",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "htmlcov",
    "node_modules",
    "venv",
}

_MAX_SNAPSHOT_FILE_BYTES = 2_000_000


def snapshot_working_files(root: str | Path) -> dict[str, str]:
    root_path = Path(root)
    if not root_path.exists():
        return {}

    snapshot: dict[str, str] = {}

    for file_path in _iter_snapshot_files(root_path):
        try:
            data = file_path.read_bytes()
        except OSError:
            continue

        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            continue

        relative_path = file_path.relative_to(root_path).as_posix()
        snapshot[relative_path] = hashlib.sha256(data).hexdigest()

    return snapshot


def detect_direct_edits(before: dict[str, str], root: str | Path) -> list[str]:
    after = snapshot_working_files(root)
    changed_paths = set(before) ^ set(after)
    changed_paths.update(path for path, digest in after.items() if before.get(path) != digest)
    return sorted(changed_paths)


def write_direct_edit_diff(root: str | Path, changed_paths: list[str]) -> Path:
    root_path = Path(root)
    report_path = root_path / DIRECT_EDIT_REPORT_PATH
    report_path.parent.mkdir(parents=True, exist_ok=True)

    diff_text = _git_diff_text(root_path, changed_paths)
    if diff_text is None:
        write_artifact_text(root_path, "direct_edit.diff", _build_text_report(changed_paths))
        return report_path

    write_artifact_text(root_path, "direct_edit.diff", diff_text)
    return report_path


def _iter_snapshot_files(root_path: Path):
    for current_root, dirnames, filenames in _walk_snapshot_tree(root_path):
        for filename in filenames:
            file_path = Path(current_root) / filename
            if not file_path.is_file() or file_path.is_symlink():
                continue

            try:
                size = file_path.stat().st_size
            except OSError:
                continue

            if size > _MAX_SNAPSHOT_FILE_BYTES:
                continue

            yield file_path


def _walk_snapshot_tree(root_path: Path):
    for current_root, dirnames, filenames in os.walk(root_path):
        dirnames[:] = [
            dirname
            for dirname in sorted(dirnames)
            if not _should_ignore_directory(dirname)
        ]
        filenames.sort()
        yield current_root, dirnames, filenames


def _should_ignore_directory(name: str) -> bool:
    normalized = name.strip()
    if not normalized:
        return True

    if normalized in _IGNORED_DIRECTORY_NAMES:
        return True

    return normalized.endswith(".egg-info") or normalized.endswith(".dist-info")


def _git_diff_text(root_path: Path, changed_paths: list[str]) -> str | None:
    if not changed_paths or shutil.which("git") is None:
        return None

    status_result = _run_git_command(root_path, ["status", "--porcelain", "--", *changed_paths])
    if status_result is None or status_result.returncode != 0:
        return None

    if any(line.startswith("?? ") for line in status_result.stdout.splitlines()):
        return None

    diff_result = _run_git_command(
        root_path,
        ["diff", "--no-ext-diff", "--no-color", "--", *changed_paths],
    )
    if diff_result is None or diff_result.returncode not in {0, 1}:
        return None

    diff_text = diff_result.stdout or ""
    if not diff_text.strip():
        return None

    return diff_text


def _run_git_command(root_path: Path, args: list[str]) -> subprocess.CompletedProcess[str] | None:
    try:
        return run_argv(
            ["git", *args],
            cwd=str(root_path),
        )
    except (OSError, ValueError):
        return None


def _build_text_report(changed_paths: list[str]) -> str:
    lines = [
        "Direct edit detected.",
        "The AI adapter changed files directly instead of creating `.aidc/agent_patch.diff`.",
        f"Strata wrote a diff report to `{DIRECT_EDIT_REPORT_PATH.as_posix()}`.",
        "",
        "Changed files:",
    ]

    if changed_paths:
        lines.extend(f"- {path}" for path in sorted(dict.fromkeys(changed_paths)))
    else:
        lines.append("- (none reported)")

    return "\n".join(lines) + "\n"
