from cli_core import (
    GATE_REPORT_JSON_FILE,
    GATE_REPORT_MD_FILE,
    build_graph,
)
from cli_ui import green, print_kv, print_title, red, yellow
from gate import evaluate_gate, write_gate_report
from routes import (
    collect_routes,
    find_duplicate_routes,
    route_files_with_unresolved_imports,
)


def write_gate_command(root_path: str) -> int:
    graph = build_graph(root_path)

    if graph is None:
        return 1

    routes_data = _load_current_routes_data(graph)
    report = evaluate_gate(graph, routes_data)
    write_gate_report(root_path, report)

    status = str(report.get("status", "FAIL")).upper()
    status_label = _status_text(status)
    failures = _count_items(report.get("failures"))
    warnings = _count_items(report.get("warnings"))

    print_title("Gate complete")
    print_kv("Status", status_label)
    print_kv("Markdown", GATE_REPORT_MD_FILE)
    print_kv("JSON", GATE_REPORT_JSON_FILE)
    print_kv("Failures", failures)
    print_kv("Warnings", warnings)

    return 1 if status == "FAIL" else 0


def _load_current_routes_data(graph: dict):
    try:
        routes = collect_routes(graph)
        duplicates = find_duplicate_routes(routes)
        route_import_risks = route_files_with_unresolved_imports(graph)

        return {
            "routes": routes,
            "duplicate_routes": duplicates,
            "route_import_risks": route_import_risks,
        }
    except Exception:
        return []


def _count_items(values: object) -> int:
    if not isinstance(values, list):
        return 0

    return len(values)


def _status_text(status: str) -> str:
    if status == "PASS":
        return green(status)

    if status == "WARN":
        return yellow(status)

    return red(status)
