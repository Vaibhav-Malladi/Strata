from impact import analyze_impact


def generate_impact_notes(graph: dict, relevant_files: list[dict]) -> str:
    """Generate impact notes for relevant files in a task brief."""

    lines = []

    lines.append("## Impact Notes")
    lines.append("")

    if not relevant_files:
        lines.append("No relevant files were selected for impact analysis.")
        return "\n".join(lines)

    for item in relevant_files:
        file_info = item.get("file", {})
        path = file_info.get("path", "")

        if not path:
            continue

        impact = analyze_impact(graph, path)

        lines.append(f"### `{path}`")
        lines.append("")
        lines.append(f"- Risk level: `{impact['risk_level']}`")
        lines.append(f"- Summary: {impact['summary']}")

        if impact.get("direct_dependents"):
            lines.append("- Direct dependents:")

            for dependent in impact["direct_dependents"]:
                lines.append(f"  - `{dependent}`")
        else:
            lines.append("- Direct dependents: none")

        if impact.get("direct_dependencies"):
            lines.append("- Direct dependencies:")

            for dependency in impact["direct_dependencies"]:
                lines.append(f"  - `{dependency}`")
        else:
            lines.append("- Direct dependencies: none")

        if impact.get("transitive_dependents"):
            lines.append("- Transitive dependents:")

            for dependent in impact["transitive_dependents"]:
                lines.append(f"  - `{dependent}`")
        else:
            lines.append("- Transitive dependents: none")

        lines.append("")

    return "\n".join(lines).rstrip()