from pathlib import Path

from context_matching import extract_identifier_terms, extract_task_terms, _normalize_path


def collect_react_hints(graph: dict, task: str, relevant_entries: list[dict]) -> list[dict]:
    """Describe strongly matched React component/hook starting files."""

    task_terms = set(extract_task_terms(task))
    hints = []
    for entry in relevant_entries:
        file_info = entry.get("file") if isinstance(entry, dict) else entry
        if not isinstance(file_info, dict):
            continue
        path = _normalize_path(str(file_info.get("path", "")))
        if Path(path).suffix.lower() not in {".jsx", ".tsx", ".js", ".ts"}:
            continue
        basename = Path(path).stem
        if basename.lower().endswith((".test", ".spec")):
            continue
        terms = set(extract_identifier_terms(path))
        symbol_terms = set()
        symbol_names = []
        for key in ("classes", "functions", "exports"):
            for item in file_info.get(key, []) or []:
                name = str(item.get("name", "")) if isinstance(item, dict) else str(item)
                if name:
                    symbol_names.append(name)
                    symbol_terms.update(extract_identifier_terms(name))
        is_hook = basename.startswith("use") and len(basename) > 3
        is_component = Path(path).suffix.lower() in {".jsx", ".tsx"} and basename[:1].isupper()
        matched = sorted(task_terms & (terms | symbol_terms))
        if not matched or not (is_hook or is_component):
            continue
        hints.append(
            {
                "path": path,
                "kind": "hook" if is_hook else "component",
                "symbols": symbol_names[:3],
                "matched_terms": matched[:4],
                "confidence": "medium",
                "confidence_reason": "convention",
            }
        )
    return hints[:4]


def build_react_hints_section(hints: list[dict] | None) -> list[str]:
    hints = list(hints or [])
    if not hints:
        return []
    lines = ["## React Hints", ""]
    for hint in hints:
        terms = ", ".join(f"`{term}`" for term in hint.get("matched_terms", []))
        lines.append(
            f"- `{hint.get('path', '<unknown>')}` - {hint.get('kind', 'React file')}, "
            f"medium confidence (convention); matched {terms}"
        )
    lines.append("")
    return lines


def collect_angular_hints(graph: dict, relevant_entries: list[dict]) -> list[dict]:
    """Find concise Angular component/service/guard/routing file relationships."""

    all_paths = {
        _normalize_path(str(file_info.get("path", "")))
        for file_info in (graph or {}).get("files", [])
        if isinstance(file_info, dict)
    }
    relevant_paths = {
        _normalize_path(str((entry.get("file") or {}).get("path", "")))
        for entry in relevant_entries
        if isinstance(entry, dict)
    }
    hints = []

    for path in sorted(all_paths):
        if path.endswith(".component.ts") and _angular_family_relevant(path, relevant_paths):
            stem = path[: -len(".component.ts")]
            item = {"path": path, "kind": "component"}
            template = f"{stem}.component.html"
            if template in all_paths:
                item["template"] = template
            styles = [
                candidate
                for candidate in (f"{stem}.component.scss", f"{stem}.component.css")
                if candidate in all_paths
            ]
            if styles:
                item["styles"] = styles
            test = f"{stem}.component.spec.ts"
            if test in all_paths:
                item["tests"] = [test]
            hints.append(item)
        elif path.endswith(".service.ts") and not path.endswith(".service.spec.ts") and path in relevant_paths:
            hints.append(_angular_single_file_hint(path, "service", all_paths, ".service.ts"))
        elif path.endswith(".guard.ts") and path in relevant_paths:
            hints.append(_angular_single_file_hint(path, "guard", all_paths, ".guard.ts"))
        elif Path(path).name in {"app.routes.ts", "app-routing.module.ts"} and path in relevant_paths:
            hints.append({"path": path, "kind": "routing"})

    return hints[:5]


def build_angular_hints_section(hints: list[dict] | None) -> list[str]:
    hints = list(hints or [])
    if not hints:
        return []
    lines = ["## Angular Hints", ""]
    for hint in hints:
        lines.append(f"- `{hint.get('path', '<unknown>')}` - {hint.get('kind', 'Angular file')}")
        if hint.get("template"):
            lines.append(f"  - template: `{hint['template']}`")
        for style in hint.get("styles", []) or []:
            lines.append(f"  - style: `{style}`")
        for test in hint.get("tests", []) or []:
            lines.append(f"  - tests: `{test}`")
    lines.append("")
    return lines


def _angular_family_relevant(path: str, relevant_paths: set[str]) -> bool:
    stem = path[: -len(".component.ts")]
    return any(candidate == path or candidate.startswith(stem + ".component.") for candidate in relevant_paths)


def _angular_single_file_hint(path: str, kind: str, all_paths: set[str], suffix: str) -> dict:
    stem = path[: -len(suffix)]
    test = f"{stem}{suffix[:-3]}.spec.ts"
    item = {"path": path, "kind": kind}
    if test in all_paths:
        item["tests"] = [test]
    return item
