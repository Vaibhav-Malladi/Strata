"""Selected-file backend journey tracing for Part P5.

This module continues supplied backend route steps through explicitly selected
backend files only. It does not recursively scan repositories, execute code,
resolve packages, run language tools, or trace runtime dependency injection.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import ast
import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

import strata.utils.user_journey as user_journey


DEFAULT_MAX_FILES = 120
DEFAULT_MAX_BYTES_PER_FILE = 512 * 1024
DEFAULT_MAX_STEPS = 120
DEFAULT_MAX_TRANSITIONS = 240
DEFAULT_MAX_DEPTH = 10
DEFAULT_MAX_OUTGOING_LINKS_PER_STEP = 12
SUPPORTED_EXTENSIONS = (".py", ".go", ".js", ".ts")
PY_ROUTE_DECORATOR = re.compile(r"@(?:[A-Za-z_$][\w$.]*)\.(?:get|post|put|patch|delete|route|api_route)\s*\([^)]*\)\s*\n\s*(?:async\s+)?def\s+(?P<name>[A-Za-z_][\w]*)", re.IGNORECASE)
JS_ROUTE = re.compile(r"\b(?:app|router)\.(?:get|post|put|patch|delete|use)\s*\(\s*['\"][^'\"]+['\"]\s*,\s*(?P<handler>[A-Za-z_$][\w$]*)?", re.IGNORECASE)
GO_ROUTE = re.compile(r"\b(?:http\.HandleFunc|(?:r|router|mux)\.(?:Get|Post|Put|Patch|Delete|HandleFunc))\s*\(\s*['\"][^'\"]+['\"]\s*,\s*(?P<handler>[A-Za-z_][\w.]*)", re.IGNORECASE)
GO_FUNC = re.compile(r"\bfunc\s+(?:\([^)]+\)\s*)?(?P<name>[A-Za-z_][\w]*)\s*\([^)]*\)\s*\{")
JS_FUNC = re.compile(r"(?:async\s+)?function\s+(?P<fn>[A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{|(?:const|let|var)\s+(?P<const>[A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>\s*\{")
CALL = re.compile(r"(?<![\w$.])(?P<name>[A-Za-z_$][\w$]*)\s*\(|(?P<object>[A-Za-z_$][\w$]*(?:\s*\.\s*[A-Za-z_$][\w$]*)*)\s*\.\s*(?P<method>[A-Za-z_$][\w$]*)\s*\(")
DYNAMIC_CALL = re.compile(r"\[[^\]]+\]\s*\(|\b[A-Za-z_$][\w$]*\s*\[\s*[^]]+\s*\]\s*\(")
BUILTINS = {"if", "for", "while", "switch", "return", "catch", "len", "print", "range", "append"}


@dataclass(frozen=True, slots=True)
class SelectedBackendSource:
    path: str
    text: str
    extension: str


@dataclass(frozen=True, slots=True)
class BackendSymbol:
    name: str
    path: str
    body: str
    language: str


def trace_backend_journey(
    request: user_journey.JourneyRequest | Mapping[str, Any],
    route_steps: Iterable[user_journey.JourneyStep | Mapping[str, Any]],
    repository_id: str,
    repository_root: str | Path,
    selected_paths: Iterable[str],
    *,
    max_files: int = DEFAULT_MAX_FILES,
    max_bytes_per_file: int = DEFAULT_MAX_BYTES_PER_FILE,
    max_steps: int = DEFAULT_MAX_STEPS,
    max_transitions: int = DEFAULT_MAX_TRANSITIONS,
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_outgoing_links_per_step: int = DEFAULT_MAX_OUTGOING_LINKS_PER_STEP,
) -> user_journey.UserJourneyResult:
    """Trace backend implementation from supplied backend route steps."""

    request = _coerce_request(request)
    repository_id = _nonempty(repository_id, "repository_id")
    diagnostics: list[user_journey.JourneyDiagnostic] = []
    sources = _load_sources(repository_root, selected_paths, diagnostics, max_files=max_files, max_bytes_per_file=max_bytes_per_file)
    symbols = _symbol_index(sources)
    routes = tuple(_coerce_step(step) for step in route_steps)
    steps: list[user_journey.JourneyStep] = list(routes)
    transitions: list[user_journey.JourneyTransition] = []
    gaps: list[user_journey.JourneyGap] = []

    for index, route in enumerate(sorted(routes, key=user_journey.step_sort_key)):
        handler = _handler_for_route(route, sources) or route.symbol
        if not handler:
            gaps.append(_gap(user_journey.GAP_REASON_SYMBOL_NOT_FOUND, "Backend route has no statically traceable handler.", route.step_id, route.path, route.symbol))
            continue
        handler_step = _step(repository_id, route.path, handler, user_journey.STEP_TYPE_BACKEND_HANDLER, f"Handle backend route with {handler}.", 0.88, index + 1, f"handler:{handler}")
        steps.append(handler_step)
        transitions.append(_transition(route.step_id, handler_step.step_id, user_journey.TRANSITION_TYPE_HANDLES, 0.88))
        _trace_symbol(handler, handler_step, symbols, steps, transitions, gaps, diagnostics, repository_id, depth=1, max_depth=max_depth, max_outgoing=max_outgoing_links_per_step)

    return user_journey.build_user_journey_result(request, steps=steps, transitions=transitions, gaps=gaps, diagnostics=diagnostics, max_steps=max_steps, max_transitions=max_transitions)


def _trace_symbol(
    symbol: str,
    source_step: user_journey.JourneyStep,
    symbols: Mapping[str, tuple[BackendSymbol, ...]],
    steps: list[user_journey.JourneyStep],
    transitions: list[user_journey.JourneyTransition],
    gaps: list[user_journey.JourneyGap],
    diagnostics: list[user_journey.JourneyDiagnostic],
    repository_id: str,
    *,
    depth: int,
    max_depth: int,
    max_outgoing: int,
) -> None:
    if depth > max_depth:
        gaps.append(_gap(user_journey.GAP_REASON_STEP_CAP_REACHED, "Backend trace depth cap was reached.", source_step.step_id, source_step.path, source_step.symbol))
        diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_BACKEND_TRACE_DEPTH_CAP_REACHED, user_journey.DIAGNOSTIC_SEVERITY_WARNING, "Backend trace depth cap was reached.", path=source_step.path, details={"symbol": source_step.symbol, "max_depth": max_depth}))
        return
    definitions = _definitions_for_symbol(symbol, symbols)
    if not definitions:
        gaps.append(_gap(user_journey.GAP_REASON_SYMBOL_NOT_FOUND, f"Could not find backend symbol {symbol}.", source_step.step_id, source_step.path, symbol))
        diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_BACKEND_SYMBOL_NOT_FOUND, user_journey.DIAGNOSTIC_SEVERITY_WARNING, "Backend symbol was not found.", path=source_step.path, details={"symbol": symbol}))
        return
    definition = definitions[0]
    if DYNAMIC_CALL.search(definition.body):
        gaps.append(_gap(user_journey.GAP_REASON_DYNAMIC_CALL_UNRESOLVED, "Dynamic backend dispatch could not be resolved statically.", source_step.step_id, definition.path, symbol))
        diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_BACKEND_DYNAMIC_CALL_UNRESOLVED, user_journey.DIAGNOSTIC_SEVERITY_WARNING, "Dynamic backend dispatch could not be resolved statically.", path=definition.path, details={"symbol": symbol}))
    outgoing = 0
    response_step = _response_step(definition, repository_id, source_step.sequence_hint + 40)
    for call in _calls_from_definition(definition):
        if outgoing >= max_outgoing:
            gaps.append(_gap(user_journey.GAP_REASON_STEP_CAP_REACHED, "Outgoing backend link cap was reached.", source_step.step_id, definition.path, symbol))
            diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_BACKEND_STEP_CAP_REACHED, user_journey.DIAGNOSTIC_SEVERITY_WARNING, "Outgoing backend link cap was reached.", path=definition.path, details={"symbol": symbol, "limit": max_outgoing}))
            break
        if call in BUILTINS or call == symbol:
            continue
        step_type, score = classify_backend_symbol(call, definition.path)
        called_step = _step(
            repository_id,
            definition.path,
            call,
            step_type,
            f"Backend call {call}.",
            score,
            source_step.sequence_hint + 10 + outgoing,
            f"backend-call:{call}",
            evidence=(_call_evidence(repository_id, definition.path, symbol, call),),
        )
        steps.append(called_step)
        transitions.append(_transition(source_step.step_id, called_step.step_id, user_journey.TRANSITION_TYPE_CALLS, min(0.82, score)))
        outgoing += 1
        if _definitions_for_symbol(call, symbols) and step_type in {user_journey.STEP_TYPE_BACKEND_SERVICE, user_journey.STEP_TYPE_BUSINESS_LOGIC, user_journey.STEP_TYPE_VALIDATION, user_journey.STEP_TYPE_AUTHENTICATION, user_journey.STEP_TYPE_AUTHORIZATION}:
            if depth < max_depth:
                _trace_symbol(call, called_step, symbols, steps, transitions, gaps, diagnostics, repository_id, depth=depth + 1, max_depth=max_depth, max_outgoing=max_outgoing)
            else:
                gaps.append(_gap(user_journey.GAP_REASON_STEP_CAP_REACHED, "Backend trace depth cap was reached.", called_step.step_id, definition.path, call))
                diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_BACKEND_TRACE_DEPTH_CAP_REACHED, user_journey.DIAGNOSTIC_SEVERITY_WARNING, "Backend trace depth cap was reached.", path=definition.path, details={"symbol": call, "max_depth": max_depth}))
    if response_step:
        steps.append(response_step)
        transitions.append(_transition(source_step.step_id, response_step.step_id, user_journey.TRANSITION_TYPE_RETURNS_RESPONSE, 0.78))


def classify_backend_symbol(symbol: str, path: str | None = None) -> tuple[str, float]:
    text = f"{symbol} {path or ''}".lower()
    parts = _symbol_parts(symbol)
    if _is_validation_symbol(symbol):
        return user_journey.STEP_TYPE_VALIDATION, 0.68
    if _has_any_part(parts, {"authorize", "authorization", "permission", "role", "policy"}):
        return user_journey.STEP_TYPE_AUTHORIZATION, 0.7
    if _has_any_part(parts, {"authenticate", "authentication", "auth", "login", "token", "session"}):
        return user_journey.STEP_TYPE_AUTHENTICATION, 0.68
    if _has_any_part(parts, {"repository", "repo", "dao", "db", "orm", "store", "query", "insert", "select"}):
        return user_journey.STEP_TYPE_DATABASE_ACCESS, 0.66
    if _has_any_part(parts, {"cache", "redis", "memo"}):
        return user_journey.STEP_TYPE_CACHE_ACCESS, 0.64
    if _has_any_part(parts, {"publish", "enqueue", "sendmessage", "queue"}):
        return user_journey.STEP_TYPE_QUEUE_PUBLISH, 0.64
    if any(word in text for word in ("requests", "http", "client", "fetch", "axios", "external")):
        return user_journey.STEP_TYPE_EXTERNAL_SERVICE, 0.64
    if _is_response_symbol(parts):
        return user_journey.STEP_TYPE_RESPONSE, 0.7
    if _has_any_part(parts, {"service", "svc", "usecase", "manager", "processor", "workflow", "interactor"}) or _contains_terms(parts, ("use", "case")):
        return user_journey.STEP_TYPE_BACKEND_SERVICE, 0.66
    return user_journey.STEP_TYPE_BUSINESS_LOGIC, 0.55


def _is_validation_symbol(symbol: str) -> bool:
    parts = _symbol_parts(symbol)
    if any(part in {"validate", "validator", "validation", "schema", "parse"} for part in parts):
        return True
    return any(_contains_terms(parts, terms) for terms in (("model", "validate"), ("parse", "obj"), ("check", "input"), ("verify", "input")))


def _is_response_symbol(parts: tuple[str, ...]) -> bool:
    return _has_any_part(parts, {"json", "response", "send", "status", "writeheader", "encode", "error"}) or _contains_terms(parts, ("write", "header"))


def _has_any_part(parts: tuple[str, ...], expected: set[str]) -> bool:
    return any(part in expected for part in parts)


def _symbol_parts(symbol: str) -> tuple[str, ...]:
    normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", symbol).lower()
    return tuple(part for part in re.split(r"[^a-z0-9]+", normalized) if part)


def _contains_terms(parts: tuple[str, ...], terms: tuple[str, ...]) -> bool:
    if len(parts) < len(terms):
        return False
    return any(parts[index : index + len(terms)] == terms for index in range(len(parts) - len(terms) + 1))


def _response_step(definition: BackendSymbol, repository_id: str, sequence_hint: int) -> user_journey.JourneyStep | None:
    if re.search(r"\b(json|response|send|status|writeheader|encode|return)\b", definition.body, re.IGNORECASE):
        return _step(repository_id, definition.path, "response", user_journey.STEP_TYPE_RESPONSE, "Construct backend response.", 0.7, sequence_hint, f"response:{definition.name}:{definition.path}")
    return None


def _symbol_index(sources: tuple[SelectedBackendSource, ...]) -> dict[str, tuple[BackendSymbol, ...]]:
    values: dict[str, list[BackendSymbol]] = {}
    for source in sources:
        for symbol in _symbols_from_source(source):
            values.setdefault(symbol.name, []).append(symbol)
    return {key: tuple(sorted(items, key=lambda item: (item.path, item.name))) for key, items in sorted(values.items())}


def _definitions_for_symbol(symbol: str, symbols: Mapping[str, tuple[BackendSymbol, ...]]) -> tuple[BackendSymbol, ...]:
    if symbol in symbols:
        return symbols[symbol]
    method = symbol.rsplit(".", 1)[-1]
    return symbols.get(method, ())


def _symbols_from_source(source: SelectedBackendSource) -> tuple[BackendSymbol, ...]:
    if source.extension == ".py":
        return _python_symbols(source)
    if source.extension == ".go":
        return _regex_symbols(source, GO_FUNC, "go")
    return _regex_symbols(source, JS_FUNC, "js_ts")


def _python_symbols(source: SelectedBackendSource) -> tuple[BackendSymbol, ...]:
    try:
        tree = ast.parse(source.text)
    except SyntaxError:
        return ()
    lines = source.text.splitlines()
    symbols = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start = max(node.lineno - 1, 0)
            end = getattr(node, "end_lineno", node.lineno)
            body = "\n".join(lines[start:end])
            symbols.append(BackendSymbol(node.name, source.path, body, "python"))
    return tuple(sorted(symbols, key=lambda item: item.name))


def _regex_symbols(source: SelectedBackendSource, pattern: re.Pattern[str], language: str) -> tuple[BackendSymbol, ...]:
    symbols = []
    for match in pattern.finditer(source.text):
        name = match.groupdict().get("name") or match.groupdict().get("fn") or match.groupdict().get("const")
        if name:
            symbols.append(BackendSymbol(name.rsplit(".", 1)[-1], source.path, _brace_body(source.text, match.end() - 1), language))
    return tuple(sorted(symbols, key=lambda item: item.name))


def _handler_for_route(route: user_journey.JourneyStep, sources: tuple[SelectedBackendSource, ...]) -> str | None:
    path_filter = route.path
    candidates = [source for source in sources if path_filter is None or source.path == path_filter]
    if path_filter is not None and not candidates:
        candidates = list(sources)
    for source in candidates:
        route_path = str((route.metadata or {}).get("route_path") or route.symbol or "")
        patterns = (PY_ROUTE_DECORATOR, JS_ROUTE, GO_ROUTE)
        for pattern in patterns:
            for match in pattern.finditer(source.text):
                if route_path and route_path not in match.group(0):
                    continue
                name = match.groupdict().get("name") or match.groupdict().get("handler")
                if name:
                    return name.rsplit(".", 1)[-1]
    return None


def _calls_from_definition(definition: BackendSymbol) -> tuple[str, ...]:
    if definition.language == "python":
        return _python_calls(definition)
    return _calls(definition.body)


def _python_calls(definition: BackendSymbol) -> tuple[str, ...]:
    try:
        tree = ast.parse(definition.body)
    except SyntaxError:
        return _calls(definition.body)
    function = next((node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == definition.name), None)
    if function is None:
        return ()
    values: list[str] = []
    seen: set[str] = set()

    def visit(node: ast.AST) -> None:
        if node is not function and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            return
        if isinstance(node, ast.Call):
            name = _python_callee_name(node.func)
            if name and name not in BUILTINS and name not in seen:
                values.append(name)
                seen.add(name)
        for child in ast.iter_child_nodes(node):
            visit(child)

    for statement in function.body:
        visit(statement)
    return tuple(values)


def _python_callee_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _python_callee_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return None


def _calls(body: str) -> tuple[str, ...]:
    values = []
    seen = set()
    for match in CALL.finditer(body):
        if match.group("method"):
            receiver = re.sub(r"\s+", "", match.group("object"))
            name = f"{receiver}.{match.group('method')}"
        else:
            name = match.group("name")
        if name and name not in BUILTINS and name not in seen:
            values.append(name)
            seen.add(name)
    return tuple(values)


def _brace_body(text: str, open_brace: int) -> str:
    depth = 0
    for index in range(open_brace, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[open_brace + 1 : index]
    return text[open_brace + 1 : open_brace + 2000]


def _load_sources(root_value: str | Path, selected_paths: Iterable[str], diagnostics: list[user_journey.JourneyDiagnostic], *, max_files: int, max_bytes_per_file: int) -> tuple[SelectedBackendSource, ...]:
    root = Path(root_value).resolve()
    selected = tuple(selected_paths)
    if len(selected) > max_files:
        diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_BACKEND_STEP_CAP_REACHED, user_journey.DIAGNOSTIC_SEVERITY_WARNING, "Selected backend file cap was reached.", details={"limit": max_files, "omitted": len(selected) - max_files}))
    sources: list[SelectedBackendSource] = []
    for raw_path in selected[:max_files]:
        normalized = _normalize_selected_path(str(raw_path), diagnostics)
        if normalized is None:
            continue
        path = (root / normalized).resolve()
        if not _is_relative_to(path, root):
            diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_ENTRY_SELECTED_PATH_OUTSIDE_REPOSITORY, user_journey.DIAGNOSTIC_SEVERITY_ERROR, "Selected backend path is outside the repository.", details={"selected_path": str(raw_path)}))
            continue
        if not path.exists():
            diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_ENTRY_SELECTED_PATH_MISSING, user_journey.DIAGNOSTIC_SEVERITY_WARNING, "Selected backend path does not exist.", path=normalized))
            continue
        extension = path.suffix.lower()
        if extension not in SUPPORTED_EXTENSIONS:
            diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_BACKEND_UNSUPPORTED_FILE, user_journey.DIAGNOSTIC_SEVERITY_INFO, "Selected backend file type is unsupported.", path=normalized))
            continue
        try:
            size = path.stat().st_size
        except OSError:
            diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_BACKEND_FILE_UNREADABLE, user_journey.DIAGNOSTIC_SEVERITY_WARNING, "Selected backend file could not be read.", path=normalized))
            continue
        if size > max_bytes_per_file:
            diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_BACKEND_FILE_TOO_LARGE, user_journey.DIAGNOSTIC_SEVERITY_WARNING, "Selected backend file exceeded the byte cap.", path=normalized))
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_BACKEND_FILE_UNREADABLE, user_journey.DIAGNOSTIC_SEVERITY_WARNING, "Selected backend file could not be read.", path=normalized))
            continue
        sources.append(SelectedBackendSource(normalized, text, extension))
    return tuple(sorted(sources, key=lambda item: item.path))


def _normalize_selected_path(raw_path: str, diagnostics: list[user_journey.JourneyDiagnostic]) -> str | None:
    try:
        text = _nonempty(raw_path, "selected_path")
        windows = PureWindowsPath(text)
        posix = PurePosixPath(text.replace("\\", "/"))
        if windows.drive or windows.is_absolute() or posix.is_absolute():
            raise ValueError("selected path must be relative")
        parts = []
        for part in posix.parts:
            if part in ("", "."):
                continue
            if part == "..":
                if parts:
                    parts.pop()
                else:
                    raise ValueError("selected path escapes repository")
                continue
            parts.append(part)
        return PurePosixPath(*parts).as_posix()
    except Exception:
        diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_ENTRY_SELECTED_PATH_INVALID, user_journey.DIAGNOSTIC_SEVERITY_ERROR, "Selected backend path is invalid.", details={"selected_path": str(raw_path)}))
        return None


def _step(
    repository_id: str,
    path: str | None,
    symbol: str | None,
    step_type: str,
    summary: str,
    score: float,
    sequence_hint: int,
    discriminator: str,
    *,
    evidence: tuple[user_journey.JourneyEvidence, ...] = (),
) -> user_journey.JourneyStep:
    return user_journey.JourneyStep(repository_id=repository_id, path=path, symbol=symbol, step_type=step_type, summary=summary, confidence=user_journey.confidence_from_score(score), confidence_score=score, sequence_hint=sequence_hint, evidence=evidence, origin=user_journey.ORIGIN_INFERRED, semantic_discriminator=discriminator)


def _call_evidence(repository_id: str, path: str, caller: str, callee: str) -> user_journey.JourneyEvidence:
    return user_journey.JourneyEvidence(
        signal_type="direct_backend_call",
        repository_id=repository_id,
        path=path,
        symbol=callee,
        summary=f"{caller} calls {callee}.",
        strength=user_journey.EVIDENCE_STRENGTH_MEDIUM,
    )


def _transition(source: str, target: str, transition_type: str, score: float) -> user_journey.JourneyTransition:
    return user_journey.JourneyTransition(source, target, transition_type, user_journey.confidence_from_score(score), score, origin=user_journey.ORIGIN_INFERRED)


def _gap(reason: str, summary: str, source_step_id: str | None, path: str | None, symbol: str | None) -> user_journey.JourneyGap:
    return user_journey.JourneyGap(reason=reason, summary=summary, severity=user_journey.DIAGNOSTIC_SEVERITY_WARNING, source_step_id=source_step_id, path=path, symbol=symbol)


def _diagnostic(code: str, severity: str, summary: str, *, path: str | None = None, details: Mapping[str, Any] | None = None) -> user_journey.JourneyDiagnostic:
    return user_journey.JourneyDiagnostic(code=code, severity=severity, summary=summary, path=path, details=details)


def _coerce_request(value: user_journey.JourneyRequest | Mapping[str, Any]) -> user_journey.JourneyRequest:
    if isinstance(value, user_journey.JourneyRequest):
        return value
    return user_journey.JourneyRequest(**dict(value))


def _coerce_step(value: user_journey.JourneyStep | Mapping[str, Any]) -> user_journey.JourneyStep:
    if isinstance(value, user_journey.JourneyStep):
        return value
    return user_journey.JourneyStep(**dict(value))


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _nonempty(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise user_journey.UserJourneyError(f"{name} must be a non-empty string")
    return value.strip()
