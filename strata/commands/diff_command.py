import json
import os
from pathlib import Path

from cli_core import (
    DIFF_REPORT_JSON_FILE,
    DIFF_REPORT_MD_FILE,
    build_graph,
)
from strata.core.diff_engine import compare_graphs, write_diff_report
from strata.core.routes import collect_routes
from strata.utils.output import build_banner, build_kv_table, build_section, format_path


def write_diff_command(root_path: str) -> int:
    latest_snapshot = _load_latest_snapshot(root_path)

    if latest_snapshot is None:
        print(build_banner())
        print()
        print(build_section("Diff unavailable"))
        print('No snapshot found. Run `strata snapshot` first.')
        return 1

    snapshot_timestamp, old_graph, old_routes_data = latest_snapshot

    current_graph = build_graph(root_path)

    if current_graph is None:
        return 1

    current_routes_data = _load_current_routes_data(current_graph)
    diff = compare_graphs(
        old_graph,
        current_graph,
        old_routes_data,
        current_routes_data,
    )

    write_diff_report(root_path, diff)

    summary = diff.get("summary", {}) if isinstance(diff, dict) else {}

    print(build_banner())
    print()
    print(build_section("Diff complete"))
    print(
        build_kv_table(
            [
                ("Markdown", format_path(DIFF_REPORT_MD_FILE)),
                ("JSON", format_path(DIFF_REPORT_JSON_FILE)),
                ("Snapshot", snapshot_timestamp),
                ("Files added", summary.get("files_added", 0)),
                ("Files removed", summary.get("files_removed", 0)),
                ("Edges added", summary.get("edges_added", 0)),
                ("Edges removed", summary.get("edges_removed", 0)),
                ("Routes added", summary.get("routes_added", 0)),
                ("Routes removed", summary.get("routes_removed", 0)),
                ("Unresolved added", summary.get("unresolved_imports_added", 0)),
                ("Unresolved removed", summary.get("unresolved_imports_removed", 0)),
                ("Symbols added", summary.get("symbols_added", 0)),
                ("Symbols removed", summary.get("symbols_removed", 0)),
            ]
        )
    )

    return 0


def _load_latest_snapshot(root_path: str):
    snapshots_dir = Path(root_path) / ".aidc" / "snapshots"
    latest_path = snapshots_dir / "latest.txt"

    if not latest_path.exists():
        return None

    try:
        timestamp = latest_path.read_text(encoding="utf-8").strip()
    except OSError:
        return None

    if not timestamp:
        return None

    snapshot_dir = snapshots_dir / timestamp
    graph_path = snapshot_dir / "graph.json"
    routes_path = snapshot_dir / "routes.json"

    if not graph_path.exists():
        return None

    try:
        old_graph = json.loads(graph_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    old_routes_data = _load_routes_data(routes_path)

    return timestamp, old_graph, old_routes_data


def _load_routes_data(routes_path: Path):
    if not routes_path.exists():
        return []

    try:
        routes_data = json.loads(routes_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    if isinstance(routes_data, (dict, list)):
        return routes_data

    return []


def _load_current_routes_data(graph: dict):
    try:
        return collect_routes(graph)
    except Exception:
        return []
