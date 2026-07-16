import copy
import json

import strata.core.guided_workflow as guided_workflow
from strata.core.context_artifacts import build_run_state
from strata.core.diagnostics import (
    DIAGNOSTIC_SOURCE_REVIEW,
    DIAGNOSTIC_SEVERITY_ERROR,
    DIAGNOSTIC_SEVERITY_WARNING,
    build_diagnostic_event,
)
from strata.core.guided_workflow import (
    GUIDED_WORKFLOW_NEXT_ACTIONS,
    GUIDED_WORKFLOW_STAGES,
    build_guided_workflow_view,
)


def _state(**overrides) -> dict[str, object]:
    state = build_run_state(
        task="Fix auth guard",
        created_at="2026-07-15T00:00:00Z",
        baseline_commit="abc123",
        baseline_commit_attached=True,
        baseline_status="attached",
        baseline_warning=None,
        in_scope_files=["src/auth.py"],
        expected_related_files=["tests/test_auth.py"],
        allowed_new_files=[],
        prompt_hash=None,
        adapter="codex",
        patch_received=False,
        error=None,
    )
    state.update(overrides)
    return state


def _session(status: str) -> dict[str, object]:
    return {"status": status}


def _diagnostic(code: str, severity: str, message: str | None = None) -> dict[str, object]:
    return build_diagnostic_event(
        code,
        severity,
        message or f"{code} message.",
        source=DIAGNOSTIC_SOURCE_REVIEW,
    )


def test_stable_stage_vocabulary():
    assert GUIDED_WORKFLOW_STAGES == (
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


def test_stable_action_vocabulary():
    assert GUIDED_WORKFLOW_NEXT_ACTIONS == (
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


def test_result_is_json_ready():
    view = build_guided_workflow_view(workflow_state=_state())

    assert json.loads(json.dumps(view, allow_nan=False, sort_keys=True)) == view


def test_setup_required_state_recommends_run_setup():
    view = build_guided_workflow_view(workflow_state=_state(adapter=None))

    assert view["stage"] == "setup_required"
    assert view["next_action"] == "run_setup"


def test_ready_state_recommends_prepare_context():
    view = build_guided_workflow_view(workflow_state=_state())

    assert view["stage"] == "ready"
    assert view["next_action"] == "prepare_context"


def test_prepared_prompt_recommends_deliver_prompt():
    view = build_guided_workflow_view(workflow_state=_state(prompt_hash="hash"))

    assert view["stage"] == "prompt_ready"
    assert view["next_action"] == "deliver_prompt"


def test_delivered_prompt_recommends_provide_ai_response():
    view = build_guided_workflow_view(
        workflow_state=_state(prompt_hash="hash"),
        session_state=_session("delivered"),
    )

    assert view["stage"] == "awaiting_ai_response"
    assert view["next_action"] == "provide_ai_response"


def test_retry_ready_session_recommends_retry_ai_request():
    view = build_guided_workflow_view(
        workflow_state=_state(prompt_hash="hash"),
        session_state=_session("retry_ready"),
    )

    assert view["stage"] == "retry_available"
    assert view["next_action"] == "retry_ai_request"


def test_accepted_session_recommends_review_changes():
    view = build_guided_workflow_view(
        workflow_state=_state(prompt_hash="hash", patch_received=True),
        session_state=_session("accepted_for_review"),
    )

    assert view["stage"] == "ready_for_review"
    assert view["next_action"] == "review_changes"


def test_review_blocker_recommends_resolve_review_issues():
    view = build_guided_workflow_view(workflow_state=_state(prompt_hash="hash", patch_received=True, review_status="FAIL"))

    assert view["stage"] == "review_blocked"
    assert view["next_action"] == "resolve_review_issues"


def test_ready_to_apply_state_recommends_apply_changes():
    view = build_guided_workflow_view(workflow_state=_state(prompt_hash="hash", patch_received=True, review_status="PASS"))

    assert view["stage"] == "ready_to_apply"
    assert view["next_action"] == "apply_changes"


def test_apply_action_requires_confirmation():
    apply_view = build_guided_workflow_view(workflow_state=_state(prompt_hash="hash", patch_received=True, review_status="PASS"))
    review_view = build_guided_workflow_view(workflow_state=_state(prompt_hash="hash", patch_received=True))

    assert apply_view["confirmation_required"] is True
    assert review_view["confirmation_required"] is False


def test_verification_required_state_recommends_run_verification():
    view = build_guided_workflow_view(
        workflow_state=_state(prompt_hash="hash", patch_received=True, review_status="PASS", patch_applied=True)
    )

    assert view["stage"] == "verification_required"
    assert view["next_action"] == "run_verification"


def test_complete_state_returns_no_action():
    view = build_guided_workflow_view(
        workflow_state=_state(
            prompt_hash="hash",
            patch_received=True,
            review_status="PASS",
            patch_applied=True,
            verification_status="PASS",
            workflow_status="complete",
        )
    )

    assert view["stage"] == "complete"
    assert view["next_action"] == "none"


def test_blocking_diagnostics_override_normal_progress():
    view = build_guided_workflow_view(
        workflow_state=_state(prompt_hash="hash", patch_received=True, review_status="PASS"),
        diagnostics=[_diagnostic("unsafe_change", DIAGNOSTIC_SEVERITY_ERROR)],
    )

    assert view["stage"] == "review_blocked"
    assert view["next_action"] == "resolve_review_issues"
    assert view["blocking"] is True


def test_warnings_are_deterministic_and_deduplicated():
    diagnostics = [
        _diagnostic("dirty_worktree", DIAGNOSTIC_SEVERITY_WARNING, "Commit or stash your current changes."),
        _diagnostic("dirty_worktree", DIAGNOSTIC_SEVERITY_WARNING, "Commit or stash your current changes."),
        _diagnostic("scope", DIAGNOSTIC_SEVERITY_WARNING, "Review the changed files."),
    ]

    view = build_guided_workflow_view(workflow_state=_state(), diagnostics=list(reversed(diagnostics)))

    assert view["warnings"] == [
        {"code": "dirty_worktree", "message": "Commit or stash your current changes."},
        {"code": "scope", "message": "Review the changed files."},
    ]


def test_warning_count_is_bounded():
    diagnostics = [
        _diagnostic(f"warning_{index}", DIAGNOSTIC_SEVERITY_WARNING, f"Warning {index}.")
        for index in range(7)
    ]

    view = build_guided_workflow_view(workflow_state=_state(), diagnostics=diagnostics)

    assert len(view["warnings"]) == 5
    assert view["details"]["warning_total"] == 7
    assert view["details"]["warnings_truncated"] is True


def test_technical_internals_do_not_appear_in_normal_headline_text():
    view = build_guided_workflow_view(workflow_state=_state(prompt_hash="hash"))

    for internal in ("adapter payload", "canonical artifact", "representation tier", "state transition", "patch AST"):
        assert internal not in view["headline"]


def test_inputs_are_not_mutated():
    state = _state(warnings=[{"code": "a", "message": "A warning."}])
    session = _session("prepared")
    diagnostics = [_diagnostic("scope", DIAGNOSTIC_SEVERITY_WARNING)]
    before = (copy.deepcopy(state), copy.deepcopy(session), copy.deepcopy(diagnostics))

    build_guided_workflow_view(workflow_state=state, session_state=session, diagnostics=diagnostics)

    assert (state, session, diagnostics) == before


def test_outputs_are_fresh():
    state = _state(warnings=[{"code": "a", "message": "A warning."}])

    first = build_guided_workflow_view(workflow_state=state)
    second = build_guided_workflow_view(workflow_state=state)
    first["warnings"].append({"code": "changed", "message": "Changed."})
    first["details"]["decision_priority"] = "changed"

    assert second["warnings"] == [{"code": "a", "message": "A warning."}]
    assert second["details"]["decision_priority"] == "missing_context"


def test_repeated_calls_are_deterministic():
    state = _state(prompt_hash="hash", patch_received=True)
    diagnostics = [_diagnostic("scope", DIAGNOSTIC_SEVERITY_WARNING)]

    assert build_guided_workflow_view(workflow_state=state, diagnostics=diagnostics) == build_guided_workflow_view(
        workflow_state=state,
        diagnostics=diagnostics,
    )


def test_malformed_top_level_input_raises_value_error():
    for kwargs in (
        {"workflow_state": None},
        {"workflow_state": _state(), "session_state": []},
        {"workflow_state": _state(), "diagnostics": {}},
    ):
        try:
            build_guided_workflow_view(**kwargs)
        except ValueError:
            pass
        else:
            raise AssertionError("Malformed top-level input was accepted")


def test_contradictory_state_produces_conservative_blocking_output():
    view = build_guided_workflow_view(workflow_state=_state(workflow_status="complete"))

    assert view["stage"] == "review_blocked"
    assert view["next_action"] == "resolve_review_issues"
    assert view["details"]["decision_priority"] == "contradictory_state"


def test_no_filesystem_or_command_access_is_required():
    public_names = {name for name in vars(guided_workflow) if not name.startswith("_")}

    for forbidden in ("Path", "open", "os", "subprocess", "run_argv", "requests", "environ"):
        assert forbidden not in public_names


def test_no_import_from_strata_patch_or_commands():
    imported_core_modules = {
        guided_workflow._workflow_state.__name__,
        guided_workflow._session_state.__name__,
        guided_workflow._diagnostics.__name__,
    }

    assert imported_core_modules == {
        "strata.core.workflow_state",
        "strata.core.session_state",
        "strata.core.diagnostics",
    }


def test_architecture_invariant_has_no_new_violation():
    assert guided_workflow.__name__ == "strata.core.guided_workflow"
    assert "patch" not in {name for name in vars(guided_workflow) if not name.startswith("_")}
    assert "commands" not in {name for name in vars(guided_workflow) if not name.startswith("_")}


TESTS = [
    test_stable_stage_vocabulary,
    test_stable_action_vocabulary,
    test_result_is_json_ready,
    test_setup_required_state_recommends_run_setup,
    test_ready_state_recommends_prepare_context,
    test_prepared_prompt_recommends_deliver_prompt,
    test_delivered_prompt_recommends_provide_ai_response,
    test_retry_ready_session_recommends_retry_ai_request,
    test_accepted_session_recommends_review_changes,
    test_review_blocker_recommends_resolve_review_issues,
    test_ready_to_apply_state_recommends_apply_changes,
    test_apply_action_requires_confirmation,
    test_verification_required_state_recommends_run_verification,
    test_complete_state_returns_no_action,
    test_blocking_diagnostics_override_normal_progress,
    test_warnings_are_deterministic_and_deduplicated,
    test_warning_count_is_bounded,
    test_technical_internals_do_not_appear_in_normal_headline_text,
    test_inputs_are_not_mutated,
    test_outputs_are_fresh,
    test_repeated_calls_are_deterministic,
    test_malformed_top_level_input_raises_value_error,
    test_contradictory_state_produces_conservative_blocking_output,
    test_no_filesystem_or_command_access_is_required,
    test_no_import_from_strata_patch_or_commands,
    test_architecture_invariant_has_no_new_violation,
]
