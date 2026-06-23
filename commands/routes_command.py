from cli_core import (
    ROUTES_JSON_FILE,
    ROUTES_MD_FILE,
    build_graph,
    save_graph,
)
from ui import build_banner, build_kv_table, build_section, format_path
from routes import (
    collect_routes,
    find_duplicate_routes,
    route_files_with_unresolved_imports,
    write_routes_json,
    write_routes_report,
)


def write_routes(root_path: str) -> int:
    graph = build_graph(root_path)

    if graph is None:
        return 1

    save_graph(graph)
    write_routes_report(graph, ROUTES_MD_FILE)
    write_routes_json(graph, ROUTES_JSON_FILE)

    routes = collect_routes(graph)
    duplicates = find_duplicate_routes(routes)
    route_import_risks = route_files_with_unresolved_imports(graph)

    print(build_banner())
    print()
    print(build_section("Routes complete"))
    print(
        build_kv_table(
            [
                ("Markdown", format_path(ROUTES_MD_FILE)),
                ("JSON", format_path(ROUTES_JSON_FILE)),
                ("Root", format_path(graph.get("root", ""))),
                ("Routes", len(routes)),
                ("Duplicate warnings", len(duplicates)),
                ("Import risks", len(route_import_risks)),
            ]
        )
    )

    return 0
