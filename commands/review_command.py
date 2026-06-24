from __future__ import annotations

import json
from pathlib import Path

from cli_core import DIFF_REPORT_MD_FILE
from commands.apply_command import inspect_apply_state
from diff_engine import compare_graphs, write_diff_report
from direct_edit import DIRECT_EDIT_REPORT_PATH
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
    print_command_header,
    print_status_card,
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

    patch_state = inspect_apply_state(root_path)
    patch_summary = patch_state["patch_summary"]
    validation = patch_state["validation"]
    patch_ready = bool(validation and validation.get("valid"))
    latest_snapshot = _load_latest_snapshot(root_path)
    snapshot_timestamp = "-"
    diff_display = "skipped"
    verify_display = format_warning("skipped")
    gate_status = "FAIL"
    review_status = "FAIL"
    next_action = ""

    _print_patch_review(patch_summary, validation)
    _print_direct_edit_report(root_path)

    if latest_snapshot is not None:
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
        diff_display = format_path(DIFF_REPORT_MD_FILE)
    elif patch_ready:
        current_graph, graph_error = _load_current_graph(root_path)

        if graph_error is not None:
            _print_error("Review failed", graph_error)
            return 1

        current_routes_data = _load_current_routes_data(current_graph)

        try:
            gate_report = evaluate_gate(current_graph, current_routes_data)
            write_gate_report(root_path, gate_report)
            gate_status = str(gate_report.get("status", "FAIL")).upper()
        except (OSError, ValueError) as error:
            _print_error("Review failed", f"Gate failed: {error}")
            return 1

        review_status = gate_status
        next_action = _patch_only_next_action(review_status)
    else:
        _print_error(
            "Review failed",
            'No AI patch found. Run `strata ask "your task"` first. No snapshot found. Run `strata snapshot` first.',
        )
        return 1

    print()
    print(build_section("Review complete" if review_status != "FAIL" else "Review failed"))
    print(
        build_kv_table(
            [
                ("Status", format_status(review_status)),
                ("Mode", config["mode"]),
                ("Root", format_path(root_path)),
                ("Snapshot", snapshot_timestamp),
                ("Diff", diff_display),
                ("Verify", verify_display),
                ("Gate", format_status(gate_status)),
                ("Patch", _display_validation_status(_patch_status(patch_summary, validation))),
                ("Dry-run", _display_validation_status(_dry_run_status(validation, patch_summary))),
                ("Safe to proceed", _safe_to_proceed(review_status, patch_ready)),
                ("Next", next_action),
            ]
        )
    )

    if latest_snapshot is None and not patch_ready:
        return 1

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
        return "Fix: Fix the reported issues and rerun `strata review`."

    if review_status == "WARN":
        return "Fix: Review warnings before commit, then rerun if needed."

    if not auto_verify:
        return "Next: Verify was skipped by config. Run `strata verify` if needed."

    return "Next: Safe to review generated reports and commit if expected."


def _patch_only_next_action(review_status: str) -> str:
    if review_status == "FAIL":
        return "Fix: Fix the reported issues and rerun `strata ask`."

    if review_status == "WARN":
        return "Fix: Review warnings before applying the patch."

    return "Next: Run `strata apply` when you are ready."


def _patch_status(patch_summary: dict, validation: dict | None) -> str:
    if validation is not None:
        return _dry_run_status(validation, patch_summary)

    return str(patch_summary.get("status", "missing")).lower()


def _dry_run_status(validation: dict | None, patch_summary: dict) -> str:
    if validation is not None:
        return str(validation.get("status", "invalid")).lower()

    return str(patch_summary.get("status", "missing")).lower()


def _safe_to_proceed(review_status: str, patch_ready: bool) -> str:
    if not patch_ready:
        return "no"

    if review_status == "FAIL":
        return "no"

    if review_status == "WARN":
        return "caution"

    return "yes"


def _build_patch_rows(patch_summary: dict, validation: dict | None, patch_ready: bool) -> list[tuple[str, object]]:
    patch_status = str(patch_summary.get("status", "missing")).lower()
    validation_status = str(validation.get("status", patch_status)).lower() if validation is not None else patch_status
    targets = validation.get("targets", []) if validation is not None else []
    rows = [
        ("Patch", format_path(patch_summary.get("patch_path", ".aidc/agent_patch.diff"))),
        ("Exists", "yes" if patch_summary.get("exists") else "no"),
        ("Size", f"{int(patch_summary.get('size', 0) or 0)} bytes"),
        ("Validation", _display_validation_status(validation_status)),
        ("Targets", ", ".join(str(target) for target in targets) if targets else "-"),
        ("Dry-run", _display_validation_status(validation_status)),
        ("Safe", "yes" if patch_ready else "no"),
    ]

    if validation is not None and validation.get("errors"):
        rows.append(("Errors", "; ".join(str(error) for error in validation.get("errors", []))))

    if validation is not None and validation.get("warnings"):
        rows.append(("Warnings", "; ".join(str(warning) for warning in validation.get("warnings", []))))

    return rows


def _display_validation_status(status: str) -> str:
    normalized = str(status).lower()

    if normalized == "valid":
        return format_success("valid")

    if normalized == "invalid":
        return format_error("invalid")

    if normalized == "empty":
        return format_warning("empty")

    if normalized == "missing":
        return format_warning("missing")

    return format_warning(normalized or "-")


def _print_patch_review(patch_summary: dict, validation: dict | None) -> None:
    patch_status = str(patch_summary.get("status", "missing")).lower()
    validation_status = str(validation.get("status", patch_status)).lower() if validation is not None else patch_status
    targets = validation.get("targets", []) if validation is not None else []
    next_label = "Next" if validation is not None and validation.get("valid") else "Fix"
    next_step = "Run `strata apply`." if validation is not None and validation.get("valid") else 'Run `strata ask "your task"` first.'

    print(build_banner())
    print()
    print_command_header("Review", "Patch-first review before apply", mode="compact")
    print_status_card(
        "Patch review",
        [
            ("Patch", format_path(patch_summary.get("patch_path", ".aidc/agent_patch.diff"))),
            ("Exists", "yes" if patch_summary.get("exists") else "no"),
            ("Size", f"{int(patch_summary.get('size', 0) or 0)} bytes"),
            ("Validation", _display_validation_status(validation_status)),
            ("Targets", ", ".join(str(target) for target in targets) if targets else "-"),
            ("Dry-run", _display_validation_status(validation_status)),
            (next_label, next_step),
        ],
        status=_patch_status(patch_summary, validation),
    )
    if patch_status == "missing":
        print()
        print(format_warning('No AI patch found. Run `strata ask "your task"` first.'))


def _print_direct_edit_report(root_path: str) -> None:
    report_path = Path(root_path) / DIRECT_EDIT_REPORT_PATH
    if not report_path.exists():
        return

    print()
    print(build_section("Direct edit report found"))
    print(
        build_kv_table(
            [
                ("Report", format_path(report_path)),
                ("Next", "Inspect `git diff`, then run your project tests."),
            ]
        )
    )


def _print_error(title: str, message: str) -> None:
    print(build_banner())
    print()
    print(build_section(title))
    print(format_error(message))
