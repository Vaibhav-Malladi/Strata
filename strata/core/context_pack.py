from __future__ import annotations

import os

from secret_redaction import redact_text

try:
    from strata.core.test_mapper import suggest_tests_for_file
except Exception:  # pragma: no cover - optional helper fallback
    suggest_tests_for_file = None

from strata.core.context_matching import (
    TASK_HINT_TERMS,
    TASK_STOP_WORDS,
    TASK_SYNONYMS,
    collect_file_terms,
    detect_file_roles,
    detect_task_hints,
    expand_task_terms,
    extract_identifier_terms,
    extract_task_phrases,
    extract_task_terms,
    score_confidence,
    score_file_for_task,
    _collect_import_strings,
    _collect_route_strings,
    _collect_symbol_names,
    _dedupe,
    _file_stem,
    _is_test_file,
    _limit_unique,
    _matched_terms_for_file,
    _normalize_path,
    _normalize_text,
)
from strata.core.repo_summary import collect_frontend_symbols, collect_framework_names, summarize_graph
from strata.core.selected_context import build_selected_file_entries, build_selected_file_section
from strata.core.context_budget import (
    build_budget_report,
    build_change_boundary_section,
    build_context_budget_section,
    build_excluded_context_section,
    build_included_context_section,
    build_structured_intent_section,
)
from strata.core.test_mapping import build_test_hints_section
from strata.parsers.symbol_slicing import build_symbol_hints_section, build_symbol_snippets_section
from strata.core.framework_hints import build_angular_hints_section, build_react_hints_section
from strata.parsers.javascript_project import build_javascript_project_hints_section
from typescript_project import (
    build_declaration_hints_section,
    build_typescript_project_hints_section,
)
from strata.core.execution_hints import build_execution_path_hints_section
from strata.core.verification_hints import build_verification_plan_section
from strata.utils.prompt_safety import UNTRUSTED_CONTENT_WARNING, wrap_repository_content


MAX_RELEVANT_FILES = 10
MAX_RELEVANT_ROUTES = 8
MAX_RELATED_TEST_FILES = 6
MAX_DEPENDENCY_NEIGHBORS = 8


def rank_relevant_files(
    graph: dict,
    task: str,
    limit: int = 10,
    selected_paths: list[str] | None = None,
) -> list[dict]:
    """Rank likely relevant files for a task."""

    task_terms = extract_task_terms(task)
    task_hints = detect_task_hints(task)
    selected_entries = build_selected_file_entries(graph, selected_paths or [])
    selected_paths_set = {
        _normalize_path(item["file"].get("path", ""))
        for item in selected_entries
    }
    scored_files = []

    for file_info in graph.get("files", []):
        score = score_file_for_task(file_info, task_terms, task, task_hints)

        normalized_path = _normalize_path(file_info.get("path", ""))
        if normalized_path in selected_paths_set:
            continue

        if score <= 0:
            continue

        file_roles = detect_file_roles(file_info)
        matched_terms = _matched_terms_for_file(file_info, task_terms)
        confidence = score_confidence(score, matched_terms, file_roles)
        included_by_hint_only = confidence == "low" and not matched_terms

        scored_files.append(
            {
                "file": file_info,
                "score": score,
                "matched_terms": matched_terms,
                "confidence": confidence,
                "is_test": "test" in file_roles,
                "included_by_hint_only": included_by_hint_only,
            }
        )

    scored_files.sort(
        key=lambda item: (
            1 if item["is_test"] and not task_hints.get("tests") else 0,
            -item["score"],
            item["file"].get("path", ""),
        )
    )

    task_ranked = [
        item
        for item in scored_files
        if item["confidence"] in {"high", "medium"}
        or item["matched_terms"]
    ]

    if selected_entries:
        fallback = task_ranked if task_ranked else scored_files[: min(limit, 3)]
        return (selected_entries + fallback)[:limit]

    if task_ranked:
        return task_ranked[:limit]

    return scored_files[: min(limit, 3)]


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


def build_context_pack(
    graph: dict,
    task: str,
    routes_data: dict | None = None,
    selected_paths: list[str] | None = None,
    budget_value: str | None = None,
    budget_report: dict | None = None,
) -> str:
    """Build a compact deterministic Markdown context pack."""

    task = redact_text(task)
    selected_paths = selected_paths or []
    if budget_report is None:
        budget_report = build_budget_report(
            graph,
            task,
            selected_paths=selected_paths,
            budget_value=budget_value,
            max_candidates=MAX_RELEVANT_FILES,
        )
    relevant_files = budget_report["included_entries"]
    relevant_paths = [item["file"].get("path", "") for item in relevant_files]
    task_terms = extract_task_terms(task)
    repo_summary = summarize_graph(graph)
    routes = _rank_relevant_routes(graph, task_terms, relevant_paths, routes_data)
    neighbors = find_dependency_neighbors(graph, relevant_paths)
    verification = list(budget_report.get("verification_plan", []) or [])
    related_tests = _collect_related_tests(graph, relevant_files)
    frontend_frameworks = collect_framework_names(repo_summary)
    frontend_source = (
        {
            "files": [
                item["file"]
                for item in relevant_files
                if isinstance(item, dict) and isinstance(item.get("file"), dict)
            ]
        }
        if relevant_files
        else graph
    )
    frontend_symbols = collect_frontend_symbols(frontend_source)

    if not frontend_symbols and frontend_source is not graph:
        frontend_symbols = collect_frontend_symbols(graph)

    lines = []
    lines.append("# Strata Context Pack")
    lines.append("")
    lines.append(UNTRUSTED_CONTENT_WARNING)
    lines.append("")
    lines.append("## Task")
    lines.append("")
    lines.append(task)
    lines.append("")
    repository_context_start = len(lines)
    lines.extend(build_selected_file_section(selected_paths))
    lines.extend(build_structured_intent_section(task))
    lines.extend(build_change_boundary_section(selected_paths, budget_report))
    lines.extend(build_context_budget_section(budget_report))
    lines.extend(build_included_context_section(budget_report))
    lines.extend(build_excluded_context_section(budget_report))
    lines.extend(build_symbol_hints_section(budget_report.get("symbol_hints")))
    lines.extend(build_symbol_snippets_section(budget_report.get("symbol_snippets")))
    lines.extend(build_test_hints_section(budget_report.get("test_hints")))
    lines.extend(build_typescript_project_hints_section(budget_report.get("typescript_project_hints")))
    lines.extend(build_javascript_project_hints_section(budget_report.get("javascript_project_hints")))
    lines.extend(build_declaration_hints_section(budget_report.get("declaration_hints")))
    lines.extend(build_react_hints_section(budget_report.get("react_hints")))
    lines.extend(build_angular_hints_section(budget_report.get("angular_hints")))
    lines.extend(build_execution_path_hints_section(budget_report.get("execution_path_hints")))
    if frontend_frameworks:
        lines.append("## Repository Intelligence")
        lines.append("")
        lines.append(f"Frameworks detected: {', '.join(frontend_frameworks)}")
        if frontend_symbols:
            lines.append(f"Relevant frontend symbols: {', '.join(frontend_symbols)}")
        lines.append("")
    lines.append("## How This Pack Was Built")
    lines.append("")
    lines.append(
        "- Deterministic repo matching was used; Strata is not an LLM and the task is only a hint."
    )
    lines.append(
        "- Task terms were matched against repository file paths, symbols, routes, and framework hints."
    )
    lines.append(
        "- Broad task hints such as frontend/backend/test/data can affect ranking."
    )
    lines.append(
        "- Dependency neighbors are included after the initial matching pass."
    )
    if selected_paths:
        lines.append("- User-selected files were anchored before scored matches.")
    lines.append("- This is deterministic repo context, not an LLM plan.")
    lines.append("- Test hints were derived conservatively from test filenames, imports, and function names.")
    lines.append("")
    lines.append("## Likely Relevant Files")
    lines.append("")

    if relevant_files:
        has_strong_match = any(item.get("confidence") in {"high", "medium"} for item in relevant_files)

        if not has_strong_match:
            lines.append(
                "Strata did not find strong direct file matches for this task. The files below are best-effort hints."
            )
            lines.append("")

        for index, item in enumerate(relevant_files, start=1):
            file_info = item["file"]
            path = file_info.get("path", "")
            score = item["score"]
            matched_terms = item.get("matched_terms", [])
            confidence = item.get("confidence", "low")

            lines.append(f"{index}. `{path}`")
            if item.get("selected_by_user"):
                lines.append("   - Selection: user-selected")
                lines.append(f"   - Score: `{score}`")
            else:
                lines.append(f"   - Score: `{score}`")
            lines.append(f"   - Confidence: `{confidence}`")

            if matched_terms:
                matched_text = ", ".join(f"`{term}`" for term in matched_terms)
                lines.append(f"   - Matched terms: {matched_text}")
            else:
                if item.get("included_by_hint_only"):
                    lines.append(
                        "   - Matched terms: none direct; included by broad task/file-role hints"
                    )
                else:
                    lines.append("   - Matched terms: none")
    else:
        lines.append("No strong file matches found.")
        lines.append(
            "The repository may not contain files that directly match this task. Results are best-effort deterministic matches."
        )
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

    dependency_edges = neighbors["dependencies"][:MAX_DEPENDENCY_NEIGHBORS]
    dependency_more = max(0, len(neighbors["dependencies"]) - MAX_DEPENDENCY_NEIGHBORS)

    if dependency_edges:
        for edge in dependency_edges:
            lines.append(
                f"- `{edge['from']}` -> `{edge['to']}` via `{edge['import']}`"
            )
        if dependency_more:
            lines.append(f"- ...and {dependency_more} more")
    else:
        lines.append("- none")

    lines.append("")
    lines.append("### Dependents")

    dependent_edges = neighbors["dependents"][:MAX_DEPENDENCY_NEIGHBORS]
    dependent_more = max(0, len(neighbors["dependents"]) - MAX_DEPENDENCY_NEIGHBORS)

    if dependent_edges:
        for edge in dependent_edges:
            lines.append(
                f"- `{edge['from']}` -> `{edge['to']}` via `{edge['import']}`"
            )
        if dependent_more:
            lines.append(f"- ...and {dependent_more} more")
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
    lines.extend(build_verification_plan_section(verification))
    repository_lines = lines[repository_context_start:]
    lines[repository_context_start:] = wrap_repository_content(repository_lines)
    lines.append("## AI Editing Instructions")
    lines.append("")
    if selected_paths:
        lines.append("- Treat user-selected files as primary anchors.")
    lines.append("- Focus on likely relevant files first.")
    lines.append("- Do not rewrite unrelated files.")
    lines.append("- Preserve public behavior unless the task requires changing it.")
    lines.append("- After editing, run suggested verification.")
    lines.append("- Treat this pack as deterministic repo context, not an LLM plan.")

    return redact_text("\n".join(lines).rstrip() + "\n")


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
