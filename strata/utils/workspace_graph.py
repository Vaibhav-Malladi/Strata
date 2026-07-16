"""Deterministic workspace dependency graph contracts for Q6.

This module combines already-produced workspace intelligence. It does not read
files, scan repositories, run discovery, extract references, compare shared
contracts, write graph files, print output, or add AI context.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import json
import math
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any

import strata.utils.workspace_config as workspace_config
import strata.utils.workspace_contracts as workspace_contracts
import strata.utils.workspace_discovery as workspace_discovery
import strata.utils.workspace_relationships as workspace_relationships


WORKSPACE_GRAPH_SCHEMA_VERSION = 1

DEFAULT_MAX_NODES = 100
DEFAULT_MAX_EDGES = 500
DEFAULT_MAX_EVIDENCE_PER_NODE = 8
DEFAULT_MAX_EVIDENCE_PER_EDGE = 12
DEFAULT_MAX_CONTRACT_NAMES_PER_EDGE = 20
DEFAULT_MAX_UNRESOLVED_RELATIONSHIPS = 200
DEFAULT_MAX_DIAGNOSTICS = 200
DEFAULT_MAX_STRONGLY_CONNECTED_COMPONENTS = 100
DEFAULT_MAX_CYCLES = 100

CONFIDENCE_LOW = "low"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_HIGH = "high"
CONFIDENCE_LEVELS = (
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    CONFIDENCE_HIGH,
)

DIAGNOSTIC_SEVERITY_INFO = "info"
DIAGNOSTIC_SEVERITY_WARNING = "warning"
DIAGNOSTIC_SEVERITY_ERROR = "error"
DIAGNOSTIC_SEVERITIES = (
    DIAGNOSTIC_SEVERITY_INFO,
    DIAGNOSTIC_SEVERITY_WARNING,
    DIAGNOSTIC_SEVERITY_ERROR,
)

UNRESOLVED_SOURCE_REPOSITORY_MISSING = "source_repository_missing"
UNRESOLVED_TARGET_REPOSITORY_MISSING = "target_repository_missing"
UNRESOLVED_BOTH_REPOSITORIES_MISSING = "both_repositories_missing"
UNRESOLVED_AMBIGUOUS_TARGET = "ambiguous_target"
UNRESOLVED_UNSUPPORTED_RELATIONSHIP_TYPE = "unsupported_relationship_type"
UNRESOLVED_SELF_RELATIONSHIP = "self_relationship"
UNRESOLVED_EDGE_CAP_REACHED = "edge_cap_reached"
UNRESOLVED_REASONS = (
    UNRESOLVED_SOURCE_REPOSITORY_MISSING,
    UNRESOLVED_TARGET_REPOSITORY_MISSING,
    UNRESOLVED_BOTH_REPOSITORIES_MISSING,
    UNRESOLVED_AMBIGUOUS_TARGET,
    UNRESOLVED_UNSUPPORTED_RELATIONSHIP_TYPE,
    UNRESOLVED_SELF_RELATIONSHIP,
    UNRESOLVED_EDGE_CAP_REACHED,
)

DIAGNOSTIC_GRAPH_NODE_CAP_REACHED = "graph_node_cap_reached"
DIAGNOSTIC_GRAPH_EDGE_CAP_REACHED = "graph_edge_cap_reached"
DIAGNOSTIC_GRAPH_EVIDENCE_TRUNCATED = "graph_evidence_truncated"
DIAGNOSTIC_GRAPH_DIAGNOSTIC_CAP_REACHED = "graph_diagnostic_cap_reached"
DIAGNOSTIC_DUPLICATE_REPOSITORY_ID = "duplicate_repository_id"
DIAGNOSTIC_DUPLICATE_REPOSITORY_PATH = "duplicate_repository_path"
DIAGNOSTIC_UNKNOWN_EDGE_SOURCE = "unknown_edge_source"
DIAGNOSTIC_UNKNOWN_EDGE_TARGET = "unknown_edge_target"
DIAGNOSTIC_UNKNOWN_EDGE_REPOSITORIES = "unknown_edge_repositories"
DIAGNOSTIC_SELF_RELATIONSHIP_REJECTED = "self_relationship_rejected"
DIAGNOSTIC_UNSUPPORTED_RELATIONSHIP_TYPE = "unsupported_relationship_type"
DIAGNOSTIC_CONFLICTING_EXPLICIT_EDGE = "conflicting_explicit_edge"
DIAGNOSTIC_CONFLICTING_NODE_ROLE = "conflicting_node_role"
DIAGNOSTIC_AMBIGUOUS_DISCOVERY_IDENTITY = "ambiguous_discovery_identity"
DIAGNOSTIC_CYCLE_DETECTED = "cycle_detected"
DIAGNOSTIC_STRONGLY_CONNECTED_COMPONENT_DETECTED = "strongly_connected_component_detected"
DIAGNOSTIC_ISOLATED_REPOSITORY = "isolated_repository"
DIAGNOSTIC_CONTRACT_EDGE_DEGRADED = "contract_edge_degraded"
DIAGNOSTIC_SENSITIVE_CONTRACT_METADATA_REDACTED = "sensitive_contract_metadata_redacted"
DIAGNOSTIC_CODES = (
    DIAGNOSTIC_GRAPH_NODE_CAP_REACHED,
    DIAGNOSTIC_GRAPH_EDGE_CAP_REACHED,
    DIAGNOSTIC_GRAPH_EVIDENCE_TRUNCATED,
    DIAGNOSTIC_GRAPH_DIAGNOSTIC_CAP_REACHED,
    DIAGNOSTIC_DUPLICATE_REPOSITORY_ID,
    DIAGNOSTIC_DUPLICATE_REPOSITORY_PATH,
    DIAGNOSTIC_UNKNOWN_EDGE_SOURCE,
    DIAGNOSTIC_UNKNOWN_EDGE_TARGET,
    DIAGNOSTIC_UNKNOWN_EDGE_REPOSITORIES,
    DIAGNOSTIC_SELF_RELATIONSHIP_REJECTED,
    DIAGNOSTIC_UNSUPPORTED_RELATIONSHIP_TYPE,
    DIAGNOSTIC_CONFLICTING_EXPLICIT_EDGE,
    DIAGNOSTIC_CONFLICTING_NODE_ROLE,
    DIAGNOSTIC_AMBIGUOUS_DISCOVERY_IDENTITY,
    DIAGNOSTIC_CYCLE_DETECTED,
    DIAGNOSTIC_STRONGLY_CONNECTED_COMPONENT_DETECTED,
    DIAGNOSTIC_ISOLATED_REPOSITORY,
    DIAGNOSTIC_CONTRACT_EDGE_DEGRADED,
    DIAGNOSTIC_SENSITIVE_CONTRACT_METADATA_REDACTED,
)

NODE_FIELD_ORDER = (
    "repository_id",
    "display_name",
    "path",
    "role",
    "role_origin",
    "role_confidence",
    "role_confidence_score",
    "configured",
    "discovered",
    "known_ports",
    "known_urls",
    "evidence",
    "warnings",
    "metadata",
)
EDGE_FIELD_ORDER = (
    "source_repository_id",
    "target_repository_id",
    "relationship_type",
    "origin",
    "confidence",
    "confidence_score",
    "evidence",
    "warnings",
    "description",
    "explicit",
    "inferred",
    "contract_names",
    "metadata",
)
UNRESOLVED_FIELD_ORDER = (
    "source_repository_id",
    "target_repository_id",
    "relationship_type",
    "reason",
    "origin",
    "evidence",
    "diagnostics",
)
CYCLE_FIELD_ORDER = (
    "repository_ids",
    "edge_identities",
    "relationship_types",
    "confidence",
)
COMPONENT_FIELD_ORDER = (
    "repository_ids",
    "edge_count",
    "relationship_types",
    "confidence",
)
DIAGNOSTIC_FIELD_ORDER = (
    "code",
    "severity",
    "summary",
    "repository_ids",
    "edge",
    "details",
)
RESULT_FIELD_ORDER = (
    "schema_version",
    "nodes",
    "edges",
    "cycles",
    "strongly_connected_components",
    "isolated_repository_ids",
    "root_repository_ids",
    "leaf_repository_ids",
    "unresolved_relationships",
    "diagnostics",
    "summary",
    "metadata",
)
SUMMARY_FIELD_ORDER = (
    "node_count",
    "edge_count",
    "explicit_edge_count",
    "inferred_edge_count",
    "high_confidence_edge_count",
    "medium_confidence_edge_count",
    "low_confidence_edge_count",
    "cycle_count",
    "isolated_repository_count",
    "unresolved_relationship_count",
    "contract_edge_count",
)

SYMMETRIC_RELATIONSHIP_TYPES = (
    workspace_config.RELATIONSHIP_TYPE_SHARES_CONTRACT_WITH,
)
DEPENDENCY_RELATIONSHIP_TYPES = (
    workspace_config.RELATIONSHIP_TYPE_CALLS_API,
    workspace_config.RELATIONSHIP_TYPE_IMPORTS_PACKAGE,
    workspace_config.RELATIONSHIP_TYPE_EMBEDS_IFRAME,
    workspace_config.RELATIONSHIP_TYPE_SENDS_MESSAGES_TO,
    workspace_config.RELATIONSHIP_TYPE_DEPENDS_ON,
    workspace_config.RELATIONSHIP_TYPE_PROXIES_TO,
)
SECRET_VALUE = "[redacted]"


class WorkspaceGraphError(ValueError):
    """Raised when a Q6 graph contract is invalid."""


@dataclass(frozen=True, slots=True)
class WorkspaceGraphDiagnostic:
    code: str
    severity: str
    summary: str
    repository_ids: tuple[str, ...] = ()
    edge: Mapping[str, Any] | None = None
    details: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", _validate_choice(self.code, "code", DIAGNOSTIC_CODES))
        object.__setattr__(self, "severity", _validate_choice(self.severity, "severity", DIAGNOSTIC_SEVERITIES))
        object.__setattr__(self, "summary", _validate_nonempty_string(self.summary, "summary"))
        object.__setattr__(self, "repository_ids", tuple(sorted(set(_validate_messages(self.repository_ids, "repository_ids")))))
        object.__setattr__(self, "edge", _copy_json(self.edge or {}, "edge"))
        object.__setattr__(self, "details", _copy_json(self.details or {}, "details"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "summary": self.summary,
            "repository_ids": list(self.repository_ids),
            "edge": _json_ready(self.edge or {}),
            "details": _json_ready(self.details or {}),
        }


@dataclass(frozen=True, slots=True)
class WorkspaceGraphNode:
    repository_id: str
    display_name: str | None
    path: str
    role: str
    role_origin: str
    role_confidence: str
    role_confidence_score: float
    configured: bool
    discovered: bool
    known_ports: tuple[int, ...] = ()
    known_urls: tuple[str, ...] = ()
    evidence: tuple[workspace_relationships.RelationshipEvidence, ...] = ()
    warnings: tuple[str, ...] = ()
    metadata: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "repository_id", _validate_nonempty_string(self.repository_id, "repository_id"))
        object.__setattr__(self, "display_name", _validate_optional_string(self.display_name, "display_name"))
        object.__setattr__(self, "path", _normalize_relative_path(self.path, "path", allow_parent=True))
        object.__setattr__(self, "role", _validate_choice(self.role, "role", workspace_config.REPOSITORY_ROLES))
        object.__setattr__(self, "role_origin", _validate_nonempty_string(self.role_origin, "role_origin"))
        object.__setattr__(self, "role_confidence", _validate_choice(self.role_confidence, "role_confidence", CONFIDENCE_LEVELS))
        object.__setattr__(self, "role_confidence_score", _validate_score(self.role_confidence_score, "role_confidence_score"))
        object.__setattr__(self, "configured", _validate_bool(self.configured, "configured"))
        object.__setattr__(self, "discovered", _validate_bool(self.discovered, "discovered"))
        object.__setattr__(self, "known_ports", tuple(sorted(_validate_port(port) for port in self.known_ports)))
        object.__setattr__(self, "known_urls", tuple(sorted(_validate_nonempty_string(url, "known_url") for url in self.known_urls)))
        object.__setattr__(self, "evidence", tuple(sorted((_coerce_evidence(item) for item in self.evidence), key=workspace_relationships.evidence_identity_key)))
        object.__setattr__(self, "warnings", tuple(sorted(set(_validate_messages(self.warnings, "warnings")))))
        object.__setattr__(self, "metadata", _copy_json(self.metadata or {}, "metadata"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "repository_id": self.repository_id,
            "display_name": self.display_name,
            "path": self.path,
            "role": self.role,
            "role_origin": self.role_origin,
            "role_confidence": self.role_confidence,
            "role_confidence_score": self.role_confidence_score,
            "configured": self.configured,
            "discovered": self.discovered,
            "known_ports": list(self.known_ports),
            "known_urls": list(self.known_urls),
            "evidence": [item.to_dict() for item in self.evidence],
            "warnings": list(self.warnings),
            "metadata": _json_ready(self.metadata or {}),
        }


@dataclass(frozen=True, slots=True)
class WorkspaceGraphEdge:
    source_repository_id: str
    target_repository_id: str
    relationship_type: str
    origin: str
    confidence: str
    confidence_score: float
    evidence: tuple[workspace_relationships.RelationshipEvidence, ...] = ()
    warnings: tuple[str, ...] = ()
    description: str | None = None
    explicit: bool = False
    inferred: bool = False
    contract_names: tuple[str, ...] = ()
    metadata: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_repository_id", _validate_nonempty_string(self.source_repository_id, "source_repository_id"))
        object.__setattr__(self, "target_repository_id", _validate_nonempty_string(self.target_repository_id, "target_repository_id"))
        if self.source_repository_id == self.target_repository_id:
            raise WorkspaceGraphError("edge source and target must differ")
        object.__setattr__(self, "relationship_type", _validate_choice(self.relationship_type, "relationship_type", workspace_config.RELATIONSHIP_TYPES))
        object.__setattr__(self, "origin", _validate_nonempty_string(self.origin, "origin"))
        object.__setattr__(self, "confidence", _validate_choice(self.confidence, "confidence", CONFIDENCE_LEVELS))
        object.__setattr__(self, "confidence_score", _validate_score(self.confidence_score, "confidence_score"))
        object.__setattr__(self, "evidence", tuple(sorted((_coerce_evidence(item) for item in self.evidence), key=workspace_relationships.evidence_identity_key)))
        object.__setattr__(self, "warnings", tuple(sorted(set(_validate_messages(self.warnings, "warnings")))))
        object.__setattr__(self, "description", _validate_optional_string(self.description, "description"))
        object.__setattr__(self, "explicit", _validate_bool(self.explicit, "explicit"))
        object.__setattr__(self, "inferred", _validate_bool(self.inferred, "inferred"))
        object.__setattr__(self, "contract_names", tuple(sorted(set(_validate_messages(self.contract_names, "contract_names")))))
        object.__setattr__(self, "metadata", _copy_json(self.metadata or {}, "metadata"))

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
            "explicit": self.explicit,
            "inferred": self.inferred,
            "contract_names": list(self.contract_names),
            "metadata": _json_ready(self.metadata or {}),
        }


@dataclass(frozen=True, slots=True)
class UnresolvedRelationship:
    source_repository_id: str | None
    target_repository_id: str | None
    relationship_type: str | None
    reason: str
    origin: str
    evidence: tuple[workspace_relationships.RelationshipEvidence, ...] = ()
    diagnostics: tuple[WorkspaceGraphDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_repository_id", _validate_optional_string(self.source_repository_id, "source_repository_id"))
        object.__setattr__(self, "target_repository_id", _validate_optional_string(self.target_repository_id, "target_repository_id"))
        if self.relationship_type is not None:
            object.__setattr__(self, "relationship_type", _validate_nonempty_string(self.relationship_type, "relationship_type"))
        object.__setattr__(self, "reason", _validate_choice(self.reason, "reason", UNRESOLVED_REASONS))
        object.__setattr__(self, "origin", _validate_nonempty_string(self.origin, "origin"))
        object.__setattr__(self, "evidence", tuple(sorted((_coerce_evidence(item) for item in self.evidence), key=workspace_relationships.evidence_identity_key)))
        object.__setattr__(self, "diagnostics", tuple(sorted((_coerce_diagnostic(item) for item in self.diagnostics), key=diagnostic_sort_key)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_repository_id": self.source_repository_id,
            "target_repository_id": self.target_repository_id,
            "relationship_type": self.relationship_type,
            "reason": self.reason,
            "origin": self.origin,
            "evidence": [item.to_dict() for item in self.evidence],
            "diagnostics": [item.to_dict() for item in self.diagnostics],
        }


@dataclass(frozen=True, slots=True)
class WorkspaceCycle:
    repository_ids: tuple[str, ...]
    edge_identities: tuple[str, ...]
    relationship_types: tuple[str, ...]
    confidence: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "repository_ids", tuple(_validate_messages(self.repository_ids, "repository_ids")))
        object.__setattr__(self, "edge_identities", tuple(sorted(_validate_messages(self.edge_identities, "edge_identities"))))
        object.__setattr__(self, "relationship_types", tuple(sorted(set(_validate_messages(self.relationship_types, "relationship_types")))))
        object.__setattr__(self, "confidence", _validate_choice(self.confidence, "confidence", CONFIDENCE_LEVELS))

    def to_dict(self) -> dict[str, Any]:
        return {
            "repository_ids": list(self.repository_ids),
            "edge_identities": list(self.edge_identities),
            "relationship_types": list(self.relationship_types),
            "confidence": self.confidence,
        }


@dataclass(frozen=True, slots=True)
class StronglyConnectedComponent:
    repository_ids: tuple[str, ...]
    edge_count: int
    relationship_types: tuple[str, ...]
    confidence: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "repository_ids", tuple(sorted(set(_validate_messages(self.repository_ids, "repository_ids")))))
        object.__setattr__(self, "edge_count", _validate_nonnegative_int(self.edge_count, "edge_count"))
        object.__setattr__(self, "relationship_types", tuple(sorted(set(_validate_messages(self.relationship_types, "relationship_types")))))
        object.__setattr__(self, "confidence", _validate_choice(self.confidence, "confidence", CONFIDENCE_LEVELS))

    def to_dict(self) -> dict[str, Any]:
        return {
            "repository_ids": list(self.repository_ids),
            "edge_count": self.edge_count,
            "relationship_types": list(self.relationship_types),
            "confidence": self.confidence,
        }


@dataclass(frozen=True, slots=True)
class WorkspaceDependencyGraph:
    schema_version: int
    nodes: tuple[WorkspaceGraphNode, ...]
    edges: tuple[WorkspaceGraphEdge, ...]
    cycles: tuple[WorkspaceCycle, ...]
    strongly_connected_components: tuple[StronglyConnectedComponent, ...]
    isolated_repository_ids: tuple[str, ...]
    root_repository_ids: tuple[str, ...]
    leaf_repository_ids: tuple[str, ...]
    unresolved_relationships: tuple[UnresolvedRelationship, ...]
    diagnostics: tuple[WorkspaceGraphDiagnostic, ...]
    summary: Mapping[str, Any]
    metadata: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.schema_version != WORKSPACE_GRAPH_SCHEMA_VERSION:
            raise WorkspaceGraphError("workspace graph schema_version must be 1")
        object.__setattr__(self, "nodes", tuple(sorted((_coerce_node(item) for item in self.nodes), key=node_sort_key)))
        object.__setattr__(self, "edges", tuple(sorted((_coerce_edge(item) for item in self.edges), key=edge_sort_key)))
        object.__setattr__(self, "cycles", tuple(sorted((_coerce_cycle(item) for item in self.cycles), key=cycle_sort_key)))
        object.__setattr__(self, "strongly_connected_components", tuple(sorted((_coerce_component(item) for item in self.strongly_connected_components), key=component_sort_key)))
        object.__setattr__(self, "isolated_repository_ids", tuple(sorted(set(_validate_messages(self.isolated_repository_ids, "isolated_repository_ids")))))
        object.__setattr__(self, "root_repository_ids", tuple(sorted(set(_validate_messages(self.root_repository_ids, "root_repository_ids")))))
        object.__setattr__(self, "leaf_repository_ids", tuple(sorted(set(_validate_messages(self.leaf_repository_ids, "leaf_repository_ids")))))
        object.__setattr__(self, "unresolved_relationships", tuple(sorted((_coerce_unresolved(item) for item in self.unresolved_relationships), key=unresolved_sort_key)))
        object.__setattr__(self, "diagnostics", tuple(sorted((_coerce_diagnostic(item) for item in self.diagnostics), key=diagnostic_sort_key)))
        object.__setattr__(self, "summary", _copy_json(self.summary, "summary"))
        object.__setattr__(self, "metadata", _copy_json(self.metadata or {}, "metadata"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
            "cycles": [cycle.to_dict() for cycle in self.cycles],
            "strongly_connected_components": [component.to_dict() for component in self.strongly_connected_components],
            "isolated_repository_ids": list(self.isolated_repository_ids),
            "root_repository_ids": list(self.root_repository_ids),
            "leaf_repository_ids": list(self.leaf_repository_ids),
            "unresolved_relationships": [item.to_dict() for item in self.unresolved_relationships],
            "diagnostics": [diagnostic.to_dict() for diagnostic in self.diagnostics],
            "summary": {key: _json_ready(self.summary[key]) for key in SUMMARY_FIELD_ORDER if key in self.summary},
            "metadata": _json_ready(self.metadata or {}),
        }


def _validate_nonempty_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkspaceGraphError(f"{name} must be a non-empty string")
    if value != value.strip() or "\x00" in value:
        raise WorkspaceGraphError(f"{name} must not contain padding or null bytes")
    return value


def _validate_optional_string(value: Any, name: str) -> str | None:
    if value is None:
        return None
    return _validate_nonempty_string(value, name)


def _validate_choice(value: Any, name: str, choices: tuple[str, ...]) -> str:
    text = _validate_nonempty_string(value, name)
    if text not in choices:
        raise WorkspaceGraphError(f"{name} must be one of: {', '.join(choices)}")
    return text


def _validate_bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{name} must be a boolean")
    return value


def _validate_score(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized < 0.0 or normalized > 1.0:
        raise WorkspaceGraphError(f"{name} must be between 0.0 and 1.0")
    return round(normalized, 3)


def _validate_limit(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 1:
        raise WorkspaceGraphError(f"{name} must be at least 1")
    return value


def _validate_nonnegative_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise WorkspaceGraphError(f"{name} must be a non-negative integer")
    return value


def _validate_port(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1 or value > 65535:
        raise WorkspaceGraphError("known port must be between 1 and 65535")
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


def _normalize_relative_path(value: Any, name: str, *, allow_parent: bool) -> str:
    text = _validate_nonempty_string(value, name)
    windows_path = PureWindowsPath(text)
    posix_text = text.replace("\\", "/")
    posix_path = PurePosixPath(posix_text)
    if windows_path.drive or windows_path.is_absolute() or posix_path.is_absolute():
        raise WorkspaceGraphError(f"{name} must be relative")
    collapsed: list[str] = []
    for part in posix_path.parts:
        if part in ("", "."):
            continue
        if part == "..":
            if not allow_parent:
                raise WorkspaceGraphError(f"{name} must not contain parent traversal")
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
            raise WorkspaceGraphError(f"{name} must be finite")
        return value
    if isinstance(value, Mapping):
        copied = {}
        for key in sorted(value):
            if not isinstance(key, str):
                raise WorkspaceGraphError(f"{name} keys must be strings")
            copied[key] = _copy_json(value[key], f"{name}.{key}")
        return copied
    if isinstance(value, (list, tuple)):
        return tuple(_copy_json(item, f"{name}[{index}]") for index, item in enumerate(value))
    raise WorkspaceGraphError(f"{name} must be JSON-ready")


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
        raise TypeError("evidence must be RelationshipEvidence or mapping")
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


def _coerce_node(value: Any) -> WorkspaceGraphNode:
    if isinstance(value, WorkspaceGraphNode):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("node must be WorkspaceGraphNode or mapping")
    return WorkspaceGraphNode(
        repository_id=value["repository_id"],
        display_name=value.get("display_name"),
        path=value["path"],
        role=value["role"],
        role_origin=value["role_origin"],
        role_confidence=value["role_confidence"],
        role_confidence_score=value["role_confidence_score"],
        configured=value["configured"],
        discovered=value["discovered"],
        known_ports=tuple(value.get("known_ports", ())),
        known_urls=tuple(value.get("known_urls", ())),
        evidence=tuple(value.get("evidence", ())),
        warnings=tuple(value.get("warnings", ())),
        metadata=value.get("metadata"),
    )


def _coerce_edge(value: Any) -> WorkspaceGraphEdge:
    if isinstance(value, WorkspaceGraphEdge):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("edge must be WorkspaceGraphEdge or mapping")
    return WorkspaceGraphEdge(
        source_repository_id=value["source_repository_id"],
        target_repository_id=value["target_repository_id"],
        relationship_type=value["relationship_type"],
        origin=value["origin"],
        confidence=value["confidence"],
        confidence_score=value["confidence_score"],
        evidence=tuple(value.get("evidence", ())),
        warnings=tuple(value.get("warnings", ())),
        description=value.get("description"),
        explicit=bool(value.get("explicit", False)),
        inferred=bool(value.get("inferred", False)),
        contract_names=tuple(value.get("contract_names", ())),
        metadata=value.get("metadata"),
    )


def _coerce_unresolved(value: Any) -> UnresolvedRelationship:
    if isinstance(value, UnresolvedRelationship):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("unresolved relationship must be UnresolvedRelationship or mapping")
    return UnresolvedRelationship(
        source_repository_id=value.get("source_repository_id"),
        target_repository_id=value.get("target_repository_id"),
        relationship_type=value.get("relationship_type"),
        reason=value["reason"],
        origin=value["origin"],
        evidence=tuple(value.get("evidence", ())),
        diagnostics=tuple(value.get("diagnostics", ())),
    )


def _coerce_cycle(value: Any) -> WorkspaceCycle:
    if isinstance(value, WorkspaceCycle):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("cycle must be WorkspaceCycle or mapping")
    return WorkspaceCycle(
        repository_ids=tuple(value.get("repository_ids", ())),
        edge_identities=tuple(value.get("edge_identities", ())),
        relationship_types=tuple(value.get("relationship_types", ())),
        confidence=value["confidence"],
    )


def _coerce_component(value: Any) -> StronglyConnectedComponent:
    if isinstance(value, StronglyConnectedComponent):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("component must be StronglyConnectedComponent or mapping")
    return StronglyConnectedComponent(
        repository_ids=tuple(value.get("repository_ids", ())),
        edge_count=value["edge_count"],
        relationship_types=tuple(value.get("relationship_types", ())),
        confidence=value["confidence"],
    )


def _coerce_diagnostic(value: Any) -> WorkspaceGraphDiagnostic:
    if isinstance(value, WorkspaceGraphDiagnostic):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("diagnostic must be WorkspaceGraphDiagnostic or mapping")
    return WorkspaceGraphDiagnostic(
        code=value["code"],
        severity=value["severity"],
        summary=value["summary"],
        repository_ids=tuple(value.get("repository_ids", ())),
        edge=value.get("edge"),
        details=value.get("details"),
    )


def node_sort_key(node: WorkspaceGraphNode) -> tuple[object, ...]:
    return (node.repository_id, node.path)


def edge_identity_key(edge: WorkspaceGraphEdge | Mapping[str, Any]) -> tuple[str, str, str]:
    item = _coerce_edge(edge)
    source = item.source_repository_id
    target = item.target_repository_id
    if item.relationship_type in SYMMETRIC_RELATIONSHIP_TYPES and target < source:
        source, target = target, source
    return (source, target, item.relationship_type)


def edge_sort_key(edge: WorkspaceGraphEdge) -> tuple[object, ...]:
    return (
        edge.source_repository_id,
        edge.target_repository_id,
        workspace_config.RELATIONSHIP_TYPES.index(edge.relationship_type),
        edge.origin,
        -edge.confidence_score,
    )


def unresolved_sort_key(item: UnresolvedRelationship) -> tuple[object, ...]:
    return (item.source_repository_id or "", item.target_repository_id or "", item.relationship_type or "", item.reason, item.origin)


def cycle_sort_key(cycle: WorkspaceCycle) -> tuple[object, ...]:
    return (cycle.repository_ids, cycle.relationship_types, cycle.edge_identities)


def component_sort_key(component: StronglyConnectedComponent) -> tuple[object, ...]:
    return (component.repository_ids, component.relationship_types, component.edge_count)


def diagnostic_sort_key(diagnostic: WorkspaceGraphDiagnostic) -> tuple[object, ...]:
    return (diagnostic.code, diagnostic.severity, diagnostic.repository_ids, _json_key(diagnostic.edge or {}), _json_key(diagnostic.details or {}), diagnostic.summary)


def _diagnostic(
    code: str,
    severity: str,
    summary: str,
    *,
    repository_ids: Iterable[str] = (),
    edge: Mapping[str, Any] | None = None,
    details: Mapping[str, Any] | None = None,
) -> WorkspaceGraphDiagnostic:
    return WorkspaceGraphDiagnostic(code, severity, summary, tuple(repository_ids), edge, details)


def _confidence_from_score(score: float) -> str:
    if score >= 0.7:
        return CONFIDENCE_HIGH
    if score >= 0.4:
        return CONFIDENCE_MEDIUM
    return CONFIDENCE_LOW


def _bound_evidence(
    evidence: Iterable[workspace_relationships.RelationshipEvidence],
    limit: int,
    diagnostics: list[WorkspaceGraphDiagnostic],
    *,
    repository_ids: Iterable[str] = (),
) -> tuple[workspace_relationships.RelationshipEvidence, ...]:
    values = tuple(sorted({_json_key(item.to_dict()): item for item in (_coerce_evidence(e) for e in evidence)}.values(), key=workspace_relationships.evidence_identity_key))
    if len(values) <= limit:
        return values
    diagnostics.append(
        _diagnostic(
            DIAGNOSTIC_GRAPH_EVIDENCE_TRUNCATED,
            DIAGNOSTIC_SEVERITY_INFO,
            "Graph evidence was truncated.",
            repository_ids=repository_ids,
            details={"limit": limit, "omitted": len(values) - limit},
        )
    )
    return values[:limit]


def _relationship_summary(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "source_repository_id": value.get("source_repository_id"),
        "target_repository_id": value.get("target_repository_id"),
        "relationship_type": value.get("relationship_type"),
    }


def _make_evidence(repository_id: str, source_path: str, summary: str, strength: str, metadata: Mapping[str, Any] | None = None) -> workspace_relationships.RelationshipEvidence:
    return workspace_relationships.RelationshipEvidence(
        signal_type="workspace_graph",
        source_repository_id=repository_id,
        source_path=source_path,
        summary=summary,
        strength=strength,
        metadata=metadata or {},
    )


def _assessment_to_dict(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, workspace_relationships.WorkspaceRelationshipAssessment):
        return value.to_dict()
    if isinstance(value, Mapping):
        return dict(value)
    raise TypeError("relationship_assessment must be a WorkspaceRelationshipAssessment, mapping, or None")


def _discovery_to_dict(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, workspace_discovery.WorkspaceDiscoveryResult):
        return value.to_dict()
    if isinstance(value, Mapping):
        return dict(value)
    raise TypeError("discovery_result must be a WorkspaceDiscoveryResult, mapping, or None")


def _contract_findings_from_input(value: Any) -> tuple[dict[str, Any], ...]:
    if value is None:
        return ()
    if isinstance(value, workspace_contracts.SharedContractComparisonResult):
        return tuple(item.to_dict() for item in value.contract_findings)
    if isinstance(value, Mapping) and "contract_findings" in value:
        return tuple(dict(item) for item in value.get("contract_findings", ()))
    return tuple(item.to_dict() if isinstance(item, workspace_contracts.SharedContractFinding) else dict(item) for item in value)


def _relationship_candidates_from_input(value: Iterable[Any]) -> tuple[dict[str, Any], ...]:
    values = []
    for item in value:
        if isinstance(item, workspace_relationships.RelationshipCandidate):
            values.append(item.to_dict())
        elif isinstance(item, Mapping):
            values.append(dict(item))
        else:
            raise TypeError("relationship hints must be RelationshipCandidate or mapping values")
    return tuple(values)


def _workspace_with_unique_repository_ids(value: Any, diagnostics: list[WorkspaceGraphDiagnostic]) -> Any:
    if not isinstance(value, Mapping):
        return value
    repositories = value.get("repositories")
    if repositories is None or isinstance(repositories, (str, bytes)):
        return value
    try:
        repository_items = tuple(repositories)
    except TypeError:
        return value
    seen: set[str] = set()
    filtered: list[Any] = []
    changed = False
    for repository in repository_items:
        repository_id = repository.get("id") if isinstance(repository, Mapping) else getattr(repository, "id", None)
        if isinstance(repository_id, str) and repository_id in seen:
            diagnostics.append(_diagnostic(DIAGNOSTIC_DUPLICATE_REPOSITORY_ID, DIAGNOSTIC_SEVERITY_ERROR, "Duplicate repository id was found.", repository_ids=(repository_id,)))
            changed = True
            continue
        if isinstance(repository_id, str):
            seen.add(repository_id)
        filtered.append(repository)
    if not changed:
        return value
    copied = dict(value)
    copied["repositories"] = tuple(filtered)
    return copied


def _role_assessment_by_id(assessment: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not assessment:
        return {}
    return {item["repository_id"]: dict(item) for item in assessment.get("role_assessments", ())}


def _discovery_candidates(discovery: dict[str, Any] | None) -> tuple[dict[str, Any], ...]:
    if not discovery:
        return ()
    return tuple(dict(item) for item in discovery.get("candidates", ()))


def _discovery_by_id(discovery: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    return {str(item.get("suggested_id")): item for item in _discovery_candidates(discovery) if item.get("suggested_id")}


def _evidence_from_discovery(repository_id: str, candidate: Mapping[str, Any]) -> tuple[workspace_relationships.RelationshipEvidence, ...]:
    evidence = []
    for item in candidate.get("evidence", ()):
        if isinstance(item, workspace_relationships.RelationshipEvidence):
            evidence.append(item)
            continue
        if not isinstance(item, Mapping):
            continue
        evidence.append(
            workspace_relationships.RelationshipEvidence(
                signal_type=str(item.get("signal_type", "discovery")),
                source_repository_id=repository_id,
                source_path=str(item.get("source_path", ".")),
                summary=str(item.get("summary", "Discovery evidence.")),
                strength=str(item.get("strength", workspace_relationships.EVIDENCE_STRENGTH_WEAK)),
                referenced_path=item.get("referenced_path"),
                metadata={"discovery_source": candidate.get("discovery_source")},
            )
        )
    return tuple(evidence)


def _build_nodes(
    workspace: Mapping[str, Any],
    assessment: dict[str, Any] | None,
    discovery: dict[str, Any] | None,
    include_discovered: bool,
    max_nodes: int,
    max_evidence_per_node: int,
    diagnostics: list[WorkspaceGraphDiagnostic],
) -> tuple[WorkspaceGraphNode, ...]:
    role_by_id = _role_assessment_by_id(assessment)
    discovery_by_id = _discovery_by_id(discovery)
    raw_repositories = tuple(workspace.get("repositories", ()))
    seen_ids: set[str] = set()
    seen_paths: dict[str, str] = {}
    nodes: list[WorkspaceGraphNode] = []
    for repository in raw_repositories:
        repository_id = repository["id"]
        if repository_id in seen_ids:
            diagnostics.append(_diagnostic(DIAGNOSTIC_DUPLICATE_REPOSITORY_ID, DIAGNOSTIC_SEVERITY_ERROR, "Duplicate repository id was found.", repository_ids=(repository_id,)))
            continue
        seen_ids.add(repository_id)
        path = repository["path"]
        if path in seen_paths:
            diagnostics.append(_diagnostic(DIAGNOSTIC_DUPLICATE_REPOSITORY_PATH, DIAGNOSTIC_SEVERITY_WARNING, "Duplicate repository path was found.", repository_ids=(seen_paths[path], repository_id), details={"path": path}))
        seen_paths[path] = repository_id
        role_assessment = role_by_id.get(repository_id, {})
        configured_role = repository["role"]
        role = configured_role
        metadata: dict[str, Any] = {}
        if configured_role == workspace_config.REPOSITORY_ROLE_UNKNOWN and role_assessment.get("suggested_role"):
            metadata["suggested_role"] = role_assessment["suggested_role"]
        elif role_assessment and role_assessment.get("role") not in {None, configured_role} and configured_role != workspace_config.REPOSITORY_ROLE_UNKNOWN:
            diagnostics.append(_diagnostic(DIAGNOSTIC_CONFLICTING_NODE_ROLE, DIAGNOSTIC_SEVERITY_WARNING, "Role assessment conflicts with configured repository role.", repository_ids=(repository_id,), details={"configured_role": configured_role, "assessed_role": role_assessment.get("role")}))
        evidence = tuple(_coerce_evidence(item) for item in role_assessment.get("evidence", ()))
        discovery_candidate = discovery_by_id.get(repository_id)
        if discovery_candidate:
            evidence = (*evidence, *_evidence_from_discovery(repository_id, discovery_candidate))
            metadata["discovery_confidence"] = discovery_candidate.get("confidence")
        bounded = _bound_evidence(evidence, max_evidence_per_node, diagnostics, repository_ids=(repository_id,))
        score = float(role_assessment.get("confidence_score", 1.0 if configured_role != workspace_config.REPOSITORY_ROLE_UNKNOWN else 0.1))
        nodes.append(
            WorkspaceGraphNode(
                repository_id=repository_id,
                display_name=repository.get("display_name"),
                path=path,
                role=role,
                role_origin=str(role_assessment.get("origin", "explicit" if configured_role != workspace_config.REPOSITORY_ROLE_UNKNOWN else "default")),
                role_confidence=str(role_assessment.get("confidence", _confidence_from_score(score))),
                role_confidence_score=score,
                configured=True,
                discovered=bool(discovery_candidate),
                known_ports=tuple(repository.get("known_ports", ())),
                known_urls=tuple(repository.get("known_urls", ())),
                evidence=bounded,
                warnings=tuple(role_assessment.get("warnings", ())),
                metadata=metadata,
            )
        )
    if include_discovered:
        for candidate in _discovery_candidates(discovery):
            repository_id = str(candidate.get("suggested_id", "")).strip()
            if not repository_id or repository_id in seen_ids:
                if repository_id in seen_ids:
                    diagnostics.append(_diagnostic(DIAGNOSTIC_AMBIGUOUS_DISCOVERY_IDENTITY, DIAGNOSTIC_SEVERITY_INFO, "Discovery candidate matched an already configured repository.", repository_ids=(repository_id,)))
                continue
            path = str(candidate.get("path", "."))
            if path in seen_paths:
                diagnostics.append(_diagnostic(DIAGNOSTIC_DUPLICATE_REPOSITORY_PATH, DIAGNOSTIC_SEVERITY_WARNING, "Discovered repository path matches another node.", repository_ids=(seen_paths[path], repository_id), details={"path": path}))
            seen_ids.add(repository_id)
            seen_paths[path] = repository_id
            evidence = _bound_evidence(_evidence_from_discovery(repository_id, candidate), max_evidence_per_node, diagnostics, repository_ids=(repository_id,))
            score = float(candidate.get("confidence_score", 0.4))
            nodes.append(
                WorkspaceGraphNode(
                    repository_id=repository_id,
                    display_name=candidate.get("display_name"),
                    path=path,
                    role=str(candidate.get("probable_role", workspace_config.REPOSITORY_ROLE_UNKNOWN)),
                    role_origin="discovered",
                    role_confidence=str(candidate.get("confidence", _confidence_from_score(score))),
                    role_confidence_score=score,
                    configured=False,
                    discovered=True,
                    evidence=evidence,
                    metadata={"discovery_source": candidate.get("discovery_source")},
                )
            )
    nodes = sorted(nodes, key=node_sort_key)
    if len(nodes) > max_nodes:
        omitted = len(nodes) - max_nodes
        diagnostics.append(_diagnostic(DIAGNOSTIC_GRAPH_NODE_CAP_REACHED, DIAGNOSTIC_SEVERITY_WARNING, "Graph node cap was reached.", details={"limit": max_nodes, "omitted": omitted}))
        nodes = nodes[:max_nodes]
    return tuple(nodes)


def _explicit_relationships(workspace: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    values = []
    for relationship in workspace.get("relationships", ()):
        values.append(
            {
                "source_repository_id": relationship["source_repository_id"],
                "target_repository_id": relationship["target_repository_id"],
                "relationship_type": relationship["relationship_type"],
                "origin": workspace_relationships.RELATIONSHIP_ORIGIN_EXPLICIT,
                "confidence": CONFIDENCE_HIGH,
                "confidence_score": 1.0,
                "evidence": (
                    _make_evidence(relationship["source_repository_id"], ".", "Relationship is configured explicitly.", workspace_relationships.EVIDENCE_STRENGTH_STRONG, {"origin": "explicit"}),
                ),
                "warnings": (),
                "description": relationship.get("description"),
                "explicit": True,
                "inferred": False,
            }
        )
    return tuple(values)


def _assessment_relationships(assessment: dict[str, Any] | None) -> tuple[dict[str, Any], ...]:
    if not assessment:
        return ()
    values = []
    for relationship in assessment.get("relationships", ()):
        value = dict(relationship)
        value["explicit"] = value.get("origin") == workspace_relationships.RELATIONSHIP_ORIGIN_EXPLICIT
        value["inferred"] = value.get("origin") != workspace_relationships.RELATIONSHIP_ORIGIN_EXPLICIT
        values.append(value)
    return tuple(values)


def _contract_edges(findings: tuple[dict[str, Any], ...]) -> tuple[dict[str, Any], ...]:
    values: list[dict[str, Any]] = []
    for finding in findings:
        repositories = sorted({item.get("repository_id") for item in finding.get("location_findings", ()) if item.get("repository_id")})
        if len(repositories) < 2:
            continue
        status = finding.get("status")
        if status in {workspace_contracts.STATUS_MISSING, workspace_contracts.STATUS_UNSUPPORTED}:
            continue
        score = float(finding.get("confidence_score", 0.5))
        warnings: tuple[str, ...] = ()
        if status != workspace_contracts.STATUS_CONSISTENT:
            score = min(score, 0.55)
            warnings = (f"shared contract {finding.get('name')} is {status}",)
        for index, source in enumerate(repositories):
            for target in repositories[index + 1 :]:
                values.append(
                    {
                        "source_repository_id": source,
                        "target_repository_id": target,
                        "relationship_type": workspace_config.RELATIONSHIP_TYPE_SHARES_CONTRACT_WITH,
                        "origin": "shared_contract",
                        "confidence": _confidence_from_score(score),
                        "confidence_score": score,
                        "evidence": tuple(_coerce_evidence(item) for item in finding.get("evidence", ())),
                        "warnings": warnings,
                        "description": "Repositories share a configured contract.",
                        "explicit": False,
                        "inferred": True,
                        "contract_names": (str(finding.get("name")),),
                        "metadata": {"contract_status": status},
                    }
                )
    return tuple(values)


def _edge_from_candidate(value: Mapping[str, Any]) -> WorkspaceGraphEdge:
    source = str(value.get("source_repository_id", "")).strip()
    target = str(value.get("target_repository_id", "")).strip()
    relationship_type = str(value.get("relationship_type", "")).strip()
    if relationship_type == workspace_config.RELATIONSHIP_TYPE_SHARES_CONTRACT_WITH and target < source:
        source, target = target, source
    score = float(value.get("confidence_score", 0.5))
    return WorkspaceGraphEdge(
        source_repository_id=source,
        target_repository_id=target,
        relationship_type=relationship_type,
        origin=str(value.get("origin", workspace_relationships.RELATIONSHIP_ORIGIN_INFERRED)),
        confidence=str(value.get("confidence", _confidence_from_score(score))),
        confidence_score=score,
        evidence=tuple(value.get("evidence", ())),
        warnings=tuple(value.get("warnings", ())),
        description=value.get("description"),
        explicit=bool(value.get("explicit", value.get("origin") == workspace_relationships.RELATIONSHIP_ORIGIN_EXPLICIT)),
        inferred=bool(value.get("inferred", value.get("origin") != workspace_relationships.RELATIONSHIP_ORIGIN_EXPLICIT)),
        contract_names=tuple(value.get("contract_names", ())),
        metadata=value.get("metadata"),
    )


def _unresolved_for_candidate(value: Mapping[str, Any], node_ids: set[str], reason: str | None = None) -> tuple[UnresolvedRelationship | None, WorkspaceGraphDiagnostic | None]:
    source = str(value.get("source_repository_id", "")).strip() or None
    target = str(value.get("target_repository_id", "")).strip() or None
    relationship_type = str(value.get("relationship_type", "")).strip() or None
    origin = str(value.get("origin", "unknown"))
    edge = _relationship_summary(value)
    if relationship_type not in workspace_config.RELATIONSHIP_TYPES:
        diagnostic = _diagnostic(DIAGNOSTIC_UNSUPPORTED_RELATIONSHIP_TYPE, DIAGNOSTIC_SEVERITY_ERROR, "Relationship type is unsupported.", repository_ids=tuple(item for item in (source, target) if item), edge=edge)
        return UnresolvedRelationship(source, target, relationship_type, UNRESOLVED_UNSUPPORTED_RELATIONSHIP_TYPE, origin, tuple(value.get("evidence", ())), (diagnostic,)), diagnostic
    if source and target and source == target:
        diagnostic = _diagnostic(DIAGNOSTIC_SELF_RELATIONSHIP_REJECTED, DIAGNOSTIC_SEVERITY_ERROR, "Self relationship was rejected.", repository_ids=(source,), edge=edge)
        return UnresolvedRelationship(source, target, relationship_type, UNRESOLVED_SELF_RELATIONSHIP, origin, tuple(value.get("evidence", ())), (diagnostic,)), diagnostic
    missing_source = source not in node_ids
    missing_target = target not in node_ids
    if reason == UNRESOLVED_AMBIGUOUS_TARGET:
        diagnostic = _diagnostic(DIAGNOSTIC_UNKNOWN_EDGE_TARGET, DIAGNOSTIC_SEVERITY_WARNING, "Relationship target is ambiguous.", repository_ids=tuple(item for item in (source, target) if item), edge=edge)
        return UnresolvedRelationship(source, target, relationship_type, UNRESOLVED_AMBIGUOUS_TARGET, origin, tuple(value.get("evidence", ())), (diagnostic,)), diagnostic
    if missing_source and missing_target:
        diagnostic = _diagnostic(DIAGNOSTIC_UNKNOWN_EDGE_REPOSITORIES, DIAGNOSTIC_SEVERITY_ERROR, "Relationship source and target are unknown.", repository_ids=tuple(item for item in (source, target) if item), edge=edge)
        return UnresolvedRelationship(source, target, relationship_type, UNRESOLVED_BOTH_REPOSITORIES_MISSING, origin, tuple(value.get("evidence", ())), (diagnostic,)), diagnostic
    if missing_source:
        diagnostic = _diagnostic(DIAGNOSTIC_UNKNOWN_EDGE_SOURCE, DIAGNOSTIC_SEVERITY_ERROR, "Relationship source is unknown.", repository_ids=tuple(item for item in (source,) if item), edge=edge)
        return UnresolvedRelationship(source, target, relationship_type, UNRESOLVED_SOURCE_REPOSITORY_MISSING, origin, tuple(value.get("evidence", ())), (diagnostic,)), diagnostic
    if missing_target:
        diagnostic = _diagnostic(DIAGNOSTIC_UNKNOWN_EDGE_TARGET, DIAGNOSTIC_SEVERITY_ERROR, "Relationship target is unknown.", repository_ids=tuple(item for item in (target,) if item), edge=edge)
        return UnresolvedRelationship(source, target, relationship_type, UNRESOLVED_TARGET_REPOSITORY_MISSING, origin, tuple(value.get("evidence", ())), (diagnostic,)), diagnostic
    return None, None


def _merge_edges(
    candidates: Iterable[Mapping[str, Any]],
    node_ids: set[str],
    max_edges: int,
    max_evidence_per_edge: int,
    max_contract_names_per_edge: int,
    max_unresolved: int,
    diagnostics: list[WorkspaceGraphDiagnostic],
) -> tuple[tuple[WorkspaceGraphEdge, ...], tuple[UnresolvedRelationship, ...]]:
    by_identity: dict[tuple[str, str, str], WorkspaceGraphEdge] = {}
    unresolved: list[UnresolvedRelationship] = []
    for candidate in sorted((dict(item) for item in candidates), key=lambda item: (str(item.get("source_repository_id", "")), str(item.get("target_repository_id", "")), str(item.get("relationship_type", "")), str(item.get("origin", "")))):
        reason = UNRESOLVED_AMBIGUOUS_TARGET if candidate.get("metadata", {}).get("ambiguous_target") else None
        unresolved_item, diagnostic = _unresolved_for_candidate(candidate, node_ids, reason)
        if unresolved_item:
            unresolved.append(unresolved_item)
            if diagnostic:
                diagnostics.append(diagnostic)
            continue
        edge = _edge_from_candidate(candidate)
        if (
            edge.relationship_type == workspace_config.RELATIONSHIP_TYPE_SHARES_CONTRACT_WITH
            and (edge.metadata or {}).get("contract_status") not in {None, workspace_contracts.STATUS_CONSISTENT}
        ):
            diagnostics.append(
                _diagnostic(
                    DIAGNOSTIC_CONTRACT_EDGE_DEGRADED,
                    DIAGNOSTIC_SEVERITY_WARNING,
                    "Shared-contract edge confidence was degraded.",
                    repository_ids=(edge.source_repository_id, edge.target_repository_id),
                    edge=_relationship_summary(candidate),
                    details={"contract_status": (edge.metadata or {}).get("contract_status")},
                )
            )
        identity = edge_identity_key(edge)
        existing = by_identity.get(identity)
        if existing is None:
            bounded_evidence = _bound_evidence(edge.evidence, max_evidence_per_edge, diagnostics, repository_ids=(edge.source_repository_id, edge.target_repository_id))
            by_identity[identity] = WorkspaceGraphEdge(
                source_repository_id=edge.source_repository_id,
                target_repository_id=edge.target_repository_id,
                relationship_type=edge.relationship_type,
                origin=edge.origin,
                confidence=edge.confidence,
                confidence_score=edge.confidence_score,
                evidence=bounded_evidence,
                warnings=edge.warnings,
                description=edge.description,
                explicit=edge.explicit,
                inferred=edge.inferred,
                contract_names=edge.contract_names[:max_contract_names_per_edge],
                metadata=edge.metadata,
            )
            continue
        explicit = existing.explicit or edge.explicit
        inferred = existing.inferred or edge.inferred
        origin = workspace_relationships.RELATIONSHIP_ORIGIN_EXPLICIT if explicit else existing.origin
        score = max(existing.confidence_score, edge.confidence_score)
        if not explicit and existing.confidence_score != edge.confidence_score:
            score = min(1.0, score + 0.05)
        evidence = _bound_evidence((*existing.evidence, *edge.evidence), max_evidence_per_edge, diagnostics, repository_ids=(existing.source_repository_id, existing.target_repository_id))
        contract_names = tuple(sorted(set((*existing.contract_names, *edge.contract_names))))[:max_contract_names_per_edge]
        warnings = tuple(sorted(set((*existing.warnings, *edge.warnings))))
        metadata = {**(existing.metadata or {}), **(edge.metadata or {})}
        by_identity[identity] = WorkspaceGraphEdge(
            source_repository_id=existing.source_repository_id,
            target_repository_id=existing.target_repository_id,
            relationship_type=existing.relationship_type,
            origin=origin,
            confidence=_confidence_from_score(score),
            confidence_score=score,
            evidence=evidence,
            warnings=warnings,
            description=existing.description or edge.description,
            explicit=explicit,
            inferred=inferred,
            contract_names=contract_names,
            metadata=metadata,
        )
    edges = tuple(sorted(by_identity.values(), key=edge_sort_key))
    if len(edges) > max_edges:
        omitted_edges = edges[max_edges:]
        diagnostics.append(_diagnostic(DIAGNOSTIC_GRAPH_EDGE_CAP_REACHED, DIAGNOSTIC_SEVERITY_WARNING, "Graph edge cap was reached.", details={"limit": max_edges, "omitted": len(omitted_edges)}))
        for edge in omitted_edges:
            unresolved.append(UnresolvedRelationship(edge.source_repository_id, edge.target_repository_id, edge.relationship_type, UNRESOLVED_EDGE_CAP_REACHED, edge.origin, edge.evidence))
        edges = edges[:max_edges]
    if len(unresolved) > max_unresolved:
        diagnostics.append(_diagnostic(DIAGNOSTIC_GRAPH_EDGE_CAP_REACHED, DIAGNOSTIC_SEVERITY_WARNING, "Unresolved relationship cap was reached.", details={"limit": max_unresolved, "omitted": len(unresolved) - max_unresolved}))
        unresolved = unresolved[:max_unresolved]
    return edges, tuple(sorted(unresolved, key=unresolved_sort_key))


def _dependency_edges(edges: Iterable[WorkspaceGraphEdge]) -> tuple[WorkspaceGraphEdge, ...]:
    return tuple(edge for edge in edges if edge.relationship_type in DEPENDENCY_RELATIONSHIP_TYPES)


def _adjacency(edges: Iterable[WorkspaceGraphEdge], node_ids: Iterable[str]) -> dict[str, list[str]]:
    adjacency = {node_id: [] for node_id in sorted(node_ids)}
    for edge in _dependency_edges(edges):
        adjacency.setdefault(edge.source_repository_id, [])
        if edge.target_repository_id not in adjacency[edge.source_repository_id]:
            adjacency[edge.source_repository_id].append(edge.target_repository_id)
        adjacency.setdefault(edge.target_repository_id, [])
    return {key: sorted(value) for key, value in adjacency.items()}


def _tarjan(adjacency: Mapping[str, list[str]]) -> tuple[tuple[str, ...], ...]:
    index = 0
    stack: list[str] = []
    indexes: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    on_stack: set[str] = set()
    components: list[tuple[str, ...]] = []

    def strongconnect(node: str) -> None:
        nonlocal index
        indexes[node] = index
        lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for neighbor in adjacency.get(node, ()):
            if neighbor not in indexes:
                strongconnect(neighbor)
                lowlinks[node] = min(lowlinks[node], lowlinks[neighbor])
            elif neighbor in on_stack:
                lowlinks[node] = min(lowlinks[node], indexes[neighbor])
        if lowlinks[node] == indexes[node]:
            component = []
            while True:
                member = stack.pop()
                on_stack.remove(member)
                component.append(member)
                if member == node:
                    break
            if len(component) > 1:
                components.append(tuple(sorted(component)))

    for node in sorted(adjacency):
        if node not in indexes:
            strongconnect(node)
    return tuple(sorted(set(components)))


def _edge_by_pair(edges: Iterable[WorkspaceGraphEdge]) -> dict[tuple[str, str], WorkspaceGraphEdge]:
    values = {}
    for edge in sorted(_dependency_edges(edges), key=edge_sort_key):
        values.setdefault((edge.source_repository_id, edge.target_repository_id), edge)
    return values


def _representative_cycle(component: tuple[str, ...], adjacency: Mapping[str, list[str]], edges: Iterable[WorkspaceGraphEdge]) -> WorkspaceCycle:
    start = min(component)
    component_set = set(component)
    path = [start]
    current = start
    seen = {start}
    while True:
        candidates = [node for node in adjacency.get(current, ()) if node in component_set]
        if start in candidates and len(path) > 1:
            path.append(start)
            break
        next_node = next((node for node in candidates if node not in seen), candidates[0])
        if next_node in seen:
            path.append(next_node)
            break
        path.append(next_node)
        seen.add(next_node)
        current = next_node
    pair_edges = _edge_by_pair(edges)
    cycle_edges = []
    relationship_types = []
    scores = []
    for source, target in zip(path, path[1:]):
        edge = pair_edges.get((source, target))
        if edge:
            cycle_edges.append(_edge_identity_string(edge))
            relationship_types.append(edge.relationship_type)
            scores.append(edge.confidence_score)
    score = min(scores) if scores else 0.1
    return WorkspaceCycle(tuple(path), tuple(cycle_edges), tuple(relationship_types), _confidence_from_score(score))


def _components_and_cycles(
    node_ids: set[str],
    edges: tuple[WorkspaceGraphEdge, ...],
    max_components: int,
    max_cycles: int,
    diagnostics: list[WorkspaceGraphDiagnostic],
) -> tuple[tuple[StronglyConnectedComponent, ...], tuple[WorkspaceCycle, ...]]:
    adjacency = _adjacency(edges, node_ids)
    components_raw = _tarjan(adjacency)
    components = []
    cycles = []
    for component in components_raw[:max_components]:
        component_edges = [edge for edge in _dependency_edges(edges) if edge.source_repository_id in component and edge.target_repository_id in component]
        score = min((edge.confidence_score for edge in component_edges), default=0.1)
        relationship_types = tuple(edge.relationship_type for edge in component_edges)
        components.append(StronglyConnectedComponent(component, len(component_edges), relationship_types, _confidence_from_score(score)))
        diagnostics.append(_diagnostic(DIAGNOSTIC_STRONGLY_CONNECTED_COMPONENT_DETECTED, DIAGNOSTIC_SEVERITY_INFO, "Strongly connected component detected.", repository_ids=component))
        if len(cycles) < max_cycles:
            cycle = _representative_cycle(component, adjacency, edges)
            cycles.append(cycle)
            diagnostics.append(_diagnostic(DIAGNOSTIC_CYCLE_DETECTED, DIAGNOSTIC_SEVERITY_WARNING, "Dependency cycle detected.", repository_ids=cycle.repository_ids))
    return tuple(sorted(components, key=component_sort_key)), tuple(sorted(cycles, key=cycle_sort_key))


def _edge_identity_string(edge: WorkspaceGraphEdge) -> str:
    return "|".join(edge_identity_key(edge))


def _connectivity(node_ids: set[str], edges: tuple[WorkspaceGraphEdge, ...], diagnostics: list[WorkspaceGraphDiagnostic]) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    outgoing = {node_id: 0 for node_id in node_ids}
    incoming = {node_id: 0 for node_id in node_ids}
    for edge in _dependency_edges(edges):
        outgoing[edge.source_repository_id] = outgoing.get(edge.source_repository_id, 0) + 1
        incoming[edge.target_repository_id] = incoming.get(edge.target_repository_id, 0) + 1
    isolated = tuple(sorted(node_id for node_id in node_ids if outgoing.get(node_id, 0) == 0 and incoming.get(node_id, 0) == 0))
    roots = tuple(sorted(node_id for node_id in node_ids if outgoing.get(node_id, 0) > 0 and incoming.get(node_id, 0) == 0))
    leaves = tuple(sorted(node_id for node_id in node_ids if incoming.get(node_id, 0) > 0 and outgoing.get(node_id, 0) == 0))
    for node_id in isolated:
        diagnostics.append(_diagnostic(DIAGNOSTIC_ISOLATED_REPOSITORY, DIAGNOSTIC_SEVERITY_INFO, "Repository is isolated in dependency graph.", repository_ids=(node_id,)))
    return isolated, roots, leaves


def _summary(nodes: tuple[WorkspaceGraphNode, ...], edges: tuple[WorkspaceGraphEdge, ...], cycles: tuple[WorkspaceCycle, ...], isolated: tuple[str, ...], unresolved: tuple[UnresolvedRelationship, ...]) -> dict[str, Any]:
    return {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "explicit_edge_count": sum(1 for edge in edges if edge.explicit),
        "inferred_edge_count": sum(1 for edge in edges if edge.inferred),
        "high_confidence_edge_count": sum(1 for edge in edges if edge.confidence == CONFIDENCE_HIGH),
        "medium_confidence_edge_count": sum(1 for edge in edges if edge.confidence == CONFIDENCE_MEDIUM),
        "low_confidence_edge_count": sum(1 for edge in edges if edge.confidence == CONFIDENCE_LOW),
        "cycle_count": len(cycles),
        "isolated_repository_count": len(isolated),
        "unresolved_relationship_count": len(unresolved),
        "contract_edge_count": sum(1 for edge in edges if edge.contract_names),
    }


def _bound_diagnostics(diagnostics: Iterable[WorkspaceGraphDiagnostic], limit: int) -> tuple[WorkspaceGraphDiagnostic, ...]:
    values = tuple(sorted((_coerce_diagnostic(item) for item in diagnostics), key=diagnostic_sort_key))
    if len(values) <= limit:
        return values
    omitted = len(values) - limit
    return (*values[: limit - 1], _diagnostic(DIAGNOSTIC_GRAPH_DIAGNOSTIC_CAP_REACHED, DIAGNOSTIC_SEVERITY_WARNING, "Graph diagnostics were truncated.", details={"limit": limit, "omitted": omitted}))


def build_workspace_dependency_graph(
    workspace: Any,
    *,
    relationship_assessment: Any = None,
    discovery_result: Any = None,
    reference_relationship_hints: Iterable[Any] = (),
    contract_findings: Any = (),
    include_discovered: bool = False,
    max_nodes: int = DEFAULT_MAX_NODES,
    max_edges: int = DEFAULT_MAX_EDGES,
    max_evidence_per_node: int = DEFAULT_MAX_EVIDENCE_PER_NODE,
    max_evidence_per_edge: int = DEFAULT_MAX_EVIDENCE_PER_EDGE,
    max_contract_names_per_edge: int = DEFAULT_MAX_CONTRACT_NAMES_PER_EDGE,
    max_unresolved_relationships: int = DEFAULT_MAX_UNRESOLVED_RELATIONSHIPS,
    max_diagnostics: int = DEFAULT_MAX_DIAGNOSTICS,
    max_strongly_connected_components: int = DEFAULT_MAX_STRONGLY_CONNECTED_COMPONENTS,
    max_cycles: int = DEFAULT_MAX_CYCLES,
) -> WorkspaceDependencyGraph:
    """Build a deterministic workspace dependency graph from supplied data."""

    max_nodes = _validate_limit(max_nodes, "max_nodes")
    max_edges = _validate_limit(max_edges, "max_edges")
    max_evidence_per_node = _validate_limit(max_evidence_per_node, "max_evidence_per_node")
    max_evidence_per_edge = _validate_limit(max_evidence_per_edge, "max_evidence_per_edge")
    max_contract_names_per_edge = _validate_limit(max_contract_names_per_edge, "max_contract_names_per_edge")
    max_unresolved_relationships = _validate_limit(max_unresolved_relationships, "max_unresolved_relationships")
    max_diagnostics = _validate_limit(max_diagnostics, "max_diagnostics")
    max_strongly_connected_components = _validate_limit(max_strongly_connected_components, "max_strongly_connected_components")
    max_cycles = _validate_limit(max_cycles, "max_cycles")
    diagnostics: list[WorkspaceGraphDiagnostic] = []
    normalized_workspace = workspace_config.validate_workspace_config(_workspace_with_unique_repository_ids(workspace, diagnostics))
    assessment = _assessment_to_dict(relationship_assessment)
    discovery = _discovery_to_dict(discovery_result)
    nodes = _build_nodes(normalized_workspace, assessment, discovery, include_discovered, max_nodes, max_evidence_per_node, diagnostics)
    node_ids = {node.repository_id for node in nodes}
    edge_candidates = (
        *_explicit_relationships(normalized_workspace),
        *_assessment_relationships(assessment),
        *_relationship_candidates_from_input(reference_relationship_hints),
        *_contract_edges(_contract_findings_from_input(contract_findings)),
    )
    edges, unresolved = _merge_edges(edge_candidates, node_ids, max_edges, max_evidence_per_edge, max_contract_names_per_edge, max_unresolved_relationships, diagnostics)
    components, cycles = _components_and_cycles(node_ids, edges, max_strongly_connected_components, max_cycles, diagnostics)
    isolated, roots, leaves = _connectivity(node_ids, edges, diagnostics)
    summary = _summary(nodes, edges, cycles, isolated, unresolved)
    return WorkspaceDependencyGraph(
        schema_version=WORKSPACE_GRAPH_SCHEMA_VERSION,
        nodes=nodes,
        edges=edges,
        cycles=cycles,
        strongly_connected_components=components,
        isolated_repository_ids=isolated,
        root_repository_ids=roots,
        leaf_repository_ids=leaves,
        unresolved_relationships=unresolved,
        diagnostics=_bound_diagnostics(diagnostics, max_diagnostics),
        summary=summary,
        metadata={"dependency_edge_types": DEPENDENCY_RELATIONSHIP_TYPES, "symmetric_edge_types": SYMMETRIC_RELATIONSHIP_TYPES},
    )


def workspace_dependency_graph_to_dict(graph: WorkspaceDependencyGraph) -> dict[str, Any]:
    """Return the stable JSON-ready workspace dependency graph."""

    if not isinstance(graph, WorkspaceDependencyGraph):
        raise TypeError("graph must be a WorkspaceDependencyGraph")
    return graph.to_dict()
