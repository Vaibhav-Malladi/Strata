from __future__ import annotations

from pathlib import Path
from typing import Any

from strata.commands.cli_core import OUTPUT_FILE, build_graph, count_unresolved_imports, save_graph
from strata.core.full_scan import (
    LARGE_REPO_THRESHOLD,
    build_full_scan_payload,
    clear_full_scan_temp_marker,
    describe_full_scan_readiness,
    finalize_full_scan_cache,
    format_full_scan_status,
    load_completed_full_scan_cache,
    load_full_scan_cache,
    write_full_scan_temp_marker,
)
from strata.core.repo_summary import build_repo_intelligence_rows, summarize_graph
from strata.core.snapshot_cache import capture_repo_snapshot, write_repo_snapshot_cache
from strata.utils.output import (
    build_banner,
    build_kv_table,
    build_section,
    format_path,
    format_success,
    format_warning,
    print_command_header,
    render_lifecycle,
    print_status_card,
)


def write_graph(root_path: str, force: bool = False) -> int:
    root = Path(root_path)

    if not root.exists():
        _print_error("Scan failed", f"path does not exist: {root_path}")
        return 1

    if not root.is_dir():
        _print_error("Scan failed", f"path is not a directory: {root_path}")
        return 1

    full_scan_state = load_full_scan_cache(root)
    readiness = describe_full_scan_readiness(full_scan_state)
    had_interrupted_scan = readiness["state"] == "interrupted"

    if force:
        print(format_warning("Forced rescan requested. Rebuilding full repo context now."))

    if had_interrupted_scan:
        print(format_warning(readiness["message"]))

    clear_full_scan_temp_marker(root)

    print(build_banner())
    print()
    print_command_header("Scan", "Full repo intelligence mode", mode="compact")
    print(
        render_lifecycle(
            "Scan phases",
            [
                "Discovering files",
                "Fingerprinting",
                "Parsing source files / building graph",
                "Detecting changes during scan",
                "Saving cache",
            ],
        )
    )

    start_snapshot = capture_repo_snapshot(root)
    total_files = int(start_snapshot.get("file_count", 0) or 0)
    print(
        _progress_card(
            phase="Discovering files",
            discovered=total_files,
            scanned=0,
            skipped=int(start_snapshot.get("ignored_count", 0) or 0),
            failed=0,
            eta="estimating...",
            status="running",
        )
    )
    write_full_scan_temp_marker(
        root,
        {
            "schema_version": 1,
            "status": "scanning",
            "started_at": start_snapshot.get("captured_at"),
            "root": str(root),
            "git_head": start_snapshot.get("git_head"),
            "file_count": total_files,
            "scanned_count": 0,
            "skipped_count": int(start_snapshot.get("ignored_count", 0) or 0),
            "failed_count": 0,
            "changed_during_scan": [],
            "changed_during_scan_count": 0,
            "changed_since_snapshot": [],
            "changed_since_snapshot_count": 0,
            "stale_files": [],
            "stale_count": 0,
            "graph_path": str(Path(".aidc") / "graph.json"),
            "interrupted": True,
        },
    )
    print(
        _progress_card(
            phase="Fingerprinting",
            discovered=total_files,
            scanned=0,
            skipped=int(start_snapshot.get("ignored_count", 0) or 0),
            failed=0,
            eta="estimating...",
            status="running",
        )
    )

    progress_printer = _ScanProgressPrinter(total_files)
    graph = build_graph(root_path, progress=progress_printer, expected_file_count=total_files)
    if graph is None:
        return 1

    save_graph(graph)
    scanned_count = len(graph.get("files", []))
    skipped_count = max(total_files - scanned_count, 0)
    failed_count = sum(1 for file_info in graph.get("files", []) if file_info.get("error"))

    after_snapshot = capture_repo_snapshot(root)
    previous_cache = load_completed_full_scan_cache(root)
    scan_result = build_full_scan_payload(
        root=root,
        before_snapshot=start_snapshot,
        after_snapshot=after_snapshot,
        graph=graph,
        scanned_count=scanned_count,
        skipped_count=skipped_count,
        failed_count=failed_count,
        started_at=start_snapshot.get("captured_at"),
        finished_at=after_snapshot.get("captured_at"),
        graph_path=OUTPUT_FILE,
        previous_cache=previous_cache,
    )
    finalize_full_scan_cache(root, scan_result)
    write_repo_snapshot_cache(root, start_snapshot, after_snapshot)
    unresolved_count = count_unresolved_imports(graph)

    if had_interrupted_scan:
        print(format_success("Interrupted scan recovered."))

    print(
        _progress_card(
            phase="Detecting changes during scan",
            discovered=int(after_snapshot.get("file_count", 0) or 0),
            scanned=scanned_count,
            skipped=skipped_count,
            failed=failed_count,
            eta="estimating...",
            status="running" if scan_result["status"] != "fresh" else "ready",
        )
    )
    print(
        _progress_card(
            phase="Saving cache",
            discovered=int(after_snapshot.get("file_count", 0) or 0),
            scanned=scanned_count,
            skipped=skipped_count,
            failed=failed_count,
            eta="about 0 sec",
            status="ready",
        )
    )

    print(build_banner())
    print()
    print(build_section("Full scan complete"))
    print(
        build_kv_table(
            [
                ("Root", format_path(graph["root"])),
                ("Graph", format_path(OUTPUT_FILE)),
                ("Full scan cache", format_path(Path(".aidc") / "cache" / "repo_scan.json")),
                ("Full scan", format_full_scan_status(scan_result)),
                ("Nodes", len(graph["files"])),
                ("Edges", len(graph["edges"])),
                ("Files discovered", f"{scan_result['file_count']:,}"),
                ("Files scanned", f"{scan_result['scanned_count']:,}"),
                ("Files skipped", f"{scan_result['skipped_count']:,}"),
                ("Failed parses", f"{scan_result['failed_count']:,}"),
                ("Warnings", f"{unresolved_count:,}" if unresolved_count else "none"),
                ("Changed during scan", _format_count(scan_result["changed_during_scan_count"])),
                ("Stale files", _format_count(scan_result["stale_count"])),
                ("ETA", _eta_text("about 0 sec")),
                ("Large repo", "yes" if scan_result["file_count"] >= LARGE_REPO_THRESHOLD else "no"),
                (
                    "Status",
                    format_success("ready")
                    if scan_result["status"] == "fresh"
                    else format_warning(scan_result["status"]),
                ),
                (
                    "Recommendation",
                    scan_result.get("recommendation", "refresh with `strata scan`")
                    if scan_result["status"] != "fresh"
                    else "-",
                ),
            ]
        )
    )

    stale_preview = _preview_paths(scan_result.get("stale_files", []))
    if stale_preview:
        print()
        print(build_section("Changed files"))
        print(build_kv_table([("Sample", stale_preview)]))

    print()
    print(build_section("Repo intelligence"))
    print(build_kv_table(build_repo_intelligence_rows(summarize_graph(graph))))

    return 0


class _ScanProgressPrinter:
    def __init__(self, total_files: int | None):
        self._total_files = total_files
        self._last_phase = ""
        self._last_scanned = -1

    def __call__(self, event: dict[str, Any]) -> None:
        phase = str(event.get("phase", "")).strip().lower()
        scanned = int(event.get("scanned", 0) or 0)

        if phase == self._last_phase and scanned == self._last_scanned:
            return

        self._last_phase = phase
        self._last_scanned = scanned

        print(
            _progress_card(
                phase=_phase_label(phase),
                discovered=int(event.get("discovered", 0) or 0),
                scanned=scanned,
                skipped=int(event.get("skipped", 0) or 0),
                failed=int(event.get("failed", 0) or 0),
                eta=str(event.get("eta", "estimating...") or "estimating..."),
                status="running",
            )
        )


def _progress_card(
    *,
    phase: str,
    discovered: int,
    scanned: int,
    skipped: int,
    failed: int,
    eta: str,
    status: str,
) -> str:
    rows = [
        ("Phase", phase),
        ("Discovered files", _format_count(discovered)),
        ("Scanned files", _format_count(scanned)),
        ("Skipped files", _format_count(skipped)),
        ("Failed parses", _format_count(failed)),
        ("ETA", _eta_text(eta)),
    ]
    return build_section("Scan progress") + "\n" + build_kv_table(rows)


def _phase_label(phase: str) -> str:
    labels = {
        "discovering_files": "Discovering files",
        "parsing_source_files": "Parsing source files / building graph",
        "building_graph": "Building graph",
    }
    return labels.get(phase, phase.replace("_", " ").strip().title() or "Scanning")


def _format_count(value: int) -> str:
    return f"{value:,}"


def _eta_text(value: str) -> str:
    text = str(value or "").strip()
    return text if text else "estimating..."


def _preview_paths(paths: list[str], limit: int = 5) -> str:
    if not paths:
        return ""

    sample = paths[:limit]
    if len(paths) > limit:
        return ", ".join(sample) + f" (+{len(paths) - limit} more)"

    return ", ".join(sample)


def _print_error(title: str, message: str) -> None:
    print(build_banner())
    print()
    print(build_section(title))
    print(message)
