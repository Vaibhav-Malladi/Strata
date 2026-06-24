from __future__ import annotations

from builtins import input as input
from pathlib import Path
from typing import Any, Sequence

from agent_adapters import run_adapter
from commands.apply_command import write_apply_command
from commands.ask_command import _build_inline_review_result, _execute_adapter
from commands.prepare_command import prepare_workflow
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

RUN_USAGE = 'Usage: strata run [--dry-run] [--fast] [--type <task_type>] "<task>" [root]'


def write_run_command(root_path: str, *args: str) -> int:
    try:
        parsed = _parse_run_args(args)
    except ValueError:
        _print_usage()
        return 1

    root = parsed["root"] or root_path
    task = parsed["task"]
    task_type = parsed["task_type"]
    dry_run = parsed["dry_run"]
    fast = parsed["fast"]

    if not _validate_root(root):
        return 1

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

        _print_plan(
            title="Run plan",
            status=format_success("dry-run"),
            plan=plan,
            config=config,
            rows=_build_dry_run_rows(adapter_result),
        )
        return 0

    try:
        with status_spinner(render_step("Preparing context", "running")) as spinner:
            prepare_result = prepare_workflow(root, task, config)
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
    snapshot_display = (
        format_path(Path(snapshot_result["latest_path"]))
        if snapshot_result is not None
        else "skipped"
    )
    prompt_path = str(prepare_result["config"].get("prompt_path") or ".aidc/agent_prompt.md")

    _print_guided_summary(
        task=task,
        config=prepare_result["config"],
        prompt_path=prompt_path,
        snapshot_display=snapshot_display,
        review_result=review_result,
    )

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
    fast = False
    task_type = None
    positionals: list[str] = []
    index = 0

    while index < len(args):
        arg = args[index]

        if arg == "--dry-run":
            dry_run = True
        elif arg == "--fast":
            fast = True
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
        "fast": fast,
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
    review_result: dict,
) -> None:
    rows = [
        ("Task", task),
        ("Mode", config["mode"]),
        ("Agent", config["agent"]),
        ("Adapter", config["adapter"]),
        ("Prompt", format_path(Path(prompt_path)) if prompt_path else "skipped"),
        ("Snapshot", snapshot_display),
    ]
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


def _print_error(title: str, message: str) -> None:
    print_banner()
    print_status_card(title, [("Message", message)], status=format_error("failed"))


def _print_usage() -> None:
    print(RUN_USAGE)
