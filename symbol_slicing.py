import ast
from pathlib import Path

from context_matching import extract_identifier_terms, extract_task_terms


DEFAULT_SYMBOL_HINT_LIMIT = 8
PER_FILE_SYMBOL_HINT_LIMIT = 4
WEAK_TASK_TERMS = {
    "bug",
    "change",
    "command",
    "fix",
    "output",
    "update",
}


def extract_python_symbols(path: str | Path) -> dict:
    """Extract top-level Python symbols and simple class methods from one file."""

    file_path = Path(path)
    normalized_path = str(file_path).replace("\\", "/")
    result = {
        "path": normalized_path,
        "language": "python",
        "status": "ok",
        "symbols": [],
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

    symbols = []

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols.append(_build_function_symbol(node, normalized_path))
            continue

        if isinstance(node, ast.ClassDef):
            symbols.append(_build_class_symbol(node, normalized_path))
            symbols.extend(_build_method_symbols(node, normalized_path))

    result["symbols"] = symbols
    return result


def collect_symbol_hints(
    graph: dict,
    task: str,
    relevant_entries: list[dict] | None = None,
    *,
    selected_paths: list[str] | None = None,
    limit: int = DEFAULT_SYMBOL_HINT_LIMIT,
) -> list[dict]:
    """Find likely relevant symbols for a task using selected or ranked files."""

    root = Path(str((graph or {}).get("root") or "."))
    task_terms = _prioritize_task_terms(extract_task_terms(task))
    selected_set = {_normalize_path(path) for path in (selected_paths or []) if str(path or "").strip()}
    entries = list(relevant_entries or [])
    hints: list[dict] = []
    seen: set[tuple[str, str, int, int]] = set()

    for entry in entries:
        file_info = entry.get("file") if isinstance(entry, dict) else entry
        if not isinstance(file_info, dict):
            continue

        path = str(file_info.get("path", "")).replace("\\", "/").strip()
        if not path:
            continue

        normalized_path = _normalize_path(path)
        language = str(file_info.get("language", "")).strip().lower()
        if language and language not in {"python", "unknown"}:
            continue
        if not normalized_path.endswith(".py"):
            continue

        file_path = root / Path(path)
        if not file_path.exists() or file_path.is_dir():
            continue

        parsed = extract_python_symbols(file_path)
        if parsed.get("status") != "ok":
            continue

        file_selected = bool(entry.get("selected_by_user")) or normalized_path in selected_set
        path_terms = set(extract_identifier_terms(path))
        file_hints = []

        for symbol in parsed.get("symbols", []):
            if not isinstance(symbol, dict):
                continue

            hint = _score_symbol_hint(
                symbol,
                task_terms,
                path_terms,
                file_path=normalized_path,
                file_selected=file_selected,
            )

            if hint is None:
                continue

            key = (
                hint["file_path"],
                hint["symbol_name"],
                int(hint["start_line"]),
                int(hint["end_line"]),
            )
            if key in seen:
                continue

            seen.add(key)
            file_hints.append(hint)

        file_hints.sort(
            key=lambda item: (
                int(item.get("priority", 99)),
                -int(item.get("score", 0)),
                -int(item.get("matched_term_count", 0)),
                item.get("kind", ""),
                int(item.get("start_line", 0)),
                item.get("symbol_name", ""),
            )
        )
        hints.extend(file_hints[:PER_FILE_SYMBOL_HINT_LIMIT])

    hints.sort(
        key=lambda item: (
            int(item.get("priority", 99)),
            -int(item.get("score", 0)),
            -int(item.get("matched_term_count", 0)),
            item.get("file_path", ""),
            int(item.get("start_line", 0)),
            item.get("symbol_name", ""),
        )
    )

    return hints[:limit]


def build_symbol_hints_section(symbol_hints: list[dict] | None) -> list[str]:
    """Render the symbol hint section for context packs and prompts."""

    lines = ["## Symbol Hints", ""]
    hints = list(symbol_hints or [])

    if not hints:
        lines.append("No strong symbol matches found.")
        lines.append("")
        return lines

    for hint in hints:
        file_path = str(hint.get("file_path", "<unknown>"))
        symbol_name = str(hint.get("symbol_name", "<unknown>"))
        kind = str(hint.get("kind", "symbol"))
        start_line = hint.get("start_line")
        end_line = hint.get("end_line")
        reason = str(hint.get("reason", "matched task context"))
        line_range = _format_line_range(start_line, end_line)

        lines.append(f"- `{file_path}`::{symbol_name} - {kind}, {line_range}, {reason}")

    lines.append("")
    return lines


def _build_class_symbol(node: ast.ClassDef, file_path: str) -> dict:
    return {
        "name": node.name,
        "qualname": node.name,
        "kind": "class",
        "file_path": file_path,
        "start_line": node.lineno,
        "end_line": getattr(node, "end_lineno", node.lineno),
        "signature": f"class {node.name}",
    }


def _build_function_symbol(node: ast.AST, file_path: str) -> dict:
    name = str(getattr(node, "name", "<unknown>"))
    return {
        "name": name,
        "qualname": name,
        "kind": "function",
        "file_path": file_path,
        "start_line": getattr(node, "lineno", 0),
        "end_line": getattr(node, "end_lineno", getattr(node, "lineno", 0)),
        "signature": _format_function_signature(node),
    }


def _build_method_symbols(node: ast.ClassDef, file_path: str) -> list[dict]:
    methods = []

    for child in node.body:
        if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        methods.append(
            {
                "name": child.name,
                "qualname": f"{node.name}.{child.name}",
                "kind": "method",
                "class_name": node.name,
                "file_path": file_path,
                "start_line": child.lineno,
                "end_line": getattr(child, "end_lineno", child.lineno),
                "signature": _format_function_signature(child),
            }
        )

    return methods


def _score_symbol_hint(
    symbol: dict,
    task_terms: list[str],
    path_terms: set[str],
    *,
    file_path: str,
    file_selected: bool,
) -> dict | None:
    symbol_terms = set(extract_identifier_terms(str(symbol.get("name", ""))))
    symbol_terms.update(extract_identifier_terms(str(symbol.get("qualname", ""))))
    symbol_matches = [term for term in task_terms if term in symbol_terms]
    path_matches = [term for term in task_terms if term in path_terms]
    matched_terms = _dedupe(symbol_matches + path_matches)

    if not file_selected and not matched_terms:
        return None

    priority, score = _score_symbol_priority(
        file_selected=file_selected,
        symbol_matches=symbol_matches,
        path_matches=path_matches,
    )
    reasons = []

    if file_selected:
        reasons.append("selected file symbol")

    if symbol_matches:
        reasons.append(_format_task_reason(symbol_matches))
    elif path_matches:
        reasons.append(_format_task_reason(path_matches))

    if len(matched_terms) >= 2:
        reasons.append("multi-term match")

    if symbol.get("kind") == "function":
        score += 3
    elif symbol.get("kind") == "class":
        score += 2
    else:
        score += 1

    return {
        "file_path": file_path,
        "symbol_name": str(symbol.get("qualname") or symbol.get("name") or "<unknown>"),
        "name": str(symbol.get("name", "")),
        "kind": str(symbol.get("kind", "symbol")),
        "start_line": int(symbol.get("start_line", 0) or 0),
        "end_line": int(symbol.get("end_line", 0) or 0),
        "signature": str(symbol.get("signature", "")),
        "reason": "; ".join(reasons) if reasons else "matched task context",
        "priority": priority,
        "matched_term_count": len(matched_terms),
        "score": score,
    }


def _score_symbol_priority(
    *,
    file_selected: bool,
    symbol_matches: list[str],
    path_matches: list[str],
) -> tuple[int, int]:
    matched_term_count = len(_dedupe(symbol_matches + path_matches))

    if file_selected:
        if len(symbol_matches) >= 2:
            return 0, 500 + 70 * len(symbol_matches) + 10 * len(path_matches)

        if symbol_matches:
            return 1, 400 + 60 * len(symbol_matches) + 8 * len(path_matches)

        if path_matches:
            return 2, 300 + 20 * len(path_matches)

        return 2, 280

    if matched_term_count >= 2:
        return 3, 220 + 60 * len(symbol_matches) + 10 * len(path_matches)

    if matched_term_count == 1:
        return 4, 140 + 40 * len(symbol_matches) + 5 * len(path_matches)

    return 5, 0


def _prioritize_task_terms(task_terms: list[str]) -> list[str]:
    strong_terms = [term for term in task_terms if term not in WEAK_TASK_TERMS]

    if strong_terms:
        return strong_terms

    return task_terms


def _format_task_reason(matched_terms: list[str]) -> str:
    if not matched_terms:
        return "matched task context"

    label = "matched task terms" if len(matched_terms) > 1 else "matched task term"
    return f"{label} {_format_term_list(matched_terms)}"


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


def _format_line_range(start_line: object, end_line: object) -> str:
    start = _safe_int(start_line)
    end = _safe_int(end_line)

    if start <= 0 and end <= 0:
        return "lines unknown"

    if end <= 0 or end == start:
        return f"line {max(start, end)}"

    return f"lines {start}-{end}"


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


def _safe_int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _normalize_path(path: str) -> str:
    return str(path or "").replace("\\", "/").strip()


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []

    for value in values:
        if value in seen:
            continue

        seen.add(value)
        result.append(value)

    return result
