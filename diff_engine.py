from __future__ import annotations

import json
import os
from pathlib import Path

from secret_redaction import redact_text


_SYMBOL_CATEGORIES = (
    "classes",
    "functions",
    "interfaces",
    "types",
    "enums",
    "exports",
)


def normalize_file_map(graph: dict) -> dict:
    """Return a path-keyed mapping of file metadata."""

    file_map = {}

    if not isinstance(graph, dict):
        return file_map

    files = graph.get("files", [])

    if not isinstance(files, list):
        return file_map

    for file_info in files:
        if not isinstance(file_info, dict):
            continue

        path = _normalize_path_value(file_info.get("path", ""))

        if not path:
            continue

        file_map[path] = file_info

    return file_map


def normalize_edges(graph: dict) -> set[tuple[str, str, str]]:
    """Return a deterministic set of normalized edge signatures."""

    edges = set()

    if not isinstance(graph, dict):
        return edges

    for edge in _iter_edges(graph.get("edges", [])):
        edges.add(_edge_signature(edge))

    return edges


def extract_unresolved_imports(graph: dict) -> dict:
    """Return unresolved imports keyed by file path."""

    unresolved = {}

    if not isinstance(graph, dict):
        return unresolved

    files = graph.get("files", [])

    if not isinstance(files, list):
        return unresolved

    for file_info in files:
        if not isinstance(file_info, dict):
            continue

        path = _normalize_path_value(file_info.get("path", ""))

        if not path:
            continue

        values = set()

        for item in _as_iterable(file_info.get("unresolved_imports")):
            value = _stringify_import_value(item)

            if value:
                values.add(value)

        for detail in _as_iterable(file_info.get("unresolved_import_details")):
            if isinstance(detail, dict):
                value = _stringify_import_value(detail.get("name"))

                if value:
                    values.add(value)

        if values:
            unresolved[path] = sorted(values)

    return dict(sorted(unresolved.items()))


def normalize_routes(routes_data: dict | list | None) -> set[tuple[str, str, str]]:
    """Return a deterministic set of normalized route signatures."""

    routes = set()

    for route in _iter_route_records(routes_data):
        method = str(route.get("method", "")).upper()
        route_path = str(route.get("path", ""))
        location = _normalize_path_value(route.get("file", "")) or str(
            route.get("source") or ""
        )
        routes.add((method, route_path, location))

    return routes


def extract_symbol_surface(file_info: dict) -> dict:
    """Return a normalized symbol surface for a file."""

    surface = {}

    if not isinstance(file_info, dict):
        return {category: [] for category in _SYMBOL_CATEGORIES}

    for category in _SYMBOL_CATEGORIES:
        values = set()

        for item in _as_iterable(file_info.get(category)):
            for name in _extract_symbol_names(item):
                if name:
                    values.add(name)

        surface[category] = sorted(values)

    return surface


def compare_graphs(
    old_graph: dict,
    new_graph: dict,
    old_routes_data: dict | list | None = None,
    new_routes_data: dict | list | None = None,
) -> dict:
    """Compare two repository intelligence states and return a structured diff."""

    old_files = normalize_file_map(old_graph)
    new_files = normalize_file_map(new_graph)

    old_file_paths = set(old_files)
    new_file_paths = set(new_files)
    files_added = sorted(new_file_paths - old_file_paths)
    files_removed = sorted(old_file_paths - new_file_paths)
    files_kept = sorted(old_file_paths & new_file_paths)

    old_edges = normalize_edges(old_graph)
    new_edges = normalize_edges(new_graph)

    old_routes = normalize_routes(old_routes_data)
    new_routes = normalize_routes(new_routes_data)

    old_unresolved = extract_unresolved_imports(old_graph)
    new_unresolved = extract_unresolved_imports(new_graph)

    unresolved_added, unresolved_removed = _compare_unresolved_imports(
        old_unresolved,
        new_unresolved,
    )

    symbol_added, symbol_removed = _compare_symbol_surfaces(
        old_files,
        new_files,
        files_kept,
        files_added,
        files_removed,
    )

    diff = {
        "files_added": files_added,
        "files_removed": files_removed,
        "files_kept": files_kept,
        "edges_added": sorted(new_edges - old_edges),
        "edges_removed": sorted(old_edges - new_edges),
        "routes_added": sorted(new_routes - old_routes),
        "routes_removed": sorted(old_routes - new_routes),
        "unresolved_imports_added": unresolved_added,
        "unresolved_imports_removed": unresolved_removed,
        "symbols_added": symbol_added,
        "symbols_removed": symbol_removed,
    }

    diff["summary"] = {
        "files_added": len(diff["files_added"]),
        "files_removed": len(diff["files_removed"]),
        "edges_added": len(diff["edges_added"]),
        "edges_removed": len(diff["edges_removed"]),
        "routes_added": len(diff["routes_added"]),
        "routes_removed": len(diff["routes_removed"]),
        "unresolved_imports_added": _count_unresolved_entries(
            diff["unresolved_imports_added"]
        ),
        "unresolved_imports_removed": _count_unresolved_entries(
            diff["unresolved_imports_removed"]
        ),
        "symbols_added": _count_symbol_entries(diff["symbols_added"]),
        "symbols_removed": _count_symbol_entries(diff["symbols_removed"]),
    }

    return diff


def build_diff_markdown(diff: dict) -> str:
    """Build a compact Markdown structural diff report."""

    summary = diff.get("summary", {}) if isinstance(diff, dict) else {}

    lines = [
        "# Strata Structural Diff",
        "",
        "## Summary",
        "",
        f"- Files added: `{summary.get('files_added', 0)}`",
        f"- Files removed: `{summary.get('files_removed', 0)}`",
        f"- Dependency edges added: `{summary.get('edges_added', 0)}`",
        f"- Dependency edges removed: `{summary.get('edges_removed', 0)}`",
        f"- Backend routes added: `{summary.get('routes_added', 0)}`",
        f"- Backend routes removed: `{summary.get('routes_removed', 0)}`",
        f"- Unresolved imports added: `{summary.get('unresolved_imports_added', 0)}`",
        f"- Unresolved imports removed: `{summary.get('unresolved_imports_removed', 0)}`",
        f"- Symbols added: `{summary.get('symbols_added', 0)}`",
        f"- Symbols removed: `{summary.get('symbols_removed', 0)}`",
        "",
        "## Files Added",
        "",
        _render_none_or_lines(diff.get("files_added", [])),
        "",
        "## Files Removed",
        "",
        _render_none_or_lines(diff.get("files_removed", [])),
        "",
        "## Dependency Edges Added",
        "",
        _render_none_or_lines(
            _format_edge_signature(edge)
            for edge in diff.get("edges_added", [])
        ),
        "",
        "## Dependency Edges Removed",
        "",
        _render_none_or_lines(
            _format_edge_signature(edge)
            for edge in diff.get("edges_removed", [])
        ),
        "",
        "## Backend Routes Added",
        "",
        _render_none_or_lines(
            _format_route_signature(route)
            for route in diff.get("routes_added", [])
        ),
        "",
        "## Backend Routes Removed",
        "",
        _render_none_or_lines(
            _format_route_signature(route)
            for route in diff.get("routes_removed", [])
        ),
        "",
        "## Unresolved Imports Added",
        "",
        _render_none_or_lines(
            _format_unresolved_entry(entry)
            for entry in diff.get("unresolved_imports_added", [])
        ),
        "",
        "## Unresolved Imports Removed",
        "",
        _render_none_or_lines(
            _format_unresolved_entry(entry)
            for entry in diff.get("unresolved_imports_removed", [])
        ),
        "",
        "## Symbols Added",
        "",
        _render_none_or_lines(
            _format_symbol_entry(entry)
            for entry in diff.get("symbols_added", [])
        ),
        "",
        "## Symbols Removed",
        "",
        _render_none_or_lines(
            _format_symbol_entry(entry)
            for entry in diff.get("symbols_removed", [])
        ),
    ]

    return redact_text("\n".join(lines))


def write_diff_report(root: str | Path, diff: dict) -> dict:
    """Write diff JSON and Markdown reports under .aidc."""

    root_path = Path(root)
    output_dir = root_path / ".aidc"
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / "diff_report.json"
    markdown_path = output_dir / "diff_report.md"

    json_path.write_text(
        redact_text(json.dumps(diff, indent=2, sort_keys=True)),
        encoding="utf-8",
    )
    markdown_path.write_text(redact_text(build_diff_markdown(diff)), encoding="utf-8")

    return {
        "root": str(root_path),
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
    }


def _iter_edges(edges: object) -> list[dict]:
    if not isinstance(edges, list):
        return []

    results = []

    for edge in edges:
        if isinstance(edge, dict):
            results.append(edge)

    return results


def _edge_signature(edge: dict) -> tuple[str, str, str]:
    from_path = _normalize_path_value(edge.get("from", ""))
    to_path = _normalize_path_value(edge.get("to", ""))
    label = str(edge.get("import") or edge.get("type") or "")
    return from_path, to_path, label


def _as_iterable(value: object) -> list:
    if value is None:
        return []

    if isinstance(value, list):
        return value

    if isinstance(value, tuple):
        return list(value)

    if isinstance(value, set):
        return list(value)

    return [value]


def _stringify_import_value(value: object) -> str:
    if isinstance(value, dict):
        name = value.get("name")

        if name is not None:
            return str(name)

        return ""

    if value is None:
        return ""

    return str(value)


def _normalize_path_value(value: object) -> str:
    if value is None:
        return ""

    text = str(value).strip()

    if not text:
        return ""

    return os.path.normpath(text)


def _iter_route_records(routes_data: dict | list | None) -> list[dict]:
    records = []

    if routes_data is None:
        return records

    if isinstance(routes_data, list):
        for item in routes_data:
            if isinstance(item, dict):
                records.append(item)
        return records

    if isinstance(routes_data, dict):
        routes = routes_data.get("routes")

        if isinstance(routes, list):
            for item in routes:
                if isinstance(item, dict):
                    records.append(item)
            return records

        if _looks_like_route(routes_data):
            return [routes_data]

    return records


def _looks_like_route(value: dict) -> bool:
    return isinstance(value, dict) and "method" in value and "path" in value


def _extract_symbol_names(value: object) -> list[str]:
    names = []

    if isinstance(value, dict):
        if "name" in value and value["name"] is not None:
            names.append(str(value["name"]))
            return names

        for nested in value.values():
            names.extend(_extract_symbol_names(nested))
        return names

    if isinstance(value, str):
        if value:
            names.append(value)
        return names

    if isinstance(value, (int, float, bool)):
        names.append(str(value))
        return names

    if isinstance(value, (list, tuple, set)):
        for item in value:
            names.extend(_extract_symbol_names(item))
        return names

    if value is not None:
        names.append(str(value))

    return names


def _compare_unresolved_imports(old: dict, new: dict) -> tuple[list[dict], list[dict]]:
    added = []
    removed = []

    for path in sorted(set(old) | set(new)):
        old_values = set(old.get(path, []))
        new_values = set(new.get(path, []))

        added_values = sorted(new_values - old_values)
        removed_values = sorted(old_values - new_values)

        if added_values:
            added.append({"path": path, "imports": added_values})

        if removed_values:
            removed.append({"path": path, "imports": removed_values})

    return added, removed


def _compare_symbol_surfaces(
    old_files: dict,
    new_files: dict,
    files_kept: list[str],
    files_added: list[str],
    files_removed: list[str],
) -> tuple[list[dict], list[dict]]:
    added = []
    removed = []

    for path in files_added:
        entry = _symbol_diff_entry(path, {}, extract_symbol_surface(new_files[path]), added=True)

        if entry:
            added.append(entry)

    for path in files_removed:
        entry = _symbol_diff_entry(path, extract_symbol_surface(old_files[path]), {}, removed=True)

        if entry:
            removed.append(entry)

    for path in files_kept:
        entry_added, entry_removed = _symbol_diff_entry_pair(
            path,
            extract_symbol_surface(old_files[path]),
            extract_symbol_surface(new_files[path]),
        )

        if entry_added:
            added.append(entry_added)

        if entry_removed:
            removed.append(entry_removed)

    return added, removed


def _symbol_diff_entry_pair(path: str, old_surface: dict, new_surface: dict) -> tuple[dict | None, dict | None]:
    added_categories = {}
    removed_categories = {}

    for category in _SYMBOL_CATEGORIES:
        old_values = set(old_surface.get(category, []))
        new_values = set(new_surface.get(category, []))

        added_values = sorted(new_values - old_values)
        removed_values = sorted(old_values - new_values)

        if added_values:
            added_categories[category] = added_values

        if removed_values:
            removed_categories[category] = removed_values

    return (
        {"path": path, "categories": added_categories} if added_categories else None,
        {"path": path, "categories": removed_categories} if removed_categories else None,
    )


def _symbol_diff_entry(path: str, old_surface: dict, new_surface: dict, *, added: bool = False, removed: bool = False) -> dict | None:
    categories = {}

    for category in _SYMBOL_CATEGORIES:
        old_values = set(old_surface.get(category, []))
        new_values = set(new_surface.get(category, []))

        if added:
            values = sorted(new_values - old_values)
        elif removed:
            values = sorted(old_values - new_values)
        else:
            values = []

        if values:
            categories[category] = values

    if not categories:
        return None

    return {"path": path, "categories": categories}


def _count_unresolved_entries(entries: list[dict]) -> int:
    total = 0

    for entry in entries:
        imports = entry.get("imports", [])

        if isinstance(imports, list):
            total += len(imports)

    return total


def _count_symbol_entries(entries: list[dict]) -> int:
    total = 0

    for entry in entries:
        categories = entry.get("categories", {})

        if isinstance(categories, dict):
            for values in categories.values():
                if isinstance(values, list):
                    total += len(values)

    return total


def _render_none_or_lines(lines: object) -> str:
    items = list(lines) if lines is not None else []

    if not items:
        return "None."

    return "\n".join(f"- {item}" for item in items)


def _format_edge_signature(edge: object) -> str:
    if not isinstance(edge, tuple):
        return str(edge)

    from_path, to_path, label = edge

    if label:
        return f"`{from_path}` -> `{to_path}` via `{label}`"

    return f"`{from_path}` -> `{to_path}`"


def _format_route_signature(route: object) -> str:
    if not isinstance(route, tuple):
        return str(route)

    method, route_path, location = route

    if location:
        return f"`{method}` `{route_path}` ({location})"

    return f"`{method}` `{route_path}`"


def _format_unresolved_entry(entry: object) -> str:
    if not isinstance(entry, dict):
        return str(entry)

    path = entry.get("path", "")
    imports = entry.get("imports", [])

    if isinstance(imports, list) and imports:
        joined = ", ".join(f"`{item}`" for item in imports)
        return f"`{path}`: {joined}"

    return f"`{path}`"


def _format_symbol_entry(entry: object) -> str:
    if not isinstance(entry, dict):
        return str(entry)

    path = entry.get("path", "")
    categories = entry.get("categories", {})

    if not isinstance(categories, dict) or not categories:
        return f"`{path}`"

    parts = []

    for category in _SYMBOL_CATEGORIES:
        values = categories.get(category, [])

        if isinstance(values, list) and values:
            parts.append(f"{category}: {', '.join(f'`{value}`' for value in values)}")

    if parts:
        return f"`{path}`: " + "; ".join(parts)

    return f"`{path}`"
