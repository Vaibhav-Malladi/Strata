from __future__ import annotations

from pathlib import Path

from strata.adapters.doctor import check_adapter
from cli_core import OUTPUT_FILE, build_graph, save_graph
from strata.core.full_scan import (
    LARGE_REPO_THRESHOLD,
    describe_full_scan_readiness,
    format_full_scan_status,
    load_full_scan_cache,
)
from strata.core.repo_summary import build_repo_intelligence_rows, summarize_graph
from strata.core.snapshot_cache import (
    capture_repo_snapshot,
    format_snapshot_cache_status,
    write_repo_snapshot_cache,
)
from strata.utils.output import (
    build_kv_table,
    build_section,
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
from strata.utils.config import config_path, load_config


def write_start_command(root_path: str = ".") -> int:
    root = Path(root_path)

    if not root.exists():
        _print_error("Start failed", f"path does not exist: {root_path}")
        return 1

    if not root.is_dir():
        _print_error("Start failed", f"path is not a directory: {root_path}")
        return 1

    print_banner(compact=False)
    print()
    print_command_header("Start", "Prepare Strata for this repository", mode="compact")
    print_status_card(
        "Reading repository",
        [
            ("Root", format_path(root)),
            ("Graph", format_path(OUTPUT_FILE)),
            ("Status", "scanning"),
        ],
        status=format_warning("working"),
    )

    before_snapshot = capture_repo_snapshot(root)

    with status_spinner(render_step("Building repo map", "running")) as spinner:
        graph = build_graph(root_path)
        if graph is not None:
            spinner.update(render_step("Repo map ready", "ready"))

    if graph is None:
        return 1

    save_graph(graph)

    after_snapshot = capture_repo_snapshot(root)
    snapshot_cache_result = write_repo_snapshot_cache(root, before_snapshot, after_snapshot)
    full_scan_state = load_full_scan_cache(root)

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

    print(format_success("Repo map ready"))
    _print_snapshot_cache_card(snapshot_cache_result)
    print_status_card(
        "Start summary",
        [
            ("Root", format_path(graph["root"])),
            ("Graph", format_path(OUTPUT_FILE)),
            ("Files", len(graph.get("files", []))),
            ("Edges", len(graph.get("edges", []))),
            ("Snapshot cache", format_snapshot_cache_status(snapshot_cache_result)),
            ("Full scan", format_full_scan_status(full_scan_state)),
            ("Changed since snapshot", snapshot_cache_result["changed_since_snapshot_count"]),
            ("Changed during scan", snapshot_cache_result["changed_during_scan_count"]),
            (
                "Setup",
                "first-time repo snapshot setup"
                if not snapshot_cache_result["cache_existed_before"]
                else "refreshed",
            ),
            ("Config", "present" if config_exists else "missing"),
            ("Adapter", _display_adapter(adapter_result, config_exists)),
            ("Adapter status", _display_adapter_status(adapter_result, config_exists)),
            ("Repo readiness", _display_repo_readiness(config_exists, adapter_result)),
            ("Next", _next_step(config_exists, adapter_result)),
        ],
        status=status,
    )

    if snapshot_cache_result["file_count"] >= LARGE_REPO_THRESHOLD:
        print(format_warning("Large repo detected: focused mode still works while the full scan runs."))

    _print_full_scan_note(full_scan_state)
    if not repo_ready:
        print()
        print(build_section("Connect AI"))
        print(
            build_kv_table(
                [
                    ("Setup", 'Run `strata setup` to choose an AI mode.'),
                    (
                        "Manual/browser AI",
                        "Run `strata setup --manual` for browser AI with no API key or local model.",
                    ),
                    ("Ask", 'Then run `strata ask "your task"` after setup.'),
                ]
            )
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
        return 'Run `strata setup` or `strata setup --manual`, then `strata ask "your task"`.'

    if adapter_result is not None and not adapter_result.get("ready"):
        return 'Run `strata setup` or `strata setup --manual`, then `strata ask "your task"` after setup is ready.'

    return 'Run `strata ask "your task"`.'


def _print_error(title: str, message: str) -> None:
    print_banner(compact=False)
    print()
    print_command_header("Start", title, mode="compact")
    print(format_error(message))


def _print_snapshot_cache_card(snapshot_cache_result: dict) -> None:
    if not snapshot_cache_result.get("cache_existed_before"):
        status = format_warning("first-time setup")
    elif snapshot_cache_result.get("status") == "fresh":
        status = format_success("fresh")
    else:
        status = format_warning(str(snapshot_cache_result.get("status", "partial")))

    print_status_card(
        "Repo snapshot",
        [
            ("Cache", format_path(Path(snapshot_cache_result["cache_path"]))),
            ("Status", format_snapshot_cache_status(snapshot_cache_result)),
            ("Changed since snapshot", snapshot_cache_result["changed_since_snapshot_count"]),
            ("Changed during scan", snapshot_cache_result["changed_during_scan_count"]),
        ],
        status=status,
    )


def _print_full_scan_note(full_scan_state: dict | None) -> None:
    readiness = describe_full_scan_readiness(full_scan_state)

    if readiness["ready"]:
        print(format_success(readiness["message"]))
        return

    print(format_warning(readiness["message"]))
