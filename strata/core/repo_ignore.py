from __future__ import annotations

from pathlib import Path


IGNORED_DIRECTORY_NAMES = {
    ".aidc",
    ".cache",
    ".git",
    ".mypy_cache",
    ".nox",
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

IGNORED_FILE_NAMES = {
    ".coverage",
    "coverage.xml",
}


def should_ignore_directory(name: str) -> bool:
    normalized = name.strip().lower()

    if not normalized:
        return True

    return normalized in IGNORED_DIRECTORY_NAMES or normalized.endswith(".egg-info")


def should_ignore_file(path: str | Path) -> bool:
    path_obj = Path(path)
    file_name = path_obj.name.strip().lower()

    if not file_name:
        return True

    if file_name in IGNORED_FILE_NAMES:
        return True

    return file_name.startswith(".coverage")


def should_ignore_path(path: str | Path) -> bool:
    path_obj = Path(path)

    return any(should_ignore_directory(part) for part in path_obj.parts[:-1]) or should_ignore_file(path_obj)
