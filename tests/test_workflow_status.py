import copy
import json

from strata.core.context_artifacts import build_run_state
from strata.core.diagnostic_explanations import summarize_diagnostic_explanations
from strata.core.diagnostics import (
    DIAGNOSTIC_SOURCE_GATE,
    DIAGNOSTIC_SEVERITY_ERROR,
    DIAGNOSTIC_SEVERITY_INFO,
    DIAGNOSTIC_SEVERITY_WARNING,
    build_diagnostic_event,
)
from strata.core.workflow_status import (
    STEP_APPLY_PATCH,
    STEP_PREPARE_CONTEXT,
    STEP_REQUEST_AI_RESPONSE,
    STEP_REVIEW_RESPONSE,
    STEP_RUN_VERIFICATION,
    STEP_WORKFLOW_COMPLETE,
    build_workflow_status,
    render_workflow_status_text,
)


def _state(**overrides) -> dict:
    state = build_run_state(
        task="Fix auth guard",
        created_at="2026-07-15T00:00:00Z",
        baseline_commit="abc123",
        baseline_commit_attached=True,
        baseline_status="attached",
        in_scope_files=["src/auth.py"],
        expected_related_files=[],
        allowed_new_files=[],
        prompt_hash="hash",
        adapter="codex",
        patch_received=False,
    )
    state.update(overrides)
    return state


def test_invalid_run_state_produces_invalid_health():
    status = build_workflow_status({})

    assert status["health"] == "invalid"
    assert status["current_step"] == "repair_run_state"


def test_missing_context_produces_prepare_context():
    status = build_workflow_status(_state(task=""))

    assert status["current_step"] == STEP_PREPARE_CONTEXT
    assert status["next_action"] == "prepare_context"


def test_context_ready_state_produces_request_ai_response():
    status = build_workflow_status(_state())

    assert status["current_step"] == STEP_REQUEST_AI_RESPONSE
    assert status["next_action"] == "request_ai_response"


def test_received_response_produces_review_response():
    status = build_workflow_status(_state(patch_received=True))

    assert status["current_step"] == STEP_REVIEW_RESPONSE
    assert status["next_action"] == "review_response"


def test_explicit_review_success_produces_apply_patch():
    status = build_workflow_status(_state(patch_received=True, review_status="PASS"))

    assert status["current_step"] == STEP_APPLY_PATCH
    assert status["next_action"] == "apply_patch"


def test_ready_to_apply_without_explicit_review_success_does_not_complete_review():
    status = build_workflow_status(_state(patch_received=True, workflow_status="ready_to_apply"))

    assert STEP_REVIEW_RESPONSE not in status["completed_steps"]
    assert status["current_step"] == STEP_REVIEW_RESPONSE


def test_applied_patch_produces_run_verification():
    status = build_workflow_status(_state(patch_received=True, review_status="PASS", patch_applied=True))

    assert status["current_step"] == STEP_RUN_VERIFICATION
    assert status["next_action"] == "run_verification"


def test_complete_status_requires_explicit_verification_success():
    incomplete = build_workflow_status(_state(workflow_status="complete"))
    complete = build_workflow_status(
        _state(
            workflow_status="complete",
            patch_received=True,
            review_status="PASS",
            patch_applied=True,
            verification_status="PASS",
        )
    )

    assert incomplete["current_step"] != STEP_WORKFLOW_COMPLETE
    assert complete["health"] == "complete"
    assert complete["current_step"] == STEP_WORKFLOW_COMPLETE


def test_explicit_failure_produces_blocked_status():
    status = build_workflow_status(_state(error="failed"))

    assert status["health"] == "blocked"
    assert status["current_step"] == "inspect_diagnostics"


def test_completed_steps_use_explicit_evidence_only():
    status = build_workflow_status(_state(workflow_status="ready_to_apply"))

    assert status["completed_steps"] == [STEP_PREPARE_CONTEXT]


def test_pending_steps_begin_at_first_incomplete_step():
    status = build_workflow_status(_state(patch_received=True, review_status="PASS"))

    assert status["pending_steps"] == [STEP_APPLY_PATCH, STEP_RUN_VERIFICATION, STEP_WORKFLOW_COMPLETE]


def test_step_ordering_is_deterministic():
    first = build_workflow_status(_state(patch_received=True, review_status="PASS", patch_applied=True))
    second = build_workflow_status(_state(patch_received=True, review_status="PASS", patch_applied=True))

    assert first["completed_steps"] == second["completed_steps"]
    assert first["pending_steps"] == second["pending_steps"]


def test_diagnostic_errors_count_as_blocking():
    status = build_workflow_status(_state(), diagnostics=[_diagnostic("error", DIAGNOSTIC_SEVERITY_ERROR)])

    assert status["blocking_issues"] == 1
    assert status["health"] == "blocked"


def test_diagnostic_warnings_are_counted():
    status = build_workflow_status(_state(), diagnostics=[_diagnostic("warning", DIAGNOSTIC_SEVERITY_WARNING)])

    assert status["warning_count"] == 1


def test_info_diagnostics_do_not_block():
    status = build_workflow_status(_state(), diagnostics=[_diagnostic("info", DIAGNOSTIC_SEVERITY_INFO)])

    assert status["blocking_issues"] == 0
    assert status["health"] == "healthy"


def test_explanation_summary_metadata_is_compact():
    explanations = [
        {
            "code": "gate_unresolved_imports",
            "severity": "error",
            "source": "gate",
            "title": "Title",
            "explanation": "Explanation",
            "why_it_matters": "Why",
            "affected_items": [],
            "next_action": "fix_imports",
            "technical_details": {"large": ["not copied into status"]},
        }
    ]
    status = build_workflow_status(_state(), explanations=explanations)

    assert status["details"] == {
        "diagnostic_total": 0,
        "explanation_total": 1,
        "primary_issue_code": None,
        "primary_next_action": "fix_imports",
    }


def test_unknown_extra_run_state_fields_do_not_crash():
    status = build_workflow_status(_state(extra={"anything": ["goes"]}))

    assert status["current_step"] == STEP_REQUEST_AI_RESPONSE


def test_none_and_empty_states_are_safe():
    assert build_workflow_status(None)["health"] == "invalid"
    assert build_workflow_status({})["health"] == "invalid"


def test_inputs_are_not_mutated():
    state = _state(patch_received=True)
    diagnostics = [_diagnostic("warning", DIAGNOSTIC_SEVERITY_WARNING)]
    explanations = []
    original = (copy.deepcopy(state), copy.deepcopy(diagnostics), copy.deepcopy(explanations))

    build_workflow_status(state, diagnostics=diagnostics, explanations=explanations)

    assert (state, diagnostics, explanations) == original


def test_repeated_calls_are_identical():
    state = _state(patch_received=True)

    assert build_workflow_status(state) == build_workflow_status(state)


def test_output_is_json_ready():
    status = build_workflow_status(_state(patch_received=True))

    assert json.loads(json.dumps(status, allow_nan=False)) == status


def test_titles_and_summaries_are_deterministic():
    status = build_workflow_status(_state(patch_received=True))

    assert status["title"] == "Review the proposed changes."
    assert status["summary"] == "Strata has received a response, but it has not been approved yet."


def test_next_action_labels_are_deterministic():
    status = build_workflow_status(_state(patch_received=True, review_status="PASS"))

    assert status["next_action_label"] == "Apply the reviewed patch"


def test_text_rendering_is_deterministic():
    status = build_workflow_status(_state(patch_received=True))

    assert render_workflow_status_text(status) == render_workflow_status_text(status)


def test_text_rendering_contains_status_step_counts_and_next_action():
    text = render_workflow_status_text(
        build_workflow_status(_state(patch_received=True), diagnostics=[_diagnostic("warning", DIAGNOSTIC_SEVERITY_WARNING)])
    )

    assert "Status:" in text
    assert "Current step:" in text
    assert "Blocking issues: 0" in text
    assert "Warnings: 1" in text
    assert "Next action:" in text


def test_text_rendering_contains_no_ansi_escape_sequences():
    text = render_workflow_status_text(build_workflow_status(_state()))

    assert "\x1b[" not in text


def test_no_unsafe_bypass_action_appears():
    status = build_workflow_status(_state(patch_received=True, review_status="PASS"))
    text = render_workflow_status_text(status)

    for unsafe in ("force_apply", "ignore_warning", "disable_gate", "bypass_review"):
        assert unsafe not in json.dumps(status)
        assert unsafe not in text


def test_m1_m2_m3_behavior_remains_compatible():
    diagnostic = _diagnostic("warning", DIAGNOSTIC_SEVERITY_WARNING)
    explanation_summary = summarize_diagnostic_explanations([])
    status = build_workflow_status(_state(), diagnostics=[diagnostic], explanations=[])

    assert diagnostic["source"] == "gate"
    assert explanation_summary["total"] == 0
    assert status["warning_count"] == 1


def _diagnostic(code: str, severity: str) -> dict[str, object]:
    return build_diagnostic_event(
        code,
        severity,
        f"{code} message.",
        source=DIAGNOSTIC_SOURCE_GATE,
    )


TESTS = [
    test_invalid_run_state_produces_invalid_health,
    test_missing_context_produces_prepare_context,
    test_context_ready_state_produces_request_ai_response,
    test_received_response_produces_review_response,
    test_explicit_review_success_produces_apply_patch,
    test_ready_to_apply_without_explicit_review_success_does_not_complete_review,
    test_applied_patch_produces_run_verification,
    test_complete_status_requires_explicit_verification_success,
    test_explicit_failure_produces_blocked_status,
    test_completed_steps_use_explicit_evidence_only,
    test_pending_steps_begin_at_first_incomplete_step,
    test_step_ordering_is_deterministic,
    test_diagnostic_errors_count_as_blocking,
    test_diagnostic_warnings_are_counted,
    test_info_diagnostics_do_not_block,
    test_explanation_summary_metadata_is_compact,
    test_unknown_extra_run_state_fields_do_not_crash,
    test_none_and_empty_states_are_safe,
    test_inputs_are_not_mutated,
    test_repeated_calls_are_identical,
    test_output_is_json_ready,
    test_titles_and_summaries_are_deterministic,
    test_next_action_labels_are_deterministic,
    test_text_rendering_is_deterministic,
    test_text_rendering_contains_status_step_counts_and_next_action,
    test_text_rendering_contains_no_ansi_escape_sequences,
    test_no_unsafe_bypass_action_appears,
    test_m1_m2_m3_behavior_remains_compatible,
]
