"""Selected-file frontend journey tracing for Part P3.

Tracing is bounded to supplied entry points and supplied frontend files. This
module does not search whole repositories, execute JavaScript, resolve runtime
framework behavior, traverse workspaces, or trace backend handlers.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import re
from pathlib import Path
from typing import Any

import strata.utils.journey_entry_points as journey_entry_points
import strata.utils.user_journey as user_journey


DEFAULT_MAX_FILES = 100
DEFAULT_MAX_BYTES_PER_FILE = 512 * 1024
DEFAULT_MAX_STEPS = 100
DEFAULT_MAX_TRANSITIONS = 200
DEFAULT_MAX_DEPTH = 8
DEFAULT_MAX_OUTGOING_LINKS_PER_STEP = 12
SUPPORTED_FRONTEND_EXTENSIONS = (".html", ".htm", ".js", ".jsx", ".ts", ".tsx")
CALL_PATTERN = re.compile(r"(?<![\w$.])(?P<name>[A-Za-z_$][\w$]*)\s*\(|(?P<object>[A-Za-z_$][\w$]*)\s*\.\s*(?P<method>[A-Za-z_$][\w$]*)\s*\(")
FUNCTION_HEADER_PATTERN = re.compile(
    r"(?:export\s+)?(?:async\s+)?function\s+(?P<fn>[A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{|"
    r"(?:const|let|var)\s+(?P<const>[A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>\s*\{|"
    r"^\s*(?P<method>[A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{",
    re.MULTILINE,
)
IMPORT_PATTERN = re.compile(r"import\s+(?P<what>[\s\S]*?)\s+from\s+['\"](?P<path>[^'\"]+)['\"]", re.MULTILINE)
FETCH_PATTERN = re.compile(r"\bfetch\s*\(\s*['\"](?P<url>[^'\"]+)['\"](?:\s*,\s*\{(?P<options>[\s\S]{0,400}?)\})?", re.IGNORECASE)
AXIOS_PATTERN = re.compile(r"\baxios(?:\.(?P<method>get|post|put|patch|delete))?\s*\(\s*['\"](?P<url>[^'\"]+)['\"]", re.IGNORECASE)
HTTP_CLIENT_PATTERN = re.compile(r"\b(?:this\.)?(?:http|httpClient)\s*\.\s*(?P<method>get|post|put|patch|delete)\s*\(\s*['\"](?P<url>[^'\"]+)['\"]", re.IGNORECASE)
NAVIGATION_PATTERN = re.compile(r"\b(?:navigate|router\.navigate|this\.router\.navigate|history\.push)\s*\(\s*(?P<target>[^)]{0,160})\)", re.IGNORECASE)
STATE_PATTERN = re.compile(r"\b(?P<name>set[A-Z][\w$]*|dispatch)\s*\(")
DYNAMIC_CALL_PATTERN = re.compile(r"\[[^\]]+\]\s*\(|\b[A-Za-z_$][\w$]*\s*\[\s*[^]]+\s*\]\s*\(")
BUILTIN_CALLS = {
    "if",
    "for",
    "while",
    "switch",
    "return",
    "catch",
    "map",
    "then",
    "subscribe",
    "console",
    "fetch",
    "setTimeout",
}


@dataclass(frozen=True, slots=True)
class _FunctionDef:
    name: str
    path: str
    body: str


def trace_frontend_journey(
    request: user_journey.JourneyRequest | Mapping[str, Any],
    entry_points: Iterable[user_journey.JourneyEntryPoint | Mapping[str, Any]],
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
    """Trace frontend flow from supplied entry points through selected files."""

    normalized_request = _coerce_request(request)
    repository_id = _nonempty(repository_id, "repository_id")
    diagnostics: list[user_journey.JourneyDiagnostic] = []
    sources = journey_entry_points.load_selected_sources(
        repository_root,
        tuple(selected_paths),
        diagnostics,
        max_files=max_files,
        max_bytes_per_file=max_bytes_per_file,
        unsupported_code=user_journey.DIAGNOSTIC_FRONTEND_UNSUPPORTED_FILE,
        too_large_code=user_journey.DIAGNOSTIC_FRONTEND_FILE_TOO_LARGE,
        unreadable_code=user_journey.DIAGNOSTIC_FRONTEND_FILE_UNREADABLE,
    )
    sources = tuple(source for source in sources if source.extension in SUPPORTED_FRONTEND_EXTENSIONS)
    functions = _function_index(sources)
    imports = _import_index(sources)
    entries = tuple(_coerce_entry_point(item) for item in entry_points)
    steps: list[user_journey.JourneyStep] = []
    transitions: list[user_journey.JourneyTransition] = []
    gaps: list[user_journey.JourneyGap] = []

    for index, entry in enumerate(sorted(entries, key=user_journey.entry_point_sort_key)):
        entry_step = _step(repository_id, entry.path, entry.symbol, user_journey.STEP_TYPE_USER_ACTION, f"User action starts at {entry.display_label}.", 0.9, index, "entry", evidence=entry.evidence)
        steps.append(entry_step)
        handler = _entry_handler(entry)
        if not handler:
            gaps.append(_gap(user_journey.GAP_REASON_SYMBOL_NOT_FOUND, "Entry point has no statically traceable handler.", entry_step.step_id, entry.path, entry.symbol))
            continue
        handler_step = _step(repository_id, entry.path, handler, user_journey.STEP_TYPE_UI_EVENT_HANDLER, f"Handle user event with {handler}.", 0.86, index + 1, f"handler:{handler}", evidence=entry.evidence)
        steps.append(handler_step)
        transitions.append(_transition(entry_step.step_id, handler_step.step_id, user_journey.TRANSITION_TYPE_HANDLES, 0.86, repository_id, entry.path, "entry_handler"))
        _trace_symbol(
            handler,
            handler_step,
            functions,
            imports,
            steps,
            transitions,
            gaps,
            repository_id,
            depth=1,
            max_depth=max_depth,
            max_outgoing=max_outgoing_links_per_step,
        )

    return user_journey.build_user_journey_result(
        normalized_request,
        entry_points=entries,
        steps=steps,
        transitions=transitions,
        gaps=gaps,
        diagnostics=diagnostics,
        max_steps=max_steps,
        max_transitions=max_transitions,
    )


def _trace_symbol(
    symbol: str,
    source_step: user_journey.JourneyStep,
    functions: Mapping[str, tuple[_FunctionDef, ...]],
    imports: Mapping[str, str],
    steps: list[user_journey.JourneyStep],
    transitions: list[user_journey.JourneyTransition],
    gaps: list[user_journey.JourneyGap],
    repository_id: str,
    *,
    depth: int,
    max_depth: int,
    max_outgoing: int,
) -> None:
    if depth > max_depth:
        gaps.append(_gap(user_journey.GAP_REASON_STEP_CAP_REACHED, "Frontend trace depth cap was reached.", source_step.step_id, source_step.path, source_step.symbol))
        return
    defs = functions.get(symbol, ())
    if not defs:
        gaps.append(_gap(user_journey.GAP_REASON_SYMBOL_NOT_FOUND, f"Could not find frontend symbol {symbol}.", source_step.step_id, source_step.path, symbol))
        return
    body = defs[0].body
    if DYNAMIC_CALL_PATTERN.search(body):
        gaps.append(_gap(user_journey.GAP_REASON_DYNAMIC_CALL_UNRESOLVED, "Dynamic frontend call could not be resolved statically.", source_step.step_id, defs[0].path, symbol))
    outgoing = 0
    for api in _api_requests(body):
        if outgoing >= max_outgoing:
            gaps.append(_gap(user_journey.GAP_REASON_STEP_CAP_REACHED, "Outgoing frontend link cap was reached.", source_step.step_id, defs[0].path, symbol))
            break
        api_client = _step(repository_id, defs[0].path, api["symbol"], user_journey.STEP_TYPE_API_CLIENT, f"Call frontend API client {api['symbol']}.", 0.78, depth + 10, f"api-client:{api['symbol']}:{api['url']}")
        api_request = _step(repository_id, defs[0].path, api["url"], user_journey.STEP_TYPE_API_REQUEST, f"Send {api['method']} request to {api['url']}.", 0.86, depth + 11, f"api-request:{api['method']}:{api['url']}", metadata={"http_method": api["method"], "url": api["url"], "route_path": api["route_path"]})
        steps.extend((api_client, api_request))
        transitions.append(_transition(source_step.step_id, api_client.step_id, user_journey.TRANSITION_TYPE_CALLS, 0.75, repository_id, defs[0].path, "api_client"))
        transitions.append(_transition(api_client.step_id, api_request.step_id, user_journey.TRANSITION_TYPE_SENDS_REQUEST, 0.86, repository_id, defs[0].path, "api_request"))
        outgoing += 1
    for state in _state_updates(body):
        state_step = _step(repository_id, defs[0].path, state, user_journey.STEP_TYPE_FRONTEND_STATE, f"Update frontend state via {state}.", 0.72, depth + 20, f"state:{state}")
        steps.append(state_step)
        transition_type = user_journey.TRANSITION_TYPE_DISPATCHES if state == "dispatch" else user_journey.TRANSITION_TYPE_WRITES_STATE
        transitions.append(_transition(source_step.step_id, state_step.step_id, transition_type, 0.72, repository_id, defs[0].path, "state_update"))
    for target in _navigations(body):
        nav_step = _step(repository_id, defs[0].path, target, user_journey.STEP_TYPE_NAVIGATION, f"Navigate to {target}.", 0.74, depth + 30, f"navigation:{target}", metadata={"route_path": target})
        steps.append(nav_step)
        transitions.append(_transition(source_step.step_id, nav_step.step_id, user_journey.TRANSITION_TYPE_NAVIGATES_TO, 0.74, repository_id, defs[0].path, "navigation"))
    for call in _function_calls(body):
        if outgoing >= max_outgoing:
            gaps.append(_gap(user_journey.GAP_REASON_STEP_CAP_REACHED, "Outgoing frontend link cap was reached.", source_step.step_id, defs[0].path, symbol))
            break
        if call in BUILTIN_CALLS or call == symbol:
            continue
        step_type = user_journey.STEP_TYPE_FRONTEND_SERVICE if call in imports or _service_like(call) else user_journey.STEP_TYPE_COMPONENT_METHOD
        called_step = _step(repository_id, defs[0].path, call, step_type, f"Call frontend symbol {call}.", 0.68 if step_type == user_journey.STEP_TYPE_FRONTEND_SERVICE else 0.62, depth + 40, f"call:{call}")
        steps.append(called_step)
        transitions.append(_transition(source_step.step_id, called_step.step_id, user_journey.TRANSITION_TYPE_CALLS, 0.66, repository_id, defs[0].path, "function_call"))
        outgoing += 1
        if call in functions and depth < max_depth:
            _trace_symbol(call, called_step, functions, imports, steps, transitions, gaps, repository_id, depth=depth + 1, max_depth=max_depth, max_outgoing=max_outgoing)
        elif call in imports:
            _trace_imported_service(call, called_step, functions, steps, transitions, gaps, repository_id, depth + 1, max_depth)


def _trace_imported_service(
    call: str,
    source_step: user_journey.JourneyStep,
    functions: Mapping[str, tuple[_FunctionDef, ...]],
    steps: list[user_journey.JourneyStep],
    transitions: list[user_journey.JourneyTransition],
    gaps: list[user_journey.JourneyGap],
    repository_id: str,
    depth: int,
    max_depth: int,
) -> None:
    if depth > max_depth:
        gaps.append(_gap(user_journey.GAP_REASON_STEP_CAP_REACHED, "Frontend trace depth cap was reached.", source_step.step_id, source_step.path, source_step.symbol))
        return
    candidates = functions.get(call, ())
    if not candidates:
        return
    service = candidates[0]
    for api in _api_requests(service.body):
        request_step = _step(repository_id, service.path, api["url"], user_journey.STEP_TYPE_API_REQUEST, f"Send {api['method']} request to {api['url']}.", 0.82, depth + 50, f"service-api:{call}:{api['method']}:{api['url']}", metadata={"http_method": api["method"], "url": api["url"], "route_path": api["route_path"]})
        steps.append(request_step)
        transitions.append(_transition(source_step.step_id, request_step.step_id, user_journey.TRANSITION_TYPE_SENDS_REQUEST, 0.82, repository_id, service.path, "service_http_call"))


def _function_index(sources: tuple[journey_entry_points.SelectedSource, ...]) -> dict[str, tuple[_FunctionDef, ...]]:
    values: dict[str, list[_FunctionDef]] = {}
    for source in sources:
        for match in FUNCTION_HEADER_PATTERN.finditer(source.text):
            name = match.group("fn") or match.group("const") or match.group("method")
            if not name or name in BUILTIN_CALLS:
                continue
            body = _brace_body(source.text, match.end() - 1)
            values.setdefault(name, []).append(_FunctionDef(name, source.path, body))
    return {key: tuple(sorted(items, key=lambda item: item.path)) for key, items in sorted(values.items())}


def _import_index(sources: tuple[journey_entry_points.SelectedSource, ...]) -> dict[str, str]:
    values = {}
    for source in sources:
        for match in IMPORT_PATTERN.finditer(source.text):
            imported = match.group("what")
            module_path = match.group("path")
            for name in re.findall(r"[A-Za-z_$][\w$]*", imported):
                if name not in {"import", "from", "as"}:
                    values[name] = module_path
    return dict(sorted(values.items()))


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
    return text[open_brace + 1 : open_brace + 1200]


def _api_requests(body: str) -> tuple[dict[str, str], ...]:
    values: list[dict[str, str]] = []
    for match in FETCH_PATTERN.finditer(body):
        options = match.group("options") or ""
        method_match = re.search(r"method\s*:\s*['\"](?P<method>[A-Za-z]+)['\"]", options, re.IGNORECASE)
        method = method_match.group("method").upper() if method_match else "GET"
        values.append(_api("fetch", method, match.group("url")))
    for match in AXIOS_PATTERN.finditer(body):
        method = (match.group("method") or "GET").upper()
        values.append(_api("axios", method, match.group("url")))
    for match in HTTP_CLIENT_PATTERN.finditer(body):
        values.append(_api("HttpClient", match.group("method").upper(), match.group("url")))
    return tuple(sorted(values, key=lambda item: (item["url"], item["method"], item["symbol"])))


def _api(symbol: str, method: str, url: str) -> dict[str, str]:
    return {"symbol": symbol, "method": method, "url": url, "route_path": _route_path(url)}


def _route_path(url: str) -> str:
    text = url.strip()
    if "://" in text:
        text = "/" + text.split("/", 3)[3] if len(text.split("/", 3)) > 3 else "/"
    if not text.startswith("/"):
        text = "/" + text
    return re.sub(r"/+", "/", text).split("?", 1)[0].rstrip("/") or "/"


def _state_updates(body: str) -> tuple[str, ...]:
    return tuple(sorted({match.group("name") for match in STATE_PATTERN.finditer(body)}))


def _navigations(body: str) -> tuple[str, ...]:
    values = []
    for match in NAVIGATION_PATTERN.finditer(body):
        literal = re.search(r"['\"]([^'\"]+)['\"]", match.group("target"))
        values.append(literal.group(1) if literal else "dynamic navigation")
    return tuple(sorted(set(values)))


def _function_calls(body: str) -> tuple[str, ...]:
    calls = []
    for match in CALL_PATTERN.finditer(body):
        name = match.group("method") or match.group("name")
        if name:
            calls.append(name)
    return tuple(sorted(set(calls)))


def _service_like(symbol: str) -> bool:
    lowered = symbol.lower()
    return any(part in lowered for part in ("api", "client", "service", "http"))


def _entry_handler(entry: user_journey.JourneyEntryPoint) -> str | None:
    metadata = entry.metadata or {}
    handler = metadata.get("handler")
    if isinstance(handler, str) and handler:
        return handler
    return entry.symbol


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
    metadata: Mapping[str, Any] | None = None,
) -> user_journey.JourneyStep:
    return user_journey.JourneyStep(
        repository_id=repository_id,
        path=path,
        symbol=symbol,
        step_type=step_type,
        summary=summary,
        confidence=user_journey.confidence_from_score(score),
        confidence_score=score,
        sequence_hint=sequence_hint,
        evidence=evidence,
        origin=user_journey.ORIGIN_INFERRED,
        semantic_discriminator=discriminator,
        metadata=metadata or {},
    )


def _transition(source: str, target: str, transition_type: str, score: float, repository_id: str, path: str | None, signal: str) -> user_journey.JourneyTransition:
    evidence = ()
    if path:
        evidence = (
            user_journey.JourneyEvidence(signal, repository_id, path, "Static frontend trace signal.", _strength(score)),
        )
    return user_journey.JourneyTransition(source, target, transition_type, user_journey.confidence_from_score(score), score, evidence=evidence, origin=user_journey.ORIGIN_INFERRED)


def _gap(reason: str, summary: str, source_step_id: str | None, path: str | None, symbol: str | None) -> user_journey.JourneyGap:
    return user_journey.JourneyGap(reason=reason, summary=summary, severity=user_journey.DIAGNOSTIC_SEVERITY_WARNING, source_step_id=source_step_id, repository_id=None, path=path, symbol=symbol)


def _strength(score: float) -> str:
    if score >= 0.7:
        return user_journey.EVIDENCE_STRENGTH_STRONG
    if score >= 0.4:
        return user_journey.EVIDENCE_STRENGTH_MEDIUM
    return user_journey.EVIDENCE_STRENGTH_WEAK


def _coerce_request(value: user_journey.JourneyRequest | Mapping[str, Any]) -> user_journey.JourneyRequest:
    if isinstance(value, user_journey.JourneyRequest):
        return value
    return user_journey.JourneyRequest(**dict(value))


def _coerce_entry_point(value: user_journey.JourneyEntryPoint | Mapping[str, Any]) -> user_journey.JourneyEntryPoint:
    if isinstance(value, user_journey.JourneyEntryPoint):
        return value
    return user_journey.JourneyEntryPoint(**dict(value))


def _nonempty(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise user_journey.UserJourneyError(f"{name} must be a non-empty string")
    return value.strip()
