from __future__ import annotations

from pathlib import Path
from typing import Sequence

from context_matching import detect_file_roles
from repo_ignore import should_ignore_path


def normalize_selected_paths(root_path: str | Path, selected_paths: Sequence[str]) -> list[str]:
    """Validate and normalize user-selected file paths relative to the repo root."""

    root = Path(root_path).resolve()
    normalized: list[str] = []
    seen: set[str] = set()

    for raw_path in selected_paths:
        candidate = str(raw_path or "").strip()

        if not candidate:
            raise ValueError("Selected file path cannot be empty.")

        candidate_path = Path(candidate)
        absolute_candidate = candidate_path if candidate_path.is_absolute() else root / candidate_path

        try:
            resolved_candidate = absolute_candidate.resolve(strict=False)
        except OSError as error:
            raise ValueError(f"Could not resolve selected file: {candidate}") from error

        try:
            relative_path = resolved_candidate.relative_to(root)
        except ValueError as error:
            raise ValueError(f"Selected file is outside the repo root: {candidate}") from error

        if not resolved_candidate.exists():
            raise ValueError(f"Selected file does not exist: {relative_path.as_posix()}")

        if resolved_candidate.is_dir():
            raise ValueError(f"Selected path is a directory, not a file: {relative_path.as_posix()}")

        relative_text = relative_path.as_posix()

        if should_ignore_path(relative_text):
            raise ValueError(f"Selected file is ignored or generated: {relative_text}")

        if relative_text in seen:
            continue

        seen.add(relative_text)
        normalized.append(relative_text)

    return normalized


def build_selected_file_entries(graph: dict, selected_paths: Sequence[str]) -> list[dict]:
    """Build context ranking entries for user-selected files."""

    selected_paths = _dedupe_paths(selected_paths)
    if not selected_paths:
        return []

    file_index = _index_graph_files(graph)
    total_selected = len(selected_paths)
    entries: list[dict] = []

    for index, path in enumerate(selected_paths):
        file_info = file_index.get(path) or _make_synthetic_file(path)
        roles = detect_file_roles(file_info)

        entries.append(
            {
                "file": file_info,
                "score": 10_000 + (total_selected - index),
                "matched_terms": [],
                "confidence": "high",
                "is_test": "test" in roles,
                "included_by_hint_only": False,
                "selected_by_user": True,
                "selection_index": index,
                "reason": "user-selected file",
            }
        )

    return entries


def context_mode_label(selected_paths: Sequence[str] | None) -> str:
    """Return the short label used in ask/run summaries."""

    return "selected files" if selected_paths else "focused context"


def context_mode_description(selected_paths: Sequence[str] | None) -> str:
    """Return the short description used in warning copy."""

    return "selected-file context" if selected_paths else "focused context"


def format_selected_file_list(selected_paths: Sequence[str] | None) -> str:
    """Render selected files for compact UI output."""

    paths = _dedupe_paths(selected_paths or [])

    if not paths:
        return "-"

    return ", ".join(paths)


def build_selected_file_section(selected_paths: Sequence[str] | None) -> list[str]:
    """Render a markdown section listing selected file anchors."""

    paths = _dedupe_paths(selected_paths or [])
    if not paths:
        return []

    lines = ["## User-selected files", ""]
    lines.extend(f"- `{path}`" for path in paths)
    lines.append("")
    return lines


def _index_graph_files(graph: dict) -> dict[str, dict]:
    indexed: dict[str, dict] = {}

    for file_info in graph.get("files", []):
        if not isinstance(file_info, dict):
            continue

        path = str(file_info.get("path", "")).replace("\\", "/").strip()
        if path:
            indexed[path] = file_info

    return indexed


def _make_synthetic_file(path: str) -> dict:
    return {
        "path": path,
        "language": "unknown",
        "classes": [],
        "functions": [],
        "interfaces": [],
        "types": [],
        "enums": [],
        "exports": [],
        "imports": [],
        "external_imports": [],
        "unresolved_imports": [],
        "unresolved_import_details": [],
        "routes": [],
    }


def _dedupe_paths(selected_paths: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []

    for raw_path in selected_paths:
        path = str(raw_path or "").replace("\\", "/").strip()

        if not path or path in seen:
            continue

        seen.add(path)
        normalized.append(path)

    return normalized
