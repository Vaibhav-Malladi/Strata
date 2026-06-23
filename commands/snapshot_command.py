from pathlib import Path

from cli_core import build_graph
from cli_ui import green, print_kv, print_title
from routes import collect_routes
from snapshot import write_snapshot


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

    print_title("Snapshot created")
    print_kv("Directory", str(snapshot_dir))
    print_kv("Graph", str(snapshot_dir / "graph.json"))
    print_kv("Routes", str(snapshot_dir / "routes.json"))
    print_kv("Summary", str(snapshot_dir / "summary.md"))
    print_kv("Files", result["summary"].get("file_count", 0))
    print_kv("Routes", result["summary"].get("route_count", 0))
    print_kv("Status", green("complete"))

    return 0
