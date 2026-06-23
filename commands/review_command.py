from __future__ import annotations

import json
from pathlib import Path

from cli_core import (
    DIFF_REPORT_MD_FILE,
)
from diff_engine import compare_graphs, write_diff_report
from gate import evaluate_gate, write_gate_report
from graph import validate_graph
from routes import collect_routes
from scanner import scan_repo
from ui import (
    build_banner,
    build_kv_table,
    build_section,
    format_error,
    format_path,
    format_status,
    format_success,
    format_warning,
)
from verify import verify_diff, write_verification_report
from workflow_config import load_config


def write_review_command(root_path: str) -> int:
    root = Path(root_path)

    if not root.exists():
        _print_error("Review failed", f"path does not exist: {root_path}")
        return 1

    if not root.is_dir():
        _print_error("Review failed", f"path is not a directory: {root_path}")
        return 1

    try:
        config = load_config(root_path)
    except ValueError as error:
        _print_error("Workflow config error", str(error))
        return 1

    latest_snapshot = _load_latest_snapshot(root_path)

    if latest_snapshot is None:
        _print_error(
            "Review failed",
            "No snapshot found. Run `strata snapshot` first.",
        )
        return 1

    snapshot_timestamp, old_graph, old_routes_data = latest_snapshot

    current_graph, graph_error = _load_current_graph(root_path)

    if graph_error is not None:
        _print_error("Review failed", graph_error)
        return 1

    current_routes_data = _load_current_routes_data(current_graph)

    try:
        diff = compare_graphs(
            old_graph,
            current_graph,
            old_routes_data,
            current_routes_data,
        )
        write_diff_report(root_path, diff)
    except (OSError, ValueError) as error:
        _print_error("Review failed", f"Diff failed: {error}")
        return 1

    verify_status = None
    verify_display = format_warning("skipped")

    if config["auto_verify"]:
        try:
            verification_report = verify_diff(diff)
            write_verification_report(root_path, verification_report)
            verify_status = str(verification_report.get("status", "FAIL")).upper()
            verify_display = format_status(verify_status)
        except (OSError, ValueError) as error:
            _print_error("Review failed", f"Verification failed: {error}")
            return 1

    try:
        gate_report = evaluate_gate(current_graph, current_routes_data)
        write_gate_report(root_path, gate_report)
        gate_status = str(gate_report.get("status", "FAIL")).upper()
    except (OSError, ValueError) as error:
        _print_error("Review failed", f"Gate failed: {error}")
        return 1

    review_status = _review_status(verify_status, gate_status)
    next_action = _next_action(review_status, config["auto_verify"])

    print(build_banner())
    print()
    print(build_section("Review complete" if review_status != "FAIL" else "Review failed"))
    print(
        build_kv_table(
            [
                ("Status", format_status(review_status)),
                ("Mode", config["mode"]),
                ("Root", format_path(root_path)),
                ("Snapshot", snapshot_timestamp),
                ("Diff", format_path(DIFF_REPORT_MD_FILE)),
                ("Verify", verify_display),
                ("Gate", format_status(gate_status)),
                ("Next", next_action),
            ]
        )
    )

    return 1 if review_status == "FAIL" else 0


def _load_latest_snapshot(root_path: str):
    snapshots_dir = Path(root_path) / ".aidc" / "snapshots"
    latest_path = snapshots_dir / "latest.txt"

    if not latest_path.exists():
        return None

    try:
        timestamp = latest_path.read_text(encoding="utf-8").strip()
    except OSError:
        return None

    if not timestamp:
        return None

    snapshot_dir = snapshots_dir / timestamp
    graph_path = snapshot_dir / "graph.json"
    routes_path = snapshot_dir / "routes.json"

    if not graph_path.exists():
        return None

    try:
        old_graph = json.loads(graph_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    old_routes_data = _load_routes_data(routes_path)

    return timestamp, old_graph, old_routes_data


def _load_routes_data(routes_path: Path):
    if not routes_path.exists():
        return []

    try:
        routes_data = json.loads(routes_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    if isinstance(routes_data, (dict, list)):
        return routes_data

    return []


def _load_current_graph(root_path: str) -> tuple[dict | None, str | None]:
    try:
        graph = scan_repo(root_path)
    except (OSError, ValueError) as error:
        return None, f"Failed to scan repository: {error}"

    problems = validate_graph(graph)

    if problems:
        return None, "Graph validation failed: " + "; ".join(problems)

    return graph, None


def _load_current_routes_data(graph: dict):
    try:
        return collect_routes(graph)
    except Exception:
        return []


def _review_status(verify_status: str | None, gate_status: str) -> str:
    statuses = [status for status in [verify_status, gate_status] if status]

    if any(status == "FAIL" for status in statuses):
        return "FAIL"

    if any(status == "WARN" for status in statuses):
        return "WARN"

    return "PASS"


def _next_action(review_status: str, auto_verify: bool) -> str:
    if review_status == "FAIL":
        return format_error("Fix the reported issues and rerun `strata review`.")

    if review_status == "WARN":
        return format_warning("Review warnings before commit, then rerun if needed.")

    if not auto_verify:
        return format_warning("Verify was skipped by config. Run `strata verify` if needed.")

    return format_success("Safe to review generated reports and commit if expected.")


def _print_error(title: str, message: str) -> None:
    print(build_banner())
    print()
    print(build_section(title))
    print(format_error(message))
