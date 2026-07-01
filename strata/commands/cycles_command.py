from strata.commands.cli_core import OUTPUT_FILE, build_graph, save_graph
from strata.core.cycles import find_cycles, format_cycles
from strata.utils.output import build_banner, build_kv_table, build_section, format_path


def show_cycles(root_path: str) -> int:
    graph = build_graph(root_path)

    if graph is None:
        return 1

    save_graph(graph)

    cycles = find_cycles(graph)

    if cycles:
        print(build_banner())
        print()
        print(build_section("Circular dependencies found"))
        print(
            build_kv_table(
                [
                    ("Root", format_path(graph["root"])),
                    ("Graph", format_path(OUTPUT_FILE)),
                    ("Files", len(graph["files"])),
                    ("Edges", len(graph["edges"])),
                    ("Cycles", len(cycles)),
                ]
            )
        )
        print()
        print(format_cycles(cycles))
        return 1

    print(build_banner())
    print()
    print(build_section("Cycles complete"))
    print(
        build_kv_table(
            [
                ("Root", format_path(graph["root"])),
                ("Graph", format_path(OUTPUT_FILE)),
                ("Files", len(graph["files"])),
                ("Edges", len(graph["edges"])),
                ("Cycles", 0),
            ]
        )
    )

    return 0
