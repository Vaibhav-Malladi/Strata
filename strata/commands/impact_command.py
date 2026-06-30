from cli_core import OUTPUT_FILE, build_graph, save_graph
from strata.core.impact import analyze_impact, format_impact_report
from strata.utils.output import build_banner, build_kv_table, build_section, format_path


def show_impact(root_path: str, target_path: str) -> int:
    graph = build_graph(root_path)

    if graph is None:
        return 1

    save_graph(graph)

    impact = analyze_impact(graph, target_path)

    if not impact["found"]:
        print(build_banner())
        print()
        print(build_section("Impact analysis failed"))
        print(
            build_kv_table(
                [
                    ("Target", format_path(impact.get("target", target_path))),
                    ("Graph", format_path(OUTPUT_FILE)),
                    ("Found", "no"),
                    ("Risk level", impact.get("risk_level", "unknown")),
                    ("Summary", impact.get("summary", "")),
                ]
            )
        )
        print()
        print(format_impact_report(impact))
        return 1

    title = (
        "Impact analysis complete"
        if impact["risk_level"] == "low"
        else "Impact analysis warning"
        if impact["risk_level"] == "medium"
        else "Impact analysis high risk"
    )

    print(build_banner())
    print()
    print(build_section(title))
    print(
        build_kv_table(
            [
                ("Target", format_path(impact.get("target", target_path))),
                ("Graph", format_path(OUTPUT_FILE)),
                ("Found", "yes"),
                ("Risk level", impact.get("risk_level", "unknown")),
                (
                    "Direct dependents",
                    len(impact.get("direct_dependents", [])),
                ),
                (
                    "Direct dependencies",
                    len(impact.get("direct_dependencies", [])),
                ),
                (
                    "Transitive dependents",
                    len(impact.get("transitive_dependents", [])),
                ),
            ]
        )
    )
    print()
    print(format_impact_report(impact))

    return 0
