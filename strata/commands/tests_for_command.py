from strata.commands.cli_core import build_graph, save_graph
from strata.core.test_mapper import suggest_tests_for_file, format_test_suggestions
from strata.utils.output import build_banner, build_kv_table, build_section, format_path


def show_tests_for(root_path: str, target_path: str) -> int:
    graph = build_graph(root_path)

    if graph is None:
        return 1

    save_graph(graph)

    result = suggest_tests_for_file(graph, target_path)

    if not result["found"]:
        print(build_banner())
        print()
        print(build_section("Test suggestion warning"))
        print(
            build_kv_table(
                [
                    ("File", format_path(result.get("target", target_path))),
                    ("Found", "no"),
                    ("Commands", len(result.get("recommended_commands", []))),
                    ("Tests", len(result.get("related_test_files", []))),
                ]
            )
        )
        print()
        print(format_test_suggestions(result))
        return 1

    print(build_banner())
    print()
    print(build_section("Tests complete"))
    print(
        build_kv_table(
            [
                ("File", format_path(result.get("target", target_path))),
                ("Found", "yes"),
                ("Commands", len(result.get("recommended_commands", []))),
                ("Tests", len(result.get("related_test_files", []))),
            ]
        )
    )
    print()
    print(format_test_suggestions(result))

    return 0
