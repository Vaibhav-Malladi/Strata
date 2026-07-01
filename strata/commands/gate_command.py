from strata.commands.cli_core import (
    GATE_REPORT_JSON_FILE,
    GATE_REPORT_MD_FILE,
    build_graph,
)
from strata.core.gate import evaluate_gate, write_gate_report
from strata.core.routes import (
    collect_routes,
    find_duplicate_routes,
    route_files_with_unresolved_imports,
)
from strata.utils.output import (
    format_path,
    format_status,
    print_banner,
    print_status_card,
    render_step,
    status_spinner,
)


def write_gate_command(root_path: str) -> int:
    with status_spinner(render_step("Evaluating gate", "running")) as spinner:
        graph = build_graph(root_path)

        if graph is None:
            return 1

        spinner.update(render_step("Collecting routes", "running"))
        routes_data = _load_current_routes_data(graph)
        spinner.update(render_step("Writing report", "running"))
        report = evaluate_gate(graph, routes_data)
        write_gate_report(root_path, report)

    status = str(report.get("status", "FAIL")).upper()
    failures = _count_items(report.get("failures"))
    warnings = _count_items(report.get("warnings"))

    print_banner()
    print_status_card(
        "Gate complete",
        [
            ("Markdown", format_path(GATE_REPORT_MD_FILE)),
            ("JSON", format_path(GATE_REPORT_JSON_FILE)),
            ("Failures", failures),
            ("Warnings", warnings),
        ],
        status=format_status(status),
    )

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
