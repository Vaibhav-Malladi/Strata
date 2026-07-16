"""Selected-file user-action entry-point detection for Part P2.

This module reads only caller-supplied selected paths. It does not recursively
scan repositories, traverse imports, execute code, call networks, or build
complete journeys.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import html
import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

import strata.utils.user_journey as user_journey


DEFAULT_MAX_FILES = 100
DEFAULT_MAX_BYTES_PER_FILE = 512 * 1024
DEFAULT_MAX_ENTRY_POINTS = 50
DEFAULT_MAX_EVIDENCE_PER_ENTRY_POINT = 8
SUPPORTED_EXTENSIONS = (".html", ".htm", ".js", ".jsx", ".ts", ".tsx", ".json")
TEXT_TAG_PATTERN = re.compile(r"<(?P<tag>button|a)\b(?P<attrs>[^>]*)>(?P<body>.*?)</(?P=tag)>", re.IGNORECASE | re.DOTALL)
FORM_PATTERN = re.compile(r"<form\b(?P<attrs>[^>]*)>", re.IGNORECASE | re.DOTALL)
ATTR_PATTERN = re.compile(r"(?P<name>\(?[\w:-]+\)?|\[[\w:-]+\])\s*=\s*(?P<quote>['\"])(?P<value>.*?)(?P=quote)", re.DOTALL)
ANGULAR_EVENT_PATTERN = re.compile(r"\((?P<event>click|submit|keydown|keyup|keypress)\)\s*=\s*['\"](?P<handler>[^'\"]+)['\"]", re.IGNORECASE)
REACT_EVENT_PATTERN = re.compile(r"\b(?P<event>onClick|onSubmit|onChange|onKeyDown|onKeyUp|onKeyPress)\s*=\s*\{?\s*(?P<handler>[A-Za-z_$][\w$]*)", re.DOTALL)
FUNCTION_PATTERN = re.compile(r"(?:export\s+)?(?:async\s+)?function\s+(?P<name>[A-Za-z_$][\w$]*)\s*\(|(?:const|let|var)\s+(?P<var>[A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>")
CLASS_METHOD_PATTERN = re.compile(r"(?m)^\s*(?P<name>[A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{")
ROUTE_PATTERN = re.compile(r"(?:path|routerLink|href)\s*[:=]\s*['\"](?P<route>/[^'\"]*|[^'\"]+)['\"]|<Route\b[^>]*\bpath\s*=\s*['\"](?P<jsxroute>[^'\"]+)['\"]", re.IGNORECASE)
MESSAGE_PATTERN = re.compile(r"addEventListener\s*\(\s*['\"]message['\"]|postMessage\s*\(", re.IGNORECASE)
DYNAMIC_BINDING_PATTERN = re.compile(r"\[(?:routerLink|href|src)\]\s*=")


@dataclass(frozen=True, slots=True)
class JourneyEntryPointDetectionResult:
    request: user_journey.JourneyRequest
    entry_points: tuple[user_journey.JourneyEntryPoint, ...]
    diagnostics: tuple[user_journey.JourneyDiagnostic, ...]
    summary: Mapping[str, Any]
    metadata: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "request": self.request.to_dict(),
            "entry_points": [item.to_dict() for item in self.entry_points],
            "diagnostics": [item.to_dict() for item in self.diagnostics],
            "summary": dict(self.summary),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class SelectedSource:
    path: str
    text: str
    extension: str


@dataclass(frozen=True, slots=True)
class _Candidate:
    path: str
    symbol: str | None
    entry_point_type: str
    label: str
    score: float
    origin: str
    evidence_summary: str
    signal_type: str
    metadata: Mapping[str, Any]


def detect_journey_entry_points(
    request: user_journey.JourneyRequest | Mapping[str, Any],
    repository_id: str,
    repository_root: str | Path,
    selected_paths: Iterable[str],
    *,
    max_files: int = DEFAULT_MAX_FILES,
    max_bytes_per_file: int = DEFAULT_MAX_BYTES_PER_FILE,
    max_entry_points: int = DEFAULT_MAX_ENTRY_POINTS,
    max_evidence_per_entry_point: int = DEFAULT_MAX_EVIDENCE_PER_ENTRY_POINT,
) -> JourneyEntryPointDetectionResult:
    """Detect likely user-action entry points from explicitly selected files."""

    normalized_request = _coerce_request(request)
    repository_id = _nonempty(repository_id, "repository_id")
    max_files = _limit(max_files, "max_files")
    max_bytes_per_file = _limit(max_bytes_per_file, "max_bytes_per_file")
    max_entry_points = _limit(max_entry_points, "max_entry_points")
    max_evidence_per_entry_point = _limit(max_evidence_per_entry_point, "max_evidence_per_entry_point")
    selected_path_values = tuple(selected_paths)

    diagnostics: list[user_journey.JourneyDiagnostic] = []
    sources = load_selected_sources(
        repository_root,
        selected_path_values,
        diagnostics,
        max_files=max_files,
        max_bytes_per_file=max_bytes_per_file,
        unsupported_code=user_journey.DIAGNOSTIC_ENTRY_UNSUPPORTED_FILE,
        too_large_code=user_journey.DIAGNOSTIC_ENTRY_FILE_TOO_LARGE,
        unreadable_code=user_journey.DIAGNOSTIC_ENTRY_FILE_UNREADABLE,
    )
    candidates: list[_Candidate] = []
    candidates.extend(_explicit_path_candidates(normalized_request, repository_id, sources))
    for source in sources:
        candidates.extend(_template_candidates(normalized_request, source))
        candidates.extend(_script_candidates(normalized_request, source))
        if DYNAMIC_BINDING_PATTERN.search(source.text):
            diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_ENTRY_DYNAMIC_BINDING_UNRESOLVED, user_journey.DIAGNOSTIC_SEVERITY_WARNING, "Dynamic template binding was not resolved.", path=source.path))

    entry_points = _entry_points_from_candidates(
        normalized_request,
        repository_id,
        candidates,
        diagnostics,
        max_entry_points=max_entry_points,
        max_evidence_per_entry_point=max_evidence_per_entry_point,
    )
    return JourneyEntryPointDetectionResult(
        request=normalized_request,
        entry_points=entry_points,
        diagnostics=tuple(sorted(diagnostics, key=user_journey.diagnostic_sort_key)),
        summary={
            "entry_point_count": len(entry_points),
            "file_count": len(sources),
            "diagnostic_count": len(diagnostics),
        },
        metadata={"selected_path_count": len(selected_path_values)},
    )


def load_selected_sources(
    repository_root: str | Path,
    selected_paths: Iterable[str],
    diagnostics: list[user_journey.JourneyDiagnostic],
    *,
    max_files: int,
    max_bytes_per_file: int,
    unsupported_code: str,
    too_large_code: str,
    unreadable_code: str,
) -> tuple[SelectedSource, ...]:
    root = Path(repository_root).resolve()
    paths = tuple(selected_paths)
    sources: list[SelectedSource] = []
    if len(paths) > max_files:
        diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_ENTRY_CAP_REACHED, user_journey.DIAGNOSTIC_SEVERITY_WARNING, "Selected file cap was reached.", details={"limit": max_files, "omitted": len(paths) - max_files}))
        paths = paths[:max_files]
    for raw_path in paths:
        raw_text = str(raw_path)
        raw_candidate = Path(raw_text)
        if raw_candidate.is_absolute():
            absolute = raw_candidate.resolve()
            if not _is_relative_to(absolute, root):
                diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_ENTRY_SELECTED_PATH_OUTSIDE_REPOSITORY, user_journey.DIAGNOSTIC_SEVERITY_ERROR, "Selected path is outside the repository.", details={"selected_path": raw_text}))
                continue
            normalized = absolute.relative_to(root).as_posix()
        else:
            normalized = _normalize_selected_path(raw_text, diagnostics)
        if normalized is None:
            continue
        candidate = (root / normalized).resolve()
        if not _is_relative_to(candidate, root):
            diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_ENTRY_SELECTED_PATH_OUTSIDE_REPOSITORY, user_journey.DIAGNOSTIC_SEVERITY_ERROR, "Selected path is outside the repository.", path=normalized))
            continue
        if not candidate.exists():
            diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_ENTRY_SELECTED_PATH_MISSING, user_journey.DIAGNOSTIC_SEVERITY_WARNING, "Selected path does not exist.", path=normalized))
            continue
        if candidate.is_symlink():
            diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_ENTRY_SYMLINK_SKIPPED, user_journey.DIAGNOSTIC_SEVERITY_WARNING, "Selected symlink was skipped.", path=normalized))
            continue
        extension = candidate.suffix.lower()
        if extension not in SUPPORTED_EXTENSIONS:
            diagnostics.append(_diagnostic(unsupported_code, user_journey.DIAGNOSTIC_SEVERITY_INFO, "Selected file type is unsupported for journey entry detection.", path=normalized))
            continue
        try:
            size = candidate.stat().st_size
        except OSError:
            diagnostics.append(_diagnostic(unreadable_code, user_journey.DIAGNOSTIC_SEVERITY_WARNING, "Selected file could not be statted.", path=normalized))
            continue
        if size > max_bytes_per_file:
            diagnostics.append(_diagnostic(too_large_code, user_journey.DIAGNOSTIC_SEVERITY_WARNING, "Selected file exceeded the byte cap.", path=normalized, details={"limit": max_bytes_per_file, "size": size}))
            continue
        try:
            text = candidate.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = candidate.read_text(encoding="utf-8", errors="replace")
        except OSError:
            diagnostics.append(_diagnostic(unreadable_code, user_journey.DIAGNOSTIC_SEVERITY_WARNING, "Selected file could not be read.", path=normalized))
            continue
        sources.append(SelectedSource(normalized, text, extension))
    return tuple(sorted(sources, key=lambda item: item.path))


def _template_candidates(request: user_journey.JourneyRequest, source: SelectedSource) -> tuple[_Candidate, ...]:
    candidates: list[_Candidate] = []
    for match in TEXT_TAG_PATTERN.finditer(source.text):
        tag = match.group("tag").lower()
        attrs = _attrs(match.group("attrs"))
        label = _clean_text(match.group("body")) or attrs.get("aria-label") or attrs.get("title") or tag
        route = attrs.get("routerlink") or attrs.get("[routerlink]") or attrs.get("href")
        handler = _handler_from_attrs(attrs)
        entry_type = user_journey.ENTRY_POINT_TYPE_BUTTON if tag == "button" else user_journey.ENTRY_POINT_TYPE_LINK
        if route and _route_relevant(request, route):
            candidates.append(_candidate(source.path, None, user_journey.ENTRY_POINT_TYPE_ROUTE, route, 0.94, user_journey.ORIGIN_ROUTE_MATCH, f"Matched route {route}.", "route_match", {"route": route}))
        if _label_relevant(request, label) or handler and _symbol_relevant(request, handler):
            score, origin = _score_for_label_handler(request, label, handler)
            candidates.append(_candidate(source.path, handler, entry_type, label, score, origin, f"Matched {tag} label or handler.", "ui_text_match", {"handler": handler, "route": route, "event": _event_from_attrs(attrs)}))
        elif handler:
            candidates.append(_candidate(source.path, handler, entry_type, label, 0.35, user_journey.ORIGIN_INFERRED, f"Found {tag} handler {handler}.", "handler_name", {"handler": handler, "event": _event_from_attrs(attrs)}))
    for match in FORM_PATTERN.finditer(source.text):
        attrs = _attrs(match.group("attrs"))
        handler = _handler_from_attrs(attrs) or "submit"
        if _symbol_relevant(request, handler) or _keywords_overlap(request, handler):
            candidates.append(_candidate(source.path, handler, user_journey.ENTRY_POINT_TYPE_FORM, "form submit", 0.82, user_journey.ORIGIN_SYMBOL_MATCH, "Matched form submit handler.", "form_submit", {"handler": handler, "event": "submit"}))
    for match in ANGULAR_EVENT_PATTERN.finditer(source.text):
        event = match.group("event").lower()
        handler = _handler_name(match.group("handler"))
        entry_type = user_journey.ENTRY_POINT_TYPE_KEYBOARD_ACTION if event.startswith("key") else user_journey.ENTRY_POINT_TYPE_UI_EVENT
        if _symbol_relevant(request, handler) or _keywords_overlap(request, handler):
            candidates.append(_candidate(source.path, handler, entry_type, handler, 0.82, user_journey.ORIGIN_SYMBOL_MATCH, f"Matched Angular {event} handler.", "angular_event", {"handler": handler, "event": event}))
    return tuple(candidates)


def _script_candidates(request: user_journey.JourneyRequest, source: SelectedSource) -> tuple[_Candidate, ...]:
    candidates: list[_Candidate] = []
    for match in REACT_EVENT_PATTERN.finditer(source.text):
        event = match.group("event")
        handler = match.group("handler")
        entry_type = user_journey.ENTRY_POINT_TYPE_FORM if event == "onSubmit" else user_journey.ENTRY_POINT_TYPE_KEYBOARD_ACTION if "Key" in event else user_journey.ENTRY_POINT_TYPE_UI_EVENT
        if _symbol_relevant(request, handler) or _keywords_overlap(request, handler):
            candidates.append(_candidate(source.path, handler, entry_type, handler, 0.84, user_journey.ORIGIN_SYMBOL_MATCH, f"Matched React {event} handler.", "react_event", {"handler": handler, "event": event}))
    for match in FUNCTION_PATTERN.finditer(source.text):
        symbol = match.group("name") or match.group("var")
        if _symbol_relevant(request, symbol) or _keywords_overlap(request, symbol):
            candidates.append(_candidate(source.path, symbol, user_journey.ENTRY_POINT_TYPE_EXPLICIT_SYMBOL, symbol, 0.78, user_journey.ORIGIN_SYMBOL_MATCH, "Matched exported or named function.", "symbol_match", {"handler": symbol}))
    for match in CLASS_METHOD_PATTERN.finditer(source.text):
        symbol = match.group("name")
        if _symbol_relevant(request, symbol) or _keywords_overlap(request, symbol):
            candidates.append(_candidate(source.path, symbol, user_journey.ENTRY_POINT_TYPE_COMPONENT, symbol, 0.72, user_journey.ORIGIN_SYMBOL_MATCH, "Matched component method.", "component_method", {"handler": symbol}))
    for match in ROUTE_PATTERN.finditer(source.text):
        route = match.group("route") or match.group("jsxroute")
        if route and _route_relevant(request, route):
            candidates.append(_candidate(source.path, None, user_journey.ENTRY_POINT_TYPE_ROUTE, route, 0.94, user_journey.ORIGIN_ROUTE_MATCH, "Matched route declaration.", "route_match", {"route": route}))
    if MESSAGE_PATTERN.search(source.text) and ("message" in request.task_keywords or any("message" in hint.lower() for hint in request.ui_hints)):
        candidates.append(_candidate(source.path, "message", user_journey.ENTRY_POINT_TYPE_MESSAGE_EVENT, "message event", 0.75, user_journey.ORIGIN_TASK_MATCH, "Matched message event listener or sender.", "message_event", {"event": "message"}))
    if _keywords_overlap(request, source.path):
        candidates.append(_candidate(source.path, None, user_journey.ENTRY_POINT_TYPE_EXPLICIT_PATH, PurePosixPath(source.path).name, 0.55, user_journey.ORIGIN_TASK_MATCH, "Selected filename overlaps task keywords.", "file_name_match", {}))
    return tuple(candidates)


def _explicit_path_candidates(request: user_journey.JourneyRequest, repository_id: str, sources: tuple[SelectedSource, ...]) -> tuple[_Candidate, ...]:
    source_paths = {source.path for source in sources}
    candidates = []
    if request.starting_repository_ids and repository_id not in request.starting_repository_ids:
        return ()
    for path in request.starting_paths:
        if path in source_paths:
            candidates.append(_candidate(path, None, user_journey.ENTRY_POINT_TYPE_EXPLICIT_PATH, path, 0.96, user_journey.ORIGIN_EXPLICIT, "Matched explicit starting path.", "explicit_path", {}))
    for symbol in request.starting_symbols:
        for source in sources:
            if re.search(rf"(?<![\w$]){re.escape(symbol)}(?![\w$])", source.text):
                candidates.append(_candidate(source.path, symbol, user_journey.ENTRY_POINT_TYPE_EXPLICIT_SYMBOL, symbol, 0.98, user_journey.ORIGIN_EXPLICIT, "Matched explicit starting symbol.", "explicit_symbol", {"handler": symbol}))
    return tuple(candidates)


def _entry_points_from_candidates(
    request: user_journey.JourneyRequest,
    repository_id: str,
    candidates: Iterable[_Candidate],
    diagnostics: list[user_journey.JourneyDiagnostic],
    *,
    max_entry_points: int,
    max_evidence_per_entry_point: int,
) -> tuple[user_journey.JourneyEntryPoint, ...]:
    grouped: dict[tuple[str, str, str, str], list[_Candidate]] = {}
    for candidate in sorted(candidates, key=_candidate_sort_key):
        grouped.setdefault((candidate.path, candidate.symbol or "", candidate.entry_point_type, candidate.label), []).append(candidate)
    entries: list[user_journey.JourneyEntryPoint] = []
    for group in grouped.values():
        best = max(group, key=lambda item: (item.score, item.origin))
        evidence = tuple(
            user_journey.JourneyEvidence(
                signal_type=item.signal_type,
                repository_id=repository_id,
                path=item.path,
                symbol=item.symbol,
                summary=item.evidence_summary,
                strength=_strength(item.score),
                metadata=item.metadata,
            )
            for item in sorted(group, key=_candidate_sort_key)[:max_evidence_per_entry_point]
        )
        if len(group) > max_evidence_per_entry_point:
            diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_ENTRY_EVIDENCE_TRUNCATED, user_journey.DIAGNOSTIC_SEVERITY_WARNING, "Entry-point evidence was truncated.", path=best.path, details={"limit": max_evidence_per_entry_point, "omitted": len(group) - max_evidence_per_entry_point}))
        entries.append(
            user_journey.JourneyEntryPoint(
                repository_id=repository_id,
                path=best.path,
                symbol=best.symbol,
                entry_point_type=best.entry_point_type,
                display_label=best.label,
                confidence=user_journey.confidence_from_score(best.score),
                confidence_score=best.score,
                evidence=evidence,
                origin=best.origin,
                metadata=best.metadata,
            )
        )
    _diagnose_ambiguity(entries, request, diagnostics)
    entries = tuple(sorted(entries, key=user_journey.entry_point_sort_key))
    if len(entries) > max_entry_points:
        diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_ENTRY_CAP_REACHED, user_journey.DIAGNOSTIC_SEVERITY_WARNING, "Entry-point cap was reached.", details={"limit": max_entry_points, "omitted": len(entries) - max_entry_points}))
        entries = entries[:max_entry_points]
    return tuple(entries)


def _diagnose_ambiguity(entries: Iterable[user_journey.JourneyEntryPoint], request: user_journey.JourneyRequest, diagnostics: list[user_journey.JourneyDiagnostic]) -> None:
    by_label: dict[str, list[user_journey.JourneyEntryPoint]] = {}
    by_symbol: dict[str, list[user_journey.JourneyEntryPoint]] = {}
    for entry in entries:
        if _label_relevant(request, entry.display_label):
            by_label.setdefault(_normalize_match_text(entry.display_label), []).append(entry)
        if entry.symbol and entry.symbol in request.starting_symbols:
            by_symbol.setdefault(entry.symbol, []).append(entry)
    for label, matches in sorted(by_label.items()):
        if len(matches) > 1:
            diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_ENTRY_ROUTE_AMBIGUOUS if label.startswith("/") else user_journey.DIAGNOSTIC_ENTRY_SYMBOL_AMBIGUOUS, user_journey.DIAGNOSTIC_SEVERITY_WARNING, "Multiple entry points matched the same user-action hint.", details={"match": label, "count": len(matches)}))
    for symbol, matches in sorted(by_symbol.items()):
        if len(matches) > 1:
            diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_ENTRY_SYMBOL_AMBIGUOUS, user_journey.DIAGNOSTIC_SEVERITY_WARNING, "Multiple entry points matched the same explicit symbol.", symbol=symbol, details={"count": len(matches)}))


def _candidate(path: str, symbol: str | None, entry_type: str, label: str, score: float, origin: str, evidence: str, signal: str, metadata: Mapping[str, Any]) -> _Candidate:
    return _Candidate(path, symbol, entry_type, label, round(score, 3), origin, evidence, signal, dict(metadata))


def _candidate_sort_key(candidate: _Candidate) -> tuple[object, ...]:
    return (-candidate.score, candidate.path, candidate.symbol or "", candidate.entry_point_type, candidate.label, candidate.signal_type)


def _strength(score: float) -> str:
    if score >= 0.7:
        return user_journey.EVIDENCE_STRENGTH_STRONG
    if score >= 0.4:
        return user_journey.EVIDENCE_STRENGTH_MEDIUM
    return user_journey.EVIDENCE_STRENGTH_WEAK


def _attrs(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for match in ATTR_PATTERN.finditer(text):
        name = match.group("name").strip().lower()
        values[name] = html.unescape(match.group("value").strip())
    return values


def _handler_from_attrs(attrs: Mapping[str, str]) -> str | None:
    for key, value in attrs.items():
        if key in {"(click)", "(submit)", "(keydown)", "(keyup)", "(keypress)", "onclick", "onsubmit", "onkeydown", "onkeyup", "onkeypress"} or key.lower().startswith("on"):
            return _handler_name(value)
    return None


def _event_from_attrs(attrs: Mapping[str, str]) -> str | None:
    for key in attrs:
        if "click" in key:
            return "click"
        if "submit" in key:
            return "submit"
        if "key" in key:
            return "keyboard"
    return None


def _handler_name(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"([A-Za-z_$][\w$]*)", value)
    return match.group(1) if match else None


def _clean_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value)
    text = html.unescape(re.sub(r"\s+", " ", text)).strip()
    return text


def _score_for_label_handler(request: user_journey.JourneyRequest, label: str, handler: str | None) -> tuple[float, str]:
    if _label_exact(request, label):
        return 0.93, user_journey.ORIGIN_UI_TEXT_MATCH
    if handler and _symbol_relevant(request, handler):
        return 0.88, user_journey.ORIGIN_SYMBOL_MATCH
    if _keywords_overlap(request, label) or handler and _keywords_overlap(request, handler):
        return 0.62, user_journey.ORIGIN_TASK_MATCH
    return 0.35, user_journey.ORIGIN_INFERRED


def _label_exact(request: user_journey.JourneyRequest, label: str) -> bool:
    normalized = _normalize_match_text(label)
    hints = {_normalize_match_text(hint) for hint in (*request.ui_hints, request.task)}
    return normalized in hints or any(normalized == hint for hint in hints)


def _label_relevant(request: user_journey.JourneyRequest, label: str) -> bool:
    return _label_exact(request, label) or _keywords_overlap(request, label)


def _symbol_relevant(request: user_journey.JourneyRequest, symbol: str | None) -> bool:
    if not symbol:
        return False
    normalized = _normalize_match_text(symbol)
    return normalized in {_normalize_match_text(item) for item in request.starting_symbols} or _keywords_overlap(request, symbol)


def _route_relevant(request: user_journey.JourneyRequest, route: str) -> bool:
    normalized = _normalize_route(route)
    hints = {_normalize_route(item) for item in request.route_hints}
    return normalized in hints or _keywords_overlap(request, route)


def _keywords_overlap(request: user_journey.JourneyRequest, value: str | None) -> bool:
    if not value:
        return False
    words = set(re.findall(r"[a-z0-9][a-z0-9_-]*", value.lower()))
    return bool(words & set(request.task_keywords))


def _normalize_match_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _normalize_route(route: str) -> str:
    text = route.strip()
    if not text.startswith("/"):
        text = "/" + text
    return re.sub(r"/+", "/", text).rstrip("/") or "/"


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
        if not collapsed:
            raise ValueError("path is empty")
        return PurePosixPath(*collapsed).as_posix()
    except Exception:
        diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_ENTRY_SELECTED_PATH_INVALID, user_journey.DIAGNOSTIC_SEVERITY_ERROR, "Selected path is invalid.", details={"selected_path": str(raw_path)}))
        return None


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _coerce_request(value: user_journey.JourneyRequest | Mapping[str, Any]) -> user_journey.JourneyRequest:
    if isinstance(value, user_journey.JourneyRequest):
        return value
    return user_journey.JourneyRequest(**dict(value))


def _diagnostic(code: str, severity: str, summary: str, *, path: str | None = None, symbol: str | None = None, details: Mapping[str, Any] | None = None) -> user_journey.JourneyDiagnostic:
    return user_journey.JourneyDiagnostic(code=code, severity=severity, summary=summary, path=path, symbol=symbol, details=details)


def _nonempty(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise user_journey.UserJourneyError(f"{name} must be a non-empty string")
    return value.strip()


def _limit(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 1:
        raise user_journey.UserJourneyError(f"{name} must be at least 1")
    return value
