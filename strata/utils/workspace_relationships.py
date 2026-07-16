"""Canonical workspace role and relationship contracts for Q3.

This module only combines already-produced workspace configuration, discovery
suggestions, and caller-supplied inferred relationship hints. It does not scan
repositories, read files, build graphs, write artifacts, or print UI output.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import json
import math
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any

import strata.utils.workspace_config as workspace_config
import strata.utils.workspace_discovery as workspace_discovery


DEFAULT_MAX_ROLE_EVIDENCE = 8
DEFAULT_MAX_RELATIONSHIP_EVIDENCE = 8
DEFAULT_MAX_RELATIONSHIPS = 100
DEFAULT_MAX_DIAGNOSTICS = 100

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

ROLE_ORIGIN_EXPLICIT = "explicit"
ROLE_ORIGIN_DISCOVERED = "discovered"
ROLE_ORIGIN_INFERRED = "inferred"
ROLE_ORIGIN_DEFAULT = "default"
ROLE_ORIGINS = (
    ROLE_ORIGIN_EXPLICIT,
    ROLE_ORIGIN_DISCOVERED,
    ROLE_ORIGIN_INFERRED,
    ROLE_ORIGIN_DEFAULT,
)

RELATIONSHIP_ORIGIN_EXPLICIT = "explicit"
RELATIONSHIP_ORIGIN_WORKSPACE_FILE = "workspace_file"
RELATIONSHIP_ORIGIN_LOCAL_PATH_REFERENCE = "local_path_reference"
RELATIONSHIP_ORIGIN_MANIFEST = "manifest"
RELATIONSHIP_ORIGIN_DISCOVERED = "discovered"
RELATIONSHIP_ORIGIN_INFERRED = "inferred"
RELATIONSHIP_ORIGINS = (
    RELATIONSHIP_ORIGIN_EXPLICIT,
    RELATIONSHIP_ORIGIN_WORKSPACE_FILE,
    RELATIONSHIP_ORIGIN_LOCAL_PATH_REFERENCE,
    RELATIONSHIP_ORIGIN_MANIFEST,
    RELATIONSHIP_ORIGIN_DISCOVERED,
    RELATIONSHIP_ORIGIN_INFERRED,
)

DIAGNOSTIC_SEVERITY_INFO = "info"
DIAGNOSTIC_SEVERITY_WARNING = "warning"
DIAGNOSTIC_SEVERITY_ERROR = "error"
DIAGNOSTIC_SEVERITIES = (
    DIAGNOSTIC_SEVERITY_INFO,
    DIAGNOSTIC_SEVERITY_WARNING,
    DIAGNOSTIC_SEVERITY_ERROR,
)

DIAGNOSTIC_UNKNOWN_REPOSITORY_REFERENCE = "unknown_repository_reference"
DIAGNOSTIC_CONFLICTING_EXPLICIT_RELATIONSHIP = "conflicting_explicit_relationship"
DIAGNOSTIC_CONFLICTING_INFERRED_RELATIONSHIP = "conflicting_inferred_relationship"
DIAGNOSTIC_CONFLICTING_ROLE_EVIDENCE = "conflicting_role_evidence"
DIAGNOSTIC_UNSUPPORTED_ROLE = "unsupported_role"
DIAGNOSTIC_UNSUPPORTED_RELATIONSHIP_TYPE = "unsupported_relationship_type"
DIAGNOSTIC_SELF_RELATIONSHIP = "self_relationship"
DIAGNOSTIC_DUPLICATE_RELATIONSHIP = "duplicate_relationship"
DIAGNOSTIC_RELATIONSHIP_EVIDENCE_TRUNCATED = "relationship_evidence_truncated"
DIAGNOSTIC_ROLE_EVIDENCE_TRUNCATED = "role_evidence_truncated"
DIAGNOSTIC_AMBIGUOUS_RELATIONSHIP_DIRECTION = "ambiguous_relationship_direction"
DIAGNOSTIC_MISSING_RELATIONSHIP_TARGET = "missing_relationship_target"
DIAGNOSTIC_RELATIONSHIP_CANDIDATE_CAP_REACHED = "relationship_candidate_cap_reached"
DIAGNOSTIC_DIAGNOSTIC_CAP_REACHED = "diagnostic_cap_reached"
DIAGNOSTIC_CODES = (
    DIAGNOSTIC_UNKNOWN_REPOSITORY_REFERENCE,
    DIAGNOSTIC_CONFLICTING_EXPLICIT_RELATIONSHIP,
    DIAGNOSTIC_CONFLICTING_INFERRED_RELATIONSHIP,
    DIAGNOSTIC_CONFLICTING_ROLE_EVIDENCE,
    DIAGNOSTIC_UNSUPPORTED_ROLE,
    DIAGNOSTIC_UNSUPPORTED_RELATIONSHIP_TYPE,
    DIAGNOSTIC_SELF_RELATIONSHIP,
    DIAGNOSTIC_DUPLICATE_RELATIONSHIP,
    DIAGNOSTIC_RELATIONSHIP_EVIDENCE_TRUNCATED,
    DIAGNOSTIC_ROLE_EVIDENCE_TRUNCATED,
    DIAGNOSTIC_AMBIGUOUS_RELATIONSHIP_DIRECTION,
    DIAGNOSTIC_MISSING_RELATIONSHIP_TARGET,
    DIAGNOSTIC_RELATIONSHIP_CANDIDATE_CAP_REACHED,
    DIAGNOSTIC_DIAGNOSTIC_CAP_REACHED,
)

EVIDENCE_FIELD_ORDER = (
    "signal_type",
    "source_repository_id",
    "source_path",
    "summary",
    "strength",
    "target_repository_id",
    "referenced_path",
    "metadata",
)
ROLE_ASSESSMENT_FIELD_ORDER = (
    "repository_id",
    "role",
    "origin",
    "confidence",
    "confidence_score",
    "evidence",
    "warnings",
    "suggested_role",
)
RELATIONSHIP_CANDIDATE_FIELD_ORDER = (
    "source_repository_id",
    "target_repository_id",
    "relationship_type",
    "origin",
    "confidence",
    "confidence_score",
    "evidence",
    "warnings",
    "description",
)
DIAGNOSTIC_FIELD_ORDER = (
    "code",
    "severity",
    "summary",
    "repository_ids",
    "relationship",
)
ASSESSMENT_FIELD_ORDER = (
    "role_assessments",
    "relationships",
    "diagnostics",
)

SYMMETRIC_RELATIONSHIP_TYPES = (
    workspace_config.RELATIONSHIP_TYPE_SHARES_CONTRACT_WITH,
)

ORIGIN_PRECEDENCE = {
    RELATIONSHIP_ORIGIN_EXPLICIT: 0,
    RELATIONSHIP_ORIGIN_WORKSPACE_FILE: 1,
    RELATIONSHIP_ORIGIN_LOCAL_PATH_REFERENCE: 2,
    RELATIONSHIP_ORIGIN_MANIFEST: 3,
    RELATIONSHIP_ORIGIN_DISCOVERED: 4,
    RELATIONSHIP_ORIGIN_INFERRED: 5,
}

EVIDENCE_STRENGTH_SCORE = {
    EVIDENCE_STRENGTH_WEAK: 0.25,
    EVIDENCE_STRENGTH_MEDIUM: 0.55,
    EVIDENCE_STRENGTH_STRONG: 0.8,
}


class WorkspaceRelationshipError(ValueError):
    """Raised when a Q3 relationship contract is invalid."""


def _validate_nonempty_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkspaceRelationshipError(f"{name} must be a non-empty string")
    if value != value.strip() or "\x00" in value:
        raise WorkspaceRelationshipError(f"{name} must not contain padding or null bytes")
    return value


def _validate_optional_string(value: Any, name: str) -> str | None:
    if value is None:
        return None
    return _validate_nonempty_string(value, name)


def _validate_choice(value: Any, name: str, choices: tuple[str, ...]) -> str:
    text = _validate_nonempty_string(value, name)
    if text not in choices:
        raise WorkspaceRelationshipError(f"{name} must be one of: {', '.join(choices)}")
    return text


def _validate_score(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized < 0.0 or normalized > 1.0:
        raise WorkspaceRelationshipError(f"{name} must be between 0.0 and 1.0")
    return round(normalized, 3)


def _confidence_from_score(score: float) -> str:
    if score >= 0.7:
        return CONFIDENCE_HIGH
    if score >= 0.4:
        return CONFIDENCE_MEDIUM
    return CONFIDENCE_LOW


def _normalize_path(value: Any, name: str) -> str:
    text = _validate_nonempty_string(value, name)
    windows_path = PureWindowsPath(text)
    posix_text = text.replace("\\", "/")
    posix_path = PurePosixPath(posix_text)
    if windows_path.drive or windows_path.is_absolute() or posix_path.is_absolute():
        raise WorkspaceRelationshipError(f"{name} must be relative")
    collapsed: list[str] = []
    for part in posix_path.parts:
        if part in ("", "."):
            continue
        if part == "..":
            if collapsed and collapsed[-1] != "..":
                collapsed.pop()
            else:
                collapsed.append(part)
            continue
        collapsed.append(part)
    return PurePosixPath(*collapsed).as_posix() if collapsed else "."


def _normalize_optional_path(value: Any, name: str) -> str | None:
    if value is None:
        return None
    return _normalize_path(value, name)


def _copy_json(value: Any, name: str) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise WorkspaceRelationshipError(f"{name} must be finite")
        return value
    if isinstance(value, Mapping):
        copied = {}
        for key in sorted(value):
            if not isinstance(key, str):
                raise WorkspaceRelationshipError(f"{name} keys must be strings")
            copied[key] = _copy_json(value[key], f"{name}.{key}")
        return copied
    if isinstance(value, (list, tuple)):
        return tuple(_copy_json(item, f"{name}[{index}]") for index, item in enumerate(value))
    raise WorkspaceRelationshipError(f"{name} must be JSON-ready")


def _json_ready(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, Mapping):
        return {key: _json_ready(value[key]) for key in sorted(value)}
    return value


def _validate_messages(value: Any, name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        raise TypeError(f"{name} must be an iterable of strings")
    try:
        messages = tuple(value)
    except TypeError as error:
        raise TypeError(f"{name} must be an iterable of strings") from error
    return tuple(_validate_nonempty_string(item, f"{name}[{index}]") for index, item in enumerate(messages))


@dataclass(frozen=True, slots=True)
class RelationshipEvidence:
    signal_type: str
    source_repository_id: str
    source_path: str
    summary: str
    strength: str
    target_repository_id: str | None = None
    referenced_path: str | None = None
    metadata: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "signal_type", _validate_nonempty_string(self.signal_type, "signal_type"))
        object.__setattr__(self, "source_repository_id", _validate_nonempty_string(self.source_repository_id, "source_repository_id"))
        object.__setattr__(self, "source_path", _normalize_path(self.source_path, "source_path"))
        object.__setattr__(self, "summary", _validate_nonempty_string(self.summary, "summary"))
        object.__setattr__(self, "strength", _validate_choice(self.strength, "strength", EVIDENCE_STRENGTHS))
        object.__setattr__(self, "target_repository_id", _validate_optional_string(self.target_repository_id, "target_repository_id"))
        object.__setattr__(self, "referenced_path", _normalize_optional_path(self.referenced_path, "referenced_path"))
        object.__setattr__(self, "metadata", _copy_json(self.metadata or {}, "metadata"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal_type": self.signal_type,
            "source_repository_id": self.source_repository_id,
            "source_path": self.source_path,
            "summary": self.summary,
            "strength": self.strength,
            "target_repository_id": self.target_repository_id,
            "referenced_path": self.referenced_path,
            "metadata": _json_ready(self.metadata or {}),
        }


@dataclass(frozen=True, slots=True)
class RepositoryRoleAssessment:
    repository_id: str
    role: str
    origin: str
    confidence: str
    confidence_score: float
    evidence: tuple[RelationshipEvidence, ...] = ()
    warnings: tuple[str, ...] = ()
    suggested_role: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "repository_id", _validate_nonempty_string(self.repository_id, "repository_id"))
        object.__setattr__(self, "role", _validate_choice(self.role, "role", workspace_config.REPOSITORY_ROLES))
        object.__setattr__(self, "origin", _validate_choice(self.origin, "origin", ROLE_ORIGINS))
        object.__setattr__(self, "confidence", _validate_choice(self.confidence, "confidence", CONFIDENCE_LEVELS))
        object.__setattr__(self, "confidence_score", _validate_score(self.confidence_score, "confidence_score"))
        object.__setattr__(self, "evidence", tuple(sorted((_coerce_evidence(item) for item in self.evidence), key=evidence_identity_key)))
        object.__setattr__(self, "warnings", _validate_messages(self.warnings, "warnings"))
        if self.suggested_role is not None:
            object.__setattr__(self, "suggested_role", _validate_choice(self.suggested_role, "suggested_role", workspace_config.REPOSITORY_ROLES))

    def to_dict(self) -> dict[str, Any]:
        return {
            "repository_id": self.repository_id,
            "role": self.role,
            "origin": self.origin,
            "confidence": self.confidence,
            "confidence_score": self.confidence_score,
            "evidence": [item.to_dict() for item in self.evidence],
            "warnings": list(self.warnings),
            "suggested_role": self.suggested_role,
        }


@dataclass(frozen=True, slots=True)
class RelationshipCandidate:
    source_repository_id: str
    target_repository_id: str
    relationship_type: str
    origin: str
    confidence: str
    confidence_score: float
    evidence: tuple[RelationshipEvidence, ...] = ()
    warnings: tuple[str, ...] = ()
    description: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_repository_id", _validate_nonempty_string(self.source_repository_id, "source_repository_id"))
        object.__setattr__(self, "target_repository_id", _validate_nonempty_string(self.target_repository_id, "target_repository_id"))
        if self.source_repository_id == self.target_repository_id:
            raise WorkspaceRelationshipError("relationship source and target must differ")
        object.__setattr__(self, "relationship_type", _validate_choice(self.relationship_type, "relationship_type", workspace_config.RELATIONSHIP_TYPES))
        object.__setattr__(self, "origin", _validate_choice(self.origin, "origin", RELATIONSHIP_ORIGINS))
        object.__setattr__(self, "confidence", _validate_choice(self.confidence, "confidence", CONFIDENCE_LEVELS))
        object.__setattr__(self, "confidence_score", _validate_score(self.confidence_score, "confidence_score"))
        object.__setattr__(self, "evidence", tuple(sorted((_coerce_evidence(item) for item in self.evidence), key=evidence_identity_key)))
        object.__setattr__(self, "warnings", _validate_messages(self.warnings, "warnings"))
        object.__setattr__(self, "description", _validate_optional_string(self.description, "description"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_repository_id": self.source_repository_id,
            "target_repository_id": self.target_repository_id,
            "relationship_type": self.relationship_type,
            "origin": self.origin,
            "confidence": self.confidence,
            "confidence_score": self.confidence_score,
            "evidence": [item.to_dict() for item in self.evidence],
            "warnings": list(self.warnings),
            "description": self.description,
        }


@dataclass(frozen=True, slots=True)
class WorkspaceRelationshipDiagnostic:
    code: str
    severity: str
    summary: str
    repository_ids: tuple[str, ...] = ()
    relationship: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", _validate_choice(self.code, "code", DIAGNOSTIC_CODES))
        object.__setattr__(self, "severity", _validate_choice(self.severity, "severity", DIAGNOSTIC_SEVERITIES))
        object.__setattr__(self, "summary", _validate_nonempty_string(self.summary, "summary"))
        object.__setattr__(self, "repository_ids", tuple(sorted(set(_validate_messages(self.repository_ids, "repository_ids")))))
        object.__setattr__(self, "relationship", _copy_json(self.relationship or {}, "relationship"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "summary": self.summary,
            "repository_ids": list(self.repository_ids),
            "relationship": _json_ready(self.relationship or {}),
        }


@dataclass(frozen=True, slots=True)
class WorkspaceRelationshipAssessment:
    role_assessments: tuple[RepositoryRoleAssessment, ...] = ()
    relationships: tuple[RelationshipCandidate, ...] = ()
    diagnostics: tuple[WorkspaceRelationshipDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "role_assessments", tuple(sorted((_coerce_role_assessment(item) for item in self.role_assessments), key=lambda item: item.repository_id)))
        object.__setattr__(self, "relationships", tuple(sorted((_coerce_relationship(item) for item in self.relationships), key=_relationship_sort_key)))
        object.__setattr__(self, "diagnostics", tuple(sorted((_coerce_diagnostic(item) for item in self.diagnostics), key=_diagnostic_sort_key)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "role_assessments": [item.to_dict() for item in self.role_assessments],
            "relationships": [item.to_dict() for item in self.relationships],
            "diagnostics": [item.to_dict() for item in self.diagnostics],
        }


def _coerce_evidence(value: Any) -> RelationshipEvidence:
    if isinstance(value, RelationshipEvidence):
        return value
    if isinstance(value, workspace_discovery.WorkspaceDiscoveryEvidence):
        return RelationshipEvidence(
            signal_type=value.signal_type,
            source_repository_id="discovery",
            source_path=value.source_path,
            summary=value.summary,
            strength=value.strength,
            referenced_path=value.referenced_path,
        )
    if not isinstance(value, Mapping):
        raise TypeError("evidence must be a RelationshipEvidence or mapping")
    return RelationshipEvidence(
        signal_type=value["signal_type"],
        source_repository_id=value["source_repository_id"],
        source_path=value.get("source_path", "."),
        summary=value["summary"],
        strength=value["strength"],
        target_repository_id=value.get("target_repository_id"),
        referenced_path=value.get("referenced_path"),
        metadata=value.get("metadata"),
    )


def _coerce_role_assessment(value: Any) -> RepositoryRoleAssessment:
    if isinstance(value, RepositoryRoleAssessment):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("role assessment must be a RepositoryRoleAssessment or mapping")
    return RepositoryRoleAssessment(
        repository_id=value["repository_id"],
        role=value["role"],
        origin=value["origin"],
        confidence=value["confidence"],
        confidence_score=value["confidence_score"],
        evidence=tuple(value.get("evidence", ())),
        warnings=tuple(value.get("warnings", ())),
        suggested_role=value.get("suggested_role"),
    )


def _coerce_relationship(value: Any) -> RelationshipCandidate:
    if isinstance(value, RelationshipCandidate):
        return value
    if isinstance(value, workspace_config.WorkspaceRelationship):
        return RelationshipCandidate(
            source_repository_id=value.source_repository_id,
            target_repository_id=value.target_repository_id,
            relationship_type=value.relationship_type,
            origin=RELATIONSHIP_ORIGIN_EXPLICIT,
            confidence=CONFIDENCE_HIGH,
            confidence_score=1.0,
            evidence=(),
            description=value.description,
        )
    if not isinstance(value, Mapping):
        raise TypeError("relationship must be a RelationshipCandidate or mapping")
    return RelationshipCandidate(
        source_repository_id=value["source_repository_id"],
        target_repository_id=value["target_repository_id"],
        relationship_type=value["relationship_type"],
        origin=value.get("origin", RELATIONSHIP_ORIGIN_INFERRED),
        confidence=value.get("confidence", CONFIDENCE_MEDIUM),
        confidence_score=value.get("confidence_score", 0.5),
        evidence=tuple(value.get("evidence", ())),
        warnings=tuple(value.get("warnings", ())),
        description=value.get("description"),
    )


def _coerce_diagnostic(value: Any) -> WorkspaceRelationshipDiagnostic:
    if isinstance(value, WorkspaceRelationshipDiagnostic):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("diagnostic must be a WorkspaceRelationshipDiagnostic or mapping")
    return WorkspaceRelationshipDiagnostic(
        code=value["code"],
        severity=value["severity"],
        summary=value["summary"],
        repository_ids=tuple(value.get("repository_ids", ())),
        relationship=value.get("relationship"),
    )


def evidence_identity_key(evidence: RelationshipEvidence) -> tuple[object, ...]:
    item = _coerce_evidence(evidence)
    return (
        item.signal_type,
        item.source_repository_id,
        item.source_path,
        item.summary,
        item.strength,
        item.target_repository_id or "",
        item.referenced_path or "",
        json.dumps(_json_ready(item.metadata or {}), sort_keys=True),
    )


def relationship_identity_key(relationship: RelationshipCandidate | Mapping[str, Any]) -> tuple[str, str, str]:
    item = _coerce_relationship(relationship)
    source = item.source_repository_id
    target = item.target_repository_id
    if item.relationship_type in SYMMETRIC_RELATIONSHIP_TYPES and target < source:
        source, target = target, source
    return (source, target, item.relationship_type)


def _directional_pair_key(relationship: RelationshipCandidate) -> tuple[str, str]:
    return (relationship.source_repository_id, relationship.target_repository_id)


def _relationship_sort_key(relationship: RelationshipCandidate) -> tuple[object, ...]:
    return (
        ORIGIN_PRECEDENCE[relationship.origin],
        relationship.source_repository_id,
        relationship.target_repository_id,
        workspace_config.RELATIONSHIP_TYPES.index(relationship.relationship_type),
        -relationship.confidence_score,
        relationship.description or "",
    )


def _diagnostic_sort_key(diagnostic: WorkspaceRelationshipDiagnostic) -> tuple[object, ...]:
    return (
        diagnostic.code,
        diagnostic.severity,
        diagnostic.repository_ids,
        json.dumps(_json_ready(diagnostic.relationship or {}), sort_keys=True),
        diagnostic.summary,
    )


def _diagnostic(
    code: str,
    severity: str,
    summary: str,
    *,
    repository_ids: Iterable[str] = (),
    relationship: Mapping[str, Any] | None = None,
) -> WorkspaceRelationshipDiagnostic:
    return WorkspaceRelationshipDiagnostic(
        code=code,
        severity=severity,
        summary=summary,
        repository_ids=tuple(repository_ids),
        relationship=relationship,
    )


def _validate_limit(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 1:
        raise WorkspaceRelationshipError(f"{name} must be at least 1")
    return value


def _dedupe_evidence(evidence: Iterable[RelationshipEvidence]) -> tuple[RelationshipEvidence, ...]:
    values = tuple(_coerce_evidence(item) for item in evidence)
    deduped = {evidence_identity_key(item): item for item in values}
    return tuple(deduped[key] for key in sorted(deduped))


def _bounded_evidence(
    evidence: Iterable[RelationshipEvidence],
    limit: int,
    diagnostic_code: str,
    diagnostic_summary: str,
    *,
    repository_ids: Iterable[str] = (),
    relationship: Mapping[str, Any] | None = None,
) -> tuple[tuple[RelationshipEvidence, ...], tuple[WorkspaceRelationshipDiagnostic, ...], int]:
    deduped = _dedupe_evidence(evidence)
    if len(deduped) <= limit:
        return deduped, (), 0
    omitted = len(deduped) - limit
    diagnostic = _diagnostic(
        diagnostic_code,
        DIAGNOSTIC_SEVERITY_INFO,
        diagnostic_summary,
        repository_ids=repository_ids,
        relationship={**(relationship or {}), "omitted": omitted, "limit": limit},
    )
    return deduped[:limit], (diagnostic,), omitted


def _score_for_origin(origin: str, evidence: tuple[RelationshipEvidence, ...]) -> float:
    if origin == RELATIONSHIP_ORIGIN_EXPLICIT:
        return 1.0
    if not evidence:
        return 0.25
    score = max(EVIDENCE_STRENGTH_SCORE[item.strength] for item in evidence)
    if all(item.strength == EVIDENCE_STRENGTH_WEAK for item in evidence):
        score = min(score, 0.35)
    if origin in {RELATIONSHIP_ORIGIN_WORKSPACE_FILE, RELATIONSHIP_ORIGIN_LOCAL_PATH_REFERENCE}:
        score = max(score, 0.75)
    return round(min(score, 0.95), 3)


def _role_score(origin: str, evidence: tuple[RelationshipEvidence, ...], role: str) -> float:
    if origin == ROLE_ORIGIN_EXPLICIT:
        return 1.0
    if role == workspace_config.REPOSITORY_ROLE_UNKNOWN:
        return 0.1
    if not evidence:
        return 0.25
    score = max(EVIDENCE_STRENGTH_SCORE[item.strength] for item in evidence)
    if all(item.strength == EVIDENCE_STRENGTH_WEAK for item in evidence):
        score = min(score, 0.35)
    return round(min(score, 0.9), 3)


def _repository_by_id(workspace: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {repository["id"]: repository for repository in workspace["repositories"]}


def _normalize_workspace(workspace: Any) -> dict[str, Any]:
    return workspace_config.validate_workspace_config(workspace)


def _discovery_to_dict(discovery_result: Any) -> dict[str, Any] | None:
    if discovery_result is None:
        return None
    if isinstance(discovery_result, workspace_discovery.WorkspaceDiscoveryResult):
        return discovery_result.to_dict()
    if isinstance(discovery_result, Mapping):
        return dict(discovery_result)
    raise TypeError("discovery_result must be a WorkspaceDiscoveryResult, mapping, or None")


def _current_repository_id(workspace: Mapping[str, Any], current_repository_id: str | None) -> str | None:
    if current_repository_id:
        return current_repository_id
    repositories = workspace["repositories"]
    for repository in repositories:
        if repository["path"] == ".":
            return repository["id"]
    return repositories[0]["id"] if repositories else None


def _role_evidence(repository_id: str, role: str, origin: str, summary: str, strength: str) -> RelationshipEvidence:
    return RelationshipEvidence(
        signal_type=f"role_{origin}",
        source_repository_id=repository_id,
        source_path=".",
        summary=summary,
        strength=strength,
        target_repository_id=repository_id,
        metadata={"role": role},
    )


def _relationship_evidence(
    source_repository_id: str,
    target_repository_id: str,
    signal_type: str,
    summary: str,
    strength: str,
    *,
    source_path: str = ".",
    referenced_path: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> RelationshipEvidence:
    return RelationshipEvidence(
        signal_type=signal_type,
        source_repository_id=source_repository_id,
        source_path=source_path,
        summary=summary,
        strength=strength,
        target_repository_id=target_repository_id,
        referenced_path=referenced_path,
        metadata=metadata or {},
    )


def _relationship_summary(relationship: RelationshipCandidate) -> dict[str, Any]:
    return {
        "source_repository_id": relationship.source_repository_id,
        "target_repository_id": relationship.target_repository_id,
        "relationship_type": relationship.relationship_type,
    }


def _discovery_signal_to_origin(signal_type: str) -> str:
    if signal_type == workspace_discovery.SIGNAL_WORKSPACE_FILE_MEMBERSHIP:
        return RELATIONSHIP_ORIGIN_WORKSPACE_FILE
    if signal_type == workspace_discovery.SIGNAL_LOCAL_PATH_REFERENCE:
        return RELATIONSHIP_ORIGIN_LOCAL_PATH_REFERENCE
    if signal_type == workspace_discovery.SIGNAL_PROJECT_MANIFEST:
        return RELATIONSHIP_ORIGIN_MANIFEST
    return RELATIONSHIP_ORIGIN_DISCOVERED


def _discovery_signal_to_relationship_type(signal_type: str) -> str | None:
    if signal_type == workspace_discovery.SIGNAL_LOCAL_PATH_REFERENCE:
        return workspace_config.RELATIONSHIP_TYPE_IMPORTS_PACKAGE
    if signal_type in {
        workspace_discovery.SIGNAL_WORKSPACE_FILE_MEMBERSHIP,
        workspace_discovery.SIGNAL_DOCKER_COMPOSE_BUILD_CONTEXT,
    }:
        return workspace_config.RELATIONSHIP_TYPE_DEPENDS_ON
    return None


def _discovery_strength(strength: str) -> str:
    if strength in EVIDENCE_STRENGTHS:
        return strength
    return EVIDENCE_STRENGTH_WEAK


def _evidence_from_discovery(
    evidence: Mapping[str, Any],
    source_repository_id: str,
    target_repository_id: str,
) -> RelationshipEvidence:
    return _relationship_evidence(
        source_repository_id,
        target_repository_id,
        str(evidence.get("signal_type", "discovery")),
        str(evidence.get("summary", "Discovery evidence.")),
        _discovery_strength(str(evidence.get("strength", EVIDENCE_STRENGTH_WEAK))),
        source_path=str(evidence.get("source_path", ".")),
        referenced_path=evidence.get("referenced_path"),
    )


def _relationships_from_discovery(
    discovery_result: dict[str, Any] | None,
    source_repository_id: str | None,
) -> tuple[RelationshipCandidate, ...]:
    if discovery_result is None or source_repository_id is None:
        return ()
    relationships: list[RelationshipCandidate] = []
    for candidate in discovery_result.get("candidates", ()):
        target_repository_id = str(candidate.get("suggested_id", "")).strip()
        if not target_repository_id:
            continue
        for evidence in candidate.get("evidence", ()):
            signal_type = str(evidence.get("signal_type", ""))
            relationship_type = _discovery_signal_to_relationship_type(signal_type)
            if relationship_type is None:
                continue
            origin = _discovery_signal_to_origin(signal_type)
            relationship_evidence = _evidence_from_discovery(
                evidence,
                source_repository_id,
                target_repository_id,
            )
            score = _score_for_origin(origin, (relationship_evidence,))
            relationships.append(
                RelationshipCandidate(
                    source_repository_id=source_repository_id,
                    target_repository_id=target_repository_id,
                    relationship_type=relationship_type,
                    origin=origin,
                    confidence=_confidence_from_score(score),
                    confidence_score=score,
                    evidence=(relationship_evidence,),
                    description="Relationship suggested from repository discovery evidence.",
                )
            )
    return tuple(relationships)


def _role_assessments(
    workspace: Mapping[str, Any],
    discovery_result: dict[str, Any] | None,
    max_role_evidence: int,
) -> tuple[tuple[RepositoryRoleAssessment, ...], tuple[WorkspaceRelationshipDiagnostic, ...]]:
    diagnostics: list[WorkspaceRelationshipDiagnostic] = []
    assessments: dict[str, RepositoryRoleAssessment] = {}
    repositories = _repository_by_id(workspace)

    discovered_roles: dict[str, tuple[str, tuple[RelationshipEvidence, ...]]] = {}
    if discovery_result is not None:
        for candidate in discovery_result.get("candidates", ()):
            repository_id = str(candidate.get("suggested_id", "")).strip()
            role = str(candidate.get("probable_role", workspace_config.REPOSITORY_ROLE_UNKNOWN))
            if not repository_id:
                continue
            if role not in workspace_config.REPOSITORY_ROLES:
                diagnostics.append(
                    _diagnostic(
                        DIAGNOSTIC_UNSUPPORTED_ROLE,
                        DIAGNOSTIC_SEVERITY_WARNING,
                        "Discovery suggested an unsupported repository role.",
                        repository_ids=(repository_id,),
                        relationship={"role": role},
                    )
                )
                continue
            evidence_items = tuple(
                _evidence_from_discovery(item, repository_id, repository_id)
                for item in candidate.get("evidence", ())
            )
            discovered_roles[repository_id] = (role, evidence_items)

    for repository_id in sorted(repositories):
        repository = repositories[repository_id]
        configured_role = repository["role"]
        discovered = discovered_roles.get(repository_id)
        suggested_role = discovered[0] if discovered else None
        role_evidence = (
            _role_evidence(
                repository_id,
                configured_role,
                ROLE_ORIGIN_EXPLICIT,
                "Repository role is configured explicitly.",
                EVIDENCE_STRENGTH_STRONG,
            ),
        )
        if discovered and configured_role == workspace_config.REPOSITORY_ROLE_UNKNOWN:
            role_evidence = (*role_evidence, *discovered[1])
        elif discovered and suggested_role not in {None, configured_role, workspace_config.REPOSITORY_ROLE_UNKNOWN}:
            diagnostics.append(
                _diagnostic(
                    DIAGNOSTIC_CONFLICTING_ROLE_EVIDENCE,
                    DIAGNOSTIC_SEVERITY_WARNING,
                    "Discovered role evidence conflicts with explicit configured role.",
                    repository_ids=(repository_id,),
                    relationship={"explicit_role": configured_role, "suggested_role": suggested_role},
                )
            )
        bounded, cap_diagnostics, omitted = _bounded_evidence(
            role_evidence,
            max_role_evidence,
            DIAGNOSTIC_ROLE_EVIDENCE_TRUNCATED,
            "Role evidence was truncated.",
            repository_ids=(repository_id,),
        )
        diagnostics.extend(cap_diagnostics)
        role = configured_role
        origin = ROLE_ORIGIN_EXPLICIT
        score = 1.0
        if configured_role == workspace_config.REPOSITORY_ROLE_UNKNOWN and discovered and suggested_role != workspace_config.REPOSITORY_ROLE_UNKNOWN:
            origin = ROLE_ORIGIN_DISCOVERED
            score = _role_score(origin, bounded, suggested_role)
            role = configured_role
        elif configured_role == workspace_config.REPOSITORY_ROLE_UNKNOWN:
            origin = ROLE_ORIGIN_DEFAULT
            score = 0.1
        assessment = RepositoryRoleAssessment(
            repository_id=repository_id,
            role=role,
            origin=origin,
            confidence=_confidence_from_score(score),
            confidence_score=score,
            evidence=bounded,
            warnings=((f"role evidence cap reached; omitted {omitted} item(s).",) if omitted else ()),
            suggested_role=(suggested_role if configured_role == workspace_config.REPOSITORY_ROLE_UNKNOWN and suggested_role != workspace_config.REPOSITORY_ROLE_UNKNOWN else None),
        )
        assessments[repository_id] = assessment

    for repository_id in sorted(set(discovered_roles) - set(repositories)):
        role, evidence_items = discovered_roles[repository_id]
        bounded, cap_diagnostics, omitted = _bounded_evidence(
            evidence_items,
            max_role_evidence,
            DIAGNOSTIC_ROLE_EVIDENCE_TRUNCATED,
            "Role evidence was truncated.",
            repository_ids=(repository_id,),
        )
        diagnostics.extend(cap_diagnostics)
        score = _role_score(ROLE_ORIGIN_DISCOVERED, bounded, role)
        assessments[repository_id] = RepositoryRoleAssessment(
            repository_id=repository_id,
            role=role,
            origin=ROLE_ORIGIN_DISCOVERED if role != workspace_config.REPOSITORY_ROLE_UNKNOWN else ROLE_ORIGIN_DEFAULT,
            confidence=_confidence_from_score(score),
            confidence_score=score,
            evidence=bounded,
            warnings=((f"role evidence cap reached; omitted {omitted} item(s).",) if omitted else ()),
        )

    return tuple(assessments[key] for key in sorted(assessments)), tuple(diagnostics)


def _validate_relationship_references(
    relationships: Iterable[RelationshipCandidate],
    repository_ids: set[str],
) -> tuple[RelationshipCandidate, ...]:
    valid = []
    for relationship in relationships:
        if relationship.source_repository_id in repository_ids and relationship.target_repository_id in repository_ids:
            valid.append(relationship)
    return tuple(valid)


def _reference_diagnostics(
    relationships: Iterable[RelationshipCandidate],
    repository_ids: set[str],
) -> tuple[WorkspaceRelationshipDiagnostic, ...]:
    diagnostics = []
    for relationship in relationships:
        missing = [
            repository_id
            for repository_id in (relationship.source_repository_id, relationship.target_repository_id)
            if repository_id not in repository_ids
        ]
        if missing:
            diagnostics.append(
                _diagnostic(
                    DIAGNOSTIC_UNKNOWN_REPOSITORY_REFERENCE,
                    DIAGNOSTIC_SEVERITY_ERROR,
                    "Relationship references an unknown repository.",
                    repository_ids=missing,
                    relationship=_relationship_summary(relationship),
                )
            )
    return tuple(diagnostics)


def _merge_relationships(
    relationships: Iterable[RelationshipCandidate],
    repository_ids: set[str],
    max_evidence_per_relationship: int,
    max_relationships: int,
) -> tuple[tuple[RelationshipCandidate, ...], tuple[WorkspaceRelationshipDiagnostic, ...]]:
    diagnostics: list[WorkspaceRelationshipDiagnostic] = list(_reference_diagnostics(relationships, repository_ids))
    valid = _validate_relationship_references(relationships, repository_ids)
    by_identity: dict[tuple[str, str, str], RelationshipCandidate] = {}
    pair_types: dict[tuple[str, str], str] = {}
    pair_origins: dict[tuple[str, str], str] = {}
    directional_identities: set[tuple[str, str, str]] = set()

    for relationship in sorted(valid, key=_relationship_sort_key):
        reverse_directional = (
            relationship.target_repository_id,
            relationship.source_repository_id,
            relationship.relationship_type,
        )
        if (
            relationship.relationship_type not in SYMMETRIC_RELATIONSHIP_TYPES
            and reverse_directional in directional_identities
        ):
            diagnostics.append(
                _diagnostic(
                    DIAGNOSTIC_AMBIGUOUS_RELATIONSHIP_DIRECTION,
                    DIAGNOSTIC_SEVERITY_INFO,
                    "Opposite-direction relationship evidence was kept distinct.",
                    repository_ids=(relationship.source_repository_id, relationship.target_repository_id),
                    relationship=_relationship_summary(relationship),
                )
            )
        directional_identities.add(
            (
                relationship.source_repository_id,
                relationship.target_repository_id,
                relationship.relationship_type,
            )
        )

        pair_key = _directional_pair_key(relationship)
        previous_type = pair_types.get(pair_key)
        if previous_type is None:
            pair_types[pair_key] = relationship.relationship_type
            pair_origins[pair_key] = relationship.origin
        elif previous_type != relationship.relationship_type:
            diagnostics.append(
                _diagnostic(
                    DIAGNOSTIC_CONFLICTING_INFERRED_RELATIONSHIP
                    if relationship.origin != RELATIONSHIP_ORIGIN_EXPLICIT
                    else DIAGNOSTIC_CONFLICTING_EXPLICIT_RELATIONSHIP,
                    DIAGNOSTIC_SEVERITY_WARNING,
                    "Relationship evidence conflicts on relationship type for the same direction.",
                    repository_ids=pair_key,
                    relationship=_relationship_summary(relationship),
                )
            )
            if pair_origins.get(pair_key) == RELATIONSHIP_ORIGIN_EXPLICIT and relationship.origin != RELATIONSHIP_ORIGIN_EXPLICIT:
                continue

        identity = relationship_identity_key(relationship)
        existing = by_identity.get(identity)
        if existing is None:
            bounded, cap_diagnostics, omitted = _bounded_evidence(
                relationship.evidence,
                max_evidence_per_relationship,
                DIAGNOSTIC_RELATIONSHIP_EVIDENCE_TRUNCATED,
                "Relationship evidence was truncated.",
                repository_ids=(relationship.source_repository_id, relationship.target_repository_id),
                relationship=_relationship_summary(relationship),
            )
            diagnostics.extend(cap_diagnostics)
            warnings = relationship.warnings
            if omitted:
                warnings = (*warnings, f"relationship evidence cap reached; omitted {omitted} item(s).")
            by_identity[identity] = RelationshipCandidate(
                source_repository_id=relationship.source_repository_id,
                target_repository_id=relationship.target_repository_id,
                relationship_type=relationship.relationship_type,
                origin=relationship.origin,
                confidence=relationship.confidence,
                confidence_score=relationship.confidence_score,
                evidence=bounded,
                warnings=tuple(sorted(set(warnings))),
                description=relationship.description,
            )
            continue

        diagnostics.append(
            _diagnostic(
                DIAGNOSTIC_DUPLICATE_RELATIONSHIP,
                DIAGNOSTIC_SEVERITY_INFO,
                "Duplicate relationship identity was merged.",
                repository_ids=(relationship.source_repository_id, relationship.target_repository_id),
                relationship=_relationship_summary(relationship),
            )
        )
        origin = existing.origin
        confidence_score = existing.confidence_score
        confidence = existing.confidence
        description = existing.description
        if ORIGIN_PRECEDENCE[relationship.origin] < ORIGIN_PRECEDENCE[existing.origin]:
            origin = relationship.origin
            confidence_score = relationship.confidence_score
            confidence = relationship.confidence
            description = relationship.description or existing.description
        elif relationship.origin == RELATIONSHIP_ORIGIN_EXPLICIT and existing.origin == RELATIONSHIP_ORIGIN_EXPLICIT:
            confidence_score = 1.0
            confidence = CONFIDENCE_HIGH
        evidence = _dedupe_evidence((*existing.evidence, *relationship.evidence))
        bounded, cap_diagnostics, omitted = _bounded_evidence(
            evidence,
            max_evidence_per_relationship,
            DIAGNOSTIC_RELATIONSHIP_EVIDENCE_TRUNCATED,
            "Relationship evidence was truncated.",
            repository_ids=(existing.source_repository_id, existing.target_repository_id),
            relationship=_relationship_summary(existing),
        )
        diagnostics.extend(cap_diagnostics)
        warnings = (*existing.warnings, *relationship.warnings)
        if omitted:
            warnings = (*warnings, f"relationship evidence cap reached; omitted {omitted} item(s).")
        by_identity[identity] = RelationshipCandidate(
            source_repository_id=existing.source_repository_id,
            target_repository_id=existing.target_repository_id,
            relationship_type=existing.relationship_type,
            origin=origin,
            confidence=confidence,
            confidence_score=confidence_score,
            evidence=bounded,
            warnings=tuple(sorted(set(warnings))),
            description=description,
        )

    ordered = tuple(sorted(by_identity.values(), key=_relationship_sort_key))
    if len(ordered) > max_relationships:
        omitted = len(ordered) - max_relationships
        diagnostics.append(
            _diagnostic(
                DIAGNOSTIC_RELATIONSHIP_CANDIDATE_CAP_REACHED,
                DIAGNOSTIC_SEVERITY_WARNING,
                "Relationship candidate cap was reached.",
                relationship={"limit": max_relationships, "omitted": omitted},
            )
        )
        ordered = ordered[:max_relationships]
    return ordered, tuple(diagnostics)


def _explicit_relationships(workspace: Mapping[str, Any]) -> tuple[RelationshipCandidate, ...]:
    relationships = []
    for relationship in workspace.get("relationships", ()):
        evidence = _relationship_evidence(
            relationship["source_repository_id"],
            relationship["target_repository_id"],
            "explicit_configuration",
            "Relationship is configured explicitly.",
            EVIDENCE_STRENGTH_STRONG,
            metadata={"origin": RELATIONSHIP_ORIGIN_EXPLICIT},
        )
        relationships.append(
            RelationshipCandidate(
                source_repository_id=relationship["source_repository_id"],
                target_repository_id=relationship["target_repository_id"],
                relationship_type=relationship["relationship_type"],
                origin=RELATIONSHIP_ORIGIN_EXPLICIT,
                confidence=CONFIDENCE_HIGH,
                confidence_score=1.0,
                evidence=(evidence,),
                description=relationship.get("description"),
            )
        )
    return tuple(relationships)


def _inferred_relationships(
    values: Iterable[Any],
) -> tuple[tuple[RelationshipCandidate, ...], tuple[WorkspaceRelationshipDiagnostic, ...]]:
    relationships: list[RelationshipCandidate] = []
    diagnostics: list[WorkspaceRelationshipDiagnostic] = []
    for value in values:
        if isinstance(value, Mapping):
            source = str(value.get("source_repository_id", "")).strip()
            target = str(value.get("target_repository_id", "")).strip()
            relationship_type = str(value.get("relationship_type", "")).strip()
            if not target:
                diagnostics.append(
                    _diagnostic(
                        DIAGNOSTIC_MISSING_RELATIONSHIP_TARGET,
                        DIAGNOSTIC_SEVERITY_ERROR,
                        "Inferred relationship is missing a target repository.",
                        repository_ids=(source,) if source else (),
                        relationship={"source_repository_id": source},
                    )
                )
                continue
            if source and source == target:
                diagnostics.append(
                    _diagnostic(
                        DIAGNOSTIC_SELF_RELATIONSHIP,
                        DIAGNOSTIC_SEVERITY_ERROR,
                        "Inferred relationship source and target are identical.",
                        repository_ids=(source,),
                        relationship={"source_repository_id": source, "target_repository_id": target},
                    )
                )
                continue
            if relationship_type not in workspace_config.RELATIONSHIP_TYPES:
                diagnostics.append(
                    _diagnostic(
                        DIAGNOSTIC_UNSUPPORTED_RELATIONSHIP_TYPE,
                        DIAGNOSTIC_SEVERITY_ERROR,
                        "Inferred relationship uses an unsupported relationship type.",
                        repository_ids=tuple(item for item in (source, target) if item),
                        relationship={
                            "source_repository_id": source,
                            "target_repository_id": target,
                            "relationship_type": relationship_type,
                        },
                    )
                )
                continue
        try:
            relationships.append(_coerce_relationship(value))
        except WorkspaceRelationshipError as error:
            diagnostics.append(
                _diagnostic(
                    DIAGNOSTIC_UNSUPPORTED_RELATIONSHIP_TYPE,
                    DIAGNOSTIC_SEVERITY_ERROR,
                    str(error),
                )
            )
    return tuple(relationships), tuple(diagnostics)


def _bound_diagnostics(
    diagnostics: Iterable[WorkspaceRelationshipDiagnostic],
    max_diagnostics: int,
) -> tuple[WorkspaceRelationshipDiagnostic, ...]:
    values = tuple(sorted((_coerce_diagnostic(item) for item in diagnostics), key=_diagnostic_sort_key))
    if len(values) <= max_diagnostics:
        return values
    omitted = len(values) - max_diagnostics
    cap = _diagnostic(
        DIAGNOSTIC_DIAGNOSTIC_CAP_REACHED,
        DIAGNOSTIC_SEVERITY_WARNING,
        "Workspace relationship diagnostics were truncated.",
        relationship={"limit": max_diagnostics, "omitted": omitted},
    )
    return (*values[: max_diagnostics - 1], cap)


def build_workspace_relationship_assessment(
    workspace: Any,
    *,
    discovery_result: Any = None,
    inferred_relationships: Iterable[Any] = (),
    current_repository_id: str | None = None,
    max_role_evidence: int = DEFAULT_MAX_ROLE_EVIDENCE,
    max_evidence_per_relationship: int = DEFAULT_MAX_RELATIONSHIP_EVIDENCE,
    max_relationships: int = DEFAULT_MAX_RELATIONSHIPS,
    max_diagnostics: int = DEFAULT_MAX_DIAGNOSTICS,
) -> WorkspaceRelationshipAssessment:
    """Merge configured and inferred workspace role/relationship information."""

    max_role_evidence = _validate_limit(max_role_evidence, "max_role_evidence")
    max_evidence_per_relationship = _validate_limit(max_evidence_per_relationship, "max_evidence_per_relationship")
    max_relationships = _validate_limit(max_relationships, "max_relationships")
    max_diagnostics = _validate_limit(max_diagnostics, "max_diagnostics")
    normalized_workspace = _normalize_workspace(workspace)
    repository_ids = {repository["id"] for repository in normalized_workspace["repositories"]}
    normalized_discovery = _discovery_to_dict(discovery_result)
    source_repository_id = _current_repository_id(normalized_workspace, current_repository_id)

    roles, role_diagnostics = _role_assessments(
        normalized_workspace,
        normalized_discovery,
        max_role_evidence,
    )
    inferred, inferred_diagnostics = _inferred_relationships(inferred_relationships)
    relationships, relationship_diagnostics = _merge_relationships(
        (
            *_explicit_relationships(normalized_workspace),
            *_relationships_from_discovery(normalized_discovery, source_repository_id),
            *inferred,
        ),
        repository_ids | {role.repository_id for role in roles},
        max_evidence_per_relationship,
        max_relationships,
    )
    diagnostics = _bound_diagnostics(
        (*role_diagnostics, *inferred_diagnostics, *relationship_diagnostics),
        max_diagnostics,
    )
    return WorkspaceRelationshipAssessment(
        role_assessments=roles,
        relationships=relationships,
        diagnostics=diagnostics,
    )


def workspace_relationship_assessment_to_dict(
    assessment: WorkspaceRelationshipAssessment,
) -> dict[str, Any]:
    """Return the stable JSON-ready workspace relationship assessment."""

    if not isinstance(assessment, WorkspaceRelationshipAssessment):
        raise TypeError("assessment must be a WorkspaceRelationshipAssessment")
    return assessment.to_dict()
