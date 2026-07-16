"""Bounded cross-repository reference extraction contracts for Q4.

This module extracts compact reference evidence from caller-selected files
only. It does not discover files recursively, build workspace graphs, compare
shared contracts, write reports, make network calls, or add AI context.
"""

from collections.abc import Iterable, Mapping
import ast
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import tomllib
from typing import Any
from urllib.parse import SplitResult, urlsplit, urlunsplit

import strata.utils.workspace_config as workspace_config
import strata.utils.workspace_relationships as workspace_relationships


DEFAULT_MAX_FILES = 100
DEFAULT_MAX_BYTES_PER_FILE = 512 * 1024
DEFAULT_MAX_TOTAL_BYTES = 8 * 1024 * 1024
DEFAULT_MAX_REFERENCES = 500
DEFAULT_MAX_REFERENCES_PER_FILE = 50
DEFAULT_MAX_DIAGNOSTICS = 200
DEFAULT_MAX_CONFIG_DEPTH = 8
DEFAULT_MAX_CONFIG_VALUES = 1000

CONFIDENCE_LOW = "low"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_HIGH = "high"
CONFIDENCE_LEVELS = (
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    CONFIDENCE_HIGH,
)

REFERENCE_TYPE_LOCALHOST_URL = "localhost_url"
REFERENCE_TYPE_ABSOLUTE_HTTP_URL = "absolute_http_url"
REFERENCE_TYPE_IFRAME_SRC = "iframe_src"
REFERENCE_TYPE_POST_MESSAGE_SEND = "post_message_send"
REFERENCE_TYPE_MESSAGE_LISTENER = "message_listener"
REFERENCE_TYPE_API_BASE_URL = "api_base_url"
REFERENCE_TYPE_ENVIRONMENT_URL = "environment_url"
REFERENCE_TYPE_ROUTE_CONSTANT = "route_constant"
REFERENCE_TYPE_SHARED_CONSTANT = "shared_constant"
REFERENCE_TYPES = (
    REFERENCE_TYPE_LOCALHOST_URL,
    REFERENCE_TYPE_ABSOLUTE_HTTP_URL,
    REFERENCE_TYPE_IFRAME_SRC,
    REFERENCE_TYPE_POST_MESSAGE_SEND,
    REFERENCE_TYPE_MESSAGE_LISTENER,
    REFERENCE_TYPE_API_BASE_URL,
    REFERENCE_TYPE_ENVIRONMENT_URL,
    REFERENCE_TYPE_ROUTE_CONSTANT,
    REFERENCE_TYPE_SHARED_CONSTANT,
)

DIAGNOSTIC_SEVERITY_INFO = "info"
DIAGNOSTIC_SEVERITY_WARNING = "warning"
DIAGNOSTIC_SEVERITY_ERROR = "error"
DIAGNOSTIC_SEVERITIES = (
    DIAGNOSTIC_SEVERITY_INFO,
    DIAGNOSTIC_SEVERITY_WARNING,
    DIAGNOSTIC_SEVERITY_ERROR,
)

DIAGNOSTIC_SELECTED_PATH_MISSING = "selected_path_missing"
DIAGNOSTIC_SELECTED_PATH_IS_DIRECTORY = "selected_path_is_directory"
DIAGNOSTIC_SELECTED_PATH_ABSOLUTE = "selected_path_absolute"
DIAGNOSTIC_SELECTED_PATH_TRAVERSAL = "selected_path_traversal"
DIAGNOSTIC_SELECTED_PATH_OUTSIDE_REPOSITORY = "selected_path_outside_repository"
DIAGNOSTIC_SYMLINK_SKIPPED = "symlink_skipped"
DIAGNOSTIC_UNSUPPORTED_FILE_TYPE = "unsupported_file_type"
DIAGNOSTIC_FILE_TOO_LARGE = "file_too_large"
DIAGNOSTIC_FILE_READ_FAILED = "file_read_failed"
DIAGNOSTIC_DECODE_FAILED = "decode_failed"
DIAGNOSTIC_MALFORMED_JSON = "malformed_json"
DIAGNOSTIC_MALFORMED_TOML = "malformed_toml"
DIAGNOSTIC_YAML_PARTIAL_PARSE = "yaml_partial_parse"
DIAGNOSTIC_REFERENCE_CAP_REACHED = "reference_cap_reached"
DIAGNOSTIC_FILE_REFERENCE_CAP_REACHED = "file_reference_cap_reached"
DIAGNOSTIC_FILE_CAP_REACHED = "file_cap_reached"
DIAGNOSTIC_TOTAL_BYTE_CAP_REACHED = "total_byte_cap_reached"
DIAGNOSTIC_AMBIGUOUS_TARGET_REPOSITORY = "ambiguous_target_repository"
DIAGNOSTIC_UNKNOWN_TARGET_REPOSITORY = "unknown_target_repository"
DIAGNOSTIC_WILDCARD_POST_MESSAGE_ORIGIN = "wildcard_post_message_origin"
DIAGNOSTIC_MESSAGE_LISTENER_WITHOUT_ORIGIN_CHECK = "message_listener_without_origin_check"
DIAGNOSTIC_DYNAMIC_REFERENCE_UNRESOLVED = "dynamic_reference_unresolved"
DIAGNOSTIC_SECRET_LIKE_VALUE_REDACTED = "secret_like_value_redacted"
DIAGNOSTIC_CREDENTIALED_URL_SKIPPED = "credentialed_url_skipped"
DIAGNOSTIC_SENSITIVE_CONFIG_VALUE_SKIPPED = "sensitive_config_value_skipped"
DIAGNOSTIC_CODES = (
    DIAGNOSTIC_SELECTED_PATH_MISSING,
    DIAGNOSTIC_SELECTED_PATH_IS_DIRECTORY,
    DIAGNOSTIC_SELECTED_PATH_ABSOLUTE,
    DIAGNOSTIC_SELECTED_PATH_TRAVERSAL,
    DIAGNOSTIC_SELECTED_PATH_OUTSIDE_REPOSITORY,
    DIAGNOSTIC_SYMLINK_SKIPPED,
    DIAGNOSTIC_UNSUPPORTED_FILE_TYPE,
    DIAGNOSTIC_FILE_TOO_LARGE,
    DIAGNOSTIC_FILE_READ_FAILED,
    DIAGNOSTIC_DECODE_FAILED,
    DIAGNOSTIC_MALFORMED_JSON,
    DIAGNOSTIC_MALFORMED_TOML,
    DIAGNOSTIC_YAML_PARTIAL_PARSE,
    DIAGNOSTIC_REFERENCE_CAP_REACHED,
    DIAGNOSTIC_FILE_REFERENCE_CAP_REACHED,
    DIAGNOSTIC_FILE_CAP_REACHED,
    DIAGNOSTIC_TOTAL_BYTE_CAP_REACHED,
    DIAGNOSTIC_AMBIGUOUS_TARGET_REPOSITORY,
    DIAGNOSTIC_UNKNOWN_TARGET_REPOSITORY,
    DIAGNOSTIC_WILDCARD_POST_MESSAGE_ORIGIN,
    DIAGNOSTIC_MESSAGE_LISTENER_WITHOUT_ORIGIN_CHECK,
    DIAGNOSTIC_DYNAMIC_REFERENCE_UNRESOLVED,
    DIAGNOSTIC_SECRET_LIKE_VALUE_REDACTED,
    DIAGNOSTIC_CREDENTIALED_URL_SKIPPED,
    DIAGNOSTIC_SENSITIVE_CONFIG_VALUE_SKIPPED,
)

REFERENCE_FIELD_ORDER = (
    "repository_id",
    "source_path",
    "reference_type",
    "raw_value",
    "normalized_value",
    "confidence",
    "confidence_score",
    "evidence",
    "symbol",
    "line_number",
    "target_repository_id",
    "target_hint",
    "metadata",
)
DIAGNOSTIC_FIELD_ORDER = (
    "code",
    "severity",
    "message",
    "path",
    "details",
)
EXTRACTION_RESULT_FIELD_ORDER = (
    "repository_id",
    "repository_root",
    "references",
    "diagnostics",
)

SUPPORTED_EXTENSIONS = (
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".html",
    ".htm",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
    ".go",
)
SUPPORTED_FILENAMES = (
    "angular.json",
    "package.json",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
)

URL_PATTERN = re.compile(r"\b(?:https?|wss?)://[^\s\"'`<>{}|]+", re.IGNORECASE)
IFRAME_OPEN_PATTERN = re.compile(r"<iframe\b[^>]*>", re.IGNORECASE | re.DOTALL)
ATTR_LITERAL_PATTERN = re.compile(r"\bsrc\s*=\s*([\"'])(.*?)\1", re.IGNORECASE | re.DOTALL)
ATTR_BRACE_PATTERN = re.compile(r"\bsrc\s*=\s*\{([^}]+)\}", re.IGNORECASE | re.DOTALL)
POST_MESSAGE_PATTERN = re.compile(r"(?P<source>(?:[\w$.[\]]+\.)?postMessage)\s*\((?P<args>.*?)\)", re.DOTALL)
LISTENER_PATTERN = re.compile(r"(?P<handler>[\w$.]*)\.?addEventListener\s*\(\s*([\"'])message\2(?P<args>.*?)\)", re.DOTALL)
ONMESSAGE_PATTERN = re.compile(r"(?P<handler>[\w$.]*)\.?onmessage\s*=", re.DOTALL)
JS_ASSIGNMENT_PATTERN = re.compile(
    r"\b(?:export\s+)?(?:const|let|var)\s+(?P<name>[A-Za-z_$][\w$]*)\s*(?::[^=]+)?=\s*(?P<quote>[\"'`])(?P<value>.*?)(?P=quote)",
    re.DOTALL,
)
GO_ASSIGNMENT_PATTERN = re.compile(
    r"\b(?:const|var)\s+(?P<name>[A-Za-z_]\w*)\s*(?:[A-Za-z_][\w\[\]]*)?\s*=\s*\"(?P<value>(?:\\.|[^\"])*)\""
)
MESSAGE_TYPE_PATTERN = re.compile(
    r"(?:type|event|messageType|kind)\s*[:=]\s*([\"'])(?P<value>[A-Za-z0-9_.:-]+)\1",
    re.IGNORECASE,
)
ORIGIN_CHECK_PATTERN = re.compile(
    r"(?:event|e)\.origin\s*(?:===|==|!==|!=)\s*([\"'])(?P<value>[^\"']+)\1",
    re.IGNORECASE,
)
DATA_TYPE_CHECK_PATTERN = re.compile(
    r"(?:event|e)\.data\.(?:type|event|messageType|kind)\s*(?:===|==)\s*([\"'])(?P<value>[A-Za-z0-9_.:-]+)\1",
    re.IGNORECASE,
)
ENV_LINE_PATTERN = re.compile(r"^\s*(?:export\s+)?(?P<key>[A-Za-z_][A-Za-z0-9_.-]*)\s*=\s*(?P<value>.*?)\s*$")
YAML_LINE_PATTERN = re.compile(r"^\s*(?P<key>[A-Za-z_][A-Za-z0-9_.-]*)\s*:\s*(?P<value>.*?)\s*$")

URL_KEYWORDS = ("url", "uri", "origin", "host", "endpoint")
API_KEYWORDS = ("api_url", "api_base", "base_url", "backend_url", "service_url", "auth_url", "endpoint", "host_url")
CONTRACT_KEYWORDS = ("route", "path", "header", "event", "message", "api", "url", "endpoint", "origin", "port")
SECRET_KEYWORDS = ("secret", "token", "password", "passwd", "pwd", "apikey", "api_key", "private_key", "cookie", "authorization")


class WorkspaceReferenceError(ValueError):
    """Raised when a Q4 reference contract is invalid."""


@dataclass(frozen=True, slots=True)
class _KnownRepository:
    repository_id: str
    display_name: str | None
    known_ports: tuple[int, ...]
    known_urls: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WorkspaceReferenceDiagnostic:
    code: str
    severity: str
    message: str
    path: str | None = None
    details: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", _validate_choice(self.code, "code", DIAGNOSTIC_CODES))
        object.__setattr__(self, "severity", _validate_choice(self.severity, "severity", DIAGNOSTIC_SEVERITIES))
        object.__setattr__(self, "message", _validate_nonempty_string(self.message, "message"))
        object.__setattr__(self, "path", _validate_optional_string(self.path, "path"))
        object.__setattr__(self, "details", _copy_json(self.details or {}, "details"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "path": self.path,
            "details": _json_ready(self.details or {}),
        }


@dataclass(frozen=True, slots=True)
class WorkspaceReference:
    repository_id: str
    source_path: str
    reference_type: str
    raw_value: str
    normalized_value: str
    confidence: str
    confidence_score: float
    evidence: tuple[workspace_relationships.RelationshipEvidence, ...] = ()
    symbol: str | None = None
    line_number: int | None = None
    target_repository_id: str | None = None
    target_hint: str | None = None
    metadata: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "repository_id", _validate_nonempty_string(self.repository_id, "repository_id"))
        object.__setattr__(self, "source_path", _normalize_relative_path(self.source_path, "source_path", allow_parent=False))
        object.__setattr__(self, "reference_type", _validate_choice(self.reference_type, "reference_type", REFERENCE_TYPES))
        object.__setattr__(self, "raw_value", _validate_nonempty_string(self.raw_value, "raw_value"))
        object.__setattr__(self, "normalized_value", _validate_nonempty_string(self.normalized_value, "normalized_value"))
        object.__setattr__(self, "confidence", _validate_choice(self.confidence, "confidence", CONFIDENCE_LEVELS))
        object.__setattr__(self, "confidence_score", _validate_score(self.confidence_score, "confidence_score"))
        object.__setattr__(self, "evidence", tuple(sorted((_coerce_evidence(item) for item in self.evidence), key=workspace_relationships.evidence_identity_key)))
        object.__setattr__(self, "symbol", _validate_optional_string(self.symbol, "symbol"))
        if self.line_number is not None:
            if isinstance(self.line_number, bool) or not isinstance(self.line_number, int) or self.line_number < 1:
                raise WorkspaceReferenceError("line_number must be a positive integer")
        object.__setattr__(self, "target_repository_id", _validate_optional_string(self.target_repository_id, "target_repository_id"))
        object.__setattr__(self, "target_hint", _validate_optional_string(self.target_hint, "target_hint"))
        object.__setattr__(self, "metadata", _copy_json(self.metadata or {}, "metadata"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "repository_id": self.repository_id,
            "source_path": self.source_path,
            "reference_type": self.reference_type,
            "raw_value": self.raw_value,
            "normalized_value": self.normalized_value,
            "confidence": self.confidence,
            "confidence_score": self.confidence_score,
            "evidence": [item.to_dict() for item in self.evidence],
            "symbol": self.symbol,
            "line_number": self.line_number,
            "target_repository_id": self.target_repository_id,
            "target_hint": self.target_hint,
            "metadata": _json_ready(self.metadata or {}),
        }


@dataclass(frozen=True, slots=True)
class WorkspaceReferenceExtractionResult:
    repository_id: str
    repository_root: str
    references: tuple[WorkspaceReference, ...] = ()
    diagnostics: tuple[WorkspaceReferenceDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "repository_id", _validate_nonempty_string(self.repository_id, "repository_id"))
        object.__setattr__(self, "repository_root", _validate_nonempty_string(self.repository_root, "repository_root"))
        object.__setattr__(self, "references", tuple(sorted((_coerce_reference(item) for item in self.references), key=reference_sort_key)))
        object.__setattr__(self, "diagnostics", tuple(sorted((_coerce_diagnostic(item) for item in self.diagnostics), key=diagnostic_sort_key)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "repository_id": self.repository_id,
            "repository_root": self.repository_root,
            "references": [item.to_dict() for item in self.references],
            "diagnostics": [item.to_dict() for item in self.diagnostics],
        }


def _validate_nonempty_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkspaceReferenceError(f"{name} must be a non-empty string")
    if value != value.strip() or "\x00" in value:
        raise WorkspaceReferenceError(f"{name} must not contain padding or null bytes")
    return value


def _validate_optional_string(value: Any, name: str) -> str | None:
    if value is None:
        return None
    return _validate_nonempty_string(value, name)


def _validate_choice(value: Any, name: str, choices: tuple[str, ...]) -> str:
    text = _validate_nonempty_string(value, name)
    if text not in choices:
        raise WorkspaceReferenceError(f"{name} must be one of: {', '.join(choices)}")
    return text


def _validate_score(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized < 0.0 or normalized > 1.0:
        raise WorkspaceReferenceError(f"{name} must be between 0.0 and 1.0")
    return round(normalized, 3)


def _validate_limit(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 1:
        raise WorkspaceReferenceError(f"{name} must be at least 1")
    return value


def _confidence_from_score(score: float) -> str:
    if score >= 0.7:
        return CONFIDENCE_HIGH
    if score >= 0.4:
        return CONFIDENCE_MEDIUM
    return CONFIDENCE_LOW


def _normalize_relative_path(value: Any, name: str, *, allow_parent: bool) -> str:
    text = _validate_nonempty_string(value, name)
    windows_path = PureWindowsPath(text)
    posix_text = text.replace("\\", "/")
    posix_path = PurePosixPath(posix_text)
    if windows_path.drive or windows_path.is_absolute() or posix_path.is_absolute():
        raise WorkspaceReferenceError(f"{name} must be relative")
    collapsed: list[str] = []
    for part in posix_path.parts:
        if part in ("", "."):
            continue
        if part == "..":
            if not allow_parent:
                raise WorkspaceReferenceError(f"{name} must not contain parent traversal")
            if collapsed and collapsed[-1] != "..":
                collapsed.pop()
            else:
                collapsed.append(part)
            continue
        collapsed.append(part)
    return PurePosixPath(*collapsed).as_posix() if collapsed else "."


def _copy_json(value: Any, name: str) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise WorkspaceReferenceError(f"{name} must be finite")
        return value
    if isinstance(value, Mapping):
        copied = {}
        for key in sorted(value):
            if not isinstance(key, str):
                raise WorkspaceReferenceError(f"{name} keys must be strings")
            copied[key] = _copy_json(value[key], f"{name}.{key}")
        return copied
    if isinstance(value, (list, tuple)):
        return tuple(_copy_json(item, f"{name}[{index}]") for index, item in enumerate(value))
    raise WorkspaceReferenceError(f"{name} must be JSON-ready")


def _json_ready(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, Mapping):
        return {key: _json_ready(value[key]) for key in sorted(value)}
    return value


def _coerce_evidence(value: Any) -> workspace_relationships.RelationshipEvidence:
    if isinstance(value, workspace_relationships.RelationshipEvidence):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("evidence must be a RelationshipEvidence or mapping")
    return workspace_relationships.RelationshipEvidence(
        signal_type=value["signal_type"],
        source_repository_id=value["source_repository_id"],
        source_path=value.get("source_path", "."),
        summary=value["summary"],
        strength=value["strength"],
        target_repository_id=value.get("target_repository_id"),
        referenced_path=value.get("referenced_path"),
        metadata=value.get("metadata"),
    )


def _coerce_reference(value: Any) -> WorkspaceReference:
    if isinstance(value, WorkspaceReference):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("reference must be a WorkspaceReference or mapping")
    return WorkspaceReference(
        repository_id=value["repository_id"],
        source_path=value["source_path"],
        reference_type=value["reference_type"],
        raw_value=value["raw_value"],
        normalized_value=value["normalized_value"],
        confidence=value["confidence"],
        confidence_score=value["confidence_score"],
        evidence=tuple(value.get("evidence", ())),
        symbol=value.get("symbol"),
        line_number=value.get("line_number"),
        target_repository_id=value.get("target_repository_id"),
        target_hint=value.get("target_hint"),
        metadata=value.get("metadata"),
    )


def _coerce_diagnostic(value: Any) -> WorkspaceReferenceDiagnostic:
    if isinstance(value, WorkspaceReferenceDiagnostic):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("diagnostic must be a WorkspaceReferenceDiagnostic or mapping")
    return WorkspaceReferenceDiagnostic(
        code=value["code"],
        severity=value["severity"],
        message=value["message"],
        path=value.get("path"),
        details=value.get("details"),
    )


def diagnostic_sort_key(diagnostic: WorkspaceReferenceDiagnostic) -> tuple[object, ...]:
    return (
        diagnostic.code,
        diagnostic.severity,
        diagnostic.path or "",
        json.dumps(_json_ready(diagnostic.details or {}), sort_keys=True),
        diagnostic.message,
    )


def reference_sort_key(reference: WorkspaceReference) -> tuple[object, ...]:
    return (
        reference.repository_id,
        reference.source_path,
        reference.line_number or 0,
        REFERENCE_TYPES.index(reference.reference_type),
        reference.normalized_value,
        reference.symbol or "",
        reference.raw_value,
        reference.target_repository_id or "",
    )


def reference_identity_key(reference: WorkspaceReference) -> tuple[object, ...]:
    return (
        reference.repository_id,
        reference.source_path,
        reference.reference_type,
        reference.raw_value,
        reference.normalized_value,
        reference.symbol or "",
        reference.line_number or 0,
        reference.target_repository_id or "",
        reference.target_hint or "",
        json.dumps(_json_ready(reference.metadata or {}), sort_keys=True),
    )


def _diagnostic(
    code: str,
    severity: str,
    message: str,
    *,
    path: str | None = None,
    details: Mapping[str, Any] | None = None,
) -> WorkspaceReferenceDiagnostic:
    return WorkspaceReferenceDiagnostic(code, severity, message, path, details)


def _dedupe_references(references: Iterable[WorkspaceReference]) -> tuple[WorkspaceReference, ...]:
    values = tuple(_coerce_reference(item) for item in references)
    deduped = {reference_identity_key(item): item for item in values}
    return tuple(deduped[key] for key in sorted(deduped))


def _bound_diagnostics(
    diagnostics: Iterable[WorkspaceReferenceDiagnostic],
    max_diagnostics: int,
) -> tuple[WorkspaceReferenceDiagnostic, ...]:
    values = tuple(sorted((_coerce_diagnostic(item) for item in diagnostics), key=diagnostic_sort_key))
    if len(values) <= max_diagnostics:
        return values
    omitted = len(values) - max_diagnostics
    cap = _diagnostic(
        DIAGNOSTIC_REFERENCE_CAP_REACHED,
        DIAGNOSTIC_SEVERITY_WARNING,
        "Workspace reference diagnostics were truncated.",
        details={"diagnostic_limit": max_diagnostics, "omitted": omitted},
    )
    return (*values[: max_diagnostics - 1], cap)


def _line_number_for_offset(text: str, offset: int) -> int:
    return text.count("\n", 0, max(0, offset)) + 1


def _strip_quotes(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1]
    return text


def _is_secret_name(name: str | None) -> bool:
    if not name:
        return False
    normalized = name.lower().replace("-", "_")
    return any(keyword in normalized for keyword in SECRET_KEYWORDS)


def _looks_secret_like(value: str) -> bool:
    stripped = value.strip()
    if "-----BEGIN " in stripped:
        return True
    if len(stripped) >= 32 and re.fullmatch(r"[A-Za-z0-9_\-./+=]+", stripped):
        return True
    if stripped.lower().startswith(("bearer ", "basic ")):
        return True
    return False


def _symbol_kind(symbol: str | None) -> str | None:
    if not symbol:
        return None
    normalized = symbol.lower().replace("-", "_").replace(".", "_")
    if any(keyword in normalized for keyword in API_KEYWORDS):
        return REFERENCE_TYPE_API_BASE_URL
    if any(keyword in normalized for keyword in URL_KEYWORDS):
        return REFERENCE_TYPE_ENVIRONMENT_URL
    if any(keyword in normalized for keyword in ("route", "path")):
        return REFERENCE_TYPE_ROUTE_CONSTANT
    if any(keyword in normalized for keyword in CONTRACT_KEYWORDS):
        return REFERENCE_TYPE_SHARED_CONSTANT
    return None


def _is_loopback_host(hostname: str | None) -> bool:
    if hostname is None:
        return False
    host = hostname.strip("[]").lower()
    return host == "localhost" or host == "::1" or host == "0.0.0.0" or host.startswith("127.")


def _clean_url_candidate(value: str) -> str:
    return value.strip().rstrip(".,;:)}")


def normalize_reference_url(value: str) -> tuple[str | None, str | None, WorkspaceReferenceDiagnostic | None]:
    candidate = _clean_url_candidate(value)
    try:
        parsed = urlsplit(candidate)
    except ValueError:
        return None, None, None
    if parsed.scheme.lower() not in {"http", "https", "ws", "wss"} or not parsed.netloc:
        return None, None, None
    if parsed.username or parsed.password:
        return (
            None,
            None,
            _diagnostic(
                DIAGNOSTIC_CREDENTIALED_URL_SKIPPED,
                DIAGNOSTIC_SEVERITY_WARNING,
                "Credentialed URL was skipped.",
                details={"scheme": parsed.scheme.lower(), "hostname": parsed.hostname or ""},
            ),
        )
    hostname = parsed.hostname.lower() if parsed.hostname else ""
    loopback = _is_loopback_host(hostname)
    normalized_host = "localhost" if loopback else hostname
    if ":" in normalized_host and not normalized_host.startswith("["):
        normalized_host = f"[{normalized_host}]"
    netloc = normalized_host
    if parsed.port is not None:
        netloc = f"{netloc}:{parsed.port}"
    path = "" if parsed.path == "/" and not parsed.query and not parsed.fragment else parsed.path
    normalized = urlunsplit(
        SplitResult(
            parsed.scheme.lower(),
            netloc,
            path,
            parsed.query,
            parsed.fragment,
        )
    )
    reference_type = REFERENCE_TYPE_LOCALHOST_URL if loopback else REFERENCE_TYPE_ABSOLUTE_HTTP_URL
    return normalized, reference_type, None


def _extract_urls_from_text(
    text: str,
    repository_id: str,
    source_path: str,
    diagnostics: list[WorkspaceReferenceDiagnostic],
) -> list[WorkspaceReference]:
    references = []
    for match in URL_PATTERN.finditer(text):
        raw = _clean_url_candidate(match.group(0))
        normalized, reference_type, diagnostic = normalize_reference_url(raw)
        if diagnostic:
            diagnostics.append(_diagnostic(diagnostic.code, diagnostic.severity, diagnostic.message, path=source_path, details=diagnostic.details))
            continue
        if normalized is None or reference_type is None:
            continue
        line_number = _line_number_for_offset(text, match.start())
        references.append(
            _make_reference(
                repository_id,
                source_path,
                reference_type,
                raw,
                normalized,
                0.62 if reference_type == REFERENCE_TYPE_LOCALHOST_URL else 0.55,
                "URL literal was found in a selected source file.",
                line_number=line_number,
                metadata={"extractor": "url_literal"},
            )
        )
    return references


def _make_evidence(
    repository_id: str,
    source_path: str,
    reference_type: str,
    summary: str,
    confidence_score: float,
    *,
    target_repository_id: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> workspace_relationships.RelationshipEvidence:
    if confidence_score >= 0.7:
        strength = workspace_relationships.EVIDENCE_STRENGTH_STRONG
    elif confidence_score >= 0.4:
        strength = workspace_relationships.EVIDENCE_STRENGTH_MEDIUM
    else:
        strength = workspace_relationships.EVIDENCE_STRENGTH_WEAK
    return workspace_relationships.RelationshipEvidence(
        signal_type=reference_type,
        source_repository_id=repository_id,
        source_path=source_path,
        summary=summary,
        strength=strength,
        target_repository_id=target_repository_id,
        metadata=metadata or {},
    )


def _make_reference(
    repository_id: str,
    source_path: str,
    reference_type: str,
    raw_value: str,
    normalized_value: str,
    confidence_score: float,
    summary: str,
    *,
    symbol: str | None = None,
    line_number: int | None = None,
    target_repository_id: str | None = None,
    target_hint: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> WorkspaceReference:
    metadata_value = dict(metadata or {})
    if symbol:
        metadata_value.setdefault("symbol", symbol)
    if line_number is not None:
        metadata_value.setdefault("line_number", line_number)
    evidence = _make_evidence(
        repository_id,
        source_path,
        reference_type,
        summary,
        confidence_score,
        target_repository_id=target_repository_id,
        metadata=metadata_value,
    )
    return WorkspaceReference(
        repository_id=repository_id,
        source_path=source_path,
        reference_type=reference_type,
        raw_value=raw_value,
        normalized_value=normalized_value,
        confidence=_confidence_from_score(confidence_score),
        confidence_score=confidence_score,
        evidence=(evidence,),
        symbol=symbol,
        line_number=line_number,
        target_repository_id=target_repository_id,
        target_hint=target_hint,
        metadata=metadata_value,
    )


def _reference_from_named_value(
    repository_id: str,
    source_path: str,
    symbol: str,
    value: str,
    line_number: int | None,
    diagnostics: list[WorkspaceReferenceDiagnostic],
    *,
    source_kind: str,
) -> WorkspaceReference | None:
    if _is_secret_name(symbol):
        diagnostics.append(
            _diagnostic(
                DIAGNOSTIC_SENSITIVE_CONFIG_VALUE_SKIPPED,
                DIAGNOSTIC_SEVERITY_WARNING,
                "Sensitive config value was skipped.",
                path=source_path,
                details={"symbol": symbol},
            )
        )
        return None
    if _looks_secret_like(value):
        diagnostics.append(
            _diagnostic(
                DIAGNOSTIC_SECRET_LIKE_VALUE_REDACTED,
                DIAGNOSTIC_SEVERITY_WARNING,
                "Secret-like value was redacted.",
                path=source_path,
                details={"symbol": symbol},
            )
        )
        return None
    kind = _symbol_kind(symbol)
    normalized_url, url_reference_type, diagnostic = normalize_reference_url(value)
    if diagnostic:
        diagnostics.append(_diagnostic(diagnostic.code, diagnostic.severity, diagnostic.message, path=source_path, details={**(diagnostic.details or {}), "symbol": symbol}))
        return None
    if normalized_url:
        reference_type = kind if kind in {REFERENCE_TYPE_API_BASE_URL, REFERENCE_TYPE_ENVIRONMENT_URL} else url_reference_type
        score = 0.82 if reference_type == REFERENCE_TYPE_API_BASE_URL else 0.72 if kind else 0.55
        return _make_reference(
            repository_id,
            source_path,
            reference_type,
            value,
            normalized_url,
            score,
            f"{symbol} contains a URL-like endpoint value.",
            symbol=symbol,
            line_number=line_number,
            metadata={"source_kind": source_kind},
        )
    if not kind:
        return None
    if kind == REFERENCE_TYPE_ROUTE_CONSTANT and value.startswith("/"):
        return _make_reference(
            repository_id,
            source_path,
            REFERENCE_TYPE_ROUTE_CONSTANT,
            value,
            value,
            0.58,
            f"{symbol} defines a route-like literal.",
            symbol=symbol,
            line_number=line_number,
            metadata={"source_kind": source_kind},
        )
    if kind == REFERENCE_TYPE_SHARED_CONSTANT and len(value) <= 160:
        return _make_reference(
            repository_id,
            source_path,
            REFERENCE_TYPE_SHARED_CONSTANT,
            value,
            value,
            0.5,
            f"{symbol} defines a shared contract-like literal.",
            symbol=symbol,
            line_number=line_number,
            metadata={"source_kind": source_kind},
        )
    return None


def _extract_env_or_yaml_lines(
    text: str,
    repository_id: str,
    source_path: str,
    diagnostics: list[WorkspaceReferenceDiagnostic],
    *,
    yaml_mode: bool,
) -> list[WorkspaceReference]:
    references = []
    partial_yaml = False
    pattern = YAML_LINE_PATTERN if yaml_mode else ENV_LINE_PATTERN
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "//")):
            continue
        match = pattern.match(line)
        if not match:
            if yaml_mode and ":" in line:
                partial_yaml = True
            continue
        key = match.group("key")
        value = _strip_quotes(match.group("value").strip())
        if not value:
            continue
        reference = _reference_from_named_value(
            repository_id,
            source_path,
            key,
            value,
            line_number,
            diagnostics,
            source_kind="yaml" if yaml_mode else "env",
        )
        if reference:
            references.append(reference)
    if yaml_mode:
        diagnostics.append(
            _diagnostic(
                DIAGNOSTIC_YAML_PARTIAL_PARSE,
                DIAGNOSTIC_SEVERITY_INFO,
                "YAML was parsed with conservative simple key/value handling only.",
                path=source_path,
                details={"partial": partial_yaml},
            )
        )
    return references


def _walk_config_values(
    value: Any,
    *,
    path: tuple[str, ...] = (),
    depth: int = 0,
    max_depth: int = DEFAULT_MAX_CONFIG_DEPTH,
    max_values: int = DEFAULT_MAX_CONFIG_VALUES,
    counter: list[int] | None = None,
) -> Iterable[tuple[str, str]]:
    if counter is None:
        counter = [0]
    if depth > max_depth or counter[0] >= max_values:
        return
    if isinstance(value, Mapping):
        for key in sorted(value):
            counter[0] += 1
            if counter[0] > max_values:
                return
            yield from _walk_config_values(value[key], path=(*path, str(key)), depth=depth + 1, max_depth=max_depth, max_values=max_values, counter=counter)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            counter[0] += 1
            if counter[0] > max_values:
                return
            yield from _walk_config_values(item, path=(*path, str(index)), depth=depth + 1, max_depth=max_depth, max_values=max_values, counter=counter)
    elif isinstance(value, str) and path:
        yield (".".join(path), value)


def _extract_json(
    text: str,
    repository_id: str,
    source_path: str,
    diagnostics: list[WorkspaceReferenceDiagnostic],
    *,
    max_depth: int,
    max_values: int,
) -> list[WorkspaceReference]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        diagnostics.append(
            _diagnostic(
                DIAGNOSTIC_MALFORMED_JSON,
                DIAGNOSTIC_SEVERITY_WARNING,
                "JSON could not be parsed.",
                path=source_path,
                details={"line": error.lineno, "column": error.colno},
            )
        )
        return []
    references = []
    for symbol, value in _walk_config_values(payload, max_depth=max_depth, max_values=max_values):
        reference = _reference_from_named_value(repository_id, source_path, symbol, value, None, diagnostics, source_kind="json")
        if reference:
            references.append(reference)
    return references


def _extract_toml(
    text: str,
    repository_id: str,
    source_path: str,
    diagnostics: list[WorkspaceReferenceDiagnostic],
    *,
    max_depth: int,
    max_values: int,
) -> list[WorkspaceReference]:
    try:
        payload = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        diagnostics.append(
            _diagnostic(
                DIAGNOSTIC_MALFORMED_TOML,
                DIAGNOSTIC_SEVERITY_WARNING,
                "TOML could not be parsed.",
                path=source_path,
                details={"error": str(error).splitlines()[0]},
            )
        )
        return []
    references = []
    for symbol, value in _walk_config_values(payload, max_depth=max_depth, max_values=max_values):
        reference = _reference_from_named_value(repository_id, source_path, symbol, value, None, diagnostics, source_kind="toml")
        if reference:
            references.append(reference)
    return references


def _extract_python(
    text: str,
    repository_id: str,
    source_path: str,
    diagnostics: list[WorkspaceReferenceDiagnostic],
) -> list[WorkspaceReference]:
    references = []
    try:
        tree = ast.parse(text, filename=source_path)
    except SyntaxError:
        return references
    for node in tree.body:
        targets: list[ast.expr] = []
        value_node: ast.expr | None = None
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
            value_node = node.value
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
            value_node = node.value
        if value_node is None or not isinstance(value_node, ast.Constant) or not isinstance(value_node.value, str):
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                reference = _reference_from_named_value(
                    repository_id,
                    source_path,
                    target.id,
                    value_node.value,
                    getattr(node, "lineno", None),
                    diagnostics,
                    source_kind="python",
                )
                if reference:
                    references.append(reference)
    return references


def _extract_js_like_assignments(
    text: str,
    repository_id: str,
    source_path: str,
    diagnostics: list[WorkspaceReferenceDiagnostic],
) -> list[WorkspaceReference]:
    references = []
    for match in JS_ASSIGNMENT_PATTERN.finditer(text):
        symbol = match.group("name")
        value = match.group("value")
        line_number = _line_number_for_offset(text, match.start())
        reference = _reference_from_named_value(repository_id, source_path, symbol, value, line_number, diagnostics, source_kind="javascript")
        if reference:
            references.append(reference)
    return references


def _extract_go_assignments(
    text: str,
    repository_id: str,
    source_path: str,
    diagnostics: list[WorkspaceReferenceDiagnostic],
) -> list[WorkspaceReference]:
    references = []
    for match in GO_ASSIGNMENT_PATTERN.finditer(text):
        symbol = match.group("name")
        value = bytes(match.group("value"), "utf-8").decode("unicode_escape", errors="replace")
        line_number = _line_number_for_offset(text, match.start())
        reference = _reference_from_named_value(repository_id, source_path, symbol, value, line_number, diagnostics, source_kind="go")
        if reference:
            references.append(reference)
    return references


def _extract_iframes(
    text: str,
    repository_id: str,
    source_path: str,
    diagnostics: list[WorkspaceReferenceDiagnostic],
) -> list[WorkspaceReference]:
    references = []
    for match in IFRAME_OPEN_PATTERN.finditer(text):
        tag = match.group(0)
        line_number = _line_number_for_offset(text, match.start())
        literal = ATTR_LITERAL_PATTERN.search(tag)
        if literal:
            raw = literal.group(2).strip()
            normalized, _, diagnostic = normalize_reference_url(raw)
            if diagnostic:
                diagnostics.append(_diagnostic(diagnostic.code, diagnostic.severity, diagnostic.message, path=source_path, details=diagnostic.details))
                continue
            references.append(
                _make_reference(
                    repository_id,
                    source_path,
                    REFERENCE_TYPE_IFRAME_SRC,
                    raw,
                    normalized or raw,
                    0.78 if normalized else 0.48,
                    "Literal iframe source was found.",
                    line_number=line_number,
                    target_hint=None if normalized else raw,
                    metadata={"extractor": "iframe_literal", "url_normalized": bool(normalized)},
                )
            )
            continue
        brace = ATTR_BRACE_PATTERN.search(tag)
        bound = brace.group(1).strip() if brace else None
        bound_match = re.search(r"\[src\]\s*=\s*([\"'])(?P<expr>.*?)\1", tag, re.IGNORECASE | re.DOTALL)
        if bound is None and bound_match:
            bound = bound_match.group("expr").strip()
        if bound:
            simple_symbol = re.fullmatch(r"[A-Za-z_$][\w$.]*", bound)
            score = 0.45 if simple_symbol else 0.25
            if not simple_symbol:
                diagnostics.append(
                    _diagnostic(
                        DIAGNOSTIC_DYNAMIC_REFERENCE_UNRESOLVED,
                        DIAGNOSTIC_SEVERITY_INFO,
                        "Dynamic iframe source expression was not resolved.",
                        path=source_path,
                        details={"expression_kind": "iframe_src"},
                    )
                )
            references.append(
                _make_reference(
                    repository_id,
                    source_path,
                    REFERENCE_TYPE_IFRAME_SRC,
                    bound,
                    bound,
                    score,
                    "Bound iframe source expression was found.",
                    symbol=bound if simple_symbol else None,
                    line_number=line_number,
                    target_hint=bound,
                    metadata={"extractor": "iframe_bound", "dynamic": not bool(simple_symbol)},
                )
            )
    return references


def _split_call_args(args: str) -> list[str]:
    values: list[str] = []
    current: list[str] = []
    depth = 0
    quote: str | None = None
    escape = False
    for char in args:
        if quote:
            current.append(char)
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == quote:
                quote = None
            continue
        if char in {"'", '"', "`"}:
            quote = char
            current.append(char)
            continue
        if char in "([{":
            depth += 1
        elif char in ")]}" and depth:
            depth -= 1
        if char == "," and depth == 0:
            values.append("".join(current).strip())
            current = []
            continue
        current.append(char)
    if current:
        values.append("".join(current).strip())
    return values


def _literal_string(value: str) -> str | None:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"', "`"}:
        return text[1:-1]
    return None


def _event_name_from_expression(expression: str) -> str | None:
    literal = _literal_string(expression)
    if literal:
        return literal
    match = MESSAGE_TYPE_PATTERN.search(expression)
    if match:
        return match.group("value")
    return None


def _extract_post_messages(
    text: str,
    repository_id: str,
    source_path: str,
    diagnostics: list[WorkspaceReferenceDiagnostic],
) -> list[WorkspaceReference]:
    references = []
    for match in POST_MESSAGE_PATTERN.finditer(text):
        args = _split_call_args(match.group("args"))
        line_number = _line_number_for_offset(text, match.start())
        event_name = _event_name_from_expression(args[0]) if args else None
        target_origin = _literal_string(args[1]) if len(args) > 1 else None
        metadata: dict[str, Any] = {"extractor": "post_message", "source_symbol": match.group("source")}
        if event_name:
            metadata["message_event"] = event_name
        if target_origin:
            metadata["target_origin"] = target_origin
        if target_origin == "*":
            diagnostics.append(
                _diagnostic(
                    DIAGNOSTIC_WILDCARD_POST_MESSAGE_ORIGIN,
                    DIAGNOSTIC_SEVERITY_WARNING,
                    "postMessage wildcard target origin was recorded with low confidence.",
                    path=source_path,
                    details={"line_number": line_number},
                )
            )
            score = 0.28
            normalized = "*"
        elif target_origin:
            normalized_url, _, diagnostic = normalize_reference_url(target_origin)
            if diagnostic:
                diagnostics.append(_diagnostic(diagnostic.code, diagnostic.severity, diagnostic.message, path=source_path, details=diagnostic.details))
                continue
            normalized = normalized_url or target_origin
            score = 0.66 if normalized_url else 0.45
        else:
            diagnostics.append(
                _diagnostic(
                    DIAGNOSTIC_DYNAMIC_REFERENCE_UNRESOLVED,
                    DIAGNOSTIC_SEVERITY_INFO,
                    "postMessage target origin was dynamic or unavailable.",
                    path=source_path,
                    details={"line_number": line_number},
                )
            )
            normalized = event_name or "postMessage"
            score = 0.32
        references.append(
            _make_reference(
                repository_id,
                source_path,
                REFERENCE_TYPE_POST_MESSAGE_SEND,
                target_origin or event_name or "postMessage",
                normalized,
                score,
                "postMessage sender was found.",
                line_number=line_number,
                target_hint=target_origin,
                metadata=metadata,
            )
        )
    return references


def _extract_message_listeners(
    text: str,
    repository_id: str,
    source_path: str,
    diagnostics: list[WorkspaceReferenceDiagnostic],
) -> list[WorkspaceReference]:
    references = []
    listener_offsets = [match.start() for match in LISTENER_PATTERN.finditer(text)]
    listener_offsets.extend(match.start() for match in ONMESSAGE_PATTERN.finditer(text))
    for offset in sorted(set(listener_offsets)):
        line_number = _line_number_for_offset(text, offset)
        window = text[offset : offset + 1200]
        origin = None
        origin_match = ORIGIN_CHECK_PATTERN.search(window)
        if origin_match:
            origin = origin_match.group("value")
        event_name = None
        event_match = DATA_TYPE_CHECK_PATTERN.search(window)
        if event_match:
            event_name = event_match.group("value")
        metadata: dict[str, Any] = {"extractor": "message_listener"}
        if event_name:
            metadata["message_event"] = event_name
        if origin:
            metadata["allowed_origin"] = origin
            normalized_url, _, diagnostic = normalize_reference_url(origin)
            if diagnostic:
                diagnostics.append(_diagnostic(diagnostic.code, diagnostic.severity, diagnostic.message, path=source_path, details=diagnostic.details))
                continue
            normalized = normalized_url or origin
            score = 0.62 if normalized_url else 0.45
        else:
            diagnostics.append(
                _diagnostic(
                    DIAGNOSTIC_MESSAGE_LISTENER_WITHOUT_ORIGIN_CHECK,
                    DIAGNOSTIC_SEVERITY_INFO,
                    "Message listener has no simple origin check.",
                    path=source_path,
                    details={"line_number": line_number},
                )
            )
            normalized = event_name or "message"
            score = 0.3
        references.append(
            _make_reference(
                repository_id,
                source_path,
                REFERENCE_TYPE_MESSAGE_LISTENER,
                origin or event_name or "message",
                normalized,
                score,
                "Message event listener was found.",
                line_number=line_number,
                target_hint=origin,
                metadata=metadata,
            )
        )
    return references


def _file_kind(path: str) -> str | None:
    name = PurePosixPath(path).name.lower()
    suffix = PurePosixPath(path).suffix.lower()
    if name.startswith(".env"):
        return "env"
    if name in SUPPORTED_FILENAMES:
        if suffix == ".json":
            return "json"
        if suffix in {".yml", ".yaml"}:
            return "yaml"
    if suffix not in SUPPORTED_EXTENSIONS:
        return None
    if suffix == ".py":
        return "python"
    if suffix in {".js", ".jsx", ".ts", ".tsx"}:
        return "javascript"
    if suffix in {".html", ".htm"}:
        return "html"
    if suffix == ".json":
        return "json"
    if suffix == ".toml":
        return "toml"
    if suffix in {".yaml", ".yml"}:
        return "yaml"
    if suffix == ".go":
        return "go"
    return None


def _extract_from_file_text(
    text: str,
    repository_id: str,
    source_path: str,
    kind: str,
    diagnostics: list[WorkspaceReferenceDiagnostic],
    *,
    max_config_depth: int,
    max_config_values: int,
) -> list[WorkspaceReference]:
    references: list[WorkspaceReference] = []
    if kind == "env":
        references.extend(_extract_env_or_yaml_lines(text, repository_id, source_path, diagnostics, yaml_mode=False))
    elif kind == "yaml":
        references.extend(_extract_env_or_yaml_lines(text, repository_id, source_path, diagnostics, yaml_mode=True))
    elif kind == "json":
        references.extend(_extract_json(text, repository_id, source_path, diagnostics, max_depth=max_config_depth, max_values=max_config_values))
    elif kind == "toml":
        references.extend(_extract_toml(text, repository_id, source_path, diagnostics, max_depth=max_config_depth, max_values=max_config_values))
    elif kind == "python":
        references.extend(_extract_python(text, repository_id, source_path, diagnostics))
    elif kind == "javascript":
        references.extend(_extract_js_like_assignments(text, repository_id, source_path, diagnostics))
        references.extend(_extract_iframes(text, repository_id, source_path, diagnostics))
        references.extend(_extract_post_messages(text, repository_id, source_path, diagnostics))
        references.extend(_extract_message_listeners(text, repository_id, source_path, diagnostics))
    elif kind == "html":
        references.extend(_extract_iframes(text, repository_id, source_path, diagnostics))
    elif kind == "go":
        references.extend(_extract_go_assignments(text, repository_id, source_path, diagnostics))
    references.extend(_extract_urls_from_text(text, repository_id, source_path, diagnostics))
    return list(_dedupe_references(references))


def _known_repository_from_value(value: Any) -> _KnownRepository:
    if isinstance(value, workspace_config.WorkspaceRepository):
        return _KnownRepository(value.id, value.display_name, tuple(value.known_ports), tuple(value.known_urls))
    if not isinstance(value, Mapping):
        raise TypeError("known repositories must be WorkspaceRepository or mapping values")
    return _KnownRepository(
        _validate_nonempty_string(value["id"], "known_repository.id"),
        _validate_optional_string(value.get("display_name"), "known_repository.display_name"),
        tuple(int(port) for port in value.get("known_ports", ())),
        tuple(str(url) for url in value.get("known_urls", ())),
    )


def _known_repositories(values: Iterable[Any]) -> tuple[_KnownRepository, ...]:
    repositories = tuple(_known_repository_from_value(value) for value in values)
    return tuple(sorted(repositories, key=lambda item: item.repository_id))


def _url_port(value: str) -> int | None:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    return parsed.port


def _match_target_repository(
    reference: WorkspaceReference,
    known_repositories: tuple[_KnownRepository, ...],
    current_repository_id: str,
) -> tuple[str | None, str | None, WorkspaceReferenceDiagnostic | None, float | None]:
    if not known_repositories or reference.reference_type in {REFERENCE_TYPE_ROUTE_CONSTANT, REFERENCE_TYPE_SHARED_CONSTANT}:
        return None, reference.target_hint, None, None
    normalized = None
    try:
        parsed = urlsplit(reference.normalized_value)
    except ValueError:
        parsed = None
    if parsed and parsed.scheme.lower() in {"http", "https", "ws", "wss"}:
        normalized = reference.normalized_value
    if normalized is None:
        return None, reference.target_hint, None, None

    exact_matches: list[str] = []
    for repository in known_repositories:
        for url in repository.known_urls:
            normalized_url, _, _ = normalize_reference_url(url)
            if normalized_url == normalized:
                exact_matches.append(repository.repository_id)
    exact_matches = sorted(set(item for item in exact_matches if item != current_repository_id))
    if len(exact_matches) == 1:
        return exact_matches[0], exact_matches[0], None, 0.95
    if len(exact_matches) > 1:
        return (
            None,
            reference.target_hint,
            _diagnostic(
                DIAGNOSTIC_AMBIGUOUS_TARGET_REPOSITORY,
                DIAGNOSTIC_SEVERITY_WARNING,
                "Reference matched multiple configured repository URLs.",
                path=reference.source_path,
                details={"repositories": exact_matches, "normalized_url": normalized},
            ),
            None,
        )

    port = _url_port(normalized)
    if port is not None:
        port_matches = sorted(
            repository.repository_id
            for repository in known_repositories
            if repository.repository_id != current_repository_id and port in repository.known_ports
        )
        if len(port_matches) == 1:
            return port_matches[0], port_matches[0], None, 0.82
        if len(port_matches) > 1:
            return (
                None,
                reference.target_hint,
                _diagnostic(
                    DIAGNOSTIC_AMBIGUOUS_TARGET_REPOSITORY,
                    DIAGNOSTIC_SEVERITY_WARNING,
                    "Reference matched multiple configured repository ports.",
                    path=reference.source_path,
                    details={"repositories": port_matches, "port": port},
                ),
                None,
            )
    return (
        None,
        reference.target_hint,
        _diagnostic(
            DIAGNOSTIC_UNKNOWN_TARGET_REPOSITORY,
            DIAGNOSTIC_SEVERITY_INFO,
            "Reference did not match a configured target repository.",
            path=reference.source_path,
            details={"normalized_value": normalized},
        ),
        None,
    )


def _apply_target_matches(
    references: Iterable[WorkspaceReference],
    known_repositories: tuple[_KnownRepository, ...],
    current_repository_id: str,
) -> tuple[tuple[WorkspaceReference, ...], tuple[WorkspaceReferenceDiagnostic, ...]]:
    matched = []
    diagnostics = []
    for reference in references:
        target_id, target_hint, diagnostic, target_score = _match_target_repository(reference, known_repositories, current_repository_id)
        if diagnostic:
            diagnostics.append(diagnostic)
        if target_id is None:
            matched.append(reference)
            continue
        confidence_score = max(reference.confidence_score, target_score or reference.confidence_score)
        metadata = {**(reference.metadata or {}), "target_match": "configured_url_or_port"}
        matched.append(
            WorkspaceReference(
                repository_id=reference.repository_id,
                source_path=reference.source_path,
                reference_type=reference.reference_type,
                raw_value=reference.raw_value,
                normalized_value=reference.normalized_value,
                confidence=_confidence_from_score(confidence_score),
                confidence_score=confidence_score,
                evidence=(
                    _make_evidence(
                        reference.repository_id,
                        reference.source_path,
                        reference.reference_type,
                        reference.evidence[0].summary if reference.evidence else "Reference matched configured repository target.",
                        confidence_score,
                        target_repository_id=target_id,
                        metadata=metadata,
                    ),
                ),
                symbol=reference.symbol,
                line_number=reference.line_number,
                target_repository_id=target_id,
                target_hint=target_hint,
                metadata=metadata,
            )
        )
    return tuple(sorted(matched, key=reference_sort_key)), tuple(diagnostics)


def _safe_resolve(path: Path) -> Path:
    return path.resolve(strict=False)


def _selected_path_is_absolute(value: str) -> bool:
    windows_path = PureWindowsPath(value)
    posix_path = PurePosixPath(value.replace("\\", "/"))
    return bool(windows_path.drive or windows_path.is_absolute() or posix_path.is_absolute())


def _normalize_selected_path(value: Any) -> tuple[str | None, WorkspaceReferenceDiagnostic | None]:
    text = str(value)
    if _selected_path_is_absolute(text):
        return (
            None,
            _diagnostic(
                DIAGNOSTIC_SELECTED_PATH_ABSOLUTE,
                DIAGNOSTIC_SEVERITY_ERROR,
                "Selected path must be relative.",
                path=text,
            ),
        )
    try:
        normalized = _normalize_relative_path(text, "selected_path", allow_parent=False)
    except WorkspaceReferenceError:
        return (
            None,
            _diagnostic(
                DIAGNOSTIC_SELECTED_PATH_TRAVERSAL,
                DIAGNOSTIC_SEVERITY_ERROR,
                "Selected path must not contain parent traversal.",
                path=text,
            ),
        )
    return normalized, None


def extract_workspace_references(
    repository_id: str,
    repository_root: str | os.PathLike[str],
    selected_paths: Iterable[str | os.PathLike[str]],
    *,
    known_repositories: Iterable[Any] = (),
    known_urls: Iterable[str] = (),
    known_ports: Iterable[int] = (),
    max_files: int = DEFAULT_MAX_FILES,
    max_bytes_per_file: int = DEFAULT_MAX_BYTES_PER_FILE,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
    max_references: int = DEFAULT_MAX_REFERENCES,
    max_references_per_file: int = DEFAULT_MAX_REFERENCES_PER_FILE,
    max_diagnostics: int = DEFAULT_MAX_DIAGNOSTICS,
    max_config_depth: int = DEFAULT_MAX_CONFIG_DEPTH,
    max_config_values: int = DEFAULT_MAX_CONFIG_VALUES,
) -> WorkspaceReferenceExtractionResult:
    """Extract Q4 references from explicit selected paths only."""

    repository_id = _validate_nonempty_string(repository_id, "repository_id")
    max_files = _validate_limit(max_files, "max_files")
    max_bytes_per_file = _validate_limit(max_bytes_per_file, "max_bytes_per_file")
    max_total_bytes = _validate_limit(max_total_bytes, "max_total_bytes")
    max_references = _validate_limit(max_references, "max_references")
    max_references_per_file = _validate_limit(max_references_per_file, "max_references_per_file")
    max_diagnostics = _validate_limit(max_diagnostics, "max_diagnostics")
    max_config_depth = _validate_limit(max_config_depth, "max_config_depth")
    max_config_values = _validate_limit(max_config_values, "max_config_values")

    root_path = Path(repository_root)
    resolved_root = _safe_resolve(root_path)
    diagnostics: list[WorkspaceReferenceDiagnostic] = []
    references: list[WorkspaceReference] = []
    total_bytes = 0
    selected = tuple(sorted(str(path) for path in selected_paths))
    if len(selected) > max_files:
        omitted = len(selected) - max_files
        diagnostics.append(
            _diagnostic(
                DIAGNOSTIC_FILE_CAP_REACHED,
                DIAGNOSTIC_SEVERITY_WARNING,
                "Selected file cap was reached.",
                details={"limit": max_files, "omitted": omitted},
            )
        )
        selected = selected[:max_files]

    known = _known_repositories(known_repositories)
    if known_urls or known_ports:
        known = tuple(
            sorted(
                (
                    *known,
                    _KnownRepository(
                        repository_id,
                        None,
                        tuple(sorted(int(port) for port in known_ports)),
                        tuple(sorted(str(url) for url in known_urls)),
                    ),
                ),
                key=lambda item: item.repository_id,
            )
        )

    for raw_path in selected:
        normalized_path, diagnostic = _normalize_selected_path(raw_path)
        if diagnostic:
            diagnostics.append(diagnostic)
            continue
        assert normalized_path is not None
        candidate = root_path / Path(normalized_path)
        resolved_candidate = _safe_resolve(candidate)
        if candidate.is_symlink():
            try:
                resolved_candidate.relative_to(resolved_root)
            except ValueError:
                diagnostics.append(
                    _diagnostic(
                        DIAGNOSTIC_SYMLINK_SKIPPED,
                        DIAGNOSTIC_SEVERITY_WARNING,
                        "Symlink selected path was skipped.",
                        path=normalized_path,
                    )
                )
                continue
        try:
            resolved_candidate.relative_to(resolved_root)
        except ValueError:
            diagnostics.append(
                _diagnostic(
                    DIAGNOSTIC_SELECTED_PATH_OUTSIDE_REPOSITORY,
                    DIAGNOSTIC_SEVERITY_ERROR,
                    "Selected path resolves outside the repository root.",
                    path=normalized_path,
                )
            )
            continue
        if not candidate.exists():
            diagnostics.append(
                _diagnostic(
                    DIAGNOSTIC_SELECTED_PATH_MISSING,
                    DIAGNOSTIC_SEVERITY_WARNING,
                    "Selected path does not exist.",
                    path=normalized_path,
                )
            )
            continue
        if candidate.is_dir():
            diagnostics.append(
                _diagnostic(
                    DIAGNOSTIC_SELECTED_PATH_IS_DIRECTORY,
                    DIAGNOSTIC_SEVERITY_INFO,
                    "Selected path is a directory and was skipped.",
                    path=normalized_path,
                )
            )
            continue
        kind = _file_kind(normalized_path)
        if kind is None:
            diagnostics.append(
                _diagnostic(
                    DIAGNOSTIC_UNSUPPORTED_FILE_TYPE,
                    DIAGNOSTIC_SEVERITY_INFO,
                    "Selected file type is unsupported for Q4 extraction.",
                    path=normalized_path,
                )
            )
            continue
        try:
            size = candidate.stat().st_size
        except OSError:
            diagnostics.append(
                _diagnostic(
                    DIAGNOSTIC_FILE_READ_FAILED,
                    DIAGNOSTIC_SEVERITY_WARNING,
                    "Selected file metadata could not be read.",
                    path=normalized_path,
                )
            )
            continue
        if size > max_bytes_per_file:
            diagnostics.append(
                _diagnostic(
                    DIAGNOSTIC_FILE_TOO_LARGE,
                    DIAGNOSTIC_SEVERITY_WARNING,
                    "Selected file exceeded the per-file byte cap.",
                    path=normalized_path,
                    details={"size": size, "limit": max_bytes_per_file},
                )
            )
            continue
        if total_bytes + size > max_total_bytes:
            diagnostics.append(
                _diagnostic(
                    DIAGNOSTIC_TOTAL_BYTE_CAP_REACHED,
                    DIAGNOSTIC_SEVERITY_WARNING,
                    "Total selected-file byte cap was reached.",
                    path=normalized_path,
                    details={"size": size, "limit": max_total_bytes},
                )
            )
            continue
        try:
            data = candidate.read_bytes()
        except OSError:
            diagnostics.append(
                _diagnostic(
                    DIAGNOSTIC_FILE_READ_FAILED,
                    DIAGNOSTIC_SEVERITY_WARNING,
                    "Selected file could not be read.",
                    path=normalized_path,
                )
            )
            continue
        total_bytes += size
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            diagnostics.append(
                _diagnostic(
                    DIAGNOSTIC_DECODE_FAILED,
                    DIAGNOSTIC_SEVERITY_WARNING,
                    "Selected file could not be decoded as UTF-8.",
                    path=normalized_path,
                )
            )
            continue
        file_references = _extract_from_file_text(
            text,
            repository_id,
            normalized_path,
            kind,
            diagnostics,
            max_config_depth=max_config_depth,
            max_config_values=max_config_values,
        )
        if len(file_references) > max_references_per_file:
            omitted = len(file_references) - max_references_per_file
            diagnostics.append(
                _diagnostic(
                    DIAGNOSTIC_FILE_REFERENCE_CAP_REACHED,
                    DIAGNOSTIC_SEVERITY_WARNING,
                    "Per-file reference cap was reached.",
                    path=normalized_path,
                    details={"limit": max_references_per_file, "omitted": omitted},
                )
            )
            file_references = sorted(file_references, key=reference_sort_key)[:max_references_per_file]
        references.extend(file_references)

    references = list(_dedupe_references(references))
    references, match_diagnostics = _apply_target_matches(references, known, repository_id)
    diagnostics.extend(match_diagnostics)
    if len(references) > max_references:
        omitted = len(references) - max_references
        diagnostics.append(
            _diagnostic(
                DIAGNOSTIC_REFERENCE_CAP_REACHED,
                DIAGNOSTIC_SEVERITY_WARNING,
                "Total reference cap was reached.",
                details={"limit": max_references, "omitted": omitted},
            )
        )
        references = tuple(sorted(references, key=reference_sort_key)[:max_references])

    return WorkspaceReferenceExtractionResult(
        repository_id=repository_id,
        repository_root=os.fspath(root_path),
        references=tuple(references),
        diagnostics=_bound_diagnostics(diagnostics, max_diagnostics),
    )


def workspace_reference_extraction_result_to_dict(
    result: WorkspaceReferenceExtractionResult,
) -> dict[str, Any]:
    """Return the stable JSON-ready workspace reference extraction result."""

    if not isinstance(result, WorkspaceReferenceExtractionResult):
        raise TypeError("result must be a WorkspaceReferenceExtractionResult")
    return result.to_dict()


def references_to_relationship_hints(
    references: Iterable[WorkspaceReference | Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """Convert targeted Q4 references into Q3-compatible inferred hints."""

    hints = []
    for value in references:
        reference = _coerce_reference(value)
        if not reference.target_repository_id or reference.target_repository_id == reference.repository_id:
            continue
        relationship_type = None
        if reference.reference_type in {REFERENCE_TYPE_API_BASE_URL, REFERENCE_TYPE_ENVIRONMENT_URL}:
            relationship_type = workspace_config.RELATIONSHIP_TYPE_CALLS_API
        elif reference.reference_type == REFERENCE_TYPE_IFRAME_SRC:
            relationship_type = workspace_config.RELATIONSHIP_TYPE_EMBEDS_IFRAME
        elif reference.reference_type == REFERENCE_TYPE_POST_MESSAGE_SEND:
            relationship_type = workspace_config.RELATIONSHIP_TYPE_SENDS_MESSAGES_TO
        elif reference.reference_type == REFERENCE_TYPE_MESSAGE_LISTENER:
            relationship_type = workspace_config.RELATIONSHIP_TYPE_RECEIVES_MESSAGES_FROM
        if relationship_type is None:
            continue
        evidence = _make_evidence(
            reference.repository_id,
            reference.source_path,
            reference.reference_type,
            f"{reference.reference_type} reference targets {reference.target_repository_id}.",
            reference.confidence_score,
            target_repository_id=reference.target_repository_id,
            metadata={
                "reference_type": reference.reference_type,
                "symbol": reference.symbol,
                "line_number": reference.line_number,
                "normalized_value": reference.normalized_value,
            },
        )
        hints.append(
            {
                "source_repository_id": reference.repository_id,
                "target_repository_id": reference.target_repository_id,
                "relationship_type": relationship_type,
                "origin": workspace_relationships.RELATIONSHIP_ORIGIN_INFERRED,
                "confidence": reference.confidence,
                "confidence_score": reference.confidence_score,
                "evidence": (evidence,),
                "description": "Relationship hint inferred from selected-file Q4 reference extraction.",
            }
        )
    return tuple(sorted(hints, key=lambda item: (item["source_repository_id"], item["target_repository_id"], item["relationship_type"], item["confidence_score"])))
