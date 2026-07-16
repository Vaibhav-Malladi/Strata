from collections.abc import Mapping

import strata.core.diagnostics as _diagnostics
import strata.core.session_state as _session_state
import strata.core.workflow_state as _workflow_state


GUIDED_WORKFLOW_SCHEMA_VERSION = 1

GUIDED_WORKFLOW_STAGES = (
    "setup_required",
    "ready",
    "context_prepared",
    "prompt_ready",
    "awaiting_ai_response",
    "response_received",
    "retry_available",
    "ready_for_review",
    "review_blocked",
    "ready_to_apply",
    "verification_required",
    "complete",
)
(
    STAGE_SETUP_REQUIRED, STAGE_READY, STAGE_CONTEXT_PREPARED, STAGE_PROMPT_READY,
    STAGE_AWAITING_AI_RESPONSE, STAGE_RESPONSE_RECEIVED, STAGE_RETRY_AVAILABLE,
    STAGE_READY_FOR_REVIEW, STAGE_REVIEW_BLOCKED, STAGE_READY_TO_APPLY,
    STAGE_VERIFICATION_REQUIRED, STAGE_COMPLETE,
) = GUIDED_WORKFLOW_STAGES

GUIDED_WORKFLOW_NEXT_ACTIONS = (
    "run_setup",
    "prepare_context",
    "deliver_prompt",
    "provide_ai_response",
    "retry_ai_request",
    "review_changes",
    "resolve_review_issues",
    "apply_changes",
    "run_verification",
    "view_results",
    "none",
)
(
    NEXT_ACTION_RUN_SETUP, NEXT_ACTION_PREPARE_CONTEXT, NEXT_ACTION_DELIVER_PROMPT,
    NEXT_ACTION_PROVIDE_AI_RESPONSE, NEXT_ACTION_RETRY_AI_REQUEST, NEXT_ACTION_REVIEW_CHANGES,
    NEXT_ACTION_RESOLVE_REVIEW_ISSUES, NEXT_ACTION_APPLY_CHANGES, NEXT_ACTION_RUN_VERIFICATION,
    NEXT_ACTION_VIEW_RESULTS, NEXT_ACTION_NONE,
) = GUIDED_WORKFLOW_NEXT_ACTIONS

_WARNING_LIMIT = 5
_SUCCESS_VALUES = {"pass", "passed", "success", "succeeded", "complete", "completed"}
_FAILURE_VALUES = {"fail", "failed", "failure", "error", "errored", "blocked", "rejected"}
_ACTION_LABELS = {
    NEXT_ACTION_RUN_SETUP: "Set up Strata",
    NEXT_ACTION_PREPARE_CONTEXT: "Prepare project context",
    NEXT_ACTION_DELIVER_PROMPT: "Copy the request into your AI tool",
    NEXT_ACTION_PROVIDE_AI_RESPONSE: "Paste the AI response back into Strata",
    NEXT_ACTION_RETRY_AI_REQUEST: "Retry the AI request",
    NEXT_ACTION_REVIEW_CHANGES: "Review the proposed changes",
    NEXT_ACTION_RESOLVE_REVIEW_ISSUES: "Fix the review issues",
    NEXT_ACTION_APPLY_CHANGES: "Apply the reviewed changes",
    NEXT_ACTION_RUN_VERIFICATION: "Run verification",
    NEXT_ACTION_VIEW_RESULTS: "View results",
    NEXT_ACTION_NONE: "No action needed",
}
_STAGE_COPY = {
    STAGE_SETUP_REQUIRED: ("Set up Strata before continuing.", "Strata needs an AI workflow setup before it can guide this task."),
    STAGE_READY: ("Strata is ready to prepare project context.", "Prepare context so your AI tool has the right project details."),
    STAGE_CONTEXT_PREPARED: ("Your project context is ready.", "Strata has enough context to prepare the AI request."),
    STAGE_PROMPT_READY: ("Copy the request into your AI tool.", "The AI request is ready and has not been delivered yet."),
    STAGE_AWAITING_AI_RESPONSE: ("Paste the AI response back into Strata.", "The request has been delivered; Strata is waiting for the AI response."),
    STAGE_RESPONSE_RECEIVED: ("The AI response is ready for review.", "Strata received a response and can guide the review step."),
    STAGE_RETRY_AVAILABLE: ("Retry the AI request.", "The last response needs correction and one retry is available."),
    STAGE_READY_FOR_REVIEW: ("The AI response is ready for review.", "Strata validated the response structure and scope."),
    STAGE_REVIEW_BLOCKED: ("Fix the review issues before applying.", "Strata found an issue that blocks progress."),
    STAGE_READY_TO_APPLY: ("The reviewed changes are ready to apply.", "The response has review evidence and can move to the apply step."),
    STAGE_VERIFICATION_REQUIRED: ("Run verification to confirm the changes.", "The changes were applied and still need verification."),
    STAGE_COMPLETE: ("The workflow is complete.", "The changes were reviewed, applied, and verified."),
}


def _require_mapping(value, field_name: str) -> Mapping:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be a mapping.")
    return value


def _optional_mapping(value, field_name: str) -> Mapping | None:
    return None if value is None else _require_mapping(value, field_name)


def _copy_json_value(value):
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, list):
        return [_copy_json_value(item) for item in value]
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("mapping keys must be strings.")
        return {key: _copy_json_value(value[key]) for key in sorted(value)}
    raise ValueError("guided workflow inputs must be JSON-ready.")


def _copy_mapping(value: Mapping) -> dict[str, object]:
    return _copy_json_value(value)


def _normalize_diagnostics(diagnostics) -> list[dict[str, object]]:
    if diagnostics is None:
        return []
    if not isinstance(diagnostics, (list, tuple)):
        raise ValueError("diagnostics must be a list or tuple.")
    return [
        _diagnostics.normalize_diagnostic_event(
            diagnostic,
            default_source=_diagnostics.DIAGNOSTIC_SOURCE_WORKFLOW_STATE,
        )
        for diagnostic in diagnostics
    ]


def _workflow_diagnostics(state: Mapping) -> list[dict[str, object]]:
    if "schema_version" not in state:
        return [] if state else [_incomplete_state_diagnostic()]
    return [
        _diagnostics.normalize_diagnostic_event(
            diagnostic,
            default_source=_diagnostics.DIAGNOSTIC_SOURCE_WORKFLOW_STATE,
        )
        for diagnostic in _workflow_state.validate_workflow_state(dict(state))
    ]


def _incomplete_state_diagnostic() -> dict[str, object]:
    return {
        "code": "incomplete_workflow_state",
        "severity": _diagnostics.DIAGNOSTIC_SEVERITY_ERROR,
        "message": "Workflow state is incomplete.",
        "source": _diagnostics.DIAGNOSTIC_SOURCE_WORKFLOW_STATE,
        "field": None,
        "path": None,
        "next_action": None,
        "details": {},
    }


def _warnings(state: Mapping, diagnostics: list[dict[str, object]]) -> tuple[list[dict[str, object]], int]:
    warnings = []
    for diagnostic in diagnostics:
        if diagnostic.get("severity") == _diagnostics.DIAGNOSTIC_SEVERITY_WARNING:
            warnings.append(_warning(diagnostic.get("code"), diagnostic.get("message")))
    if isinstance(state.get("baseline_warning"), str) and state.get("baseline_warning").strip():
        warnings.append(_warning("baseline_warning", state["baseline_warning"]))
    for item in state.get("warnings") or []:
        if isinstance(item, Mapping):
            warnings.append(_warning(item.get("code"), item.get("message")))
        elif isinstance(item, str) and item.strip():
            warnings.append(_warning("workflow_warning", item))

    deduplicated = {}
    for item in warnings:
        deduplicated[(item["code"], item["message"])] = item
    ordered = [deduplicated[key] for key in sorted(deduplicated)]
    return ordered[:_WARNING_LIMIT], len(ordered)


def _warning(code, message) -> dict[str, object]:
    text = str(message or "").strip()
    return {
        "code": str(code or "warning").strip() or "warning",
        "message": text or "Review this workflow warning before continuing.",
    }


def _has_blocking_diagnostics(diagnostics: list[dict[str, object]]) -> bool:
    return any(diagnostic.get("severity") == _diagnostics.DIAGNOSTIC_SEVERITY_ERROR for diagnostic in diagnostics)


def _contradiction(state: Mapping, session: Mapping | None) -> str | None:
    if _workflow_status(state) == _workflow_state.WORKFLOW_STATUS_COMPLETE and not _verification_passed(state):
        return "Workflow is marked complete without verification evidence."
    if _verification_passed(state) and not _patch_applied(state):
        return "Verification is marked complete before changes were applied."
    if _patch_applied(state) and not _review_passed(state):
        return "Changes are marked applied without review evidence."
    if _review_passed(state) and not _response_received(state, session):
        return "Review is marked complete before an AI response was received."
    if _review_passed(state) and _review_failed(state, session):
        return "Review evidence is contradictory."
    return None


def _decide_stage_and_action(state: Mapping, session: Mapping | None, diagnostics: list[dict[str, object]]) -> tuple[str, str, str]:
    if _has_blocking_diagnostics(diagnostics):
        return STAGE_REVIEW_BLOCKED, NEXT_ACTION_RESOLVE_REVIEW_ISSUES, "blocking_diagnostics"
    if _contradiction(state, session):
        return STAGE_REVIEW_BLOCKED, NEXT_ACTION_RESOLVE_REVIEW_ISSUES, "contradictory_state"
    if _setup_required(state):
        return STAGE_SETUP_REQUIRED, NEXT_ACTION_RUN_SETUP, "incomplete_setup"
    if _review_failed(state, session):
        return STAGE_REVIEW_BLOCKED, NEXT_ACTION_RESOLVE_REVIEW_ISSUES, "review_blockers"
    if _verification_required(state):
        return STAGE_VERIFICATION_REQUIRED, NEXT_ACTION_RUN_VERIFICATION, "verification_required"
    if _complete(state):
        return STAGE_COMPLETE, NEXT_ACTION_NONE, "complete"
    if _ready_to_apply(state):
        return STAGE_READY_TO_APPLY, NEXT_ACTION_APPLY_CHANGES, "ready_to_apply"
    if _session_status(session) == _session_state.SESSION_STATUS_RETRY_READY:
        return STAGE_RETRY_AVAILABLE, NEXT_ACTION_RETRY_AI_REQUEST, "retry_available"
    if _session_status(session) == _session_state.SESSION_STATUS_ACCEPTED_FOR_REVIEW:
        return STAGE_READY_FOR_REVIEW, NEXT_ACTION_REVIEW_CHANGES, "response_ready_for_review"
    if _response_received(state, session):
        return STAGE_RESPONSE_RECEIVED, NEXT_ACTION_REVIEW_CHANGES, "response_received"
    if _awaiting_ai_response(state, session):
        return STAGE_AWAITING_AI_RESPONSE, NEXT_ACTION_PROVIDE_AI_RESPONSE, "waiting_for_ai_response"
    if _prompt_ready(state, session):
        return STAGE_PROMPT_READY, NEXT_ACTION_DELIVER_PROMPT, "prompt_prepared"
    if _context_prepared(state):
        return STAGE_CONTEXT_PREPARED, NEXT_ACTION_PREPARE_CONTEXT, "context_prepared"
    if _missing_context(state):
        return STAGE_READY, NEXT_ACTION_PREPARE_CONTEXT, "missing_context"
    return STAGE_REVIEW_BLOCKED, NEXT_ACTION_RESOLVE_REVIEW_ISSUES, "ambiguous_state"


def _setup_required(state: Mapping) -> bool:
    if state.get("setup_required") is True or state.get("setup_complete") is False:
        return True
    return "adapter" in state and (not isinstance(state.get("adapter"), str) or not state.get("adapter").strip())


def _missing_context(state: Mapping) -> bool:
    return not _prompt_ready(state, None) and not _context_prepared(state)


def _context_prepared(state: Mapping) -> bool:
    return state.get("context_ready") is True or _workflow_status(state) == _workflow_state.WORKFLOW_STATUS_CONTEXT_READY


def _prompt_ready(state: Mapping, session: Mapping | None) -> bool:
    return (
        _session_status(session) == _session_state.SESSION_STATUS_PREPARED
        or isinstance(state.get("prompt_hash"), str)
        and bool(state.get("prompt_hash").strip())
    )


def _awaiting_ai_response(state: Mapping, session: Mapping | None) -> bool:
    return (
        _session_status(session) == _session_state.SESSION_STATUS_DELIVERED
        or _workflow_status(state) == _workflow_state.WORKFLOW_STATUS_AWAITING_AI_RESPONSE
    )


def _response_received(state: Mapping, session: Mapping | None) -> bool:
    return (
        _session_status(session) == _session_state.SESSION_STATUS_RESPONSE_RECEIVED
        or state.get("response_received") is True
        or state.get("patch_received") is True
        or _workflow_status(state) in {
        _workflow_state.WORKFLOW_STATUS_RESPONSE_RECEIVED,
        _workflow_state.WORKFLOW_STATUS_REVIEW_REQUIRED,
        }
    )


def _review_failed(state: Mapping, session: Mapping | None) -> bool:
    return _session_status(session) == _session_state.SESSION_STATUS_REJECTED or _normalized(state.get("review_status")) in _FAILURE_VALUES


def _ready_to_apply(state: Mapping) -> bool:
    return _review_passed(state)


def _verification_required(state: Mapping) -> bool:
    return not _complete(state) and (
        _patch_applied(state) or _workflow_status(state) == _workflow_state.WORKFLOW_STATUS_VERIFICATION_REQUIRED
    )


def _complete(state: Mapping) -> bool:
    return _workflow_status(state) == _workflow_state.WORKFLOW_STATUS_COMPLETE and _verification_passed(state)


def _review_passed(state: Mapping) -> bool:
    return state.get("review_passed") is True or _normalized(state.get("review_status")) in _SUCCESS_VALUES


def _patch_applied(state: Mapping) -> bool:
    return state.get("patch_applied") is True


def _verification_passed(state: Mapping) -> bool:
    return state.get("verification_passed") is True or _normalized(state.get("verification_status")) in _SUCCESS_VALUES


def _workflow_status(state: Mapping) -> str:
    return state.get("workflow_status") if isinstance(state.get("workflow_status"), str) else ""


def _session_status(session: Mapping | None) -> str:
    return "" if session is None or not isinstance(session.get("status"), str) else session["status"]


def _normalized(value) -> str:
    return str(value or "").strip().lower()


def build_guided_workflow_view(
    *,
    workflow_state,
    session_state=None,
    diagnostics=None,
) -> dict[str, object]:
    """Return one deterministic, JSON-ready guided workflow view."""

    state = _copy_mapping(_require_mapping(workflow_state, "workflow_state"))
    session = _optional_mapping(session_state, "session_state")
    session = _copy_mapping(session) if session is not None else None
    normalized_diagnostics = _workflow_diagnostics(state) + _normalize_diagnostics(diagnostics)
    warnings, warning_total = _warnings(state, normalized_diagnostics)
    stage, next_action, priority = _decide_stage_and_action(state, session, normalized_diagnostics)
    headline, summary = _STAGE_COPY[stage]
    blocking_count = sum(
        1
        for diagnostic in normalized_diagnostics
        if diagnostic.get("severity") == _diagnostics.DIAGNOSTIC_SEVERITY_ERROR
    )
    details = {
        "decision_priority": priority,
        "diagnostic_count": len(normalized_diagnostics),
        "blocking_diagnostic_count": blocking_count,
        "warning_total": warning_total,
        "warnings_truncated": warning_total > len(warnings),
    }
    contradiction = _contradiction(state, session)
    if contradiction is not None:
        details["blocking_reason"] = contradiction

    return {
        "schema_version": GUIDED_WORKFLOW_SCHEMA_VERSION,
        "stage": stage,
        "headline": headline,
        "summary": summary,
        "next_action": next_action,
        "next_action_label": _ACTION_LABELS[next_action],
        "confirmation_required": next_action == NEXT_ACTION_APPLY_CHANGES,
        "blocking": stage in {STAGE_SETUP_REQUIRED, STAGE_REVIEW_BLOCKED},
        "warnings": warnings,
        "details": details,
    }
