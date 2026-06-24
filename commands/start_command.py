from __future__ import annotations

from pathlib import Path

from adapter_doctor import check_adapter
from cli_core import build_graph, save_graph
from repo_summary import build_repo_intelligence_rows, summarize_graph
from ui import (
    build_banner,
    build_kv_table,
    build_section,
    format_error,
    format_path,
    format_success,
    format_warning,
    print_command_header,
    print_status_card,
)
from workflow_config import config_path, load_config


def write_start_command(root_path: str = ".") -> int:
    root = Path(root_path)

    if not root.exists():
        _print_error("Start failed", f"path does not exist: {root_path}")
        return 1

    if not root.is_dir():
        _print_error("Start failed", f"path is not a directory: {root_path}")
        return 1

    graph = build_graph(root_path)
    if graph is None:
        return 1

    save_graph(graph)

    config_exists = config_path(root).exists()
    adapter_result = None

    if config_exists:
        try:
            load_config(root)
        except ValueError as error:
            _print_error("Workflow config error", str(error))
            return 1

        adapter_result = check_adapter(root)

    repo_summary = summarize_graph(graph)
    repo_ready = bool(config_exists and adapter_result is not None and adapter_result.get("ready"))
    status = (
        format_success("ready")
        if repo_ready
        else format_warning("setup required")
        if not config_exists
        else format_warning("not ready")
    )

    print(build_banner())
    print()
    print_command_header("Start", "Prepare Strata for this repository", mode="compact")
    print_status_card(
        "Start summary",
        [
            ("Root", format_path(graph["root"])),
            ("Files", len(graph.get("files", []))),
            ("Edges", len(graph.get("edges", []))),
            ("Config", "present" if config_exists else "missing"),
            ("Adapter", _display_adapter(adapter_result, config_exists)),
            ("Adapter status", _display_adapter_status(adapter_result, config_exists)),
            ("Repo readiness", _display_repo_readiness(config_exists, adapter_result)),
            ("Next", _next_step(config_exists, adapter_result)),
        ],
        status=status,
    )

    intelligence_rows = build_repo_intelligence_rows(repo_summary)
    if intelligence_rows:
        print()
        print(build_section("Repo intelligence"))
        print(build_kv_table(intelligence_rows))

    return 0


def _display_adapter(adapter_result: dict | None, config_exists: bool) -> str:
    if adapter_result is None and not config_exists:
        return "prompt_file"

    if adapter_result is None:
        return "-"

    adapter = str(adapter_result.get("adapter") or "").strip()
    return adapter or "-"


def _display_adapter_status(adapter_result: dict | None, config_exists: bool) -> str:
    if not config_exists:
        return "setup required"

    if adapter_result is None:
        return "unknown"

    status = str(adapter_result.get("status", "unknown")).strip()
    if status == "ready":
        return "ready"

    if status == "not_ready":
        return "not ready"

    if status == "invalid":
        return "invalid"

    return status or "unknown"


def _display_repo_readiness(config_exists: bool, adapter_result: dict | None) -> str:
    if not config_exists:
        return "setup required"

    if adapter_result is None:
        return "unknown"

    if adapter_result.get("ready"):
        return "ready"

    return "not ready"


def _next_step(config_exists: bool, adapter_result: dict | None) -> str:
    if not config_exists:
        return 'Run `strata setup`, then `strata ask "your task"`.'

    if adapter_result is not None and not adapter_result.get("ready"):
        return 'Run `strata ask "your task"` after the adapter is ready.'

    return 'Run `strata ask "your task"`.'


def _print_error(title: str, message: str) -> None:
    print(build_banner())
    print()
    print_command_header("Start", title, mode="compact")
    print(format_error(message))
