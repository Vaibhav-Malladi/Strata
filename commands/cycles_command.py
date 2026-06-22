from cli_core import build_graph, save_graph
from cli_ui import green, yellow, print_title, print_kv
from cycles import find_cycles, format_cycles


def show_cycles(root_path: str) -> int:
    graph = build_graph(root_path)

    if graph is None:
        return 1

    save_graph(graph)

    cycles = find_cycles(graph)

    if cycles:
        print_title(yellow("Circular dependencies found"))
        print(format_cycles(cycles))
        return 1

    print_title(green("Cycle check complete"))
    print_kv("Root", graph["root"])
    print_kv("Files", len(graph["files"]))
    print_kv("Edges", len(graph["edges"]))
    print_kv("Cycles", green("none"))

    return 0