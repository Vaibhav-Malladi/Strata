from __future__ import annotations

import json
from pathlib import Path

from cli_core import (
    VERIFICATION_REPORT_JSON_FILE,
    VERIFICATION_REPORT_MD_FILE,
    build_graph,
)
from diff_engine import compare_graphs
from routes import collect_routes
from verify import verify_diff, write_verification_report
from ui import (
    build_banner,
    build_kv_table,
    build_section,
    format_path,
    format_status,
)


def write_verify_command(root_path: str) -> int:
    latest_snapshot = _load_latest_snapshot(root_path)

    if latest_snapshot is None:
        print(build_banner())
        print()
        print(build_section("Verification unavailable"))
        print("No snapshot found. Run `strata snapshot` first.")
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
    report = verify_diff(diff)
    write_verification_report(root_path, report)

    status = str(report.get("status", "FAIL")).upper()
    failures = _count_items(report.get("failures"))
    warnings = _count_items(report.get("warnings"))
    improvements = _count_items(report.get("improvements"))

    print(build_banner())
    print()
    print(build_section("Verification complete"))
    print(
        build_kv_table(
            [
                ("Status", format_status(status)),
                ("Markdown", format_path(VERIFICATION_REPORT_MD_FILE)),
                ("JSON", format_path(VERIFICATION_REPORT_JSON_FILE)),
                ("Snapshot", snapshot_timestamp),
                ("Failures", failures),
                ("Warnings", warnings),
                ("Improvements", improvements),
            ]
        )
    )

    return 1 if status == "FAIL" else 0


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


def _count_items(values: object) -> int:
    if not isinstance(values, list):
        return 0

    return len(values)
