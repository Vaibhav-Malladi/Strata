from cli_core import (
    OUTPUT_FILE,
    PREFLIGHT_FILE,
    build_graph,
    save_graph,
    count_unresolved_imports,
)
from strata.core.brief import score_relevant_files
from strata.core.preflight import write_preflight_report
from strata.utils.output import build_banner, build_kv_table, build_section, format_path


def write_preflight(root_path: str, task: str) -> int:
    graph = build_graph(root_path)

    if graph is None:
        return 1

    save_graph(graph)
    write_preflight_report(graph, task, PREFLIGHT_FILE)

    unresolved_count = count_unresolved_imports(graph)
    relevant_count = len(score_relevant_files(graph, task))

    print(build_banner())
    print()
    print(build_section("Preflight complete"))
    print(
        build_kv_table(
            [
                ("Task", task),
                ("Output", format_path(PREFLIGHT_FILE)),
                ("Graph", format_path(OUTPUT_FILE)),
                ("Files", len(graph["files"])),
                ("Symbols", _count_symbols(graph)),
                ("Routes", _count_routes(graph)),
                ("Relevant files", relevant_count),
                (
                    "Warnings",
                    f"{unresolved_count} unresolved import(s)"
                    if unresolved_count
                    else "none",
                ),
            ]
        )
    )

    return 0


def _count_routes(graph: dict) -> int:
    count = 0

    for file_info in graph.get("files", []):
        if not isinstance(file_info, dict):
            continue

        routes = file_info.get("routes", [])

        if isinstance(routes, list):
            count += len(routes)

    return count


def _count_symbols(graph: dict) -> int:
    count = 0
    symbol_keys = (
        "classes",
        "functions",
        "interfaces",
        "types",
        "enums",
        "exports",
    )

    for file_info in graph.get("files", []):
        if not isinstance(file_info, dict):
            continue

        for key in symbol_keys:
            values = file_info.get(key, [])

            if isinstance(values, list):
                count += len(values)

    return count
