import ast
import re
from pathlib import Path

from context_matching import extract_identifier_terms, extract_task_terms, _dedupe, _file_stem, _normalize_path

DEFAULT_TEST_HINT_FILE_LIMIT = 3
DEFAULT_TEST_HINT_FUNCTION_LIMIT = 5
DEFAULT_TEST_HINT_FUNCTIONS_PER_FILE = 2

_WEAK_TASK_TERMS = {
    "bug",
    "change",
    "fix",
    "issue",
    "output",
    "update",
}


def extract_python_test_functions(path: str | Path) -> dict:
    """Extract top-level pytest-style test functions from one Python file."""

    file_path = Path(path)
    normalized_path = str(file_path).replace("\\", "/")
    result = {
        "path": normalized_path,
        "language": "python",
        "status": "ok",
        "functions": [],
    }

    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError as error:
        result["status"] = "syntax_error"
        result["error"] = {
            "type": "syntax_error",
            "message": str(error),
            "line": error.lineno,
        }
        return result
    except OSError as error:
        result["status"] = "read_error"
        result["error"] = {
            "type": "read_error",
            "message": str(error),
        }
        return result

    functions = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        if not node.name.startswith("test_"):
            continue

        functions.append(
            {
                "name": node.name,
                "start_line": int(getattr(node, "lineno", 0) or 0),
                "end_line": int(getattr(node, "end_lineno", getattr(node, "lineno", 0)) or 0),
                "signature": _format_function_signature(node),
            }
        )

    result["functions"] = functions
    return result


def extract_javascript_test_functions(path: str | Path) -> dict:
    """Extract common test/it declarations from JS, TS, JSX, and TSX files."""

    file_path = Path(path)
    normalized_path = str(file_path).replace("\\", "/")
    result = {
        "path": normalized_path,
        "language": "typescript" if file_path.suffix.lower() in {".ts", ".tsx"} else "javascript",
        "status": "ok",
        "functions": [],
    }
    try:
        lines = file_path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        result["status"] = "read_error"
        result["error"] = {"type": "read_error", "message": str(error)}
        return result

    pattern = re.compile(
        r"^\s*(?:it|test)\s*\(\s*([\"'`])(?P<name>.+?)\1\s*,"
    )
    functions = []
    for line_number, line in enumerate(lines, start=1):
        match = pattern.match(line)
        if match is None:
            continue
        functions.append(
            {
                "name": match.group("name"),
                "start_line": line_number,
                "end_line": line_number,
                "signature": "",
            }
        )
    result["functions"] = functions
    return result


def extract_test_functions(path: str | Path) -> dict:
    if Path(path).suffix.lower() == ".py":
        return extract_python_test_functions(path)
    return extract_javascript_test_functions(path)


def collect_test_hints(
    graph: dict,
    task: str,
    relevant_entries: list[dict] | None = None,
    *,
    selected_paths: list[str] | None = None,
    limit_files: int = DEFAULT_TEST_HINT_FILE_LIMIT,
    limit_functions: int = DEFAULT_TEST_HINT_FUNCTION_LIMIT,
) -> dict:
    """Collect conservative test-file hints for a task."""

    root = Path(str((graph or {}).get("root") or "."))
    task_terms = _prioritize_task_terms(extract_task_terms(task))
    selected_set = {
        _normalize_path(path)
        for path in (selected_paths or [])
        if str(path or "").strip()
    }
    source_candidates = _collect_source_candidates(relevant_entries or [], selected_set)
    if not source_candidates:
        return _empty_test_hint_report(limit_files, limit_functions)

    file_candidates: list[dict] = []
    candidate_function_count = 0

    for test_file in _collect_test_files(graph):
        file_path = root / Path(test_file["path"])
        if not file_path.exists() or file_path.is_dir():
            continue

        parsed = extract_test_functions(file_path)
        if parsed.get("status") != "ok":
            continue

        source_match = _best_source_match(test_file, source_candidates)
        if source_match is None:
            continue

        function_hints = _score_test_functions(
            parsed.get("functions", []),
            task_terms,
            source_match,
        )
        file_only = (
            not function_hints
            and bool(source_match.get("exact_filename"))
            and file_path.suffix.lower() in {".js", ".jsx", ".ts", ".tsx"}
        )
        if not function_hints and not file_only:
            continue

        function_hints = function_hints[:DEFAULT_TEST_HINT_FUNCTIONS_PER_FILE]
        candidate_function_count += len(function_hints)
        file_candidates.append(
            {
                "test_file": test_file["path"],
                "source_path": source_match["source_path"],
                "reason": source_match["reason"],
                "score": source_match["score"],
                "functions": function_hints,
                "file_only": file_only,
            }
        )

    file_candidates.sort(
        key=lambda item: (
            -int(item.get("score", 0)),
            str(item.get("test_file", "")),
            str(item.get("source_path", "")),
        )
    )

    included_files = file_candidates[:limit_files]
    included_function_count = 0
    for file_item in included_files:
        functions = list(file_item.get("functions", []))
        trimmed = []
        for function in functions:
            if included_function_count >= limit_functions:
                break
            trimmed.append(function)
            included_function_count += 1
        file_item["functions"] = trimmed

    included_files = [
        file_item
        for file_item in included_files
        if file_item.get("functions") or file_item.get("file_only")
    ]
    included_function_count = sum(len(file_item.get("functions", [])) for file_item in included_files)

    skipped_file_count = max(0, len(file_candidates) - len(included_files))
    skipped_function_count = max(0, candidate_function_count - included_function_count)

    return {
        "included": included_files,
        "included_count": len(included_files),
        "included_function_count": included_function_count,
        "candidate_count": len(file_candidates),
        "candidate_function_count": candidate_function_count,
        "skipped_count": skipped_file_count + skipped_function_count,
        "skipped_file_count": skipped_file_count,
        "skipped_function_count": skipped_function_count,
        "max_files": limit_files,
        "max_functions": limit_functions,
    }


def build_test_hints_section(test_hints_report: dict | None) -> list[str]:
    """Render the test-hints section for context packs and prompts."""

    lines = ["## Test Hints", ""]
    report = test_hints_report or {}
    hints = list(report.get("included", []) or [])

    if not hints:
        lines.append("No strong test hints found.")
        skipped_count = int(report.get("skipped_count", 0) or 0)
        if skipped_count:
            lines.append(
                f"Skipped test hints: {skipped_count} hint(s) were skipped by cap or safety filters."
            )
        lines.append("")
        return lines

    for hint in hints:
        test_file = str(hint.get("test_file", "<unknown>"))
        source_path = str(hint.get("source_path", "<unknown>"))
        reason = str(hint.get("reason", "filename match"))

        lines.append(f"- `{test_file}` - likely covers `{source_path}`")
        if reason:
            lines.append(f"  - {reason}")

        for function in hint.get("functions", []) or []:
            function_name = str(function.get("name", "<unknown>"))
            function_reason = str(function.get("reason", "matched test context"))
            lines.append(f"  - `{function_name}` - {function_reason}")

    skipped_count = int(report.get("skipped_count", 0) or 0)
    if skipped_count:
        lines.append(
            f"Skipped test hints: {skipped_count} hint(s) were skipped by cap or safety filters."
        )

    lines.append("")
    return lines


def _collect_source_candidates(relevant_entries: list[dict], selected_set: set[str]) -> list[dict]:
    candidates: list[dict] = []
    seen: set[str] = set()

    for entry in relevant_entries:
        file_info = entry.get("file") if isinstance(entry, dict) else entry
        if not isinstance(file_info, dict):
            continue

        path = _normalize_path(str(file_info.get("path", "")))
        if not path or path in seen or _is_test_file(path):
            continue

        seen.add(path)
        candidates.append(
            {
                "path": path,
                "file": file_info,
                "selected": bool(entry.get("selected_by_user")) or path in selected_set,
                "terms": _collect_source_terms(file_info),
            }
        )

    for path in selected_set:
        if path in seen or _is_test_file(path):
            continue

        candidates.append(
            {
                "path": path,
                "file": {
                    "path": path,
                    "language": "unknown",
                    "classes": [],
                    "functions": [],
                    "interfaces": [],
                    "types": [],
                    "enums": [],
                    "exports": [],
                    "imports": [],
                    "external_imports": [],
                    "unresolved_imports": [],
                    "unresolved_import_details": [],
                    "routes": [],
                },
                "selected": True,
                "terms": extract_identifier_terms(path),
            }
        )

    return candidates


def _collect_source_terms(file_info: dict) -> list[str]:
    terms: list[str] = []
    path = str(file_info.get("path", "")).replace("\\", "/").strip()
    if path:
        terms.extend(extract_identifier_terms(path))

    for key in ("classes", "functions", "exports"):
        for item in file_info.get(key, []) or []:
            if isinstance(item, dict):
                terms.extend(extract_identifier_terms(str(item.get("name", ""))))
                terms.extend(extract_identifier_terms(str(item.get("qualname", ""))))
                continue

            terms.extend(extract_identifier_terms(str(item)))

    for route in file_info.get("routes", []) or []:
        if not isinstance(route, dict):
            continue

        terms.extend(extract_identifier_terms(str(route.get("method", ""))))
        terms.extend(extract_identifier_terms(str(route.get("path", ""))))
        terms.extend(extract_identifier_terms(str(route.get("source", ""))))

    return _dedupe([term for term in terms if term])


def _collect_test_files(graph: dict) -> list[dict]:
    files = []

    for file_info in graph.get("files", []):
        if not isinstance(file_info, dict):
            continue

        path = _normalize_path(str(file_info.get("path", "")))
        if not path or not _is_test_file(path):
            continue

        basename = Path(path).name
        files.append(
            {
                "path": path,
                "basename": basename,
                "stem": _file_stem(basename),
                "text_hint": _build_test_text_hint(file_info, path),
            }
        )

    files.sort(key=lambda item: (str(item.get("path", "")), str(item.get("basename", ""))))
    return files


def _build_test_text_hint(file_info: dict, path: str) -> str:
    values = [path]
    for key in ("imports", "external_imports", "unresolved_imports"):
        for item in file_info.get(key, []) or []:
            values.append(str(item))

    for item in file_info.get("unresolved_import_details", []) or []:
        if isinstance(item, dict):
            values.extend(str(value) for value in item.values())

    return _normalize_text(" ".join(values))


def _best_source_match(test_file: dict, source_candidates: list[dict]) -> dict | None:
    stem = _source_test_stem(str(test_file.get("stem", "")))
    text_hint = str(test_file.get("text_hint", ""))
    test_parent = Path(str(test_file.get("path", ""))).parent.as_posix()
    best: dict | None = None

    for source in source_candidates:
        source_path = str(source.get("path", ""))
        source_basename = Path(source_path).name
        source_stem = _file_stem(source_basename)
        source_module = source_path[:-3].replace("/", ".") if source_path.endswith(".py") else source_path.replace("/", ".")

        exact_filename = stem == f"test_{source_stem}" or stem == source_stem
        referenced_source = any(
            needle and needle in text_hint
            for needle in (
                _normalize_text(source_path),
                _normalize_text(source_module),
                _normalize_text(source_basename),
                _normalize_text(source_stem),
            )
        )

        if not exact_filename and not referenced_source:
            continue

        score = 0
        reasons = []

        if exact_filename:
            score += 300
            reasons.append("filename match")

        if referenced_source:
            score += 180
            reasons.append("references source path or module")

        source_parent = Path(source_path).parent.as_posix()
        proximity = _directory_proximity(test_parent, source_parent)
        if proximity:
            score += proximity
            reasons.append("nearby directory")

        if source.get("selected"):
            score += 40
            reasons.append("selected source")

        score += min(len(source.get("terms", [])), 15)

        candidate = {
            "source_path": source_path,
            "source_terms": list(source.get("terms", [])),
            "selected": bool(source.get("selected")),
            "exact_filename": exact_filename,
            "score": score,
            "reason": "; ".join(reasons) if reasons else "matched source file",
        }

        if best is None or _source_is_better(candidate, best):
            best = candidate

    return best


def _source_is_better(candidate: dict, current: dict) -> bool:
    candidate_key = (
        int(candidate.get("score", 0)),
        1 if candidate.get("exact_filename") else 0,
        1 if candidate.get("selected") else 0,
        -len(str(candidate.get("source_path", ""))),
        str(candidate.get("source_path", "")),
    )
    current_key = (
        int(current.get("score", 0)),
        1 if current.get("exact_filename") else 0,
        1 if current.get("selected") else 0,
        -len(str(current.get("source_path", ""))),
        str(current.get("source_path", "")),
    )
    return candidate_key > current_key


def _score_test_functions(
    functions: list[dict],
    task_terms: list[str],
    source_match: dict,
) -> list[dict]:
    source_terms = set(source_match.get("source_terms", []) or [])
    matched = []

    for function in functions:
        if not isinstance(function, dict):
            continue

        name = str(function.get("name", "")).strip()
        if not name:
            continue

        function_terms = set(extract_identifier_terms(name))
        task_matches = [term for term in task_terms if term in function_terms]
        source_matches = [term for term in source_terms if term in function_terms]

        if not task_matches and not source_matches:
            continue

        matched.append(
            {
                "name": name,
                "start_line": int(function.get("start_line", 0) or 0),
                "end_line": int(function.get("end_line", function.get("start_line", 0)) or 0),
                "reason": _format_function_reason(task_matches, source_matches, source_match),
                "matched_terms": _dedupe(task_matches + source_matches),
                "score": _score_function(function, task_matches, source_matches, source_match),
            }
        )

    if matched:
        matched.sort(
            key=lambda item: (
                -int(item.get("score", 0)),
                int(item.get("start_line", 0)),
                str(item.get("name", "")),
            )
        )
        return matched

    if not source_match.get("exact_filename"):
        return []

    fallback = []
    for function in sorted(
        [item for item in functions if isinstance(item, dict)],
        key=lambda item: (
            int(item.get("start_line", 0) or 0),
            str(item.get("name", "")),
        ),
    ):
        name = str(function.get("name", "")).strip()
        if not name:
            continue

        fallback.append(
            {
                "name": name,
                "start_line": int(function.get("start_line", 0) or 0),
                "end_line": int(function.get("end_line", function.get("start_line", 0)) or 0),
                "reason": "filename match",
                "matched_terms": [],
                "score": max(1, 1_000 - int(function.get("start_line", 0) or 0)),
            }
        )
        if len(fallback) >= DEFAULT_TEST_HINT_FUNCTIONS_PER_FILE:
            break

    return fallback


def _score_function(
    function: dict,
    task_matches: list[str],
    source_matches: list[str],
    source_match: dict,
) -> int:
    score = 0
    score += 120 * len(task_matches)
    score += 80 * len(source_matches)
    if source_match.get("selected"):
        score += 25
    score += max(0, 40 - int(function.get("start_line", 0) or 0))
    return score


def _format_function_reason(
    task_matches: list[str],
    source_matches: list[str],
    source_match: dict,
) -> str:
    reasons = []

    if task_matches:
        reasons.append(f"matched task terms {_format_term_list(task_matches)}")

    if source_matches:
        reasons.append(f"matched source terms {_format_term_list(source_matches)}")

    if source_match.get("exact_filename") and not task_matches and not source_matches:
        reasons.append("filename match")

    if source_match.get("selected") and not task_matches:
        reasons.append("selected source")

    if not reasons:
        return "matched test context"

    return "; ".join(reasons)


def _format_term_list(terms: list[str]) -> str:
    unique_terms = []
    seen = set()

    for term in terms:
        normalized = str(term).strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique_terms.append(f'"{normalized}"')

    if not unique_terms:
        return '""'

    return ", ".join(unique_terms)


def _prioritize_task_terms(task_terms: list[str]) -> list[str]:
    strong_terms = [term for term in task_terms if term not in _WEAK_TASK_TERMS]
    return strong_terms or task_terms


def _format_function_signature(node: ast.AST) -> str:
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return ""

    args = node.args
    parts: list[str] = []

    for arg in getattr(args, "posonlyargs", []):
        parts.append(arg.arg)

    for arg in args.args:
        parts.append(arg.arg)

    if args.vararg is not None:
        parts.append(f"*{args.vararg.arg}")
    elif args.kwonlyargs:
        parts.append("*")

    for arg in args.kwonlyargs:
        parts.append(arg.arg)

    if args.kwarg is not None:
        parts.append(f"**{args.kwarg.arg}")

    return f"({', '.join(parts)})"


def _is_test_file(normalized_path: str) -> bool:
    path = _normalize_path(normalized_path)
    basename = Path(path).name
    stem = _file_stem(basename).lower()
    return (
        path.startswith("tests/")
        or "/tests/" in path
        or stem.startswith("test_")
        or stem.endswith(".test")
        or stem.endswith(".spec")
        or ".test." in path
        or ".spec." in path
    )


def _normalize_text(text: str) -> str:
    return (
        str(text)
        .replace("\\", "/")
        .replace("_", " ")
        .replace("-", " ")
        .lower()
    )


def _source_test_stem(stem: str) -> str:
    normalized = str(stem)
    for suffix in (".test", ".spec"):
        if normalized.lower().endswith(suffix):
            return normalized[: -len(suffix)]
    return normalized


def _directory_proximity(test_parent: str, source_parent: str) -> int:
    if test_parent == source_parent:
        return 80

    test_parts = [part for part in test_parent.split("/") if part and part != "__tests__"]
    source_parts = [part for part in source_parent.split("/") if part]
    shared = 0
    for left, right in zip(test_parts, source_parts):
        if left != right:
            break
        shared += 1
    return min(45, shared * 15)


def _empty_test_hint_report(limit_files: int, limit_functions: int) -> dict:
    return {
        "included": [],
        "included_count": 0,
        "included_function_count": 0,
        "candidate_count": 0,
        "candidate_function_count": 0,
        "skipped_count": 0,
        "skipped_file_count": 0,
        "skipped_function_count": 0,
        "max_files": limit_files,
        "max_functions": limit_functions,
    }
