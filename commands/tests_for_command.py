from cli_core import build_graph, save_graph
from cli_ui import green, red, print_title
from test_mapper import suggest_tests_for_file, format_test_suggestions


def show_tests_for(root_path: str, target_path: str) -> int:
    graph = build_graph(root_path)

    if graph is None:
        return 1

    save_graph(graph)

    result = suggest_tests_for_file(graph, target_path)

    if not result["found"]:
        print_title(red("Test suggestion warning"))
        print(format_test_suggestions(result))
        return 1

    print_title(green("Test suggestions generated"))
    print(format_test_suggestions(result))

    return 0