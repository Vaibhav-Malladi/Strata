from __future__ import annotations

import os
import re


TASK_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "in", "into", "is", "it", "of", "on", "or", "the", "this", "to",
    "with", "add", "change", "create", "delete", "do", "edit", "fix",
    "improve", "implement", "make", "modify", "remove", "replace",
    "rewrite", "task", "update", "upgrade",
}

IDENTIFIER_STOP_WORDS = {
    "cjs", "css", "d", "gif", "html", "ico", "jpeg", "jpg", "js", "json",
    "less", "md", "mjs", "png", "py", "rb", "scss", "spec", "styl", "svg",
    "ts", "tsx", "txt", "yaml", "yml",
}

TASK_HINT_TERMS = {
    "frontend_ui": {
        "button", "card", "component", "dashboard", "form", "hook", "home",
        "landing", "navbar", "page", "profile", "screen", "ui", "view",
    },
    "backend_api": {
        "api", "controller", "endpoint", "request", "response", "route",
        "server",
    },
    "tests": {
        "fail", "failed", "failing", "spec", "test", "tests",
    },
    "data_model": {
        "database", "db", "migration", "model", "schema",
    },
    "styles": {
        "css", "layout", "less", "sass", "scss", "style", "styles", "styling",
    },
}

TASK_SYNONYMS = {
    "api": ("endpoint", "route"),
    "auth": ("login", "session", "token"),
    "button": ("click", "handler", "onclick"),
    "db": ("database",),
    "endpoint": ("api", "route"),
    "form": ("input", "submit", "validation"),
    "home": ("index", "landing"),
    "landing": ("home", "index"),
    "page": ("screen", "view"),
    "screen": ("page", "view"),
}


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


def extract_identifier_terms(text: str) -> list[str]:
    """Split a path or identifier into stable lowercase terms."""

    if not text:
        return []

    terms = []
    raw_text = str(text).replace("\\", "/")

    for fragment in re.split(r"[^A-Za-z0-9]+", raw_text):
        if not fragment:
            continue

        parts = re.findall(
            r"[A-Z]+(?=[A-Z][a-z]|[0-9]|$)|[A-Z]?[a-z]+|[0-9]+",
            fragment,
        )

        if not parts:
            parts = [fragment]

        for part in parts:
            term = part.lower()

            if len(term) <= 1:
                continue

            if term in IDENTIFIER_STOP_WORDS:
                continue

            terms.append(term)

    return _dedupe(terms)


def collect_file_terms(file_info: dict) -> list[str]:
    """Collect deterministic terms from a repository file description."""

    if not file_info:
        return []

    terms = []
    path = str(file_info.get("path", ""))

    if path:
        terms.extend(extract_identifier_terms(path))

    for key in ("language", "framework", "framework_hint", "framework_hints", "frameworks"):
        terms.extend(_extract_terms_from_value(file_info.get(key)))

    for key in (
        "classes",
        "functions",
        "interfaces",
        "types",
        "enums",
        "exports",
        "imports",
        "external_imports",
        "unresolved_imports",
    ):
        for item in file_info.get(key, []):
            terms.extend(_extract_terms_from_item(item))

    for detail in file_info.get("unresolved_import_details", []):
        terms.extend(_extract_terms_from_item(detail))

    for route in file_info.get("routes", []):
        if not isinstance(route, dict):
            continue

        terms.extend(extract_identifier_terms(route.get("method", "")))
        terms.extend(extract_identifier_terms(route.get("path", "")))
        terms.extend(extract_identifier_terms(route.get("source", "")))

    return _dedupe([term for term in terms if term])


def detect_file_roles(file_info: dict) -> list[str]:
    """Conservatively infer file roles from path and symbols."""

    if not file_info:
        return []

    path = _normalize_path(file_info.get("path", ""))
    if not path:
        return []

    basename = os.path.basename(path)
    stem = _file_stem(basename)
    path_terms = set(extract_identifier_terms(path))
    basename_terms = set(extract_identifier_terms(basename))
    stem_terms = set(extract_identifier_terms(stem))
    normalized_path = path.lower()
    roles = []

    def add(role: str) -> None:
        if role not in roles:
            roles.append(role)

    if _is_test_file(normalized_path, basename):
        add("test")

    if normalized_path.endswith(
        (".css", ".scss", ".sass", ".less", ".styl")
    ) or {"style", "styles"} & path_terms:
        add("style")

    if {"middleware"} & (path_terms | basename_terms | stem_terms):
        add("middleware")

    if {"controller"} & (path_terms | basename_terms | stem_terms):
        add("controller")

    if {"service"} & (path_terms | basename_terms | stem_terms):
        add("service")

    if {"model", "schema", "entity", "entities", "migration", "migrations"} & (
        path_terms | basename_terms | stem_terms
    ):
        add("model")

    if (
        "config" in path_terms
        or "config" in basename_terms
        or normalized_path.endswith(
            (
                ".config.js",
                ".config.jsx",
                ".config.ts",
                ".config.tsx",
                ".config.py",
                ".config.json",
            )
        )
    ):
        add("config")

    if file_info.get("routes") or {"route", "routes"} & (
        path_terms | basename_terms | stem_terms
    ):
        add("route")

    if _looks_like_page_file(path, basename, path_terms, basename_terms, stem_terms):
        add("page")

    if _looks_like_component_file(
        path, basename, path_terms, basename_terms, stem_terms
    ):
        add("component")

    if stem.startswith("use") and len(stem) > 3 and path.lower().endswith(
        (".js", ".jsx", ".ts", ".tsx")
    ):
        add("hook")

    return roles


def detect_task_hints(task: str) -> dict:
    """Detect broad task hints that can steer ranking."""

    task_terms = set(extract_task_terms(task))
    task_text = _normalize_text(task)

    def matches(category: str) -> bool:
        return bool(TASK_HINT_TERMS[category] & task_terms)

    frontend = matches("frontend_ui")
    backend = matches("backend_api")
    tests = matches("tests") or "failing test" in task_text
    data_model = matches("data_model")
    styles = matches("styles")

    return {
        "frontend_ui": frontend,
        "backend_api": backend,
        "tests": tests,
        "data_model": data_model,
        "styles": styles,
    }


def score_file_for_task(
    file_info: dict,
    task_terms: list[str],
    task_text: str = "",
    task_hints: dict | None = None,
) -> int:
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
    file_terms = collect_file_terms(file_info)
    file_term_text = " ".join(file_terms)
    expanded_task_terms = expand_task_terms(task_terms)
    task_phrases = extract_task_phrases(task_terms)
    roles = detect_file_roles(file_info)
    hints = task_hints if task_hints is not None else detect_task_hints(task_text)

    for term in expanded_task_terms:
        if term in basename_text:
            score += 6
        elif term in path_text:
            score += 4

        if term in file_terms:
            score += 3

        if any(term in symbol for symbol in symbols):
            score += 2

        if any(term in import_name for import_name in imports):
            score += 1

        if any(term in route_text for route_text in routes):
            score += 3

    for phrase in task_phrases:
        if phrase in file_term_text:
            score += 4 + len(phrase.split())

        compact_phrase = phrase.replace(" ", "")
        if any(
            phrase in text or compact_phrase in text.replace(" ", "")
            for text in [path_text, basename_text, *routes]
        ):
            score += 5

    shared_terms = [term for term in expanded_task_terms if term in file_terms]
    if len(shared_terms) >= 2:
        score += len(shared_terms) * 2
    elif shared_terms:
        score += 1

    direct_shared_terms = [term for term in task_terms if term in file_terms]
    if direct_shared_terms:
        score += len(direct_shared_terms) * 4

    if "page" in roles and hints.get("frontend_ui"):
        score += 6

    if "component" in roles and hints.get("frontend_ui"):
        score += 3

    if "hook" in roles and ("hook" in task_terms or hints.get("frontend_ui")):
        score += 7

    if "route" in roles and hints.get("backend_api"):
        score += 7

    if "controller" in roles and hints.get("backend_api"):
        score += 5

    if "service" in roles and hints.get("backend_api"):
        score += 4

    if "test" in roles and hints.get("tests"):
        score += 6

    if "style" in roles and hints.get("styles"):
        score += 6

    if "model" in roles and hints.get("data_model"):
        score += 5

    if "config" in roles and hints.get("data_model"):
        score += 2

    if "test" in roles and not hints.get("tests"):
        score = max(score - 15, 1)

    if _is_framework_support_file(path) and not (hints.get("tests") or hints.get("styles")):
        score = max(score - 12, 1)

    return score


def expand_task_terms(task_terms: list[str]) -> list[str]:
    expanded = []

    for term in task_terms:
        expanded.append(term)
        expanded.extend(TASK_SYNONYMS.get(term, ()))

    return _dedupe(expanded)


def extract_task_phrases(task_terms: list[str]) -> list[str]:
    phrases = []

    for size in (2, 3):
        if len(task_terms) < size:
            continue

        for index in range(len(task_terms) - size + 1):
            phrase = " ".join(task_terms[index : index + size])
            phrases.append(phrase)

    return _dedupe(phrases)


def score_confidence(
    score: int,
    matched_terms: list[str],
    file_roles: list[str] | None = None,
) -> str:
    direct_matches = len(matched_terms)
    roles = set(file_roles or [])

    if direct_matches >= 2:
        return "high"

    if direct_matches >= 1:
        return "medium"

    if score >= 12 and roles.intersection({"page", "component", "hook", "route", "controller", "service", "model"}):
        return "medium"

    return "low"


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
    return os.path.splitext(filename)[0]


def _is_test_file(normalized_path: str, basename: str) -> bool:
    basename_stem = _file_stem(basename).lower()
    return (
        normalized_path.startswith("tests/")
        or "/tests/" in normalized_path
        or basename_stem.startswith("test_")
        or basename_stem.endswith(".test")
        or basename_stem.endswith(".spec")
        or ".test." in normalized_path
        or ".spec." in normalized_path
    )


def _is_framework_support_file(path: str) -> bool:
    normalized = _normalize_path(path).lower()
    return normalized.endswith(
        (
            ".component.html",
            ".component.css",
            ".component.scss",
            ".component.sass",
            ".component.less",
            ".module.css",
            ".module.scss",
            ".module.sass",
            ".module.less",
        )
    )


def _extract_terms_from_value(value) -> list[str]:
    if value is None:
        return []

    if isinstance(value, dict):
        terms = []

        for item in value.values():
            terms.extend(_extract_terms_from_value(item))

        return terms

    if isinstance(value, (list, tuple, set)):
        terms = []

        for item in value:
            terms.extend(_extract_terms_from_value(item))

        return terms

    return extract_identifier_terms(str(value))


def _extract_terms_from_item(item) -> list[str]:
    if isinstance(item, dict):
        terms = []

        for key in ("name", "path", "module", "value", "source", "framework"):
            if key in item:
                terms.extend(extract_identifier_terms(str(item.get(key, ""))))

        if not terms:
            terms.extend(_extract_terms_from_value(item))

        return terms

    return extract_identifier_terms(str(item))


def _looks_like_page_file(
    path: str,
    basename: str,
    path_terms: set[str],
    basename_terms: set[str],
    stem_terms: set[str],
) -> bool:
    basename_stem = _file_stem(basename).lower()

    if "pages" in path_terms and (
        {"page", "index", "home", "landing"} & (basename_terms | stem_terms)
    ):
        return True

    if "app" in path_terms and basename_stem in {"page", "index"}:
        return True

    if basename_stem in {"page", "index"} and {"app", "pages"} & path_terms:
        return True

    if "pages" in path_terms and (
        {"page", "home", "landing"} & (basename_terms | stem_terms)
    ):
        return True

    return False


def _looks_like_component_file(
    path: str,
    basename: str,
    path_terms: set[str],
    basename_terms: set[str],
    stem_terms: set[str],
) -> bool:
    basename_stem = _file_stem(basename).lower()

    if {"component", "components", "ui"} & path_terms:
        return True

    if "component" in basename_terms or "component" in stem_terms:
        return True

    if basename_stem.endswith("component"):
        return True

    if path.lower().endswith((".jsx", ".tsx")) and _file_stem(basename)[:1].isupper():
        return True

    return False


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


_expand_task_terms = expand_task_terms
_task_phrases = extract_task_phrases
