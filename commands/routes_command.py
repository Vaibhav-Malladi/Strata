from cli_core import (
    ROUTES_JSON_FILE,
    ROUTES_MD_FILE,
    build_graph,
    save_graph,
)
from cli_ui import green, print_kv, print_title
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

    print_title("Route map generated")
    print_kv("Markdown", ROUTES_MD_FILE)
    print_kv("JSON", ROUTES_JSON_FILE)
    print_kv("Root", graph.get("root", ""))
    print_kv("Backend routes", len(routes))
    print_kv("Duplicate warnings", len(duplicates))
    print_kv("Import risks", len(route_import_risks))
    print_kv("Status", green("complete"))

    return 0