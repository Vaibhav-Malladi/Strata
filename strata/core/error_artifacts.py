import json
from collections.abc import Mapping
from pathlib import Path

from strata.core.diagnostic_explanations import (
    explain_diagnostic_events,
    summarize_diagnostic_explanations,
)
from strata.core.diagnostics import (
    DIAGNOSTIC_SOURCE_WORKFLOW_STATE,
    deduplicate_diagnostic_events,
    normalize_diagnostic_event,
    summarize_diagnostic_events,
)
from strata.core.workflow_state import (
    NEXT_ACTION_INSPECT_DIAGNOSTICS,
    NEXT_ACTION_PREPARE_CONTEXT,
    NEXT_ACTION_REPAIR_RUN_STATE,
    NEXT_ACTION_REQUEST_AI_RESPONSE,
    NEXT_ACTION_REVIEW_RESPONSE,
    NEXT_ACTION_RUN_VERIFICATION,
    suggest_next_workflow_action,
    validate_workflow_state,
)
from strata.core.workflow_status import build_workflow_status
from strata.utils.artifacts import write_artifact_text


RUN_ERROR_SCHEMA_VERSION = 1
RUN_ERROR_ARTIFACT_TYPE = "run_error"
DEFAULT_RUN_ERROR_JSON_PATH = Path("diagnostics") / "run_error.json"
DEFAULT_RUN_ERROR_MARKDOWN_PATH = Path("diagnostics") / "run_error.md"

RUN_ERROR_STAGE_PREPARE = "prepare"
RUN_ERROR_STAGE_CONTEXT = "context"
RUN_ERROR_STAGE_AI_RESPONSE = "ai_response"
RUN_ERROR_STAGE_REVIEW = "review"
RUN_ERROR_STAGE_APPLY = "apply"
RUN_ERROR_STAGE_VERIFY = "verify"
RUN_ERROR_STAGE_GATE = "gate"
RUN_ERROR_STAGE_WORKFLOW = "workflow"
RUN_ERROR_STAGE_UNKNOWN = "unknown"
RUN_ERROR_STAGES = (
    RUN_ERROR_STAGE_PREPARE,
    RUN_ERROR_STAGE_CONTEXT,
    RUN_ERROR_STAGE_AI_RESPONSE,
    RUN_ERROR_STAGE_REVIEW,
    RUN_ERROR_STAGE_APPLY,
    RUN_ERROR_STAGE_VERIFY,
    RUN_ERROR_STAGE_GATE,
    RUN_ERROR_STAGE_WORKFLOW,
    RUN_ERROR_STAGE_UNKNOWN,
)

MAX_RUN_ERROR_DIAGNOSTICS = 25
MAX_RUN_ERROR_EXPLANATIONS = 25
MAX_RECOVERY_GUIDANCE = 10

SAFE_RECOVERY_ACTION_REPAIR_RUN_STATE = "repair_or_regenerate_run_state"
SAFE_RECOVERY_ACTION_PREPARE_CONTEXT = "prepare_context"
SAFE_RECOVERY_ACTION_REQUEST_AI_RESPONSE = "request_ai_response"
SAFE_RECOVERY_ACTION_REVIEW_RESPONSE = "review_response"
SAFE_RECOVERY_ACTION_REVISE_PATCH = "revise_patch"
SAFE_RECOVERY_ACTION_REMOVE_OUT_OF_SCOPE_CHANGES = "remove_out_of_scope_changes"
SAFE_RECOVERY_ACTION_APPROVE_EXPECTED_FILE = "approve_expected_file"
SAFE_RECOVERY_ACTION_FIX_IMPORTS = "fix_imports"
SAFE_RECOVERY_ACTION_RUN_TESTS = "run_tests"
SAFE_RECOVERY_ACTION_RUN_VERIFICATION = "run_verification"
SAFE_RECOVERY_ACTION_REGENERATE_CONTEXT = "regenerate_context"
SAFE_RECOVERY_ACTION_INSPECT_DETAILS = "inspect_details"
SAFE_RECOVERY_ACTION_INSPECT_DIAGNOSTICS = "inspect_diagnostics"
SAFE_RECOVERY_ACTIONS = (
    SAFE_RECOVERY_ACTION_REPAIR_RUN_STATE,
    SAFE_RECOVERY_ACTION_PREPARE_CONTEXT,
    SAFE_RECOVERY_ACTION_REQUEST_AI_RESPONSE,
    SAFE_RECOVERY_ACTION_REVIEW_RESPONSE,
    SAFE_RECOVERY_ACTION_REVISE_PATCH,
    SAFE_RECOVERY_ACTION_REMOVE_OUT_OF_SCOPE_CHANGES,
    SAFE_RECOVERY_ACTION_APPROVE_EXPECTED_FILE,
    SAFE_RECOVERY_ACTION_FIX_IMPORTS,
    SAFE_RECOVERY_ACTION_RUN_TESTS,
    SAFE_RECOVERY_ACTION_RUN_VERIFICATION,
    SAFE_RECOVERY_ACTION_REGENERATE_CONTEXT,
    SAFE_RECOVERY_ACTION_INSPECT_DETAILS,
    SAFE_RECOVERY_ACTION_INSPECT_DIAGNOSTICS,
)
UNSAFE_RECOVERY_ACTIONS = {
    "apply_patch",
    "force_apply",
    "disable_gate",
    "bypass_review",
    "ignore_warning",
    "skip_verification",
}

_RECOVERY_LABELS = {
    SAFE_RECOVERY_ACTION_REPAIR_RUN_STATE: "Repair or regenerate the run state",
    SAFE_RECOVERY_ACTION_PREPARE_CONTEXT: "Prepare project context",
    SAFE_RECOVERY_ACTION_REQUEST_AI_RESPONSE: "Request an AI response",
    SAFE_RECOVERY_ACTION_REVIEW_RESPONSE: "Review the proposed changes",
    SAFE_RECOVERY_ACTION_REVISE_PATCH: "Revise the patch",
    SAFE_RECOVERY_ACTION_REMOVE_OUT_OF_SCOPE_CHANGES: "Remove out-of-scope changes",
    SAFE_RECOVERY_ACTION_APPROVE_EXPECTED_FILE: "Approve the expected file",
    SAFE_RECOVERY_ACTION_FIX_IMPORTS: "Fix unresolved imports",
    SAFE_RECOVERY_ACTION_RUN_TESTS: "Run tests",
    SAFE_RECOVERY_ACTION_RUN_VERIFICATION: "Run verification",
    SAFE_RECOVERY_ACTION_REGENERATE_CONTEXT: "Regenerate context",
    SAFE_RECOVERY_ACTION_INSPECT_DETAILS: "Inspect details",
    SAFE_RECOVERY_ACTION_INSPECT_DIAGNOSTICS: "Inspect diagnostics",
}

_RECOVERY_REASONS = {
    SAFE_RECOVERY_ACTION_REPAIR_RUN_STATE: "The workflow state is incomplete or invalid.",
    SAFE_RECOVERY_ACTION_PREPARE_CONTEXT: "The workflow needs a valid context package before continuing.",
    SAFE_RECOVERY_ACTION_REQUEST_AI_RESPONSE: "The context is ready, but a response has not been received.",
    SAFE_RECOVERY_ACTION_REVIEW_RESPONSE: "The response must be reviewed before any patch is applied.",
    SAFE_RECOVERY_ACTION_REVISE_PATCH: "The patch needs to be corrected before review can continue safely.",
    SAFE_RECOVERY_ACTION_REMOVE_OUT_OF_SCOPE_CHANGES: "The patch contains unsafe or unapproved file changes.",
    SAFE_RECOVERY_ACTION_APPROVE_EXPECTED_FILE: "The expected file list may need to be updated before continuing.",
    SAFE_RECOVERY_ACTION_FIX_IMPORTS: "The project contains unresolved imports or route import risks.",
    SAFE_RECOVERY_ACTION_RUN_TESTS: "Tests can confirm whether the project still behaves as expected.",
    SAFE_RECOVERY_ACTION_RUN_VERIFICATION: "Verification has not completed successfully yet.",
    SAFE_RECOVERY_ACTION_REGENERATE_CONTEXT: "The context or generated project evidence may be stale or incomplete.",
    SAFE_RECOVERY_ACTION_INSPECT_DETAILS: "The diagnostic details need review before choosing a fix.",
    SAFE_RECOVERY_ACTION_INSPECT_DIAGNOSTICS: "A blocking diagnostic must be inspected before continuing.",
}


def build_run_error_artifact(
    run_state,
    *,
    stage,
    diagnostics=None,
    explanations=None,
    metadata=None,
) -> dict[str, object]:
    """Build a deterministic local run-error artifact."""

    normalized_stage = _validate_stage(stage)
    m1_diagnostics = validate_workflow_state(run_state)
    normalized_diagnostics = _diagnostics_for_artifact(m1_diagnostics, diagnostics)
    diagnostic_summary = summarize_diagnostic_events(normalized_diagnostics)
    explanation_items = _explanations_for_artifact(normalized_diagnostics, explanations)
    workflow_status = build_workflow_status(
        run_state,
        diagnostics=normalized_diagnostics,
        explanations=explanation_items,
    )
    run_state_invalid = bool(m1_diagnostics)
    primary = _select_primary(normalized_diagnostics)
    explanation_by_code = _explanation_by_code(explanation_items)
    primary_explanation = explanation_by_code.get(primary.get("code")) if primary else None
    next_action = _select_next_action(run_state, m1_diagnostics, primary, primary_explanation)
    guidance = _build_recovery_guidance(
        workflow_status.get("next_action"),
        explanation_items,
        next_action=next_action,
        limit=None,
    )
    artifact_metadata = _metadata(
        metadata,
        diagnostic_count_total=len(normalized_diagnostics),
        diagnostics_shown=min(len(normalized_diagnostics), MAX_RUN_ERROR_DIAGNOSTICS),
        explanation_count_total=len(explanation_items),
        explanations_shown=min(len(explanation_items), MAX_RUN_ERROR_EXPLANATIONS),
        recovery_guidance_count_total=len(guidance),
        recovery_guidance_shown=min(len(guidance), MAX_RECOVERY_GUIDANCE),
    )

    bounded_diagnostics = normalized_diagnostics[:MAX_RUN_ERROR_DIAGNOSTICS]
    bounded_explanations = explanation_items[:MAX_RUN_ERROR_EXPLANATIONS]
    bounded_guidance = guidance[:MAX_RECOVERY_GUIDANCE]
    summary = _summary_text(workflow_status, primary_explanation, primary)

    artifact = {
        "schema_version": RUN_ERROR_SCHEMA_VERSION,
        "artifact_type": RUN_ERROR_ARTIFACT_TYPE,
        "workflow_status": workflow_status["status"],
        "health": workflow_status["health"],
        "stage": normalized_stage,
        "summary": summary,
        "primary_code": "invalid_run_state" if run_state_invalid else primary.get("code") if primary else None,
        "next_action": next_action,
        "diagnostic_summary": diagnostic_summary,
        "diagnostics": bounded_diagnostics,
        "explanations": bounded_explanations,
        "recovery_guidance": bounded_guidance,
        "metadata": artifact_metadata,
    }
    validate_run_error_artifact(artifact)
    return artifact


def build_recovery_guidance(
    workflow_next_action,
    explanations=None,
    *,
    next_action=None,
) -> list[dict[str, object]]:
    """Build deterministic safe recovery guidance records."""

    return _build_recovery_guidance(
        workflow_next_action,
        explanations,
        next_action=next_action,
        limit=MAX_RECOVERY_GUIDANCE,
    )


def _build_recovery_guidance(
    workflow_next_action,
    explanations=None,
    *,
    next_action=None,
    limit: int | None,
) -> list[dict[str, object]]:
    actions = []
    if next_action is not None:
        actions.append(next_action)
    if isinstance(explanations, (list, tuple)):
        for explanation in explanations:
            if isinstance(explanation, Mapping):
                actions.append(explanation.get("next_action"))
    actions.append(workflow_next_action)

    guidance = []
    seen = set()
    for raw_action in actions:
        action = _safe_recovery_action(raw_action)
        if action in seen:
            continue
        seen.add(action)
        guidance.append(
            {
                "action": action,
                "label": _RECOVERY_LABELS[action],
                "reason": _RECOVERY_REASONS[action],
                "priority": _recovery_priority(action),
            }
        )

    ordered = sorted(guidance, key=lambda item: (item["priority"], item["action"]))
    if limit is None:
        return ordered
    return ordered[:limit]


def render_run_error_json(artifact) -> str:
    """Render deterministic run-error JSON with a trailing newline."""

    payload = validate_run_error_artifact(artifact)
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def render_run_error_markdown(artifact) -> str:
    """Render a concise deterministic Markdown run-error report."""

    payload = validate_run_error_artifact(artifact)
    lines = [
        "# Strata Run Error",
        "",
        "## Summary",
        "",
        str(payload["summary"]),
        "",
        "## Current Status",
        "",
        f"- Stage: {_display_value(payload['stage'])}",
        f"- Health: {_display_value(payload['health'])}",
        f"- Primary issue: {_display_value(payload['primary_code']) or 'None'}",
        f"- Next action: {_display_value(payload['next_action'])}",
        "",
        "## Recovery Guidance",
        "",
    ]

    guidance = payload.get("recovery_guidance", [])
    if guidance:
        for item in guidance:
            lines.append(
                f"{int(item['priority'])}. {item['label']} - {item['reason']}"
            )
    else:
        lines.append("None.")

    lines.extend(["", "## Diagnostics", ""])
    diagnostics = payload.get("diagnostics", [])
    if diagnostics:
        for diagnostic in diagnostics:
            lines.append(
                f"- `{diagnostic['severity']}` {diagnostic['source']}/{diagnostic['code']}: {diagnostic['message']}"
            )
    else:
        lines.append("None.")

    return "\n".join(lines).rstrip() + "\n"


def write_run_error_json(
    repo_root,
    artifact,
    *,
    relative_path=DEFAULT_RUN_ERROR_JSON_PATH,
) -> Path:
    """Write a run-error JSON artifact under repo_root/.aidc."""

    return write_artifact_text(repo_root, relative_path, render_run_error_json(artifact))


def write_run_error_markdown(
    repo_root,
    artifact,
    *,
    relative_path=DEFAULT_RUN_ERROR_MARKDOWN_PATH,
) -> Path:
    """Write a run-error Markdown artifact under repo_root/.aidc."""

    return write_artifact_text(repo_root, relative_path, render_run_error_markdown(artifact))


def validate_run_error_artifact(artifact) -> dict[str, object]:
    """Return a validated run-error artifact mapping."""

    if not isinstance(artifact, Mapping):
        raise ValueError("run-error artifact must be a mapping.")
    required = (
        "schema_version",
        "artifact_type",
        "workflow_status",
        "health",
        "stage",
        "summary",
        "primary_code",
        "next_action",
        "diagnostic_summary",
        "diagnostics",
        "explanations",
        "recovery_guidance",
        "metadata",
    )
    for key in required:
        if key not in artifact:
            raise ValueError(f"run-error artifact is missing required field: {key}")
    if artifact["schema_version"] != RUN_ERROR_SCHEMA_VERSION:
        raise ValueError("run-error artifact schema_version is unsupported.")
    if artifact["artifact_type"] != RUN_ERROR_ARTIFACT_TYPE:
        raise ValueError("run-error artifact_type is unsupported.")
    _validate_stage(artifact["stage"])
    _validate_optional_string(artifact["primary_code"], "primary_code")
    for field in ("workflow_status", "health", "summary", "next_action"):
        _validate_nonempty_string(artifact[field], field)
    if not isinstance(artifact["diagnostic_summary"], Mapping):
        raise ValueError("diagnostic_summary must be a mapping.")
    diagnostics = _validate_list(artifact["diagnostics"], "diagnostics")
    explanations = _validate_list(artifact["explanations"], "explanations")
    guidance = _validate_list(artifact["recovery_guidance"], "recovery_guidance")
    metadata = _validate_mapping(artifact["metadata"], "metadata")

    for index, diagnostic in enumerate(diagnostics):
        normalize_diagnostic_event(diagnostic)
    for index, explanation in enumerate(explanations):
        _validate_explanation(explanation, f"explanations[{index}]")
    for index, item in enumerate(guidance):
        _validate_recovery_guidance(item, f"recovery_guidance[{index}]")

    _copy_json_ready(dict(artifact["diagnostic_summary"]), "diagnostic_summary")
    _copy_json_ready(metadata, "metadata")
    return _copy_json_ready(dict(artifact), "artifact")


def _diagnostics_for_artifact(m1_diagnostics, supplied_diagnostics) -> list[dict[str, object]]:
    diagnostics = []
    if supplied_diagnostics is None:
        for diagnostic in m1_diagnostics:
            diagnostics.append(
                normalize_diagnostic_event(
                    diagnostic,
                    default_source=DIAGNOSTIC_SOURCE_WORKFLOW_STATE,
                )
            )
    else:
        if not isinstance(supplied_diagnostics, (list, tuple)):
            raise ValueError("diagnostics must be a list or tuple.")
        diagnostics.extend(
            normalize_diagnostic_event(diagnostic)
            for diagnostic in supplied_diagnostics
        )
        for diagnostic in m1_diagnostics:
            diagnostics.append(
                normalize_diagnostic_event(
                    diagnostic,
                    default_source=DIAGNOSTIC_SOURCE_WORKFLOW_STATE,
                )
            )
    return deduplicate_diagnostic_events(diagnostics)


def _explanations_for_artifact(diagnostics, supplied_explanations) -> list[dict[str, object]]:
    if supplied_explanations is None:
        return explain_diagnostic_events(diagnostics) if diagnostics else []
    if not isinstance(supplied_explanations, (list, tuple)):
        raise ValueError("explanations must be a list or tuple.")
    return [_validate_explanation(explanation, f"explanations[{index}]") for index, explanation in enumerate(supplied_explanations)]


def _select_primary(diagnostics: list[dict[str, object]]) -> dict[str, object] | None:
    if not diagnostics:
        return None
    severity_order = {"error": 0, "warning": 1, "info": 2}
    source_order = {
        "workflow_state": 0,
        "gate": 1,
        "review": 2,
        "apply": 3,
        "verify": 4,
        "context": 5,
        "system": 6,
    }
    return sorted(
        diagnostics,
        key=lambda item: (
            severity_order.get(str(item.get("severity") or ""), 9),
            source_order.get(str(item.get("source") or ""), 9),
            str(item.get("code") or ""),
            str(item.get("message") or ""),
        ),
    )[0]


def _explanation_by_code(explanations: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    by_code = {}
    for explanation in explanations:
        by_code.setdefault(str(explanation.get("code")), explanation)
    return by_code


def _select_next_action(run_state, m1_diagnostics, primary, primary_explanation) -> str:
    if m1_diagnostics:
        return SAFE_RECOVERY_ACTION_REPAIR_RUN_STATE
    if primary_explanation is not None:
        return _safe_recovery_action(primary_explanation.get("next_action"))
    if primary is not None:
        action = primary.get("next_action")
        if action:
            return _safe_recovery_action(action)
        return SAFE_RECOVERY_ACTION_INSPECT_DETAILS
    if m1_diagnostics:
        return SAFE_RECOVERY_ACTION_REPAIR_RUN_STATE
    return _safe_recovery_action(suggest_next_workflow_action(run_state, m1_diagnostics))


def _summary_text(workflow_status, primary_explanation, primary) -> str:
    if primary_explanation is not None:
        return str(primary_explanation.get("explanation") or workflow_status.get("summary") or "")
    if primary is not None:
        return str(primary.get("message") or workflow_status.get("summary") or "")
    return str(workflow_status.get("summary") or "No failure evidence was supplied.")


def _metadata(metadata, **counts) -> dict[str, object]:
    if metadata is None:
        result = {}
    else:
        result = _validate_mapping(metadata, "metadata")
    result.update(
        {
            "diagnostic_count_total": counts["diagnostic_count_total"],
            "diagnostics_shown": counts["diagnostics_shown"],
            "diagnostics_truncated": counts["diagnostic_count_total"] > counts["diagnostics_shown"],
            "explanation_count_total": counts["explanation_count_total"],
            "explanations_shown": counts["explanations_shown"],
            "explanations_truncated": counts["explanation_count_total"] > counts["explanations_shown"],
            "recovery_guidance_count_total": counts["recovery_guidance_count_total"],
            "recovery_guidance_shown": counts["recovery_guidance_shown"],
            "recovery_guidance_truncated": counts["recovery_guidance_count_total"] > counts["recovery_guidance_shown"],
        }
    )
    return result


def _safe_recovery_action(action) -> str:
    text = str(action or "").strip()
    if text in UNSAFE_RECOVERY_ACTIONS:
        return SAFE_RECOVERY_ACTION_INSPECT_DETAILS
    if text == NEXT_ACTION_REPAIR_RUN_STATE:
        return SAFE_RECOVERY_ACTION_REPAIR_RUN_STATE
    if text == NEXT_ACTION_PREPARE_CONTEXT:
        return SAFE_RECOVERY_ACTION_PREPARE_CONTEXT
    if text == NEXT_ACTION_REQUEST_AI_RESPONSE:
        return SAFE_RECOVERY_ACTION_REQUEST_AI_RESPONSE
    if text == NEXT_ACTION_REVIEW_RESPONSE:
        return SAFE_RECOVERY_ACTION_REVIEW_RESPONSE
    if text == NEXT_ACTION_RUN_VERIFICATION:
        return SAFE_RECOVERY_ACTION_RUN_VERIFICATION
    if text == NEXT_ACTION_INSPECT_DIAGNOSTICS:
        return SAFE_RECOVERY_ACTION_INSPECT_DIAGNOSTICS
    if text in SAFE_RECOVERY_ACTIONS:
        return text
    return SAFE_RECOVERY_ACTION_INSPECT_DETAILS


def _recovery_priority(action: str) -> int:
    return SAFE_RECOVERY_ACTIONS.index(action) + 1


def _validate_stage(stage) -> str:
    if not isinstance(stage, str) or not stage.strip():
        raise ValueError("stage must be a non-empty string.")
    if stage not in RUN_ERROR_STAGES:
        raise ValueError(f"stage must be one of: {', '.join(RUN_ERROR_STAGES)}.")
    return stage


def _validate_explanation(explanation, field_name: str) -> dict[str, object]:
    mapping = _validate_mapping(explanation, field_name)
    required = (
        "code",
        "severity",
        "source",
        "title",
        "explanation",
        "why_it_matters",
        "affected_items",
        "next_action",
        "technical_details",
    )
    for key in required:
        if key not in mapping:
            raise ValueError(f"{field_name} is missing required field: {key}")
    _validate_nonempty_string(mapping["code"], f"{field_name}.code")
    _validate_nonempty_string(mapping["severity"], f"{field_name}.severity")
    _validate_nonempty_string(mapping["source"], f"{field_name}.source")
    _validate_nonempty_string(mapping["title"], f"{field_name}.title")
    _validate_nonempty_string(mapping["explanation"], f"{field_name}.explanation")
    _validate_nonempty_string(mapping["why_it_matters"], f"{field_name}.why_it_matters")
    _validate_list(mapping["affected_items"], f"{field_name}.affected_items")
    _safe_recovery_action(mapping["next_action"])
    _validate_mapping(mapping["technical_details"], f"{field_name}.technical_details")
    return _copy_json_ready(mapping, field_name)


def _validate_recovery_guidance(item, field_name: str) -> dict[str, object]:
    mapping = _validate_mapping(item, field_name)
    for key in ("action", "label", "reason", "priority"):
        if key not in mapping:
            raise ValueError(f"{field_name} is missing required field: {key}")
    action = _safe_recovery_action(mapping["action"])
    if action != mapping["action"]:
        raise ValueError(f"{field_name}.action must be a safe recovery action.")
    _validate_nonempty_string(mapping["label"], f"{field_name}.label")
    _validate_nonempty_string(mapping["reason"], f"{field_name}.reason")
    if not isinstance(mapping["priority"], int) or isinstance(mapping["priority"], bool):
        raise ValueError(f"{field_name}.priority must be an integer.")
    return _copy_json_ready(mapping, field_name)


def _validate_mapping(value, field_name: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be a mapping.")
    return _copy_json_ready(value, field_name)


def _validate_list(value, field_name: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list.")
    return _copy_json_ready(value, field_name)


def _validate_nonempty_string(value, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string.")
    return value


def _validate_optional_string(value, field_name: str) -> str | None:
    if value is None:
        return None
    return _validate_nonempty_string(value, field_name)


def _copy_json_ready(value, field_name: str):
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, list):
        return [
            _copy_json_ready(item, f"{field_name}[{index}]")
            for index, item in enumerate(value)
        ]
    if isinstance(value, Mapping):
        copied = {}
        for key in sorted(value):
            if not isinstance(key, str):
                raise ValueError(f"{field_name} keys must be strings.")
            copied[key] = _copy_json_ready(value[key], f"{field_name}.{key}")
        return copied
    raise ValueError(f"{field_name} must be JSON-ready.")


def _display_value(value) -> str:
    return str(value or "").replace("_", " ").title()
