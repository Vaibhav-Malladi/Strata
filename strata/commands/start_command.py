from __future__ import annotations

import json
from pathlib import Path

import strata.core.context_artifacts as context_artifacts
import strata.core.guided_workflow as guided_workflow
from strata.utils.config import config_path, load_config


_CONFIRMATION_NOTE = "Confirmation will be required before repository files are changed."


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


def build_start_command_output(guided_view) -> str:
    view = _require_guided_view(guided_view)
    lines = ["Strata", "", str(view["headline"]), str(view["summary"])]
    warnings = view.get("warnings")
    if isinstance(warnings, list) and warnings:
        lines.extend(["", "Warnings:"])
        for warning in warnings:
            if isinstance(warning, dict):
                lines.append(f"- {warning.get('message', '')}")

    if view["next_action"] != guided_workflow.NEXT_ACTION_NONE:
        lines.extend(["", f"Next: {view['next_action_label']}"])
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
        print("Next: Resolve the state issue")
        return 1

    return 0
