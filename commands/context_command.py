import json
import os

from cli_core import (
    CONTEXT_PACK_FILE,
    OUTPUT_FILE,
    ROUTES_JSON_FILE,
    build_graph,
    save_graph,
)
from cli_ui import green, print_kv, print_title
from context_pack import build_context_pack, rank_relevant_files
from routes import collect_routes


def write_context(root_path: str, task: str | None = None) -> int:
    if not task:
        _print_usage()
        return 1

    graph = build_graph(root_path)

    if graph is None:
        return 1

    save_graph(graph)
    routes_data = _load_routes_data(graph)
    content = build_context_pack(graph, task, routes_data)

    output_dir = os.path.dirname(CONTEXT_PACK_FILE)

    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    with open(CONTEXT_PACK_FILE, "w", encoding="utf-8") as file:
        file.write(content)

    relevant_files = rank_relevant_files(graph, task)

    print_title(green("Context pack generated"))
    print_kv("Graph", OUTPUT_FILE)
    print_kv("Markdown", CONTEXT_PACK_FILE)
    print_kv("Task", task)
    print_kv("Relevant files", len(relevant_files))
    print_kv("Status", green("complete"))

    return 0


def _load_routes_data(graph: dict) -> dict:
    if os.path.exists(ROUTES_JSON_FILE):
        try:
            with open(ROUTES_JSON_FILE, "r", encoding="utf-8") as file:
                routes_data = json.load(file)

            if isinstance(routes_data, dict):
                return routes_data
        except (OSError, json.JSONDecodeError):
            pass

    return {"routes": collect_routes(graph)}


def _print_usage() -> None:
    print('Usage: strata context "<task>"')
    print('Usage: strata context <root> "<task>"')
