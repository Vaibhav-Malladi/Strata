import contextlib
import inspect
import io
import json
import sys
import tempfile
from pathlib import Path

import strata.commands.cli as cli_module
import strata.commands.cli_help as cli_help
import strata.commands.start_command as start_command
from tests.helpers import change_directory
from workflow_config import default_config, save_config


def capture_output(function, *args, **kwargs):
    output = io.StringIO()

    with contextlib.redirect_stdout(output):
        result = function(*args, **kwargs)

    return result, output.getvalue()


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


def _action_result(**overrides) -> dict[str, object]:
    result = {
        "action": "review_changes",
        "status": "completed",
        "executed": True,
        "message": "Action completed.",
        "next_action": "view_results",
        "next_action_label": "Run `strata start` again to refresh the workflow.",
        "blocking": False,
        "recovery": None,
    }
    result.update(overrides)
    return result


@contextlib.contextmanager
def patched_guided_views(views: list[dict[str, object]]):
    original = start_command.build_start_guided_view
    calls = []
    remaining = list(views)

    def fake_build_start_guided_view(root):
        calls.append(root)
        if len(remaining) > 1:
            return remaining.pop(0)
        return remaining[0]

    start_command.build_start_guided_view = fake_build_start_guided_view
    try:
        yield calls
    finally:
        start_command.build_start_guided_view = original


def test_strata_start_remains_registered_once():
    source = inspect.getsource(cli_module)

    assert source.count('command == "start"') == 1


def test_start_is_described_as_recommended_normal_entry_point():
    lines = dict(cli_help._main_workflow_lines())

    assert lines["strata start [path]"] == (
        "Open the guided workflow. In an interactive terminal, Strata stays open and offers each next step."
    )
    assert lines["strata start --continue [path]"] == (
        "Attempt one recommended step and exit. Repository-changing actions still require confirmation."
    )


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


def test_normal_start_does_not_execute_actions():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_run_state(root, _run_state(patch_received=True))
        original = start_command.handle_recommended_action
        start_command.handle_recommended_action = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("action should not execute")
        )
        try:
            exit_code, output = capture_output(start_command.write_start_command, str(root))
        finally:
            start_command.handle_recommended_action = original

        assert exit_code == 0
        assert "Action result" not in output


def test_interactive_start_enters_guided_loop():
    calls = []
    with patched_guided_views([
        _guided_view(),
        _guided_view(stage="complete", next_action="none", next_action_label="No action needed"),
    ]):
        exit_code, output = capture_output(
            start_command.run_guided_start_session,
            ".",
            input_fn=lambda _prompt: "",
            interactive=True,
            action_handlers={"review_changes": lambda root: calls.append(root) or 0},
        )

    assert exit_code == 0
    assert calls == ["."]
    assert "Action result" in output
    assert "Complete" in output


def test_non_interactive_start_remains_status_only():
    calls = []
    with patched_guided_views([_guided_view()]):
        exit_code, output = capture_output(
            start_command.run_guided_start_session,
            ".",
            interactive=False,
            action_handlers={"review_changes": lambda root: calls.append(root) or 0},
        )

    assert exit_code == 0
    assert calls == []
    assert "Action result" not in output
    assert "The AI response is ready for review." in output


def test_interactive_terminal_detection_requires_stdin_and_stdout_tty():
    class FakeStream:
        def __init__(self, value: bool):
            self.value = value

        def isatty(self):
            return self.value

    assert start_command.is_interactive_terminal(stdin=FakeStream(True), stdout=FakeStream(True)) is True
    assert start_command.is_interactive_terminal(stdin=FakeStream(False), stdout=FakeStream(True)) is False
    assert start_command.is_interactive_terminal(stdin=FakeStream(True), stdout=FakeStream(False)) is False


def test_enter_continues_guided_session():
    calls = []
    with patched_guided_views([
        _guided_view(),
        _guided_view(stage="complete", next_action="none", next_action_label="No action needed"),
    ]):
        exit_code, _ = capture_output(
            start_command.run_guided_start_session,
            ".",
            input_fn=lambda _prompt: "",
            interactive=True,
            action_handlers={"review_changes": lambda root: calls.append(root) or 0},
        )

    assert exit_code == 0
    assert calls == ["."]


def test_y_continues_guided_session():
    calls = []
    with patched_guided_views([
        _guided_view(),
        _guided_view(stage="complete", next_action="none", next_action_label="No action needed"),
    ]):
        exit_code, _ = capture_output(
            start_command.run_guided_start_session,
            ".",
            input_fn=lambda _prompt: "y",
            interactive=True,
            action_handlers={"review_changes": lambda root: calls.append(root) or 0},
        )

    assert exit_code == 0
    assert calls == ["."]


def test_yes_continues_guided_session():
    calls = []
    with patched_guided_views([
        _guided_view(),
        _guided_view(stage="complete", next_action="none", next_action_label="No action needed"),
    ]):
        exit_code, _ = capture_output(
            start_command.run_guided_start_session,
            ".",
            input_fn=lambda _prompt: "yes",
            interactive=True,
            action_handlers={"review_changes": lambda root: calls.append(root) or 0},
        )

    assert exit_code == 0
    assert calls == ["."]


def test_stop_choices_exit_normally_without_action():
    for value in ("n", "no", "q", "quit", "exit"):
        calls = []
        with patched_guided_views([_guided_view()]):
            exit_code, output = capture_output(
                start_command.run_guided_start_session,
                ".",
                input_fn=lambda _prompt, value=value: value,
                interactive=True,
                action_handlers={"review_changes": lambda root: calls.append(root) or 0},
            )

        assert exit_code == 0
        assert calls == []
        assert "Guided session ended." in output


def test_invalid_input_does_not_execute_action_and_shows_guidance():
    responses = iter(["maybe", "n"])
    calls = []
    with patched_guided_views([_guided_view()]):
        exit_code, output = capture_output(
            start_command.run_guided_start_session,
            ".",
            input_fn=lambda _prompt: next(responses),
            interactive=True,
            action_handlers={"review_changes": lambda root: calls.append(root) or 0},
        )

    assert exit_code == 0
    assert calls == []
    assert "Enter y to continue, n to stop, or q to quit." in output


def test_one_action_runs_per_iteration_and_state_is_reloaded():
    calls = []
    first = _guided_view(headline="First view.")
    second = _guided_view(
        stage="awaiting_ai_response",
        headline="Second view.",
        summary="External work is needed.",
        next_action="deliver_prompt",
        next_action_label="Copy the prompt",
    )
    with patched_guided_views([first, second]):
        exit_code, output = capture_output(
            start_command.run_guided_start_session,
            ".",
            input_fn=lambda _prompt: "",
            interactive=True,
            action_handlers={"review_changes": lambda root: calls.append(root) or 0},
        )

    assert exit_code == 0
    assert calls == ["."]
    assert "First view." in output
    assert "Second view." in output
    assert "Copy the prepared request into your AI tool." in output


def test_complete_workflow_exits_without_prompting():
    prompts = []
    with patched_guided_views([
        _guided_view(stage="complete", next_action="none", next_action_label="No action needed")
    ]):
        exit_code, output = capture_output(
            start_command.run_guided_start_session,
            ".",
            input_fn=lambda prompt: prompts.append(prompt) or "",
            interactive=True,
        )

    assert exit_code == 0
    assert prompts == []
    assert "Action result" not in output


def test_next_action_none_exits_without_prompting():
    prompts = []
    with patched_guided_views([_guided_view(next_action="none", next_action_label="No action needed")]):
        exit_code, _ = capture_output(
            start_command.run_guided_start_session,
            ".",
            input_fn=lambda prompt: prompts.append(prompt) or "",
            interactive=True,
        )

    assert exit_code == 0
    assert prompts == []


def test_manual_ai_transfer_action_shows_guidance_and_exits():
    with patched_guided_views([
        _guided_view(next_action="deliver_prompt", next_action_label="Copy the prompt")
    ]):
        exit_code, output = capture_output(
            start_command.run_guided_start_session,
            ".",
            input_fn=lambda _prompt: "",
            interactive=True,
        )

    assert exit_code == 0
    assert "Copy the prepared request into your AI tool." in output
    assert output.count("Action result") == 1


def test_blocking_state_does_not_execute_destructive_action():
    calls = []
    with patched_guided_views([
        _guided_view(
            stage="review_blocked",
            next_action="apply_changes",
            next_action_label="Apply the reviewed changes",
            confirmation_required=True,
            blocking=True,
        )
    ]):
        exit_code, output = capture_output(
            start_command.run_guided_start_session,
            ".",
            input_fn=lambda _prompt: "",
            interactive=True,
            action_handlers={"apply_changes": lambda root: calls.append(root) or 0},
        )

    assert exit_code == 0
    assert calls == []
    assert "Blocked" in output


def test_failed_action_stops_loop_and_returns_nonzero():
    calls = []
    with patched_guided_views([_guided_view()]):
        exit_code, output = capture_output(
            start_command.run_guided_start_session,
            ".",
            input_fn=lambda _prompt: "",
            interactive=True,
            action_handlers={"review_changes": lambda root: calls.append(root) or 1},
        )

    assert exit_code == 1
    assert calls == ["."]
    assert "Action could not complete." in output


def test_cancelled_apply_stops_without_further_actions():
    prompts = iter(["", ""])
    calls = []
    with patched_guided_views([
        _guided_view(
            stage="ready_to_apply",
            next_action="apply_changes",
            next_action_label="Apply the reviewed changes",
            confirmation_required=True,
        )
    ]):
        exit_code, output = capture_output(
            start_command.run_guided_start_session,
            ".",
            input_fn=lambda _prompt: next(prompts),
            interactive=True,
            action_handlers={"apply_changes": lambda root: calls.append(root) or 0},
        )

    assert exit_code == 0
    assert calls == []
    assert "Cancelled. No files were changed." in output


def test_loop_prompt_does_not_replace_apply_confirmation():
    prompts = []
    with patched_guided_views([
        _guided_view(
            stage="ready_to_apply",
            next_action="apply_changes",
            next_action_label="Apply the reviewed changes",
            confirmation_required=True,
        ),
        _guided_view(stage="complete", next_action="none", next_action_label="No action needed"),
    ]):
        exit_code, _ = capture_output(
            start_command.run_guided_start_session,
            ".",
            input_fn=lambda prompt: prompts.append(prompt) or "y",
            interactive=True,
            action_handlers={"apply_changes": lambda _root: 0},
        )

    assert exit_code == 0
    assert prompts == ["Continue with this step? [Y/n/q] ", "Apply the reviewed changes? [y/N] "]


def test_unchanged_state_after_action_stops_loop():
    with patched_guided_views([_guided_view()]):
        exit_code, output = capture_output(
            start_command.run_guided_start_session,
            ".",
            input_fn=lambda _prompt: "",
            interactive=True,
            action_handlers={"review_changes": lambda _root: 0},
        )

    assert exit_code == 0
    assert "Strata is waiting for an external step before it can continue." in output


def test_iteration_limit_prevents_infinite_loop():
    views = [
        _guided_view(headline=f"View {index}.", summary=f"Summary {index}.")
        for index in range(start_command.MAX_GUIDED_ITERATIONS + 1)
    ]
    calls = []
    with patched_guided_views(views):
        exit_code, output = capture_output(
            start_command.run_guided_start_session,
            ".",
            input_fn=lambda _prompt: "",
            interactive=True,
            action_handlers={"review_changes": lambda root: calls.append(root) or 0},
        )

    assert exit_code == 0
    assert len(calls) == start_command.MAX_GUIDED_ITERATIONS
    assert "Guided session stopped after too many steps." in output


def test_one_continuation_mechanism_exists():
    source = inspect.getsource(cli_module)

    assert source.count("--continue") == 1


def test_continue_attempts_exactly_one_recommended_action():
    view = _guided_view()
    calls = []
    original_build = start_command.build_start_guided_view
    original_handle = start_command.handle_recommended_action
    start_command.build_start_guided_view = lambda _root: view
    start_command.handle_recommended_action = lambda guided_view, **kwargs: calls.append((guided_view, kwargs)) or _action_result()
    try:
        exit_code, output = capture_output(start_command.write_start_command, ".", continue_action=True)
    finally:
        start_command.build_start_guided_view = original_build
        start_command.handle_recommended_action = original_handle

    assert exit_code == 0
    assert len(calls) == 1
    assert calls[0][0] == view
    assert "Action result" in output
    assert _next_section_count(output) == 1


def test_apply_requires_confirmation_and_prompt_uses_y_no_default():
    prompts = []

    allowed = start_command.confirm_recommended_action(
        action="apply_changes",
        confirmation_required=True,
        input_fn=lambda prompt: prompts.append(prompt) or "y",
    )

    assert allowed is True
    assert prompts == ["Apply the reviewed changes? [y/N] "]


def test_explicit_y_and_yes_proceed():
    for value in ("y", "yes"):
        assert start_command.confirm_recommended_action(
            action="apply_changes",
            confirmation_required=True,
            input_fn=lambda _prompt, value=value: value,
        ) is True


def test_empty_no_and_invalid_input_cancel_conservatively():
    for value in ("", "n", "no", "maybe"):
        assert start_command.confirm_recommended_action(
            action="apply_changes",
            confirmation_required=True,
            input_fn=lambda _prompt, value=value: value,
        ) is False


def test_cancellation_does_not_execute_apply_and_returns_normal_result():
    calls = []
    result = start_command.handle_recommended_action(
        _guided_view(
            stage="ready_to_apply",
            next_action="apply_changes",
            next_action_label="Apply the reviewed changes",
            confirmation_required=True,
        ),
        confirm_fn=lambda **_kwargs: False,
        action_handlers={"apply_changes": lambda _root: calls.append("apply") or 0},
    )

    assert result["status"] == "cancelled"
    assert result["executed"] is False
    assert calls == []
    assert result["message"] == "Cancelled. No files were changed."


def test_start_continue_cancellation_returns_normal_completion():
    view = _guided_view(
        stage="ready_to_apply",
        next_action="apply_changes",
        next_action_label="Apply the reviewed changes",
        confirmation_required=True,
    )
    original_build = start_command.build_start_guided_view
    start_command.build_start_guided_view = lambda _root: view
    try:
        exit_code, output = capture_output(start_command.write_start_command, ".", continue_action=True, input_fn=lambda _prompt: "")
    finally:
        start_command.build_start_guided_view = original_build

    assert exit_code == 0
    assert "Cancelled. No files were changed." in output
    assert _next_section_count(output) == 1


def test_non_confirmation_actions_do_not_prompt():
    prompts = []

    assert start_command.confirm_recommended_action(
        action="review_changes",
        confirmation_required=False,
        input_fn=lambda prompt: prompts.append(prompt) or "",
    ) is True
    assert prompts == []


def test_blocking_state_prevents_destructive_execution():
    calls = []
    result = start_command.handle_recommended_action(
        _guided_view(
            stage="review_blocked",
            next_action="apply_changes",
            next_action_label="Apply the reviewed changes",
            confirmation_required=True,
            blocking=True,
        ),
        confirm_fn=lambda **_kwargs: True,
        action_handlers={"apply_changes": lambda _root: calls.append("apply") or 0},
    )

    assert result["status"] == "blocked"
    assert result["executed"] is False
    assert calls == []


def test_manual_ai_actions_are_not_executed():
    for action in ("deliver_prompt", "provide_ai_response", "retry_ai_request"):
        result = start_command.handle_recommended_action(
            _guided_view(next_action=action, next_action_label="Manual action"),
            action_handlers={action: lambda _root: (_ for _ in ()).throw(AssertionError("should not run"))},
        )
        assert result["status"] == "not_executed"
        assert result["executed"] is False


def test_existing_handler_is_called_at_most_once_and_success_completes():
    calls = []
    result = start_command.handle_recommended_action(
        _guided_view(next_action="review_changes", next_action_label="Review the proposed changes"),
        action_handlers={"review_changes": lambda root: calls.append(root) or 0},
    )

    assert calls == ["."]
    assert result["status"] == "completed"
    assert result["executed"] is True
    assert result["next_action"] == "view_results"


def test_handler_failure_returns_failed_status():
    result = start_command.handle_recommended_action(
        _guided_view(next_action="run_verification", next_action_label="Run verification"),
        action_handlers={"run_verification": lambda _root: 1},
    )

    assert result["status"] == "failed"
    assert result["executed"] is True
    assert result["blocking"] is True


def test_handler_exception_returns_failed_status_without_traceback():
    result = start_command.handle_recommended_action(
        _guided_view(next_action="review_changes", next_action_label="Review the proposed changes"),
        action_handlers={"review_changes": lambda _root: (_ for _ in ()).throw(RuntimeError("boom"))},
    )

    assert result["status"] == "failed"
    assert result["executed"] is False
    assert "boom" in result["message"]


def test_action_result_is_json_ready():
    result = start_command.handle_recommended_action(
        _guided_view(next_action="review_changes", next_action_label="Review the proposed changes"),
        action_handlers={"review_changes": lambda _root: 0},
    )

    assert json.loads(json.dumps(result, allow_nan=False, sort_keys=True)) == result


def test_guided_view_and_handler_mapping_are_not_mutated():
    view = _guided_view(next_action="review_changes", next_action_label="Review the proposed changes")
    handlers = {"review_changes": lambda _root: 0}
    before = (json.loads(json.dumps(view)), dict(handlers))

    start_command.handle_recommended_action(view, action_handlers=handlers)

    assert view == before[0]
    assert handlers == before[1]


def test_recovery_guidance_is_deterministic():
    first = start_command.handle_recommended_action(
        _guided_view(
            stage="review_blocked",
            next_action="resolve_review_issues",
            next_action_label="Fix the review issues",
            blocking=True,
        )
    )
    second = start_command.handle_recommended_action(
        _guided_view(
            stage="review_blocked",
            next_action="resolve_review_issues",
            next_action_label="Fix the review issues",
            blocking=True,
        )
    )

    assert first["recovery"] == second["recovery"] == "Resolve the review issues before applying."


def test_render_action_result_keeps_exactly_one_next_action_visible():
    output = start_command.render_action_result(
        {
            "action": "apply_changes",
            "status": "cancelled",
            "executed": False,
            "message": "Cancelled. No files were changed.",
            "next_action": "apply_changes",
            "next_action_label": "Apply the reviewed changes",
            "blocking": False,
            "recovery": None,
        }
    )

    assert _next_section_count(output) == 1
    assert "Options" not in output
    assert "Possible actions" not in output


def test_apply_is_not_executed():
    calls = []
    start_command.handle_recommended_action(
        _guided_view(
            stage="ready_to_apply",
            next_action="apply_changes",
            next_action_label="Apply the reviewed changes",
            confirmation_required=True,
        ),
        confirm_fn=lambda **_kwargs: False,
        action_handlers={"apply_changes": lambda _root: calls.append("apply") or 0},
    )

    assert calls == []


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

    for forbidden in ("check_adapter", "execute_command", "run_argv", "subprocess", "clipboard", "browser", "model"):
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
    assert "import strata.commands.apply_command as apply_command" in source


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


def test_cli_routes_start_continue_to_guided_command():
    calls = []
    original = cli_module.write_start_command
    cli_module.write_start_command = lambda root, **kwargs: calls.append((root, kwargs)) or 0
    try:
        with change_argv(["cli.py", "start", "--continue", "repo"]):
            exit_code, _output = capture_output(cli_module.main)
    finally:
        cli_module.write_start_command = original

    assert exit_code == 0
    assert calls == [("repo", {"continue_action": True})]


def test_existing_apply_safety_behavior_remains_unchanged():
    source = inspect.getsource(start_command)

    assert "apply_command.write_apply_command(root_path, yes=True)" in source
    assert "force" not in source.lower()


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
    test_normal_start_does_not_execute_actions,
    test_interactive_start_enters_guided_loop,
    test_non_interactive_start_remains_status_only,
    test_interactive_terminal_detection_requires_stdin_and_stdout_tty,
    test_enter_continues_guided_session,
    test_y_continues_guided_session,
    test_yes_continues_guided_session,
    test_stop_choices_exit_normally_without_action,
    test_invalid_input_does_not_execute_action_and_shows_guidance,
    test_one_action_runs_per_iteration_and_state_is_reloaded,
    test_complete_workflow_exits_without_prompting,
    test_next_action_none_exits_without_prompting,
    test_manual_ai_transfer_action_shows_guidance_and_exits,
    test_blocking_state_does_not_execute_destructive_action,
    test_failed_action_stops_loop_and_returns_nonzero,
    test_cancelled_apply_stops_without_further_actions,
    test_loop_prompt_does_not_replace_apply_confirmation,
    test_unchanged_state_after_action_stops_loop,
    test_iteration_limit_prevents_infinite_loop,
    test_one_continuation_mechanism_exists,
    test_continue_attempts_exactly_one_recommended_action,
    test_apply_requires_confirmation_and_prompt_uses_y_no_default,
    test_explicit_y_and_yes_proceed,
    test_empty_no_and_invalid_input_cancel_conservatively,
    test_cancellation_does_not_execute_apply_and_returns_normal_result,
    test_start_continue_cancellation_returns_normal_completion,
    test_non_confirmation_actions_do_not_prompt,
    test_blocking_state_prevents_destructive_execution,
    test_manual_ai_actions_are_not_executed,
    test_existing_handler_is_called_at_most_once_and_success_completes,
    test_handler_failure_returns_failed_status,
    test_handler_exception_returns_failed_status_without_traceback,
    test_action_result_is_json_ready,
    test_guided_view_and_handler_mapping_are_not_mutated,
    test_recovery_guidance_is_deterministic,
    test_render_action_result_keeps_exactly_one_next_action_visible,
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
    test_cli_routes_start_continue_to_guided_command,
    test_existing_apply_safety_behavior_remains_unchanged,
    test_plain_text_fallback_is_readable_without_ansi_assumptions,
]
