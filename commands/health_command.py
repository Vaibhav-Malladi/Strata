from cli_core import build_graph, save_graph
from cli_ui import green, yellow, print_title
from health import analyze_health, format_health_report


def show_health(root_path: str) -> int:
    graph = build_graph(root_path)

    if graph is None:
        return 1

    save_graph(graph)

    health = analyze_health(graph)

    if health["status"] == "healthy":
        print_title(green("Dependency health complete"))
    else:
        print_title(yellow("Dependency health warnings"))

    print(format_health_report(health))

    return 0