from pathlib import Path

from cli_core import build_graph
from routes import collect_routes
from snapshot import write_snapshot
from ui import build_banner, build_kv_table, build_section, format_path


def write_snapshot_command(root_path: str) -> int:
    graph = build_graph(root_path)

    if graph is None:
        return 1

    try:
        routes_data = collect_routes(graph)
    except Exception:
        routes_data = []

    result = write_snapshot(root_path, graph, routes_data)
    snapshot_dir = Path(".aidc") / "snapshots" / result["timestamp"]

    print(build_banner())
    print()
    print(build_section("Snapshot complete"))
    print(
        build_kv_table(
            [
                ("Snapshot", result["timestamp"]),
                ("Folder", format_path(snapshot_dir)),
                ("Latest", format_path(Path(".aidc") / "snapshots" / "latest.txt")),
                ("Graph", format_path(snapshot_dir / "graph.json")),
                ("Routes", format_path(snapshot_dir / "routes.json")),
                ("Summary", format_path(snapshot_dir / "summary.md")),
            ]
        )
    )

    return 0
