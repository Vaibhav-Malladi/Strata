from __future__ import annotations

from pathlib import Path
from typing import Sequence

from adapter_doctor import check_adapter
from command_executor import DEFAULT_TIMEOUT_SECONDS, execute_command_adapter
from commands.prepare_command import prepare_workflow
from http_executor import execute_openai_compatible_http_adapter
from ollama_adapter import execute_ollama_adapter
from ui import (
    format_error,
    format_path,
    format_success,
    format_warning,
    print_banner,
    print_command_header,
    print_success,
    print_status_card,
    print_warning,
    render_step,
    status_spinner,
)
from workflow_config import load_config

_DIRECT_EDIT_WARNING_LINES = [
    "Warning:",
    "  This adapter may edit files directly.",
    "  Strata V6 direct-edit safety is not enabled yet.",
    "  If this command changes files without creating `.aidc/agent_patch.diff`,",
    "  run `strata review` and inspect `git diff` carefully.",
]


def write_ask_command(root_path: str = ".", *args: str) -> int:
    try:
        parsed = _parse_ask_args(args)
    except ValueError:
        _print_usage()
        return 1

    root = parsed["root"] or root_path
    task = parsed["task"]

    if not _validate_root(root):
        return 1

    try:
        config = load_config(root)
    except ValueError as error:
        _print_error("Workflow config error", str(error))
        return 1

    try:
        with status_spinner(render_step("Preparing prompt", "running")) as spinner:
            prepare_result = prepare_workflow(root, task, config)
            spinner.update(render_step("Checking adapter", "running"))
    except ValueError as error:
        _print_error("Ask failed", str(error))
        return 1

    if prepare_result is None:
        return 1

    adapter_result = check_adapter(root)
    adapter = str(adapter_result.get("adapter") or config.get("adapter") or "prompt_file")
    adapter_family = str(adapter_result.get("adapter_family") or "")
    ready = bool(adapter_result.get("ready"))
    prompt_path = str(prepare_result["config"].get("prompt_path") or ".aidc/agent_prompt.md")
    snapshot_result = prepare_result.get("snapshot_result")
    snapshot_display = (
        format_path(Path(snapshot_result["latest_path"]))
        if snapshot_result is not None
        else "skipped"
    )
    warnings = list(adapter_result.get("warnings", []) or [])

    if adapter == "prompt_file" or not ready:
        _print_prepared_summary(
            task=task,
            config=prepare_result["config"],
            adapter=adapter,
            adapter_result=adapter_result,
            prompt_path=prompt_path,
            snapshot_display=snapshot_display,
            warnings=warnings,
            ready=ready,
        )

        if adapter == "prompt_file":
            for line in _manual_next_steps():
                print(line)
            print_success('Next: Save the AI patch to `.aidc/agent_patch.diff`, then run `strata review`.')
            return 0

        for line in _not_ready_next_steps():
            print(line)
        print_error('Fix: Fix the adapter setup and run `strata ask` again.')
        return 1

    if adapter_family == "command":
        _print_direct_edit_warning()
        warnings = _merge_unique(warnings, [" ".join(line.strip() for line in _DIRECT_EDIT_WARNING_LINES[1:])])

    execution_result = _execute_adapter(root, adapter, prepare_result["config"])
    execution_status = str(execution_result.get("status", "failed")).lower()
    patch_status = execution_result.get("patch_status")
    patch_valid = bool(execution_result.get("patch_valid"))
    targets = execution_result.get("targets", [])
    execution_warnings = _merge_unique(
        warnings,
        list(execution_result.get("warnings", []) or []),
    )

    status = _format_execution_status(execution_status)
    next_step = "Run `strata review`." if execution_status == "patch_ready" else "Fix the adapter setup and run `strata ask` again."

    print_banner()
    print_command_header("Ask", "Prepare context and request a patch", mode="compact")
    print_status_card(
        "Ask patch",
        _build_execution_rows(
            task=task,
            config=prepare_result["config"],
            adapter=adapter,
            prompt_path=prompt_path,
            execution_result=execution_result,
            patch_status=patch_status,
            patch_valid=patch_valid,
            targets=targets,
            warnings=execution_warnings,
            next_step=next_step,
        ),
        status=status,
    )

    if execution_status == "patch_ready":
        print_success("Next: Run `strata review`.")
        return 0

    print_error("Fix: Fix the adapter setup and run `strata ask` again.")
    return 1


def _execute_adapter(root: str, adapter: str, config: dict) -> dict:
    if adapter == "ollama":
        with status_spinner(render_step("Executing adapter", "running")) as spinner:
            execution_result = execute_ollama_adapter(root, config=config)
            spinner.update(render_step("Inspecting patch", "running"))
        return execution_result

    if adapter == "openai_compatible_http":
        with status_spinner(render_step("Executing adapter", "running")) as spinner:
            execution_result = execute_openai_compatible_http_adapter(root, config=config)
            spinner.update(render_step("Inspecting patch", "running"))
        return execution_result

    timeout_seconds = config.get("command_timeout_seconds") if isinstance(config.get("command_timeout_seconds"), int) else None
    if type(timeout_seconds) is not int or timeout_seconds <= 0:
        timeout_seconds = DEFAULT_TIMEOUT_SECONDS

    with status_spinner(render_step("Executing adapter", "running")) as spinner:
        execution_result = execute_command_adapter(
            root,
            command=config.get("command"),
            timeout_seconds=timeout_seconds,
        )
        spinner.update(render_step("Inspecting patch", "running"))

    return execution_result


def _build_execution_rows(
    *,
    task: str,
    config: dict,
    adapter: str,
    prompt_path: str,
    execution_result: dict,
    patch_status: object,
    patch_valid: bool,
    targets: object,
    warnings: list[str],
    next_step: str,
) -> list[tuple[str, object]]:
    rows: list[tuple[str, object]] = [
        ("Task", task),
        ("Mode", _display_value(config.get("mode"))),
        ("Agent", _display_value(config.get("agent"))),
        ("Adapter", _display_value(adapter)),
        ("Prompt", format_path(prompt_path)),
        ("Patch", format_path(execution_result.get("patch_path") or ".aidc/agent_patch.diff")),
        ("Patch status", _format_patch_status(patch_status)),
        ("Patch valid", _format_yes_no(patch_valid)),
        ("Targets", _format_targets(targets)),
        ("Message", str(execution_result.get("message", ""))),
        ("Next", next_step),
    ]

    if warnings:
        rows.append(("Warnings", _format_notes(warnings)))

    stdout_preview = _preview_text(execution_result.get("stdout", ""))
    stderr_preview = _preview_text(execution_result.get("stderr", ""))

    if stdout_preview:
        rows.append(("Stdout", stdout_preview))

    if stderr_preview:
        rows.append(("Stderr", stderr_preview))

    errors = execution_result.get("errors", [])
    if errors:
        rows.append(("Errors", _format_notes(errors)))

    return rows


def _print_prepared_summary(
    *,
    task: str,
    config: dict,
    adapter: str,
    adapter_result: dict,
    prompt_path: str,
    snapshot_display: str,
    warnings: list[str],
    ready: bool,
) -> None:
    print_banner()
    print_command_header("Ask", "Prepare context and request a patch", mode="compact")
    print_status_card(
        "Ask prepared",
        [
            ("Task", task),
            ("Mode", _display_value(config.get("mode"))),
            ("Agent", _display_value(config.get("agent"))),
            ("Adapter", _display_value(adapter)),
            ("Prompt", format_path(prompt_path)),
            ("Snapshot", snapshot_display),
            ("Adapter status", _display_adapter_status(adapter_result, ready)),
            ("Message", _display_value(adapter_result.get("message"))),
        ],
        status=_format_ready_status(adapter, ready),
    )

    if warnings:
        print_status_card("Ask warnings", [("Warnings", _format_notes(warnings))], status=format_warning("warn"))


def _format_ready_status(adapter: str, ready: bool) -> str:
    if adapter == "prompt_file":
        return format_warning("manual")

    if ready:
        return format_success("ready")

    return format_warning("not ready")


def _display_adapter_status(adapter_result: dict, ready: bool) -> str:
    status = str(adapter_result.get("status", "unknown")).strip()

    if ready:
        return "ready"

    if status:
        return status

    return "unknown"


def _format_execution_status(status: str) -> str:
    if status == "patch_ready":
        return format_success("patch_ready")

    if status in {
        "invalid_patch",
        "command_failed",
        "timeout",
        "invalid_command",
        "http_error",
        "missing_api_key",
        "invalid_json",
        "invalid_response",
        "missing_base_url",
        "missing_prompt",
    }:
        return format_error(status)

    if status in {"missing_patch", "empty_patch", "not_ready"}:
        return format_warning(status)

    return format_warning(status or "not_ready")


def _format_patch_status(value: object) -> str:
    status = str(value).lower()

    if status == "ready":
        return format_success("ready")

    if status == "empty":
        return format_warning("empty")

    if status == "missing":
        return format_warning("missing")

    return format_warning(status or "-")


def _format_yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _format_targets(targets: object) -> str:
    if not targets:
        return "-"

    return ", ".join(str(target) for target in targets)


def _format_notes(notes: object) -> str:
    if not notes:
        return "-"

    return "; ".join(str(note) for note in notes)


def _preview_text(text: object, max_chars: int = 500) -> str:
    if text is None:
        return ""

    normalized = str(text).replace("\r\n", "\n").replace("\r", "\n")
    compact = " | ".join(part.strip() for part in normalized.split("\n") if part.strip())

    if not compact:
        return ""

    if len(compact) <= max_chars:
        return compact

    if max_chars <= 3:
        return compact[:max_chars]

    return compact[: max_chars - 3] + "..."


def _display_value(value: object) -> object:
    if value is None or value == "":
        return "-"

    return value


def _merge_unique(existing: list[str], additions: Sequence[str]) -> list[str]:
    merged = list(existing)

    for item in additions:
        text = str(item).strip()
        if text and text not in merged:
            merged.append(text)

    return merged


def _parse_ask_args(args: Sequence[str]) -> dict:
    positionals: list[str] = []

    for arg in args:
        if arg.startswith("-"):
            raise ValueError(f"Unknown option: {arg}")

        positionals.append(arg)

    if not positionals:
        raise ValueError("ask requires a task")

    if len(positionals) > 2:
        raise ValueError("ask accepts a task and an optional root path")

    task = positionals[0]
    root = positionals[1] if len(positionals) == 2 else None

    return {
        "task": task,
        "root": root,
    }


def _validate_root(root: str) -> bool:
    root_path = Path(root)

    if not root_path.exists():
        _print_error("Ask failed", f"path does not exist: {root}")
        return False

    if not root_path.is_dir():
        _print_error("Ask failed", f"path is not a directory: {root}")
        return False

    return True


def _print_usage() -> None:
    print('Usage: strata ask "<task>" [root]')


def _print_error(title: str, message: str) -> None:
    print_banner()
    print_command_header("Ask", title, mode="compact")
    print(format_error(message))


def _print_direct_edit_warning() -> None:
    for line in _DIRECT_EDIT_WARNING_LINES:
        print(line)


def _manual_next_steps() -> list[str]:
    return [
        "1. Open `.aidc/agent_prompt.md`",
        "2. Paste it into the AI tool",
        "3. Ask for a unified diff",
        "4. Save it to `.aidc/agent_patch.diff`",
        "5. Run `strata review`",
    ]


def _not_ready_next_steps() -> list[str]:
    return [
        "Run `strata doctor adapter`.",
        "Fix the adapter setup, then run `strata ask` again.",
    ]
