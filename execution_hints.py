from __future__ import annotations

from pathlib import Path

from context_matching import _normalize_path


EXECUTION_HINT_LIMIT = 8


def collect_execution_path_hints(
    graph: dict,
    relevant_entries: list[dict],
    *,
    react_hints: list[dict] | None = None,
    angular_hints: list[dict] | None = None,
) -> list[str]:
    """Describe compact, evidence-based paths into relevant code."""

    relevant_paths = [
        _normalize_path(str((entry.get("file") or {}).get("path", "")))
        for entry in relevant_entries
        if isinstance(entry, dict)
    ]
    selected_paths = {
        _normalize_path(str((entry.get("file") or {}).get("path", "")))
        for entry in relevant_entries
        if isinstance(entry, dict) and entry.get("selected_by_user")
    }
    hints: list[str] = []

    edges = sorted(
        (edge for edge in (graph or {}).get("edges", []) if isinstance(edge, dict)),
        key=lambda edge: (
            0
            if _normalize_path(str(edge.get("from", ""))) in selected_paths
            or _normalize_path(str(edge.get("to", ""))) in selected_paths
            else 1,
            0
            if _normalize_path(str(edge.get("from", ""))) in relevant_paths
            or _normalize_path(str(edge.get("to", ""))) in relevant_paths
            else 1,
            str(edge.get("from", "")),
            str(edge.get("to", "")),
        ),
    )
    relevant_set = set(relevant_paths)
    edge_hint_count = 0
    for edge in edges:
        source = _normalize_path(str(edge.get("from", "")))
        target = _normalize_path(str(edge.get("to", "")))
        if not source or not target or not ({source, target} & relevant_set):
            continue
        import_name = str(edge.get("import", "")).strip()
        suffix = f" via import `{import_name}`" if import_name else " via import"
        _append_unique(hints, f"`{source}` imports `{target}`{suffix}.")
        edge_hint_count += 1
        if edge_hint_count >= 4:
            break

    for entry in relevant_entries:
        file_info = entry.get("file") if isinstance(entry, dict) else None
        if not isinstance(file_info, dict):
            continue
        path = _normalize_path(str(file_info.get("path", "")))
        command_name = _command_name(path)
        if not command_name:
            continue
        functions = {
            _symbol_name(item)
            for item in file_info.get("functions", []) or []
        }
        handler = f"write_{command_name.replace('-', '_')}_command"
        if handler in functions:
            _append_unique(
                hints,
                f"`{path}::{handler}` is likely the command handler for `strata {command_name}` by convention.",
            )

    for hint in react_hints or []:
        path = str(hint.get("path", "")).strip()
        for test_path in hint.get("tests", []) or []:
            _append_unique(
                hints,
                f"`{path}` is likely covered by `{test_path}` by convention.",
            )
        for hook_path in hint.get("hooks", []) or []:
            _append_unique(
                hints,
                f"`{path}` likely uses nearby hook `{hook_path}` by convention.",
            )

    for hint in angular_hints or []:
        path = str(hint.get("path", "")).strip()
        template = str(hint.get("template", "")).strip()
        if template:
            _append_unique(
                hints,
                f"`{path}` uses template `{template}` by convention.",
            )
        for style_path in hint.get("styles", []) or []:
            _append_unique(
                hints,
                f"`{path}` uses style `{style_path}` by convention.",
            )
        for test_path in hint.get("tests", []) or []:
            _append_unique(
                hints,
                f"`{path}` is likely covered by `{test_path}` by convention.",
            )

    return hints[:EXECUTION_HINT_LIMIT]


def build_execution_path_hints_section(hints: list[str] | None) -> list[str]:
    hints = list(hints or [])
    if not hints:
        return []
    return ["## Execution Path Hints", "", *[f"- {hint}" for hint in hints], ""]


def _append_unique(hints: list[str], hint: str) -> None:
    if hint and hint not in hints and len(hints) < EXECUTION_HINT_LIMIT:
        hints.append(hint)


def _command_name(path: str) -> str:
    normalized = _normalize_path(path)
    if "/commands/" not in f"/{normalized}" or not normalized.endswith("_command.py"):
        return ""
    return Path(normalized).stem[: -len("_command")].replace("_", "-")


def _symbol_name(symbol: object) -> str:
    if isinstance(symbol, dict):
        return str(symbol.get("name", ""))
    return str(symbol)
