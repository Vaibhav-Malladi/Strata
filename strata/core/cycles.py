def find_cycles(graph: dict) -> list[list[str]]:
    """Find circular dependency paths in a Strata graph."""

    adjacency = _build_adjacency(graph.get("edges", []))
    cycles = []

    for node in sorted(adjacency):
        _visit(
            node=node,
            adjacency=adjacency,
            path=[],
            visiting=set(),
            cycles=cycles,
        )

    return _dedupe_cycles(cycles)


def has_cycles(graph: dict) -> bool:
    """Return True if the graph contains at least one circular dependency."""

    return bool(find_cycles(graph))


def format_cycles(cycles: list[list[str]]) -> str:
    """Format dependency cycles as readable text."""

    if not cycles:
        return "No circular dependencies found."

    lines = []

    for index, cycle in enumerate(cycles, start=1):
        lines.append(f"Cycle {index}:")
        lines.append("  " + " -> ".join(cycle))
        lines.append("")

    return "\n".join(lines).rstrip()


def _build_adjacency(edges: list[dict]) -> dict[str, list[str]]:
    adjacency = {}

    for edge in edges:
        source = edge.get("from")
        target = edge.get("to")

        if not source or not target:
            continue

        adjacency.setdefault(source, [])

        if target not in adjacency[source]:
            adjacency[source].append(target)

        adjacency.setdefault(target, [])

    return adjacency


def _visit(
    node: str,
    adjacency: dict[str, list[str]],
    path: list[str],
    visiting: set[str],
    cycles: list[list[str]],
) -> None:
    if node in visiting:
        cycle_start = path.index(node)
        cycle = path[cycle_start:] + [node]
        cycles.append(cycle)
        return

    visiting.add(node)
    path.append(node)

    for neighbor in adjacency.get(node, []):
        _visit(
            node=neighbor,
            adjacency=adjacency,
            path=path.copy(),
            visiting=visiting.copy(),
            cycles=cycles,
        )


def _dedupe_cycles(cycles: list[list[str]]) -> list[list[str]]:
    seen = set()
    unique_cycles = []

    for cycle in cycles:
        key = _cycle_key(cycle)

        if key in seen:
            continue

        seen.add(key)
        unique_cycles.append(cycle)

    return unique_cycles


def _cycle_key(cycle: list[str]) -> tuple[str, ...]:
    if len(cycle) <= 1:
        return tuple(cycle)

    nodes = cycle[:-1]

    rotations = []

    for index in range(len(nodes)):
        rotated = nodes[index:] + nodes[:index]
        rotations.append(tuple(rotated))

    return min(rotations)
