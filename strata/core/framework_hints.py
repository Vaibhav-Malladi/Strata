import re
from pathlib import Path

from strata.core.context_matching import (
    _normalize_path,
    expand_task_terms,
    extract_identifier_terms,
    extract_task_terms,
)


REACT_SOURCE_SUFFIXES = {".jsx", ".tsx", ".js", ".ts"}
REACT_STYLE_SUFFIXES = (
    ".module.css",
    ".module.scss",
    ".css",
    ".scss",
    ".sass",
    ".less",
)
TAILWIND_CONFIG_NAMES = {
    "tailwind.config.js",
    "tailwind.config.cjs",
    "tailwind.config.mjs",
    "tailwind.config.ts",
}
ANGULAR_HINT_LIMIT = 5
REACT_HINT_LIMIT = 4


def collect_react_hints(graph: dict, task: str, relevant_entries: list[dict]) -> list[dict]:
    """Describe compact React component/hook relationships."""

    task_terms = set(extract_task_terms(task))
    expanded_task_terms = set(expand_task_terms(list(task_terms)))
    all_files = {
        _normalize_path(str(file_info.get("path", ""))): file_info
        for file_info in (graph or {}).get("files", [])
        if isinstance(file_info, dict) and file_info.get("path")
    }
    all_paths = set(all_files)
    root = Path(str((graph or {}).get("root") or "."))
    tailwind_configured = any(Path(path).name.lower() in TAILWIND_CONFIG_NAMES for path in all_paths)
    if not tailwind_configured:
        tailwind_configured = any((root / name).is_file() for name in TAILWIND_CONFIG_NAMES)
    hints = []

    for entry in relevant_entries:
        file_info = entry.get("file") if isinstance(entry, dict) else entry
        if not isinstance(file_info, dict):
            continue

        path = _normalize_path(str(file_info.get("path", "")))
        basename = Path(path).stem
        if Path(path).suffix.lower() not in REACT_SOURCE_SUFFIXES or _is_test_or_spec(path):
            continue

        symbol_terms, symbol_names = _symbol_details(file_info)
        file_terms = set(extract_identifier_terms(path)) | symbol_terms
        is_hook = basename.lower().startswith("use") and len(basename) > 3
        is_component = (
            Path(path).suffix.lower() in {".jsx", ".tsx"}
            and basename[:1].isupper()
        )
        matched = sorted(task_terms & file_terms)
        if not matched or not (is_hook or is_component):
            continue

        hint = {
            "path": path,
            "kind": "hook" if is_hook else "component",
            "symbols": symbol_names[:3],
            "matched_terms": matched[:4],
            "confidence": "medium",
            "confidence_reason": "convention",
        }

        if is_component:
            tests = _react_family_tests(path, all_paths, root)
            styles = _react_family_styles(path, all_paths, root)
            if tests:
                hint["tests"] = tests
            if styles:
                hint["styles"] = styles

            tailwind_reason = _tailwind_reason(graph, path, tailwind_configured)
            if tailwind_reason:
                hint["styling"] = f"Tailwind (detected via {tailwind_reason})"

            hooks = _nearby_react_files(
                path,
                all_paths,
                expanded_task_terms,
                kind="hook",
            )
            helpers = _nearby_react_files(
                path,
                all_paths,
                expanded_task_terms,
                kind="helper",
            )
            if hooks:
                hint["hooks"] = hooks
            if helpers:
                hint["related"] = helpers

        hints.append(hint)

    nested_paths = {
        related_path
        for hint in hints
        if hint.get("kind") == "component"
        for key in ("hooks", "related")
        for related_path in hint.get(key, []) or []
    }
    compact_hints = [
        hint
        for hint in hints
        if not (hint.get("kind") == "hook" and hint.get("path") in nested_paths)
    ]
    return compact_hints[:REACT_HINT_LIMIT]


def build_react_hints_section(hints: list[dict] | None) -> list[str]:
    hints = list(hints or [])
    if not hints:
        return []
    lines = ["## React Hints", ""]
    for hint in hints:
        terms = ", ".join(f"`{term}`" for term in hint.get("matched_terms", []))
        matched = f"; matched {terms}" if terms else ""
        lines.append(
            f"- `{hint.get('path', '<unknown>')}` - {hint.get('kind', 'React file')}, "
            f"medium confidence (convention){matched}"
        )
        for key, label in (
            ("tests", "tests"),
            ("styles", "styles"),
            ("hooks", "hooks"),
            ("related", "related"),
        ):
            values = hint.get(key, []) or []
            if values:
                lines.append(f"  - {label}: {', '.join(f'`{value}`' for value in values)}")
        if hint.get("styling"):
            lines.append(f"  - styling: {hint['styling']}")
    lines.append("")
    return lines


def collect_angular_hints(
    graph: dict,
    relevant_entries: list[dict],
    task: str = "",
) -> list[dict]:
    """Find concise Angular component/service/guard/routing file relationships."""

    task_terms = set(extract_task_terms(task))
    all_paths = {
        _normalize_path(str(file_info.get("path", "")))
        for file_info in (graph or {}).get("files", [])
        if isinstance(file_info, dict) and file_info.get("path")
    }
    root = Path(str((graph or {}).get("root") or "."))
    relevant_paths = {
        _normalize_path(str((entry.get("file") or {}).get("path", "")))
        for entry in relevant_entries
        if isinstance(entry, dict)
    }
    hints = []

    for path in sorted(all_paths):
        if path.endswith(".component.ts") and _angular_family_relevant(path, relevant_paths):
            stem = path[: -len(".component.ts")]
            item = _angular_hint(path, "component", task_terms)
            template = _first_existing_relative(
                root,
                all_paths,
                [f"{stem}.component.html"],
            )
            if template:
                item["template"] = template
            styles = _existing_relative_paths(
                root,
                all_paths,
                [
                    f"{stem}.component.scss",
                    f"{stem}.component.css",
                    f"{stem}.component.sass",
                    f"{stem}.component.less",
                ],
            )
            if styles:
                item["styles"] = styles
            test = _first_existing_relative(
                root,
                all_paths,
                [f"{stem}.component.spec.ts"],
            )
            if test:
                item["tests"] = [test]
            hints.append(item)
        elif path.endswith(".service.ts") and not path.endswith(".service.spec.ts") and path in relevant_paths:
            hints.append(_angular_single_file_hint(path, "service", root, all_paths, ".service.ts", task_terms))
        elif path.endswith(".guard.ts") and not path.endswith(".guard.spec.ts") and path in relevant_paths:
            hints.append(_angular_single_file_hint(path, "guard", root, all_paths, ".guard.ts", task_terms))
        elif Path(path).name in {"app.routes.ts", "app-routing.module.ts"} and path in relevant_paths:
            hints.append(_angular_hint(path, "routing", task_terms))

    return hints[:ANGULAR_HINT_LIMIT]


def build_angular_hints_section(hints: list[dict] | None) -> list[str]:
    hints = list(hints or [])
    if not hints:
        return []
    lines = ["## Angular Hints", ""]
    for hint in hints:
        terms = ", ".join(f"`{term}`" for term in hint.get("matched_terms", []))
        matched = f"; matched {terms}" if terms else ""
        lines.append(
            f"- `{hint.get('path', '<unknown>')}` - {hint.get('kind', 'Angular file')}, "
            f"medium confidence (convention){matched}"
        )
        if hint.get("template"):
            lines.append(f"  - template: `{hint['template']}`")
        styles = hint.get("styles", []) or []
        if styles:
            lines.append(f"  - styles: {', '.join(f'`{style}`' for style in styles)}")
        tests = hint.get("tests", []) or []
        if tests:
            lines.append(f"  - tests: {', '.join(f'`{test}`' for test in tests)}")
    lines.append("")
    return lines


def _symbol_details(file_info: dict) -> tuple[set[str], list[str]]:
    terms = set()
    names = []
    for key in ("classes", "functions", "exports"):
        for item in file_info.get(key, []) or []:
            name = str(item.get("name", "")) if isinstance(item, dict) else str(item)
            if name:
                names.append(name)
                terms.update(extract_identifier_terms(name))
    return terms, names


def _is_test_or_spec(path: str) -> bool:
    lower = path.lower()
    return ".test." in lower or ".spec." in lower


def _react_family_tests(path: str, all_paths: set[str], root: Path) -> list[str]:
    parent = str(Path(path).parent).replace("\\", "/")
    stem = Path(path).stem
    candidates = [
        f"{parent}/{stem}.{marker}.{suffix}"
        for marker in ("test", "spec")
        for suffix in ("tsx", "jsx", "ts", "js")
    ]
    return _existing_relative_paths(root, all_paths, candidates)[:2]


def _react_family_styles(path: str, all_paths: set[str], root: Path) -> list[str]:
    base = str(Path(path).with_suffix("")).replace("\\", "/")
    return _existing_relative_paths(
        root,
        all_paths,
        [f"{base}{suffix}" for suffix in REACT_STYLE_SUFFIXES],
    )[:2]


def _tailwind_reason(graph: dict, path: str, configured: bool) -> str | None:
    root = Path(str((graph or {}).get("root") or "."))
    source_path = root / Path(path)
    try:
        source = source_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        source = ""

    class_value = re.search(
        r"\bclass(?:Name)?\s*=\s*(?:[\"'][^\"']+[\"']|\{[\"'][^\"']+[\"']\})",
        source,
    )
    if class_value and re.search(
        r"\b(?:bg|text|flex|grid|p[trblxy]?|m[trblxy]?|rounded|items|justify|gap|w|h)-",
        class_value.group(0),
    ):
        return "class usage"
    if configured:
        return "config"
    return None


def _nearby_react_files(
    source_path: str,
    all_paths: set[str],
    task_terms: set[str],
    kind: str,
) -> list[str]:
    source_parent = Path(source_path).parent
    matches = []
    for path in sorted(all_paths):
        suffix = Path(path).suffix.lower()
        stem = Path(path).stem
        if path == source_path or suffix not in REACT_SOURCE_SUFFIXES or _is_test_or_spec(path):
            continue

        terms = set(extract_identifier_terms(path))
        shared = task_terms & terms
        if kind == "hook":
            qualifies = stem.lower().startswith("use") and bool(shared)
        else:
            helper_named = bool({"helper", "helpers", "service", "services", "util", "utils"} & terms)
            qualifies = helper_named and len(shared) >= 2
        if not qualifies:
            continue

        distance = 0 if Path(path).parent == source_parent else 1
        matches.append((distance, -len(shared), path))

    return [path for _, _, path in sorted(matches)[:2]]


def _angular_family_relevant(path: str, relevant_paths: set[str]) -> bool:
    stem = path[: -len(".component.ts")]
    return any(candidate == path or candidate.startswith(stem + ".component.") for candidate in relevant_paths)


def _angular_hint(path: str, kind: str, task_terms: set[str]) -> dict:
    return {
        "path": path,
        "kind": kind,
        "matched_terms": sorted(task_terms & set(extract_identifier_terms(path)))[:4],
        "confidence": "medium",
        "confidence_reason": "convention",
    }


def _angular_single_file_hint(
    path: str,
    kind: str,
    root: Path,
    all_paths: set[str],
    suffix: str,
    task_terms: set[str],
) -> dict:
    stem = path[: -len(suffix)]
    test = f"{stem}{suffix[:-3]}.spec.ts"
    item = _angular_hint(path, kind, task_terms)
    if _relative_path_exists(root, all_paths, test):
        item["tests"] = [test]
    return item


def _first_existing_relative(
    root: Path,
    indexed_paths: set[str],
    candidates: list[str],
) -> str:
    matches = _existing_relative_paths(root, indexed_paths, candidates)
    return matches[0] if matches else ""


def _existing_relative_paths(
    root: Path,
    indexed_paths: set[str],
    candidates: list[str],
) -> list[str]:
    return [
        candidate
        for candidate in candidates
        if _relative_path_exists(root, indexed_paths, candidate)
    ]


def _relative_path_exists(root: Path, indexed_paths: set[str], path: str) -> bool:
    return path in indexed_paths or (root / Path(path)).is_file()
