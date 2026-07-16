"""Journey readiness and safe-failure aggregation for Part P8.

This module consumes supplied stage outputs only. It does not rerun journey
stages, write files, prompt users, or modify repositories.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import json
from typing import Any

import strata.utils.user_journey as user_journey


JOURNEY_READINESS_SCHEMA_VERSION = 1

STATUS_READY = "ready"
STATUS_PARTIAL = "partial"
STATUS_BLOCKED = "blocked"
STATUS_NOT_FOUND = "not_found"
STATUS_UNSUPPORTED = "unsupported"
STATUS_UNAVAILABLE = "unavailable"
READINESS_STATUSES = (STATUS_READY, STATUS_PARTIAL, STATUS_BLOCKED, STATUS_NOT_FOUND, STATUS_UNSUPPORTED, STATUS_UNAVAILABLE)
STATUS_PRECEDENCE = (STATUS_BLOCKED, STATUS_UNAVAILABLE, STATUS_UNSUPPORTED, STATUS_NOT_FOUND, STATUS_PARTIAL, STATUS_READY)

STAGE_REQUEST = "request_validation"
STAGE_ENTRY_POINT_DETECTION = "entry_point_detection"
STAGE_FRONTEND_TRACING = "frontend_tracing"
STAGE_API_BOUNDARY_LINKING = "api_boundary_linking"
STAGE_BACKEND_TRACING = "backend_tracing"
STAGE_JOURNEY_ASSEMBLY = "journey_assembly"
STAGE_CONTEXT_REPRESENTATION = "context_representation"
STAGES = (STAGE_REQUEST, STAGE_ENTRY_POINT_DETECTION, STAGE_FRONTEND_TRACING, STAGE_API_BOUNDARY_LINKING, STAGE_BACKEND_TRACING, STAGE_JOURNEY_ASSEMBLY, STAGE_CONTEXT_REPRESENTATION)

DEFAULT_MAX_DIAGNOSTICS = 200


@dataclass(frozen=True, slots=True)
class JourneyStageStatus:
    stage: str
    status: str
    summary: str
    step_count: int = 0
    transition_count: int = 0
    gap_count: int = 0
    diagnostic_count: int = 0
    warning_count: int = 0
    error_count: int = 0
    truncated_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "status": self.status,
            "summary": self.summary,
            "step_count": self.step_count,
            "transition_count": self.transition_count,
            "gap_count": self.gap_count,
            "diagnostic_count": self.diagnostic_count,
            "warning_count": self.warning_count,
            "error_count": self.error_count,
            "truncated_count": self.truncated_count,
        }


@dataclass(frozen=True, slots=True)
class JourneyReadinessResult:
    schema_version: int
    status: str
    summary: str
    stages: tuple[JourneyStageStatus, ...]
    diagnostics: tuple[user_journey.JourneyDiagnostic, ...]
    recommended_action: str | None
    safe_fallback: Mapping[str, Any]
    metadata: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "summary": self.summary,
            "stages": [stage.to_dict() for stage in self.stages],
            "diagnostics": [diagnostic.to_dict() for diagnostic in self.diagnostics],
            "recommended_action": self.recommended_action,
            "safe_fallback": _json_ready(self.safe_fallback),
            "metadata": _json_ready(self.metadata),
        }


def build_journey_readiness(
    *,
    request: user_journey.JourneyRequest | Mapping[str, Any] | None = None,
    entry_point_detection: Any = None,
    frontend_tracing: Any = None,
    api_boundary_linking: Any = None,
    backend_tracing: Any = None,
    journey_assembly: Any = None,
    context_representation: Any = None,
    stage_failures: Mapping[str, Any] | None = None,
    unsupported_patterns: Iterable[str] = (),
    max_diagnostics: int = DEFAULT_MAX_DIAGNOSTICS,
) -> JourneyReadinessResult:
    """Aggregate supplied Part P stage outputs into readiness."""

    stage_failures = dict(stage_failures or {})
    diagnostics: list[user_journey.JourneyDiagnostic] = []
    stages = []
    stage_inputs = {
        STAGE_REQUEST: request,
        STAGE_ENTRY_POINT_DETECTION: entry_point_detection,
        STAGE_FRONTEND_TRACING: frontend_tracing,
        STAGE_API_BOUNDARY_LINKING: api_boundary_linking,
        STAGE_BACKEND_TRACING: backend_tracing,
        STAGE_JOURNEY_ASSEMBLY: journey_assembly,
        STAGE_CONTEXT_REPRESENTATION: context_representation,
    }
    for stage in STAGES:
        status = _stage_status(stage, stage_inputs.get(stage), stage_failures.get(stage), tuple(unsupported_patterns))
        stages.append(status)
        diagnostics.extend(_stage_diagnostics(stage_inputs.get(stage)))
        diagnostics.extend(_gap_diagnostics(stage_inputs.get(stage)))
        if stage in stage_failures:
            diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_JOURNEY_READINESS_UNAVAILABLE, user_journey.DIAGNOSTIC_SEVERITY_WARNING, f"{stage} failed.", details={"failure": str(stage_failures[stage])}))
    if unsupported_patterns:
        diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_JOURNEY_UNSUPPORTED_PATTERN, user_journey.DIAGNOSTIC_SEVERITY_WARNING, "Unsupported journey pattern was supplied.", details={"patterns": tuple(sorted(str(item) for item in unsupported_patterns))}))
    status = _overall_status(stages, diagnostics)
    if status == STATUS_BLOCKED:
        diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_JOURNEY_READINESS_BLOCKED, user_journey.DIAGNOSTIC_SEVERITY_ERROR, "Journey readiness is blocked by required unresolved information."))
    diagnostics = _bound_diagnostics(diagnostics, max_diagnostics)
    summary = _summary(status, stages)
    return JourneyReadinessResult(
        schema_version=JOURNEY_READINESS_SCHEMA_VERSION,
        status=status,
        summary=summary,
        stages=tuple(sorted(stages, key=lambda item: STAGES.index(item.stage))),
        diagnostics=tuple(sorted(diagnostics, key=user_journey.diagnostic_sort_key)),
        recommended_action=_recommended_action(status, stages, diagnostics),
        safe_fallback={
            "normal_repository_context_available": True,
            "workspace_context_available": True,
            "journey_context_safe_to_skip": status != STATUS_READY,
            "partial_journey_data_labeled": status in {STATUS_PARTIAL, STATUS_BLOCKED, STATUS_UNAVAILABLE, STATUS_UNSUPPORTED},
            "no_automatic_writes": True,
            "no_patches_applied": True,
        },
        metadata={"builder": "journey_readiness", "stage_count": len(stages)},
    )


def journey_readiness_to_dict(result: JourneyReadinessResult | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(result, JourneyReadinessResult):
        return result.to_dict()
    if isinstance(result, Mapping):
        return dict(result)
    raise TypeError("result must be a JourneyReadinessResult or mapping")


def _stage_status(stage: str, value: Any, failure: Any, unsupported: tuple[str, ...]) -> JourneyStageStatus:
    if failure is not None:
        return JourneyStageStatus(stage, STATUS_UNAVAILABLE, "Stage failed before producing reliable journey data.")
    payload = _payload(value)
    if stage == STAGE_REQUEST:
        return JourneyStageStatus(stage, STATUS_READY if value is not None else STATUS_NOT_FOUND, "Journey request supplied." if value is not None else "Journey request was not supplied.")
    if unsupported:
        return JourneyStageStatus(stage, STATUS_UNSUPPORTED, "Unsupported journey pattern remains.")
    steps = len(payload.get("steps", ()))
    transitions = len(payload.get("transitions", ()))
    gaps = len(payload.get("gaps", ()))
    diagnostics = payload.get("diagnostics", ())
    warnings = sum(1 for item in diagnostics if item.get("severity") == user_journey.DIAGNOSTIC_SEVERITY_WARNING)
    errors = sum(1 for item in diagnostics if item.get("severity") == user_journey.DIAGNOSTIC_SEVERITY_ERROR)
    truncated = _truncated_count(payload)
    if value is None:
        status = STATUS_NOT_FOUND
        summary = "Stage output was not supplied."
    elif errors:
        status = STATUS_BLOCKED
        summary = "Stage produced blocking diagnostics."
    elif gaps or warnings or truncated:
        status = STATUS_PARTIAL
        summary = "Stage produced useful partial journey data."
    elif steps or transitions or payload.get("entry_points") or payload.get("journeys"):
        status = STATUS_READY
        summary = "Stage produced useful journey data."
    else:
        status = STATUS_NOT_FOUND
        summary = "Stage did not find journey data."
    return JourneyStageStatus(stage, status, summary, steps, transitions, gaps, len(tuple(diagnostics)), warnings, errors, truncated)


def _overall_status(stages: Iterable[JourneyStageStatus], diagnostics: Iterable[user_journey.JourneyDiagnostic]) -> str:
    stage_statuses = {stage.status for stage in stages}
    if any(diagnostic.severity == user_journey.DIAGNOSTIC_SEVERITY_ERROR for diagnostic in diagnostics):
        return STATUS_BLOCKED
    for status in STATUS_PRECEDENCE:
        if status in stage_statuses:
            if status == STATUS_NOT_FOUND and any(item in stage_statuses for item in (STATUS_READY, STATUS_PARTIAL)):
                continue
            return status
    return STATUS_READY


def _recommended_action(status: str, stages: Iterable[JourneyStageStatus], diagnostics: Iterable[user_journey.JourneyDiagnostic]) -> str | None:
    codes = {diagnostic.code for diagnostic in diagnostics}
    if status == STATUS_NOT_FOUND:
        return "Provide a starting path or symbol."
    if user_journey.DIAGNOSTIC_API_TARGET_AMBIGUOUS in codes:
        return "Resolve ambiguous API port ownership."
    if user_journey.DIAGNOSTIC_TARGET_REPOSITORY_UNKNOWN in codes:
        return "Add the backend repository to workspace configuration."
    if user_journey.DIAGNOSTIC_BACKEND_SYMBOL_NOT_FOUND in codes:
        return "Include the handler file in selected paths."
    if status == STATUS_BLOCKED:
        return "Review unresolved authorization boundary."
    if status == STATUS_PARTIAL:
        return "Continue with a partial journey."
    if status == STATUS_UNSUPPORTED:
        return "Narrow the task to one supported user action."
    if status == STATUS_UNAVAILABLE:
        return "Retry the unavailable journey stage with explicit selected files."
    return None


def _stage_diagnostics(value: Any) -> tuple[user_journey.JourneyDiagnostic, ...]:
    payload = _payload(value)
    return tuple(_coerce_diagnostic(item) for item in payload.get("diagnostics", ()))


def _gap_diagnostics(value: Any) -> tuple[user_journey.JourneyDiagnostic, ...]:
    payload = _payload(value)
    diagnostics = []
    for gap in payload.get("gaps", ()):
        item = gap.to_dict() if hasattr(gap, "to_dict") else gap if isinstance(gap, Mapping) else {}
        reason = item.get("reason")
        if reason == user_journey.GAP_REASON_API_TARGET_AMBIGUOUS:
            diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_API_TARGET_AMBIGUOUS, user_journey.DIAGNOSTIC_SEVERITY_WARNING, "API target is ambiguous.", details={"source_gap": reason}))
        elif reason == user_journey.GAP_REASON_TARGET_REPOSITORY_UNKNOWN:
            diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_TARGET_REPOSITORY_UNKNOWN, user_journey.DIAGNOSTIC_SEVERITY_ERROR, "Target repository is unknown.", details={"source_gap": reason}))
        elif reason == user_journey.GAP_REASON_SYMBOL_NOT_FOUND:
            diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_BACKEND_SYMBOL_NOT_FOUND, user_journey.DIAGNOSTIC_SEVERITY_WARNING, "Backend symbol was not found.", details={"source_gap": reason}))
    return tuple(diagnostics)


def _bound_diagnostics(diagnostics: Iterable[user_journey.JourneyDiagnostic], limit: int) -> list[user_journey.JourneyDiagnostic]:
    values = list(sorted(diagnostics, key=user_journey.diagnostic_sort_key))
    if len(values) <= limit:
        return values
    omitted = len(values) - limit + 1
    return [
        *values[: limit - 1],
        _diagnostic(user_journey.DIAGNOSTIC_JOURNEY_DIAGNOSTIC_CAP_REACHED, user_journey.DIAGNOSTIC_SEVERITY_WARNING, "Journey readiness diagnostics were truncated.", details={"limit": limit, "omitted": omitted}),
    ]


def _summary(status: str, stages: Iterable[JourneyStageStatus]) -> str:
    counts = {stage.status: 0 for stage in stages}
    for stage in stages:
        counts[stage.status] = counts.get(stage.status, 0) + 1
    return f"Journey readiness is {status}; " + ", ".join(f"{key}: {counts[key]}" for key in sorted(counts))


def _truncated_count(payload: Mapping[str, Any]) -> int:
    metadata = payload.get("metadata", {})
    omitted = metadata.get("omitted_counts", payload.get("omitted_counts", {})) if isinstance(metadata, Mapping) else payload.get("omitted_counts", {})
    if isinstance(omitted, Mapping):
        return sum(int(value) for value in omitted.values() if isinstance(value, int))
    return 0


def _payload(value: Any) -> Mapping[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, Mapping):
        return value
    return {}


def _coerce_diagnostic(value: user_journey.JourneyDiagnostic | Mapping[str, Any]) -> user_journey.JourneyDiagnostic:
    if isinstance(value, user_journey.JourneyDiagnostic):
        return value
    return user_journey.JourneyDiagnostic(**dict(value))


def _diagnostic(code: str, severity: str, summary: str, *, details: Mapping[str, Any] | None = None) -> user_journey.JourneyDiagnostic:
    return user_journey.JourneyDiagnostic(code=code, severity=severity, summary=summary, details=details)


def _json_ready(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, Mapping):
        return {key: _json_ready(value[key]) for key in sorted(value)}
    return value
