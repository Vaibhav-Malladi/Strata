"""Workspace readiness and diagnostic aggregation for Part Q8.

Q8 consumes already-produced workspace stage outputs, diagnostics, and failure
records. It does not rerun configuration, discovery, extraction, comparison,
graph construction, or context rendering.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import json
import math
from typing import Any

import strata.utils.workspace_context as workspace_context
import strata.utils.workspace_graph as workspace_graph


WORKSPACE_READINESS_SCHEMA_VERSION = 1

STATUS_READY = "ready"
STATUS_DEGRADED = "degraded"
STATUS_BLOCKED = "blocked"
STATUS_UNAVAILABLE = "unavailable"
STATUS_NOT_CONFIGURED = "not_configured"
READINESS_STATUSES = (
    STATUS_READY,
    STATUS_DEGRADED,
    STATUS_BLOCKED,
    STATUS_UNAVAILABLE,
    STATUS_NOT_CONFIGURED,
)
STATUS_PRECEDENCE = (
    STATUS_BLOCKED,
    STATUS_UNAVAILABLE,
    STATUS_DEGRADED,
    STATUS_READY,
    STATUS_NOT_CONFIGURED,
)

STAGE_CONFIGURATION = "configuration"
STAGE_DISCOVERY = "discovery"
STAGE_RELATIONSHIP_ASSESSMENT = "relationship_assessment"
STAGE_REFERENCE_EXTRACTION = "reference_extraction"
STAGE_CONTRACT_COMPARISON = "contract_comparison"
STAGE_GRAPH_CONSTRUCTION = "graph_construction"
STAGE_CONTEXT_REPRESENTATION = "context_representation"
STAGES = (
    STAGE_CONFIGURATION,
    STAGE_DISCOVERY,
    STAGE_RELATIONSHIP_ASSESSMENT,
    STAGE_REFERENCE_EXTRACTION,
    STAGE_CONTRACT_COMPARISON,
    STAGE_GRAPH_CONSTRUCTION,
    STAGE_CONTEXT_REPRESENTATION,
)

SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"
SEVERITY_ERROR = "error"
SEVERITIES = (SEVERITY_INFO, SEVERITY_WARNING, SEVERITY_ERROR)

DIAGNOSTIC_WORKSPACE_NOT_CONFIGURED = "workspace_not_configured"
DIAGNOSTIC_REQUIRED_REPOSITORY_MISSING = "workspace_required_repository_missing"
DIAGNOSTIC_STAGE_FAILED = "workspace_stage_failed"
DIAGNOSTIC_STAGE_DEGRADED = "workspace_stage_degraded"
DIAGNOSTIC_EVIDENCE_TRUNCATED = "workspace_evidence_truncated"
DIAGNOSTIC_BUDGET_EXHAUSTED = "workspace_budget_exhausted"
DIAGNOSTIC_GRAPH_UNAVAILABLE = "workspace_graph_unavailable"
DIAGNOSTIC_CONTEXT_UNAVAILABLE = "workspace_context_unavailable"
DIAGNOSTIC_SENSITIVE_DATA_REDACTED = "workspace_sensitive_data_redacted"
DIAGNOSTIC_PARTIAL_RESULTS_AVAILABLE = "workspace_partial_results_available"
DIAGNOSTIC_DIAGNOSTIC_CAP_REACHED = "workspace_diagnostic_cap_reached"
DIAGNOSTIC_CODES = (
    DIAGNOSTIC_WORKSPACE_NOT_CONFIGURED,
    DIAGNOSTIC_REQUIRED_REPOSITORY_MISSING,
    DIAGNOSTIC_STAGE_FAILED,
    DIAGNOSTIC_STAGE_DEGRADED,
    DIAGNOSTIC_EVIDENCE_TRUNCATED,
    DIAGNOSTIC_BUDGET_EXHAUSTED,
    DIAGNOSTIC_GRAPH_UNAVAILABLE,
    DIAGNOSTIC_CONTEXT_UNAVAILABLE,
    DIAGNOSTIC_SENSITIVE_DATA_REDACTED,
    DIAGNOSTIC_PARTIAL_RESULTS_AVAILABLE,
    DIAGNOSTIC_DIAGNOSTIC_CAP_REACHED,
)

DEFAULT_MAX_DIAGNOSTICS = 200

DIAGNOSTIC_FIELD_ORDER = (
    "stage",
    "code",
    "severity",
    "summary",
    "repository_ids",
    "details",
    "source",
)
STAGE_FIELD_ORDER = (
    "stage",
    "status",
    "summary",
    "diagnostic_count",
    "warning_count",
    "error_count",
    "skipped_count",
    "truncated_count",
)
RESULT_FIELD_ORDER = (
    "schema_version",
    "status",
    "summary",
    "stages",
    "diagnostics",
    "recommended_action",
    "safe_fallback",
    "metadata",
)


class WorkspaceReadinessError(ValueError):
    """Raised when Q8 readiness contracts are invalid."""


@dataclass(frozen=True, slots=True)
class WorkspaceReadinessDiagnostic:
    stage: str
    code: str
    severity: str
    summary: str
    repository_ids: tuple[str, ...] = ()
    details: Mapping[str, Any] | None = None
    source: str = "workspace"

    def __post_init__(self) -> None:
        object.__setattr__(self, "stage", _choice(self.stage, "stage", STAGES))
        object.__setattr__(self, "code", _nonempty(self.code, "code"))
        object.__setattr__(self, "severity", _choice(self.severity, "severity", SEVERITIES))
        object.__setattr__(self, "summary", _nonempty(self.summary, "summary"))
        object.__setattr__(self, "repository_ids", tuple(sorted(set(_string_tuple(self.repository_ids)))))
        object.__setattr__(self, "details", _copy_json(self.details or {}, "details"))
        object.__setattr__(self, "source", _nonempty(self.source, "source"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "code": self.code,
            "severity": self.severity,
            "summary": self.summary,
            "repository_ids": list(self.repository_ids),
            "details": _json_ready(self.details or {}),
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class WorkspaceStageStatus:
    stage: str
    status: str
    summary: str
    diagnostic_count: int = 0
    warning_count: int = 0
    error_count: int = 0
    skipped_count: int = 0
    truncated_count: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "stage", _choice(self.stage, "stage", STAGES))
        object.__setattr__(self, "status", _choice(self.status, "status", READINESS_STATUSES))
        object.__setattr__(self, "summary", _nonempty(self.summary, "summary"))
        for name in ("diagnostic_count", "warning_count", "error_count", "skipped_count", "truncated_count"):
            object.__setattr__(self, name, _nonnegative_int(getattr(self, name), name))

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "status": self.status,
            "summary": self.summary,
            "diagnostic_count": self.diagnostic_count,
            "warning_count": self.warning_count,
            "error_count": self.error_count,
            "skipped_count": self.skipped_count,
            "truncated_count": self.truncated_count,
        }


@dataclass(frozen=True, slots=True)
class WorkspaceReadinessResult:
    schema_version: int
    status: str
    summary: str
    stages: tuple[WorkspaceStageStatus, ...]
    diagnostics: tuple[WorkspaceReadinessDiagnostic, ...]
    recommended_action: str | None
    safe_fallback: Mapping[str, Any]
    metadata: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.schema_version != WORKSPACE_READINESS_SCHEMA_VERSION:
            raise WorkspaceReadinessError("workspace readiness schema_version must be 1")
        object.__setattr__(self, "status", _choice(self.status, "status", READINESS_STATUSES))
        object.__setattr__(self, "summary", _nonempty(self.summary, "summary"))
        object.__setattr__(self, "stages", tuple(sorted((_coerce_stage(item) for item in self.stages), key=lambda item: STAGES.index(item.stage))))
        object.__setattr__(self, "diagnostics", tuple(sorted((_coerce_diagnostic(item) for item in self.diagnostics), key=diagnostic_sort_key)))
        if self.recommended_action is not None:
            object.__setattr__(self, "recommended_action", _nonempty(self.recommended_action, "recommended_action"))
        object.__setattr__(self, "safe_fallback", _copy_json(self.safe_fallback, "safe_fallback"))
        object.__setattr__(self, "metadata", _copy_json(self.metadata or {}, "metadata"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "summary": self.summary,
            "stages": [item.to_dict() for item in self.stages],
            "diagnostics": [item.to_dict() for item in self.diagnostics],
            "recommended_action": self.recommended_action,
            "safe_fallback": _json_ready(self.safe_fallback),
            "metadata": _json_ready(self.metadata or {}),
        }


def build_workspace_readiness(
    *,
    workspace_config: Any = None,
    discovery_result: Any = None,
    relationship_assessment: Any = None,
    reference_extraction: Any = None,
    contract_comparison: Any = None,
    graph: Any = None,
    context_representation: Any = None,
    stage_failures: Mapping[str, Any] | None = None,
    required_repository_ids: Iterable[str] = (),
    optional_repository_ids: Iterable[str] = (),
    workspace_requested: bool = True,
    max_diagnostics: int = DEFAULT_MAX_DIAGNOSTICS,
) -> WorkspaceReadinessResult:
    """Aggregate supplied workspace stage outputs into one readiness result."""

    max_diagnostics = _validate_limit(max_diagnostics, "max_diagnostics")
    if not workspace_requested and workspace_config is None:
        diagnostic = WorkspaceReadinessDiagnostic(
            STAGE_CONFIGURATION,
            DIAGNOSTIC_WORKSPACE_NOT_CONFIGURED,
            SEVERITY_INFO,
            "Workspace intelligence was not configured for this run.",
        )
        return _result(STATUS_NOT_CONFIGURED, (diagnostic,), (), "Workspace intelligence is not configured.", None, max_diagnostics)

    failures = dict(stage_failures or {})
    diagnostics: list[WorkspaceReadinessDiagnostic] = []
    stages: list[WorkspaceStageStatus] = []
    stage_inputs = {
        STAGE_CONFIGURATION: workspace_config,
        STAGE_DISCOVERY: discovery_result,
        STAGE_RELATIONSHIP_ASSESSMENT: relationship_assessment,
        STAGE_REFERENCE_EXTRACTION: reference_extraction,
        STAGE_CONTRACT_COMPARISON: contract_comparison,
        STAGE_GRAPH_CONSTRUCTION: graph,
        STAGE_CONTEXT_REPRESENTATION: context_representation,
    }

    repository_ids = _repository_ids(workspace_config, graph)
    for repository_id in sorted(set(required_repository_ids)):
        if repository_id not in repository_ids:
            diagnostics.append(
                WorkspaceReadinessDiagnostic(
                    STAGE_CONFIGURATION,
                    DIAGNOSTIC_REQUIRED_REPOSITORY_MISSING,
                    SEVERITY_ERROR,
                    "Required configured repository is missing.",
                    (repository_id,),
                    {"required": True},
                )
            )
    for repository_id in sorted(set(optional_repository_ids)):
        if repository_id not in repository_ids:
            diagnostics.append(
                WorkspaceReadinessDiagnostic(
                    STAGE_CONFIGURATION,
                    DIAGNOSTIC_STAGE_DEGRADED,
                    SEVERITY_WARNING,
                    "Optional workspace repository is missing.",
                    (repository_id,),
                    {"required": False},
                )
            )

    for stage in STAGES:
        stage_diagnostics = _diagnostics_from_stage(stage, stage_inputs.get(stage))
        stage_diagnostics.extend(_failure_diagnostics(stage, failures.get(stage)))
        diagnostics.extend(stage_diagnostics)
        stages.append(_stage_status(stage, stage_inputs.get(stage), stage_diagnostics, failures.get(stage)))

    if graph is None and workspace_config is not None:
        diagnostics.append(WorkspaceReadinessDiagnostic(STAGE_GRAPH_CONSTRUCTION, DIAGNOSTIC_GRAPH_UNAVAILABLE, SEVERITY_ERROR, "Workspace graph is unavailable."))
    if context_representation is None and graph is not None:
        diagnostics.append(WorkspaceReadinessDiagnostic(STAGE_CONTEXT_REPRESENTATION, DIAGNOSTIC_CONTEXT_UNAVAILABLE, SEVERITY_WARNING, "Workspace context representation is unavailable."))
    if _context_budget_exhausted(context_representation):
        diagnostics.append(WorkspaceReadinessDiagnostic(STAGE_CONTEXT_REPRESENTATION, DIAGNOSTIC_BUDGET_EXHAUSTED, SEVERITY_WARNING, "Workspace context budget was exhausted."))
    if any(_redaction_code(diag) for diag in diagnostics):
        diagnostics.append(WorkspaceReadinessDiagnostic(STAGE_CONTEXT_REPRESENTATION, DIAGNOSTIC_SENSITIVE_DATA_REDACTED, SEVERITY_INFO, "Workspace sensitive data was redacted."))
    if diagnostics and any(stage_inputs.values()):
        diagnostics.append(WorkspaceReadinessDiagnostic(STAGE_CONTEXT_REPRESENTATION, DIAGNOSTIC_PARTIAL_RESULTS_AVAILABLE, SEVERITY_INFO, "Partial workspace results remain available."))

    bounded = _bound_diagnostics(diagnostics, max_diagnostics)
    status = _overall_status(bounded, stages, workspace_config, graph, context_representation)
    summary = _summary_for_status(status)
    action = _recommended_action(status, bounded)
    return WorkspaceReadinessResult(
        schema_version=WORKSPACE_READINESS_SCHEMA_VERSION,
        status=status,
        summary=summary,
        stages=tuple(stages),
        diagnostics=bounded,
        recommended_action=action,
        safe_fallback={
            "single_repository_context_available": True,
            "workspace_data_authoritative": status == STATUS_READY,
            "automatic_configuration_changes": False,
            "automatic_patches": False,
            "partial_workspace_data_labeled": status in {STATUS_DEGRADED, STATUS_BLOCKED, STATUS_UNAVAILABLE},
        },
        metadata={"builder": "workspace_readiness", "stage_count": len(STAGES)},
    )


def workspace_readiness_to_dict(result: WorkspaceReadinessResult | Mapping[str, Any]) -> dict[str, Any]:
    """Return the stable JSON-ready workspace readiness result."""

    if isinstance(result, WorkspaceReadinessResult):
        return result.to_dict()
    if isinstance(result, Mapping):
        return WorkspaceReadinessResult(
            schema_version=result["schema_version"],
            status=result["status"],
            summary=result["summary"],
            stages=tuple(result.get("stages", ())),
            diagnostics=tuple(result.get("diagnostics", ())),
            recommended_action=result.get("recommended_action"),
            safe_fallback=result.get("safe_fallback", {}),
            metadata=result.get("metadata"),
        ).to_dict()
    raise TypeError("result must be a WorkspaceReadinessResult or mapping")


def diagnostic_sort_key(diagnostic: WorkspaceReadinessDiagnostic) -> tuple[object, ...]:
    return (STAGES.index(diagnostic.stage), diagnostic.severity, diagnostic.code, diagnostic.repository_ids, _json_key(diagnostic.details or {}), diagnostic.summary)


def _result(status: str, diagnostics: tuple[WorkspaceReadinessDiagnostic, ...], stages: tuple[WorkspaceStageStatus, ...], summary: str, action: str | None, max_diagnostics: int) -> WorkspaceReadinessResult:
    return WorkspaceReadinessResult(
        WORKSPACE_READINESS_SCHEMA_VERSION,
        status,
        summary,
        stages,
        _bound_diagnostics(diagnostics, max_diagnostics),
        action,
        {
            "single_repository_context_available": True,
            "workspace_data_authoritative": False,
            "automatic_configuration_changes": False,
            "automatic_patches": False,
            "partial_workspace_data_labeled": False,
        },
        {"builder": "workspace_readiness"},
    )


def _diagnostics_from_stage(stage: str, value: Any) -> list[WorkspaceReadinessDiagnostic]:
    diagnostics = []
    payload = _to_mapping(value)
    if not payload:
        return diagnostics
    raw = payload.get("diagnostics", ())
    for item in raw or ():
        diagnostic = _normalize_source_diagnostic(stage, item)
        if diagnostic:
            diagnostics.append(diagnostic)
    if _context_budget_exhausted(value):
        diagnostics.append(WorkspaceReadinessDiagnostic(stage, DIAGNOSTIC_BUDGET_EXHAUSTED, SEVERITY_WARNING, "Stage exhausted its workspace budget."))
    return diagnostics


def _failure_diagnostics(stage: str, failure: Any) -> list[WorkspaceReadinessDiagnostic]:
    if failure is None:
        return []
    if isinstance(failure, Mapping):
        severity = str(failure.get("severity", SEVERITY_ERROR))
        summary = str(failure.get("summary", failure.get("message", "Workspace stage failed.")))
        details = {str(key): failure[key] for key in sorted(failure) if key not in {"severity", "summary", "message"}}
    else:
        severity = SEVERITY_ERROR
        summary = str(failure)
        details = {}
    if severity not in SEVERITIES:
        severity = SEVERITY_ERROR
    return [WorkspaceReadinessDiagnostic(stage, DIAGNOSTIC_STAGE_FAILED, severity, summary or "Workspace stage failed.", details=details)]


def _normalize_source_diagnostic(stage: str, value: Any) -> WorkspaceReadinessDiagnostic | None:
    item = value.to_dict() if hasattr(value, "to_dict") else dict(value) if isinstance(value, Mapping) else None
    if not isinstance(item, Mapping):
        return None
    severity = str(item.get("severity", SEVERITY_WARNING))
    if severity not in SEVERITIES:
        severity = SEVERITY_WARNING
    code = str(item.get("code", DIAGNOSTIC_STAGE_DEGRADED))
    summary = str(item.get("summary", item.get("message", code)))
    source_stage = str(item.get("stage", stage))
    if source_stage not in STAGES:
        source_stage = stage
    return WorkspaceReadinessDiagnostic(
        source_stage,
        code,
        severity,
        summary,
        _string_tuple(item.get("repository_ids", ())),
        {"source_code": code, "source_stage": stage},
        "workspace_stage",
    )


def _stage_status(stage: str, value: Any, diagnostics: list[WorkspaceReadinessDiagnostic], failure: Any) -> WorkspaceStageStatus:
    warning_count = sum(1 for item in diagnostics if item.severity == SEVERITY_WARNING)
    error_count = sum(1 for item in diagnostics if item.severity == SEVERITY_ERROR)
    skipped_count = _count_keywords(diagnostics, "skipped")
    truncated_count = _count_keywords(diagnostics, "truncated")
    if failure is not None and error_count:
        status = STATUS_UNAVAILABLE if stage in {STAGE_GRAPH_CONSTRUCTION, STAGE_CONTEXT_REPRESENTATION} else STATUS_BLOCKED
    elif error_count:
        status = STATUS_BLOCKED if stage == STAGE_CONFIGURATION else STATUS_DEGRADED
    elif warning_count or skipped_count or truncated_count:
        status = STATUS_DEGRADED
    elif value is None:
        status = STATUS_UNAVAILABLE if stage in {STAGE_GRAPH_CONSTRUCTION, STAGE_CONTEXT_REPRESENTATION} else STATUS_DEGRADED
    else:
        status = STATUS_READY
    return WorkspaceStageStatus(
        stage=stage,
        status=status,
        summary=_stage_summary(stage, status),
        diagnostic_count=len(diagnostics),
        warning_count=warning_count,
        error_count=error_count,
        skipped_count=skipped_count,
        truncated_count=truncated_count,
    )


def _overall_status(diagnostics: tuple[WorkspaceReadinessDiagnostic, ...], stages: list[WorkspaceStageStatus], workspace_config: Any, graph: Any, context: Any) -> str:
    if workspace_config is None:
        return STATUS_NOT_CONFIGURED
    if any(item.code == DIAGNOSTIC_REQUIRED_REPOSITORY_MISSING for item in diagnostics):
        return STATUS_BLOCKED
    if any(item.status == STATUS_BLOCKED for item in stages):
        return STATUS_BLOCKED
    if graph is None and any(item.stage == STAGE_GRAPH_CONSTRUCTION and item.severity == SEVERITY_ERROR for item in diagnostics):
        return STATUS_UNAVAILABLE
    if any(item.status == STATUS_UNAVAILABLE for item in stages if item.stage in {STAGE_GRAPH_CONSTRUCTION}) and graph is None:
        return STATUS_UNAVAILABLE
    if any(item.status == STATUS_DEGRADED for item in stages) or any(item.severity in {SEVERITY_WARNING, SEVERITY_ERROR} for item in diagnostics) or _context_budget_exhausted(context):
        return STATUS_DEGRADED
    return STATUS_READY


def _recommended_action(status: str, diagnostics: tuple[WorkspaceReadinessDiagnostic, ...]) -> str | None:
    if status == STATUS_NOT_CONFIGURED:
        return "Configure workspace repositories before using Workspace Intelligence."
    for diagnostic in diagnostics:
        if diagnostic.code == DIAGNOSTIC_REQUIRED_REPOSITORY_MISSING:
            repo = diagnostic.repository_ids[0] if diagnostic.repository_ids else "required repository"
            return f"Review missing repository path for {repo}."
    for diagnostic in diagnostics:
        if diagnostic.code == DIAGNOSTIC_BUDGET_EXHAUSTED:
            return "Increase context budget or narrow the task."
    for diagnostic in diagnostics:
        if diagnostic.severity == SEVERITY_ERROR and "contract" in diagnostic.code:
            return "Fix an error-level shared contract mismatch."
    if status == STATUS_DEGRADED:
        return "Continue with degraded workspace evidence."
    if status == STATUS_UNAVAILABLE:
        return "Continue with single-repository context and review workspace stage failures."
    return None


def _summary_for_status(status: str) -> str:
    return {
        STATUS_READY: "Workspace intelligence is ready for normal use.",
        STATUS_DEGRADED: "Workspace intelligence is available with degraded or partial evidence.",
        STATUS_BLOCKED: "Workspace intelligence is blocked by a critical workspace issue.",
        STATUS_UNAVAILABLE: "Workspace intelligence is unavailable for this run.",
        STATUS_NOT_CONFIGURED: "Workspace intelligence is not configured.",
    }[status]


def _repository_ids(workspace_config: Any, graph: Any) -> set[str]:
    ids = set()
    workspace = _to_mapping(workspace_config)
    for repo in workspace.get("repositories", ()) if workspace else ():
        if isinstance(repo, Mapping) and repo.get("id"):
            ids.add(str(repo["id"]))
    graph_payload = _to_mapping(graph)
    for node in graph_payload.get("nodes", ()) if graph_payload else ():
        if isinstance(node, Mapping) and node.get("repository_id"):
            ids.add(str(node["repository_id"]))
    return ids


def _context_budget_exhausted(value: Any) -> bool:
    payload = _to_mapping(value)
    if not payload:
        return False
    budget = payload.get("budget_summary", payload.get("budget", {}))
    return isinstance(budget, Mapping) and bool(budget.get("budget_exhausted"))


def _redaction_code(diagnostic: WorkspaceReadinessDiagnostic) -> bool:
    text = f"{diagnostic.code} {diagnostic.summary}".lower()
    return "redact" in text or "sensitive" in text


def _bound_diagnostics(diagnostics: Iterable[WorkspaceReadinessDiagnostic], limit: int) -> tuple[WorkspaceReadinessDiagnostic, ...]:
    values = tuple(sorted((_coerce_diagnostic(item) for item in diagnostics), key=diagnostic_sort_key))
    if len(values) <= limit:
        return values
    omitted = len(values) - limit
    cap = WorkspaceReadinessDiagnostic(
        STAGE_CONTEXT_REPRESENTATION,
        DIAGNOSTIC_DIAGNOSTIC_CAP_REACHED,
        SEVERITY_WARNING,
        "Workspace readiness diagnostics were truncated.",
        details={"limit": limit, "omitted": omitted},
    )
    if limit == 1:
        return (cap,)
    return (*values[: limit - 1], cap)


def _coerce_diagnostic(value: Any) -> WorkspaceReadinessDiagnostic:
    if isinstance(value, WorkspaceReadinessDiagnostic):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("diagnostic must be WorkspaceReadinessDiagnostic or mapping")
    return WorkspaceReadinessDiagnostic(
        stage=value["stage"],
        code=value["code"],
        severity=value["severity"],
        summary=value["summary"],
        repository_ids=tuple(value.get("repository_ids", ())),
        details=value.get("details"),
        source=value.get("source", "workspace"),
    )


def _coerce_stage(value: Any) -> WorkspaceStageStatus:
    if isinstance(value, WorkspaceStageStatus):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("stage must be WorkspaceStageStatus or mapping")
    return WorkspaceStageStatus(
        stage=value["stage"],
        status=value["status"],
        summary=value["summary"],
        diagnostic_count=value.get("diagnostic_count", 0),
        warning_count=value.get("warning_count", 0),
        error_count=value.get("error_count", 0),
        skipped_count=value.get("skipped_count", 0),
        truncated_count=value.get("truncated_count", 0),
    )


def _to_mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, workspace_graph.WorkspaceDependencyGraph):
        return value.to_dict()
    if isinstance(value, workspace_context.WorkspaceContextRepresentation):
        return value.to_dict()
    if hasattr(value, "to_dict"):
        converted = value.to_dict()
        return dict(converted) if isinstance(converted, Mapping) else {}
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _stage_summary(stage: str, status: str) -> str:
    label = stage.replace("_", " ")
    return f"{label} stage is {status}."


def _count_keywords(diagnostics: Iterable[WorkspaceReadinessDiagnostic], keyword: str) -> int:
    return sum(1 for item in diagnostics if keyword in f"{item.code} {item.summary}".lower())


def _copy_json(value: Any, name: str) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise WorkspaceReadinessError(f"{name} must be finite")
        return value
    if isinstance(value, Mapping):
        return {str(key): _copy_json(value[key], f"{name}.{key}") for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return tuple(_copy_json(item, f"{name}[]") for item in value)
    raise WorkspaceReadinessError(f"{name} must be JSON-ready")


def _json_ready(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _json_ready(value[key]) for key in sorted(value)}
    return value


def _json_key(value: Any) -> str:
    return json.dumps(_json_ready(value), sort_keys=True, separators=(",", ":"))


def _choice(value: Any, name: str, choices: tuple[str, ...]) -> str:
    text = _nonempty(value, name)
    if text not in choices:
        raise WorkspaceReadinessError(f"{name} must be one of: {', '.join(choices)}")
    return text


def _nonempty(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkspaceReadinessError(f"{name} must be a non-empty string")
    return value.strip()


def _string_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        return (str(value),) if str(value) else ()
    return tuple(str(item) for item in value if str(item))


def _nonnegative_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise WorkspaceReadinessError(f"{name} must be a non-negative integer")
    return value


def _validate_limit(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise WorkspaceReadinessError(f"{name} must be a positive integer")
    return value
