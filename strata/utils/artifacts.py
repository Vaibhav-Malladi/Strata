from __future__ import annotations

import json
import os
import re
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any


AIDC_DIRECTORY_NAME = ".aidc"
GENERATED_FILE_MODE = 0o600
_WINDOWS_ABSOLUTE_PATH = re.compile(r"^[A-Za-z]:[\\/]")


def resolve_artifact_path(root: str | Path, artifact_name: str | Path) -> Path:
    public_path, _resolved_path = _artifact_paths(root, artifact_name)
    return public_path


def _artifact_paths(root: str | Path, artifact_name: str | Path) -> tuple[Path, Path]:
    root_path = Path(root)
    resolved_root = root_path.resolve()
    raw_name = str(artifact_name)
    relative_path = Path(raw_name.replace("\\", "/"))

    if relative_path.is_absolute() or _WINDOWS_ABSOLUTE_PATH.match(raw_name) or raw_name.startswith("\\\\"):
        raise ValueError(f"Artifact path must be relative to .aidc: {artifact_name}")
    if not relative_path.parts or ".." in relative_path.parts:
        raise ValueError(f"Artifact path must not contain parent traversal: {artifact_name}")

    public_path = root_path / AIDC_DIRECTORY_NAME / relative_path
    aidc_path = resolved_root / AIDC_DIRECTORY_NAME
    if aidc_path.is_symlink():
        raise ValueError("Artifact directory must not be a symbolic link: .aidc")

    resolved_aidc = aidc_path.resolve(strict=False)
    candidate = aidc_path / relative_path
    if candidate.is_symlink():
        raise ValueError(f"Artifact target must not be a symbolic link: {artifact_name}")

    try:
        resolved_aidc.relative_to(resolved_root)
        resolved_candidate = candidate.resolve(strict=False)
        resolved_candidate.relative_to(resolved_aidc)
    except (OSError, RuntimeError, ValueError) as error:
        raise ValueError(f"Artifact path must stay inside repo/.aidc: {artifact_name}") from error

    return public_path, resolved_candidate


def write_artifact_text(root: str | Path, artifact_name: str | Path, content: str) -> Path:
    public_path, target_path = _artifact_paths(root, artifact_name)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    with NamedTemporaryFile(
        "w",
        encoding="utf-8",
        newline="",
        delete=False,
        dir=str(target_path.parent),
    ) as handle:
        handle.write(str(content))
        temp_path = Path(handle.name)

    try:
        _restrict_file_permissions(temp_path)
        os.replace(temp_path, target_path)
        _restrict_file_permissions(target_path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise

    return public_path


def write_artifact_json(root: str | Path, artifact_name: str | Path, payload: Any) -> Path:
    content = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    return write_artifact_text(root, artifact_name, content)


def write_artifact_output_path(output_path: str | Path, content: str) -> Path:
    path = Path(output_path)
    parts = path.parts
    try:
        aidc_index = len(parts) - 1 - tuple(reversed(parts)).index(AIDC_DIRECTORY_NAME)
    except ValueError as error:
        raise ValueError(f"Generated artifact path must be under .aidc: {output_path}") from error

    root_parts = parts[:aidc_index]
    artifact_parts = parts[aidc_index + 1 :]
    root = Path(*root_parts) if root_parts else Path(".")
    return write_artifact_text(root, Path(*artifact_parts), content)


def _restrict_file_permissions(path: Path) -> None:
    try:
        path.chmod(GENERATED_FILE_MODE)
    except OSError:
        pass
