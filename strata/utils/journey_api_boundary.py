"""Frontend-to-backend API boundary linking for Part P4.

This module consumes supplied frontend journey data and supplied backend route
files. It does not discover repositories, traverse workspace graphs, make
network calls, or trace backend handlers beyond route detection.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any
from urllib.parse import urlsplit

import strata.utils.user_journey as user_journey
import strata.utils.workspace_config as workspace_config


DEFAULT_MAX_FILES = 100
DEFAULT_MAX_BYTES_PER_FILE = 512 * 1024
DEFAULT_MAX_BACKEND_ROUTES = 200
DEFAULT_MAX_STEPS = 150
DEFAULT_MAX_TRANSITIONS = 300
SUPPORTED_BACKEND_EXTENSIONS = (".py", ".go", ".js", ".ts")
PY_DECORATOR_PATTERN = re.compile(r"@(?P<prefix>[A-Za-z_$][\w$.]*)\.(?P<method>get|post|put|patch|delete|options|head|route|api_route)\s*\(\s*['\"](?P<path>[^'\"]+)['\"](?P<args>[^)]*)\)\s*\n\s*(?:async\s+)?def\s+(?P<handler>[A-Za-z_][\w]*)", re.IGNORECASE)
DJANGO_PATH_PATTERN = re.compile(r"\bpath\s*\(\s*['\"](?P<path>[^'\"]+)['\"]\s*,\s*(?P<handler>[A-Za-z_][\w.]*)", re.IGNORECASE)
GO_HANDLE_PATTERN = re.compile(r"\bhttp\.HandleFunc\s*\(\s*['\"](?P<path>[^'\"]+)['\"]\s*,\s*(?P<handler>[A-Za-z_][\w.]*)", re.IGNORECASE)
GO_ROUTER_PATTERN = re.compile(r"\b(?:r|router|mux)\.(?P<method>Get|Post|Put|Patch|Delete|HandleFunc)\s*\(\s*['\"](?P<path>[^'\"]+)['\"]\s*,?\s*(?P<handler>[A-Za-z_][\w.]*)?", re.IGNORECASE)
EXPRESS_PATTERN = re.compile(r"\b(?:app|router)\.(?P<method>get|post|put|patch|delete|use)\s*\(\s*['\"](?P<path>[^'\"]+)['\"]\s*,\s*(?P<handler>[A-Za-z_$][\w$]*)?", re.IGNORECASE)
METHODS_PATH_PATTERN = re.compile(r"\bMethods\s*\(\s*['\"](?P<method>[A-Za-z]+)['\"]\s*\)\s*\.\s*Path\s*\(\s*['\"](?P<path>[^'\"]+)['\"]\s*\)\s*\.\s*HandlerFunc\s*\(\s*(?P<handler>[A-Za-z_][\w.]*)", re.IGNORECASE)
HTTP_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD", "ANY")


@dataclass(frozen=True, slots=True)
class BackendRouteCandidate:
    repository_id: str
    path: str
    route_path: str
    http_method: str
    handler_symbol: str | None
    framework: str
    confidence_score: float
    evidence_summary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "repository_id": self.repository_id,
            "path": self.path,
            "route_path": self.route_path,
            "http_method": self.http_method,
            "handler_symbol": self.handler_symbol,
            "framework": self.framework,
            "confidence_score": self.confidence_score,
            "evidence_summary": self.evidence_summary,
        }


def link_frontend_backend_api_boundary(
    request: user_journey.JourneyRequest | Mapping[str, Any],
    frontend_journey: user_journey.UserJourneyResult | Mapping[str, Any] | None = None,
    *,
    frontend_steps: Iterable[user_journey.JourneyStep | Mapping[str, Any]] = (),
    frontend_transitions: Iterable[user_journey.JourneyTransition | Mapping[str, Any]] = (),
    frontend_repository_id: str,
    backend_repository_id: str | None,
    backend_repository_root: str | Path,
    selected_backend_paths: Iterable[str],
    workspace_graph: Any = None,
    known_repository_urls: Iterable[str] = (),
    known_ports: Iterable[int] = (),
    max_files: int = DEFAULT_MAX_FILES,
    max_bytes_per_file: int = DEFAULT_MAX_BYTES_PER_FILE,
    max_backend_routes: int = DEFAULT_MAX_BACKEND_ROUTES,
    max_steps: int = DEFAULT_MAX_STEPS,
    max_transitions: int = DEFAULT_MAX_TRANSITIONS,
) -> user_journey.UserJourneyResult:
    """Link frontend API request steps to backend route candidates."""

    normalized_request = _coerce_request(request)
    frontend_repository_id = _nonempty(frontend_repository_id, "frontend_repository_id")
    backend_repository_id = _nonempty(backend_repository_id, "backend_repository_id") if backend_repository_id else None
    diagnostics: list[user_journey.JourneyDiagnostic] = []
    if frontend_journey is not None:
        steps = tuple(frontend_journey.steps if isinstance(frontend_journey, user_journey.UserJourneyResult) else _steps_from_mapping(frontend_journey))
        transitions = tuple(frontend_journey.transitions if isinstance(frontend_journey, user_journey.UserJourneyResult) else _transitions_from_mapping(frontend_journey))
    else:
        steps = tuple(_coerce_step(item) for item in frontend_steps)
        transitions = tuple(_coerce_transition(item) for item in frontend_transitions)
    routes = extract_backend_routes(
        backend_repository_id or "unknown",
        backend_repository_root,
        selected_backend_paths,
        diagnostics,
        max_files=max_files,
        max_bytes_per_file=max_bytes_per_file,
        max_backend_routes=max_backend_routes,
    )
    api_steps = tuple(step for step in steps if step.step_type == user_journey.STEP_TYPE_API_REQUEST)
    result_steps = list(steps)
    result_transitions = list(transitions)
    gaps: list[user_journey.JourneyGap] = []

    if not backend_repository_id:
        diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_TARGET_REPOSITORY_UNKNOWN, user_journey.DIAGNOSTIC_SEVERITY_ERROR, "Backend repository is unknown."))
        for api_step in api_steps:
            gaps.append(_gap(user_journey.GAP_REASON_TARGET_REPOSITORY_UNKNOWN, "API target repository is unknown.", api_step.step_id, api_step.path, api_step.symbol))
        return _result(normalized_request, result_steps, result_transitions, gaps, diagnostics, max_steps, max_transitions)

    relationship_available = _workspace_has_calls_api(workspace_graph, frontend_repository_id, backend_repository_id)
    if workspace_graph is not None and not relationship_available:
        diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_WORKSPACE_RELATIONSHIP_MISSING, user_journey.DIAGNOSTIC_SEVERITY_WARNING, "Workspace graph has no calls_api edge for the frontend/backend pair."))

    for api_step in api_steps:
        api = _api_from_step(api_step, known_repository_urls, known_ports, diagnostics)
        if api is None:
            gaps.append(_gap(user_journey.GAP_REASON_API_TARGET_AMBIGUOUS, "Frontend API request could not be resolved to a literal route.", api_step.step_id, api_step.path, api_step.symbol))
            continue
        matches = _matching_routes(api, routes)
        if not matches:
            diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_BACKEND_ROUTE_NOT_FOUND, user_journey.DIAGNOSTIC_SEVERITY_WARNING, "No backend route matched the frontend API request.", details=api))
            gaps.append(_gap(user_journey.GAP_REASON_TARGET_PATH_UNKNOWN, "No backend route matched the API request.", api_step.step_id, api_step.path, api_step.symbol))
            continue
        best_score = matches[0][1]
        best_matches = [route for route, score in matches if score == best_score]
        if len(best_matches) > 1:
            diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_BACKEND_ROUTE_AMBIGUOUS, user_journey.DIAGNOSTIC_SEVERITY_WARNING, "Multiple backend routes matched the frontend API request.", details={"route_path": api["route_path"], "count": len(best_matches)}))
            gaps.append(_gap(user_journey.GAP_REASON_API_TARGET_AMBIGUOUS, "Backend route match is ambiguous.", api_step.step_id, api_step.path, api_step.symbol))
            continue
        route = best_matches[0]
        if api["route_path"] != route.route_path:
            diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_ROUTE_PARAMETER_UNRESOLVED, user_journey.DIAGNOSTIC_SEVERITY_INFO, "Parameterized backend route matched the frontend request.", details={"api_route": api["route_path"], "backend_route": route.route_path}))
        boundary = _step(frontend_repository_id, api_step.path, api["route_path"], user_journey.STEP_TYPE_WORKSPACE_BOUNDARY, f"Cross repository boundary for {api['method']} {api['route_path']}.", min(0.9, best_score), api_step.sequence_hint + 1, f"boundary:{api_step.step_id}:{backend_repository_id}", metadata={"target_repository_id": backend_repository_id, "route_path": api["route_path"]})
        backend = _step(backend_repository_id, route.path, route.handler_symbol, user_journey.STEP_TYPE_BACKEND_ROUTE, f"Backend route {route.http_method} {route.route_path}.", min(0.95, best_score), api_step.sequence_hint + 2, f"backend-route:{route.http_method}:{route.route_path}:{route.path}", metadata={"http_method": route.http_method, "route_path": route.route_path, "framework": route.framework})
        result_steps.extend((boundary, backend))
        result_transitions.append(_transition(api_step.step_id, boundary.step_id, user_journey.TRANSITION_TYPE_SENDS_REQUEST, min(0.9, best_score), False, None))
        result_transitions.append(_transition(boundary.step_id, backend.step_id, user_journey.TRANSITION_TYPE_CROSSES_REPOSITORY, min(0.9, best_score), True, workspace_config.RELATIONSHIP_TYPE_CALLS_API))
        result_transitions.append(_transition(boundary.step_id, backend.step_id, user_journey.TRANSITION_TYPE_ROUTES_TO, min(0.9, best_score), True, workspace_config.RELATIONSHIP_TYPE_CALLS_API))
        result_transitions.append(_transition(api_step.step_id, backend.step_id, user_journey.TRANSITION_TYPE_RECEIVES_REQUEST, min(0.85, best_score), True, workspace_config.RELATIONSHIP_TYPE_CALLS_API))

    return _result(normalized_request, result_steps, result_transitions, gaps, diagnostics, max_steps, max_transitions)


def extract_backend_routes(
    repository_id: str,
    repository_root: str | Path,
    selected_paths: Iterable[str],
    diagnostics: list[user_journey.JourneyDiagnostic],
    *,
    max_files: int,
    max_bytes_per_file: int,
    max_backend_routes: int,
) -> tuple[BackendRouteCandidate, ...]:
    root = Path(repository_root).resolve()
    routes: list[BackendRouteCandidate] = []
    selected = tuple(selected_paths)
    if len(selected) > max_files:
        diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_BACKEND_ROUTE_AMBIGUOUS, user_journey.DIAGNOSTIC_SEVERITY_WARNING, "Selected backend file cap was reached.", details={"limit": max_files, "omitted": len(selected) - max_files}))
    for raw_path in selected[:max_files]:
        raw_text = str(raw_path)
        raw_candidate = Path(raw_text)
        if raw_candidate.is_absolute():
            absolute = raw_candidate.resolve()
            if not _is_relative_to(absolute, root):
                diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_ENTRY_SELECTED_PATH_OUTSIDE_REPOSITORY, user_journey.DIAGNOSTIC_SEVERITY_ERROR, "Selected backend path is outside the repository.", details={"selected_path": raw_text}))
                continue
            normalized = absolute.relative_to(root).as_posix()
        else:
            normalized = _normalize_selected_path(raw_text, diagnostics)
        if normalized is None:
            continue
        path = (root / normalized).resolve()
        if not _is_relative_to(path, root):
            diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_ENTRY_SELECTED_PATH_OUTSIDE_REPOSITORY, user_journey.DIAGNOSTIC_SEVERITY_ERROR, "Selected backend path is outside the repository.", path=normalized))
            continue
        if not path.exists():
            diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_ENTRY_SELECTED_PATH_MISSING, user_journey.DIAGNOSTIC_SEVERITY_WARNING, "Selected backend route file does not exist.", path=normalized))
            continue
        if path.suffix.lower() not in SUPPORTED_BACKEND_EXTENSIONS:
            continue
        if path.stat().st_size > max_bytes_per_file:
            diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_FRONTEND_FILE_TOO_LARGE, user_journey.DIAGNOSTIC_SEVERITY_WARNING, "Selected backend route file exceeded the byte cap.", path=normalized))
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        routes.extend(_routes_from_text(repository_id, normalized, text))
    routes = sorted(routes, key=lambda item: (item.route_path, item.http_method, item.path, item.handler_symbol or ""))
    if len(routes) > max_backend_routes:
        diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_BACKEND_ROUTE_AMBIGUOUS, user_journey.DIAGNOSTIC_SEVERITY_WARNING, "Backend route candidate cap was reached.", details={"limit": max_backend_routes, "omitted": len(routes) - max_backend_routes}))
        routes = routes[:max_backend_routes]
    return tuple(routes)


def _routes_from_text(repository_id: str, path: str, text: str) -> tuple[BackendRouteCandidate, ...]:
    routes: list[BackendRouteCandidate] = []
    for match in PY_DECORATOR_PATTERN.finditer(text):
        methods = _python_methods(match.group("method"), match.group("args"))
        for method in methods:
            routes.append(_route(repository_id, path, match.group("path"), method, match.group("handler"), "python", "Python route decorator."))
    for match in DJANGO_PATH_PATTERN.finditer(text):
        routes.append(_route(repository_id, path, match.group("path"), "ANY", match.group("handler").rsplit(".", 1)[-1], "django", "Django path declaration."))
    for match in GO_HANDLE_PATTERN.finditer(text):
        routes.append(_route(repository_id, path, match.group("path"), "ANY", match.group("handler").rsplit(".", 1)[-1], "go", "Go http.HandleFunc declaration."))
    for match in GO_ROUTER_PATTERN.finditer(text):
        method = "ANY" if match.group("method").lower() == "handlefunc" else match.group("method").upper()
        routes.append(_route(repository_id, path, match.group("path"), method, (match.group("handler") or "").rsplit(".", 1)[-1] or None, "go", "Go router route declaration."))
    for match in METHODS_PATH_PATTERN.finditer(text):
        routes.append(_route(repository_id, path, match.group("path"), match.group("method").upper(), match.group("handler").rsplit(".", 1)[-1], "go", "Go method/path route declaration."))
    for match in EXPRESS_PATTERN.finditer(text):
        method = "ANY" if match.group("method").lower() == "use" else match.group("method").upper()
        routes.append(_route(repository_id, path, match.group("path"), method, match.group("handler"), "express", "Express route declaration."))
    deduped = {(_normalize_route(item.route_path), item.http_method, item.path, item.handler_symbol or ""): item for item in routes}
    return tuple(deduped[key] for key in sorted(deduped))


def _python_methods(method: str, args: str) -> tuple[str, ...]:
    normalized = method.upper()
    if normalized in HTTP_METHODS and normalized not in {"ROUTE", "API_ROUTE"}:
        return (normalized,)
    methods = re.findall(r"['\"]([A-Za-z]+)['\"]", args or "")
    values = tuple(sorted({item.upper() for item in methods if item.upper() in HTTP_METHODS}))
    return values or ("ANY",)


def _route(repository_id: str, path: str, route_path: str, method: str, handler: str | None, framework: str, evidence: str) -> BackendRouteCandidate:
    return BackendRouteCandidate(repository_id, path, _normalize_route(route_path), method if method in HTTP_METHODS else "ANY", handler, framework, 0.9 if method != "ANY" else 0.65, evidence)


def _api_from_step(step: user_journey.JourneyStep, known_urls: Iterable[str], known_ports: Iterable[int], diagnostics: list[user_journey.JourneyDiagnostic]) -> dict[str, str] | None:
    metadata = step.metadata or {}
    method = str(metadata.get("http_method") or metadata.get("method") or "").upper()
    url = str(metadata.get("url") or metadata.get("route_path") or step.symbol or "")
    if not method:
        method = "GET"
        diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_API_METHOD_UNKNOWN, user_journey.DIAGNOSTIC_SEVERITY_INFO, "API method was unknown and defaulted to GET.", path=step.path))
    if not url:
        diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_API_ROUTE_UNKNOWN, user_journey.DIAGNOSTIC_SEVERITY_WARNING, "API route path was unknown.", path=step.path))
        return None
    target_port = _url_port(url)
    if target_port and tuple(known_ports) and target_port not in set(known_ports):
        diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_API_TARGET_AMBIGUOUS, user_journey.DIAGNOSTIC_SEVERITY_WARNING, "API request port does not match supplied backend ports.", path=step.path, details={"port": target_port}))
    if "://" in url and tuple(known_urls) and not _known_url_match(url, known_urls):
        diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_API_TARGET_AMBIGUOUS, user_journey.DIAGNOSTIC_SEVERITY_WARNING, "API request URL does not match supplied backend URLs.", path=step.path))
    return {"method": method if method in HTTP_METHODS else "ANY", "route_path": _normalize_route(_url_path(url)), "url": url}


def _matching_routes(api: Mapping[str, str], routes: tuple[BackendRouteCandidate, ...]) -> tuple[tuple[BackendRouteCandidate, float], ...]:
    matches = []
    for route in routes:
        route_score = _route_match_score(api["route_path"], route.route_path)
        if route_score <= 0:
            continue
        method_score = 0.15 if route.http_method == "ANY" or api["method"] == "ANY" else 0.3 if route.http_method == api["method"] else -1.0
        if method_score < 0:
            continue
        matches.append((route, round(min(1.0, route_score + method_score), 3)))
    return tuple(sorted(matches, key=lambda item: (-item[1], item[0].route_path, item[0].http_method, item[0].path)))


def _route_match_score(request_path: str, route_path: str) -> float:
    if request_path == route_path:
        return 0.65
    request_parts = tuple(part for part in request_path.strip("/").split("/") if part)
    route_parts = tuple(part for part in route_path.strip("/").split("/") if part)
    if len(request_parts) != len(route_parts):
        return 0.0
    for request_part, route_part in zip(request_parts, route_parts):
        if route_part.startswith(":") or route_part.startswith("{") and route_part.endswith("}"):
            continue
        if request_part != route_part:
            return 0.0
    return 0.5


def _workspace_has_calls_api(workspace_graph: Any, frontend_repository_id: str, backend_repository_id: str) -> bool:
    if workspace_graph is None:
        return False
    payload = workspace_graph.to_dict() if hasattr(workspace_graph, "to_dict") else workspace_graph if isinstance(workspace_graph, Mapping) else {}
    for edge in payload.get("edges", ()):
        if (
            edge.get("source_repository_id") == frontend_repository_id
            and edge.get("target_repository_id") == backend_repository_id
            and edge.get("relationship_type") == workspace_config.RELATIONSHIP_TYPE_CALLS_API
        ):
            return True
    return False


def _result(request, steps, transitions, gaps, diagnostics, max_steps, max_transitions):
    return user_journey.build_user_journey_result(request, steps=steps, transitions=transitions, gaps=gaps, diagnostics=diagnostics, max_steps=max_steps, max_transitions=max_transitions)


def _step(repository_id: str, path: str | None, symbol: str | None, step_type: str, summary: str, score: float, sequence_hint: int, discriminator: str, *, metadata: Mapping[str, Any] | None = None) -> user_journey.JourneyStep:
    return user_journey.JourneyStep(repository_id=repository_id, path=path, symbol=symbol, step_type=step_type, summary=summary, confidence=user_journey.confidence_from_score(score), confidence_score=score, sequence_hint=sequence_hint, origin=user_journey.ORIGIN_INFERRED, semantic_discriminator=discriminator, metadata=metadata or {})


def _transition(source: str, target: str, transition_type: str, score: float, cross_repository: bool, relationship_type: str | None) -> user_journey.JourneyTransition:
    return user_journey.JourneyTransition(source, target, transition_type, user_journey.confidence_from_score(score), score, origin=user_journey.ORIGIN_INFERRED, cross_repository=cross_repository, relationship_type=relationship_type)


def _gap(reason: str, summary: str, source_step_id: str | None, path: str | None, symbol: str | None) -> user_journey.JourneyGap:
    return user_journey.JourneyGap(reason=reason, summary=summary, severity=user_journey.DIAGNOSTIC_SEVERITY_WARNING, source_step_id=source_step_id, path=path, symbol=symbol)


def _steps_from_mapping(value: Mapping[str, Any]) -> tuple[user_journey.JourneyStep, ...]:
    return tuple(_coerce_step(item) for item in value.get("steps", ()))


def _transitions_from_mapping(value: Mapping[str, Any]) -> tuple[user_journey.JourneyTransition, ...]:
    return tuple(_coerce_transition(item) for item in value.get("transitions", ()))


def _coerce_step(value: user_journey.JourneyStep | Mapping[str, Any]) -> user_journey.JourneyStep:
    if isinstance(value, user_journey.JourneyStep):
        return value
    return user_journey.JourneyStep(**dict(value))


def _coerce_transition(value: user_journey.JourneyTransition | Mapping[str, Any]) -> user_journey.JourneyTransition:
    if isinstance(value, user_journey.JourneyTransition):
        return value
    return user_journey.JourneyTransition(**dict(value))


def _coerce_request(value: user_journey.JourneyRequest | Mapping[str, Any]) -> user_journey.JourneyRequest:
    if isinstance(value, user_journey.JourneyRequest):
        return value
    return user_journey.JourneyRequest(**dict(value))


def _diagnostic(code: str, severity: str, summary: str, *, path: str | None = None, details: Mapping[str, Any] | None = None) -> user_journey.JourneyDiagnostic:
    return user_journey.JourneyDiagnostic(code=code, severity=severity, summary=summary, path=path, details=details)


def _normalize_selected_path(raw_path: str, diagnostics: list[user_journey.JourneyDiagnostic]) -> str | None:
    try:
        text = _nonempty(raw_path, "selected_path")
        windows = PureWindowsPath(text)
        posix = PurePosixPath(text.replace("\\", "/"))
        if windows.drive or windows.is_absolute() or posix.is_absolute():
            return posix.as_posix().lstrip("/")
        collapsed = []
        for part in posix.parts:
            if part in ("", "."):
                continue
            if part == "..":
                if collapsed:
                    collapsed.pop()
                else:
                    raise ValueError("path escapes repository")
                continue
            collapsed.append(part)
        return PurePosixPath(*collapsed).as_posix()
    except Exception:
        diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_ENTRY_SELECTED_PATH_INVALID, user_journey.DIAGNOSTIC_SEVERITY_ERROR, "Selected backend path is invalid.", details={"selected_path": str(raw_path)}))
        return None


def _normalize_route(path: str) -> str:
    text = path.strip()
    if not text.startswith("/"):
        text = "/" + text
    return re.sub(r"/+", "/", text).split("?", 1)[0].rstrip("/") or "/"


def _url_path(url: str) -> str:
    if "://" not in url:
        return url
    parsed = urlsplit(url)
    return parsed.path or "/"


def _url_port(url: str) -> int | None:
    if "://" not in url:
        return None
    try:
        return urlsplit(url).port
    except ValueError:
        return None


def _known_url_match(url: str, known_urls: Iterable[str]) -> bool:
    parsed = urlsplit(url)
    for known in known_urls:
        known_parsed = urlsplit(known)
        if parsed.scheme == known_parsed.scheme and parsed.netloc == known_parsed.netloc:
            return True
    return False


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
