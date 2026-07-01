import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path


_LANGUAGE_BY_EXTENSION = {
    ".c": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cs": "csharp",
    ".css": "css",
    ".go": "go",
    ".h": "c",
    ".hpp": "cpp",
    ".html": "html",
    ".java": "java",
    ".js": "javascript",
    ".json": "json",
    ".jsx": "javascript",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".less": "less",
    ".md": "markdown",
    ".mjs": "javascript",
    ".php": "php",
    ".ps1": "powershell",
    ".py": "python",
    ".rb": "ruby",
    ".rs": "rust",
    ".sass": "sass",
    ".scss": "scss",
    ".sh": "shell",
    ".sql": "sql",
    ".swift": "swift",
    ".toml": "toml",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".vue": "vue",
    ".xml": "xml",
    ".yaml": "yaml",
    ".yml": "yaml",
}

_LANGUAGE_BY_FILENAME = {
    "dockerfile": "dockerfile",
    "gemfile": "ruby",
    "makefile": "makefile",
    "rakefile": "ruby",
}

_TEST_FOLDER_NAMES = {
    "__tests__",
    "spec",
    "specs",
    "test",
    "tests",
}

_GENERATED_FOLDER_NAMES = {
    ".aidc",
    ".next",
    ".nuxt",
    "build",
    "coverage",
    "dist",
    "generated",
    "htmlcov",
    "out",
    "target",
}

_VENDOR_FOLDER_NAMES = {
    "node_modules",
    "third_party",
    "third-party",
    "vendor",
}

_LOCKFILE_NAMES = {
    "cargo.lock",
    "composer.lock",
    "gemfile.lock",
    "package-lock.json",
    "pnpm-lock.yaml",
    "poetry.lock",
    "uv.lock",
    "yarn.lock",
}

_NOISY_DIRECTORY_NAMES = {
    ".angular",
    ".git",
    ".hg",
    ".mypy_cache",
    ".next",
    ".pytest_cache",
    ".ruff_cache",
    ".svn",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "target",
    "venv",
}


@dataclass(frozen=True, slots=True)
class InventoryRecord:
    path: str
    extension: str
    size: int
    mtime: float
    is_test: bool
    is_generated_guess: bool
    folder_role: str
    language_guess: str | None


def guess_language(path: str | Path) -> str | None:
    """Guess a file's language from its name or extension only."""

    filename = _path_parts(path)[-1].lower()
    named_language = _LANGUAGE_BY_FILENAME.get(filename)
    if named_language is not None:
        return named_language
    return _LANGUAGE_BY_EXTENSION.get(Path(filename).suffix.lower())


def is_test_path(path: str | Path) -> bool:
    """Return whether common test path or filename conventions match."""

    parts = _path_parts(path)
    filename = parts[-1].lower()
    stem = Path(filename).stem
    return (
        any(part.lower() in _TEST_FOLDER_NAMES for part in parts[:-1])
        or stem.startswith("test_")
        or stem.endswith("_test")
        or stem.endswith(".test")
        or stem.endswith(".spec")
    )


def is_generated_path(path: str | Path) -> bool:
    """Conservatively guess whether a path is generated or vendored."""

    parts = _path_parts(path)
    folder_names = {part.lower() for part in parts[:-1]}
    filename = parts[-1].lower()
    stem = Path(filename).stem
    return (
        bool(folder_names & (_GENERATED_FOLDER_NAMES | _VENDOR_FOLDER_NAMES))
        or filename in _LOCKFILE_NAMES
        or ".min." in filename
        or ".generated." in filename
        or stem.endswith("_generated")
        or stem.endswith("_pb2")
        or stem.endswith(".designer")
        or stem.endswith(".g")
    )


def guess_folder_role(path: str | Path) -> str:
    """Return a coarse role inferred from folder names only."""

    parts = _path_parts(path)
    folders = {part.lower() for part in parts[:-1]}

    if folders & _VENDOR_FOLDER_NAMES:
        return "vendor"
    if folders & _GENERATED_FOLDER_NAMES:
        return "generated"
    if folders & _TEST_FOLDER_NAMES:
        return "test"
    if folders & {"docs", "doc", "documentation"}:
        return "docs"
    if folders & {"config", "configs", ".config"}:
        return "config"
    if folders & {"scripts", "script", "tools", "bin"}:
        return "scripts"
    if folders & {"assets", "asset", "images", "img", "public", "static"}:
        return "assets"
    if folders & {"src", "source", "sources", "lib", "app"}:
        return "source"
    if len(parts) == 1:
        return "root"
    return "other"


def create_inventory_record(root: str | Path, file_path: str | Path) -> InventoryRecord:
    """Build an inventory record using one filesystem stat and no file reads."""

    root_path = Path(root)
    target_path = _target_path(root_path, Path(file_path))
    metadata = target_path.stat()
    relative_path = os.path.relpath(target_path, root_path)

    return InventoryRecord(
        path=relative_path,
        extension=target_path.suffix.lower(),
        size=metadata.st_size,
        mtime=metadata.st_mtime,
        is_test=is_test_path(relative_path),
        is_generated_guess=is_generated_path(relative_path),
        folder_role=guess_folder_role(relative_path),
        language_guess=guess_language(relative_path),
    )


def iter_inventory_records(
    root: str | Path,
    *,
    max_files: int | None = None,
    include_hidden: bool = False,
) -> Iterator[InventoryRecord]:
    """Iterate repository files using directory entries and stat metadata only."""

    root_path = Path(root)
    _validate_inventory_root(root_path)
    _validate_max_files(max_files)
    return _iter_inventory_records(
        root_path,
        max_files=max_files,
        include_hidden=include_hidden,
    )


def collect_inventory(
    root: str | Path,
    *,
    max_files: int | None = None,
    include_hidden: bool = False,
) -> list[InventoryRecord]:
    """Collect a deterministic repository inventory without reading contents."""

    return list(
        iter_inventory_records(
            root,
            max_files=max_files,
            include_hidden=include_hidden,
        )
    )


def _iter_inventory_records(
    root_path: Path,
    *,
    max_files: int | None,
    include_hidden: bool,
) -> Iterator[InventoryRecord]:
    collected = 0
    for current_root, directory_names, file_names in os.walk(
        root_path,
        onerror=lambda _error: None,
    ):
        directory_names[:] = [
            name
            for name in sorted(directory_names)
            if not _skip_inventory_directory(name, include_hidden=include_hidden)
            and not (Path(current_root) / name).is_symlink()
        ]

        for file_name in sorted(file_names):
            if not include_hidden and file_name.startswith("."):
                continue

            file_path = Path(current_root) / file_name
            if file_path.is_symlink():
                continue
            try:
                record = create_inventory_record(root_path, file_path)
            except OSError:
                continue

            yield record
            collected += 1
            if max_files is not None and collected >= max_files:
                return


def _skip_inventory_directory(name: str, *, include_hidden: bool) -> bool:
    normalized = name.lower()
    return normalized in _NOISY_DIRECTORY_NAMES or (
        not include_hidden and name.startswith(".")
    )


def _validate_inventory_root(root_path: Path) -> None:
    if not root_path.exists():
        raise FileNotFoundError(f"inventory root does not exist: {root_path}")
    if not root_path.is_dir():
        raise NotADirectoryError(f"inventory root is not a directory: {root_path}")


def _validate_max_files(max_files: int | None) -> None:
    if max_files is None:
        return
    if isinstance(max_files, bool) or not isinstance(max_files, int):
        raise TypeError("max_files must be an integer or None")
    if max_files <= 0:
        raise ValueError("max_files must be greater than zero")


def _path_parts(path: str | Path) -> tuple[str, ...]:
    normalized = str(path).replace("\\", "/")
    return tuple(part for part in normalized.split("/") if part and part != ".") or ("",)


def _target_path(root_path: Path, file_path: Path) -> Path:
    if file_path.is_absolute():
        return file_path

    root_absolute = Path(os.path.abspath(root_path))
    file_absolute = Path(os.path.abspath(file_path))
    try:
        file_absolute.relative_to(root_absolute)
    except ValueError:
        return root_path / file_path
    return file_path
