from strata.core.brief import write_task_brief
from cli_core import (
    OUTPUT_FILE,
    TASK_BRIEF_FILE,
    build_graph,
    save_graph,
    count_unresolved_imports,
)
from strata.utils.output import build_banner, build_kv_table, build_section, format_path


def write_brief(root_path: str, task: str) -> int:
    graph = build_graph(root_path)

    if graph is None:
        return 1

    save_graph(graph)
    write_task_brief(graph, task, TASK_BRIEF_FILE)

    unresolved_count = count_unresolved_imports(graph)

    print(build_banner())
    print()
    print(build_section("Brief complete"))
    print(
        build_kv_table(
            [
                ("Task", task),
                ("Output", format_path(TASK_BRIEF_FILE)),
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
