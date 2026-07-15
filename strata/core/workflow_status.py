from collections.abc import Mapping

from strata.core.diagnostic_explanations import summarize_diagnostic_explanations
from strata.core.diagnostics import (
    DIAGNOSTIC_SEVERITY_ERROR,
    DIAGNOSTIC_SEVERITY_INFO,
    DIAGNOSTIC_SEVERITY_WARNING,
    normalize_diagnostic_event,
    summarize_diagnostic_events,
)
from strata.core.workflow_state import (
    NEXT_ACTION_APPLY_PATCH,
    NEXT_ACTION_INSPECT_DIAGNOSTICS,
    NEXT_ACTION_PREPARE_CONTEXT,
    NEXT_ACTION_REPAIR_RUN_STATE,
    NEXT_ACTION_REQUEST_AI_RESPONSE,
    NEXT_ACTION_REVIEW_RESPONSE,
    NEXT_ACTION_RUN_VERIFICATION,
    NEXT_ACTION_WORKFLOW_COMPLETE,
    WORKFLOW_STATUS_BLOCKED,
    WORKFLOW_STATUS_COMPLETE,
    WORKFLOW_STATUS_FAILED,
    build_workflow_state_summary,
    suggest_next_workflow_action,
    validate_workflow_state,
)


WORKFLOW_HEALTH_HEALTHY = "healthy"
WORKFLOW_HEALTH_ATTENTION = "attention"
WORKFLOW_HEALTH_BLOCKED = "blocked"
WORKFLOW_HEALTH_INVALID = "invalid"
WORKFLOW_HEALTH_COMPLETE = "complete"
WORKFLOW_HEALTH_VALUES = (
    WORKFLOW_HEALTH_HEALTHY,
    WORKFLOW_HEALTH_ATTENTION,
    WORKFLOW_HEALTH_BLOCKED,
    WORKFLOW_HEALTH_INVALID,
    WORKFLOW_HEALTH_COMPLETE,
)

STEP_PREPARE_CONTEXT = "prepare_context"
STEP_REQUEST_AI_RESPONSE = "request_ai_response"
STEP_REVIEW_RESPONSE = "review_response"
STEP_APPLY_PATCH = "apply_patch"
STEP_RUN_VERIFICATION = "run_verification"
STEP_WORKFLOW_COMPLETE = "workflow_complete"
STEP_REPAIR_RUN_STATE = "repair_run_state"
STEP_INSPECT_DIAGNOSTICS = "inspect_diagnostics"
WORKFLOW_STEPS = (
    STEP_PREPARE_CONTEXT,
    STEP_REQUEST_AI_RESPONSE,
    STEP_REVIEW_RESPONSE,
    STEP_APPLY_PATCH,
    STEP_RUN_VERIFICATION,
    STEP_WORKFLOW_COMPLETE,
)

_SUCCESS_VALUES = {"pass", "passed", "success", "succeeded", "complete", "completed"}
_FAILURE_VALUES = {"fail", "failed", "failure", "error", "errored", "blocked"}

_ACTION_LABELS = {
    NEXT_ACTION_REPAIR_RUN_STATE: "Repair or regenerate the run state",
    NEXT_ACTION_PREPARE_CONTEXT: "Prepare project context",
    NEXT_ACTION_REQUEST_AI_RESPONSE: "Request an AI response",
    NEXT_ACTION_REVIEW_RESPONSE: "Review the proposed changes",
    NEXT_ACTION_APPLY_PATCH: "Apply the reviewed patch",
    NEXT_ACTION_RUN_VERIFICATION: "Run verification",
    NEXT_ACTION_WORKFLOW_COMPLETE: "Workflow complete",
    NEXT_ACTION_INSPECT_DIAGNOSTICS: "Inspect reported issues",
}

_STEP_TEXT = {
    STEP_PREPARE_CONTEXT: (
        "Prepare the project context.",
        "Strata needs a valid context package before an AI response can be reviewed safely.",
    ),
    STEP_REQUEST_AI_RESPONSE: (
        "Send the prepared context to your AI tool.",
        "The project context is ready, but no AI response has been received yet.",
    ),
    STEP_REVIEW_RESPONSE: (
        "Review the proposed changes.",
        "Strata has received a response, but it has not been approved yet.",
    ),
    STEP_APPLY_PATCH: (
        "Apply the reviewed patch.",
        "The proposed changes passed review and are ready for the normal safe apply workflow.",
    ),
    STEP_RUN_VERIFICATION: (
        "Verify the applied changes.",
        "The patch was applied, but verification has not completed successfully yet.",
    ),
    STEP_WORKFLOW_COMPLETE: (
        "Workflow complete.",
        "The patch was reviewed, applied, and verified successfully.",
    ),
    STEP_REPAIR_RUN_STATE: (
        "Repair the workflow state.",
        "The current run state is incomplete or invalid and should be regenerated before continuing.",
    ),
    STEP_INSPECT_DIAGNOSTICS: (
        "Inspect the reported issues.",
        "Strata found a blocking problem that must be resolved before the workflow can continue.",
    ),
}


def build_workflow_status(
    run_state,
    *,
    diagnostics=None,
    explanations=None,
) -> dict[str, object]:
    """Build a deterministic JSON-ready workflow status summary."""

    state = run_state if isinstance(run_state, Mapping) else {}
    m1_diagnostics = validate_workflow_state(run_state)
    normalized_diagnostics = _normalize_diagnostics(m1_diagnostics, default_source="workflow_state")
    if diagnostics is not None:
        normalized_diagnostics.extend(_normalize_diagnostics(diagnostics))
    diagnostic_summary = summarize_diagnostic_events(normalized_diagnostics)
    workflow_summary = build_workflow_state_summary(run_state)
    explanation_summary = _summarize_explanations(explanations)

    invalid = bool(m1_diagnostics)
    explicit_blocked = _explicit_blocked(state, workflow_summary)
    blocking_issues = int(diagnostic_summary["errors"])
    warning_count = int(diagnostic_summary["warnings"])
    current_step = _current_step(state, invalid, explicit_blocked, workflow_summary)
    completed_steps = _completed_steps(state)
    pending_steps = _pending_steps(current_step, completed_steps)
    next_action = _next_action(state, m1_diagnostics, current_step, invalid, explicit_blocked, blocking_issues)
    health = _health(invalid, explicit_blocked, current_step, blocking_issues, warning_count)
    status = _status_value(current_step, health)
    title, summary = _STEP_TEXT[current_step]

    details = {
        "diagnostic_total": int(diagnostic_summary["total"]),
        "explanation_total": int(explanation_summary.get("total", 0)),
        "primary_issue_code": _primary_issue_code(normalized_diagnostics),
        "primary_next_action": explanation_summary.get("primary_next_action"),
    }

    return {
        "status": status,
        "health": health,
        "title": title,
        "summary": summary,
        "current_step": current_step,
        "completed_steps": completed_steps,
        "pending_steps": pending_steps,
        "blocking_issues": blocking_issues,
        "warning_count": warning_count,
        "next_action": next_action,
        "next_action_label": _ACTION_LABELS[next_action],
        "details": details,
    }


def render_workflow_status_text(status_summary) -> str:
    """Render a concise deterministic plain-text workflow status block."""

    summary = _status_mapping(status_summary)
    return "\n".join(
        [
            f"Status: {_display_value(summary.get('status'))}",
            f"Current step: {summary.get('title', '')}",
            f"Blocking issues: {summary.get('blocking_issues', 0)}",
            f"Warnings: {summary.get('warning_count', 0)}",
            f"Next action: {summary.get('next_action_label', '')}",
        ]
    )


def _normalize_diagnostics(diagnostics, *, default_source=None) -> list[dict[str, object]]:
    if not isinstance(diagnostics, (list, tuple)):
        return []
    normalized = []
    for diagnostic in diagnostics:
        normalized.append(normalize_diagnostic_event(diagnostic, default_source=default_source))
    return normalized


def _summarize_explanations(explanations) -> dict[str, object]:
    if not isinstance(explanations, (list, tuple)):
        return {
            "total": 0,
            "errors": 0,
            "warnings": 0,
            "has_blocking_issues": False,
            "primary_next_action": None,
        }
    return summarize_diagnostic_explanations(explanations)


def _current_step(
    state: Mapping,
    invalid: bool,
    explicit_blocked: bool,
    workflow_summary: Mapping,
) -> str:
    if invalid:
        return STEP_REPAIR_RUN_STATE
    if explicit_blocked:
        return STEP_INSPECT_DIAGNOSTICS
    if _verification_passed(state):
        return STEP_WORKFLOW_COMPLETE
    if _patch_applied(state):
        return STEP_RUN_VERIFICATION
    if _review_passed(state):
        return STEP_APPLY_PATCH
    if _response_received(state):
        return STEP_REVIEW_RESPONSE
    if bool(workflow_summary.get("context_ready")):
        return STEP_REQUEST_AI_RESPONSE
    return STEP_PREPARE_CONTEXT


def _completed_steps(state: Mapping) -> list[str]:
    completed = []
    if _context_ready_evidence(state):
        completed.append(STEP_PREPARE_CONTEXT)
    if _response_received(state):
        completed.append(STEP_REQUEST_AI_RESPONSE)
    if _review_passed(state):
        completed.append(STEP_REVIEW_RESPONSE)
    if _patch_applied(state):
        completed.append(STEP_APPLY_PATCH)
    if _verification_passed(state):
        completed.append(STEP_RUN_VERIFICATION)
        completed.append(STEP_WORKFLOW_COMPLETE)
    return [step for step in WORKFLOW_STEPS if step in completed]


def _pending_steps(current_step: str, completed_steps: list[str]) -> list[str]:
    if current_step in {STEP_REPAIR_RUN_STATE, STEP_INSPECT_DIAGNOSTICS}:
        return [current_step]
    completed = set(completed_steps)
    pending = [step for step in WORKFLOW_STEPS if step not in completed]
    if current_step in WORKFLOW_STEPS:
        start = WORKFLOW_STEPS.index(current_step)
        pending = [step for step in pending if WORKFLOW_STEPS.index(step) >= start]
    return pending


def _next_action(
    state: Mapping,
    m1_diagnostics: list[dict[str, object]],
    current_step: str,
    invalid: bool,
    explicit_blocked: bool,
    blocking_issues: int,
) -> str:
    if invalid:
        return NEXT_ACTION_REPAIR_RUN_STATE
    if explicit_blocked or blocking_issues > 0:
        return NEXT_ACTION_INSPECT_DIAGNOSTICS
    if current_step == STEP_REPAIR_RUN_STATE:
        return NEXT_ACTION_REPAIR_RUN_STATE
    if current_step == STEP_INSPECT_DIAGNOSTICS:
        return NEXT_ACTION_INSPECT_DIAGNOSTICS
    return suggest_next_workflow_action(dict(state), m1_diagnostics)


def _health(
    invalid: bool,
    explicit_blocked: bool,
    current_step: str,
    blocking_issues: int,
    warning_count: int,
) -> str:
    if invalid:
        return WORKFLOW_HEALTH_INVALID
    if explicit_blocked or blocking_issues > 0:
        return WORKFLOW_HEALTH_BLOCKED
    if current_step == STEP_WORKFLOW_COMPLETE:
        return WORKFLOW_HEALTH_COMPLETE
    if warning_count > 0 or current_step in {
        STEP_REVIEW_RESPONSE,
        STEP_APPLY_PATCH,
        STEP_RUN_VERIFICATION,
    }:
        return WORKFLOW_HEALTH_ATTENTION
    return WORKFLOW_HEALTH_HEALTHY


def _status_value(current_step: str, health: str) -> str:
    if health == WORKFLOW_HEALTH_INVALID:
        return "invalid"
    if health == WORKFLOW_HEALTH_BLOCKED:
        return "blocked"
    if current_step == STEP_REPAIR_RUN_STATE:
        return "invalid"
    if current_step == STEP_INSPECT_DIAGNOSTICS:
        return "blocked"
    if current_step == STEP_PREPARE_CONTEXT:
        return "not_started"
    if current_step == STEP_REQUEST_AI_RESPONSE:
        return "context_ready"
    if current_step == STEP_REVIEW_RESPONSE:
        return "review_required"
    if current_step == STEP_APPLY_PATCH:
        return "ready_to_apply"
    if current_step == STEP_RUN_VERIFICATION:
        return "verification_required"
    return "complete"


def _explicit_blocked(state: Mapping, workflow_summary: Mapping) -> bool:
    status = str(workflow_summary.get("workflow_status") or "").strip()
    if status in {WORKFLOW_STATUS_FAILED, WORKFLOW_STATUS_BLOCKED}:
        return True
    if isinstance(state.get("error"), str) and state.get("error").strip():
        return True
    return _normalized(state.get("review_status")) in _FAILURE_VALUES or _normalized(state.get("verification_status")) in _FAILURE_VALUES


def _context_ready_evidence(state: Mapping) -> bool:
    if isinstance(state.get("context_ready"), bool):
        return bool(state.get("context_ready"))
    return bool(isinstance(state.get("task"), str) and state.get("task").strip())


def _response_received(state: Mapping) -> bool:
    if isinstance(state.get("response_received"), bool):
        return bool(state.get("response_received"))
    return state.get("patch_received") is True


def _review_passed(state: Mapping) -> bool:
    if isinstance(state.get("review_passed"), bool):
        return bool(state.get("review_passed"))
    return _normalized(state.get("review_status")) in _SUCCESS_VALUES


def _patch_applied(state: Mapping) -> bool:
    return state.get("patch_applied") is True


def _verification_passed(state: Mapping) -> bool:
    if isinstance(state.get("verification_passed"), bool):
        return bool(state.get("verification_passed"))
    return _normalized(state.get("verification_status")) in _SUCCESS_VALUES


def _primary_issue_code(diagnostics: list[dict[str, object]]) -> str | None:
    for severity in (DIAGNOSTIC_SEVERITY_ERROR, DIAGNOSTIC_SEVERITY_WARNING, DIAGNOSTIC_SEVERITY_INFO):
        matching = [
            diagnostic
            for diagnostic in diagnostics
            if diagnostic.get("severity") == severity
        ]
        matching = sorted(
            matching,
            key=_diagnostic_sort_key,
        )
        if matching:
            return str(matching[0].get("code"))
    return None


def _diagnostic_sort_key(diagnostic: Mapping) -> tuple[str, str, str, str, str]:
    return (
        str(diagnostic.get("source") or ""),
        str(diagnostic.get("code") or ""),
        str(diagnostic.get("path") or ""),
        str(diagnostic.get("field") or ""),
        str(diagnostic.get("message") or ""),
    )


def _status_mapping(status_summary) -> Mapping:
    if not isinstance(status_summary, Mapping):
        raise ValueError("workflow status summary must be a mapping.")
    return status_summary


def _display_value(value) -> str:
    return str(value or "").replace("_", " ").capitalize()


def _normalized(value) -> str:
    return str(value or "").strip().lower()
