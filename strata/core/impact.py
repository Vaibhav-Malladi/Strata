def analyze_impact(graph: dict, target_path: str) -> dict:
    """Analyze likely impact of changing a file in a Strata graph."""

    matching_path = _find_matching_path(graph, target_path)

    if matching_path is None:
        return {
            "target": target_path,
            "found": False,
            "direct_dependents": [],
            "direct_dependencies": [],
            "transitive_dependents": [],
            "risk_level": "unknown",
            "summary": f"File not found in graph: {target_path}",
        }

    direct_dependents = _direct_neighbors(
        graph=graph,
        path=matching_path,
        edge_key="to",
        result_key="from",
    )

    direct_dependencies = _direct_neighbors(
        graph=graph,
        path=matching_path,
        edge_key="from",
        result_key="to",
    )

    transitive_dependents = _transitive_dependents(graph, matching_path)

    return {
        "target": matching_path,
        "found": True,
        "direct_dependents": direct_dependents,
        "direct_dependencies": direct_dependencies,
        "transitive_dependents": transitive_dependents,
        "risk_level": _risk_level(
            direct_dependents=direct_dependents,
            transitive_dependents=transitive_dependents,
        ),
        "summary": _summary(
            target=matching_path,
            direct_dependents=direct_dependents,
            transitive_dependents=transitive_dependents,
        ),
    }


def format_impact_report(impact: dict) -> str:
    """Format impact analysis as readable text."""

    lines = []

    lines.append("Impact analysis")
    lines.append("")
    lines.append(f"Target: {impact.get('target', '')}")
    lines.append(f"Found: {impact.get('found', False)}")
    lines.append(f"Risk level: {impact.get('risk_level', 'unknown')}")
    lines.append(f"Summary: {impact.get('summary', '')}")
    lines.append("")

    if not impact.get("found", False):
        return "\n".join(lines).rstrip()

    lines.append("Direct dependents")
    lines.append("-----------------")

    if impact.get("direct_dependents"):
        for path in impact["direct_dependents"]:
            lines.append(f"- {path}")
    else:
        lines.append("none")

    lines.append("")
    lines.append("Direct dependencies")
    lines.append("-------------------")

    if impact.get("direct_dependencies"):
        for path in impact["direct_dependencies"]:
            lines.append(f"- {path}")
    else:
        lines.append("none")

    lines.append("")
    lines.append("Transitive dependents")
    lines.append("---------------------")

    if impact.get("transitive_dependents"):
        for path in impact["transitive_dependents"]:
            lines.append(f"- {path}")
    else:
        lines.append("none")

    return "\n".join(lines).rstrip()


def _find_matching_path(graph: dict, target_path: str) -> str | None:
    normalized_target = _normalize_path(target_path)

    for file_info in graph.get("files", []):
        path = file_info.get("path", "")
        normalized_path = _normalize_path(path)

        if normalized_path == normalized_target:
            return path

        if normalized_path.endswith(normalized_target):
            return path

    return None


def _direct_neighbors(
    graph: dict,
    path: str,
    edge_key: str,
    result_key: str,
) -> list[str]:
    results = []

    for edge in graph.get("edges", []):
        if edge.get(edge_key) != path:
            continue

        result = edge.get(result_key)

        if result and result not in results:
            results.append(result)

    return sorted(results)


def _transitive_dependents(graph: dict, path: str) -> list[str]:
    reverse_adjacency = {}

    for edge in graph.get("edges", []):
        source = edge.get("from")
        target = edge.get("to")

        if not source or not target:
            continue

        reverse_adjacency.setdefault(target, [])

        if source not in reverse_adjacency[target]:
            reverse_adjacency[target].append(source)

    visited = set()
    pending = list(reverse_adjacency.get(path, []))

    while pending:
        current = pending.pop(0)

        if current in visited:
            continue

        visited.add(current)

        for next_path in reverse_adjacency.get(current, []):
            if next_path not in visited:
                pending.append(next_path)

    visited.discard(path)

    return sorted(visited)


def _risk_level(
    direct_dependents: list[str],
    transitive_dependents: list[str],
) -> str:
    affected_count = len(set(direct_dependents) | set(transitive_dependents))

    if affected_count == 0:
        return "low"

    if affected_count <= 2:
        return "medium"

    return "high"


def _summary(
    target: str,
    direct_dependents: list[str],
    transitive_dependents: list[str],
) -> str:
    affected_count = len(set(direct_dependents) | set(transitive_dependents))

    if affected_count == 0:
        return f"Changing {target} is unlikely to affect other tracked files."

    if affected_count == 1:
        return f"Changing {target} may affect 1 tracked file."

    return f"Changing {target} may affect {affected_count} tracked files."


def _normalize_path(path: str) -> str:
    return path.replace("\\", "/").strip()
