from cli_core import build_graph, save_graph
from cli_ui import green, yellow, red, print_title
from impact import analyze_impact, format_impact_report


def show_impact(root_path: str, target_path: str) -> int:
    graph = build_graph(root_path)

    if graph is None:
        return 1

    save_graph(graph)

    impact = analyze_impact(graph, target_path)

    if not impact["found"]:
        print_title(red("Impact analysis failed"))
        print(format_impact_report(impact))
        return 1

    if impact["risk_level"] == "low":
        print_title(green("Impact analysis complete"))
    elif impact["risk_level"] == "medium":
        print_title(yellow("Impact analysis warning"))
    else:
        print_title(red("Impact analysis high risk"))

    print(format_impact_report(impact))

    return 0