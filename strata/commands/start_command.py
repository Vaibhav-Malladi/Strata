from __future__ import annotations

import json
from pathlib import Path
import sys

import strata.commands.apply_command as apply_command
import strata.commands.review_command as review_command
import strata.commands.verify_command as verify_command
import strata.core.context_artifacts as context_artifacts
import strata.core.guided_workflow as guided_workflow
from strata.utils.config import config_path, load_config


_CONFIRMATION_NOTE = "Confirmation will be required before repository files are changed."
_GUIDED_SESSION_PROMPT = "Continue with this step? [Y/n/q] "
_GUIDED_SESSION_INVALID_CHOICE = "Enter y to continue, n to stop, or q to quit."
_GUIDED_SESSION_ENDED = "Guided session ended.\nRun `strata start` whenever you are ready to continue."
_GUIDED_SESSION_WAITING = (
    "Strata is waiting for an external step before it can continue.\n"
    "Run `strata start` again after completing that step."
)
_GUIDED_SESSION_LIMIT_REACHED = "Guided session stopped after too many steps. Run `strata start` again to continue."
MAX_GUIDED_ITERATIONS = 20
ACTION_STATUS_NOT_EXECUTED = "not_executed"
ACTION_STATUS_CANCELLED = "cancelled"
ACTION_STATUS_COMPLETED = "completed"
ACTION_STATUS_BLOCKED = "blocked"
ACTION_STATUS_FAILED = "failed"
ACTION_STATUSES = (
    ACTION_STATUS_NOT_EXECUTED,
    ACTION_STATUS_CANCELLED,
    ACTION_STATUS_COMPLETED,
    ACTION_STATUS_BLOCKED,
    ACTION_STATUS_FAILED,
)
_ACTION_CATEGORIES = {
    guided_workflow.NEXT_ACTION_RUN_SETUP: "informational",
    guided_workflow.NEXT_ACTION_PREPARE_CONTEXT: "informational",
    guided_workflow.NEXT_ACTION_DELIVER_PROMPT: "unsupported_for_now",
    guided_workflow.NEXT_ACTION_PROVIDE_AI_RESPONSE: "unsupported_for_now",
    guided_workflow.NEXT_ACTION_RETRY_AI_REQUEST: "unsupported_for_now",
    guided_workflow.NEXT_ACTION_REVIEW_CHANGES: "delegatable",
    guided_workflow.NEXT_ACTION_RESOLVE_REVIEW_ISSUES: "informational",
    guided_workflow.NEXT_ACTION_APPLY_CHANGES: "destructive",
    guided_workflow.NEXT_ACTION_RUN_VERIFICATION: "delegatable",
    guided_workflow.NEXT_ACTION_VIEW_RESULTS: "informational",
    guided_workflow.NEXT_ACTION_NONE: "informational",
}
_MANUAL_ACTION_MESSAGES = {
    guided_workflow.NEXT_ACTION_RUN_SETUP: "Run `strata setup` to configure how Strata works with your AI tool.",
    guided_workflow.NEXT_ACTION_PREPARE_CONTEXT: "Prepare the project context before continuing.",
    guided_workflow.NEXT_ACTION_DELIVER_PROMPT: "Copy the prepared request into your AI tool.",
    guided_workflow.NEXT_ACTION_PROVIDE_AI_RESPONSE: "Paste the AI response back into Strata.",
    guided_workflow.NEXT_ACTION_RETRY_AI_REQUEST: "Send the corrected request to your AI tool.",
    guided_workflow.NEXT_ACTION_RESOLVE_REVIEW_ISSUES: "Resolve the review issues before applying.",
    guided_workflow.NEXT_ACTION_VIEW_RESULTS: "Review the current Strata output, then run `strata start` again.",
    guided_workflow.NEXT_ACTION_NONE: "This workflow is complete.",
}
_RECOVERY_GUIDANCE = {
    "dirty_worktree": "Commit or stash your current changes, then run `strata start` again.",
    "missing_context": "Prepare the project context before continuing.",
    "malformed_state": "Recreate the current Strata workflow state.",
    "review_blocked": "Resolve the review issues before applying.",
    "verification_failed": "Review the verification report before continuing.",
    "action_failed": "Review the command output, then run `strata start` again.",
}
_PROGRESS_STEPS = (
    ("setup", "Setup"),
    ("prepare_context", "Prepare context"),
    ("send_to_ai", "Send to AI"),
    ("receive_response", "Receive response"),
    ("review", "Review"),
    ("apply", "Apply"),
    ("verify", "Verify"),
    ("complete", "Complete"),
)
_STAGE_PROGRESS_STEP = {
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
_STAGE_LABELS = {
    "setup_required": "Setup required",
    "ready": "Ready",
    "context_prepared": "Context prepared",
    "prompt_ready": "Request ready",
    "awaiting_ai_response": "Waiting for AI response",
    "response_received": "Response received",
    "retry_available": "Retry available",
    "ready_for_review": "Ready for review",
    "review_blocked": "Review blocked",
    "ready_to_apply": "Ready to apply",
    "verification_required": "Verification required",
    "complete": "Complete",
}
_PROGRESS_PREFIXES = {
    "complete": "[done]",
    "current": "[now]",
    "upcoming": "[next]",
    "blocked": "[blocked]",
}


def _load_json_mapping(path: Path, *, required: bool) -> dict[str, object] | None:
    if not path.exists():
        if required:
            raise ValueError(f"Required state file is missing: {_display_path(path)}")
        return None

    try:
        with path.open("r", encoding="utf-8") as file:
            value = json.load(file)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Could not read state file: {_display_path(path)}") from error

    if not isinstance(value, dict):
        raise ValueError(f"State file must contain a JSON object: {_display_path(path)}")
    return value


def _load_workflow_state(root: Path) -> dict[str, object]:
    run_state_path = root / context_artifacts.RUN_STATE_ARTIFACT_PATH
    run_state = _load_json_mapping(run_state_path, required=False)
    if run_state is not None:
        return run_state

    try:
        config_exists = config_path(root).exists()
        if config_exists:
            load_config(root)
    except ValueError as error:
        raise ValueError(f"Workflow config error: {error}") from error

    if not config_exists:
        return {"setup_required": True}

    return {"setup_complete": True}


def _load_session_state(root: Path) -> dict[str, object] | None:
    return None


def _display_path(path: Path) -> str:
    return str(path).replace("\\", "/")


def _require_guided_view(value) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("guided view must be a mapping.")
    required = (
        "headline",
        "summary",
        "next_action",
        "next_action_label",
        "confirmation_required",
        "warnings",
    )
    for field in required:
        if field not in value:
            raise ValueError(f"guided view is missing required field: {field}")
    return dict(value)


def _action_result(
    *,
    action: str,
    status: str,
    executed: bool,
    message: str,
    next_action: str,
    next_action_label: str,
    blocking: bool = False,
    recovery: str | None = None,
) -> dict[str, object]:
    if status not in ACTION_STATUSES:
        raise ValueError(f"unsupported action status: {status}")
    result = {
        "action": action,
        "status": status,
        "executed": bool(executed),
        "message": message,
        "next_action": next_action,
        "next_action_label": next_action_label,
        "blocking": bool(blocking),
        "recovery": recovery,
    }
    json.dumps(result, allow_nan=False)
    return result


def is_interactive_terminal(
    *,
    stdin=None,
    stdout=None,
) -> bool:
    input_stream = sys.stdin if stdin is None else stdin
    output_stream = sys.stdout if stdout is None else stdout
    return _stream_is_tty(input_stream) and _stream_is_tty(output_stream)


def _stream_is_tty(stream) -> bool:
    isatty = getattr(stream, "isatty", None)
    if not callable(isatty):
        return False
    try:
        return bool(isatty())
    except OSError:
        return False


def _recovery_for(action: str, status: str, guided_view: dict[str, object]) -> str | None:
    if status == ACTION_STATUS_COMPLETED:
        return None
    if guided_view.get("blocking") is True:
        return _RECOVERY_GUIDANCE["review_blocked"]
    if action == guided_workflow.NEXT_ACTION_PREPARE_CONTEXT:
        return _RECOVERY_GUIDANCE["missing_context"]
    if action == guided_workflow.NEXT_ACTION_RUN_VERIFICATION:
        return _RECOVERY_GUIDANCE["verification_failed"]
    if action == guided_workflow.NEXT_ACTION_APPLY_CHANGES:
        return _RECOVERY_GUIDANCE["dirty_worktree"] if status == ACTION_STATUS_FAILED else None
    if status == ACTION_STATUS_FAILED:
        return _RECOVERY_GUIDANCE["action_failed"]
    return None


def confirm_recommended_action(
    *,
    action: str,
    confirmation_required: bool,
    input_fn=input,
) -> bool:
    if not confirmation_required:
        return True
    prompt = "Apply the reviewed changes? [y/N] " if action == guided_workflow.NEXT_ACTION_APPLY_CHANGES else "Continue? [y/N] "
    response = input_fn(prompt)
    return str(response or "").strip().lower() in {"y", "yes"}


def _default_action_handlers() -> dict[str, object]:
    return {
        guided_workflow.NEXT_ACTION_REVIEW_CHANGES: review_command.write_review_command,
        guided_workflow.NEXT_ACTION_APPLY_CHANGES: lambda root_path: apply_command.write_apply_command(root_path, yes=True),
        guided_workflow.NEXT_ACTION_RUN_VERIFICATION: verify_command.write_verify_command,
    }


def _manual_action_result(action: str, view: dict[str, object]) -> dict[str, object]:
    message = _MANUAL_ACTION_MESSAGES.get(action, "Run `strata start` again to refresh the workflow.")
    return _action_result(
        action=action,
        status=ACTION_STATUS_NOT_EXECUTED,
        executed=False,
        message=message,
        next_action=action,
        next_action_label=str(view["next_action_label"]),
        blocking=bool(view.get("blocking")),
        recovery=_recovery_for(action, ACTION_STATUS_NOT_EXECUTED, view),
    )


def handle_recommended_action(
    guided_view,
    *,
    root_path: str = ".",
    confirm_fn=None,
    action_handlers=None,
) -> dict[str, object]:
    view = _require_guided_view(guided_view)
    action = str(view["next_action"])
    category = _ACTION_CATEGORIES.get(action)
    handlers = dict(_default_action_handlers() if action_handlers is None else action_handlers)
    confirm = confirm_fn or confirm_recommended_action

    if action not in _ACTION_CATEGORIES:
        raise ValueError(f"unsupported guided action: {action}")
    if action == guided_workflow.NEXT_ACTION_NONE:
        return _manual_action_result(action, view)
    if view.get("blocking") is True and action not in {
        guided_workflow.NEXT_ACTION_RESOLVE_REVIEW_ISSUES,
        guided_workflow.NEXT_ACTION_VIEW_RESULTS,
    }:
        return _action_result(
            action=action,
            status=ACTION_STATUS_BLOCKED,
            executed=False,
            message="Resolve the current issues before continuing.",
            next_action=action,
            next_action_label=str(view["next_action_label"]),
            blocking=True,
            recovery=_recovery_for(action, ACTION_STATUS_BLOCKED, view),
        )
    if category in {"informational", "unsupported_for_now"}:
        return _manual_action_result(action, view)
    confirmation_required = view.get("confirmation_required") is True or action == guided_workflow.NEXT_ACTION_APPLY_CHANGES
    if confirmation_required and not confirm(
        action=action,
        confirmation_required=True,
    ):
        return _action_result(
            action=action,
            status=ACTION_STATUS_CANCELLED,
            executed=False,
            message="Cancelled. No files were changed.",
            next_action=action,
            next_action_label=str(view["next_action_label"]),
            recovery=_recovery_for(action, ACTION_STATUS_CANCELLED, view),
        )

    handler = handlers.get(action)
    if handler is None:
        return _manual_action_result(action, view)
    try:
        exit_code = handler(root_path)
    except Exception as error:
        return _action_result(
            action=action,
            status=ACTION_STATUS_FAILED,
            executed=False,
            message=f"Action failed: {error}",
            next_action=action,
            next_action_label=str(view["next_action_label"]),
            blocking=True,
            recovery=_recovery_for(action, ACTION_STATUS_FAILED, view),
        )

    completed = exit_code == 0
    return _action_result(
        action=action,
        status=ACTION_STATUS_COMPLETED if completed else ACTION_STATUS_FAILED,
        executed=True,
        message="Action completed." if completed else "Action could not complete.",
        next_action=guided_workflow.NEXT_ACTION_VIEW_RESULTS if completed else action,
        next_action_label="Run `strata start` again to refresh the workflow." if completed else str(view["next_action_label"]),
        blocking=not completed,
        recovery=_recovery_for(action, ACTION_STATUS_COMPLETED if completed else ACTION_STATUS_FAILED, view),
    )


def _stage_label(stage: object) -> str:
    return _STAGE_LABELS.get(str(stage or ""), "Current status")


def _progress_prefix(state: object) -> str:
    return _PROGRESS_PREFIXES.get(str(state or ""), "[next]")


def build_start_command_output(guided_view) -> str:
    return render_guided_workflow_view(guided_view)


def build_guided_progress(stage, *, blocking: bool = False) -> list[dict[str, object]]:
    step_keys = [key for key, _label in _PROGRESS_STEPS]
    step_key = _STAGE_PROGRESS_STEP.get(str(stage or ""), "prepare_context")
    current_index = step_keys.index(step_key)
    progress = []
    for index, (key, label) in enumerate(_PROGRESS_STEPS):
        state = "upcoming"
        if index < current_index or step_key == "complete":
            state = "complete"
        if index == current_index and step_key != "complete":
            state = "blocked" if blocking else "current"
        progress.append({"key": key, "label": label, "state": state})
    return progress


def render_guided_workflow_view(guided_view, *, include_next_action: bool = True) -> str:
    view = _require_guided_view(guided_view)
    stage = str(view.get("stage") or "")
    lines = [
        "Strata",
        "",
        "Current status",
        _stage_label(stage),
    ]
    if view.get("blocking") is True:
        lines.extend(["", "Blocked", "Resolve the current issues before continuing."])

    lines.extend(["", str(view["headline"]), str(view["summary"]), "", "Progress"])
    for item in build_guided_progress(stage, blocking=view.get("blocking") is True):
        lines.append(f"{_progress_prefix(item['state'])} {item['label']}")

    warnings = view.get("warnings")
    if isinstance(warnings, list) and warnings:
        lines.extend(["", "Warnings"])
        for warning in warnings:
            if isinstance(warning, dict):
                lines.append(f"- {warning.get('message', '')}")

    if include_next_action and view["next_action"] != guided_workflow.NEXT_ACTION_NONE:
        lines.extend(["", "Next step", str(view["next_action_label"])])
        if view.get("confirmation_required") is True:
            lines.append(_CONFIRMATION_NOTE)

    return "\n".join(lines).rstrip() + "\n"


def render_action_result(action_result) -> str:
    if not isinstance(action_result, dict):
        raise ValueError("action result must be a mapping.")
    lines = ["Action result", str(action_result.get("message") or "No action was executed.")]
    recovery = action_result.get("recovery")
    if isinstance(recovery, str) and recovery.strip():
        lines.extend(["", "Recovery", recovery])
    next_action = action_result.get("next_action")
    if next_action != guided_workflow.NEXT_ACTION_NONE:
        lines.extend(["", "Next step", str(action_result.get("next_action_label") or "")])
    return "\n".join(lines).rstrip() + "\n"


def _emit(output_fn, text: str = "", *, end: str = "\n") -> None:
    try:
        output_fn(text, end=end)
    except TypeError:
        output_fn(text if end == "\n" else text + end)


def _guided_view_signature(guided_view) -> tuple[object, ...]:
    view = _require_guided_view(guided_view)
    return (
        view.get("stage"),
        view.get("headline"),
        view.get("summary"),
        view.get("next_action"),
        view.get("next_action_label"),
        view.get("blocking") is True,
    )


def _read_guided_session_choice(input_fn=input, output_fn=print) -> str:
    while True:
        try:
            response = input_fn(_GUIDED_SESSION_PROMPT)
        except (EOFError, KeyboardInterrupt):
            return "exit"

        normalized = str(response or "").strip().lower()
        if normalized in {"", "y", "yes"}:
            return "continue"
        if normalized in {"n", "no", "q", "quit", "exit"}:
            return "exit"

        _emit(output_fn, _GUIDED_SESSION_INVALID_CHOICE)


def _should_stop_without_prompt(guided_view: dict[str, object]) -> bool:
    view = _require_guided_view(guided_view)
    if view.get("next_action") == guided_workflow.NEXT_ACTION_NONE:
        return True
    if view.get("blocking") is True:
        return True
    return False


def run_guided_start_session(
    root_path: str = ".",
    *,
    input_fn=input,
    output_fn=print,
    interactive=None,
    action_handlers=None,
) -> int:
    if interactive is None:
        interactive = is_interactive_terminal()

    try:
        if not interactive:
            view = build_start_guided_view(root_path)
            _emit(output_fn, render_guided_workflow_view(view), end="")
            return 0

        previous_attempt_signature = None
        for _iteration in range(MAX_GUIDED_ITERATIONS):
            view = build_start_guided_view(root_path)
            signature = _guided_view_signature(view)
            _emit(output_fn, render_guided_workflow_view(view), end="")

            if previous_attempt_signature == signature:
                _emit(output_fn)
                _emit(output_fn, _GUIDED_SESSION_WAITING)
                return 0

            if _should_stop_without_prompt(view):
                return 0

            choice = _read_guided_session_choice(input_fn=input_fn, output_fn=output_fn)
            if choice == "exit":
                _emit(output_fn, _GUIDED_SESSION_ENDED)
                return 0

            result = handle_recommended_action(
                view,
                root_path=root_path,
                confirm_fn=lambda **kwargs: confirm_recommended_action(**kwargs, input_fn=input_fn),
                action_handlers=action_handlers,
            )
            _emit(output_fn)
            _emit(output_fn, render_action_result(result), end="")

            status = result.get("status")
            if status == ACTION_STATUS_FAILED:
                return 1
            if status != ACTION_STATUS_COMPLETED:
                return 0

            previous_attempt_signature = signature
            _emit(output_fn)

        _emit(output_fn, _GUIDED_SESSION_LIMIT_REACHED)
        return 0
    except ValueError as error:
        _emit(output_fn, "Strata")
        _emit(output_fn)
        _emit(output_fn, "Start could not continue.")
        _emit(output_fn, str(error))
        _emit(output_fn)
        _emit(output_fn, "Next step")
        _emit(output_fn, "Resolve the state issue")
        return 1


def build_start_guided_view(root_path: str = ".") -> dict[str, object]:
    root = Path(root_path)
    if not root.exists():
        raise ValueError(f"path does not exist: {root_path}")
    if not root.is_dir():
        raise ValueError(f"path is not a directory: {root_path}")

    workflow_state = _load_workflow_state(root)
    return guided_workflow.build_guided_workflow_view(
        workflow_state=workflow_state,
        session_state=_load_session_state(root),
        diagnostics=None,
    )


def write_start_command(root_path: str = ".", *, continue_action: bool = False, input_fn=input, interactive=None) -> int:
    try:
        if not continue_action:
            return run_guided_start_session(
                root_path,
                input_fn=input_fn,
                interactive=interactive,
            )

        view = build_start_guided_view(root_path)
        print(render_guided_workflow_view(view, include_next_action=not continue_action), end="")
        if continue_action:
            result = handle_recommended_action(
                view,
                root_path=root_path,
                confirm_fn=lambda **kwargs: confirm_recommended_action(**kwargs, input_fn=input_fn),
            )
            print()
            print(render_action_result(result), end="")
            if result.get("status") == ACTION_STATUS_FAILED:
                return 1
    except ValueError as error:
        print("Strata")
        print()
        print("Start could not continue.")
        print(str(error))
        print()
        print("Next step")
        print("Resolve the state issue")
        return 1

    return 0
