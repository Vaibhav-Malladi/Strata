from strata.core.context_artifacts import (
    BASELINE_STATUS_ATTACHED,
    BASELINE_STATUS_AVAILABLE,
    BASELINE_STATUS_DETACHED,
    BASELINE_STATUS_GIT_UNAVAILABLE,
    BASELINE_STATUS_MISSING,
    BASELINE_STATUS_NO_COMMITS,
    BASELINE_STATUS_NOT_GIT,
    BASELINE_STATUS_NOT_PROVIDED,
    RUN_STATE_FIELD_ORDER,
    RUN_STATE_SCHEMA_VERSION,
)


WORKFLOW_STATUS_NOT_STARTED = "not_started"
WORKFLOW_STATUS_CONTEXT_READY = "context_ready"
WORKFLOW_STATUS_AWAITING_AI_RESPONSE = "awaiting_ai_response"
WORKFLOW_STATUS_RESPONSE_RECEIVED = "response_received"
WORKFLOW_STATUS_REVIEW_REQUIRED = "review_required"
WORKFLOW_STATUS_READY_TO_APPLY = "ready_to_apply"
WORKFLOW_STATUS_VERIFICATION_REQUIRED = "verification_required"
WORKFLOW_STATUS_COMPLETE = "complete"
WORKFLOW_STATUS_BLOCKED = "blocked"
WORKFLOW_STATUS_FAILED = "failed"
WORKFLOW_STATUSES = (
    WORKFLOW_STATUS_NOT_STARTED,
    WORKFLOW_STATUS_CONTEXT_READY,
    WORKFLOW_STATUS_AWAITING_AI_RESPONSE,
    WORKFLOW_STATUS_RESPONSE_RECEIVED,
    WORKFLOW_STATUS_REVIEW_REQUIRED,
    WORKFLOW_STATUS_READY_TO_APPLY,
    WORKFLOW_STATUS_VERIFICATION_REQUIRED,
    WORKFLOW_STATUS_COMPLETE,
    WORKFLOW_STATUS_BLOCKED,
    WORKFLOW_STATUS_FAILED,
)

NEXT_ACTION_REPAIR_RUN_STATE = "repair_or_regenerate_run_state"
NEXT_ACTION_PREPARE_CONTEXT = "prepare_context"
NEXT_ACTION_REQUEST_AI_RESPONSE = "request_ai_response"
NEXT_ACTION_REVIEW_RESPONSE = "review_response"
NEXT_ACTION_APPLY_PATCH = "apply_patch"
NEXT_ACTION_RUN_VERIFICATION = "run_verification"
NEXT_ACTION_WORKFLOW_COMPLETE = "workflow_complete"
NEXT_ACTION_INSPECT_DIAGNOSTICS = "inspect_diagnostics"

DIAGNOSTIC_SEVERITY_ERROR = "error"
DIAGNOSTIC_MISSING_REQUIRED_FIELD = "missing_required_field"
DIAGNOSTIC_INVALID_FIELD_TYPE = "invalid_field_type"
DIAGNOSTIC_INVALID_STATE_VALUE = "invalid_state_value"
DIAGNOSTIC_INVALID_COLLECTION_ITEM = "invalid_collection_item"
DIAGNOSTIC_UNSUPPORTED_SCHEMA_VERSION = "unsupported_schema_version"
DIAGNOSTIC_CODES = (
    DIAGNOSTIC_MISSING_REQUIRED_FIELD,
    DIAGNOSTIC_INVALID_FIELD_TYPE,
    DIAGNOSTIC_INVALID_STATE_VALUE,
    DIAGNOSTIC_INVALID_COLLECTION_ITEM,
    DIAGNOSTIC_UNSUPPORTED_SCHEMA_VERSION,
)

BASELINE_STATUSES = (
    BASELINE_STATUS_ATTACHED,
    BASELINE_STATUS_DETACHED,
    BASELINE_STATUS_NO_COMMITS,
    BASELINE_STATUS_NOT_GIT,
    BASELINE_STATUS_GIT_UNAVAILABLE,
    BASELINE_STATUS_AVAILABLE,
    BASELINE_STATUS_MISSING,
    BASELINE_STATUS_NOT_PROVIDED,
)

RUN_STATE_REQUIRED_FIELDS = RUN_STATE_FIELD_ORDER
_OPTIONAL_STRING_FIELDS = (
    "created_at",
    "baseline_commit",
    "baseline_warning",
    "prompt_hash",
    "adapter",
    "error",
)
_STRING_LIST_FIELDS = (
    "in_scope_files",
    "expected_related_files",
    "allowed_new_files",
)
_OPEN_LIST_FIELDS = (
    "cross_repo_references",
    "internal_libraries",
)
_OPTIONAL_STATUS_FIELDS = (
    "review_status",
    "verification_status",
)
_OPTIONAL_BOOL_FIELDS = (
    "response_received",
    "review_passed",
    "patch_applied",
    "verification_passed",
)
_SUCCESS_VALUES = {"pass", "passed", "success", "succeeded", "complete", "completed"}
_FAILURE_VALUES = {"fail", "failed", "failure", "error", "errored", "blocked"}


def validate_workflow_state(run_state) -> list[dict[str, object]]:
    """Return deterministic validation diagnostics for a canonical run_state mapping."""

    diagnostics: list[dict[str, object]] = []

    if not isinstance(run_state, dict):
        return [
            _diagnostic(
                DIAGNOSTIC_INVALID_FIELD_TYPE,
                "Run state must be a mapping.",
                field="run_state",
            )
        ]

    for field in RUN_STATE_REQUIRED_FIELDS:
        if field not in run_state:
            diagnostics.append(
                _diagnostic(
                    DIAGNOSTIC_MISSING_REQUIRED_FIELD,
                    f"Run state is missing the required field '{field}'.",
                    field=field,
                )
            )

    if "schema_version" in run_state:
        schema_version = run_state.get("schema_version")
        if isinstance(schema_version, bool) or not isinstance(schema_version, int):
            diagnostics.append(
                _diagnostic(
                    DIAGNOSTIC_INVALID_FIELD_TYPE,
                    "Run state field 'schema_version' must be an integer.",
                    field="schema_version",
                )
            )
        elif schema_version != RUN_STATE_SCHEMA_VERSION:
            diagnostics.append(
                _diagnostic(
                    DIAGNOSTIC_UNSUPPORTED_SCHEMA_VERSION,
                    f"Run state schema_version must be {RUN_STATE_SCHEMA_VERSION}.",
                    field="schema_version",
                    value=schema_version,
                )
            )

    _validate_type(run_state, diagnostics, "task", str)
    _validate_type(run_state, diagnostics, "baseline_commit_attached", bool)
    _validate_type(run_state, diagnostics, "patch_received", bool)
    _validate_type(run_state, diagnostics, "workspace_mode", str)
    _validate_optional_dict(run_state, diagnostics, "workspace")

    for field in _OPTIONAL_STRING_FIELDS:
        _validate_optional_type(run_state, diagnostics, field, str)

    _validate_optional_bounded_value(
        run_state,
        diagnostics,
        "baseline_status",
        BASELINE_STATUSES,
    )
    _validate_optional_bounded_value(
        run_state,
        diagnostics,
        "workflow_status",
        WORKFLOW_STATUSES,
    )

    for field in _STRING_LIST_FIELDS:
        _validate_string_list(run_state, diagnostics, field)

    for field in _OPEN_LIST_FIELDS:
        _validate_list(run_state, diagnostics, field)

    for field in _OPTIONAL_STATUS_FIELDS:
        _validate_optional_type(run_state, diagnostics, field, str)

    for field in _OPTIONAL_BOOL_FIELDS:
        _validate_optional_type(run_state, diagnostics, field, bool)

    return diagnostics


def suggest_next_workflow_action(run_state, diagnostics=None) -> str:
    """Return one conservative next action for the supplied run state."""

    state = run_state if isinstance(run_state, dict) else {}
    issues = diagnostics if diagnostics is not None else validate_workflow_state(run_state)
    if any(_is_error(issue) for issue in issues):
        return NEXT_ACTION_REPAIR_RUN_STATE

    workflow_status = _workflow_status(state)
    if workflow_status in {WORKFLOW_STATUS_FAILED, WORKFLOW_STATUS_BLOCKED}:
        return NEXT_ACTION_INSPECT_DIAGNOSTICS

    if _has_error(state):
        return NEXT_ACTION_INSPECT_DIAGNOSTICS

    if _is_complete(state, workflow_status):
        return NEXT_ACTION_WORKFLOW_COMPLETE

    if _patch_applied(state) or workflow_status == WORKFLOW_STATUS_VERIFICATION_REQUIRED:
        return NEXT_ACTION_RUN_VERIFICATION

    if _review_passed(state):
        return NEXT_ACTION_APPLY_PATCH

    if workflow_status == WORKFLOW_STATUS_READY_TO_APPLY:
        return NEXT_ACTION_REVIEW_RESPONSE

    if _response_received(state) or workflow_status in {
        WORKFLOW_STATUS_RESPONSE_RECEIVED,
        WORKFLOW_STATUS_REVIEW_REQUIRED,
    }:
        return NEXT_ACTION_REVIEW_RESPONSE

    if _context_ready(state) or workflow_status in {
        WORKFLOW_STATUS_CONTEXT_READY,
        WORKFLOW_STATUS_AWAITING_AI_RESPONSE,
    }:
        return NEXT_ACTION_REQUEST_AI_RESPONSE

    return NEXT_ACTION_PREPARE_CONTEXT


def build_workflow_state_summary(run_state) -> dict[str, object]:
    """Build a deterministic JSON-ready workflow summary from run_state data."""

    state = run_state if isinstance(run_state, dict) else {}
    diagnostics = validate_workflow_state(run_state)
    workflow_status = _workflow_status(state)

    return {
        "workflow_status": workflow_status,
        "is_valid": not any(_is_error(issue) for issue in diagnostics),
        "task_present": bool(str(state.get("task", "")).strip()) if isinstance(state.get("task"), str) else False,
        "baseline_present": _baseline_present(state),
        "baseline_status": state.get("baseline_status") if isinstance(state.get("baseline_status"), str) else None,
        "context_ready": _context_ready(state),
        "response_received": _response_received(state),
        "patch_received": state.get("patch_received") if isinstance(state.get("patch_received"), bool) else False,
        "review_status": state.get("review_status") if isinstance(state.get("review_status"), str) else None,
        "verification_status": state.get("verification_status") if isinstance(state.get("verification_status"), str) else None,
        "diagnostic_count": len(diagnostics),
        "next_action": suggest_next_workflow_action(state, diagnostics),
        "diagnostics": diagnostics,
    }


def _validate_type(
    run_state: dict,
    diagnostics: list[dict[str, object]],
    field: str,
    expected_type: type,
) -> None:
    if field not in run_state:
        return

    value = run_state.get(field)
    if expected_type is bool:
        valid = isinstance(value, bool)
        label = "boolean"
    else:
        valid = isinstance(value, expected_type)
        label = expected_type.__name__

    if not valid:
        diagnostics.append(
            _diagnostic(
                DIAGNOSTIC_INVALID_FIELD_TYPE,
                f"Run state field '{field}' must be a {label}.",
                field=field,
            )
        )


def _validate_optional_type(
    run_state: dict,
    diagnostics: list[dict[str, object]],
    field: str,
    expected_type: type,
) -> None:
    if field not in run_state or run_state.get(field) is None:
        return

    _validate_type(run_state, diagnostics, field, expected_type)


def _validate_optional_dict(
    run_state: dict,
    diagnostics: list[dict[str, object]],
    field: str,
) -> None:
    if field not in run_state or run_state.get(field) is None:
        return

    if not isinstance(run_state.get(field), dict):
        diagnostics.append(
            _diagnostic(
                DIAGNOSTIC_INVALID_FIELD_TYPE,
                f"Run state field '{field}' must be a mapping or null.",
                field=field,
            )
        )


def _validate_list(
    run_state: dict,
    diagnostics: list[dict[str, object]],
    field: str,
) -> None:
    if field not in run_state:
        return

    if not isinstance(run_state.get(field), list):
        diagnostics.append(
            _diagnostic(
                DIAGNOSTIC_INVALID_FIELD_TYPE,
                f"Run state field '{field}' must be a list.",
                field=field,
            )
        )


def _validate_string_list(
    run_state: dict,
    diagnostics: list[dict[str, object]],
    field: str,
) -> None:
    _validate_list(run_state, diagnostics, field)
    values = run_state.get(field)
    if not isinstance(values, list):
        return

    for index, item in enumerate(values):
        if not isinstance(item, str):
            diagnostics.append(
                _diagnostic(
                    DIAGNOSTIC_INVALID_COLLECTION_ITEM,
                    f"Run state field '{field}' item {index} must be a string.",
                    field=f"{field}[{index}]",
                )
            )


def _validate_optional_bounded_value(
    run_state: dict,
    diagnostics: list[dict[str, object]],
    field: str,
    allowed_values: tuple[str, ...],
) -> None:
    if field not in run_state or run_state.get(field) is None:
        return

    value = run_state.get(field)
    if not isinstance(value, str):
        diagnostics.append(
            _diagnostic(
                DIAGNOSTIC_INVALID_FIELD_TYPE,
                f"Run state field '{field}' must be a string or null.",
                field=field,
            )
        )
        return

    if value not in allowed_values:
        diagnostics.append(
            _diagnostic(
                DIAGNOSTIC_INVALID_STATE_VALUE,
                f"Run state field '{field}' has an unsupported value.",
                field=field,
                value=value,
            )
        )


def _diagnostic(
    code: str,
    message: str,
    *,
    field: str | None = None,
    value: object = None,
) -> dict[str, object]:
    issue: dict[str, object] = {
        "code": code,
        "severity": DIAGNOSTIC_SEVERITY_ERROR,
        "message": message,
    }
    if field is not None:
        issue["field"] = field
    if value is not None:
        issue["value"] = value
    return issue


def _workflow_status(run_state: dict) -> str:
    value = run_state.get("workflow_status")
    if isinstance(value, str) and value in WORKFLOW_STATUSES:
        return value

    if _has_error(run_state):
        return WORKFLOW_STATUS_FAILED

    if _response_received(run_state):
        return WORKFLOW_STATUS_RESPONSE_RECEIVED

    if _context_ready(run_state):
        return WORKFLOW_STATUS_CONTEXT_READY

    return WORKFLOW_STATUS_NOT_STARTED


def _context_ready(run_state: dict) -> bool:
    if isinstance(run_state.get("context_ready"), bool):
        return bool(run_state.get("context_ready"))

    if not isinstance(run_state.get("task"), str) or not run_state.get("task").strip():
        return False

    return all(field in run_state for field in RUN_STATE_REQUIRED_FIELDS)


def _response_received(run_state: dict) -> bool:
    if isinstance(run_state.get("response_received"), bool):
        return bool(run_state.get("response_received"))

    return bool(run_state.get("patch_received") is True)


def _review_passed(run_state: dict) -> bool:
    if isinstance(run_state.get("review_passed"), bool):
        return bool(run_state.get("review_passed"))

    status = _normalized(run_state.get("review_status"))
    return status in _SUCCESS_VALUES


def _patch_applied(run_state: dict) -> bool:
    return bool(run_state.get("patch_applied") is True)


def _verification_passed(run_state: dict) -> bool:
    if isinstance(run_state.get("verification_passed"), bool):
        return bool(run_state.get("verification_passed"))

    status = _normalized(run_state.get("verification_status"))
    return status in _SUCCESS_VALUES


def _is_complete(run_state: dict, workflow_status: str) -> bool:
    return workflow_status == WORKFLOW_STATUS_COMPLETE and _verification_passed(run_state)


def _has_error(run_state: dict) -> bool:
    error = run_state.get("error")
    if isinstance(error, str) and error.strip():
        return True

    for field in ("review_status", "verification_status"):
        if _normalized(run_state.get(field)) in _FAILURE_VALUES:
            return True

    return False


def _baseline_present(run_state: dict) -> bool:
    if isinstance(run_state.get("baseline_commit"), str) and run_state.get("baseline_commit").strip():
        return True

    return run_state.get("baseline_status") in {
        BASELINE_STATUS_ATTACHED,
        BASELINE_STATUS_DETACHED,
        BASELINE_STATUS_NO_COMMITS,
    }


def _is_error(diagnostic: object) -> bool:
    return isinstance(diagnostic, dict) and diagnostic.get("severity") == DIAGNOSTIC_SEVERITY_ERROR


def _normalized(value: object) -> str:
    return str(value or "").strip().lower()
