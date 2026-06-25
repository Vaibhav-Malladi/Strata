from pathlib import Path

from agent_export import write_agent_prompt
from cli_core import CONTEXT_PACK_FILE, OUTPUT_FILE, PREFLIGHT_FILE, build_graph, save_graph
from context_pack import build_context_pack
from preflight import write_preflight_report
from routes import collect_routes
from snapshot import write_snapshot
from snapshot_cache import (
    capture_repo_snapshot,
    format_snapshot_cache_status,
    write_repo_snapshot_cache,
)
from full_scan import load_full_scan_cache, format_full_scan_status
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

from commands.agent_prompt_command import AGENT_PROMPT_FILE

PREPARE_USAGE = 'Usage: strata prepare "<task>" [root]'


def write_prepare_command(root_path: str, task: str | None = None) -> int:
    if not task:
        _print_usage()
        return 1

    try:
        config = load_config(root_path)
    except ValueError as error:
        _print_error("Workflow config error", str(error))
        return 1

    try:
        result = prepare_workflow(root_path, task, config)
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
                ("Root", format_path(root_path)),
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

    if result["snapshot_result"] is None:
        print()
        print(format_warning("Snapshot skipped"))

    return 0


def prepare_workflow(
    root_path: str,
    task: str,
    config: dict | None = None,
    selected_paths: list[str] | None = None,
) -> dict | None:
    if config is None:
        config = load_config(root_path)

    selected_paths = selected_paths or []

    before_snapshot = capture_repo_snapshot(root_path)
    graph = build_graph(root_path)

    if graph is None:
        return None

    try:
        save_graph(graph)
        routes_data = collect_routes(graph)

        _write_context_pack(graph, task, routes_data, selected_paths)
        write_preflight_report(graph, task, PREFLIGHT_FILE)
        _write_agent_prompt(graph, task, config["agent"], selected_paths)

        snapshot_result = None

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
    }


def _write_context_pack(
    graph: dict,
    task: str,
    routes_data: list[dict],
    selected_paths: list[str],
) -> None:
    output_path = Path(CONTEXT_PACK_FILE)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        build_context_pack(graph, task, routes_data, selected_paths=selected_paths),
        encoding="utf-8",
    )


def _write_agent_prompt(graph: dict, task: str, agent: str, selected_paths: list[str]) -> None:
    resolved_agent = _resolve_prompt_agent(agent)
    write_agent_prompt(
        graph,
        task,
        resolved_agent,
        AGENT_PROMPT_FILE,
        selected_paths=selected_paths,
    )


def _resolve_prompt_agent(agent: str) -> str:
    normalized = agent.strip().lower()

    if normalized in {"manual", "codex"}:
        return "generic"

    return normalized


def _print_usage() -> None:
    print(PREPARE_USAGE)


def _print_error(title: str, message: str) -> None:
    print(build_banner())
    print()
    print(build_section(title))
    print(format_error(message))
