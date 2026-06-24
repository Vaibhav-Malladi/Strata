from __future__ import annotations

from pathlib import Path
from typing import Sequence

from adapter_doctor import check_adapter
from command_executor import DEFAULT_TIMEOUT_SECONDS, execute_command_adapter
from cli_core import CONTEXT_PACK_FILE
from commands.prepare_command import prepare_workflow
from context_efficiency import compute_context_efficiency, estimate_graph_source_chars
from context_pack import rank_relevant_files
from direct_edit import DIRECT_EDIT_REPORT_PATH, detect_direct_edits, snapshot_working_files, write_direct_edit_diff
from http_executor import execute_openai_compatible_http_adapter
from ollama_adapter import execute_ollama_adapter
from patch_contract import inspect_patch
from patch_validator import validate_patch_file
from snapshot_cache import format_snapshot_cache_status
from ui import (
    format_error,
    format_path,
    format_success,
    format_warning,
    print_banner,
    print_command_header,
    print_error,
    print_success,
    print_status_card,
    render_step,
    status_spinner,
)
from workflow_config import load_config

_DIRECT_EDIT_WARNING_LINES = [
    "Warning:",
    "  This adapter may edit files directly.",
    "  Strata will write `.aidc/direct_edit.diff` if no patch is produced.",
    "  Run `strata review` and inspect `git diff` carefully.",
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
    cache_result = prepare_result.get("cache_result")
    snapshot_display = (
        format_path(Path(snapshot_result["latest_path"]))
        if snapshot_result is not None
        else "skipped"
    )
    snapshot_cache_display = (
        format_snapshot_cache_status(cache_result) if cache_result is not None else "skipped"
    )
    warnings = list(adapter_result.get("warnings", []) or [])
    context_efficiency_rows = _build_context_efficiency_rows(
        prepare_result["graph"],
        task,
        _read_text_chars(Path(CONTEXT_PACK_FILE)),
    )

    if not ready:
        _print_prepared_summary(
            task=task,
            config=prepare_result["config"],
            adapter=adapter,
            adapter_result=adapter_result,
            prompt_path=prompt_path,
            snapshot_display=snapshot_display,
            snapshot_cache_display=snapshot_cache_display,
            warnings=warnings,
            ready=ready,
            cache_result=cache_result,
        )
        print_status_card("Context Efficiency", context_efficiency_rows)
        _print_snapshot_cache_note(cache_result)
        for line in _not_ready_next_steps():
            print(line)
        print_status_card(
            "Connect AI",
            _ask_setup_rows(adapter_result, ready),
            status=format_warning("setup required"),
        )
        print_error('Fix: Run `strata setup` or `strata setup --manual`, then run `strata ask` again.')
        return 1

    if adapter == "prompt_file":
        _print_prepared_summary(
            task=task,
            config=prepare_result["config"],
            adapter=adapter,
            adapter_result=adapter_result,
            prompt_path=prompt_path,
            snapshot_display=snapshot_display,
            snapshot_cache_display=snapshot_cache_display,
            warnings=warnings,
            ready=ready,
            cache_result=cache_result,
        )
        print_status_card("Context Efficiency", context_efficiency_rows)
        _print_snapshot_cache_note(cache_result)

        for line in _manual_next_steps():
            print(line)
        print_success('Next: Save the AI patch to `.aidc/agent_patch.diff`, then run `strata review`.')
        return 0

    if adapter_family == "command":
        _print_direct_edit_warning()

    print_status_card("Context Efficiency", context_efficiency_rows)
    before_snapshot = snapshot_working_files(root) if adapter_family == "command" else None
    if before_snapshot is not None:
        (Path(root) / DIRECT_EDIT_REPORT_PATH).unlink(missing_ok=True)

    execution_result = _execute_adapter(root, adapter, prepare_result["config"])
    direct_edit_report = _maybe_write_direct_edit_report(root, before_snapshot, execution_result)
    if direct_edit_report is not None:
        print_banner()
        print_command_header("Ask", "Prepare context and request a patch", mode="compact")
        _print_direct_edit_detected(direct_edit_report)
        return 1

    review_result = _build_inline_review_result(root)

    print_banner()
    print_command_header("Ask", "Prepare context and request a patch", mode="compact")
    print_status_card(
        "Inline review",
        review_result["rows"],
    )

    return 0 if review_result["ready"] else 1


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


def _build_inline_review_result(root: str, *, mode: str = "ask") -> dict:
    patch_summary = inspect_patch(root)
    summary_status = str(patch_summary.get("status", "missing")).lower()
    validation = None
    validation_error = None

    if summary_status != "missing":
        try:
            validation = validate_patch_file(root)
        except (OSError, ValueError) as error:
            validation_error = str(error)

    patch_status = _inline_patch_status(summary_status, validation, validation_error)
    validation_status = _inline_validation_status(summary_status, validation, validation_error)
    dry_run_status = _inline_dry_run_status(validation, validation_error)
    files_changed = _inline_files_changed(validation)
    targets = _inline_targets(validation)
    fix = _inline_fix(mode, summary_status, validation, validation_error)
    next_step = _inline_next_step(mode, summary_status, validation, validation_error)

    rows: list[tuple[str, object]] = [
        ("Patch status", _format_inline_value(patch_status)),
        ("Validation", _format_inline_value(validation_status)),
        ("Dry-run", _format_inline_value(dry_run_status)),
        ("Files changed", files_changed),
        ("Targets", targets),
    ]

    if fix:
        rows.append(("Fix", fix))

    rows.append(("Next", next_step))

    return {
        "rows": rows,
        "ready": patch_status == "ready",
    }


def _print_prepared_summary(
    *,
    task: str,
    config: dict,
    adapter: str,
    adapter_result: dict,
    prompt_path: str,
    snapshot_display: str,
    snapshot_cache_display: str,
    warnings: list[str],
    ready: bool,
    cache_result: dict | None,
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
            ("Snapshot cache", snapshot_cache_display),
            ("Adapter status", _display_adapter_status(adapter_result, ready)),
            ("Message", _display_value(adapter_result.get("message"))),
        ],
        status=_format_ready_status(adapter, ready),
    )

    if warnings:
        print_status_card("Ask warnings", [("Warnings", _format_notes(warnings))], status=format_warning("warn"))


def _print_snapshot_cache_note(cache_result: dict | None) -> None:
    if not cache_result:
        return

    changed_count = int(cache_result.get("stale_count", 0) or 0)
    if changed_count <= 0:
        return

    status = str(cache_result.get("status", "partial")).strip().lower()
    if status == "stale":
        message = f"Snapshot cache stale: {changed_count} file(s) need refresh."
    else:
        message = f"Snapshot cache partial: {changed_count} file(s) changed while Strata was scanning."

    print(format_warning(message))


def _inline_patch_status(
    summary_status: str,
    validation: dict | None,
    validation_error: str | None,
) -> str:
    if validation_error is not None:
        return "invalid"

    if validation is None:
        return summary_status or "missing"

    status = str(validation.get("status", summary_status or "missing")).lower()

    if status == "valid":
        return "ready"

    return status or "missing"


def _inline_validation_status(
    summary_status: str,
    validation: dict | None,
    validation_error: str | None,
) -> str:
    if validation_error is not None:
        return "failed"

    if validation is None:
        if summary_status == "missing":
            return "missing"
        return "not run"

    status = str(validation.get("status", summary_status or "missing")).lower()

    if status == "valid":
        return "passed"

    return status or "not run"


def _inline_dry_run_status(validation: dict | None, validation_error: str | None) -> str:
    if validation_error is not None:
        return "failed"

    if validation is None:
        return "not run"

    status = str(validation.get("status", "invalid")).lower()
    if status == "valid":
        return "passed"

    return "not run"


def _inline_files_changed(validation: dict | None) -> object:
    if validation is None:
        return "-"

    if str(validation.get("status", "")).lower() != "valid":
        return "-"

    return str(len(validation.get("targets", []) or []))


def _inline_targets(validation: dict | None) -> object:
    if validation is None:
        return "-"

    if str(validation.get("status", "")).lower() != "valid":
        return "-"

    targets = validation.get("targets", [])
    return ", ".join(str(target) for target in targets) if targets else "-"


def _inline_fix(
    mode: str,
    summary_status: str,
    validation: dict | None,
    validation_error: str | None,
) -> str | None:
    normalized_mode = str(mode or "ask").strip().lower()

    if normalized_mode == "run":
        if validation_error is not None:
            return "Inspect `.aidc/agent_patch.diff`, then run `strata review`."

        if summary_status == "missing":
            return "Inspect `.aidc/agent_patch.diff`, then run `strata review`."

        if validation is None:
            return "Inspect `.aidc/agent_patch.diff`, then run `strata review`."

        status = str(validation.get("status", summary_status or "missing")).lower()

        if status in {"invalid", "empty"}:
            return "Inspect `.aidc/agent_patch.diff`, then run `strata review`."

        return None

    if validation_error is not None:
        return "Review the adapter output and save a valid unified diff."

    if summary_status == "missing":
        return "Fix the adapter setup or save a patch to `.aidc/agent_patch.diff`."

    if validation is None:
        return None

    status = str(validation.get("status", summary_status or "missing")).lower()

    if status in {"invalid", "empty"}:
        return "Ask the AI to return a valid unified diff."

    return None


def _inline_next_step(
    mode: str,
    summary_status: str,
    validation: dict | None,
    validation_error: str | None,
) -> str:
    normalized_mode = str(mode or "ask").strip().lower()

    if normalized_mode == "run":
        if validation_error is not None or summary_status == "missing":
            return "Run `strata review`."

        if validation is None:
            return "Run `strata review`."

        status = str(validation.get("status", summary_status or "missing")).lower()

        if status == "valid":
            return "Run `strata apply`."

        return "Run `strata review`."

    if validation_error is not None:
        return "Run `strata review`."

    if summary_status == "missing":
        return 'Run `strata ask "your task"` again, or run `strata review` after saving a patch.'

    if validation is None:
        return "Run `strata review`."

    status = str(validation.get("status", summary_status or "missing")).lower()

    if status == "valid":
        return "Run `strata review` for full review, or `strata apply` when ready."

    return 'Run `strata ask "your task"` again.'


def _format_inline_value(status: str) -> str:
    normalized = str(status or "").strip().lower()

    if normalized == "ready":
        return format_success("ready")

    if normalized == "passed":
        return format_success("passed")

    if normalized in {"missing", "not run", "empty"}:
        return format_warning(normalized)

    if normalized in {"invalid", "failed"}:
        return format_error(normalized)

    return format_warning(normalized or "-")


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


def _maybe_write_direct_edit_report(
    root: str,
    before_snapshot: dict[str, str] | None,
    execution_result: dict,
) -> Path | None:
    if before_snapshot is None:
        return None

    if str(execution_result.get("patch_status", "missing")).lower() != "missing":
        return None

    changed_paths = detect_direct_edits(before_snapshot, root)
    if not changed_paths:
        return None

    return write_direct_edit_diff(root, changed_paths)


def _print_direct_edit_detected(report_path: Path) -> None:
    print_status_card(
        "Direct edit detected",
        [
            ("Message", "The AI adapter changed files directly instead of creating `.aidc/agent_patch.diff`."),
            ("Diff report", format_path(report_path)),
            ("Next", "Run `strata review` and inspect `git diff` carefully."),
        ],
        status=format_warning("warn"),
    )


def _manual_next_steps() -> list[str]:
    return [
        "1. Open `.aidc/agent_prompt.md`.",
        "2. Paste it into ChatGPT, Claude, Gemini, or Copilot Chat.",
        "3. Ask for a unified diff.",
        "4. Save it to `.aidc/agent_patch.diff`.",
        "5. Run `strata review`, then `strata apply --dry-run`.",
    ]


def _not_ready_next_steps() -> list[str]:
    return [
        "No AI adapter is configured yet.",
        "Run `strata setup` to choose an AI mode.",
        "For browser AI, run `strata setup --manual`.",
        "Then paste `.aidc/agent_prompt.md` into ChatGPT, Claude, Gemini, or Copilot Chat.",
        "Save the returned unified diff to `.aidc/agent_patch.diff`.",
        "Run `strata review`, then `strata apply --dry-run`.",
    ]


def _ask_setup_rows(adapter_result: dict, ready: bool) -> list[tuple[str, object]]:
    adapter = str(adapter_result.get("adapter") or "prompt_file")
    prompt = str(adapter_result.get("prompt") or ".aidc/agent_prompt.md")
    return [
        ("Adapter", adapter),
        ("Ready", "yes" if ready else "no"),
        ("Prompt", format_path(Path(prompt)) if prompt else ".aidc/agent_prompt.md"),
        ("Browser AI", "No API key or local model required."),
        (
            "Next",
            "Run `strata setup` to choose an AI mode, or `strata setup --manual` for browser AI.",
        ),
    ]


def _build_context_efficiency_rows(
    graph: dict,
    task: str,
    focused_context_chars: int | None,
) -> list[tuple[str, object]]:
    relevant_files = rank_relevant_files(graph, task)
    source_files_scanned = len(graph.get("files", []))
    files_included = len(relevant_files)
    full_source_chars = estimate_graph_source_chars(graph)
    rows: list[tuple[str, object]] = [
        ("Source files scanned", f"{source_files_scanned:,}"),
        ("Files included", f"{files_included:,}"),
    ]

    if focused_context_chars is None:
        rows.append(("Full source estimate", "not available"))
        rows.append(("Strata context estimate", "not available"))
        rows.append(("Estimated context reduction", "not available"))
        rows.append(("Note", "Actual AI token usage may vary by adapter."))
        return rows

    efficiency = compute_context_efficiency(full_source_chars, focused_context_chars)
    rows.append(("Full source estimate", f"~{efficiency['full_source_tokens']:,} tokens"))
    rows.append(("Strata context estimate", f"~{efficiency['focused_context_tokens']:,} tokens"))
    rows.append(("Estimated context reduction", f"~{efficiency['reduction_percent']:,}%"))
    rows.append(("Note", "Actual AI token usage may vary by adapter."))

    return rows


def _read_text_chars(path: Path) -> int | None:
    try:
        return len(path.read_text(encoding="utf-8"))
    except OSError:
        return None
