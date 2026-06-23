from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from agent_adapters import run_adapter
from commands.prepare_command import prepare_workflow
from ui import (
    build_banner,
    build_kv_table,
    build_section,
    format_error,
    format_path,
    format_success,
    format_warning,
)
from workflow_config import load_config
from workflow_planner import build_step_plan

RUN_USAGE = 'Usage: strata run [--dry-run] [--type <task_type>] "<task>" [root]'


def write_run_command(root_path: str, *args: str) -> int:
    try:
        parsed = _parse_run_args(args)
    except ValueError as error:
        _print_usage()
        return 1

    root = parsed["root"] or root_path
    task = parsed["task"]
    task_type = parsed["task_type"]
    dry_run = parsed["dry_run"]

    if not _validate_root(root):
        return 1

    try:
        config = load_config(root)
    except ValueError as error:
        _print_error("Workflow config error", str(error))
        return 1

    try:
        plan = build_step_plan(
            task,
            explicit_type=task_type,
            auto_snapshot=config["auto_snapshot"],
            auto_verify=config["auto_verify"],
        )
    except ValueError as error:
        _print_error("Run failed", str(error))
        return 1

    if dry_run:
        try:
            adapter_result = run_adapter(config["adapter"], root, config, dry_run=True)
        except ValueError as error:
            _print_error("Run failed", str(error))
            return 1

        _print_plan(
            title="Run plan",
            status=format_success("dry-run"),
            plan=plan,
            config=config,
            rows=_build_dry_run_rows(adapter_result),
        )
        return 0

    try:
        prepare_result = prepare_workflow(root, task, config)
    except ValueError as error:
        _print_error("Run failed", str(error))
        return 1

    if prepare_result is None:
        return 1

    adapter_result = run_adapter(config["adapter"], root, config)
    status = str(adapter_result.get("status", "not_implemented"))
    prompt_path = str(adapter_result.get("prompt_path") or "")
    next_message = adapter_result.get("message") or "Adapter finished."

    if status == "ready":
        next_message = _prompt_next_step(config["agent"], prompt_path)
        status_text = format_success("ready")
        exit_code = 0
    elif status == "not_implemented":
        status_text = format_warning("not implemented")
        exit_code = 1
    else:
        _print_error("Run failed", str(next_message))
        return 1

    snapshot_result = prepare_result["snapshot_result"]
    snapshot_display = (
        format_path(Path(snapshot_result["latest_path"]))
        if snapshot_result is not None
        else "skipped"
    )

    _print_plan(
        title="Run prepared",
        status=status_text,
        plan=plan,
        config=config,
        rows=[
            ("Prompt", format_path(Path(prompt_path)) if prompt_path else "skipped"),
            ("Snapshot", snapshot_display),
            ("Automation", "not executed"),
            ("Next", next_message),
        ],
    )

    return exit_code


def _build_dry_run_rows(adapter_result: dict[str, object]) -> list[tuple[str, object]]:
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

    return rows


def _parse_run_args(args: Sequence[str]) -> dict[str, Any]:
    dry_run = False
    task_type = None
    positionals: list[str] = []
    index = 0

    while index < len(args):
        arg = args[index]

        if arg == "--dry-run":
            dry_run = True
        elif arg == "--type":
            index += 1
            if index >= len(args):
                raise ValueError("--type requires a task type")
            task_type = args[index]
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

    return {
        "dry_run": dry_run,
        "root": root,
        "task": task,
        "task_type": task_type,
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
        ("Status", status),
        ("Task", plan["task"]),
        ("Task type", classification["task_type"]),
        ("Confidence", classification["confidence"]),
        ("Mode", config["mode"]),
        ("Agent", config["agent"]),
        ("Adapter", config["adapter"]),
        ("Steps", " -> ".join(plan["steps"])),
    ]
    table_rows.extend(rows)

    print(build_banner())
    print()
    print(build_section(title))
    print(build_kv_table(table_rows))


def _prompt_next_step(agent: str, prompt_path: str) -> str:
    prompt_display = format_path(Path(prompt_path))
    normalized_agent = agent.strip().lower()

    if normalized_agent == "codex":
        return f"Paste {prompt_display} into Codex, then run `strata review`."

    if normalized_agent == "aider":
        return f"Paste {prompt_display} into Aider, then run `strata review`."

    return f"Paste {prompt_display} into your AI coding tool, then run `strata review`."


def _print_error(title: str, message: str) -> None:
    print(build_banner())
    print()
    print(build_section(title))
    print(format_error(message))


def _print_usage() -> None:
    print(RUN_USAGE)
