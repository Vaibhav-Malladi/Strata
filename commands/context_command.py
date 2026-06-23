import json
import os

from cli_core import (
    CONTEXT_PACK_FILE,
    OUTPUT_FILE,
    ROUTES_JSON_FILE,
    build_graph,
    save_graph,
)
from context_pack import build_context_pack, rank_relevant_files
from routes import collect_routes
from ui import build_banner, build_kv_table, build_section, format_path


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
    routes_count = _count_routes(routes_data)
    symbols_count = _count_symbols(graph)

    print(build_banner())
    print()
    print(build_section("Context complete"))
    print(
        build_kv_table(
            [
                ("Task", task),
                ("Output", format_path(CONTEXT_PACK_FILE)),
                ("Graph", format_path(OUTPUT_FILE)),
                ("Files", len(graph.get("files", []))),
                ("Symbols", symbols_count),
                ("Routes", routes_count),
                ("Relevant files", len(relevant_files)),
            ]
        )
    )

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


def _count_routes(routes_data: dict) -> int:
    routes = routes_data.get("routes", [])

    if not isinstance(routes, list):
        return 0

    return len(routes)


def _count_symbols(graph: dict) -> int:
    symbol_keys = (
        "classes",
        "functions",
        "interfaces",
        "types",
        "enums",
        "exports",
    )
    total = 0

    for file_info in graph.get("files", []):
        if not isinstance(file_info, dict):
            continue

        for key in symbol_keys:
            values = file_info.get(key, [])

            if isinstance(values, list):
                total += len(values)

    return total
