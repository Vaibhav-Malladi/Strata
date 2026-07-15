"""Stable backend route/service relationship contracts.

This module defines JSON-ready shapes and deterministic ordering helpers only.
Framework-specific extraction is intentionally deferred to later Part K work.
"""

from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Callable, Iterable

from strata.core.stage_report import CONFIDENCE_LEVELS


BACKEND_RELATIONSHIP_BACKEND_ROUTE = "backend_route"
BACKEND_RELATIONSHIP_ROUTE_HANDLER = "route_handler"
BACKEND_RELATIONSHIP_HANDLER_SERVICE = "handler_service"
BACKEND_RELATIONSHIP_SERVICE_REPOSITORY = "service_repository"
BACKEND_RELATIONSHIP_SERVICE_MODEL = "service_model"
BACKEND_RELATIONSHIP_ROUTE_SCHEMA = "route_schema"
BACKEND_RELATIONSHIP_ROUTE_MIDDLEWARE = "route_middleware"
BACKEND_RELATIONSHIP_ROUTE_AUTH_GUARD = "route_auth_guard"
BACKEND_RELATIONSHIP_ROUTE_EXTERNAL_API = "route_external_api"
BACKEND_RELATIONSHIP_ROUTE_DATABASE_ACCESS = "route_database_access"
BACKEND_RELATIONSHIP_INTERNAL_LIBRARY_USAGE = "backend_internal_library_usage"
BACKEND_RELATIONSHIP_BACKEND_INTERNAL_LIBRARY_USAGE = (
    BACKEND_RELATIONSHIP_INTERNAL_LIBRARY_USAGE
)
BACKEND_RELATIONSHIP_TYPES = (
    BACKEND_RELATIONSHIP_BACKEND_ROUTE,
    BACKEND_RELATIONSHIP_ROUTE_HANDLER,
    BACKEND_RELATIONSHIP_HANDLER_SERVICE,
    BACKEND_RELATIONSHIP_SERVICE_REPOSITORY,
    BACKEND_RELATIONSHIP_SERVICE_MODEL,
    BACKEND_RELATIONSHIP_ROUTE_SCHEMA,
    BACKEND_RELATIONSHIP_ROUTE_MIDDLEWARE,
    BACKEND_RELATIONSHIP_ROUTE_AUTH_GUARD,
    BACKEND_RELATIONSHIP_ROUTE_EXTERNAL_API,
    BACKEND_RELATIONSHIP_ROUTE_DATABASE_ACCESS,
    BACKEND_RELATIONSHIP_INTERNAL_LIBRARY_USAGE,
)

BACKEND_FRAMEWORK_FASTAPI = "fastapi"
BACKEND_FRAMEWORK_FLASK = "flask"
BACKEND_FRAMEWORK_DJANGO = "django"
BACKEND_FRAMEWORK_DJANGO_REST_FRAMEWORK = "django_rest_framework"
BACKEND_FRAMEWORK_EXPRESS = "express"
BACKEND_FRAMEWORK_NESTJS = "nestjs"
BACKEND_FRAMEWORK_GO = "go"
BACKEND_FRAMEWORK_GENERIC_BACKEND = "generic_backend"
BACKEND_FRAMEWORK_UNKNOWN = "unknown"
BACKEND_FRAMEWORKS = (
    BACKEND_FRAMEWORK_FASTAPI,
    BACKEND_FRAMEWORK_FLASK,
    BACKEND_FRAMEWORK_DJANGO,
    BACKEND_FRAMEWORK_DJANGO_REST_FRAMEWORK,
    BACKEND_FRAMEWORK_EXPRESS,
    BACKEND_FRAMEWORK_NESTJS,
    BACKEND_FRAMEWORK_GO,
    BACKEND_FRAMEWORK_GENERIC_BACKEND,
    BACKEND_FRAMEWORK_UNKNOWN,
)

HTTP_METHOD_GET = "GET"
HTTP_METHOD_POST = "POST"
HTTP_METHOD_PUT = "PUT"
HTTP_METHOD_PATCH = "PATCH"
HTTP_METHOD_DELETE = "DELETE"
HTTP_METHOD_OPTIONS = "OPTIONS"
HTTP_METHOD_HEAD = "HEAD"
HTTP_METHOD_ANY = "ANY"
HTTP_METHOD_UNKNOWN = "unknown"
HTTP_METHODS = (
    HTTP_METHOD_GET,
    HTTP_METHOD_POST,
    HTTP_METHOD_PUT,
    HTTP_METHOD_PATCH,
    HTTP_METHOD_DELETE,
    HTTP_METHOD_OPTIONS,
    HTTP_METHOD_HEAD,
    HTTP_METHOD_ANY,
    HTTP_METHOD_UNKNOWN,
)

BACKEND_CONFIDENCE_UNKNOWN = "unknown"
BACKEND_CONFIDENCE_LOW = "low"
BACKEND_CONFIDENCE_MEDIUM = "medium"
BACKEND_CONFIDENCE_HIGH = "high"
BACKEND_CONFIDENCE_VALUES = CONFIDENCE_LEVELS
BACKEND_RELATIONSHIP_FIELD_ORDER = (
    "framework",
    "relationship_type",
    "source_path",
    "target_path",
    "target_symbol",
    "route_path",
    "http_method",
    "handler_symbol",
    "service_symbol",
    "model_symbol",
    "confidence",
    "evidence",
    "warnings",
    "reason",
)

BACKEND_FRAMEWORK_PLACEHOLDER_FASTAPI = "reserved_for_k3_fastapi"
BACKEND_FRAMEWORK_PLACEHOLDER_FLASK = "reserved_for_k4_flask"
BACKEND_FRAMEWORK_PLACEHOLDER_DJANGO = "reserved_for_k5_django"
BACKEND_FRAMEWORK_PLACEHOLDER_DJANGO_REST_FRAMEWORK = "reserved_for_k5_drf"
BACKEND_FRAMEWORK_PLACEHOLDER_EXPRESS = "reserved_for_k6_express"
BACKEND_FRAMEWORK_PLACEHOLDER_NESTJS = "reserved_for_k7_nestjs"
BACKEND_FRAMEWORK_PLACEHOLDER_GO = "reserved_for_k8_k9_go"
BACKEND_FRAMEWORK_PLACEHOLDERS = (
    (BACKEND_FRAMEWORK_FASTAPI, BACKEND_FRAMEWORK_PLACEHOLDER_FASTAPI),
    (BACKEND_FRAMEWORK_FLASK, BACKEND_FRAMEWORK_PLACEHOLDER_FLASK),
    (BACKEND_FRAMEWORK_DJANGO, BACKEND_FRAMEWORK_PLACEHOLDER_DJANGO),
    (
        BACKEND_FRAMEWORK_DJANGO_REST_FRAMEWORK,
        BACKEND_FRAMEWORK_PLACEHOLDER_DJANGO_REST_FRAMEWORK,
    ),
    (BACKEND_FRAMEWORK_EXPRESS, BACKEND_FRAMEWORK_PLACEHOLDER_EXPRESS),
    (BACKEND_FRAMEWORK_NESTJS, BACKEND_FRAMEWORK_PLACEHOLDER_NESTJS),
    (BACKEND_FRAMEWORK_GO, BACKEND_FRAMEWORK_PLACEHOLDER_GO),
)


@dataclass(frozen=True, slots=True)
class BackendRelationship:
    """One immutable backend relationship observation."""

    framework: str
    relationship_type: str
    source_path: str
    target_path: str | None = None
    target_symbol: str | None = None
    route_path: str | None = None
    http_method: str = HTTP_METHOD_UNKNOWN
    handler_symbol: str | None = None
    service_symbol: str | None = None
    model_symbol: str | None = None
    confidence: str = "unknown"
    evidence: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    reason: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "framework",
            _validate_choice(self.framework, "framework", BACKEND_FRAMEWORKS),
        )
        object.__setattr__(
            self,
            "relationship_type",
            _validate_choice(
                self.relationship_type,
                "relationship_type",
                BACKEND_RELATIONSHIP_TYPES,
            ),
        )
        object.__setattr__(
            self,
            "source_path",
            _normalize_required_path(self.source_path, "source_path"),
        )
        object.__setattr__(
            self,
            "target_path",
            _normalize_optional_path(self.target_path, "target_path"),
        )
        object.__setattr__(
            self,
            "target_symbol",
            _normalize_optional_string(self.target_symbol, "target_symbol"),
        )
        object.__setattr__(
            self,
            "route_path",
            _normalize_optional_string(self.route_path, "route_path"),
        )
        object.__setattr__(
            self,
            "http_method",
            _validate_choice(self.http_method, "http_method", HTTP_METHODS),
        )
        object.__setattr__(
            self,
            "handler_symbol",
            _normalize_optional_string(self.handler_symbol, "handler_symbol"),
        )
        object.__setattr__(
            self,
            "service_symbol",
            _normalize_optional_string(self.service_symbol, "service_symbol"),
        )
        object.__setattr__(
            self,
            "model_symbol",
            _normalize_optional_string(self.model_symbol, "model_symbol"),
        )
        object.__setattr__(
            self,
            "confidence",
            _validate_choice(
                self.confidence,
                "confidence",
                BACKEND_CONFIDENCE_VALUES,
            ),
        )
        object.__setattr__(
            self,
            "evidence",
            _validate_messages(self.evidence, "evidence"),
        )
        object.__setattr__(
            self,
            "warnings",
            _validate_messages(self.warnings, "warnings"),
        )
        object.__setattr__(
            self,
            "reason",
            _normalize_optional_string(self.reason, "reason") or "",
        )

    def to_dict(self) -> dict[str, Any]:
        """Return the stable JSON-ready relationship representation."""

        return {
            "framework": self.framework,
            "relationship_type": self.relationship_type,
            "source_path": self.source_path,
            "target_path": self.target_path,
            "target_symbol": self.target_symbol,
            "route_path": self.route_path,
            "http_method": self.http_method,
            "handler_symbol": self.handler_symbol,
            "service_symbol": self.service_symbol,
            "model_symbol": self.model_symbol,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
            "warnings": list(self.warnings),
            "reason": self.reason,
        }


def create_backend_relationship(**values: Any) -> BackendRelationship:
    """Create and validate one backend relationship contract value."""

    return BackendRelationship(**values)


def backend_relationship_to_dict(relationship: BackendRelationship) -> dict[str, Any]:
    """Convert one backend relationship to its stable JSON-ready shape."""

    if not isinstance(relationship, BackendRelationship):
        raise TypeError("relationship must be a BackendRelationship")
    return relationship.to_dict()


def sort_backend_relationships(
    relationships: Iterable[BackendRelationship],
) -> tuple[BackendRelationship, ...]:
    """Return backend relationships in deterministic contract order."""

    validated = _validate_relationships(relationships)
    return tuple(sorted(validated, key=_relationship_sort_key))


def merge_backend_relationships(
    relationships: Iterable[BackendRelationship],
) -> tuple[BackendRelationship, ...]:
    """Remove exactly identical relationships and return deterministic ordering."""

    return sort_backend_relationships(set(_validate_relationships(relationships)))


def group_backend_relationships_by_source_path(
    relationships: Iterable[BackendRelationship],
) -> dict[str, tuple[BackendRelationship, ...]]:
    """Group relationships by source path with deterministic keys and values."""

    return _group_relationships(relationships, lambda relationship: relationship.source_path)


def group_backend_relationships_by_route_path(
    relationships: Iterable[BackendRelationship],
) -> dict[str, tuple[BackendRelationship, ...]]:
    """Group relationships by route path, using ``unknown`` when absent."""

    return _group_relationships(
        relationships,
        lambda relationship: relationship.route_path or "unknown",
    )


def group_backend_relationships_by_relationship_type(
    relationships: Iterable[BackendRelationship],
) -> dict[str, tuple[BackendRelationship, ...]]:
    """Group relationships by backend relationship type."""

    return _group_relationships(
        relationships,
        lambda relationship: relationship.relationship_type,
    )


def group_backend_relationships_by_framework(
    relationships: Iterable[BackendRelationship],
) -> dict[str, tuple[BackendRelationship, ...]]:
    """Group relationships by backend framework."""

    return _group_relationships(
        relationships,
        lambda relationship: relationship.framework,
    )


def _group_relationships(
    relationships: Iterable[BackendRelationship],
    key_for: Callable[[BackendRelationship], str],
) -> dict[str, tuple[BackendRelationship, ...]]:
    groups: dict[str, list[BackendRelationship]] = {}
    for relationship in sort_backend_relationships(relationships):
        key = key_for(relationship)
        groups.setdefault(key, []).append(relationship)
    return {
        key: tuple(groups[key])
        for key in sorted(groups)
    }


def _validate_relationships(
    relationships: Iterable[BackendRelationship],
) -> tuple[BackendRelationship, ...]:
    if isinstance(relationships, (str, bytes)):
        raise TypeError("relationships must be an iterable of BackendRelationship values")
    try:
        result = tuple(relationships)
    except TypeError as error:
        raise TypeError(
            "relationships must be an iterable of BackendRelationship values"
        ) from error
    if not all(isinstance(item, BackendRelationship) for item in result):
        raise TypeError(
            "relationships must contain only BackendRelationship values"
        )
    return result


def _relationship_sort_key(relationship: BackendRelationship) -> tuple:
    return (
        relationship.source_path,
        relationship.route_path or "",
        _http_method_index(relationship.http_method),
        _relationship_type_index(relationship.relationship_type),
        relationship.target_path or "",
        relationship.target_symbol or "",
        relationship.handler_symbol or "",
        relationship.service_symbol or "",
        relationship.model_symbol or "",
        _framework_index(relationship.framework),
        _confidence_index(relationship.confidence),
        relationship.reason,
        relationship.evidence,
        relationship.warnings,
    )


def _relationship_type_index(value: str) -> int:
    return BACKEND_RELATIONSHIP_TYPES.index(value)


def _framework_index(value: str) -> int:
    return BACKEND_FRAMEWORKS.index(value)


def _http_method_index(value: str) -> int:
    return HTTP_METHODS.index(value)


def _confidence_index(value: str) -> int:
    return BACKEND_CONFIDENCE_VALUES.index(value)


def _validate_choice(value: Any, name: str, allowed: tuple[str, ...]) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if value not in allowed:
        raise ValueError(f"{name} must be one of: {', '.join(allowed)}")
    return next(item for item in allowed if item == value)


def _normalize_required_path(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    text = value.strip()
    if not text:
        raise ValueError(f"{name} must be a non-empty relative path")
    if text != value or "\x00" in text:
        raise ValueError(f"{name} must not contain whitespace padding or null bytes")

    windows_path = PureWindowsPath(text)
    posix_text = text.replace("\\", "/")
    posix_path = PurePosixPath(posix_text)
    if posix_path.is_absolute() or windows_path.is_absolute() or windows_path.drive:
        raise ValueError(f"{name} must be relative")
    if ".." in posix_path.parts:
        raise ValueError(f"{name} must not escape its root with '..'")

    normalized = posix_path.as_posix()
    if normalized in ("", "."):
        raise ValueError(f"{name} must identify a repository file")
    return normalized


def _normalize_optional_path(value: Any, name: str) -> str | None:
    if value is None:
        return None
    return _normalize_required_path(value, name)


def _normalize_optional_string(value: Any, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string or None")
    text = value.strip()
    if text != value:
        raise ValueError(f"{name} must not have surrounding whitespace")
    return text or None


def _validate_messages(value: Any, name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        raise TypeError(f"{name} must be an iterable of strings")
    try:
        messages = tuple(value)
    except TypeError as error:
        raise TypeError(f"{name} must be an iterable of strings") from error
    for index, message in enumerate(messages):
        _normalize_message(message, f"{name}[{index}]")
    return messages


def _normalize_message(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    if value != value.strip():
        raise ValueError(f"{name} must not have surrounding whitespace")
    return value
