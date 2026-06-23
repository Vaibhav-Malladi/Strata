from __future__ import annotations

import os
import re

try:
    from test_mapper import suggest_tests_for_file
except Exception:  # pragma: no cover - optional helper fallback
    suggest_tests_for_file = None


TASK_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "in", "into", "is", "it", "of", "on", "or", "the", "this", "to",
    "with", "add", "change", "create", "delete", "do", "edit", "fix",
    "improve", "implement", "make", "modify", "remove", "replace",
    "rewrite", "task", "update", "upgrade",
}

MAX_RELEVANT_FILES = 10
MAX_RELEVANT_ROUTES = 8
MAX_RELATED_TEST_FILES = 6
MAX_VERIFICATION_COMMANDS = 6


def extract_task_terms(task: str) -> list[str]:
    """Extract deterministic keyword terms from a task hint."""

    terms = []

    for word in re.findall(r"[A-Za-z0-9]+", task.lower()):
        if len(word) <= 2:
            continue

        if word in TASK_STOP_WORDS:
            continue

        terms.append(word)

    return _dedupe(terms)


def score_file_for_task(file_info: dict, task_terms: list[str]) -> int:
    """Score a file against extracted task terms."""

    if not file_info or not task_terms:
        return 0

    score = 0
    path = str(file_info.get("path", ""))
    basename = os.path.basename(path)
    path_text = _normalize_text(path)
    basename_text = _normalize_text(basename)
    symbols = _collect_symbol_names(file_info)
    imports = _collect_import_strings(file_info)
    routes = _collect_route_strings(file_info)

    for term in task_terms:
        if term in path_text:
            score += 4

        if term in basename_text:
            score += 6

        for symbol in symbols:
            if term in symbol:
                score += 3
                break

        for import_name in imports:
            if term in import_name:
                score += 1
                break

        for route_text in routes:
            if term in route_text:
                score += 2
                break

    return score


def rank_relevant_files(graph: dict, task: str, limit: int = 10) -> list[dict]:
    """Rank likely relevant files for a task."""

    task_terms = extract_task_terms(task)
    scored_files = []

    for file_info in graph.get("files", []):
        score = score_file_for_task(file_info, task_terms)

        if score <= 0:
            continue

        scored_files.append(
            {
                "file": file_info,
                "score": score,
                "matched_terms": _matched_terms_for_file(file_info, task_terms),
            }
        )

    scored_files.sort(
        key=lambda item: (
            -item["score"],
            item["file"].get("path", ""),
        )
    )

    return scored_files[:limit]


def find_dependency_neighbors(graph: dict, relevant_paths: list[str]) -> dict:
    """Find files directly connected to relevant files through graph edges."""

    relevant_set = {_normalize_path(path) for path in relevant_paths if path}
    dependencies = []
    dependents = []

    for edge in graph.get("edges", []):
        from_path = _normalize_path(edge.get("from", ""))
        to_path = _normalize_path(edge.get("to", ""))

        if from_path in relevant_set and to_path and to_path not in relevant_set:
            dependencies.append(_edge_payload(edge))

        if to_path in relevant_set and from_path and from_path not in relevant_set:
            dependents.append(_edge_payload(edge))

    return {
        "dependencies": _dedupe_edges(dependencies),
        "dependents": _dedupe_edges(dependents),
    }


def build_context_pack(graph: dict, task: str, routes_data: dict | None = None) -> str:
    """Build a compact deterministic Markdown context pack."""

    relevant_files = rank_relevant_files(graph, task, limit=MAX_RELEVANT_FILES)
    relevant_paths = [
        item["file"].get("path", "")
        for item in relevant_files
    ]
    task_terms = extract_task_terms(task)
    routes = _rank_relevant_routes(graph, task_terms, relevant_paths, routes_data)
    neighbors = find_dependency_neighbors(graph, relevant_paths)
    verification = _suggest_verification(graph, relevant_files)
    related_tests = _collect_related_tests(graph, relevant_files)

    lines = []
    lines.append("# Strata Context Pack")
    lines.append("")
    lines.append("## Task")
    lines.append("")
    lines.append(task)
    lines.append("")
    lines.append("## How This Pack Was Built")
    lines.append("")
    lines.append(
        "- Deterministic keyword matching was used; Strata is not an LLM and the task is only a hint."
    )
    lines.append(
        "- Files were scored against paths, symbols, imports, and backend route data."
    )
    lines.append(
        "- Test suggestions were reused from `test_mapper.py` when available, with a conservative fallback."
    )
    lines.append("")
    lines.append("## Likely Relevant Files")
    lines.append("")

    if relevant_files:
        for index, item in enumerate(relevant_files, start=1):
            file_info = item["file"]
            path = file_info.get("path", "")
            score = item["score"]
            matched_terms = item.get("matched_terms", [])

            lines.append(f"{index}. `{path}`")
            lines.append(f"   - Score: `{score}`")

            if matched_terms:
                matched_text = ", ".join(f"`{term}`" for term in matched_terms)
                lines.append(f"   - Matched terms: {matched_text}")
            else:
                lines.append("   - Matched terms: none")
    else:
        lines.append("No strong file matches found.")
        lines.append("")
        lines.append("## Repository Summary")
        lines.append("")
        lines.append(f"- Files scanned: `{len(graph.get('files', []))}`")
        lines.append(f"- Dependency edges: `{len(graph.get('edges', []))}`")
        lines.append(f"- Backend routes: `{len(_collect_all_routes(graph, routes_data))}`")

    lines.append("")
    lines.append("## Relevant Backend Routes")
    lines.append("")

    if routes:
        for route in routes:
            route_label = f"{route.get('method', '')} {route.get('path', '')}".strip()
            location = route.get("file", "")
            line = route.get("line", "")
            source = route.get("source", "")

            if line != "":
                location = f"{location}:{line}"

            lines.append(f"- `{route_label}` -> `{location}`")

            if source:
                lines.append(f"  - Source: `{source}`")
    else:
        lines.append("No relevant backend routes found.")

    lines.append("")
    lines.append("## Dependency Neighbors")
    lines.append("")
    lines.append("### Dependencies")

    if neighbors["dependencies"]:
        for edge in neighbors["dependencies"]:
            lines.append(
                f"- `{edge['from']}` -> `{edge['to']}` via `{edge['import']}`"
            )
    else:
        lines.append("- none")

    lines.append("")
    lines.append("### Dependents")

    if neighbors["dependents"]:
        for edge in neighbors["dependents"]:
            lines.append(
                f"- `{edge['from']}` -> `{edge['to']}` via `{edge['import']}`"
            )
    else:
        lines.append("- none")

    lines.append("")
    lines.append("## Likely Related Tests")
    lines.append("")

    if related_tests:
        for path in related_tests:
            lines.append(f"- `{path}`")
    else:
        lines.append("- none identified yet")

    lines.append("")
    lines.append("## Suggested Verification")
    lines.append("")

    for command in verification:
        lines.append(f"- `{command}`")

    lines.append("")
    lines.append("## AI Editing Instructions")
    lines.append("")
    lines.append("- Focus on likely relevant files first.")
    lines.append("- Do not rewrite unrelated files.")
    lines.append("- Preserve public behavior unless the task requires changing it.")
    lines.append("- After editing, run suggested verification.")
    lines.append("- Treat this pack as deterministic repo context, not as an LLM plan.")

    return "\n".join(lines).rstrip() + "\n"


def _collect_all_routes(graph: dict, routes_data: dict | None) -> list[dict]:
    if routes_data and isinstance(routes_data, dict):
        routes = routes_data.get("routes", [])

        if isinstance(routes, list):
            collected = []

            for route in routes:
                if not isinstance(route, dict):
                    continue

                collected.append(
                    {
                        "method": str(route.get("method", "")),
                        "path": str(route.get("path", "")),
                        "file": str(route.get("file", "")),
                        "line": route.get("line", ""),
                        "source": str(route.get("source", "")),
                    }
                )

            if collected:
                return sorted(
                    collected,
                    key=lambda item: (
                        item.get("path", ""),
                        item.get("method", ""),
                        item.get("file", ""),
                        str(item.get("line", "")),
                    ),
                )

    collected = []

    for file_info in graph.get("files", []):
        file_path = str(file_info.get("path", ""))

        for route in file_info.get("routes", []):
            if not isinstance(route, dict):
                continue

            collected.append(
                {
                    "method": str(route.get("method", "")),
                    "path": str(route.get("path", "")),
                    "file": file_path,
                    "line": route.get("line", ""),
                    "source": str(route.get("source", "")),
                }
            )

    return sorted(
        collected,
        key=lambda item: (
            item.get("path", ""),
            item.get("method", ""),
            item.get("file", ""),
            str(item.get("line", "")),
        ),
    )


def _rank_relevant_routes(
    graph: dict,
    task_terms: list[str],
    relevant_paths: list[str],
    routes_data: dict | None,
) -> list[dict]:
    relevant_set = {_normalize_path(path) for path in relevant_paths if path}
    routes = _collect_all_routes(graph, routes_data)
    scored_routes = []

    for route in routes:
        route_file = _normalize_path(route.get("file", ""))
        route_path = _normalize_text(route.get("path", ""))
        route_method = _normalize_text(route.get("method", ""))
        route_source = _normalize_text(route.get("source", ""))
        score = 0

        if route_file in relevant_set:
            score += 10

        for term in task_terms:
            if term in route_path:
                score += 4

            if term in route_file:
                score += 2

            if term == route_method:
                score += 5

            if term in route_source:
                score += 1

        if score > 0:
            scored_routes.append(
                {
                    "method": route.get("method", ""),
                    "path": route.get("path", ""),
                    "file": route.get("file", ""),
                    "line": route.get("line", ""),
                    "source": route.get("source", ""),
                    "score": score,
                }
            )

    scored_routes.sort(
        key=lambda item: (
            -item["score"],
            item.get("path", ""),
            item.get("method", ""),
            item.get("file", ""),
            str(item.get("line", "")),
        )
    )

    return scored_routes[:MAX_RELEVANT_ROUTES]


def _collect_related_tests(graph: dict, relevant_files: list[dict]) -> list[str]:
    related_tests = []

    for item in relevant_files:
        file_info = item.get("file", {})
        path = file_info.get("path", "")

        if not path:
            continue

        if suggest_tests_for_file is not None:
            suggestion = suggest_tests_for_file(graph, path)
            related_tests.extend(
                candidate
                for candidate in suggestion.get("related_test_files", [])
                if _normalize_path(candidate) != _normalize_path(path)
            )

    if not related_tests:
        related_tests.extend(_fallback_related_test_files(graph, relevant_files))

    filtered = [
        candidate
        for candidate in _dedupe(related_tests)
        if _normalize_path(candidate) not in {
            _normalize_path(item.get("file", {}).get("path", ""))
            for item in relevant_files
        }
    ]

    return _limit_unique(sorted(filtered), MAX_RELATED_TEST_FILES)


def _suggest_verification(graph: dict, relevant_files: list[dict]) -> list[str]:
    commands = []

    for item in relevant_files:
        file_info = item.get("file", {})
        path = file_info.get("path", "")

        if not path:
            continue

        if suggest_tests_for_file is not None:
            suggestion = suggest_tests_for_file(graph, path)
            commands.extend(suggestion.get("recommended_commands", []))

    if not commands:
        commands = ["py tests.py", "py tests\\run.py"]
    else:
        commands.append("py tests\\run.py")

    return _limit_unique(commands, MAX_VERIFICATION_COMMANDS)


def _fallback_related_test_files(graph: dict, relevant_files: list[dict]) -> list[str]:
    candidates = []

    for item in relevant_files:
        file_info = item.get("file", {})
        target_path = file_info.get("path", "")

        if not target_path:
            continue

        target_name = os.path.basename(target_path)
        target_stem = _file_stem(target_name)

        for candidate in graph.get("files", []):
            path = candidate.get("path", "")
            normalized_path = _normalize_path(path)
            basename = os.path.basename(normalized_path)
            stem = _file_stem(basename)

            if not _is_test_file(normalized_path, basename):
                continue

            if stem == f"test_{target_stem}":
                candidates.append(path)
                continue

            if target_stem in stem:
                candidates.append(path)
                continue

    return candidates


def _collect_symbol_names(file_info: dict) -> list[str]:
    names = []

    for key in ("classes", "functions", "interfaces", "types", "enums", "exports"):
        for item in file_info.get(key, []):
            if isinstance(item, dict):
                name = item.get("name", "")
            else:
                name = item

            normalized = _normalize_text(str(name))

            if normalized:
                names.append(normalized)

    return _dedupe(names)


def _collect_import_strings(file_info: dict) -> list[str]:
    imports = []

    for key in ("imports", "external_imports", "unresolved_imports"):
        for value in file_info.get(key, []):
            normalized = _normalize_text(str(value))

            if normalized:
                imports.append(normalized)

    for detail in file_info.get("unresolved_import_details", []):
        if isinstance(detail, dict):
            name = detail.get("name", "")
            normalized = _normalize_text(str(name))

            if normalized:
                imports.append(normalized)

    return _dedupe(imports)


def _collect_route_strings(file_info: dict) -> list[str]:
    route_texts = []

    for route in file_info.get("routes", []):
        if not isinstance(route, dict):
            continue

        route_method = _normalize_text(str(route.get("method", "")))
        route_path = _normalize_text(str(route.get("path", "")))
        route_source = _normalize_text(str(route.get("source", "")))

        for value in (route_method, route_path, route_source):
            if value:
                route_texts.append(value)

    return _dedupe(route_texts)


def _matched_terms_for_file(file_info: dict, task_terms: list[str]) -> list[str]:
    matches = []
    path = _normalize_text(str(file_info.get("path", "")))
    basename = _normalize_text(os.path.basename(str(file_info.get("path", ""))))
    symbols = _collect_symbol_names(file_info)
    imports = _collect_import_strings(file_info)
    routes = _collect_route_strings(file_info)

    for term in task_terms:
        if term in path or term in basename:
            matches.append(term)
            continue

        if any(term in symbol for symbol in symbols):
            matches.append(term)
            continue

        if any(term in import_name for import_name in imports):
            matches.append(term)
            continue

        if any(term in route_text for route_text in routes):
            matches.append(term)

    return _dedupe(matches)


def _edge_payload(edge: dict) -> dict:
    return {
        "from": str(edge.get("from", "")),
        "to": str(edge.get("to", "")),
        "import": str(edge.get("import", "")),
        "type": str(edge.get("type", "")),
    }


def _dedupe_edges(edges: list[dict]) -> list[dict]:
    seen = set()
    result = []

    for edge in sorted(
        edges,
        key=lambda item: (
            item.get("from", ""),
            item.get("to", ""),
            item.get("import", ""),
            item.get("type", ""),
        ),
    ):
        key = (
            edge.get("from", ""),
            edge.get("to", ""),
            edge.get("import", ""),
            edge.get("type", ""),
        )

        if key in seen:
            continue

        seen.add(key)
        result.append(edge)

    return result


def _normalize_text(text: str) -> str:
    return (
        str(text)
        .replace("\\", "/")
        .replace("_", " ")
        .replace("-", " ")
        .lower()
    )


def _normalize_path(path: str) -> str:
    return str(path).replace("\\", "/").strip()


def _file_stem(filename: str) -> str:
    if filename.endswith(".py"):
        return filename[:-3]

    return filename


def _is_test_file(normalized_path: str, basename: str) -> bool:
    return normalized_path.startswith("tests/") and basename.startswith("test_")


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []

    for value in values:
        if value in seen:
            continue

        seen.add(value)
        result.append(value)

    return result


def _limit_unique(values: list[str], limit: int) -> list[str]:
    return _dedupe(values)[:limit]
