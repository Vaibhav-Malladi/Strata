from __future__ import annotations

from builtins import input as input
from pathlib import Path
from typing import Any, Sequence

from agent_adapters import run_adapter
from commands.apply_command import write_apply_command
from commands.ask_command import _build_inline_review_result, _execute_adapter
from commands.prepare_command import prepare_workflow
from context_budget import BudgetParseError, build_budget_summary_rows, parse_budget_value
from full_scan import describe_full_scan_readiness, format_full_scan_status, load_full_scan_cache
from selected_context import (
    context_mode_description,
    context_mode_label,
    format_file_reference_failure_lines,
    format_file_reference_resolution_lines,
    format_selected_file_list,
    resolve_file_references,
    normalize_selected_paths,
)
from snapshot_cache import format_snapshot_cache_status
from ui import (
    format_error,
    format_path,
    format_success,
    format_warning,
    print_banner,
    print_command_header,
    print_status_card,
    render_step,
    status_spinner,
)
from workflow_config import load_config
from workflow_planner import build_step_plan

RUN_USAGE = 'Usage: strata run [--file <reference>]... [--budget <preset|tokens>] [--dry-run] [--fast] [--type <task_type>] "<task>" [root]'


def write_run_command(root_path: str, *args: str) -> int:
    try:
        parsed = _parse_run_args(args)
    except BudgetParseError as error:
        _print_error("Run failed", str(error))
        return 1
    except ValueError:
        _print_usage()
        return 1

    root = parsed["root"] or root_path
    task = parsed["task"]
    task_type = parsed["task_type"]
    dry_run = parsed["dry_run"]
    fast = parsed["fast"]
    raw_selected_paths = parsed["selected_paths"]

    if not _validate_root(root):
        return 1

    try:
        resolution_result = resolve_file_references(root, raw_selected_paths, task=task)
    except ValueError as error:
        _print_error("Run failed", str(error))
        return 1

    if resolution_result["status"] != "resolved":
        failed = resolution_result.get("failed") or resolution_result
        _print_error(
            "Run failed",
            str(failed.get("message") or "File reference could not be resolved."),
            format_file_reference_failure_lines(failed)[1:],
        )
        return 1

    try:
        selected_paths = normalize_selected_paths(root, resolution_result["resolved_paths"])
    except ValueError as error:
        _print_error("Run failed", str(error))
        return 1

    resolution_lines = format_file_reference_resolution_lines(resolution_result)
    if resolution_lines:
        for line in resolution_lines:
            print(line)

    try:
        config = load_config(root)
    except ValueError as error:
        _print_error("Workflow config error", str(error))
        return 1

    try:
        with status_spinner(render_step("Planning run", "running")) as spinner:
            plan = build_step_plan(
                task,
                explicit_type=task_type,
                auto_snapshot=config["auto_snapshot"],
                auto_verify=config["auto_verify"],
            )
            spinner.update(render_step("Preparing workflow", "running"))
    except ValueError as error:
        _print_error("Run failed", str(error))
        return 1

    if dry_run:
        try:
            adapter_result = run_adapter(config["adapter"], root, config, dry_run=True)
        except ValueError as error:
            _print_error("Run failed", str(error))
            return 1

        preview_result = prepare_workflow(
            root,
            task,
            config,
            selected_paths=selected_paths,
            budget_value=parsed["budget"],
            write_outputs=False,
        )
        if preview_result is None:
            return 1

        _print_plan(
            title="Run plan",
            status=format_success("dry-run"),
            plan=plan,
            config=config,
            rows=_build_dry_run_rows(
                adapter_result,
                selected_paths,
                preview_result.get("budget_report", {}),
            ),
        )
        return 0

    try:
        with status_spinner(render_step("Preparing context", "running")) as spinner:
            prepare_result = prepare_workflow(
                root,
                task,
                config,
                selected_paths=selected_paths,
                budget_value=parsed["budget"],
            )
            spinner.update(render_step("Requesting patch", "running"))
    except ValueError as error:
        _print_error("Run failed", str(error))
        return 1

    if prepare_result is None:
        return 1

    if str(config.get("adapter", "")).strip().lower() != "prompt_file":
        try:
            with status_spinner(render_step("Collecting patch", "running")) as spinner:
                _execute_adapter(root, str(config["adapter"]), prepare_result["config"])
                spinner.update(render_step("Reviewing patch", "running"))
        except ValueError as error:
            _print_error("Run failed", str(error))
            return 1

    review_result = _build_inline_review_result(root, mode="run")
    snapshot_result = prepare_result["snapshot_result"]
    cache_result = prepare_result.get("cache_result")
    full_scan_state = prepare_result.get("full_scan_state") or load_full_scan_cache(root)
    snapshot_display = (
        format_path(Path(snapshot_result["latest_path"]))
        if snapshot_result is not None
        else "skipped"
    )
    snapshot_cache_display = (
        format_snapshot_cache_status(cache_result) if cache_result is not None else "skipped"
    )
    full_scan_display = format_full_scan_status(full_scan_state)
    prompt_path = str(prepare_result["config"].get("prompt_path") or ".aidc/agent_prompt.md")

    _print_guided_summary(
        task=task,
        config=prepare_result["config"],
        prompt_path=prompt_path,
        snapshot_display=snapshot_display,
        snapshot_cache_display=snapshot_cache_display,
        full_scan_display=full_scan_display,
        full_scan_state=full_scan_state,
        review_result=review_result,
        selected_paths=prepare_result.get("selected_paths", selected_paths),
    )
    print_status_card("Budget Summary", build_budget_summary_rows(prepare_result.get("budget_report", {})))
    _print_snapshot_cache_note(cache_result)
    _print_full_scan_note(full_scan_state, prepare_result.get("selected_paths", selected_paths))

    if review_result["ready"] and fast:
        if _confirm_apply():
            apply_exit = write_apply_command(root, yes=True)
            if apply_exit != 0:
                return apply_exit

            _print_block("Next", ["run your project tests", "strata gate"])
            return 0

        _print_block("Next", ["strata apply"])
        return 0

    if review_result["ready"]:
        _print_block("Next", ["strata apply"])
        return 0

    _print_block("Fix", ["inspect .aidc/agent_patch.diff", "run strata review"])
    return 1


def _build_dry_run_rows(
    adapter_result: dict[str, object],
    selected_paths: list[str],
    budget_report: dict,
) -> list[tuple[str, object]]:
    rows: list[tuple[str, object]] = [
        ("Writes files", "no"),
        ("Executes AI", "no"),
    ]

    adapter_name = str(adapter_result.get("adapter", ""))
    prompt_path = str(adapter_result.get("prompt_path") or "")
    patch_path = str(adapter_result.get("patch_path") or "")
    message = str(adapter_result.get("message") or "")

    if adapter_name == "command":
        command = adapter_result.get("command")
        rows.append(("Command", command if command is not None else ""))
        if prompt_path:
            rows.append(("Prompt", format_path(Path(prompt_path))))
        if patch_path:
            rows.append(("Patch", format_path(Path(patch_path))))
        rows.append(("Executes command", "no"))
    elif prompt_path:
        rows.append(("Prompt", format_path(Path(prompt_path))))

    if message:
        rows.append(("Message", message))

    if selected_paths:
        rows.append(("Context mode", context_mode_label(selected_paths)))
        rows.append(("Selected files", format_selected_file_list(selected_paths)))

    rows.append(("Budget summary", "see below"))
    rows.extend(build_budget_summary_rows(budget_report))

    return rows


def _parse_run_args(args: Sequence[str]) -> dict[str, Any]:
    dry_run = False
    fast = False
    task_type = None
    positionals: list[str] = []
    selected_paths: list[str] = []
    budget_value: str | None = None
    index = 0

    while index < len(args):
        arg = args[index]

        if arg == "--file":
            index += 1
            if index >= len(args):
                raise ValueError("--file requires a file reference")
            selected_paths.append(args[index])
        elif arg == "--dry-run":
            dry_run = True
        elif arg == "--fast":
            fast = True
        elif arg == "--type":
            index += 1
            if index >= len(args):
                raise ValueError("--type requires a task type")
            task_type = args[index]
        elif arg == "--budget":
            index += 1
            if index >= len(args):
                raise ValueError("--budget requires a preset or token count")
            budget_value = args[index]
        elif arg.startswith("--budget="):
            budget_value = arg.split("=", 1)[1]
            if not budget_value:
                raise ValueError("--budget requires a preset or token count")
        elif arg.startswith("-"):
            raise ValueError(f"Unknown option: {arg}")
        else:
            positionals.append(arg)

        index += 1

    if not positionals:
        raise ValueError("run requires a task")

    if len(positionals) > 2:
        raise ValueError("run accepts a task and an optional root path")

    task = positionals[0]
    root = positionals[1] if len(positionals) == 2 else None

    if budget_value is not None:
        budget_value = parse_budget_value(budget_value).get("raw")

    return {
        "dry_run": dry_run,
        "fast": fast,
        "root": root,
        "task": task,
        "task_type": task_type,
        "selected_paths": selected_paths,
        "budget": budget_value,
    }


def _validate_root(root: str) -> bool:
    root_path = Path(root)

    if not root_path.exists():
        _print_error("Run failed", f"path does not exist: {root}")
        return False

    if not root_path.is_dir():
        _print_error("Run failed", f"path is not a directory: {root}")
        return False

    return True


def _print_plan(
    title: str,
    status: str,
    plan: dict,
    config: dict,
    rows: list[tuple[str, object]],
) -> None:
    classification = plan["classification"]

    table_rows = [
        ("Task", plan["task"]),
        ("Task type", classification["task_type"]),
        ("Confidence", classification["confidence"]),
        ("Mode", config["mode"]),
        ("Agent", config["agent"]),
        ("Adapter", config["adapter"]),
        ("Steps", " -> ".join(plan["steps"])),
    ]
    table_rows.extend(rows)

    print_banner()
    print_command_header("Run", "Workflow planning", mode="compact")
    print_status_card(title, table_rows, status=status)


def _print_guided_summary(
    *,
    task: str,
    config: dict,
    prompt_path: str,
    snapshot_display: str,
    snapshot_cache_display: str,
    full_scan_display: str,
    full_scan_state: dict | None,
    review_result: dict,
    selected_paths: list[str],
) -> None:
    rows = [
        ("Task", task),
        ("Mode", config["mode"]),
        ("Agent", config["agent"]),
        ("Adapter", config["adapter"]),
        ("Prompt", format_path(Path(prompt_path)) if prompt_path else "skipped"),
        ("Snapshot", snapshot_display),
        ("Snapshot cache", snapshot_cache_display),
        ("Full scan", full_scan_display),
        ("Context mode", context_mode_label(selected_paths)),
        ("Confidence", _context_confidence(full_scan_state)),
    ]
    if selected_paths:
        rows.insert(8, ("Selected files", format_selected_file_list(selected_paths)))
    rows.extend(review_result["rows"])

    print_banner()
    print_command_header("Run", "Guided patch-first workflow", mode="compact")
    print_status_card(
        "Run summary",
        rows,
        status=format_success("ready") if review_result["ready"] else format_warning("needs attention"),
    )


def _print_block(title: str, lines: list[str]) -> None:
    print(f"{title}:")
    for line in lines:
        print(f"  {line}")


def _confirm_apply() -> bool:
    try:
        response = input("Apply this patch now? [y/N]: ")
    except EOFError:
        return False

    return response.strip().lower() in {"y", "yes"}


def _print_error(title: str, message: str, details: list[str] | None = None) -> None:
    print_banner()
    print_status_card(title, [("Message", message)], status=format_error("failed"))

    for line in details or []:
        print(line)


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


def _print_full_scan_note(full_scan_state: dict | None, selected_paths: list[str]) -> None:
    readiness = describe_full_scan_readiness(full_scan_state)

    if readiness["ready"]:
        return

    print(
        format_warning(
            f"Full repo scan is not ready; using {context_mode_description(selected_paths)}. Run `strata scan`."
        )
    )


def _print_usage() -> None:
    print(RUN_USAGE)


def _context_confidence(full_scan_state: dict | None) -> str:
    status = str((full_scan_state or {}).get("status", "missing")).strip().lower()

    if status == "fresh":
        return "full"

    if status in {"partial", "stale"}:
        return "medium"

    return "basic"
