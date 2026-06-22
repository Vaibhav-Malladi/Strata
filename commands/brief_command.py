from brief import write_task_brief
from cli_core import (
    OUTPUT_FILE,
    TASK_BRIEF_FILE,
    build_graph,
    save_graph,
    count_unresolved_imports,
)
from cli_ui import green, yellow, print_title, print_kv


def write_brief(root_path: str, task: str) -> int:
    graph = build_graph(root_path)

    if graph is None:
        return 1

    save_graph(graph)
    write_task_brief(graph, task, TASK_BRIEF_FILE)

    unresolved_count = count_unresolved_imports(graph)

    print_title(green("Task brief generated"))
    print_kv("Graph", OUTPUT_FILE)
    print_kv("Task brief", TASK_BRIEF_FILE)
    print_kv("Root", graph["root"])
    print_kv("Files", len(graph["files"]))
    print_kv("Edges", len(graph["edges"]))

    if unresolved_count:
        print_kv("Warnings", yellow(f"{unresolved_count} unresolved import(s)"))
    else:
        print_kv("Warnings", green("none"))

    return 0