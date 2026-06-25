import ast
import re
from pathlib import Path

from context_matching import extract_identifier_terms, extract_task_terms
from context_efficiency import estimate_tokens
from selected_context import is_generated_or_ignored_path, is_secret_like_path


DEFAULT_SYMBOL_HINT_LIMIT = 8
PER_FILE_SYMBOL_HINT_LIMIT = 4
DEFAULT_SYMBOL_SNIPPET_LIMIT = 4
DEFAULT_SYMBOL_SNIPPET_MAX_LINES = 80
DEFAULT_SYMBOL_SNIPPET_MAX_CHARS = 2500
DEFAULT_SYMBOL_SNIPPET_SKIPPED_LIMIT = 4
WEAK_TASK_TERMS = {
    "bug",
    "change",
    "command",
    "fix",
    "output",
    "update",
}
JS_TS_EXTENSIONS = {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"}


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


def extract_javascript_symbols(path: str | Path) -> dict:
    """Extract useful JavaScript/TypeScript symbols with approximate ranges."""

    file_path = Path(path)
    normalized_path = str(file_path).replace("\\", "/")
    language = _javascript_language(file_path)
    result = {
        "path": normalized_path,
        "language": language,
        "status": "ok",
        "symbols": [],
    }

    try:
        source = file_path.read_text(encoding="utf-8")
    except OSError as error:
        result["status"] = "read_error"
        result["error"] = {"type": "read_error", "message": str(error)}
        return result

    lines = source.splitlines()
    symbols: list[dict] = []
    seen: set[tuple[str, int]] = set()
    class_ranges: list[tuple[str, int, int]] = []

    patterns = (
        (
            re.compile(
                r"^\s*(?:export\s+)?(?:default\s+)?(?P<async>async\s+)?function\s+"
                r"(?P<name>[A-Za-z_$][\w$]*)\s*(?P<signature>\([^)]*\))"
            ),
            "function",
        ),
        (
            re.compile(
                r"^\s*(?:export\s+)?(?:default\s+)?class\s+"
                r"(?P<name>[A-Za-z_$][\w$]*)"
            ),
            "class",
        ),
        (
            re.compile(
                r"^\s*(?:export\s+)?(?:default\s+)?(?:const|let|var)\s+"
                r"(?P<name>[A-Za-z_$][\w$]*)"
                r"(?:\s*:\s*[^=]+)?\s*=\s*(?:async\s*)?"
                r"(?P<signature>\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>"
            ),
            "function",
        ),
    )

    for index, line in enumerate(lines, start=1):
        for pattern, default_kind in patterns:
            match = pattern.match(line)
            if match is None:
                continue

            name = match.group("name")
            key = (name, index)
            if key in seen:
                break
            seen.add(key)

            end_line = _approximate_js_symbol_end(lines, index)
            kind = _javascript_symbol_kind(
                name,
                default_kind,
                file_path.suffix.lower(),
            )
            signature = _compact_signature(line, match.groupdict().get("signature"))
            symbol = {
                "name": name,
                "qualname": name,
                "kind": kind,
                "file_path": normalized_path,
                "start_line": index,
                "end_line": end_line,
                "signature": signature,
                "language": language,
                "confidence": "medium",
                "confidence_reason": "regex",
            }
            symbols.append(symbol)
            if default_kind == "class":
                class_ranges.append((name, index, end_line))
            break

    for class_name, start_line, end_line in class_ranges:
        symbols.extend(
            _extract_javascript_class_methods(
                lines,
                class_name,
                start_line,
                end_line,
                normalized_path,
                language,
            )
        )

    symbols.sort(key=lambda item: (int(item["start_line"]), str(item["qualname"])))
    result["symbols"] = symbols
    return result


def extract_symbols(path: str | Path) -> dict:
    """Dispatch symbol extraction by supported source extension."""

    suffix = Path(path).suffix.lower()
    if suffix == ".py":
        return extract_python_symbols(path)
    if suffix in JS_TS_EXTENSIONS:
        return extract_javascript_symbols(path)
    return {
        "path": str(path).replace("\\", "/"),
        "language": "unknown",
        "status": "unsupported",
        "symbols": [],
    }


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
        suffix = Path(normalized_path).suffix.lower()
        if suffix != ".py" and suffix not in JS_TS_EXTENSIONS:
            continue

        file_path = root / Path(path)
        if not file_path.exists() or file_path.is_dir():
            continue

        parsed = extract_symbols(file_path)
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
        confidence = str(hint.get("confidence", "")).strip()
        confidence_reason = str(hint.get("confidence_reason", "")).strip()
        line_range = _format_line_range(start_line, end_line)
        confidence_text = ""
        if confidence:
            confidence_text = f", {confidence} confidence"
            if confidence_reason:
                confidence_text += f" ({confidence_reason})"

        lines.append(
            f"- `{file_path}`::{symbol_name} - {kind}, {line_range}"
            f"{confidence_text}, {reason}"
        )

    lines.append("")
    return lines


def build_symbol_snippets(
    root: str | Path,
    symbol_hints: list[dict] | None,
    selected_paths: list[str] | None = None,
    budget_remaining: int | None = None,
    *,
    max_snippets: int = DEFAULT_SYMBOL_SNIPPET_LIMIT,
    max_lines_per_snippet: int = DEFAULT_SYMBOL_SNIPPET_MAX_LINES,
    max_chars_per_snippet: int = DEFAULT_SYMBOL_SNIPPET_MAX_CHARS,
) -> dict:
    """Build short source snippets for non-selected matched symbols."""

    root_path = Path(root).resolve()
    hints = sorted(
        [hint for hint in (symbol_hints or []) if isinstance(hint, dict)],
        key=_symbol_snippet_sort_key,
    )
    selected_set = {
        _normalize_path(path)
        for path in (selected_paths or [])
        if str(path or "").strip()
    }
    included: list[dict] = []
    skipped: list[dict] = []
    seen: set[tuple[str, str, int, int]] = set()
    used_tokens = 0
    budget_limit = None if budget_remaining is None else max(0, int(budget_remaining))

    for hint in hints:
        if len(included) >= max_snippets:
            skipped.append(_build_symbol_snippet_skip(hint, "cap reached"))
            continue

        file_path = _normalize_path(str(hint.get("file_path", "")))
        symbol_name = str(hint.get("symbol_name") or hint.get("name") or "<unknown>")
        kind = str(hint.get("kind") or "symbol")
        start_line = _safe_int(hint.get("start_line"))
        end_line = _safe_int(hint.get("end_line"))
        reason = str(hint.get("reason") or "matched task context")

        if not file_path:
            skipped.append(_build_symbol_snippet_skip(hint, "missing file path"))
            continue

        if file_path in selected_set:
            skipped.append(_build_symbol_snippet_skip(hint, "selected file"))
            continue

        if is_generated_or_ignored_path(file_path):
            skipped.append(_build_symbol_snippet_skip(hint, "generated or ignored path"))
            continue

        if is_secret_like_path(file_path):
            skipped.append(_build_symbol_snippet_skip(hint, "secret-looking path"))
            continue

        if Path(file_path).suffix.lower() != ".py" and Path(file_path).suffix.lower() not in JS_TS_EXTENSIONS:
            skipped.append(_build_symbol_snippet_skip(hint, "unsupported file type"))
            continue

        file_path_obj = _resolve_repo_relative_path(root_path, file_path)
        if file_path_obj is None:
            skipped.append(_build_symbol_snippet_skip(hint, "file missing or outside repo root"))
            continue

        source_result = _read_symbol_snippet(
            file_path_obj,
            start_line,
            end_line,
            max_lines_per_snippet=max_lines_per_snippet,
            max_chars_per_snippet=max_chars_per_snippet,
        )
        if source_result.get("status") != "ok":
            skipped.append(
                {
                    "file_path": file_path,
                    "symbol_name": symbol_name,
                    "kind": kind,
                    "start_line": start_line,
                    "end_line": end_line,
                    "reason": reason,
                    "skip_reason": source_result.get("reason") or "snippet read failed",
                }
            )
            continue

        snippet_text = str(source_result.get("text") or "")
        estimated_tokens = estimate_tokens(snippet_text)
        if budget_limit is not None and used_tokens + estimated_tokens > budget_limit:
            skipped.append(_build_symbol_snippet_skip(hint, "budget reached"))
            continue

        record = {
            "file_path": file_path,
            "symbol_name": symbol_name,
            "kind": kind,
            "start_line": int(source_result.get("start_line") or start_line or 0),
            "end_line": int(source_result.get("end_line") or end_line or 0),
            "reason": reason,
            "text": snippet_text,
            "estimated_tokens": estimated_tokens,
            "line_count": int(source_result.get("line_count") or 0),
            "truncated": bool(source_result.get("truncated")),
        }
        key = (
            record["file_path"],
            record["symbol_name"],
            record["start_line"],
            record["end_line"],
        )
        if key in seen:
            skipped.append(_build_symbol_snippet_skip(hint, "duplicate symbol range"))
            continue

        seen.add(key)
        included.append(record)
        used_tokens += estimated_tokens

    return {
        "included": included,
        "included_count": len(included),
        "skipped": skipped,
        "skipped_count": len(skipped),
        "estimated_tokens": used_tokens,
        "budget_remaining": budget_limit,
        "max_snippets": max_snippets,
    }


def build_symbol_snippets_section(snippet_report: dict | None) -> list[str]:
    """Render the snippet section for context packs and prompts."""

    lines = ["## Symbol Snippets", ""]
    report = snippet_report or {}
    snippets = list(report.get("included", []) or [])
    skipped = list(report.get("skipped", []) or [])
    skipped_count = int(report.get("skipped_count", 0) or 0)

    if not snippets:
        lines.append("No symbol snippets included.")
        if skipped_count:
            lines.append(f"Skipped snippets: {skipped_count} skipped by budget/cap or safety filters.")
            lines.append("")
            _append_skipped_snippets(lines, skipped)
        lines.append("")
        return lines

    for snippet in snippets:
        file_path = str(snippet.get("file_path", "<unknown>"))
        symbol_name = str(snippet.get("symbol_name", "<unknown>"))
        start_line = _safe_int(snippet.get("start_line"))
        end_line = _safe_int(snippet.get("end_line"))
        reason = str(snippet.get("reason", "matched task context"))
        snippet_text = str(snippet.get("text", "")).rstrip()

        lines.append(f"### `{file_path}`::`{symbol_name}`")
        lines.append("")
        lines.append(f"Lines {start_line}-{end_line}. Reason: {reason}.")
        lines.append("")
        lines.append(f"```{_snippet_language(file_path)}")
        if snippet_text:
            lines.extend(snippet_text.splitlines())
        else:
            lines.append("")
        lines.append("```")
        lines.append("")

    if skipped_count:
        lines.append(f"Skipped snippets: {skipped_count} skipped by budget/cap or safety filters.")
        lines.append("")
        _append_skipped_snippets(lines, skipped)
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
        "language": "python",
        "confidence": "high",
        "confidence_reason": "ast",
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
        "language": "python",
        "confidence": "high",
        "confidence_reason": "ast",
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
                "language": "python",
                "confidence": "high",
                "confidence_reason": "ast",
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
        "language": str(symbol.get("language", "")),
        "confidence": str(symbol.get("confidence", "medium")),
        "confidence_reason": str(symbol.get("confidence_reason", "regex")),
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


def _javascript_language(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".tsx":
        return "tsx"
    if suffix == ".ts":
        return "typescript"
    if suffix == ".jsx":
        return "jsx"
    return "javascript"


def _javascript_symbol_kind(name: str, default_kind: str, suffix: str) -> str:
    if default_kind == "class":
        return "class"
    if name.startswith("use") and len(name) > 3 and name[3].isupper():
        return "hook"
    if suffix in {".tsx", ".jsx"} and name[:1].isupper():
        return "component"
    return "function"


def _compact_signature(line: str, parameter_text: str | None) -> str:
    if parameter_text:
        return re.sub(r"\s+", " ", parameter_text.strip())
    return re.sub(r"\s+", " ", line.strip())[:240]


def _approximate_js_symbol_end(lines: list[str], start_line: int) -> int:
    start_index = max(0, start_line - 1)
    brace_depth = 0
    saw_brace = False

    for index in range(start_index, min(len(lines), start_index + 200)):
        line = lines[index]
        brace_depth += line.count("{")
        brace_depth -= line.count("}")
        saw_brace = saw_brace or "{" in line
        if saw_brace and brace_depth <= 0:
            return index + 1
        if not saw_brace and line.rstrip().endswith(";"):
            return index + 1

    return min(len(lines), start_line + 20)


def _extract_javascript_class_methods(
    lines: list[str],
    class_name: str,
    start_line: int,
    end_line: int,
    file_path: str,
    language: str,
) -> list[dict]:
    methods = []
    method_pattern = re.compile(
        r"^\s*(?:(?:public|private|protected|static|async|readonly|abstract|override)\s+)*"
        r"(?P<name>[A-Za-z_$][\w$]*)\s*(?P<signature>\([^)]*\))"
        r"(?:\s*:\s*[^{=]+)?\s*\{"
    )

    for line_number in range(start_line + 1, min(end_line, len(lines)) + 1):
        match = method_pattern.match(lines[line_number - 1])
        if match is None or match.group("name") in {"if", "for", "while", "switch", "catch"}:
            continue
        name = match.group("name")
        methods.append(
            {
                "name": name,
                "qualname": f"{class_name}.{name}",
                "kind": "method",
                "class_name": class_name,
                "file_path": file_path,
                "start_line": line_number,
                "end_line": min(end_line, _approximate_js_symbol_end(lines, line_number)),
                "signature": _compact_signature(lines[line_number - 1], match.group("signature")),
                "language": language,
                "confidence": "medium",
                "confidence_reason": "regex",
            }
        )

    return methods


def _snippet_language(file_path: str) -> str:
    suffix = Path(file_path).suffix.lower()
    return {
        ".py": "python",
        ".ts": "typescript",
        ".tsx": "tsx",
        ".js": "javascript",
        ".jsx": "jsx",
        ".mjs": "javascript",
        ".cjs": "javascript",
    }.get(suffix, "text")


def _safe_int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _resolve_repo_relative_path(root: Path, relative_path: str) -> Path | None:
    candidate = root / Path(relative_path)

    try:
        resolved_candidate = candidate.resolve(strict=False)
    except OSError:
        return None

    try:
        resolved_candidate.relative_to(root)
    except ValueError:
        return None

    if not resolved_candidate.exists() or resolved_candidate.is_dir():
        return None

    return resolved_candidate


def _read_symbol_snippet(
    file_path: Path,
    start_line: int,
    end_line: int,
    *,
    max_lines_per_snippet: int,
    max_chars_per_snippet: int,
) -> dict:
    try:
        source_lines = file_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        return {
            "status": "read_error",
            "reason": str(error),
            "text": "",
            "start_line": 0,
            "end_line": 0,
            "line_count": 0,
            "truncated": False,
        }

    if not source_lines:
        return {
            "status": "empty",
            "reason": "empty file",
            "text": "",
            "start_line": 0,
            "end_line": 0,
            "line_count": 0,
            "truncated": False,
        }

    clamped_start = max(1, min(_safe_int(start_line) or 1, len(source_lines)))
    clamped_end = max(clamped_start, min(_safe_int(end_line) or clamped_start, len(source_lines)))

    snippet_lines = source_lines[clamped_start - 1 : clamped_end]
    if not snippet_lines:
        return {
            "status": "empty",
            "reason": "snippet range outside file",
            "text": "",
            "start_line": clamped_start,
            "end_line": clamped_end,
            "line_count": 0,
            "truncated": False,
        }

    truncated = False
    if len(snippet_lines) > max_lines_per_snippet:
        snippet_lines = snippet_lines[:max_lines_per_snippet]
        clamped_end = clamped_start + len(snippet_lines) - 1
        truncated = True

    snippet_text = "\n".join(snippet_lines)
    marker = "# ... snippet truncated to fit Strata budget ..."
    if len(snippet_text) > max_chars_per_snippet:
        text_limit = max(0, max_chars_per_snippet - len(marker) - 1)
        snippet_text = snippet_text[:text_limit].rstrip()
        truncated = True
        if snippet_text:
            snippet_text = f"{snippet_text}\n{marker}"
        else:
            snippet_text = marker

    if truncated and not snippet_text.rstrip().endswith(marker):
        snippet_text = f"{snippet_text.rstrip()}\n{marker}"

    return {
        "status": "ok",
        "reason": None,
        "text": snippet_text,
        "start_line": clamped_start,
        "end_line": clamped_end,
        "line_count": len(snippet_lines),
        "truncated": truncated,
    }


def _build_symbol_snippet_skip(hint: dict, skip_reason: str) -> dict:
    if not isinstance(hint, dict):
        hint = {}

    return {
        "file_path": _normalize_path(str(hint.get("file_path", ""))),
        "symbol_name": str(hint.get("symbol_name") or hint.get("name") or "<unknown>"),
        "kind": str(hint.get("kind") or "symbol"),
        "start_line": _safe_int(hint.get("start_line")),
        "end_line": _safe_int(hint.get("end_line")),
        "reason": str(hint.get("reason") or "matched task context"),
        "skip_reason": skip_reason,
    }


def _append_skipped_snippets(lines: list[str], skipped: list[dict], *, max_items: int = DEFAULT_SYMBOL_SNIPPET_SKIPPED_LIMIT) -> None:
    if not skipped:
        return

    for skipped_item in skipped[:max_items]:
        file_path = str(skipped_item.get("file_path", "<unknown>"))
        symbol_name = str(skipped_item.get("symbol_name", "<unknown>"))
        skip_reason = str(skipped_item.get("skip_reason", "skipped"))
        lines.append(f"- `{file_path}`::{symbol_name} - {skip_reason}")

    if len(skipped) > max_items:
        lines.append(f"- ...and {len(skipped) - max_items} more")


def _symbol_snippet_sort_key(hint: dict) -> tuple:
    return (
        int(hint.get("priority", 99)),
        -int(hint.get("score", 0)),
        -int(hint.get("matched_term_count", 0)),
        _normalize_path(str(hint.get("file_path", ""))),
        str(hint.get("symbol_name") or hint.get("name") or "<unknown>"),
        int(hint.get("start_line", 0) or 0),
        int(hint.get("end_line", 0) or 0),
    )


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
