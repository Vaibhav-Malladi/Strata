from cli_core import (
    OUTPUT_FILE,
    PROJECT_MAP_FILE,
    build_graph,
    save_graph,
    count_unresolved_imports,
)
from strata.utils.output import build_banner, build_kv_table, build_section, format_path
from strata.core.map_writer import write_project_map


def write_map(root_path: str) -> int:
    graph = build_graph(root_path)

    if graph is None:
        return 1

    save_graph(graph)
    write_project_map(graph, PROJECT_MAP_FILE)

    unresolved_count = count_unresolved_imports(graph)

    print(build_banner())
    print()
    print(build_section("Map complete"))
    print(
        build_kv_table(
            [
                ("Output", format_path(PROJECT_MAP_FILE)),
                ("Graph", format_path(OUTPUT_FILE)),
                ("Root", format_path(graph["root"])),
                ("Files", len(graph["files"])),
                ("Edges", len(graph["edges"])),
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
