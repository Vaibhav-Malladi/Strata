from cli_core import OUTPUT_FILE, build_graph, save_graph, count_unresolved_imports
from cli_ui import green, yellow, print_title, print_kv


def write_graph(root_path: str) -> int:
    graph = build_graph(root_path)

    if graph is None:
        return 1

    save_graph(graph)

    unresolved_count = count_unresolved_imports(graph)

    print_title(green("Scan complete"))
    print_kv("Output", OUTPUT_FILE)
    print_kv("Root", graph["root"])
    print_kv("Files", len(graph["files"]))
    print_kv("Edges", len(graph["edges"]))

    if unresolved_count:
        print_kv("Warnings", yellow(f"{unresolved_count} unresolved import(s)"))
    else:
        print_kv("Warnings", green("none"))

    return 0