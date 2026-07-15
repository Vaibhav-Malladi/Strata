from __future__ import annotations

import json
from pathlib import Path

import strata.core.context_artifacts as context_artifacts
import strata.core.guided_workflow as guided_workflow
from strata.utils.config import config_path, load_config


_CONFIRMATION_NOTE = "Confirmation will be required before repository files are changed."
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


def render_guided_workflow_view(guided_view) -> str:
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

    if view["next_action"] != guided_workflow.NEXT_ACTION_NONE:
        lines.extend(["", "Next step", str(view["next_action_label"])])
        if view.get("confirmation_required") is True:
            lines.append(_CONFIRMATION_NOTE)

    return "\n".join(lines).rstrip() + "\n"


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


def write_start_command(root_path: str = ".") -> int:
    try:
        view = build_start_guided_view(root_path)
        print(build_start_command_output(view), end="")
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
