import contextlib
import inspect
import json
import sys
import tempfile
from pathlib import Path

import strata.commands.cli as cli_module
import strata.commands.cli_help as cli_help
import strata.commands.start_command as start_command
from tests.helpers import capture_output, change_directory
from workflow_config import default_config, save_config


@contextlib.contextmanager
def change_argv(args: list[str]):
    original = sys.argv[:]
    sys.argv = args
    try:
        yield
    finally:
        sys.argv = original


def _run_state(**overrides) -> dict[str, object]:
    state = {
        "schema_version": 1,
        "task": "Fix auth guard",
        "created_at": "2026-07-15T00:00:00Z",
        "baseline_commit": "abc123",
        "baseline_commit_attached": True,
        "baseline_status": "attached",
        "baseline_warning": None,
        "in_scope_files": ["src/auth.py"],
        "expected_related_files": [],
        "allowed_new_files": [],
        "prompt_hash": "hash",
        "adapter": "codex",
        "patch_received": False,
        "error": None,
        "workspace_mode": "single_repo",
        "workspace": None,
        "cross_repo_references": [],
        "internal_libraries": [],
    }
    state.update(overrides)
    return state


def _write_run_state(root: Path, state: dict[str, object]) -> None:
    path = root / ".aidc" / "context" / "run_state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state), encoding="utf-8")


def _save_config(root: Path) -> None:
    save_config(default_config(), root)


def _guided_view(**overrides) -> dict[str, object]:
    view = {
        "schema_version": 1,
        "stage": "ready_for_review",
        "headline": "The AI response is ready for review.",
        "summary": "Strata validated the response structure and scope.",
        "next_action": "review_changes",
        "next_action_label": "Review the proposed changes",
        "confirmation_required": False,
        "blocking": False,
        "warnings": [],
        "details": {},
    }
    view.update(overrides)
    return view


def test_strata_start_remains_registered_once():
    source = inspect.getsource(cli_module)

    assert source.count('command == "start"') == 1


def test_start_is_described_as_recommended_normal_entry_point():
    lines = dict(cli_help._main_workflow_lines())

    assert lines["strata start [path]"] == "Continue with Strata's recommended next step."


def test_command_uses_n1_guided_view():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _save_config(root)
        calls = []
        original = start_command.guided_workflow.build_guided_workflow_view

        def fake_build_guided_workflow_view(**kwargs):
            calls.append(kwargs)
            return _guided_view()

        start_command.guided_workflow.build_guided_workflow_view = fake_build_guided_workflow_view
        try:
            exit_code, output = capture_output(start_command.write_start_command, str(root))
        finally:
            start_command.guided_workflow.build_guided_workflow_view = original

        assert exit_code == 0
        assert calls
        assert calls[0]["session_state"] is None
        assert "The AI response is ready for review." in output


def test_output_contains_n1_headline_and_summary():
    output = start_command.build_start_command_output(_guided_view())

    assert "The AI response is ready for review." in output
    assert "Strata validated the response structure and scope." in output


def test_guided_progress_has_eight_stable_display_steps():
    progress = start_command.build_guided_progress("ready_for_review")

    assert [item["label"] for item in progress] == [
        "Setup",
        "Prepare context",
        "Send to AI",
        "Receive response",
        "Review",
        "Apply",
        "Verify",
        "Complete",
    ]


def test_each_n1_stage_maps_to_one_progress_step():
    expected = {
        "setup_required": "setup",
        "ready": "prepare_context",
        "context_prepared": "prepare_context",
        "prompt_ready": "send_to_ai",
        "awaiting_ai_response": "send_to_ai",
        "response_received": "receive_response",
        "retry_available": "receive_response",
        "ready_for_review": "review",
        "review_blocked": "review",
        "ready_to_apply": "apply",
        "verification_required": "verify",
        "complete": "complete",
    }

    for stage, key in expected.items():
        current = [
            item
            for item in start_command.build_guided_progress(stage, blocking=stage == "review_blocked")
            if item["state"] in {"current", "blocked"}
        ]
        if stage == "complete":
            assert all(item["state"] == "complete" for item in start_command.build_guided_progress(stage))
        else:
            assert current == [
                {
                    "key": key,
                    "label": dict(start_command._PROGRESS_STEPS)[key],
                    "state": "blocked" if stage == "review_blocked" else "current",
                }
            ]


def test_completed_current_and_future_steps_are_marked():
    progress = start_command.build_guided_progress("ready_for_review")

    assert progress[0]["state"] == "complete"
    assert progress[4]["state"] == "current"
    assert progress[5]["state"] == "upcoming"


def test_blocking_review_state_marks_review_as_blocked():
    progress = start_command.build_guided_progress("review_blocked", blocking=True)

    assert progress[4] == {"key": "review", "label": "Review", "state": "blocked"}


def test_stage_labels_are_plain_language_and_hide_raw_stage_values():
    output = start_command.build_start_command_output(_guided_view(stage="awaiting_ai_response"))

    assert "Waiting for AI response" in output
    assert "awaiting_ai_response" not in output


def test_progress_section_is_shown():
    output = start_command.build_start_command_output(_guided_view())

    assert "Progress" in output
    assert "[done] Setup" in output
    assert "[now] Review" in output


def test_warning_section_is_omitted_when_empty():
    output = start_command.build_start_command_output(_guided_view(warnings=[]))

    assert "Warnings" not in output


def test_non_complete_output_contains_exactly_one_next_action_section():
    output = start_command.build_start_command_output(_guided_view())

    assert _next_section_count(output) == 1


def test_completed_output_contains_no_next_action_section():
    output = start_command.build_start_command_output(
        _guided_view(
            stage="complete",
            headline="The workflow is complete.",
            summary="The changes were reviewed, applied, and verified.",
            next_action="none",
            next_action_label="No action needed",
        )
    )

    assert _next_section_count(output) == 0


def test_apply_next_action_displays_confirmation_guidance():
    output = start_command.build_start_command_output(
        _guided_view(
            stage="ready_to_apply",
            next_action="apply_changes",
            next_action_label="Apply the reviewed changes",
            confirmation_required=True,
        )
    )

    assert "Next step\nApply the reviewed changes" in output
    assert "Confirmation will be required before repository files are changed." in output


def test_apply_is_not_executed():
    source = inspect.getsource(start_command)

    assert "write_apply_command" not in source
    assert "apply_patch" not in source


def test_warnings_are_shown_deterministically():
    output = start_command.build_start_command_output(
        _guided_view(
            warnings=[
                {"code": "a", "message": "First warning."},
                {"code": "b", "message": "Second warning."},
            ]
        )
    )

    assert output.index("First warning.") < output.index("Second warning.")
    assert "Warnings" in output


def test_multiple_warnings_do_not_create_multiple_primary_actions():
    output = start_command.build_start_command_output(
        _guided_view(
            warnings=[
                {"code": "a", "message": "First warning."},
                {"code": "b", "message": "Second warning."},
            ]
        )
    )

    assert _next_section_count(output) == 1


def test_missing_optional_session_state_is_handled():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _save_config(root)

        view = start_command.build_start_guided_view(str(root))

        assert view["stage"] == "ready"
        assert view["next_action"] == "prepare_context"


def test_missing_setup_state_produces_conservative_guided_result():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        view = start_command.build_start_guided_view(str(root))

        assert view["stage"] == "setup_required"
        assert view["next_action"] == "run_setup"


def test_workflow_blockers_do_not_produce_command_menu():
    output = start_command.build_start_command_output(
        _guided_view(
            stage="review_blocked",
            headline="Fix the review issues before applying.",
            summary="Strata found an issue that blocks progress.",
            next_action="resolve_review_issues",
            next_action_label="Fix the review issues",
            blocking=True,
        )
    )

    assert _next_section_count(output) == 1
    assert "strata ask" not in output
    assert "strata review" not in output
    assert "strata apply" not in output


def test_malformed_required_state_follows_existing_cli_error_behavior():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        path = root / ".aidc" / "context" / "run_state.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not json", encoding="utf-8")

        exit_code, output = capture_output(start_command.write_start_command, str(root))

        assert exit_code == 1
        assert "Start could not continue." in output
        assert "Traceback" not in output
        assert _next_section_count(output) == 1


def test_output_helper_is_deterministic():
    view = _guided_view()

    assert start_command.build_start_command_output(view) == start_command.build_start_command_output(view)


def test_input_guided_mapping_is_not_mutated():
    view = _guided_view(warnings=[{"code": "a", "message": "First warning."}])
    before = json.loads(json.dumps(view))

    start_command.build_start_command_output(view)

    assert view == before


def test_existing_advanced_commands_remain_registered():
    source = inspect.getsource(cli_module)

    for command in ('"ask"', '"run"', '"prepare"', '"review"', '"apply"', '"verify"', '"gate"', '"status"'):
        assert command in source


def test_no_model_patch_apply_git_verification_or_delivery_action_is_invoked():
    source = inspect.getsource(start_command)

    for forbidden in ("check_adapter", "write_apply", "write_verify", "execute_command", "run_argv", "git", "deliver"):
        assert forbidden not in source


def test_no_rich_panel_or_scan_progress_bar_dependency_is_introduced():
    source = inspect.getsource(start_command)

    for forbidden in ("rich", "Panel", "print_status_card", "status_spinner"):
        assert forbidden not in source


def test_no_workflow_decision_logic_is_duplicated():
    source = inspect.getsource(start_command)

    for forbidden in ("review_status", "verification_status", "patch_received", "workflow_status"):
        assert forbidden not in source


def test_new_internal_imports_use_direct_fully_qualified_module_imports():
    source = inspect.getsource(start_command)

    assert "import strata.core.guided_workflow as guided_workflow" in source
    assert "import strata.core.context_artifacts as context_artifacts" in source


def test_no_from_strata_core_import_module_form_exists():
    source = inspect.getsource(start_command)

    assert "from strata.core import" not in source


def test_package_layering_invariant_has_no_new_violation():
    assert start_command.guided_workflow.__name__ == "strata.core.guided_workflow"
    assert start_command.context_artifacts.__name__ == "strata.core.context_artifacts"


def test_cli_routes_start_to_guided_command():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_run_state(root, _run_state(patch_received=True))

        with change_directory(root):
            with change_argv(["cli.py", "start"]):
                exit_code, output = capture_output(cli_module.main)

        assert exit_code == 0
        assert "The AI response is ready for review." in output
        assert _next_section_count(output) == 1


def test_plain_text_fallback_is_readable_without_ansi_assumptions():
    output = start_command.build_start_command_output(_guided_view())

    assert "\x1b[" not in output
    assert "[done] Setup" in output
    assert "[now] Review" in output


def _next_section_count(output: str) -> int:
    return sum(1 for line in output.splitlines() if line == "Next step")


TESTS = [
    test_strata_start_remains_registered_once,
    test_start_is_described_as_recommended_normal_entry_point,
    test_command_uses_n1_guided_view,
    test_output_contains_n1_headline_and_summary,
    test_guided_progress_has_eight_stable_display_steps,
    test_each_n1_stage_maps_to_one_progress_step,
    test_completed_current_and_future_steps_are_marked,
    test_blocking_review_state_marks_review_as_blocked,
    test_stage_labels_are_plain_language_and_hide_raw_stage_values,
    test_progress_section_is_shown,
    test_warning_section_is_omitted_when_empty,
    test_non_complete_output_contains_exactly_one_next_action_section,
    test_completed_output_contains_no_next_action_section,
    test_apply_next_action_displays_confirmation_guidance,
    test_apply_is_not_executed,
    test_warnings_are_shown_deterministically,
    test_multiple_warnings_do_not_create_multiple_primary_actions,
    test_missing_optional_session_state_is_handled,
    test_missing_setup_state_produces_conservative_guided_result,
    test_workflow_blockers_do_not_produce_command_menu,
    test_malformed_required_state_follows_existing_cli_error_behavior,
    test_output_helper_is_deterministic,
    test_input_guided_mapping_is_not_mutated,
    test_existing_advanced_commands_remain_registered,
    test_no_model_patch_apply_git_verification_or_delivery_action_is_invoked,
    test_no_rich_panel_or_scan_progress_bar_dependency_is_introduced,
    test_no_workflow_decision_logic_is_duplicated,
    test_new_internal_imports_use_direct_fully_qualified_module_imports,
    test_no_from_strata_core_import_module_form_exists,
    test_package_layering_invariant_has_no_new_violation,
    test_cli_routes_start_to_guided_command,
    test_plain_text_fallback_is_readable_without_ansi_assumptions,
]
