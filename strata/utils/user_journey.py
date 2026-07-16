"""User journey contracts for Part P foundation work.

P1 is contract-only. This module does not read files, scan repositories,
discover entry points, trace calls, traverse workspace graphs, write artifacts,
print output, or add journey data to AI context.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import PurePosixPath, PureWindowsPath
import re
from typing import Any

import strata.utils.workspace_config as workspace_config


USER_JOURNEY_SCHEMA_VERSION = 1

DEFAULT_MAX_ENTRY_POINTS = 20
DEFAULT_MAX_STEPS = 150
DEFAULT_MAX_TRANSITIONS = 300
DEFAULT_MAX_GAPS = 100
DEFAULT_MAX_DIAGNOSTICS = 200
DEFAULT_MAX_EVIDENCE_PER_ENTRY_POINT = 8
DEFAULT_MAX_EVIDENCE_PER_STEP = 8
DEFAULT_MAX_EVIDENCE_PER_TRANSITION = 8
DEFAULT_MAX_EVIDENCE_PER_GAP = 8
MAX_TEXT_LENGTH = 240
MAX_KEYWORDS = 12

CONFIDENCE_LOW = "low"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_HIGH = "high"
CONFIDENCE_LEVELS = (
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    CONFIDENCE_HIGH,
)

EVIDENCE_STRENGTH_WEAK = "weak"
EVIDENCE_STRENGTH_MEDIUM = "medium"
EVIDENCE_STRENGTH_STRONG = "strong"
EVIDENCE_STRENGTHS = (
    EVIDENCE_STRENGTH_WEAK,
    EVIDENCE_STRENGTH_MEDIUM,
    EVIDENCE_STRENGTH_STRONG,
)

DIAGNOSTIC_SEVERITY_INFO = "info"
DIAGNOSTIC_SEVERITY_WARNING = "warning"
DIAGNOSTIC_SEVERITY_ERROR = "error"
DIAGNOSTIC_SEVERITIES = (
    DIAGNOSTIC_SEVERITY_INFO,
    DIAGNOSTIC_SEVERITY_WARNING,
    DIAGNOSTIC_SEVERITY_ERROR,
)

ENTRY_POINT_TYPE_UI_EVENT = "ui_event"
ENTRY_POINT_TYPE_ROUTE = "route"
ENTRY_POINT_TYPE_PAGE = "page"
ENTRY_POINT_TYPE_COMPONENT = "component"
ENTRY_POINT_TYPE_TEMPLATE = "template"
ENTRY_POINT_TYPE_FORM = "form"
ENTRY_POINT_TYPE_BUTTON = "button"
ENTRY_POINT_TYPE_LINK = "link"
ENTRY_POINT_TYPE_KEYBOARD_ACTION = "keyboard_action"
ENTRY_POINT_TYPE_MESSAGE_EVENT = "message_event"
ENTRY_POINT_TYPE_API_REQUEST = "api_request"
ENTRY_POINT_TYPE_EXPLICIT_SYMBOL = "explicit_symbol"
ENTRY_POINT_TYPE_EXPLICIT_PATH = "explicit_path"
ENTRY_POINT_TYPE_UNKNOWN = "unknown"
ENTRY_POINT_TYPES = (
    ENTRY_POINT_TYPE_UI_EVENT,
    ENTRY_POINT_TYPE_ROUTE,
    ENTRY_POINT_TYPE_PAGE,
    ENTRY_POINT_TYPE_COMPONENT,
    ENTRY_POINT_TYPE_TEMPLATE,
    ENTRY_POINT_TYPE_FORM,
    ENTRY_POINT_TYPE_BUTTON,
    ENTRY_POINT_TYPE_LINK,
    ENTRY_POINT_TYPE_KEYBOARD_ACTION,
    ENTRY_POINT_TYPE_MESSAGE_EVENT,
    ENTRY_POINT_TYPE_API_REQUEST,
    ENTRY_POINT_TYPE_EXPLICIT_SYMBOL,
    ENTRY_POINT_TYPE_EXPLICIT_PATH,
    ENTRY_POINT_TYPE_UNKNOWN,
)

ORIGIN_EXPLICIT = "explicit"
ORIGIN_TASK_MATCH = "task_match"
ORIGIN_ROUTE_MATCH = "route_match"
ORIGIN_UI_TEXT_MATCH = "ui_text_match"
ORIGIN_SYMBOL_MATCH = "symbol_match"
ORIGIN_WORKSPACE_HINT = "workspace_hint"
ORIGIN_INFERRED = "inferred"
ORIGIN_UNKNOWN = "unknown"
ORIGINS = (
    ORIGIN_EXPLICIT,
    ORIGIN_TASK_MATCH,
    ORIGIN_ROUTE_MATCH,
    ORIGIN_UI_TEXT_MATCH,
    ORIGIN_SYMBOL_MATCH,
    ORIGIN_WORKSPACE_HINT,
    ORIGIN_INFERRED,
    ORIGIN_UNKNOWN,
)

STEP_TYPE_USER_ACTION = "user_action"
STEP_TYPE_UI_EVENT_HANDLER = "ui_event_handler"
STEP_TYPE_COMPONENT_METHOD = "component_method"
STEP_TYPE_FRONTEND_SERVICE = "frontend_service"
STEP_TYPE_FRONTEND_STATE = "frontend_state"
STEP_TYPE_FRONTEND_ROUTE = "frontend_route"
STEP_TYPE_API_REQUEST = "api_request"
STEP_TYPE_API_CLIENT = "api_client"
STEP_TYPE_WORKSPACE_BOUNDARY = "workspace_boundary"
STEP_TYPE_BACKEND_ROUTE = "backend_route"
STEP_TYPE_BACKEND_HANDLER = "backend_handler"
STEP_TYPE_BACKEND_SERVICE = "backend_service"
STEP_TYPE_AUTHENTICATION = "authentication"
STEP_TYPE_AUTHORIZATION = "authorization"
STEP_TYPE_VALIDATION = "validation"
STEP_TYPE_BUSINESS_LOGIC = "business_logic"
STEP_TYPE_DATABASE_ACCESS = "database_access"
STEP_TYPE_CACHE_ACCESS = "cache_access"
STEP_TYPE_QUEUE_PUBLISH = "queue_publish"
STEP_TYPE_QUEUE_CONSUME = "queue_consume"
STEP_TYPE_EXTERNAL_SERVICE = "external_service"
STEP_TYPE_IFRAME_SEND = "iframe_send"
STEP_TYPE_IFRAME_RECEIVE = "iframe_receive"
STEP_TYPE_MESSAGE_SEND = "message_send"
STEP_TYPE_MESSAGE_RECEIVE = "message_receive"
STEP_TYPE_RESPONSE = "response"
STEP_TYPE_FRONTEND_UPDATE = "frontend_update"
STEP_TYPE_NAVIGATION = "navigation"
STEP_TYPE_RENDER = "render"
STEP_TYPE_UNKNOWN = "unknown"
STEP_TYPES = (
    STEP_TYPE_USER_ACTION,
    STEP_TYPE_UI_EVENT_HANDLER,
    STEP_TYPE_COMPONENT_METHOD,
    STEP_TYPE_FRONTEND_SERVICE,
    STEP_TYPE_FRONTEND_STATE,
    STEP_TYPE_FRONTEND_ROUTE,
    STEP_TYPE_API_REQUEST,
    STEP_TYPE_API_CLIENT,
    STEP_TYPE_WORKSPACE_BOUNDARY,
    STEP_TYPE_BACKEND_ROUTE,
    STEP_TYPE_BACKEND_HANDLER,
    STEP_TYPE_BACKEND_SERVICE,
    STEP_TYPE_AUTHENTICATION,
    STEP_TYPE_AUTHORIZATION,
    STEP_TYPE_VALIDATION,
    STEP_TYPE_BUSINESS_LOGIC,
    STEP_TYPE_DATABASE_ACCESS,
    STEP_TYPE_CACHE_ACCESS,
    STEP_TYPE_QUEUE_PUBLISH,
    STEP_TYPE_QUEUE_CONSUME,
    STEP_TYPE_EXTERNAL_SERVICE,
    STEP_TYPE_IFRAME_SEND,
    STEP_TYPE_IFRAME_RECEIVE,
    STEP_TYPE_MESSAGE_SEND,
    STEP_TYPE_MESSAGE_RECEIVE,
    STEP_TYPE_RESPONSE,
    STEP_TYPE_FRONTEND_UPDATE,
    STEP_TYPE_NAVIGATION,
    STEP_TYPE_RENDER,
    STEP_TYPE_UNKNOWN,
)

PHASE_ENTRY = "entry"
PHASE_FRONTEND = "frontend"
PHASE_BOUNDARY = "boundary"
PHASE_BACKEND = "backend"
PHASE_DATA = "data"
PHASE_EXTERNAL = "external"
PHASE_RESPONSE = "response"
PHASE_FRONTEND_COMPLETION = "frontend_completion"
PHASE_UNKNOWN = "unknown"
PHASES = (
    PHASE_ENTRY,
    PHASE_FRONTEND,
    PHASE_BOUNDARY,
    PHASE_BACKEND,
    PHASE_DATA,
    PHASE_EXTERNAL,
    PHASE_RESPONSE,
    PHASE_FRONTEND_COMPLETION,
    PHASE_UNKNOWN,
)
STEP_TYPE_PHASES = {
    STEP_TYPE_USER_ACTION: PHASE_ENTRY,
    STEP_TYPE_UI_EVENT_HANDLER: PHASE_FRONTEND,
    STEP_TYPE_COMPONENT_METHOD: PHASE_FRONTEND,
    STEP_TYPE_FRONTEND_SERVICE: PHASE_FRONTEND,
    STEP_TYPE_FRONTEND_STATE: PHASE_FRONTEND,
    STEP_TYPE_FRONTEND_ROUTE: PHASE_FRONTEND,
    STEP_TYPE_API_REQUEST: PHASE_BOUNDARY,
    STEP_TYPE_API_CLIENT: PHASE_BOUNDARY,
    STEP_TYPE_WORKSPACE_BOUNDARY: PHASE_BOUNDARY,
    STEP_TYPE_IFRAME_SEND: PHASE_BOUNDARY,
    STEP_TYPE_IFRAME_RECEIVE: PHASE_BOUNDARY,
    STEP_TYPE_MESSAGE_SEND: PHASE_BOUNDARY,
    STEP_TYPE_MESSAGE_RECEIVE: PHASE_BOUNDARY,
    STEP_TYPE_BACKEND_ROUTE: PHASE_BACKEND,
    STEP_TYPE_BACKEND_HANDLER: PHASE_BACKEND,
    STEP_TYPE_BACKEND_SERVICE: PHASE_BACKEND,
    STEP_TYPE_AUTHENTICATION: PHASE_BACKEND,
    STEP_TYPE_AUTHORIZATION: PHASE_BACKEND,
    STEP_TYPE_VALIDATION: PHASE_BACKEND,
    STEP_TYPE_BUSINESS_LOGIC: PHASE_BACKEND,
    STEP_TYPE_DATABASE_ACCESS: PHASE_DATA,
    STEP_TYPE_CACHE_ACCESS: PHASE_DATA,
    STEP_TYPE_QUEUE_PUBLISH: PHASE_DATA,
    STEP_TYPE_QUEUE_CONSUME: PHASE_DATA,
    STEP_TYPE_EXTERNAL_SERVICE: PHASE_EXTERNAL,
    STEP_TYPE_RESPONSE: PHASE_RESPONSE,
    STEP_TYPE_FRONTEND_UPDATE: PHASE_FRONTEND_COMPLETION,
    STEP_TYPE_NAVIGATION: PHASE_FRONTEND_COMPLETION,
    STEP_TYPE_RENDER: PHASE_FRONTEND_COMPLETION,
    STEP_TYPE_UNKNOWN: PHASE_UNKNOWN,
}

TRANSITION_TYPE_CALLS = "calls"
TRANSITION_TYPE_HANDLES = "handles"
TRANSITION_TYPE_ROUTES_TO = "routes_to"
TRANSITION_TYPE_IMPORTS = "imports"
TRANSITION_TYPE_DISPATCHES = "dispatches"
TRANSITION_TYPE_SUBSCRIBES = "subscribes"
TRANSITION_TYPE_READS_STATE = "reads_state"
TRANSITION_TYPE_WRITES_STATE = "writes_state"
TRANSITION_TYPE_SENDS_REQUEST = "sends_request"
TRANSITION_TYPE_RECEIVES_REQUEST = "receives_request"
TRANSITION_TYPE_RETURNS_RESPONSE = "returns_response"
TRANSITION_TYPE_NAVIGATES_TO = "navigates_to"
TRANSITION_TYPE_RENDERS = "renders"
TRANSITION_TYPE_SENDS_MESSAGE = "sends_message"
TRANSITION_TYPE_RECEIVES_MESSAGE = "receives_message"
TRANSITION_TYPE_EMBEDS = "embeds"
TRANSITION_TYPE_CROSSES_REPOSITORY = "crosses_repository"
TRANSITION_TYPE_CONTINUES_AS = "continues_as"
TRANSITION_TYPE_INFERRED = "inferred"
TRANSITION_TYPE_UNKNOWN = "unknown"
TRANSITION_TYPES = (
    TRANSITION_TYPE_CALLS,
    TRANSITION_TYPE_HANDLES,
    TRANSITION_TYPE_ROUTES_TO,
    TRANSITION_TYPE_IMPORTS,
    TRANSITION_TYPE_DISPATCHES,
    TRANSITION_TYPE_SUBSCRIBES,
    TRANSITION_TYPE_READS_STATE,
    TRANSITION_TYPE_WRITES_STATE,
    TRANSITION_TYPE_SENDS_REQUEST,
    TRANSITION_TYPE_RECEIVES_REQUEST,
    TRANSITION_TYPE_RETURNS_RESPONSE,
    TRANSITION_TYPE_NAVIGATES_TO,
    TRANSITION_TYPE_RENDERS,
    TRANSITION_TYPE_SENDS_MESSAGE,
    TRANSITION_TYPE_RECEIVES_MESSAGE,
    TRANSITION_TYPE_EMBEDS,
    TRANSITION_TYPE_CROSSES_REPOSITORY,
    TRANSITION_TYPE_CONTINUES_AS,
    TRANSITION_TYPE_INFERRED,
    TRANSITION_TYPE_UNKNOWN,
)

GAP_REASON_ENTRY_POINT_NOT_FOUND = "entry_point_not_found"
GAP_REASON_SYMBOL_NOT_FOUND = "symbol_not_found"
GAP_REASON_TARGET_REPOSITORY_UNKNOWN = "target_repository_unknown"
GAP_REASON_TARGET_PATH_UNKNOWN = "target_path_unknown"
GAP_REASON_DYNAMIC_CALL_UNRESOLVED = "dynamic_call_unresolved"
GAP_REASON_RUNTIME_ROUTE_UNRESOLVED = "runtime_route_unresolved"
GAP_REASON_DEPENDENCY_UNRESOLVED = "dependency_unresolved"
GAP_REASON_API_TARGET_AMBIGUOUS = "api_target_ambiguous"
GAP_REASON_MESSAGE_TARGET_AMBIGUOUS = "message_target_ambiguous"
GAP_REASON_FRAMEWORK_BINDING_UNRESOLVED = "framework_binding_unresolved"
GAP_REASON_EXTERNAL_BOUNDARY = "external_boundary"
GAP_REASON_EVIDENCE_CAP_REACHED = "evidence_cap_reached"
GAP_REASON_STEP_CAP_REACHED = "step_cap_reached"
GAP_REASON_TRANSITION_CAP_REACHED = "transition_cap_reached"
GAP_REASON_UNSUPPORTED_LANGUAGE = "unsupported_language"
GAP_REASON_UNSUPPORTED_PATTERN = "unsupported_pattern"
GAP_REASON_SOURCE_UNREADABLE = "source_unreadable"
GAP_REASON_SOURCE_SKIPPED = "source_skipped"
GAP_REASON_UNKNOWN = "unknown"
GAP_REASONS = (
    GAP_REASON_ENTRY_POINT_NOT_FOUND,
    GAP_REASON_SYMBOL_NOT_FOUND,
    GAP_REASON_TARGET_REPOSITORY_UNKNOWN,
    GAP_REASON_TARGET_PATH_UNKNOWN,
    GAP_REASON_DYNAMIC_CALL_UNRESOLVED,
    GAP_REASON_RUNTIME_ROUTE_UNRESOLVED,
    GAP_REASON_DEPENDENCY_UNRESOLVED,
    GAP_REASON_API_TARGET_AMBIGUOUS,
    GAP_REASON_MESSAGE_TARGET_AMBIGUOUS,
    GAP_REASON_FRAMEWORK_BINDING_UNRESOLVED,
    GAP_REASON_EXTERNAL_BOUNDARY,
    GAP_REASON_EVIDENCE_CAP_REACHED,
    GAP_REASON_STEP_CAP_REACHED,
    GAP_REASON_TRANSITION_CAP_REACHED,
    GAP_REASON_UNSUPPORTED_LANGUAGE,
    GAP_REASON_UNSUPPORTED_PATTERN,
    GAP_REASON_SOURCE_UNREADABLE,
    GAP_REASON_SOURCE_SKIPPED,
    GAP_REASON_UNKNOWN,
)

READINESS_COMPLETE = "complete"
READINESS_PARTIAL = "partial"
READINESS_BLOCKED = "blocked"
READINESS_NOT_FOUND = "not_found"
READINESS_UNSUPPORTED = "unsupported"
READINESS_VALUES = (
    READINESS_COMPLETE,
    READINESS_PARTIAL,
    READINESS_BLOCKED,
    READINESS_NOT_FOUND,
    READINESS_UNSUPPORTED,
)

DIAGNOSTIC_JOURNEY_REQUEST_INVALID = "journey_request_invalid"
DIAGNOSTIC_JOURNEY_ENTRY_POINT_DUPLICATE = "journey_entry_point_duplicate"
DIAGNOSTIC_JOURNEY_STEP_DUPLICATE = "journey_step_duplicate"
DIAGNOSTIC_JOURNEY_STEP_CONFLICT = "journey_step_conflict"
DIAGNOSTIC_JOURNEY_TRANSITION_DUPLICATE = "journey_transition_duplicate"
DIAGNOSTIC_JOURNEY_TRANSITION_CONFLICT = "journey_transition_conflict"
DIAGNOSTIC_JOURNEY_TRANSITION_UNKNOWN_STEP = "journey_transition_unknown_step"
DIAGNOSTIC_JOURNEY_SELF_TRANSITION = "journey_self_transition"
DIAGNOSTIC_JOURNEY_GAP_DUPLICATE = "journey_gap_duplicate"
DIAGNOSTIC_JOURNEY_EVIDENCE_TRUNCATED = "journey_evidence_truncated"
DIAGNOSTIC_JOURNEY_ENTRY_POINT_CAP_REACHED = "journey_entry_point_cap_reached"
DIAGNOSTIC_JOURNEY_STEP_CAP_REACHED = "journey_step_cap_reached"
DIAGNOSTIC_JOURNEY_TRANSITION_CAP_REACHED = "journey_transition_cap_reached"
DIAGNOSTIC_JOURNEY_GAP_CAP_REACHED = "journey_gap_cap_reached"
DIAGNOSTIC_JOURNEY_DIAGNOSTIC_CAP_REACHED = "journey_diagnostic_cap_reached"
DIAGNOSTIC_JOURNEY_REPOSITORY_UNKNOWN = "journey_repository_unknown"
DIAGNOSTIC_JOURNEY_PATH_INVALID = "journey_path_invalid"
DIAGNOSTIC_JOURNEY_CONFIDENCE_INVALID = "journey_confidence_invalid"
DIAGNOSTIC_JOURNEY_SCHEMA_VERSION_INVALID = "journey_schema_version_invalid"
DIAGNOSTIC_ENTRY_SELECTED_PATH_MISSING = "entry_selected_path_missing"
DIAGNOSTIC_ENTRY_SELECTED_PATH_INVALID = "entry_selected_path_invalid"
DIAGNOSTIC_ENTRY_SELECTED_PATH_OUTSIDE_REPOSITORY = "entry_selected_path_outside_repository"
DIAGNOSTIC_ENTRY_SYMLINK_SKIPPED = "entry_symlink_skipped"
DIAGNOSTIC_ENTRY_FILE_TOO_LARGE = "entry_file_too_large"
DIAGNOSTIC_ENTRY_FILE_UNREADABLE = "entry_file_unreadable"
DIAGNOSTIC_ENTRY_UNSUPPORTED_FILE = "entry_unsupported_file"
DIAGNOSTIC_ENTRY_DYNAMIC_BINDING_UNRESOLVED = "entry_dynamic_binding_unresolved"
DIAGNOSTIC_ENTRY_ROUTE_AMBIGUOUS = "entry_route_ambiguous"
DIAGNOSTIC_ENTRY_SYMBOL_AMBIGUOUS = "entry_symbol_ambiguous"
DIAGNOSTIC_ENTRY_CAP_REACHED = "entry_cap_reached"
DIAGNOSTIC_ENTRY_EVIDENCE_TRUNCATED = "entry_evidence_truncated"
DIAGNOSTIC_FRONTEND_FILE_TOO_LARGE = "frontend_file_too_large"
DIAGNOSTIC_FRONTEND_FILE_UNREADABLE = "frontend_file_unreadable"
DIAGNOSTIC_FRONTEND_UNSUPPORTED_FILE = "frontend_unsupported_file"
DIAGNOSTIC_FRONTEND_TRACE_DEPTH_CAP_REACHED = "frontend_trace_depth_cap_reached"
DIAGNOSTIC_FRONTEND_STEP_CAP_REACHED = "frontend_step_cap_reached"
DIAGNOSTIC_FRONTEND_TRANSITION_CAP_REACHED = "frontend_transition_cap_reached"
DIAGNOSTIC_FRONTEND_DYNAMIC_CALL_UNRESOLVED = "frontend_dynamic_call_unresolved"
DIAGNOSTIC_FRONTEND_SYMBOL_NOT_FOUND = "frontend_symbol_not_found"
DIAGNOSTIC_API_REQUEST_UNRESOLVED = "api_request_unresolved"
DIAGNOSTIC_API_METHOD_UNKNOWN = "api_method_unknown"
DIAGNOSTIC_API_ROUTE_UNKNOWN = "api_route_unknown"
DIAGNOSTIC_API_TARGET_AMBIGUOUS = "api_target_ambiguous"
DIAGNOSTIC_TARGET_REPOSITORY_UNKNOWN = "target_repository_unknown"
DIAGNOSTIC_BACKEND_ROUTE_NOT_FOUND = "backend_route_not_found"
DIAGNOSTIC_BACKEND_ROUTE_AMBIGUOUS = "backend_route_ambiguous"
DIAGNOSTIC_WORKSPACE_RELATIONSHIP_MISSING = "workspace_relationship_missing"
DIAGNOSTIC_ROUTE_PARAMETER_UNRESOLVED = "route_parameter_unresolved"
DIAGNOSTIC_CODES = (
    DIAGNOSTIC_JOURNEY_REQUEST_INVALID,
    DIAGNOSTIC_JOURNEY_ENTRY_POINT_DUPLICATE,
    DIAGNOSTIC_JOURNEY_STEP_DUPLICATE,
    DIAGNOSTIC_JOURNEY_STEP_CONFLICT,
    DIAGNOSTIC_JOURNEY_TRANSITION_DUPLICATE,
    DIAGNOSTIC_JOURNEY_TRANSITION_CONFLICT,
    DIAGNOSTIC_JOURNEY_TRANSITION_UNKNOWN_STEP,
    DIAGNOSTIC_JOURNEY_SELF_TRANSITION,
    DIAGNOSTIC_JOURNEY_GAP_DUPLICATE,
    DIAGNOSTIC_JOURNEY_EVIDENCE_TRUNCATED,
    DIAGNOSTIC_JOURNEY_ENTRY_POINT_CAP_REACHED,
    DIAGNOSTIC_JOURNEY_STEP_CAP_REACHED,
    DIAGNOSTIC_JOURNEY_TRANSITION_CAP_REACHED,
    DIAGNOSTIC_JOURNEY_GAP_CAP_REACHED,
    DIAGNOSTIC_JOURNEY_DIAGNOSTIC_CAP_REACHED,
    DIAGNOSTIC_JOURNEY_REPOSITORY_UNKNOWN,
    DIAGNOSTIC_JOURNEY_PATH_INVALID,
    DIAGNOSTIC_JOURNEY_CONFIDENCE_INVALID,
    DIAGNOSTIC_JOURNEY_SCHEMA_VERSION_INVALID,
    DIAGNOSTIC_ENTRY_SELECTED_PATH_MISSING,
    DIAGNOSTIC_ENTRY_SELECTED_PATH_INVALID,
    DIAGNOSTIC_ENTRY_SELECTED_PATH_OUTSIDE_REPOSITORY,
    DIAGNOSTIC_ENTRY_SYMLINK_SKIPPED,
    DIAGNOSTIC_ENTRY_FILE_TOO_LARGE,
    DIAGNOSTIC_ENTRY_FILE_UNREADABLE,
    DIAGNOSTIC_ENTRY_UNSUPPORTED_FILE,
    DIAGNOSTIC_ENTRY_DYNAMIC_BINDING_UNRESOLVED,
    DIAGNOSTIC_ENTRY_ROUTE_AMBIGUOUS,
    DIAGNOSTIC_ENTRY_SYMBOL_AMBIGUOUS,
    DIAGNOSTIC_ENTRY_CAP_REACHED,
    DIAGNOSTIC_ENTRY_EVIDENCE_TRUNCATED,
    DIAGNOSTIC_FRONTEND_FILE_TOO_LARGE,
    DIAGNOSTIC_FRONTEND_FILE_UNREADABLE,
    DIAGNOSTIC_FRONTEND_UNSUPPORTED_FILE,
    DIAGNOSTIC_FRONTEND_TRACE_DEPTH_CAP_REACHED,
    DIAGNOSTIC_FRONTEND_STEP_CAP_REACHED,
    DIAGNOSTIC_FRONTEND_TRANSITION_CAP_REACHED,
    DIAGNOSTIC_FRONTEND_DYNAMIC_CALL_UNRESOLVED,
    DIAGNOSTIC_FRONTEND_SYMBOL_NOT_FOUND,
    DIAGNOSTIC_API_REQUEST_UNRESOLVED,
    DIAGNOSTIC_API_METHOD_UNKNOWN,
    DIAGNOSTIC_API_ROUTE_UNKNOWN,
    DIAGNOSTIC_API_TARGET_AMBIGUOUS,
    DIAGNOSTIC_TARGET_REPOSITORY_UNKNOWN,
    DIAGNOSTIC_BACKEND_ROUTE_NOT_FOUND,
    DIAGNOSTIC_BACKEND_ROUTE_AMBIGUOUS,
    DIAGNOSTIC_WORKSPACE_RELATIONSHIP_MISSING,
    DIAGNOSTIC_ROUTE_PARAMETER_UNRESOLVED,
)

SECRET_VALUE = "[redacted]"
SECRET_KEYWORDS = ("password", "secret", "token", "api_key", "apikey", "private_key", "credential", "authorization")
SECRET_PATTERN = re.compile(r"(?i)(password|secret|token|api[_-]?key|private[_-]?key|credential|authorization)\s*[:=]\s*(?:Bearer\s+)?[^,\s;]+")
TASK_STOPWORDS = {
    "a",
    "an",
    "and",
    "from",
    "happens",
    "the",
    "to",
    "trace",
    "user",
    "what",
    "when",
}
SEVERITY_ORDER = {
    DIAGNOSTIC_SEVERITY_ERROR: 0,
    DIAGNOSTIC_SEVERITY_WARNING: 1,
    DIAGNOSTIC_SEVERITY_INFO: 2,
}


class UserJourneyError(ValueError):
    """Raised when a Part P journey contract is invalid."""


@dataclass(frozen=True, slots=True)
class JourneyRequest:
    task: str
    journey_name: str | None = None
    starting_repository_ids: tuple[str, ...] = ()
    starting_paths: tuple[str, ...] = ()
    starting_symbols: tuple[str, ...] = ()
    route_hints: tuple[str, ...] = ()
    ui_hints: tuple[str, ...] = ()
    expected_destination: str | None = None
    metadata: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "task", _validate_task(self.task))
        object.__setattr__(self, "journey_name", _validate_optional_text(self.journey_name, "journey_name"))
        object.__setattr__(self, "starting_repository_ids", _normalize_string_tuple(self.starting_repository_ids, "starting_repository_ids"))
        object.__setattr__(self, "starting_paths", _normalize_path_tuple(self.starting_paths, "starting_paths"))
        object.__setattr__(self, "starting_symbols", _normalize_string_tuple(self.starting_symbols, "starting_symbols"))
        object.__setattr__(self, "route_hints", _normalize_string_tuple(self.route_hints, "route_hints"))
        object.__setattr__(self, "ui_hints", _normalize_string_tuple(self.ui_hints, "ui_hints"))
        object.__setattr__(self, "expected_destination", _validate_optional_text(self.expected_destination, "expected_destination"))
        object.__setattr__(self, "metadata", _copy_json(_redact_json(self.metadata or {}), "metadata"))

    @property
    def task_keywords(self) -> tuple[str, ...]:
        return task_keywords(self.task)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "journey_name": self.journey_name,
            "task_keywords": list(self.task_keywords),
            "starting_repository_ids": list(self.starting_repository_ids),
            "starting_paths": list(self.starting_paths),
            "starting_symbols": list(self.starting_symbols),
            "route_hints": list(self.route_hints),
            "ui_hints": list(self.ui_hints),
            "expected_destination": self.expected_destination,
            "metadata": _json_ready(self.metadata or {}),
        }


@dataclass(frozen=True, slots=True)
class JourneyEvidence:
    signal_type: str
    repository_id: str
    path: str
    summary: str
    strength: str
    symbol: str | None = None
    line_number: int | None = None
    related_repository_id: str | None = None
    related_path: str | None = None
    metadata: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "signal_type", _validate_nonempty_string(self.signal_type, "signal_type"))
        object.__setattr__(self, "repository_id", _validate_nonempty_string(self.repository_id, "repository_id"))
        object.__setattr__(self, "path", _normalize_relative_path(self.path, "path", allow_current=True))
        object.__setattr__(self, "summary", _redact_text(_validate_nonempty_string(self.summary, "summary")))
        object.__setattr__(self, "strength", _validate_choice(self.strength, "strength", EVIDENCE_STRENGTHS))
        object.__setattr__(self, "symbol", _validate_optional_text(self.symbol, "symbol"))
        object.__setattr__(self, "line_number", _validate_optional_line_number(self.line_number, "line_number"))
        object.__setattr__(self, "related_repository_id", _validate_optional_text(self.related_repository_id, "related_repository_id"))
        object.__setattr__(self, "related_path", _normalize_optional_path(self.related_path, "related_path"))
        object.__setattr__(self, "metadata", _copy_json(_redact_json(self.metadata or {}), "metadata"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal_type": self.signal_type,
            "repository_id": self.repository_id,
            "path": self.path,
            "summary": self.summary,
            "strength": self.strength,
            "symbol": self.symbol,
            "line_number": self.line_number,
            "related_repository_id": self.related_repository_id,
            "related_path": self.related_path,
            "metadata": _json_ready(self.metadata or {}),
        }


@dataclass(frozen=True, slots=True)
class JourneyDiagnostic:
    code: str
    severity: str
    summary: str
    repository_id: str | None = None
    path: str | None = None
    symbol: str | None = None
    details: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", _validate_choice(self.code, "code", DIAGNOSTIC_CODES))
        object.__setattr__(self, "severity", _validate_choice(self.severity, "severity", DIAGNOSTIC_SEVERITIES))
        object.__setattr__(self, "summary", _redact_text(_validate_nonempty_string(self.summary, "summary")))
        object.__setattr__(self, "repository_id", _validate_optional_text(self.repository_id, "repository_id"))
        object.__setattr__(self, "path", _normalize_optional_path(self.path, "path"))
        object.__setattr__(self, "symbol", _validate_optional_text(self.symbol, "symbol"))
        object.__setattr__(self, "details", _copy_json(_redact_json(self.details or {}), "details"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "summary": self.summary,
            "repository_id": self.repository_id,
            "path": self.path,
            "symbol": self.symbol,
            "details": _json_ready(self.details or {}),
        }


@dataclass(frozen=True, slots=True)
class JourneyEntryPoint:
    repository_id: str
    path: str | None
    entry_point_type: str
    display_label: str
    confidence: str
    confidence_score: float
    symbol: str | None = None
    evidence: tuple[JourneyEvidence, ...] = ()
    origin: str = ORIGIN_UNKNOWN
    metadata: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "repository_id", _validate_nonempty_string(self.repository_id, "repository_id"))
        object.__setattr__(self, "path", _normalize_optional_path(self.path, "path"))
        object.__setattr__(self, "symbol", _validate_optional_text(self.symbol, "symbol"))
        object.__setattr__(self, "entry_point_type", _validate_choice(self.entry_point_type, "entry_point_type", ENTRY_POINT_TYPES))
        object.__setattr__(self, "display_label", _redact_text(_validate_nonempty_string(self.display_label, "display_label")))
        object.__setattr__(self, "confidence", _validate_choice(self.confidence, "confidence", CONFIDENCE_LEVELS))
        object.__setattr__(self, "confidence_score", validate_confidence_score(self.confidence_score))
        object.__setattr__(self, "evidence", _dedupe_evidence(self.evidence))
        object.__setattr__(self, "origin", _validate_choice(self.origin, "origin", ORIGINS))
        object.__setattr__(self, "metadata", _copy_json(_redact_json(self.metadata or {}), "metadata"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "repository_id": self.repository_id,
            "path": self.path,
            "symbol": self.symbol,
            "entry_point_type": self.entry_point_type,
            "display_label": self.display_label,
            "confidence": self.confidence,
            "confidence_score": self.confidence_score,
            "evidence": [item.to_dict() for item in self.evidence],
            "origin": self.origin,
            "metadata": _json_ready(self.metadata or {}),
        }


@dataclass(frozen=True, slots=True)
class JourneyStep:
    repository_id: str
    path: str | None
    step_type: str
    summary: str
    confidence: str
    confidence_score: float
    step_id: str | None = None
    sequence_hint: int = 0
    symbol: str | None = None
    phase: str | None = None
    evidence: tuple[JourneyEvidence, ...] = ()
    origin: str = ORIGIN_UNKNOWN
    input_hints: tuple[str, ...] = ()
    output_hints: tuple[str, ...] = ()
    workspace_graph_node_id: str | None = None
    workspace_contract_name: str | None = None
    semantic_discriminator: str | None = None
    metadata: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "repository_id", _validate_nonempty_string(self.repository_id, "repository_id"))
        object.__setattr__(self, "path", _normalize_optional_path(self.path, "path"))
        object.__setattr__(self, "symbol", _validate_optional_text(self.symbol, "symbol"))
        object.__setattr__(self, "step_type", _validate_choice(self.step_type, "step_type", STEP_TYPES))
        object.__setattr__(self, "summary", _redact_text(_validate_nonempty_string(self.summary, "summary")))
        object.__setattr__(self, "confidence", _validate_choice(self.confidence, "confidence", CONFIDENCE_LEVELS))
        object.__setattr__(self, "confidence_score", validate_confidence_score(self.confidence_score))
        object.__setattr__(self, "sequence_hint", _validate_nonnegative_int(self.sequence_hint, "sequence_hint"))
        normalized_phase = derive_phase(self.step_type) if self.phase is None else _validate_choice(self.phase, "phase", PHASES)
        object.__setattr__(self, "phase", normalized_phase)
        object.__setattr__(self, "evidence", _dedupe_evidence(self.evidence))
        object.__setattr__(self, "origin", _validate_choice(self.origin, "origin", ORIGINS))
        object.__setattr__(self, "input_hints", _normalize_string_tuple(self.input_hints, "input_hints"))
        object.__setattr__(self, "output_hints", _normalize_string_tuple(self.output_hints, "output_hints"))
        object.__setattr__(self, "workspace_graph_node_id", _validate_optional_text(self.workspace_graph_node_id, "workspace_graph_node_id"))
        object.__setattr__(self, "workspace_contract_name", _validate_optional_text(self.workspace_contract_name, "workspace_contract_name"))
        object.__setattr__(self, "semantic_discriminator", _validate_optional_text(self.semantic_discriminator, "semantic_discriminator"))
        object.__setattr__(self, "metadata", _copy_json(_redact_json(self.metadata or {}), "metadata"))
        object.__setattr__(self, "step_id", _normalize_step_id(self.step_id, self))

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "sequence_hint": self.sequence_hint,
            "repository_id": self.repository_id,
            "path": self.path,
            "symbol": self.symbol,
            "step_type": self.step_type,
            "phase": self.phase,
            "summary": self.summary,
            "confidence": self.confidence,
            "confidence_score": self.confidence_score,
            "evidence": [item.to_dict() for item in self.evidence],
            "origin": self.origin,
            "input_hints": list(self.input_hints),
            "output_hints": list(self.output_hints),
            "workspace_graph_node_id": self.workspace_graph_node_id,
            "workspace_contract_name": self.workspace_contract_name,
            "semantic_discriminator": self.semantic_discriminator,
            "metadata": _json_ready(self.metadata or {}),
        }


@dataclass(frozen=True, slots=True)
class JourneyTransition:
    source_step_id: str
    target_step_id: str
    transition_type: str
    confidence: str
    confidence_score: float
    evidence: tuple[JourneyEvidence, ...] = ()
    origin: str = ORIGIN_UNKNOWN
    cross_repository: bool = False
    relationship_type: str | None = None
    workspace_graph_edge_id: str | None = None
    workspace_contract_name: str | None = None
    metadata: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_step_id", _validate_nonempty_string(self.source_step_id, "source_step_id"))
        object.__setattr__(self, "target_step_id", _validate_nonempty_string(self.target_step_id, "target_step_id"))
        if self.source_step_id == self.target_step_id:
            raise UserJourneyError("transition source and target must differ")
        object.__setattr__(self, "transition_type", _validate_choice(self.transition_type, "transition_type", TRANSITION_TYPES))
        object.__setattr__(self, "confidence", _validate_choice(self.confidence, "confidence", CONFIDENCE_LEVELS))
        object.__setattr__(self, "confidence_score", validate_confidence_score(self.confidence_score))
        object.__setattr__(self, "evidence", _dedupe_evidence(self.evidence))
        object.__setattr__(self, "origin", _validate_choice(self.origin, "origin", ORIGINS))
        object.__setattr__(self, "cross_repository", _validate_bool(self.cross_repository, "cross_repository"))
        if self.relationship_type is not None:
            object.__setattr__(self, "relationship_type", _validate_choice(self.relationship_type, "relationship_type", workspace_config.RELATIONSHIP_TYPES))
        object.__setattr__(self, "workspace_graph_edge_id", _validate_optional_text(self.workspace_graph_edge_id, "workspace_graph_edge_id"))
        object.__setattr__(self, "workspace_contract_name", _validate_optional_text(self.workspace_contract_name, "workspace_contract_name"))
        object.__setattr__(self, "metadata", _copy_json(_redact_json(self.metadata or {}), "metadata"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_step_id": self.source_step_id,
            "target_step_id": self.target_step_id,
            "transition_type": self.transition_type,
            "confidence": self.confidence,
            "confidence_score": self.confidence_score,
            "evidence": [item.to_dict() for item in self.evidence],
            "origin": self.origin,
            "cross_repository": self.cross_repository,
            "relationship_type": self.relationship_type,
            "workspace_graph_edge_id": self.workspace_graph_edge_id,
            "workspace_contract_name": self.workspace_contract_name,
            "metadata": _json_ready(self.metadata or {}),
        }


@dataclass(frozen=True, slots=True)
class JourneyGap:
    reason: str
    summary: str
    severity: str
    gap_id: str | None = None
    source_step_id: str | None = None
    repository_id: str | None = None
    path: str | None = None
    symbol: str | None = None
    evidence: tuple[JourneyEvidence, ...] = ()
    metadata: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "reason", _validate_choice(self.reason, "reason", GAP_REASONS))
        object.__setattr__(self, "summary", _redact_text(_validate_nonempty_string(self.summary, "summary")))
        object.__setattr__(self, "severity", _validate_choice(self.severity, "severity", DIAGNOSTIC_SEVERITIES))
        object.__setattr__(self, "source_step_id", _validate_optional_text(self.source_step_id, "source_step_id"))
        object.__setattr__(self, "repository_id", _validate_optional_text(self.repository_id, "repository_id"))
        object.__setattr__(self, "path", _normalize_optional_path(self.path, "path"))
        object.__setattr__(self, "symbol", _validate_optional_text(self.symbol, "symbol"))
        object.__setattr__(self, "evidence", _dedupe_evidence(self.evidence))
        object.__setattr__(self, "metadata", _copy_json(_redact_json(self.metadata or {}), "metadata"))
        object.__setattr__(self, "gap_id", _normalize_gap_id(self.gap_id, self))

    def to_dict(self) -> dict[str, Any]:
        return {
            "gap_id": self.gap_id,
            "reason": self.reason,
            "summary": self.summary,
            "severity": self.severity,
            "source_step_id": self.source_step_id,
            "repository_id": self.repository_id,
            "path": self.path,
            "symbol": self.symbol,
            "evidence": [item.to_dict() for item in self.evidence],
            "metadata": _json_ready(self.metadata or {}),
        }


@dataclass(frozen=True, slots=True)
class UserJourneyResult:
    schema_version: int
    request: JourneyRequest
    entry_points: tuple[JourneyEntryPoint, ...]
    steps: tuple[JourneyStep, ...]
    transitions: tuple[JourneyTransition, ...]
    gaps: tuple[JourneyGap, ...]
    diagnostics: tuple[JourneyDiagnostic, ...]
    summary: Mapping[str, Any]
    readiness: str
    metadata: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.schema_version != USER_JOURNEY_SCHEMA_VERSION:
            raise UserJourneyError("journey schema_version must be 1")
        object.__setattr__(self, "request", _coerce_request(self.request))
        object.__setattr__(self, "entry_points", tuple(sorted((_coerce_entry_point(item) for item in self.entry_points), key=entry_point_sort_key)))
        object.__setattr__(self, "steps", tuple(sorted((_coerce_step(item) for item in self.steps), key=step_sort_key)))
        object.__setattr__(self, "transitions", tuple(sorted((_coerce_transition(item) for item in self.transitions), key=transition_sort_key)))
        object.__setattr__(self, "gaps", tuple(sorted((_coerce_gap(item) for item in self.gaps), key=gap_sort_key)))
        object.__setattr__(self, "diagnostics", tuple(sorted((_coerce_diagnostic(item) for item in self.diagnostics), key=diagnostic_sort_key)))
        object.__setattr__(self, "summary", _copy_json(self.summary, "summary"))
        object.__setattr__(self, "readiness", _validate_choice(self.readiness, "readiness", READINESS_VALUES))
        object.__setattr__(self, "metadata", _copy_json(_redact_json(self.metadata or {}), "metadata"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "request": self.request.to_dict(),
            "entry_points": [item.to_dict() for item in self.entry_points],
            "steps": [item.to_dict() for item in self.steps],
            "transitions": [item.to_dict() for item in self.transitions],
            "gaps": [item.to_dict() for item in self.gaps],
            "diagnostics": [item.to_dict() for item in self.diagnostics],
            "summary": _json_ready(self.summary),
            "readiness": self.readiness,
            "metadata": _json_ready(self.metadata or {}),
        }


def task_keywords(task: str) -> tuple[str, ...]:
    text = _validate_task(task)
    tokens = re.findall(r"[a-z0-9][a-z0-9_-]*", text.lower())
    return tuple(sorted({token for token in tokens if token not in TASK_STOPWORDS and len(token) > 1}))[:MAX_KEYWORDS]


def validate_confidence_score(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("confidence_score must be a number")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized < 0.0 or normalized > 1.0:
        raise UserJourneyError("confidence_score must be between 0.0 and 1.0")
    return round(normalized, 3)


def confidence_from_score(score: float) -> str:
    normalized = validate_confidence_score(score)
    if normalized >= 0.7:
        return CONFIDENCE_HIGH
    if normalized >= 0.4:
        return CONFIDENCE_MEDIUM
    return CONFIDENCE_LOW


def derive_phase(step_type: str) -> str:
    return STEP_TYPE_PHASES[_validate_choice(step_type, "step_type", STEP_TYPES)]


def evidence_identity_key(evidence: JourneyEvidence | Mapping[str, Any]) -> tuple[object, ...]:
    item = _coerce_evidence(evidence)
    return (
        item.signal_type,
        item.repository_id,
        item.path,
        item.symbol or "",
        item.line_number or 0,
        item.related_repository_id or "",
        item.related_path or "",
        item.summary,
        item.strength,
        json.dumps(_json_ready(item.metadata or {}), sort_keys=True),
    )


def entry_point_identity_key(entry_point: JourneyEntryPoint | Mapping[str, Any]) -> tuple[str, str, str, str]:
    item = _coerce_entry_point(entry_point)
    return (item.repository_id, item.path or "", item.symbol or "", item.entry_point_type)


def step_identity_key(step: JourneyStep | Mapping[str, Any]) -> tuple[str, str, str, str, str]:
    item = _coerce_step(step)
    return (item.repository_id, item.path or "", item.symbol or "", item.step_type, item.semantic_discriminator or "")


def transition_identity_key(transition: JourneyTransition | Mapping[str, Any]) -> tuple[str, str, str]:
    item = _coerce_transition(transition)
    return (item.source_step_id, item.target_step_id, item.transition_type)


def gap_identity_key(gap: JourneyGap | Mapping[str, Any]) -> tuple[str, str, str, str, str]:
    item = _coerce_gap(gap)
    return (item.reason, item.source_step_id or "", item.repository_id or "", item.path or "", item.symbol or "")


def entry_point_sort_key(entry_point: JourneyEntryPoint) -> tuple[object, ...]:
    return (-entry_point.confidence_score, entry_point.repository_id, entry_point.path or "", entry_point.symbol or "", entry_point.entry_point_type)


def step_sort_key(step: JourneyStep) -> tuple[object, ...]:
    return (step.sequence_hint, step.repository_id, step.path or "", step.symbol or "", step.step_type, step.step_id or "")


def transition_sort_key(transition: JourneyTransition) -> tuple[object, ...]:
    return (transition.source_step_id, transition.target_step_id, transition.transition_type)


def gap_sort_key(gap: JourneyGap) -> tuple[object, ...]:
    return (SEVERITY_ORDER[gap.severity], gap.reason, gap.repository_id or "", gap.path or "", gap.symbol or "", gap.gap_id or "")


def diagnostic_sort_key(diagnostic: JourneyDiagnostic) -> tuple[object, ...]:
    return (SEVERITY_ORDER[diagnostic.severity], diagnostic.code, diagnostic.repository_id or "", diagnostic.path or "", diagnostic.symbol or "", diagnostic.summary)


def build_user_journey_result(
    request: JourneyRequest | Mapping[str, Any],
    *,
    entry_points: Iterable[Any] = (),
    steps: Iterable[Any] = (),
    transitions: Iterable[Any] = (),
    gaps: Iterable[Any] = (),
    diagnostics: Iterable[Any] = (),
    readiness: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    max_entry_points: int = DEFAULT_MAX_ENTRY_POINTS,
    max_steps: int = DEFAULT_MAX_STEPS,
    max_transitions: int = DEFAULT_MAX_TRANSITIONS,
    max_gaps: int = DEFAULT_MAX_GAPS,
    max_diagnostics: int = DEFAULT_MAX_DIAGNOSTICS,
    max_evidence_per_entry_point: int = DEFAULT_MAX_EVIDENCE_PER_ENTRY_POINT,
    max_evidence_per_step: int = DEFAULT_MAX_EVIDENCE_PER_STEP,
    max_evidence_per_transition: int = DEFAULT_MAX_EVIDENCE_PER_TRANSITION,
    max_evidence_per_gap: int = DEFAULT_MAX_EVIDENCE_PER_GAP,
) -> UserJourneyResult:
    """Build a deterministic journey result from supplied contracts only."""

    max_entry_points = _validate_limit(max_entry_points, "max_entry_points")
    max_steps = _validate_limit(max_steps, "max_steps")
    max_transitions = _validate_limit(max_transitions, "max_transitions")
    max_gaps = _validate_limit(max_gaps, "max_gaps")
    max_diagnostics = _validate_limit(max_diagnostics, "max_diagnostics")
    max_evidence_per_entry_point = _validate_limit(max_evidence_per_entry_point, "max_evidence_per_entry_point")
    max_evidence_per_step = _validate_limit(max_evidence_per_step, "max_evidence_per_step")
    max_evidence_per_transition = _validate_limit(max_evidence_per_transition, "max_evidence_per_transition")
    max_evidence_per_gap = _validate_limit(max_evidence_per_gap, "max_evidence_per_gap")

    normalized_request = _coerce_request(request)
    result_diagnostics = [_coerce_diagnostic(item) for item in diagnostics]
    omitted_counts = {
        "entry_points": 0,
        "steps": 0,
        "transitions": 0,
        "gaps": 0,
        "diagnostics": 0,
        "evidence": 0,
    }

    normalized_entry_points = _dedupe_records(
        (_with_bounded_entry_point_evidence(_coerce_entry_point(item), max_evidence_per_entry_point, result_diagnostics, omitted_counts) for item in entry_points),
        entry_point_identity_key,
        DIAGNOSTIC_JOURNEY_ENTRY_POINT_DUPLICATE,
        DIAGNOSTIC_JOURNEY_ENTRY_POINT_DUPLICATE,
        result_diagnostics,
    )
    normalized_steps = _dedupe_records(
        (_with_bounded_step_evidence(_coerce_step(item), max_evidence_per_step, result_diagnostics, omitted_counts) for item in steps),
        step_identity_key,
        DIAGNOSTIC_JOURNEY_STEP_DUPLICATE,
        DIAGNOSTIC_JOURNEY_STEP_CONFLICT,
        result_diagnostics,
    )
    bounded_steps = _bound_records(
        normalized_steps,
        max_steps,
        step_sort_key,
        DIAGNOSTIC_JOURNEY_STEP_CAP_REACHED,
        "Journey step cap was reached.",
        result_diagnostics,
        omitted_counts,
        "steps",
    )
    step_ids = {step.step_id for step in bounded_steps}
    step_repositories = {step.step_id: step.repository_id for step in bounded_steps}

    normalized_transitions = []
    for item in transitions:
        transition = _with_bounded_transition_evidence(_coerce_transition(item), max_evidence_per_transition, result_diagnostics, omitted_counts)
        missing = []
        if transition.source_step_id not in step_ids:
            missing.append("source")
        if transition.target_step_id not in step_ids:
            missing.append("target")
        if missing:
            result_diagnostics.append(_diagnostic(DIAGNOSTIC_JOURNEY_TRANSITION_UNKNOWN_STEP, DIAGNOSTIC_SEVERITY_ERROR, "Journey transition references an unknown step.", details={"missing": tuple(missing), "transition": transition_identity_key(transition)}))
            continue
        expected_cross_repository = step_repositories[transition.source_step_id] != step_repositories[transition.target_step_id]
        if expected_cross_repository and not transition.cross_repository:
            result_diagnostics.append(_diagnostic(DIAGNOSTIC_JOURNEY_REPOSITORY_UNKNOWN, DIAGNOSTIC_SEVERITY_WARNING, "Cross-repository transition was not explicitly marked.", details={"transition": transition_identity_key(transition)}))
        normalized_transitions.append(transition)
    normalized_transitions = _dedupe_records(
        normalized_transitions,
        transition_identity_key,
        DIAGNOSTIC_JOURNEY_TRANSITION_DUPLICATE,
        DIAGNOSTIC_JOURNEY_TRANSITION_CONFLICT,
        result_diagnostics,
    )

    normalized_gaps = _dedupe_records(
        (_with_bounded_gap_evidence(_coerce_gap(item), max_evidence_per_gap, result_diagnostics, omitted_counts) for item in gaps),
        gap_identity_key,
        DIAGNOSTIC_JOURNEY_GAP_DUPLICATE,
        DIAGNOSTIC_JOURNEY_GAP_DUPLICATE,
        result_diagnostics,
    )
    bounded_entry_points = _bound_records(normalized_entry_points, max_entry_points, entry_point_sort_key, DIAGNOSTIC_JOURNEY_ENTRY_POINT_CAP_REACHED, "Journey entry-point cap was reached.", result_diagnostics, omitted_counts, "entry_points")
    bounded_transitions = _bound_records(normalized_transitions, max_transitions, transition_sort_key, DIAGNOSTIC_JOURNEY_TRANSITION_CAP_REACHED, "Journey transition cap was reached.", result_diagnostics, omitted_counts, "transitions")
    bounded_gaps = _bound_records(normalized_gaps, max_gaps, gap_sort_key, DIAGNOSTIC_JOURNEY_GAP_CAP_REACHED, "Journey gap cap was reached.", result_diagnostics, omitted_counts, "gaps")

    summary = _summary(bounded_entry_points, bounded_steps, bounded_transitions, bounded_gaps)
    final_readiness = _derive_readiness(readiness, bounded_entry_points, bounded_steps, bounded_gaps)
    bounded_diagnostics = _bound_diagnostics(result_diagnostics, max_diagnostics, omitted_counts)
    result_metadata = _copy_json(_redact_json(metadata or {}), "metadata")
    result_metadata["omitted_counts"] = {key: value for key, value in sorted(omitted_counts.items()) if value}
    return UserJourneyResult(
        schema_version=USER_JOURNEY_SCHEMA_VERSION,
        request=normalized_request,
        entry_points=bounded_entry_points,
        steps=bounded_steps,
        transitions=bounded_transitions,
        gaps=bounded_gaps,
        diagnostics=bounded_diagnostics,
        summary=summary,
        readiness=final_readiness,
        metadata=result_metadata,
    )


def user_journey_result_to_dict(result: UserJourneyResult) -> dict[str, Any]:
    if not isinstance(result, UserJourneyResult):
        raise TypeError("result must be a UserJourneyResult")
    return result.to_dict()


def _validate_task(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise UserJourneyError("task must be a non-empty string")
    if "\x00" in value:
        raise UserJourneyError("task must not contain null bytes")
    return _redact_text(value)


def _validate_nonempty_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise UserJourneyError(f"{name} must be a non-empty string")
    if value != value.strip() or "\x00" in value:
        raise UserJourneyError(f"{name} must not contain padding or null bytes")
    return _redact_text(value)


def _validate_optional_text(value: Any, name: str) -> str | None:
    if value is None:
        return None
    return _validate_nonempty_string(value, name)


def _validate_choice(value: Any, name: str, choices: tuple[str, ...]) -> str:
    text = _validate_nonempty_string(value, name)
    if text not in choices:
        raise UserJourneyError(f"{name} must be one of: {', '.join(choices)}")
    return text


def _validate_bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{name} must be a boolean")
    return value


def _validate_nonnegative_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 0:
        raise UserJourneyError(f"{name} must be non-negative")
    return value


def _validate_optional_line_number(value: Any, name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 1:
        raise UserJourneyError(f"{name} must be at least 1")
    return value


def _validate_limit(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 1:
        raise UserJourneyError(f"{name} must be at least 1")
    return value


def _normalize_string_tuple(value: Any, name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        raise TypeError(f"{name} must be an iterable of strings")
    try:
        items = tuple(value)
    except TypeError as error:
        raise TypeError(f"{name} must be an iterable of strings") from error
    normalized = {_validate_nonempty_string(item, f"{name}[{index}]") for index, item in enumerate(items)}
    return tuple(sorted(normalized))


def _normalize_path_tuple(value: Any, name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        raise TypeError(f"{name} must be an iterable of strings")
    try:
        items = tuple(value)
    except TypeError as error:
        raise TypeError(f"{name} must be an iterable of strings") from error
    normalized = {_normalize_relative_path(item, f"{name}[{index}]", allow_current=True) for index, item in enumerate(items)}
    return tuple(sorted(normalized))


def _normalize_relative_path(value: Any, name: str, *, allow_current: bool = False) -> str:
    text = _validate_nonempty_string(value, name)
    windows_path = PureWindowsPath(text)
    posix_text = text.replace("\\", "/")
    posix_path = PurePosixPath(posix_text)
    if windows_path.drive or windows_path.is_absolute() or posix_path.is_absolute():
        raise UserJourneyError(f"{name} must be relative")
    collapsed: list[str] = []
    for part in posix_path.parts:
        if part in ("", "."):
            continue
        if part == "..":
            if collapsed:
                collapsed.pop()
                continue
            raise UserJourneyError(f"{name} must not escape its repository with '..'")
        collapsed.append(part)
    if not collapsed:
        if allow_current:
            return "."
        raise UserJourneyError(f"{name} must identify a file")
    return PurePosixPath(*collapsed).as_posix()


def _normalize_optional_path(value: Any, name: str) -> str | None:
    if value is None:
        return None
    return _normalize_relative_path(value, name, allow_current=True)


def _copy_json(value: Any, name: str) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise UserJourneyError(f"{name} must be finite")
        return value
    if isinstance(value, Mapping):
        copied = {}
        for key in sorted(value):
            if not isinstance(key, str):
                raise UserJourneyError(f"{name} keys must be strings")
            copied[key] = _copy_json(value[key], f"{name}.{key}")
        return copied
    if isinstance(value, (list, tuple)):
        return tuple(_copy_json(item, f"{name}[{index}]") for index, item in enumerate(value))
    raise UserJourneyError(f"{name} must be JSON-ready")


def _json_ready(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, Mapping):
        return {key: _json_ready(value[key]) for key in sorted(value)}
    return value


def _redact_text(value: str) -> str:
    redacted = SECRET_PATTERN.sub(lambda match: f"{match.group(1)}={SECRET_VALUE}", value)
    if len(redacted) > MAX_TEXT_LENGTH:
        return redacted[: MAX_TEXT_LENGTH - 3] + "..."
    return redacted


def _redact_json(value: Any, key_hint: str = "") -> Any:
    if isinstance(value, Mapping):
        copied = {}
        for key in sorted(value):
            if not isinstance(key, str):
                copied[key] = value[key]
                continue
            if _is_secret_key(key):
                copied[key] = SECRET_VALUE
            else:
                copied[key] = _redact_json(value[key], key)
        return copied
    if isinstance(value, (list, tuple)):
        return tuple(_redact_json(item, key_hint) for item in value)
    if isinstance(value, str):
        if _is_secret_key(key_hint):
            return SECRET_VALUE
        return _redact_text(value)
    return value


def _is_secret_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(keyword in normalized for keyword in SECRET_KEYWORDS)


def _short_hash(parts: tuple[str, ...]) -> str:
    digest = hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()
    return digest[:16]


def _normalize_step_id(value: str | None, step: JourneyStep) -> str:
    if value is not None:
        return _validate_nonempty_string(value, "step_id")
    return "step:" + _short_hash(step_identity_key(step))


def _normalize_gap_id(value: str | None, gap: JourneyGap) -> str:
    if value is not None:
        return _validate_nonempty_string(value, "gap_id")
    return "gap:" + _short_hash(gap_identity_key(gap))


def _coerce_request(value: JourneyRequest | Mapping[str, Any]) -> JourneyRequest:
    if isinstance(value, JourneyRequest):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("request must be a JourneyRequest or mapping")
    return JourneyRequest(
        task=value["task"],
        journey_name=value.get("journey_name"),
        starting_repository_ids=tuple(value.get("starting_repository_ids", ())),
        starting_paths=tuple(value.get("starting_paths", ())),
        starting_symbols=tuple(value.get("starting_symbols", ())),
        route_hints=tuple(value.get("route_hints", ())),
        ui_hints=tuple(value.get("ui_hints", ())),
        expected_destination=value.get("expected_destination"),
        metadata=value.get("metadata"),
    )


def _coerce_evidence(value: JourneyEvidence | Mapping[str, Any]) -> JourneyEvidence:
    if isinstance(value, JourneyEvidence):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("evidence must be a JourneyEvidence or mapping")
    return JourneyEvidence(
        signal_type=value["signal_type"],
        repository_id=value["repository_id"],
        path=value.get("path", "."),
        summary=value["summary"],
        strength=value["strength"],
        symbol=value.get("symbol"),
        line_number=value.get("line_number"),
        related_repository_id=value.get("related_repository_id"),
        related_path=value.get("related_path"),
        metadata=value.get("metadata"),
    )


def _coerce_diagnostic(value: JourneyDiagnostic | Mapping[str, Any]) -> JourneyDiagnostic:
    if isinstance(value, JourneyDiagnostic):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("diagnostic must be a JourneyDiagnostic or mapping")
    return JourneyDiagnostic(
        code=value["code"],
        severity=value["severity"],
        summary=value["summary"],
        repository_id=value.get("repository_id"),
        path=value.get("path"),
        symbol=value.get("symbol"),
        details=value.get("details"),
    )


def _coerce_entry_point(value: JourneyEntryPoint | Mapping[str, Any]) -> JourneyEntryPoint:
    if isinstance(value, JourneyEntryPoint):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("entry point must be a JourneyEntryPoint or mapping")
    return JourneyEntryPoint(
        repository_id=value["repository_id"],
        path=value.get("path"),
        symbol=value.get("symbol"),
        entry_point_type=value["entry_point_type"],
        display_label=value["display_label"],
        confidence=value["confidence"],
        confidence_score=value["confidence_score"],
        evidence=tuple(value.get("evidence", ())),
        origin=value.get("origin", ORIGIN_UNKNOWN),
        metadata=value.get("metadata"),
    )


def _coerce_step(value: JourneyStep | Mapping[str, Any]) -> JourneyStep:
    if isinstance(value, JourneyStep):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("step must be a JourneyStep or mapping")
    return JourneyStep(
        step_id=value.get("step_id"),
        sequence_hint=value.get("sequence_hint", 0),
        repository_id=value["repository_id"],
        path=value.get("path"),
        symbol=value.get("symbol"),
        step_type=value["step_type"],
        phase=value.get("phase"),
        summary=value["summary"],
        confidence=value["confidence"],
        confidence_score=value["confidence_score"],
        evidence=tuple(value.get("evidence", ())),
        origin=value.get("origin", ORIGIN_UNKNOWN),
        input_hints=tuple(value.get("input_hints", ())),
        output_hints=tuple(value.get("output_hints", ())),
        workspace_graph_node_id=value.get("workspace_graph_node_id"),
        workspace_contract_name=value.get("workspace_contract_name"),
        semantic_discriminator=value.get("semantic_discriminator"),
        metadata=value.get("metadata"),
    )


def _coerce_transition(value: JourneyTransition | Mapping[str, Any]) -> JourneyTransition:
    if isinstance(value, JourneyTransition):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("transition must be a JourneyTransition or mapping")
    return JourneyTransition(
        source_step_id=value["source_step_id"],
        target_step_id=value["target_step_id"],
        transition_type=value["transition_type"],
        confidence=value["confidence"],
        confidence_score=value["confidence_score"],
        evidence=tuple(value.get("evidence", ())),
        origin=value.get("origin", ORIGIN_UNKNOWN),
        cross_repository=value.get("cross_repository", False),
        relationship_type=value.get("relationship_type"),
        workspace_graph_edge_id=value.get("workspace_graph_edge_id"),
        workspace_contract_name=value.get("workspace_contract_name"),
        metadata=value.get("metadata"),
    )


def _coerce_gap(value: JourneyGap | Mapping[str, Any]) -> JourneyGap:
    if isinstance(value, JourneyGap):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("gap must be a JourneyGap or mapping")
    return JourneyGap(
        gap_id=value.get("gap_id"),
        reason=value["reason"],
        summary=value["summary"],
        severity=value["severity"],
        source_step_id=value.get("source_step_id"),
        repository_id=value.get("repository_id"),
        path=value.get("path"),
        symbol=value.get("symbol"),
        evidence=tuple(value.get("evidence", ())),
        metadata=value.get("metadata"),
    )


def _dedupe_evidence(evidence: Iterable[Any]) -> tuple[JourneyEvidence, ...]:
    by_identity = {}
    for item in evidence:
        normalized = _coerce_evidence(item)
        by_identity.setdefault(evidence_identity_key(normalized), normalized)
    return tuple(by_identity[key] for key in sorted(by_identity))


def _bound_evidence(
    evidence: Iterable[JourneyEvidence],
    limit: int,
    diagnostics: list[JourneyDiagnostic],
    omitted_counts: dict[str, int],
    *,
    repository_id: str | None,
    path: str | None,
) -> tuple[JourneyEvidence, ...]:
    values = tuple(sorted(_dedupe_evidence(evidence), key=evidence_identity_key))
    if len(values) <= limit:
        return values
    omitted = len(values) - limit
    omitted_counts["evidence"] += omitted
    diagnostics.append(_diagnostic(DIAGNOSTIC_JOURNEY_EVIDENCE_TRUNCATED, DIAGNOSTIC_SEVERITY_WARNING, "Journey evidence was truncated.", repository_id=repository_id, path=path, details={"limit": limit, "omitted": omitted}))
    return values[:limit]


def _with_bounded_entry_point_evidence(entry_point: JourneyEntryPoint, limit: int, diagnostics: list[JourneyDiagnostic], omitted_counts: dict[str, int]) -> JourneyEntryPoint:
    evidence = _bound_evidence(entry_point.evidence, limit, diagnostics, omitted_counts, repository_id=entry_point.repository_id, path=entry_point.path)
    if evidence == entry_point.evidence:
        return entry_point
    return JourneyEntryPoint(**{**entry_point.to_dict(), "evidence": evidence})


def _with_bounded_step_evidence(step: JourneyStep, limit: int, diagnostics: list[JourneyDiagnostic], omitted_counts: dict[str, int]) -> JourneyStep:
    evidence = _bound_evidence(step.evidence, limit, diagnostics, omitted_counts, repository_id=step.repository_id, path=step.path)
    if evidence == step.evidence:
        return step
    return JourneyStep(**{**step.to_dict(), "evidence": evidence})


def _with_bounded_transition_evidence(transition: JourneyTransition, limit: int, diagnostics: list[JourneyDiagnostic], omitted_counts: dict[str, int]) -> JourneyTransition:
    evidence = _bound_evidence(transition.evidence, limit, diagnostics, omitted_counts, repository_id=None, path=None)
    if evidence == transition.evidence:
        return transition
    return JourneyTransition(**{**transition.to_dict(), "evidence": evidence})


def _with_bounded_gap_evidence(gap: JourneyGap, limit: int, diagnostics: list[JourneyDiagnostic], omitted_counts: dict[str, int]) -> JourneyGap:
    evidence = _bound_evidence(gap.evidence, limit, diagnostics, omitted_counts, repository_id=gap.repository_id, path=gap.path)
    if evidence == gap.evidence:
        return gap
    return JourneyGap(**{**gap.to_dict(), "evidence": evidence})


def _dedupe_records(
    records: Iterable[Any],
    identity,
    duplicate_code: str,
    conflict_code: str,
    diagnostics: list[JourneyDiagnostic],
) -> tuple[Any, ...]:
    by_identity = {}
    payloads = {}
    for record in records:
        key = identity(record)
        payload = record.to_dict()
        existing = by_identity.get(key)
        if existing is None:
            by_identity[key] = record
            payloads[key] = payload
            continue
        if payloads[key] == payload:
            diagnostics.append(_diagnostic(duplicate_code, DIAGNOSTIC_SEVERITY_INFO, "Duplicate journey record was deduplicated.", details={"identity": key}))
        else:
            diagnostics.append(_diagnostic(conflict_code, DIAGNOSTIC_SEVERITY_WARNING, "Conflicting journey record sharing an identity was ignored.", details={"identity": key}))
    return tuple(by_identity[key] for key in sorted(by_identity))


def _bound_records(
    records: Iterable[Any],
    limit: int,
    sort_key,
    diagnostic_code: str,
    summary: str,
    diagnostics: list[JourneyDiagnostic],
    omitted_counts: dict[str, int],
    omitted_key: str,
) -> tuple[Any, ...]:
    values = tuple(sorted(records, key=sort_key))
    if len(values) <= limit:
        return values
    omitted = len(values) - limit
    omitted_counts[omitted_key] += omitted
    diagnostics.append(_diagnostic(diagnostic_code, DIAGNOSTIC_SEVERITY_WARNING, summary, details={"limit": limit, "omitted": omitted}))
    return values[:limit]


def _bound_diagnostics(
    diagnostics: Iterable[JourneyDiagnostic],
    limit: int,
    omitted_counts: dict[str, int],
) -> tuple[JourneyDiagnostic, ...]:
    values = tuple(sorted((_coerce_diagnostic(item) for item in diagnostics), key=diagnostic_sort_key))
    if len(values) <= limit:
        return values
    omitted = len(values) if limit == 1 else len(values) - (limit - 1)
    omitted_counts["diagnostics"] += omitted
    cap = _diagnostic(DIAGNOSTIC_JOURNEY_DIAGNOSTIC_CAP_REACHED, DIAGNOSTIC_SEVERITY_WARNING, "Journey diagnostics were truncated.", details={"limit": limit, "omitted": omitted})
    if limit == 1:
        return (cap,)
    return (*values[: limit - 1], cap)


def _diagnostic(
    code: str,
    severity: str,
    summary: str,
    *,
    repository_id: str | None = None,
    path: str | None = None,
    symbol: str | None = None,
    details: Mapping[str, Any] | None = None,
) -> JourneyDiagnostic:
    return JourneyDiagnostic(code=code, severity=severity, summary=summary, repository_id=repository_id, path=path, symbol=symbol, details=details)


def _summary(
    entry_points: tuple[JourneyEntryPoint, ...],
    steps: tuple[JourneyStep, ...],
    transitions: tuple[JourneyTransition, ...],
    gaps: tuple[JourneyGap, ...],
) -> dict[str, Any]:
    repository_ids = {
        *(item.repository_id for item in entry_points),
        *(item.repository_id for item in steps),
        *(item.repository_id for item in gaps if item.repository_id),
        *(item.repository_id for transition in transitions for item in transition.evidence),
    }
    return {
        "entry_point_count": len(entry_points),
        "step_count": len(steps),
        "transition_count": len(transitions),
        "repository_count": len(repository_ids),
        "cross_repository_transition_count": sum(1 for item in transitions if item.cross_repository),
        "gap_count": len(gaps),
        "high_confidence_step_count": sum(1 for item in steps if item.confidence == CONFIDENCE_HIGH),
        "medium_confidence_step_count": sum(1 for item in steps if item.confidence == CONFIDENCE_MEDIUM),
        "low_confidence_step_count": sum(1 for item in steps if item.confidence == CONFIDENCE_LOW),
        "frontend_step_count": sum(1 for item in steps if item.phase == PHASE_FRONTEND),
        "backend_step_count": sum(1 for item in steps if item.phase == PHASE_BACKEND),
        "boundary_step_count": sum(1 for item in steps if item.phase == PHASE_BOUNDARY),
        "data_step_count": sum(1 for item in steps if item.phase == PHASE_DATA),
        "external_step_count": sum(1 for item in steps if item.phase == PHASE_EXTERNAL),
    }


def _derive_readiness(
    requested: str | None,
    entry_points: tuple[JourneyEntryPoint, ...],
    steps: tuple[JourneyStep, ...],
    gaps: tuple[JourneyGap, ...],
) -> str:
    if requested is not None:
        return _validate_choice(requested, "readiness", READINESS_VALUES)
    if any(gap.severity == DIAGNOSTIC_SEVERITY_ERROR for gap in gaps):
        return READINESS_BLOCKED
    if not entry_points and not steps:
        return READINESS_NOT_FOUND
    if gaps:
        return READINESS_PARTIAL
    return READINESS_COMPLETE
