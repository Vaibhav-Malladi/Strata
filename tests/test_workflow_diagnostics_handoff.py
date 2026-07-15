from pathlib import Path

from strata.core.diagnostic_explanations import AFFECTED_ITEM_LIMIT, explain_diagnostic_event
from strata.core.diagnostics import (
    DIAGNOSTIC_SEVERITIES,
    DIAGNOSTIC_SOURCES,
    normalize_diagnostic_event,
    summarize_diagnostic_events,
)
from strata.core.error_artifacts import (
    MAX_RECOVERY_GUIDANCE,
    MAX_RUN_ERROR_DIAGNOSTICS,
    MAX_RUN_ERROR_EXPLANATIONS,
    RUN_ERROR_ARTIFACT_TYPE,
    RUN_ERROR_SCHEMA_VERSION,
    RUN_ERROR_STAGES,
    build_run_error_artifact,
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
    WORKFLOW_STATUSES,
    build_workflow_state_summary,
    suggest_next_workflow_action,
    validate_workflow_state,
)
from strata.core.workflow_status import WORKFLOW_HEALTH_VALUES, build_workflow_status


DOC_PATH = Path("docs/roadmap/workflow-state-diagnostics.md")


def _doc() -> str:
    return DOC_PATH.read_text(encoding="utf-8")


def test_part_m_core_modules_are_available():
    assert callable(validate_workflow_state)
    assert callable(build_workflow_state_summary)
    assert callable(suggest_next_workflow_action)
    assert callable(normalize_diagnostic_event)
    assert callable(summarize_diagnostic_events)
    assert callable(explain_diagnostic_event)
    assert callable(build_workflow_status)
    assert callable(build_run_error_artifact)


def test_workflow_status_vocabulary_is_bounded():
    assert WORKFLOW_STATUSES == (
        "not_started",
        "context_ready",
        "awaiting_ai_response",
        "response_received",
        "review_required",
        "ready_to_apply",
        "verification_required",
        "complete",
        "blocked",
        "failed",
    )


def test_m1_next_action_vocabulary_is_bounded():
    assert (
        NEXT_ACTION_REPAIR_RUN_STATE,
        NEXT_ACTION_PREPARE_CONTEXT,
        NEXT_ACTION_REQUEST_AI_RESPONSE,
        NEXT_ACTION_REVIEW_RESPONSE,
        NEXT_ACTION_APPLY_PATCH,
        NEXT_ACTION_RUN_VERIFICATION,
        NEXT_ACTION_WORKFLOW_COMPLETE,
        NEXT_ACTION_INSPECT_DIAGNOSTICS,
    ) == (
        "repair_or_regenerate_run_state",
        "prepare_context",
        "request_ai_response",
        "review_response",
        "apply_patch",
        "run_verification",
        "workflow_complete",
        "inspect_diagnostics",
    )


def test_diagnostic_vocabularies_are_bounded():
    assert DIAGNOSTIC_SEVERITIES == ("info", "warning", "error")
    assert DIAGNOSTIC_SOURCES == (
        "workflow_state",
        "context",
        "review",
        "apply",
        "verify",
        "gate",
        "system",
    )


def test_workflow_health_vocabulary_is_bounded():
    assert WORKFLOW_HEALTH_VALUES == (
        "healthy",
        "attention",
        "blocked",
        "invalid",
        "complete",
    )


def test_m3_and_m5_limits_match_stable_contracts():
    assert AFFECTED_ITEM_LIMIT == 20
    assert MAX_RUN_ERROR_DIAGNOSTICS == 25
    assert MAX_RUN_ERROR_EXPLANATIONS == 25
    assert MAX_RECOVERY_GUIDANCE == 10


def test_run_error_artifact_contract_constants_are_stable():
    assert RUN_ERROR_SCHEMA_VERSION == 1
    assert RUN_ERROR_ARTIFACT_TYPE == "run_error"
    assert RUN_ERROR_STAGES == (
        "prepare",
        "context",
        "ai_response",
        "review",
        "apply",
        "verify",
        "gate",
        "workflow",
        "unknown",
    )


def test_roadmap_exists_and_has_part_m_batch_labels():
    assert DOC_PATH.exists()
    content = _doc()
    assert content.strip()

    for label in ("M1", "M2", "M3", "M4", "M5", "M6"):
        assert label in content


def test_roadmap_has_handoff_and_remaining_roadmap_labels():
    content = _doc()

    assert "Part O" in content
    for label in ("O", "N", "Q", "P"):
        assert f"- {label} " in content


TESTS = [
    test_part_m_core_modules_are_available,
    test_workflow_status_vocabulary_is_bounded,
    test_m1_next_action_vocabulary_is_bounded,
    test_diagnostic_vocabularies_are_bounded,
    test_workflow_health_vocabulary_is_bounded,
    test_m3_and_m5_limits_match_stable_contracts,
    test_run_error_artifact_contract_constants_are_stable,
    test_roadmap_exists_and_has_part_m_batch_labels,
    test_roadmap_has_handoff_and_remaining_roadmap_labels,
]
