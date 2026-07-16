"""Shared-contract comparison contracts for Q5.

This module compares configured Q1 shared contracts with already-produced Q4
reference records. It does not read files, run extraction, discover
repositories, build graphs, write reports, or add AI context.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import json
import math
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any
from urllib.parse import urlsplit

import strata.utils.workspace_config as workspace_config
import strata.utils.workspace_references as workspace_references
import strata.utils.workspace_relationships as workspace_relationships


DEFAULT_MAX_CONTRACTS = 100
DEFAULT_MAX_LOCATIONS_PER_CONTRACT = 50
DEFAULT_MAX_OBSERVATIONS_PER_LOCATION = 25
DEFAULT_MAX_EVIDENCE_PER_LOCATION = 8
DEFAULT_MAX_EVIDENCE_PER_CONTRACT = 12
DEFAULT_MAX_FINDINGS = 100
DEFAULT_MAX_DIAGNOSTICS = 200

CONFIDENCE_LOW = "low"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_HIGH = "high"
CONFIDENCE_LEVELS = (
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    CONFIDENCE_HIGH,
)

STATUS_CONSISTENT = "consistent"
STATUS_INCONSISTENT = "inconsistent"
STATUS_MISSING = "missing"
STATUS_AMBIGUOUS = "ambiguous"
STATUS_UNREADABLE = "unreadable"
STATUS_SKIPPED = "skipped"
STATUS_UNSUPPORTED = "unsupported"
STATUSES = (
    STATUS_CONSISTENT,
    STATUS_INCONSISTENT,
    STATUS_MISSING,
    STATUS_AMBIGUOUS,
    STATUS_UNREADABLE,
    STATUS_SKIPPED,
    STATUS_UNSUPPORTED,
)
STATUS_PRECEDENCE = (
    STATUS_INCONSISTENT,
    STATUS_AMBIGUOUS,
    STATUS_UNREADABLE,
    STATUS_UNSUPPORTED,
    STATUS_SKIPPED,
    STATUS_MISSING,
    STATUS_CONSISTENT,
)

LOCATION_STATE_UNREADABLE = "unreadable"
LOCATION_STATE_SKIPPED = "skipped"
LOCATION_STATE_UNSUPPORTED = "unsupported"
LOCATION_STATES = (
    LOCATION_STATE_UNREADABLE,
    LOCATION_STATE_SKIPPED,
    LOCATION_STATE_UNSUPPORTED,
)

DIAGNOSTIC_SEVERITY_INFO = "info"
DIAGNOSTIC_SEVERITY_WARNING = "warning"
DIAGNOSTIC_SEVERITY_ERROR = "error"
DIAGNOSTIC_SEVERITIES = (
    DIAGNOSTIC_SEVERITY_INFO,
    DIAGNOSTIC_SEVERITY_WARNING,
    DIAGNOSTIC_SEVERITY_ERROR,
)

DIAGNOSTIC_CONTRACT_LOCATION_MISSING = "contract_location_missing"
DIAGNOSTIC_CONTRACT_LOCATION_AMBIGUOUS = "contract_location_ambiguous"
DIAGNOSTIC_CONTRACT_LOCATION_UNREADABLE = "contract_location_unreadable"
DIAGNOSTIC_CONTRACT_LOCATION_SKIPPED = "contract_location_skipped"
DIAGNOSTIC_CONTRACT_LOCATION_UNSUPPORTED = "contract_location_unsupported"
DIAGNOSTIC_CONTRACT_VALUE_MISMATCH = "contract_value_mismatch"
DIAGNOSTIC_CONTRACT_CROSS_LOCATION_MISMATCH = "contract_cross_location_mismatch"
DIAGNOSTIC_CONTRACT_REFERENCE_TYPE_INCOMPATIBLE = "contract_reference_type_incompatible"
DIAGNOSTIC_CONTRACT_SYMBOL_NOT_FOUND = "contract_symbol_not_found"
DIAGNOSTIC_CONTRACT_PATH_NOT_FOUND = "contract_path_not_found"
DIAGNOSTIC_CONTRACT_EXPECTED_VALUE_UNSUPPORTED = "contract_expected_value_unsupported"
DIAGNOSTIC_CONTRACT_ALLOWED_VALUE_UNSUPPORTED = "contract_allowed_value_unsupported"
DIAGNOSTIC_CONTRACT_NORMALIZATION_FAILED = "contract_normalization_failed"
DIAGNOSTIC_CONTRACT_PORT_INVALID = "contract_port_invalid"
DIAGNOSTIC_CONTRACT_URL_INVALID = "contract_url_invalid"
DIAGNOSTIC_CONTRACT_EVIDENCE_TRUNCATED = "contract_evidence_truncated"
DIAGNOSTIC_CONTRACT_FINDING_CAP_REACHED = "contract_finding_cap_reached"
DIAGNOSTIC_CONTRACT_DIAGNOSTIC_CAP_REACHED = "contract_diagnostic_cap_reached"
DIAGNOSTIC_DUPLICATE_CONTRACT_NAME = "duplicate_contract_name"
DIAGNOSTIC_DUPLICATE_CONTRACT_LOCATION = "duplicate_contract_location"
DIAGNOSTIC_SENSITIVE_CONTRACT_VALUE_REDACTED = "sensitive_contract_value_redacted"
DIAGNOSTIC_CODES = (
    DIAGNOSTIC_CONTRACT_LOCATION_MISSING,
    DIAGNOSTIC_CONTRACT_LOCATION_AMBIGUOUS,
    DIAGNOSTIC_CONTRACT_LOCATION_UNREADABLE,
    DIAGNOSTIC_CONTRACT_LOCATION_SKIPPED,
    DIAGNOSTIC_CONTRACT_LOCATION_UNSUPPORTED,
    DIAGNOSTIC_CONTRACT_VALUE_MISMATCH,
    DIAGNOSTIC_CONTRACT_CROSS_LOCATION_MISMATCH,
    DIAGNOSTIC_CONTRACT_REFERENCE_TYPE_INCOMPATIBLE,
    DIAGNOSTIC_CONTRACT_SYMBOL_NOT_FOUND,
    DIAGNOSTIC_CONTRACT_PATH_NOT_FOUND,
    DIAGNOSTIC_CONTRACT_EXPECTED_VALUE_UNSUPPORTED,
    DIAGNOSTIC_CONTRACT_ALLOWED_VALUE_UNSUPPORTED,
    DIAGNOSTIC_CONTRACT_NORMALIZATION_FAILED,
    DIAGNOSTIC_CONTRACT_PORT_INVALID,
    DIAGNOSTIC_CONTRACT_URL_INVALID,
    DIAGNOSTIC_CONTRACT_EVIDENCE_TRUNCATED,
    DIAGNOSTIC_CONTRACT_FINDING_CAP_REACHED,
    DIAGNOSTIC_CONTRACT_DIAGNOSTIC_CAP_REACHED,
    DIAGNOSTIC_DUPLICATE_CONTRACT_NAME,
    DIAGNOSTIC_DUPLICATE_CONTRACT_LOCATION,
    DIAGNOSTIC_SENSITIVE_CONTRACT_VALUE_REDACTED,
)

LOCATION_FINDING_FIELD_ORDER = (
    "contract_name",
    "repository_id",
    "path",
    "symbol",
    "status",
    "expected_value",
    "allowed_values",
    "observed_values",
    "normalized_expected",
    "normalized_allowed_values",
    "normalized_observed_values",
    "matching_reference_ids",
    "confidence",
    "confidence_score",
    "evidence",
    "diagnostics",
)
CONTRACT_FINDING_FIELD_ORDER = (
    "name",
    "contract_type",
    "severity",
    "normalization",
    "status",
    "expected_value",
    "allowed_values",
    "location_findings",
    "distinct_observed_values",
    "confidence",
    "confidence_score",
    "evidence",
    "diagnostics",
)
DIAGNOSTIC_FIELD_ORDER = (
    "code",
    "severity",
    "summary",
    "contract_name",
    "repository_id",
    "path",
    "symbol",
    "details",
)
RESULT_FIELD_ORDER = (
    "contract_findings",
    "diagnostics",
)

SECRET_VALUE = "[redacted]"
SECRET_KEYWORDS = ("password", "secret", "token", "api_key", "apikey", "private_key", "cookie", "credential")
HEADER_HINTS = ("header", "auth", "authorization")


class WorkspaceContractComparisonError(ValueError):
    """Raised when a Q5 comparison contract is invalid."""


@dataclass(frozen=True, slots=True)
class NormalizedValue:
    value: Any
    key: str


@dataclass(frozen=True, slots=True)
class LocationState:
    repository_id: str
    path: str
    state: str
    symbol: str | None = None
    diagnostic_code: str | None = None
    summary: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "repository_id", _validate_nonempty_string(self.repository_id, "repository_id"))
        object.__setattr__(self, "path", _normalize_relative_path(self.path, "path"))
        object.__setattr__(self, "state", _validate_choice(self.state, "state", LOCATION_STATES))
        object.__setattr__(self, "symbol", _validate_optional_string(self.symbol, "symbol"))
        object.__setattr__(self, "diagnostic_code", _validate_optional_string(self.diagnostic_code, "diagnostic_code"))
        object.__setattr__(self, "summary", _validate_optional_string(self.summary, "summary"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "repository_id": self.repository_id,
            "path": self.path,
            "symbol": self.symbol,
            "state": self.state,
            "diagnostic_code": self.diagnostic_code,
            "summary": self.summary,
        }


@dataclass(frozen=True, slots=True)
class WorkspaceContractDiagnostic:
    code: str
    severity: str
    summary: str
    contract_name: str | None = None
    repository_id: str | None = None
    path: str | None = None
    symbol: str | None = None
    details: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", _validate_choice(self.code, "code", DIAGNOSTIC_CODES))
        object.__setattr__(self, "severity", _validate_choice(self.severity, "severity", DIAGNOSTIC_SEVERITIES))
        object.__setattr__(self, "summary", _validate_nonempty_string(self.summary, "summary"))
        object.__setattr__(self, "contract_name", _validate_optional_string(self.contract_name, "contract_name"))
        object.__setattr__(self, "repository_id", _validate_optional_string(self.repository_id, "repository_id"))
        object.__setattr__(self, "path", _validate_optional_string(self.path, "path"))
        object.__setattr__(self, "symbol", _validate_optional_string(self.symbol, "symbol"))
        object.__setattr__(self, "details", _copy_json(self.details or {}, "details"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "summary": self.summary,
            "contract_name": self.contract_name,
            "repository_id": self.repository_id,
            "path": self.path,
            "symbol": self.symbol,
            "details": _json_ready(self.details or {}),
        }


@dataclass(frozen=True, slots=True)
class ContractLocationFinding:
    contract_name: str
    repository_id: str
    path: str
    status: str
    expected_value: Any
    allowed_values: tuple[Any, ...]
    observed_values: tuple[Any, ...]
    normalized_expected: Any
    normalized_allowed_values: tuple[Any, ...]
    normalized_observed_values: tuple[Any, ...]
    matching_reference_ids: tuple[str, ...]
    confidence: str
    confidence_score: float
    evidence: tuple[workspace_relationships.RelationshipEvidence, ...] = ()
    diagnostics: tuple[WorkspaceContractDiagnostic, ...] = ()
    symbol: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "contract_name", _validate_nonempty_string(self.contract_name, "contract_name"))
        object.__setattr__(self, "repository_id", _validate_nonempty_string(self.repository_id, "repository_id"))
        object.__setattr__(self, "path", _normalize_relative_path(self.path, "path"))
        object.__setattr__(self, "symbol", _validate_optional_string(self.symbol, "symbol"))
        object.__setattr__(self, "status", _validate_choice(self.status, "status", STATUSES))
        object.__setattr__(self, "expected_value", _copy_json(self.expected_value, "expected_value"))
        object.__setattr__(self, "allowed_values", tuple(_copy_json(value, "allowed_values") for value in self.allowed_values))
        object.__setattr__(self, "observed_values", tuple(_copy_json(value, "observed_values") for value in self.observed_values))
        object.__setattr__(self, "normalized_expected", _copy_json(self.normalized_expected, "normalized_expected"))
        object.__setattr__(self, "normalized_allowed_values", tuple(_copy_json(value, "normalized_allowed_values") for value in self.normalized_allowed_values))
        object.__setattr__(self, "normalized_observed_values", tuple(_copy_json(value, "normalized_observed_values") for value in self.normalized_observed_values))
        object.__setattr__(self, "matching_reference_ids", tuple(sorted(_validate_nonempty_string(value, "matching_reference_ids") for value in self.matching_reference_ids)))
        object.__setattr__(self, "confidence", _validate_choice(self.confidence, "confidence", CONFIDENCE_LEVELS))
        object.__setattr__(self, "confidence_score", _validate_score(self.confidence_score, "confidence_score"))
        object.__setattr__(self, "evidence", tuple(sorted((_coerce_evidence(item) for item in self.evidence), key=workspace_relationships.evidence_identity_key)))
        object.__setattr__(self, "diagnostics", tuple(sorted((_coerce_diagnostic(item) for item in self.diagnostics), key=diagnostic_sort_key)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_name": self.contract_name,
            "repository_id": self.repository_id,
            "path": self.path,
            "symbol": self.symbol,
            "status": self.status,
            "expected_value": _json_ready(self.expected_value),
            "allowed_values": [_json_ready(value) for value in self.allowed_values],
            "observed_values": [_json_ready(value) for value in self.observed_values],
            "normalized_expected": _json_ready(self.normalized_expected),
            "normalized_allowed_values": [_json_ready(value) for value in self.normalized_allowed_values],
            "normalized_observed_values": [_json_ready(value) for value in self.normalized_observed_values],
            "matching_reference_ids": list(self.matching_reference_ids),
            "confidence": self.confidence,
            "confidence_score": self.confidence_score,
            "evidence": [item.to_dict() for item in self.evidence],
            "diagnostics": [item.to_dict() for item in self.diagnostics],
        }


@dataclass(frozen=True, slots=True)
class SharedContractFinding:
    name: str
    contract_type: str
    severity: str
    normalization: str
    status: str
    expected_value: Any
    allowed_values: tuple[Any, ...]
    location_findings: tuple[ContractLocationFinding, ...]
    distinct_observed_values: tuple[Any, ...]
    confidence: str
    confidence_score: float
    evidence: tuple[workspace_relationships.RelationshipEvidence, ...] = ()
    diagnostics: tuple[WorkspaceContractDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _validate_nonempty_string(self.name, "name"))
        object.__setattr__(self, "contract_type", _validate_choice(self.contract_type, "contract_type", workspace_config.SHARED_CONTRACT_TYPES))
        object.__setattr__(self, "severity", _validate_choice(self.severity, "severity", workspace_config.CONTRACT_SEVERITIES))
        object.__setattr__(self, "normalization", _validate_choice(self.normalization, "normalization", workspace_config.CONTRACT_NORMALIZATIONS))
        object.__setattr__(self, "status", _validate_choice(self.status, "status", STATUSES))
        object.__setattr__(self, "expected_value", _copy_json(self.expected_value, "expected_value"))
        object.__setattr__(self, "allowed_values", tuple(_copy_json(value, "allowed_values") for value in self.allowed_values))
        object.__setattr__(self, "location_findings", tuple(sorted((_coerce_location_finding(item) for item in self.location_findings), key=location_finding_sort_key)))
        object.__setattr__(self, "distinct_observed_values", tuple(_copy_json(value, "distinct_observed_values") for value in self.distinct_observed_values))
        object.__setattr__(self, "confidence", _validate_choice(self.confidence, "confidence", CONFIDENCE_LEVELS))
        object.__setattr__(self, "confidence_score", _validate_score(self.confidence_score, "confidence_score"))
        object.__setattr__(self, "evidence", tuple(sorted((_coerce_evidence(item) for item in self.evidence), key=workspace_relationships.evidence_identity_key)))
        object.__setattr__(self, "diagnostics", tuple(sorted((_coerce_diagnostic(item) for item in self.diagnostics), key=diagnostic_sort_key)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "contract_type": self.contract_type,
            "severity": self.severity,
            "normalization": self.normalization,
            "status": self.status,
            "expected_value": _json_ready(self.expected_value),
            "allowed_values": [_json_ready(value) for value in self.allowed_values],
            "location_findings": [finding.to_dict() for finding in self.location_findings],
            "distinct_observed_values": [_json_ready(value) for value in self.distinct_observed_values],
            "confidence": self.confidence,
            "confidence_score": self.confidence_score,
            "evidence": [item.to_dict() for item in self.evidence],
            "diagnostics": [item.to_dict() for item in self.diagnostics],
        }


@dataclass(frozen=True, slots=True)
class SharedContractComparisonResult:
    contract_findings: tuple[SharedContractFinding, ...] = ()
    diagnostics: tuple[WorkspaceContractDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "contract_findings", tuple(sorted((_coerce_contract_finding(item) for item in self.contract_findings), key=contract_finding_sort_key)))
        object.__setattr__(self, "diagnostics", tuple(sorted((_coerce_diagnostic(item) for item in self.diagnostics), key=diagnostic_sort_key)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_findings": [finding.to_dict() for finding in self.contract_findings],
            "diagnostics": [diagnostic.to_dict() for diagnostic in self.diagnostics],
        }


def _validate_nonempty_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkspaceContractComparisonError(f"{name} must be a non-empty string")
    if value != value.strip() or "\x00" in value:
        raise WorkspaceContractComparisonError(f"{name} must not contain padding or null bytes")
    return value


def _validate_optional_string(value: Any, name: str) -> str | None:
    if value is None:
        return None
    return _validate_nonempty_string(value, name)


def _validate_choice(value: Any, name: str, choices: tuple[str, ...]) -> str:
    text = _validate_nonempty_string(value, name)
    if text not in choices:
        raise WorkspaceContractComparisonError(f"{name} must be one of: {', '.join(choices)}")
    return text


def _validate_score(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized < 0.0 or normalized > 1.0:
        raise WorkspaceContractComparisonError(f"{name} must be between 0.0 and 1.0")
    return round(normalized, 3)


def _validate_limit(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 1:
        raise WorkspaceContractComparisonError(f"{name} must be at least 1")
    return value


def _normalize_relative_path(value: Any, name: str) -> str:
    text = _validate_nonempty_string(value, name)
    windows_path = PureWindowsPath(text)
    posix_text = text.replace("\\", "/")
    posix_path = PurePosixPath(posix_text)
    if windows_path.drive or windows_path.is_absolute() or posix_path.is_absolute():
        raise WorkspaceContractComparisonError(f"{name} must be relative")
    collapsed: list[str] = []
    for part in posix_path.parts:
        if part in ("", "."):
            continue
        if part == "..":
            raise WorkspaceContractComparisonError(f"{name} must not contain parent traversal")
        collapsed.append(part)
    return PurePosixPath(*collapsed).as_posix() if collapsed else "."


def _copy_json(value: Any, name: str) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise WorkspaceContractComparisonError(f"{name} must be finite")
        return value
    if isinstance(value, Mapping):
        copied = {}
        for key in sorted(value):
            if not isinstance(key, str):
                raise WorkspaceContractComparisonError(f"{name} keys must be strings")
            copied[key] = _copy_json(value[key], f"{name}.{key}")
        return copied
    if isinstance(value, (list, tuple)):
        return tuple(_copy_json(item, f"{name}[{index}]") for index, item in enumerate(value))
    raise WorkspaceContractComparisonError(f"{name} must be JSON-ready")


def _json_ready(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, Mapping):
        return {key: _json_ready(value[key]) for key in sorted(value)}
    return value


def _json_key(value: Any) -> str:
    return json.dumps(_json_ready(value), sort_keys=True, separators=(",", ":"))


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


def _coerce_reference(value: Any) -> workspace_references.WorkspaceReference:
    if isinstance(value, workspace_references.WorkspaceReference):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("reference must be a WorkspaceReference or mapping")
    return workspace_references.WorkspaceReference(
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


def _coerce_state(value: Any) -> LocationState:
    if isinstance(value, LocationState):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("location state must be a LocationState or mapping")
    return LocationState(
        repository_id=value["repository_id"],
        path=value["path"],
        symbol=value.get("symbol"),
        state=value["state"],
        diagnostic_code=value.get("diagnostic_code"),
        summary=value.get("summary"),
    )


def _coerce_diagnostic(value: Any) -> WorkspaceContractDiagnostic:
    if isinstance(value, WorkspaceContractDiagnostic):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("diagnostic must be a WorkspaceContractDiagnostic or mapping")
    return WorkspaceContractDiagnostic(
        code=value["code"],
        severity=value["severity"],
        summary=value["summary"],
        contract_name=value.get("contract_name"),
        repository_id=value.get("repository_id"),
        path=value.get("path"),
        symbol=value.get("symbol"),
        details=value.get("details"),
    )


def _coerce_location_finding(value: Any) -> ContractLocationFinding:
    if isinstance(value, ContractLocationFinding):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("location finding must be a ContractLocationFinding or mapping")
    return ContractLocationFinding(
        contract_name=value["contract_name"],
        repository_id=value["repository_id"],
        path=value["path"],
        symbol=value.get("symbol"),
        status=value["status"],
        expected_value=value["expected_value"],
        allowed_values=tuple(value.get("allowed_values", ())),
        observed_values=tuple(value.get("observed_values", ())),
        normalized_expected=value.get("normalized_expected"),
        normalized_allowed_values=tuple(value.get("normalized_allowed_values", ())),
        normalized_observed_values=tuple(value.get("normalized_observed_values", ())),
        matching_reference_ids=tuple(value.get("matching_reference_ids", ())),
        confidence=value["confidence"],
        confidence_score=value["confidence_score"],
        evidence=tuple(value.get("evidence", ())),
        diagnostics=tuple(value.get("diagnostics", ())),
    )


def _coerce_contract_finding(value: Any) -> SharedContractFinding:
    if isinstance(value, SharedContractFinding):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("contract finding must be a SharedContractFinding or mapping")
    return SharedContractFinding(
        name=value["name"],
        contract_type=value["contract_type"],
        severity=value["severity"],
        normalization=value["normalization"],
        status=value["status"],
        expected_value=value["expected_value"],
        allowed_values=tuple(value.get("allowed_values", ())),
        location_findings=tuple(value.get("location_findings", ())),
        distinct_observed_values=tuple(value.get("distinct_observed_values", ())),
        confidence=value["confidence"],
        confidence_score=value["confidence_score"],
        evidence=tuple(value.get("evidence", ())),
        diagnostics=tuple(value.get("diagnostics", ())),
    )


def diagnostic_sort_key(diagnostic: WorkspaceContractDiagnostic) -> tuple[object, ...]:
    return (
        diagnostic.code,
        diagnostic.severity,
        diagnostic.contract_name or "",
        diagnostic.repository_id or "",
        diagnostic.path or "",
        diagnostic.symbol or "",
        _json_key(diagnostic.details or {}),
        diagnostic.summary,
    )


def location_finding_sort_key(finding: ContractLocationFinding) -> tuple[object, ...]:
    return (finding.repository_id, finding.path, finding.symbol or "", finding.contract_name)


def contract_finding_sort_key(finding: SharedContractFinding) -> tuple[object, ...]:
    return (finding.name, workspace_config.SHARED_CONTRACT_TYPES.index(finding.contract_type))


def _diagnostic(
    code: str,
    severity: str,
    summary: str,
    *,
    contract_name: str | None = None,
    repository_id: str | None = None,
    path: str | None = None,
    symbol: str | None = None,
    details: Mapping[str, Any] | None = None,
) -> WorkspaceContractDiagnostic:
    return WorkspaceContractDiagnostic(code, severity, summary, contract_name, repository_id, path, symbol, details)


def _severity_for_contract(contract: Mapping[str, Any]) -> str:
    return str(contract.get("severity", workspace_config.CONTRACT_SEVERITY_WARNING))


def _mismatch_severity(contract: Mapping[str, Any]) -> str:
    severity = _severity_for_contract(contract)
    if severity == workspace_config.CONTRACT_SEVERITY_ERROR:
        return DIAGNOSTIC_SEVERITY_ERROR
    if severity == workspace_config.CONTRACT_SEVERITY_INFO:
        return DIAGNOSTIC_SEVERITY_INFO
    return DIAGNOSTIC_SEVERITY_WARNING


def _confidence_from_score(score: float) -> str:
    if score >= 0.7:
        return CONFIDENCE_HIGH
    if score >= 0.4:
        return CONFIDENCE_MEDIUM
    return CONFIDENCE_LOW


def _is_sensitive_name(name: str | None) -> bool:
    if not name:
        return False
    normalized = name.lower().replace("-", "_").replace(".", "_")
    return any(keyword in normalized for keyword in SECRET_KEYWORDS)


def _looks_secret_like(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    stripped = value.strip()
    if "-----BEGIN " in stripped:
        return True
    if stripped.lower().startswith(("bearer ", "basic ")):
        return True
    if len(stripped) >= 32 and all(char.isalnum() or char in "_-./+=" for char in stripped):
        return True
    return False


def _redact_if_sensitive(value: Any, contract_name: str, diagnostics: list[WorkspaceContractDiagnostic]) -> Any:
    if _is_sensitive_name(contract_name) or _looks_secret_like(value):
        diagnostics.append(
            _diagnostic(
                DIAGNOSTIC_SENSITIVE_CONTRACT_VALUE_REDACTED,
                DIAGNOSTIC_SEVERITY_WARNING,
                "Sensitive shared-contract value was redacted.",
                contract_name=contract_name,
            )
        )
        return SECRET_VALUE
    return value


def _normalize_url(value: Any) -> NormalizedValue:
    if not isinstance(value, str):
        raise WorkspaceContractComparisonError("url normalization requires a string")
    normalized, _, diagnostic = workspace_references.normalize_reference_url(value)
    if diagnostic or normalized is None:
        raise WorkspaceContractComparisonError("invalid URL")
    return NormalizedValue(normalized, f"str:{normalized}")


def _normalize_port(value: Any) -> NormalizedValue:
    port_value: int | None = None
    if isinstance(value, bool):
        raise WorkspaceContractComparisonError("boolean is not a valid port")
    if isinstance(value, int):
        port_value = value
    elif isinstance(value, str):
        text = value.strip()
        if text.isdigit():
            port_value = int(text)
        else:
            normalized, _, diagnostic = workspace_references.normalize_reference_url(text)
            if diagnostic or normalized is None:
                raise WorkspaceContractComparisonError("invalid port")
            parsed = urlsplit(normalized)
            port_value = parsed.port
    if port_value is None:
        raise WorkspaceContractComparisonError("missing explicit port")
    if port_value < 1 or port_value > 65535:
        raise WorkspaceContractComparisonError("port out of range")
    return NormalizedValue(port_value, f"int:{port_value}")


def normalize_contract_value(value: Any, normalization: str) -> NormalizedValue:
    normalization = _validate_choice(normalization, "normalization", workspace_config.CONTRACT_NORMALIZATIONS)
    if normalization == workspace_config.CONTRACT_NORMALIZATION_EXACT:
        return NormalizedValue(value, f"{type(value).__name__}:{_json_key(value)}")
    if normalization == workspace_config.CONTRACT_NORMALIZATION_CASE_INSENSITIVE:
        if not isinstance(value, str):
            raise WorkspaceContractComparisonError("case_insensitive normalization requires a string")
        normalized = value.casefold()
        return NormalizedValue(normalized, f"str:{normalized}")
    if normalization == workspace_config.CONTRACT_NORMALIZATION_TRIMMED:
        if not isinstance(value, str):
            raise WorkspaceContractComparisonError("trimmed normalization requires a string")
        normalized = value.strip()
        return NormalizedValue(normalized, f"str:{normalized}")
    if normalization == workspace_config.CONTRACT_NORMALIZATION_URL:
        return _normalize_url(value)
    if normalization == workspace_config.CONTRACT_NORMALIZATION_PORT:
        return _normalize_port(value)
    raise WorkspaceContractComparisonError("unsupported normalization")


def _reference_observed_value(contract_type: str, reference: workspace_references.WorkspaceReference) -> Any:
    metadata = reference.metadata or {}
    if contract_type == workspace_config.SHARED_CONTRACT_TYPE_PORT_NUMBER:
        normalized, _, diagnostic = workspace_references.normalize_reference_url(reference.normalized_value)
        if diagnostic or normalized is None:
            return reference.normalized_value
        return normalized
    if contract_type == workspace_config.SHARED_CONTRACT_TYPE_MESSAGE_EVENT:
        value = metadata.get("message_event")
        return value if value is not None else reference.normalized_value
    return reference.normalized_value


def _reference_compatible(contract: Mapping[str, Any], reference: workspace_references.WorkspaceReference, location: Mapping[str, Any]) -> bool:
    contract_type = contract["contract_type"]
    reference_type = reference.reference_type
    symbol = (reference.symbol or "").lower()
    path = reference.source_path.lower()
    metadata = reference.metadata or {}
    if contract_type == workspace_config.SHARED_CONTRACT_TYPE_AUTH_HEADER:
        return reference_type == workspace_references.REFERENCE_TYPE_SHARED_CONSTANT and any(hint in f"{symbol} {path}".lower() for hint in HEADER_HINTS)
    if contract_type == workspace_config.SHARED_CONTRACT_TYPE_IFRAME_URL:
        return reference_type in {
            workspace_references.REFERENCE_TYPE_IFRAME_SRC,
            workspace_references.REFERENCE_TYPE_ENVIRONMENT_URL,
            workspace_references.REFERENCE_TYPE_SHARED_CONSTANT,
        }
    if contract_type == workspace_config.SHARED_CONTRACT_TYPE_API_CONSTANT:
        return reference_type in {
            workspace_references.REFERENCE_TYPE_API_BASE_URL,
            workspace_references.REFERENCE_TYPE_ENVIRONMENT_URL,
            workspace_references.REFERENCE_TYPE_SHARED_CONSTANT,
        }
    if contract_type == workspace_config.SHARED_CONTRACT_TYPE_ROUTE_NAME:
        return reference_type in {
            workspace_references.REFERENCE_TYPE_ROUTE_CONSTANT,
            workspace_references.REFERENCE_TYPE_SHARED_CONSTANT,
        }
    if contract_type == workspace_config.SHARED_CONTRACT_TYPE_PORT_NUMBER:
        return reference_type in {
            workspace_references.REFERENCE_TYPE_LOCALHOST_URL,
            workspace_references.REFERENCE_TYPE_ENVIRONMENT_URL,
            workspace_references.REFERENCE_TYPE_API_BASE_URL,
            workspace_references.REFERENCE_TYPE_SHARED_CONSTANT,
        }
    if contract_type == workspace_config.SHARED_CONTRACT_TYPE_MESSAGE_EVENT:
        return reference_type in {
            workspace_references.REFERENCE_TYPE_POST_MESSAGE_SEND,
            workspace_references.REFERENCE_TYPE_MESSAGE_LISTENER,
            workspace_references.REFERENCE_TYPE_SHARED_CONSTANT,
        } and (reference_type == workspace_references.REFERENCE_TYPE_SHARED_CONSTANT or metadata.get("message_event") is not None)
    if contract_type == workspace_config.SHARED_CONTRACT_TYPE_CUSTOM:
        return location.get("symbol") is not None and reference.symbol == location.get("symbol")
    return False


def _reference_key(reference: workspace_references.WorkspaceReference) -> str:
    parts = workspace_references.reference_identity_key(reference)
    return json.dumps(_json_ready(parts), sort_keys=True, separators=(",", ":"))


def _observation_sort_key(reference: workspace_references.WorkspaceReference) -> tuple[object, ...]:
    return (
        reference.source_path,
        reference.line_number or 0,
        workspace_references.REFERENCE_TYPES.index(reference.reference_type),
        reference.normalized_value,
        reference.symbol or "",
        _reference_key(reference),
    )


def _state_key(state: LocationState) -> tuple[str, str, str]:
    return (state.repository_id, state.path, state.symbol or "")


def _location_key(location: Mapping[str, Any]) -> tuple[str, str, str]:
    return (str(location["repository_id"]), _normalize_relative_path(location["path"], "location.path"), str(location.get("symbol") or ""))


def _matching_references(
    contract: Mapping[str, Any],
    location: Mapping[str, Any],
    references: Iterable[workspace_references.WorkspaceReference],
) -> tuple[workspace_references.WorkspaceReference, ...]:
    repository_id, path, symbol = _location_key(location)
    path_matches = [
        reference
        for reference in references
        if reference.repository_id == repository_id and reference.source_path == path and _reference_compatible(contract, reference, location)
    ]
    if symbol:
        exact = [reference for reference in path_matches if reference.symbol == symbol]
        return tuple(sorted(exact, key=_observation_sort_key))
    return tuple(sorted(path_matches, key=_observation_sort_key))


def _make_evidence(
    contract_name: str,
    repository_id: str,
    path: str,
    summary: str,
    score: float,
    *,
    metadata: Mapping[str, Any] | None = None,
) -> workspace_relationships.RelationshipEvidence:
    if score >= 0.7:
        strength = workspace_relationships.EVIDENCE_STRENGTH_STRONG
    elif score >= 0.4:
        strength = workspace_relationships.EVIDENCE_STRENGTH_MEDIUM
    else:
        strength = workspace_relationships.EVIDENCE_STRENGTH_WEAK
    return workspace_relationships.RelationshipEvidence(
        signal_type="shared_contract_comparison",
        source_repository_id=repository_id,
        source_path=path,
        summary=summary,
        strength=strength,
        metadata={"contract_name": contract_name, **(metadata or {})},
    )


def _bound_evidence(
    evidence: Iterable[workspace_relationships.RelationshipEvidence],
    limit: int,
    diagnostics: list[WorkspaceContractDiagnostic],
    *,
    contract_name: str,
    repository_id: str | None = None,
    path: str | None = None,
) -> tuple[workspace_relationships.RelationshipEvidence, ...]:
    values = tuple(sorted({_json_key(item.to_dict()): item for item in evidence}.values(), key=workspace_relationships.evidence_identity_key))
    if len(values) <= limit:
        return values
    diagnostics.append(
        _diagnostic(
            DIAGNOSTIC_CONTRACT_EVIDENCE_TRUNCATED,
            DIAGNOSTIC_SEVERITY_INFO,
            "Contract comparison evidence was truncated.",
            contract_name=contract_name,
            repository_id=repository_id,
            path=path,
            details={"limit": limit, "omitted": len(values) - limit},
        )
    )
    return values[:limit]


def _allowed_normalized_values(
    contract: Mapping[str, Any],
    diagnostics: list[WorkspaceContractDiagnostic],
) -> tuple[NormalizedValue, ...]:
    values = []
    seen = set()
    for value in contract.get("allowed_values", ()):
        try:
            normalized = normalize_contract_value(value, contract["normalization"])
        except WorkspaceContractComparisonError as error:
            diagnostics.append(
                _diagnostic(
                    DIAGNOSTIC_CONTRACT_ALLOWED_VALUE_UNSUPPORTED,
                    _mismatch_severity(contract),
                    str(error),
                    contract_name=contract["name"],
                )
            )
            continue
        if normalized.key not in seen:
            values.append(normalized)
            seen.add(normalized.key)
    return tuple(sorted(values, key=lambda item: item.key))


def _diagnostic_for_state(state: LocationState, contract: Mapping[str, Any]) -> WorkspaceContractDiagnostic:
    code = {
        LOCATION_STATE_UNREADABLE: DIAGNOSTIC_CONTRACT_LOCATION_UNREADABLE,
        LOCATION_STATE_SKIPPED: DIAGNOSTIC_CONTRACT_LOCATION_SKIPPED,
        LOCATION_STATE_UNSUPPORTED: DIAGNOSTIC_CONTRACT_LOCATION_UNSUPPORTED,
    }[state.state]
    return _diagnostic(
        code,
        _mismatch_severity(contract),
        state.summary or f"Contract location was {state.state}.",
        contract_name=contract["name"],
        repository_id=state.repository_id,
        path=state.path,
        symbol=state.symbol,
        details={"diagnostic_code": state.diagnostic_code} if state.diagnostic_code else {},
    )


def _location_finding(
    contract: Mapping[str, Any],
    location: Mapping[str, Any],
    references: tuple[workspace_references.WorkspaceReference, ...],
    states: Mapping[tuple[str, str, str], LocationState],
    *,
    max_observations: int,
    max_evidence: int,
) -> ContractLocationFinding:
    diagnostics: list[WorkspaceContractDiagnostic] = []
    repository_id, path, symbol = _location_key(location)
    safe_expected = _redact_if_sensitive(contract["expected_value"], contract["name"], diagnostics)
    safe_allowed = tuple(_redact_if_sensitive(value, contract["name"], diagnostics) for value in contract.get("allowed_values", ()))
    normalized_expected: NormalizedValue | None = None
    normalized_allowed: tuple[NormalizedValue, ...] = ()
    if safe_expected == SECRET_VALUE or any(value == SECRET_VALUE for value in safe_allowed):
        score = 0.85
        diagnostics.append(
            _diagnostic(
                DIAGNOSTIC_CONTRACT_LOCATION_UNSUPPORTED,
                DIAGNOSTIC_SEVERITY_WARNING,
                "Sensitive configured contract value was not compared.",
                contract_name=contract["name"],
                repository_id=repository_id,
                path=path,
                symbol=symbol or None,
            )
        )
        return ContractLocationFinding(
            contract_name=contract["name"],
            repository_id=repository_id,
            path=path,
            symbol=symbol or None,
            status=STATUS_UNSUPPORTED,
            expected_value=safe_expected,
            allowed_values=safe_allowed,
            observed_values=(),
            normalized_expected=None,
            normalized_allowed_values=(),
            normalized_observed_values=(),
            matching_reference_ids=(),
            confidence=_confidence_from_score(score),
            confidence_score=score,
            evidence=(),
            diagnostics=tuple(diagnostics),
        )
    state = states.get((repository_id, path, symbol))
    if state:
        diagnostics.append(_diagnostic_for_state(state, contract))
        score = 0.9
        evidence = (
            _make_evidence(contract["name"], repository_id, path, f"Configured location was reported as {state.state}.", score),
        )
        return ContractLocationFinding(
            contract_name=contract["name"],
            repository_id=repository_id,
            path=path,
            symbol=symbol or None,
            status=state.state,
            expected_value=safe_expected,
            allowed_values=safe_allowed,
            observed_values=(),
            normalized_expected=None,
            normalized_allowed_values=(),
            normalized_observed_values=(),
            matching_reference_ids=(),
            confidence=_confidence_from_score(score),
            confidence_score=score,
            evidence=_bound_evidence(evidence, max_evidence, diagnostics, contract_name=contract["name"], repository_id=repository_id, path=path),
            diagnostics=tuple(diagnostics),
        )
    if contract["contract_type"] == workspace_config.SHARED_CONTRACT_TYPE_SHARED_PACKAGE:
        diagnostics.append(
            _diagnostic(
                DIAGNOSTIC_CONTRACT_LOCATION_UNSUPPORTED,
                _mismatch_severity(contract),
                "shared_package comparison is unsupported until package-name extraction exists.",
                contract_name=contract["name"],
                repository_id=repository_id,
                path=path,
                symbol=symbol or None,
            )
        )
        score = 0.85
        return ContractLocationFinding(
            contract_name=contract["name"],
            repository_id=repository_id,
            path=path,
            symbol=symbol or None,
            status=STATUS_UNSUPPORTED,
            expected_value=safe_expected,
            allowed_values=safe_allowed,
            observed_values=(),
            normalized_expected=None,
            normalized_allowed_values=(),
            normalized_observed_values=(),
            matching_reference_ids=(),
            confidence=_confidence_from_score(score),
            confidence_score=score,
            evidence=(),
            diagnostics=tuple(diagnostics),
        )
    try:
        normalized_expected = normalize_contract_value(contract["expected_value"], contract["normalization"])
    except WorkspaceContractComparisonError as error:
        diagnostics.append(_diagnostic(DIAGNOSTIC_CONTRACT_EXPECTED_VALUE_UNSUPPORTED, _mismatch_severity(contract), str(error), contract_name=contract["name"], repository_id=repository_id, path=path, symbol=symbol or None))
    normalized_allowed = _allowed_normalized_values(contract, diagnostics)
    if normalized_expected is None:
        score = 0.85
        return ContractLocationFinding(
            contract_name=contract["name"],
            repository_id=repository_id,
            path=path,
            symbol=symbol or None,
            status=STATUS_UNSUPPORTED,
            expected_value=safe_expected,
            allowed_values=safe_allowed,
            observed_values=(),
            normalized_expected=None,
            normalized_allowed_values=tuple(value.value for value in normalized_allowed),
            normalized_observed_values=(),
            matching_reference_ids=(),
            confidence=_confidence_from_score(score),
            confidence_score=score,
            evidence=(),
            diagnostics=tuple(diagnostics),
        )

    matches = _matching_references(contract, location, references)
    if not matches:
        same_path = [reference for reference in references if reference.repository_id == repository_id and reference.source_path == path]
        same_symbol = [reference for reference in same_path if symbol and reference.symbol == symbol]
        if symbol and same_path and not same_symbol:
            code = DIAGNOSTIC_CONTRACT_SYMBOL_NOT_FOUND
            summary = "Configured contract symbol was not found in matching references."
        elif not same_path:
            code = DIAGNOSTIC_CONTRACT_PATH_NOT_FOUND
            summary = "Configured contract path had no matching references."
        else:
            code = DIAGNOSTIC_CONTRACT_REFERENCE_TYPE_INCOMPATIBLE
            summary = "References at the configured location were incompatible with the contract type."
        diagnostics.append(_diagnostic(code, _mismatch_severity(contract), summary, contract_name=contract["name"], repository_id=repository_id, path=path, symbol=symbol or None))
        diagnostics.append(_diagnostic(DIAGNOSTIC_CONTRACT_LOCATION_MISSING, _mismatch_severity(contract), "No comparable observation was found for the configured location.", contract_name=contract["name"], repository_id=repository_id, path=path, symbol=symbol or None))
        score = 0.25
        evidence = (_make_evidence(contract["name"], repository_id, path, "No comparable observation was found.", score),)
        return ContractLocationFinding(
            contract_name=contract["name"],
            repository_id=repository_id,
            path=path,
            symbol=symbol or None,
            status=STATUS_MISSING,
            expected_value=safe_expected,
            allowed_values=safe_allowed,
            observed_values=(),
            normalized_expected=normalized_expected.value,
            normalized_allowed_values=tuple(value.value for value in normalized_allowed),
            normalized_observed_values=(),
            matching_reference_ids=(),
            confidence=_confidence_from_score(score),
            confidence_score=score,
            evidence=_bound_evidence(evidence, max_evidence, diagnostics, contract_name=contract["name"], repository_id=repository_id, path=path),
            diagnostics=tuple(diagnostics),
        )

    if len(matches) > max_observations:
        matches = matches[:max_observations]
        diagnostics.append(_diagnostic(DIAGNOSTIC_CONTRACT_LOCATION_AMBIGUOUS, DIAGNOSTIC_SEVERITY_WARNING, "Observation cap was reached for the configured location.", contract_name=contract["name"], repository_id=repository_id, path=path, symbol=symbol or None, details={"limit": max_observations}))

    observed_by_key: dict[str, tuple[NormalizedValue, Any]] = {}
    reference_ids = []
    for reference in matches:
        observed = _reference_observed_value(contract["contract_type"], reference)
        if _looks_secret_like(reference.raw_value) or _looks_secret_like(observed):
            diagnostics.append(_diagnostic(DIAGNOSTIC_SENSITIVE_CONTRACT_VALUE_REDACTED, DIAGNOSTIC_SEVERITY_WARNING, "Sensitive observed value was redacted.", contract_name=contract["name"], repository_id=repository_id, path=path, symbol=symbol or None))
            observed = SECRET_VALUE
        try:
            normalized = normalize_contract_value(observed, contract["normalization"])
        except WorkspaceContractComparisonError as error:
            code = DIAGNOSTIC_CONTRACT_PORT_INVALID if contract["normalization"] == workspace_config.CONTRACT_NORMALIZATION_PORT else DIAGNOSTIC_CONTRACT_URL_INVALID if contract["normalization"] == workspace_config.CONTRACT_NORMALIZATION_URL else DIAGNOSTIC_CONTRACT_NORMALIZATION_FAILED
            diagnostics.append(_diagnostic(code, _mismatch_severity(contract), str(error), contract_name=contract["name"], repository_id=repository_id, path=path, symbol=symbol or None))
            continue
        if normalized.key not in observed_by_key:
            observed_by_key[normalized.key] = (normalized, observed)
        reference_ids.append(_reference_key(reference))
    normalized_observed = tuple(item[0] for _, item in sorted(observed_by_key.items()))
    observed_values = tuple(item[1] for _, item in sorted(observed_by_key.items()))
    allowed_keys = {normalized_expected.key, *(value.key for value in normalized_allowed)}
    observed_keys = {value.key for value in normalized_observed}
    evidence: list[workspace_relationships.RelationshipEvidence] = []
    if len(observed_keys) > 1:
        status = STATUS_AMBIGUOUS
        score = 0.35
        diagnostics.append(_diagnostic(DIAGNOSTIC_CONTRACT_LOCATION_AMBIGUOUS, _mismatch_severity(contract), "Multiple different observations matched the configured location.", contract_name=contract["name"], repository_id=repository_id, path=path, symbol=symbol or None, details={"observed_count": len(observed_keys)}))
        evidence.append(_make_evidence(contract["name"], repository_id, path, "Multiple different observations matched this location.", score))
    elif observed_keys and not observed_keys <= allowed_keys:
        status = STATUS_INCONSISTENT
        score = 0.85 if symbol else 0.65
        diagnostics.append(_diagnostic(DIAGNOSTIC_CONTRACT_VALUE_MISMATCH, _mismatch_severity(contract), "Observed value conflicts with the configured shared contract.", contract_name=contract["name"], repository_id=repository_id, path=path, symbol=symbol or None))
        evidence.append(_make_evidence(contract["name"], repository_id, path, "Observed value conflicts with the expected or allowed value.", score))
    elif observed_keys:
        status = STATUS_CONSISTENT
        score = 0.9 if symbol else 0.65
        evidence.append(_make_evidence(contract["name"], repository_id, path, "Observed value matches the expected or allowed value.", score))
    else:
        status = STATUS_UNSUPPORTED
        score = 0.45
        evidence.append(_make_evidence(contract["name"], repository_id, path, "No observation could be normalized for comparison.", score))
    return ContractLocationFinding(
        contract_name=contract["name"],
        repository_id=repository_id,
        path=path,
        symbol=symbol or None,
        status=status,
        expected_value=safe_expected,
        allowed_values=safe_allowed,
        observed_values=tuple(_redact_if_sensitive(value, contract["name"], diagnostics) for value in observed_values),
        normalized_expected=normalized_expected.value,
        normalized_allowed_values=tuple(value.value for value in normalized_allowed),
        normalized_observed_values=tuple(value.value for value in normalized_observed),
        matching_reference_ids=tuple(sorted(set(reference_ids))),
        confidence=_confidence_from_score(score),
        confidence_score=score,
        evidence=_bound_evidence(evidence, max_evidence, diagnostics, contract_name=contract["name"], repository_id=repository_id, path=path),
        diagnostics=tuple(diagnostics),
    )


def _contract_status(location_findings: tuple[ContractLocationFinding, ...], diagnostics: list[WorkspaceContractDiagnostic], contract: Mapping[str, Any]) -> str:
    observed_keys = {_json_key(value) for finding in location_findings for value in finding.normalized_observed_values}
    individually_consistent = all(finding.status == STATUS_CONSISTENT for finding in location_findings)
    if individually_consistent and len(observed_keys) > 1:
        diagnostics.append(_diagnostic(DIAGNOSTIC_CONTRACT_CROSS_LOCATION_MISMATCH, _mismatch_severity(contract), "Configured locations use different accepted values.", contract_name=contract["name"], details={"distinct_observed_values": len(observed_keys)}))
        return STATUS_INCONSISTENT
    statuses = {finding.status for finding in location_findings}
    for status in STATUS_PRECEDENCE:
        if status in statuses:
            return status
    return STATUS_MISSING


def _contract_finding(
    contract: Mapping[str, Any],
    references: tuple[workspace_references.WorkspaceReference, ...],
    states: Mapping[tuple[str, str, str], LocationState],
    *,
    max_locations: int,
    max_observations: int,
    max_location_evidence: int,
    max_contract_evidence: int,
) -> SharedContractFinding:
    diagnostics: list[WorkspaceContractDiagnostic] = []
    locations = tuple(contract.get("locations", ()))
    if len(locations) > max_locations:
        diagnostics.append(_diagnostic(DIAGNOSTIC_CONTRACT_FINDING_CAP_REACHED, DIAGNOSTIC_SEVERITY_WARNING, "Location finding cap was reached.", contract_name=contract["name"], details={"limit": max_locations, "omitted": len(locations) - max_locations}))
        locations = locations[:max_locations]
    seen_locations = set()
    deduped_locations = []
    for location in locations:
        key = _location_key(location)
        if key in seen_locations:
            diagnostics.append(_diagnostic(DIAGNOSTIC_DUPLICATE_CONTRACT_LOCATION, DIAGNOSTIC_SEVERITY_INFO, "Duplicate contract location was deduplicated.", contract_name=contract["name"], repository_id=key[0], path=key[1], symbol=key[2] or None))
            continue
        seen_locations.add(key)
        deduped_locations.append(location)
    location_findings = tuple(
        _location_finding(contract, location, references, states, max_observations=max_observations, max_evidence=max_location_evidence)
        for location in deduped_locations
    )
    diagnostics.extend(diagnostic for finding in location_findings for diagnostic in finding.diagnostics)
    status = _contract_status(location_findings, diagnostics, contract)
    distinct_values = tuple(value for _, value in sorted({_json_key(value): value for finding in location_findings for value in finding.normalized_observed_values}.items()))
    score = min((finding.confidence_score for finding in location_findings), default=0.1)
    if status == STATUS_CONSISTENT:
        score = max(score, 0.75)
    elif status in {STATUS_INCONSISTENT, STATUS_AMBIGUOUS, STATUS_UNREADABLE, STATUS_SKIPPED, STATUS_UNSUPPORTED}:
        score = max(score, 0.65)
    evidence = [
        _make_evidence(contract["name"], finding.repository_id, finding.path, f"Location {finding.repository_id}:{finding.path} is {finding.status}.", finding.confidence_score)
        for finding in location_findings
    ]
    evidence = list(_bound_evidence(evidence, max_contract_evidence, diagnostics, contract_name=contract["name"]))
    safe_expected = _redact_if_sensitive(contract["expected_value"], contract["name"], diagnostics)
    safe_allowed = tuple(_redact_if_sensitive(value, contract["name"], diagnostics) for value in contract.get("allowed_values", ()))
    return SharedContractFinding(
        name=contract["name"],
        contract_type=contract["contract_type"],
        severity=contract["severity"],
        normalization=contract["normalization"],
        status=status,
        expected_value=safe_expected,
        allowed_values=safe_allowed,
        location_findings=location_findings,
        distinct_observed_values=distinct_values,
        confidence=_confidence_from_score(score),
        confidence_score=score,
        evidence=tuple(evidence),
        diagnostics=tuple(diagnostics),
    )


def _references_from_input(values: Any) -> tuple[workspace_references.WorkspaceReference, ...]:
    if isinstance(values, workspace_references.WorkspaceReferenceExtractionResult):
        return values.references
    if isinstance(values, Mapping) and "references" in values:
        return tuple(_coerce_reference(item) for item in values.get("references", ()))
    return tuple(_coerce_reference(item) for item in values)


def _raw_duplicate_location_diagnostics(workspace: Any) -> tuple[WorkspaceContractDiagnostic, ...]:
    if not isinstance(workspace, Mapping):
        return ()
    diagnostics = []
    for contract in workspace.get("shared_contracts", ()):
        if not isinstance(contract, Mapping):
            continue
        seen = set()
        for location in contract.get("locations", ()):
            if not isinstance(location, Mapping):
                continue
            try:
                key = _location_key(location)
            except WorkspaceContractComparisonError:
                continue
            if key in seen:
                diagnostics.append(
                    _diagnostic(
                        DIAGNOSTIC_DUPLICATE_CONTRACT_LOCATION,
                        DIAGNOSTIC_SEVERITY_INFO,
                        "Duplicate contract location was deduplicated.",
                        contract_name=str(contract.get("name", "")) or None,
                        repository_id=key[0],
                        path=key[1],
                        symbol=key[2] or None,
                    )
                )
            seen.add(key)
    return tuple(diagnostics)


def _bound_diagnostics(diagnostics: Iterable[WorkspaceContractDiagnostic], limit: int) -> tuple[WorkspaceContractDiagnostic, ...]:
    values = tuple(sorted((_coerce_diagnostic(item) for item in diagnostics), key=diagnostic_sort_key))
    if len(values) <= limit:
        return values
    omitted = len(values) - limit
    return (
        *values[: limit - 1],
        _diagnostic(DIAGNOSTIC_CONTRACT_DIAGNOSTIC_CAP_REACHED, DIAGNOSTIC_SEVERITY_WARNING, "Contract diagnostics were truncated.", details={"limit": limit, "omitted": omitted}),
    )


def compare_shared_contracts(
    workspace: Any,
    references: Any,
    *,
    location_states: Iterable[Any] = (),
    max_contracts: int = DEFAULT_MAX_CONTRACTS,
    max_locations_per_contract: int = DEFAULT_MAX_LOCATIONS_PER_CONTRACT,
    max_observations_per_location: int = DEFAULT_MAX_OBSERVATIONS_PER_LOCATION,
    max_evidence_per_location_finding: int = DEFAULT_MAX_EVIDENCE_PER_LOCATION,
    max_evidence_per_contract_finding: int = DEFAULT_MAX_EVIDENCE_PER_CONTRACT,
    max_findings: int = DEFAULT_MAX_FINDINGS,
    max_diagnostics: int = DEFAULT_MAX_DIAGNOSTICS,
) -> SharedContractComparisonResult:
    """Compare configured shared contracts with already-extracted Q4 references."""

    max_contracts = _validate_limit(max_contracts, "max_contracts")
    max_locations_per_contract = _validate_limit(max_locations_per_contract, "max_locations_per_contract")
    max_observations_per_location = _validate_limit(max_observations_per_location, "max_observations_per_location")
    max_evidence_per_location_finding = _validate_limit(max_evidence_per_location_finding, "max_evidence_per_location_finding")
    max_evidence_per_contract_finding = _validate_limit(max_evidence_per_contract_finding, "max_evidence_per_contract_finding")
    max_findings = _validate_limit(max_findings, "max_findings")
    max_diagnostics = _validate_limit(max_diagnostics, "max_diagnostics")
    diagnostics: list[WorkspaceContractDiagnostic] = list(_raw_duplicate_location_diagnostics(workspace))
    normalized_workspace = workspace_config.validate_workspace_config(workspace)
    normalized_references = tuple(sorted(_references_from_input(references), key=_observation_sort_key))
    states = {_state_key(_coerce_state(state)): _coerce_state(state) for state in location_states}
    contracts = tuple(normalized_workspace.get("shared_contracts", ()))
    if len(contracts) > max_contracts:
        diagnostics.append(_diagnostic(DIAGNOSTIC_CONTRACT_FINDING_CAP_REACHED, DIAGNOSTIC_SEVERITY_WARNING, "Contract cap was reached.", details={"limit": max_contracts, "omitted": len(contracts) - max_contracts}))
        contracts = contracts[:max_contracts]
    name_counts: dict[str, int] = {}
    for contract in contracts:
        name_counts[contract["name"]] = name_counts.get(contract["name"], 0) + 1
    for name, count in sorted(name_counts.items()):
        if count > 1:
            diagnostics.append(_diagnostic(DIAGNOSTIC_DUPLICATE_CONTRACT_NAME, DIAGNOSTIC_SEVERITY_ERROR, "Duplicate shared-contract name was found.", contract_name=name, details={"count": count}))
    findings = tuple(
        _contract_finding(
            contract,
            normalized_references,
            states,
            max_locations=max_locations_per_contract,
            max_observations=max_observations_per_location,
            max_location_evidence=max_evidence_per_location_finding,
            max_contract_evidence=max_evidence_per_contract_finding,
        )
        for contract in contracts
    )
    if len(findings) > max_findings:
        diagnostics.append(_diagnostic(DIAGNOSTIC_CONTRACT_FINDING_CAP_REACHED, DIAGNOSTIC_SEVERITY_WARNING, "Finding cap was reached.", details={"limit": max_findings, "omitted": len(findings) - max_findings}))
        findings = findings[:max_findings]
    diagnostics.extend(diagnostic for finding in findings for diagnostic in finding.diagnostics)
    return SharedContractComparisonResult(
        contract_findings=findings,
        diagnostics=_bound_diagnostics(diagnostics, max_diagnostics),
    )


def shared_contract_comparison_result_to_dict(result: SharedContractComparisonResult) -> dict[str, Any]:
    """Return the stable JSON-ready shared-contract comparison result."""

    if not isinstance(result, SharedContractComparisonResult):
        raise TypeError("result must be a SharedContractComparisonResult")
    return result.to_dict()
