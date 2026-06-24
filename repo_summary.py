from __future__ import annotations

from collections import Counter


MAX_TOP_FILES = 5


def summarize_graph(graph: dict) -> dict:
    graph_data = graph if isinstance(graph, dict) else {}
    files = _as_list(graph_data.get("files"))
    edges = _as_list(graph_data.get("edges"))

    summary = {
        "languages": _count_file_values(files, "language"),
        "frameworks": _count_frameworks(files),
        "symbols": {
            "functions": 0,
            "classes": 0,
            "components": 0,
            "hooks": 0,
            "angular_components": 0,
            "angular_services": 0,
            "angular_modules": 0,
            "angular_routes": 0,
        },
        "imports": {
            "resolved_edges": len(edges),
            "unresolved": 0,
            "external": 0,
            "path_alias": 0,
            "workspace": 0,
        },
        "top_files": [],
    }

    symbol_counts = summary["symbols"]
    import_counts = summary["imports"]
    edge_import_index = _build_edge_import_index(edges)

    for file_info in files:
        if not isinstance(file_info, dict):
            continue

        symbol_counts["functions"] += _count_items(file_info.get("functions"))
        symbol_counts["classes"] += _count_items(file_info.get("classes"))
        symbol_counts["components"] += _count_items(file_info.get("components"))
        symbol_counts["hooks"] += _count_items(file_info.get("hooks"))

        angular = file_info.get("angular", {})
        if isinstance(angular, dict):
            symbol_counts["angular_components"] += _count_items(angular.get("components"))
            symbol_counts["angular_services"] += _count_items(angular.get("services"))
            symbol_counts["angular_modules"] += _count_items(angular.get("modules"))
            symbol_counts["angular_routes"] += _count_items(angular.get("routes"))

        import_counts["unresolved"] += _count_items(file_info.get("unresolved_imports"))
        import_counts["external"] += _count_items(file_info.get("external_imports"))
        import_counts["path_alias"] += _count_path_alias_imports(file_info)
        import_counts["workspace"] += _count_workspace_imports(file_info, edge_import_index)

    summary["top_files"] = _build_top_files(files)

    return {
        "languages": dict(summary["languages"]),
        "frameworks": dict(summary["frameworks"]),
        "symbols": dict(summary["symbols"]),
        "imports": dict(summary["imports"]),
        "top_files": [dict(item) for item in summary["top_files"]],
    }


def format_counts(counts: dict) -> str:
    if not isinstance(counts, dict) or not counts:
        return "None"

    parts = []
    for key, value in counts.items():
        label = _display_name(str(key))
        parts.append(f"{label} {value}")

    return ", ".join(parts)


def build_repo_intelligence_rows(summary: dict) -> list[tuple[str, object]]:
    if not isinstance(summary, dict):
        summary = {}

    languages = summary.get("languages", {})
    frameworks = summary.get("frameworks", {})
    symbols = summary.get("symbols", {})
    imports = summary.get("imports", {})

    rows: list[tuple[str, object]] = [
        ("Languages", format_counts(languages)),
    ]

    if frameworks:
        rows.append(("Frameworks", format_counts(frameworks)))

    component_count = _count_value(symbols, "components")
    hook_count = _count_value(symbols, "hooks")
    angular_component_count = _count_value(symbols, "angular_components")
    angular_service_count = _count_value(symbols, "angular_services")
    angular_module_count = _count_value(symbols, "angular_modules")
    angular_route_count = _count_value(symbols, "angular_routes")

    if component_count:
        rows.append(("Components", component_count))

    if hook_count:
        rows.append(("Hooks", hook_count))

    if angular_component_count:
        rows.append(("Angular components", angular_component_count))

    if angular_service_count:
        rows.append(("Angular services", angular_service_count))

    if angular_module_count:
        rows.append(("Angular modules", angular_module_count))

    if angular_route_count:
        rows.append(("Angular routes", angular_route_count))

    rows.extend(
        [
            ("Import edges", _count_value(imports, "resolved_edges")),
            ("Unresolved imports", _count_value(imports, "unresolved")),
        ]
    )

    return rows


def collect_framework_names(summary: dict) -> list[str]:
    frameworks = summary.get("frameworks", {}) if isinstance(summary, dict) else {}

    if not isinstance(frameworks, dict):
        return []

    names = []
    for key, value in frameworks.items():
        if _safe_int(value) <= 0:
            continue
        names.append(_display_name(str(key)))

    return names


def collect_frontend_symbols(graph: dict, limit: int = 6) -> list[str]:
    graph_data = graph if isinstance(graph, dict) else {}
    files = _as_list(graph_data.get("files"))
    names = []
    seen = set()

    for file_info in files:
        if not isinstance(file_info, dict):
            continue

        if not _is_frontend_file(file_info):
            continue

        for candidate in _frontend_symbol_candidates(file_info):
            if candidate in seen:
                continue

            seen.add(candidate)
            names.append(candidate)

            if len(names) >= limit:
                return names

    return names


def _build_top_files(files: list) -> list[dict]:
    scored = []

    for file_info in files:
        if not isinstance(file_info, dict):
            continue

        path = str(file_info.get("path", "")).strip()
        if not path:
            continue

        language = str(file_info.get("language", "")).strip().lower()
        frameworks = _file_frameworks(file_info)
        symbol_count = _count_items(file_info.get("functions")) + _count_items(file_info.get("classes"))
        symbol_count += _count_items(file_info.get("components")) + _count_items(file_info.get("hooks"))

        angular = file_info.get("angular", {})
        if isinstance(angular, dict):
            symbol_count += _count_items(angular.get("components"))
            symbol_count += _count_items(angular.get("services"))
            symbol_count += _count_items(angular.get("modules"))
            symbol_count += _count_items(angular.get("routes"))

        import_count = _count_items(file_info.get("imports"))
        unresolved_count = _count_items(file_info.get("unresolved_imports"))
        external_count = _count_items(file_info.get("external_imports"))
        score = symbol_count * 4 + len(frameworks) * 3 + import_count + unresolved_count + external_count

        scored.append(
            {
                "path": path,
                "language": language,
                "frameworks": frameworks,
                "score": score,
                "symbols": symbol_count,
                "imports": import_count,
                "unresolved_imports": unresolved_count,
            }
        )

    scored.sort(
        key=lambda item: (
            -item["score"],
            item["path"],
        )
    )

    return scored[:MAX_TOP_FILES]


def _build_edge_import_index(edges: list) -> dict[str, set[str]]:
    index: dict[str, set[str]] = {}

    for edge in edges:
        if not isinstance(edge, dict):
            continue

        from_path = str(edge.get("from", "")).strip()
        import_name = str(edge.get("import", "")).strip()

        if not from_path or not import_name:
            continue

        index.setdefault(from_path, set()).add(import_name)

    return index


def _count_file_values(files: list, key: str) -> dict:
    counts = Counter()

    for file_info in files:
        if not isinstance(file_info, dict):
            continue

        value = file_info.get(key)
        if not value:
            continue

        if isinstance(value, (list, tuple, set)):
            for item in value:
                text = str(item).strip().lower()
                if text:
                    counts[text] += 1
            continue

        text = str(value).strip().lower()
        if text:
            counts[text] += 1

    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _count_frameworks(files: list) -> dict:
    counts = Counter()

    for file_info in files:
        if not isinstance(file_info, dict):
            continue

        for framework in _file_frameworks(file_info):
            counts[framework] += 1

    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _file_frameworks(file_info: dict) -> list[str]:
    frameworks = []
    seen = set()

    raw_frameworks = file_info.get("frameworks", [])
    if isinstance(raw_frameworks, (list, tuple, set)):
        values = raw_frameworks
    elif raw_frameworks:
        values = [raw_frameworks]
    else:
        values = []

    for value in values:
        text = str(value).strip().lower()
        if text and text not in seen:
            seen.add(text)
            frameworks.append(text)

    fallback = str(file_info.get("framework", "")).strip().lower()
    if fallback and fallback not in seen:
        frameworks.append(fallback)

    return frameworks


def _count_items(value: object) -> int:
    if isinstance(value, list):
        return len(value)

    if isinstance(value, (tuple, set)):
        return len(value)

    return 1 if value else 0


def _count_path_alias_imports(file_info: dict) -> int:
    count = 0
    imports = _as_list(file_info.get("imports"))
    if not imports:
        return 0

    external = {_normalize_text(item) for item in _as_list(file_info.get("external_imports"))}
    unresolved = {_normalize_text(item) for item in _as_list(file_info.get("unresolved_imports"))}
    path_alias = {_normalize_text(item) for item in _as_list(file_info.get("path_alias_imports"))}

    for import_name in imports:
        normalized = _normalize_text(import_name)
        if not normalized:
            continue

        if normalized in external or normalized in unresolved:
            continue

        if normalized in path_alias or _looks_like_path_alias(normalized):
            count += 1

    return count


def _count_workspace_imports(file_info: dict, edge_import_index: dict[str, set[str]]) -> int:
    language = _normalize_text(file_info.get("language"))
    if language not in {"javascript", "typescript"}:
        return 0

    path = str(file_info.get("path", "")).strip()
    if not path:
        return 0

    imports = _as_list(file_info.get("imports"))
    if not imports:
        return 0

    external = {_normalize_text(item) for item in _as_list(file_info.get("external_imports"))}
    unresolved = {_normalize_text(item) for item in _as_list(file_info.get("unresolved_imports"))}
    path_alias = {_normalize_text(item) for item in _as_list(file_info.get("path_alias_imports"))}
    edge_imports = edge_import_index.get(path, set())
    count = 0

    for import_name in imports:
        normalized = _normalize_text(import_name)
        if not normalized:
            continue

        if normalized in external or normalized in unresolved or normalized in path_alias:
            continue

        if _looks_like_relative_import(normalized) or _looks_like_path_alias(normalized):
            continue

        if normalized in edge_imports:
            count += 1

    return count


def _is_frontend_file(file_info: dict) -> bool:
    framework_values = {framework for framework in _file_frameworks(file_info) if framework}
    if framework_values.intersection({"react", "angular"}):
        return True

    if _count_items(file_info.get("components")) or _count_items(file_info.get("hooks")):
        return True

    angular = file_info.get("angular", {})
    if isinstance(angular, dict):
        for key in ("components", "services", "modules", "routes"):
            if _count_items(angular.get(key)):
                return True

    return False


def _frontend_symbol_candidates(file_info: dict) -> list[str]:
    names = []
    seen = set()

    for item in _as_list(file_info.get("components")):
        name = _extract_name(item)
        if name and name not in seen:
            seen.add(name)
            names.append(name)

    for item in _as_list(file_info.get("hooks")):
        name = _extract_name(item)
        if name and name not in seen:
            seen.add(name)
            names.append(name)

    angular = file_info.get("angular", {})
    if isinstance(angular, dict):
        for key in ("components", "services", "modules", "routes"):
            for item in _as_list(angular.get(key)):
                name = _extract_name(item)
                if name and name not in seen:
                    seen.add(name)
                    names.append(name)

    for item in _as_list(file_info.get("classes")):
        name = _extract_name(item)
        if name and name not in seen:
            seen.add(name)
            names.append(name)

    return names


def _extract_name(item: object) -> str:
    if isinstance(item, dict):
        return str(item.get("name", "")).strip()

    return str(item).strip()


def _display_name(value: str) -> str:
    mapping = {
        "python": "Python",
        "javascript": "JavaScript",
        "typescript": "TypeScript",
        "react": "React",
        "angular": "Angular",
        "functions": "Functions",
        "classes": "Classes",
        "components": "Components",
        "hooks": "Hooks",
        "angular_components": "Angular components",
        "angular_services": "Angular services",
        "angular_modules": "Angular modules",
        "angular_routes": "Angular routes",
        "resolved_edges": "Resolved edges",
        "unresolved": "Unresolved",
        "external": "External",
        "path_alias": "Path alias",
        "workspace": "Workspace",
    }

    if value in mapping:
        return mapping[value]

    return value.replace("_", " ").title()


def _normalize_text(value: object) -> str:
    return str(value).strip().lower()


def _looks_like_relative_import(import_name: str) -> bool:
    return import_name.startswith("./") or import_name.startswith("../")


def _looks_like_path_alias(import_name: str) -> bool:
    return import_name.startswith("@/") or import_name.startswith("~/")


def _as_list(value: object) -> list:
    if isinstance(value, list):
        return list(value)

    if isinstance(value, tuple):
        return list(value)

    if isinstance(value, set):
        return list(value)

    if value is None:
        return []

    return [value]


def _safe_int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _count_value(mapping: dict, key: str) -> int:
    if not isinstance(mapping, dict):
        return 0

    return _safe_int(mapping.get(key, 0))
