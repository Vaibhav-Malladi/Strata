from cycles import find_cycles


def analyze_health(graph: dict) -> dict:
    """Analyze repository dependency health from a Strata graph."""

    files = graph.get("files", [])
    edges = graph.get("edges", [])
    cycles = find_cycles(graph)

    incoming_counts = _count_edges(edges, "to")
    outgoing_counts = _count_edges(edges, "from")
    unresolved_imports = _collect_unresolved_imports(files)

    return {
        "root": graph.get("root", ""),
        "file_count": len(files),
        "edge_count": len(edges),
        "unresolved_import_count": len(unresolved_imports),
        "unresolved_imports": unresolved_imports,
        "cycle_count": len(cycles),
        "cycles": cycles,
        "top_incoming": _top_counts(incoming_counts),
        "top_outgoing": _top_counts(outgoing_counts),
        "status": _health_status(
            unresolved_import_count=len(unresolved_imports),
            cycle_count=len(cycles),
        ),
    }


def format_health_report(health: dict) -> str:
    """Format a repository health report as readable text."""

    lines = []

    lines.append("Dependency health summary")
    lines.append("")
    lines.append(f"Root: {health.get('root', '')}")
    lines.append(f"Files: {health.get('file_count', 0)}")
    lines.append(f"Dependency edges: {health.get('edge_count', 0)}")
    lines.append(f"Status: {health.get('status', 'unknown')}")
    lines.append("")

    lines.append("Warnings")
    lines.append("--------")

    if health.get("unresolved_import_count", 0) == 0 and health.get("cycle_count", 0) == 0:
        lines.append("No dependency warnings found.")
    else:
        if health.get("unresolved_import_count", 0):
            lines.append(f"Unresolved imports: {health['unresolved_import_count']}")

            for item in health.get("unresolved_imports", []):
                path = item.get("path", "")
                name = item.get("name", "")
                line = item.get("line", "")
                lines.append(f"- {path}: {name} at line {line}")

        if health.get("cycle_count", 0):
            lines.append(f"Circular dependencies: {health['cycle_count']}")

            for cycle in health.get("cycles", []):
                lines.append(f"- {' -> '.join(cycle)}")

    lines.append("")
    lines.append("Files with most incoming dependencies")
    lines.append("-------------------------------------")

    if health.get("top_incoming"):
        for item in health["top_incoming"]:
            lines.append(f"- {item['path']}: {item['count']}")
    else:
        lines.append("none")

    lines.append("")
    lines.append("Files with most outgoing dependencies")
    lines.append("-------------------------------------")

    if health.get("top_outgoing"):
        for item in health["top_outgoing"]:
            lines.append(f"- {item['path']}: {item['count']}")
    else:
        lines.append("none")

    return "\n".join(lines)


def _collect_unresolved_imports(files: list[dict]) -> list[dict]:
    unresolved = []

    for file_info in files:
        path = file_info.get("path", "")

        for item in file_info.get("unresolved_import_details", []):
            unresolved.append(
                {
                    "path": path,
                    "name": item.get("name", ""),
                    "line": item.get("line", ""),
                }
            )

    return unresolved


def _count_edges(edges: list[dict], key: str) -> dict[str, int]:
    counts = {}

    for edge in edges:
        path = edge.get(key)

        if not path:
            continue

        counts[path] = counts.get(path, 0) + 1

    return counts


def _top_counts(counts: dict[str, int], limit: int = 5) -> list[dict]:
    items = []

    for path, count in counts.items():
        items.append(
            {
                "path": path,
                "count": count,
            }
        )

    items.sort(key=lambda item: (item["count"], item["path"]), reverse=True)

    return items[:limit]


def _health_status(unresolved_import_count: int, cycle_count: int) -> str:
    if cycle_count:
        return "warning: circular dependencies found"

    if unresolved_import_count:
        return "warning: unresolved imports found"

    return "healthy"