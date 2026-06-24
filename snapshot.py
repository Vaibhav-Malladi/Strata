from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fs_utils import atomic_write_json, atomic_write_text


def make_snapshot_timestamp(now: datetime | None = None) -> str:
    """Return a Windows-safe timestamp for snapshot folder names."""

    return (now or datetime.now()).strftime("%Y%m%d_%H%M%S")


def summarize_snapshot(graph: dict, routes_data: dict | None = None) -> dict:
    """Summarize a structural snapshot without including source contents."""

    graph_data = graph if isinstance(graph, dict) else {}
    files = graph_data.get("files", [])
    edges = graph_data.get("edges", [])

    summary = {
        "file_count": len(files) if isinstance(files, list) else 0,
        "edge_count": len(edges) if isinstance(edges, list) else 0,
        "route_count": _count_routes(routes_data),
        "unresolved_import_count": _count_unresolved_imports(files),
        "language_counts": _count_values(files, "language"),
    }

    framework_counts = _count_values(files, "framework")

    if framework_counts:
        summary["framework_counts"] = framework_counts

    error_count = _count_errors(files)

    if error_count is not None:
        summary["error_count"] = error_count

    return summary


def write_snapshot(
    root: str | Path,
    graph: dict,
    routes_data: dict | None = None,
    timestamp: str | None = None,
) -> dict:
    """Write a snapshot folder containing graph, routes, and summary files."""

    root_path = Path(root)
    snapshot_timestamp = timestamp or make_snapshot_timestamp()
    snapshots_dir = root_path / ".aidc" / "snapshots"
    snapshot_dir = snapshots_dir / snapshot_timestamp
    graph_path = snapshot_dir / "graph.json"
    routes_path = snapshot_dir / "routes.json"
    summary_path = snapshot_dir / "summary.md"
    latest_path = snapshots_dir / "latest.txt"

    snapshot_dir.mkdir(parents=True, exist_ok=True)
    snapshots_dir.mkdir(parents=True, exist_ok=True)

    graph_payload = graph if isinstance(graph, dict) else {}
    routes_payload = _normalize_routes_payload(routes_data)

    atomic_write_json(graph_path, graph_payload)
    atomic_write_json(routes_path, routes_payload)

    summary = summarize_snapshot(graph_payload, routes_payload)
    summary["timestamp"] = snapshot_timestamp
    summary["root"] = str(root_path)

    summary_markdown = build_snapshot_summary_markdown(summary)
    atomic_write_text(summary_path, summary_markdown)
    atomic_write_text(latest_path, snapshot_timestamp)

    return {
        "root": str(root_path),
        "timestamp": snapshot_timestamp,
        "snapshot_dir": str(snapshot_dir),
        "graph_path": str(graph_path),
        "routes_path": str(routes_path),
        "summary_path": str(summary_path),
        "latest_path": str(latest_path),
        "summary": summary,
    }


def build_snapshot_summary_markdown(summary: dict) -> str:
    """Build a compact Markdown summary for a snapshot."""

    lines = [
        "# Strata Snapshot Summary",
        "",
        f"- Timestamp: `{summary.get('timestamp', '')}`",
        f"- Root: `{summary.get('root', '')}`",
        f"- Files: `{summary.get('file_count', 0)}`",
        f"- Edges: `{summary.get('edge_count', 0)}`",
        f"- Routes: `{summary.get('route_count', 0)}`",
        f"- Unresolved Imports: `{summary.get('unresolved_import_count', 0)}`",
        f"- Languages: `{_format_counts(summary.get('language_counts', {}))}`",
        f"- Frameworks: `{_format_counts(summary.get('framework_counts', {}))}`",
        f"- Errors: `{summary.get('error_count', 0)}`",
    ]

    return "\n".join(lines)


def _count_routes(routes_data: dict | list | None) -> int:
    routes = _extract_routes(routes_data)
    return len(routes)


def _extract_routes(routes_data: dict | list | None) -> list:
    if routes_data is None:
        return []

    if isinstance(routes_data, list):
        return routes_data

    if isinstance(routes_data, dict):
        routes = routes_data.get("routes", [])

        if isinstance(routes, list):
            return routes

    return []


def _count_unresolved_imports(files: list) -> int:
    count = 0

    if not isinstance(files, list):
        return count

    for file_info in files:
        if not isinstance(file_info, dict):
            continue

        unresolved_imports = file_info.get("unresolved_imports", [])

        if isinstance(unresolved_imports, list):
            count += len(unresolved_imports)
        elif unresolved_imports:
            count += 1

    return count


def _count_values(files: list, key: str) -> dict:
    counts = {}

    if not isinstance(files, list):
        return counts

    for file_info in files:
        if not isinstance(file_info, dict):
            continue

        value = file_info.get(key)

        if not value:
            continue

        counts[value] = counts.get(value, 0) + 1

    return dict(sorted(counts.items()))


def _count_errors(files: list) -> int | None:
    if not isinstance(files, list):
        return None

    count = 0
    saw_error_field = False

    for file_info in files:
        if not isinstance(file_info, dict):
            continue

        if "errors" in file_info:
            saw_error_field = True
            errors = file_info.get("errors")

            if isinstance(errors, list):
                count += len(errors)
            elif errors:
                count += 1

        elif "error" in file_info:
            saw_error_field = True

            if file_info.get("error"):
                count += 1

    return count if saw_error_field else None


def _format_counts(counts: dict | None) -> str:
    if not counts:
        return "None"

    parts = [f"{key}={value}" for key, value in counts.items()]
    return ", ".join(parts)


def _normalize_routes_payload(routes_data: dict | list | None) -> dict:
    if routes_data is None:
        return {"routes": []}

    if isinstance(routes_data, list):
        return {"routes": routes_data}

    if isinstance(routes_data, dict):
        payload = dict(routes_data)
        routes = payload.get("routes", [])

        if isinstance(routes, list):
            payload["routes"] = routes
        else:
            payload["routes"] = []

        return payload

    return {"routes": []}
