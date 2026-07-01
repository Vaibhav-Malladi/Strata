from strata.commands.cli_core import OUTPUT_FILE, build_graph, save_graph
from strata.core.health import analyze_health, format_health_report
from strata.utils.output import build_banner, build_kv_table, build_section, format_path


def show_health(root_path: str) -> int:
    graph = build_graph(root_path)

    if graph is None:
        return 1

    save_graph(graph)

    health = analyze_health(graph)
    title = (
        "Dependency health complete"
        if health["status"] == "healthy"
        else "Dependency health warnings"
    )

    print(build_banner())
    print()
    print(build_section(title))
    print(
        build_kv_table(
            [
                ("Root", format_path(health.get("root", graph.get("root", "")))),
                ("Graph", format_path(OUTPUT_FILE)),
                ("Files", health.get("file_count", 0)),
                ("Edges", health.get("edge_count", 0)),
                ("Status", health.get("status", "unknown")),
                (
                    "Warnings",
                    "none"
                    if not health.get("unresolved_import_count", 0)
                    and not health.get("cycle_count", 0)
                    else (
                        f"unresolved imports: {health.get('unresolved_import_count', 0)}; "
                        f"cycles: {health.get('cycle_count', 0)}"
                    ),
                ),
            ]
        )
    )
    print()
    print(format_health_report(health))

    return 0
