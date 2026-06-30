from __future__ import annotations

from pathlib import Path

from strata.adapters.export import generate_agent_prompt, write_agent_prompt
from cli_core import CONTEXT_PACK_FILE, OUTPUT_FILE, PREFLIGHT_FILE, build_graph, save_graph
from strata.core.context_pack import build_context_pack
from strata.core.context_budget import build_budget_report, build_budget_summary_rows, BudgetParseError, parse_budget_value
from strata.core.context_efficiency import estimate_tokens
from strata.core.preflight import write_preflight_report
from strata.core.routes import collect_routes
from strata.core.snapshot import write_snapshot
from strata.core.snapshot_cache import (
    capture_repo_snapshot,
    format_snapshot_cache_status,
    write_repo_snapshot_cache,
)
from strata.core.full_scan import load_full_scan_cache, format_full_scan_status
from strata.utils.output import (
    build_banner,
    build_kv_table,
    build_section,
    format_error,
    format_path,
    format_success,
    format_warning,
    print_status_card,
)
from strata.utils.config import load_config

from strata.commands.agent_prompt_command import AGENT_PROMPT_FILE

PREPARE_USAGE = 'Usage: strata prepare [--budget <preset|tokens>] "<task>" [root]'


def write_prepare_command(root_path: str = ".", *args: str) -> int:
    try:
        parsed = _parse_prepare_args(args)
    except BudgetParseError as error:
        _print_error("Prepare failed", str(error))
        return 1
    except ValueError:
        _print_usage()
        return 1

    root = parsed["root"] or root_path
    task = parsed["task"]
    budget_value = parsed["budget"]

    try:
        config = load_config(root)
    except ValueError as error:
        _print_error("Workflow config error", str(error))
        return 1

    try:
        result = prepare_workflow(root, task, config, budget_value=budget_value)
    except ValueError as error:
        _print_error("Prepare failed", str(error))
        return 1

    if result is None:
        return 1

    print(build_banner())
    print()
    print(build_section("Prepare complete"))
    print(
        build_kv_table(
            [
                ("Status", format_success("ready")),
                ("Task", task),
                ("Mode", config["mode"]),
                ("Agent", config["agent"]),
                ("Root", format_path(root)),
                ("Graph", format_path(OUTPUT_FILE)),
                ("Context", format_path(CONTEXT_PACK_FILE)),
                ("Preflight", format_path(PREFLIGHT_FILE)),
                ("Agent prompt", format_path(AGENT_PROMPT_FILE)),
                (
                    "Snapshot cache",
                    format_snapshot_cache_status(result["cache_result"])
                    if result.get("cache_result") is not None
                    else "skipped",
                ),
                (
                    "Full scan",
                    format_full_scan_status(result.get("full_scan_state")),
                ),
                (
                    "Snapshot",
                    format_path(Path(result["snapshot_result"]["latest_path"]))
                    if result["snapshot_result"] is not None
                    else "skipped",
                ),
                ("Next", "Paste .aidc\\agent_prompt.md into your AI coding tool."),
            ]
        )
    )
    print()
    print_status_card("Budget Summary", build_budget_summary_rows(result["budget_report"]))

    if result["snapshot_result"] is None:
        print()
        print(format_warning("Snapshot skipped"))

    return 0


def prepare_workflow(
    root_path: str,
    task: str,
    config: dict | None = None,
    selected_paths: list[str] | None = None,
    budget_value: str | None = None,
    write_outputs: bool = True,
) -> dict | None:
    if config is None:
        config = load_config(root_path)

    selected_paths = selected_paths or []
    graph = build_graph(root_path)

    if graph is None:
        return None

    routes_data = []
    snapshot_result = None
    cache_result = None
    full_scan_state = None

    try:
        budget_report = build_budget_report(
            graph,
            task,
            selected_paths=selected_paths,
            budget_value=budget_value,
        )

        routes_data = collect_routes(graph)
        full_scan_state = load_full_scan_cache(root_path)
        agent_prompt_content = _build_agent_prompt_content(graph, task, config["agent"], selected_paths, budget_value)
        budget_report["budgeted_context_tokens"] = estimate_tokens(agent_prompt_content)

        if write_outputs:
            before_snapshot = capture_repo_snapshot(root_path)
            save_graph(graph)
            _write_context_pack(graph, task, routes_data, selected_paths, budget_value)
            write_preflight_report(graph, task, PREFLIGHT_FILE)
            _write_agent_prompt(graph, task, config["agent"], selected_paths, budget_value)

            if config["auto_snapshot"]:
                snapshot_result = write_snapshot(root_path, graph, routes_data)

            after_snapshot = capture_repo_snapshot(root_path)
            cache_result = write_repo_snapshot_cache(root_path, before_snapshot, after_snapshot)
            full_scan_state = load_full_scan_cache(root_path)
    except (OSError, ValueError):
        raise

    return {
        "config": config,
        "graph": graph,
        "routes_data": routes_data,
        "selected_paths": selected_paths,
        "snapshot_result": snapshot_result,
        "cache_result": cache_result,
        "full_scan_state": full_scan_state,
        "budget_report": budget_report,
    }


def _write_context_pack(
    graph: dict,
    task: str,
    routes_data: list[dict],
    selected_paths: list[str],
    budget_value: str | None,
) -> str:
    output_path = Path(CONTEXT_PACK_FILE)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    content = build_context_pack(
        graph,
        task,
        routes_data,
        selected_paths=selected_paths,
        budget_value=budget_value,
    )
    output_path.write_text(content, encoding="utf-8")
    return content


def _write_agent_prompt(
    graph: dict,
    task: str,
    agent: str,
    selected_paths: list[str],
    budget_value: str | None,
) -> str:
    resolved_agent = _resolve_prompt_agent(agent)
    prompt = write_agent_prompt(
        graph,
        task,
        resolved_agent,
        AGENT_PROMPT_FILE,
        selected_paths=selected_paths,
        budget_value=budget_value,
    )
    return prompt


def _build_agent_prompt_content(
    graph: dict,
    task: str,
    agent: str,
    selected_paths: list[str],
    budget_value: str | None,
) -> str:
    resolved_agent = _resolve_prompt_agent(agent)
    return generate_agent_prompt(
        graph,
        task,
        resolved_agent,
        selected_paths=selected_paths,
        budget_value=budget_value,
    )


def _resolve_prompt_agent(agent: str) -> str:
    normalized = agent.strip().lower()

    if normalized in {"manual", "codex"}:
        return "generic"

    if normalized not in {"generic", "local", "aider", "chatgpt"}:
        return "generic"

    return normalized


def _print_usage() -> None:
    print(PREPARE_USAGE)


def _print_error(title: str, message: str) -> None:
    print(build_banner())
    print()
    print(build_section(title))
    print(format_error(message))


def _parse_prepare_args(args: list[str]) -> dict:
    positionals: list[str] = []
    budget_value: str | None = None
    index = 0

    while index < len(args):
        arg = args[index]

        if arg == "--budget":
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
        raise ValueError("prepare requires a task")

    if len(positionals) > 2:
        raise ValueError("prepare accepts a task and an optional root path")

    task = positionals[0]
    root = positionals[1] if len(positionals) == 2 else None

    if budget_value is not None:
        budget_value = parse_budget_value(budget_value).get("raw")

    return {
        "task": task,
        "root": root,
        "budget": budget_value,
    }
