import json
import re
from pathlib import Path

from strata.core.context_matching import extract_identifier_terms, extract_task_terms


DEFAULT_DECLARATION_HINT_LIMIT = 6


def collect_typescript_project_hints(graph: dict) -> dict:
    """Read compact baseUrl/path-alias hints from tsconfig.json or jsconfig.json."""

    root = Path(str((graph or {}).get("root") or "."))
    config_paths = _project_config_paths(graph)

    for relative_path in config_paths:
        path = root / Path(relative_path)
        if not path.exists() or path.is_dir():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue

        compiler_options = payload.get("compilerOptions")
        if not isinstance(compiler_options, dict):
            continue

        base_url = str(compiler_options.get("baseUrl") or "").strip()
        aliases = []
        raw_paths = compiler_options.get("paths")
        if isinstance(raw_paths, dict):
            for alias, targets in raw_paths.items():
                if isinstance(targets, str):
                    targets = [targets]
                if not isinstance(targets, list):
                    continue
                clean_targets = [str(target).strip() for target in targets if str(target).strip()]
                if clean_targets:
                    aliases.append({"alias": str(alias), "targets": clean_targets[:3]})

        if base_url or aliases:
            return {
                "config_path": relative_path,
                "base_url": base_url,
                "aliases": aliases[:8],
                "alias_count": len(aliases),
            }

    return {"config_path": "", "base_url": "", "aliases": [], "alias_count": 0}


def build_typescript_project_hints_section(report: dict | None) -> list[str]:
    report = report or {}
    base_url = str(report.get("base_url") or "")
    aliases = list(report.get("aliases", []) or [])
    if not base_url and not aliases:
        return []

    lines = ["## TypeScript Project Hints", ""]
    if base_url:
        lines.append(f"- baseUrl: `{base_url}`")
    for item in aliases:
        alias = str(item.get("alias", ""))
        targets = list(item.get("targets", []) or [])
        if alias and targets:
            lines.append(f"- path alias: `{alias}` -> `{', '.join(targets)}`")
    lines.append("")
    return lines


def collect_declaration_hints(
    graph: dict,
    task: str,
    *,
    limit: int = DEFAULT_DECLARATION_HINT_LIMIT,
) -> list[dict]:
    """Collect task-relevant public API declarations from .d.ts files."""

    root = Path(str((graph or {}).get("root") or "."))
    task_terms = set(extract_task_terms(task))
    candidates = []

    for file_info in (graph or {}).get("files", []):
        path = str(file_info.get("path", "")).replace("\\", "/").strip()
        if not path.endswith(".d.ts"):
            continue
        file_path = root / Path(path)
        if not file_path.exists() or file_path.is_dir():
            continue
        candidates.extend(_parse_declaration_file(file_path, path, task_terms))

    candidates.sort(
        key=lambda item: (
            -int(item.get("matched_term_count", 0)),
            str(item.get("file_path", "")),
            int(item.get("start_line", 0)),
            str(item.get("name", "")),
        )
    )
    return candidates[:limit]


def build_declaration_hints_section(hints: list[dict] | None) -> list[str]:
    hints = list(hints or [])
    if not hints:
        return []

    lines = ["## Declaration Hints", ""]
    for hint in hints:
        signature = str(hint.get("signature") or "").strip()
        suffix = f": `{signature}`" if signature else ""
        lines.append(
            f"- `{hint.get('file_path', '<unknown>')}`::{hint.get('name', '<unknown>')}"
            f" - {hint.get('kind', 'declaration')}, declaration, high confidence{suffix}"
        )
    lines.append("")
    return lines


def _project_config_paths(graph: dict) -> list[str]:
    paths = []
    for file_info in (graph or {}).get("files", []):
        path = str(file_info.get("path", "")).replace("\\", "/").strip()
        if Path(path).name.lower() in {"tsconfig.json", "jsconfig.json"}:
            paths.append(path)
    for fallback in ("tsconfig.json", "jsconfig.json"):
        if fallback not in paths:
            paths.append(fallback)
    return sorted(paths, key=lambda path: (path.count("/"), path))


def _parse_declaration_file(path: Path, relative_path: str, task_terms: set[str]) -> list[dict]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return []

    patterns = (
        ("function", re.compile(r"^\s*(?:export\s+)?declare\s+function\s+(?P<name>\w+)\s*(?P<sig>\([^;{]*\)[^;{]*)")),
        ("function", re.compile(r"^\s*export\s+function\s+(?P<name>\w+)\s*(?P<sig>\([^;{]*\)[^;{]*)")),
        ("interface", re.compile(r"^\s*export\s+interface\s+(?P<name>\w+)")),
        ("type", re.compile(r"^\s*export\s+type\s+(?P<name>\w+)(?P<sig>\s*=\s*[^;]+)?")),
        ("class", re.compile(r"^\s*export\s+(?:declare\s+)?class\s+(?P<name>\w+)")),
    )
    results = []
    current_container = ""
    container_end = 0

    for index, line in enumerate(lines, start=1):
        if current_container and index <= container_end:
            method = re.match(r"^\s+(?P<name>\w+)\s*(?P<sig>\([^;{]*\)[^;{]*);", line)
            if method:
                results.append(
                    _declaration_record(
                        relative_path,
                        f"{current_container}.{method.group('name')}",
                        "method",
                        index,
                        method.group("sig"),
                        task_terms,
                    )
                )

        for kind, pattern in patterns:
            match = pattern.match(line)
            if match is None:
                continue
            name = match.group("name")
            signature = str(match.groupdict().get("sig") or "").strip()
            results.append(
                _declaration_record(
                    relative_path,
                    name,
                    kind,
                    index,
                    signature,
                    task_terms,
                )
            )
            if kind in {"interface", "class"} and "{" in line:
                current_container = name
                container_end = _brace_end(lines, index)
            break

    matched = [item for item in results if item["matched_term_count"]]
    return matched or results[:2]


def _declaration_record(
    path: str,
    name: str,
    kind: str,
    line: int,
    signature: str,
    task_terms: set[str],
) -> dict:
    terms = set(extract_identifier_terms(f"{path} {name}"))
    return {
        "file_path": path,
        "name": name,
        "kind": kind,
        "start_line": line,
        "end_line": line,
        "signature": re.sub(r"\s+", " ", signature)[:240],
        "language": "typescript",
        "confidence": "high",
        "confidence_reason": "declaration",
        "matched_term_count": len(task_terms & terms),
    }


def _brace_end(lines: list[str], start_line: int) -> int:
    depth = 0
    for index in range(start_line - 1, min(len(lines), start_line + 200)):
        depth += lines[index].count("{")
        depth -= lines[index].count("}")
        if depth <= 0 and index >= start_line:
            return index + 1
    return min(len(lines), start_line + 50)
