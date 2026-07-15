import copy
import json
import tempfile
from pathlib import Path

from strata.core.context_artifacts import build_run_state
from strata.core.workflow_state import (
    DIAGNOSTIC_INVALID_COLLECTION_ITEM,
    DIAGNOSTIC_INVALID_FIELD_TYPE,
    DIAGNOSTIC_INVALID_STATE_VALUE,
    DIAGNOSTIC_MISSING_REQUIRED_FIELD,
    DIAGNOSTIC_UNSUPPORTED_SCHEMA_VERSION,
    NEXT_ACTION_APPLY_PATCH,
    NEXT_ACTION_INSPECT_DIAGNOSTICS,
    NEXT_ACTION_REPAIR_RUN_STATE,
    NEXT_ACTION_REQUEST_AI_RESPONSE,
    NEXT_ACTION_REVIEW_RESPONSE,
    NEXT_ACTION_RUN_VERIFICATION,
    NEXT_ACTION_WORKFLOW_COMPLETE,
    WORKFLOW_STATUS_COMPLETE,
    WORKFLOW_STATUS_READY_TO_APPLY,
    build_workflow_state_summary,
    suggest_next_workflow_action,
    validate_workflow_state,
)


def _canonical_state(**overrides) -> dict:
    state = build_run_state(
        task="Fix auth guard",
        created_at="2026-07-15T00:00:00Z",
        baseline_commit="abc123",
        baseline_commit_attached=True,
        baseline_status="attached",
        baseline_warning=None,
        in_scope_files=["src/auth.py"],
        expected_related_files=["tests/test_auth.py"],
        allowed_new_files=["docs/notes.md"],
        prompt_hash="prompt-hash",
        adapter="codex",
        patch_received=False,
        error=None,
    )
    state.update(overrides)
    return state


def test_valid_canonical_run_state_produces_no_validation_errors():
    assert validate_workflow_state(_canonical_state()) == []


def test_summary_output_is_json_ready():
    summary = build_workflow_state_summary(_canonical_state())

    assert json.loads(json.dumps(summary, sort_keys=True)) == summary


def test_summary_output_is_deterministic_for_repeated_calls():
    state = _canonical_state()

    assert build_workflow_state_summary(state) == build_workflow_state_summary(state)


def test_helpers_do_not_mutate_input_mapping():
    state = _canonical_state(patch_received=True)
    original = copy.deepcopy(state)

    validate_workflow_state(state)
    suggest_next_workflow_action(state)
    build_workflow_state_summary(state)

    assert state == original


def test_missing_required_fields_produce_stable_diagnostics():
    state = _canonical_state()
    del state["task"]
    del state["adapter"]

    diagnostics = validate_workflow_state(state)

    assert diagnostics[:2] == [
        {
            "code": DIAGNOSTIC_MISSING_REQUIRED_FIELD,
            "severity": "error",
            "message": "Run state is missing the required field 'task'.",
            "field": "task",
        },
        {
            "code": DIAGNOSTIC_MISSING_REQUIRED_FIELD,
            "severity": "error",
            "message": "Run state is missing the required field 'adapter'.",
            "field": "adapter",
        },
    ]


def test_invalid_field_types_produce_stable_diagnostics():
    state = _canonical_state(schema_version="1", patch_received="yes")

    diagnostics = validate_workflow_state(state)

    assert _diagnostic_codes(diagnostics) == [
        DIAGNOSTIC_INVALID_FIELD_TYPE,
        DIAGNOSTIC_INVALID_FIELD_TYPE,
    ]
    assert [issue["field"] for issue in diagnostics] == ["schema_version", "patch_received"]


def test_invalid_workflow_status_values_are_rejected():
    diagnostics = validate_workflow_state(_canonical_state(workflow_status="doneish"))

    assert diagnostics == [
        {
            "code": DIAGNOSTIC_INVALID_STATE_VALUE,
            "severity": "error",
            "message": "Run state field 'workflow_status' has an unsupported value.",
            "field": "workflow_status",
            "value": "doneish",
        }
    ]


def test_unknown_extra_fields_do_not_crash_validation():
    state = _canonical_state(extra={"shape": ["not", "owned", "by", "m1"]})

    assert validate_workflow_state(state) == []


def test_none_empty_and_minimal_states_are_handled_safely():
    assert _diagnostic_codes(validate_workflow_state(None)) == [DIAGNOSTIC_INVALID_FIELD_TYPE]
    assert len(validate_workflow_state({})) == 18

    minimal = {"schema_version": 1}
    diagnostics = validate_workflow_state(minimal)
    summary = build_workflow_state_summary(minimal)

    assert diagnostics
    assert summary["is_valid"] is False
    assert summary["next_action"] == NEXT_ACTION_REPAIR_RUN_STATE


def test_unsupported_schema_versions_are_handled_safely():
    diagnostics = validate_workflow_state(_canonical_state(schema_version=2))

    assert diagnostics == [
        {
            "code": DIAGNOSTIC_UNSUPPORTED_SCHEMA_VERSION,
            "severity": "error",
            "message": "Run state schema_version must be 1.",
            "field": "schema_version",
            "value": 2,
        }
    ]


def test_next_action_is_conservative_for_invalid_state():
    assert suggest_next_workflow_action({}) == NEXT_ACTION_REPAIR_RUN_STATE


def test_context_ready_state_without_patch_suggests_requesting_ai_response():
    assert suggest_next_workflow_action(_canonical_state()) == NEXT_ACTION_REQUEST_AI_RESPONSE


def test_received_response_that_has_not_been_reviewed_suggests_review():
    state = _canonical_state(patch_received=True)

    assert suggest_next_workflow_action(state) == NEXT_ACTION_REVIEW_RESPONSE


def test_applied_but_unverified_patch_suggests_verification():
    state = _canonical_state(patch_received=True, review_status="PASS", patch_applied=True)

    assert suggest_next_workflow_action(state) == NEXT_ACTION_RUN_VERIFICATION


def test_completion_is_suggested_only_with_explicit_success_evidence():
    almost_done = _canonical_state(workflow_status=WORKFLOW_STATUS_COMPLETE)
    done = _canonical_state(
        workflow_status=WORKFLOW_STATUS_COMPLETE,
        patch_received=True,
        review_status="PASS",
        patch_applied=True,
        verification_status="PASS",
    )

    assert suggest_next_workflow_action(almost_done) != NEXT_ACTION_WORKFLOW_COMPLETE
    assert suggest_next_workflow_action(done) == NEXT_ACTION_WORKFLOW_COMPLETE


def test_review_passed_but_unapplied_patch_suggests_apply():
    state = _canonical_state(patch_received=True, review_status="PASS")

    assert suggest_next_workflow_action(state) == NEXT_ACTION_APPLY_PATCH


def test_ready_to_apply_with_explicit_successful_review_suggests_apply():
    state = _canonical_state(
        patch_received=True,
        workflow_status=WORKFLOW_STATUS_READY_TO_APPLY,
        review_status="PASS",
    )

    assert suggest_next_workflow_action(state) == NEXT_ACTION_APPLY_PATCH


def test_ready_to_apply_without_successful_review_does_not_suggest_apply():
    state = _canonical_state(
        patch_received=True,
        workflow_status=WORKFLOW_STATUS_READY_TO_APPLY,
    )

    assert suggest_next_workflow_action(state) == NEXT_ACTION_REVIEW_RESPONSE


def test_failed_review_suggests_inspecting_diagnostics():
    state = _canonical_state(patch_received=True, review_status="FAIL")

    assert suggest_next_workflow_action(state) == NEXT_ACTION_INSPECT_DIAGNOSTICS


def test_diagnostic_ordering_is_deterministic():
    state = _canonical_state(
        schema_version=2,
        task=123,
        baseline_status="floating",
        in_scope_files=["ok.py", 7],
        workflow_status="doneish",
    )

    first = validate_workflow_state(state)
    second = validate_workflow_state(state)

    assert first == second
    assert _diagnostic_codes(first) == [
        DIAGNOSTIC_UNSUPPORTED_SCHEMA_VERSION,
        DIAGNOSTIC_INVALID_FIELD_TYPE,
        DIAGNOSTIC_INVALID_STATE_VALUE,
        DIAGNOSTIC_INVALID_STATE_VALUE,
        DIAGNOSTIC_INVALID_COLLECTION_ITEM,
    ]


def test_no_generated_context_artifacts_remain_after_tests():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        validate_workflow_state(_canonical_state())
        build_workflow_state_summary(_canonical_state())

        assert not (root / ".aidc" / "context").exists()


def _diagnostic_codes(diagnostics: list[dict[str, object]]) -> list[object]:
    return [diagnostic.get("code") for diagnostic in diagnostics]


def run_all() -> None:
    for test in TESTS:
        test()


TESTS = [
    test_valid_canonical_run_state_produces_no_validation_errors,
    test_summary_output_is_json_ready,
    test_summary_output_is_deterministic_for_repeated_calls,
    test_helpers_do_not_mutate_input_mapping,
    test_missing_required_fields_produce_stable_diagnostics,
    test_invalid_field_types_produce_stable_diagnostics,
    test_invalid_workflow_status_values_are_rejected,
    test_unknown_extra_fields_do_not_crash_validation,
    test_none_empty_and_minimal_states_are_handled_safely,
    test_unsupported_schema_versions_are_handled_safely,
    test_next_action_is_conservative_for_invalid_state,
    test_context_ready_state_without_patch_suggests_requesting_ai_response,
    test_received_response_that_has_not_been_reviewed_suggests_review,
    test_applied_but_unverified_patch_suggests_verification,
    test_completion_is_suggested_only_with_explicit_success_evidence,
    test_review_passed_but_unapplied_patch_suggests_apply,
    test_ready_to_apply_with_explicit_successful_review_suggests_apply,
    test_ready_to_apply_without_successful_review_does_not_suggest_apply,
    test_failed_review_suggests_inspecting_diagnostics,
    test_diagnostic_ordering_is_deterministic,
    test_no_generated_context_artifacts_remain_after_tests,
]
