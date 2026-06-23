from cli_core import OUTPUT_FILE, build_graph, save_graph, count_unresolved_imports
from ui import build_banner, build_kv_table, build_section, format_path, format_warning


def write_graph(root_path: str) -> int:
    graph = build_graph(root_path)

    if graph is None:
        return 1

    save_graph(graph)

    unresolved_count = count_unresolved_imports(graph)

    print(build_banner())
    print()
    print(build_section("Scan complete"))
    print(
        build_kv_table(
            [
                ("Root", format_path(graph["root"])),
                ("Graph", format_path(OUTPUT_FILE)),
                ("Nodes", len(graph["files"])),
                ("Edges", len(graph["edges"])),
                (
                    "Warnings",
                    format_warning(f"{unresolved_count} unresolved import(s)")
                    if unresolved_count
                    else 0,
                ),
            ]
        )
    )

    return 0
