from __future__ import annotations

import json
from pathlib import Path

from graph import validate_graph


RECOMMENDED_COMMANDS = [
    "py tests.py",
    "py tests\\run.py",
]


def evaluate_gate(graph: dict, routes_data: dict | list | None = None) -> dict:
    """Evaluate whether the current repository state is safe enough to commit."""

    graph_data = graph if isinstance(graph, dict) else {}
    failures = []
    warnings = []

    validation_problems = validate_graph(graph_data)
    failures.extend(validation_problems)

    files = graph_data.get("files") if isinstance(graph_data.get("files"), list) else []
    edges = graph_data.get("edges") if isinstance(graph_data.get("edges"), list) else []

    summary = {
        "file_count": _count_source_files(files),
        "edge_count": _count_edges(edges),
        "unresolved_import_count": _count_unresolved_imports(files),
        "error_count": _count_file_errors(files),
        "route_count": 0,
        "duplicate_route_warning_count": 0,
        "route_import_risk_count": 0,
    }

    if summary["error_count"] > 0:
        failures.append("graph contains file syntax/error fields")

    if summary["unresolved_import_count"] > 0:
        failures.append(
            f"graph has {summary['unresolved_import_count']} unresolved imports"
        )

    if not failures:
        if summary["file_count"] == 0:
            warnings.append("graph has no source files")

        route_summary = _summarize_routes_data(routes_data)
        summary["route_count"] = route_summary["route_count"]
        summary["duplicate_route_warning_count"] = route_summary[
            "duplicate_route_warning_count"
        ]
        summary["route_import_risk_count"] = route_summary["route_import_risk_count"]

        if route_summary["missing_or_malformed"]:
            warnings.append("routes_data is missing or malformed")

        if summary["duplicate_route_warning_count"] > 0:
            warnings.append(
                "duplicate route warnings found: "
                f"{summary['duplicate_route_warning_count']}"
            )

        if summary["route_import_risk_count"] > 0:
            warnings.append(
                "route import risks found: "
                f"{summary['route_import_risk_count']}"
            )

        cycle_count = _extract_cycle_count(graph_data.get("summary"))

        if cycle_count > 0:
            warnings.append(f"dependency cycles found: {cycle_count}")

    status = _status_from_findings(failures, warnings)

    return {
        "status": status,
        "failures": failures,
        "warnings": warnings,
        "summary": summary,
        "recommended_commands": list(RECOMMENDED_COMMANDS),
    }


def build_gate_markdown(report: dict) -> str:
    """Build a compact Markdown gate report."""

    report_data = report if isinstance(report, dict) else {}
    summary = report_data.get("summary") if isinstance(report_data.get("summary"), dict) else {}
    failures = report_data.get("failures") if isinstance(report_data.get("failures"), list) else []
    warnings = report_data.get("warnings") if isinstance(report_data.get("warnings"), list) else []
    commands = report_data.get("recommended_commands")
    if not isinstance(commands, list) or not commands:
        commands = list(RECOMMENDED_COMMANDS)

    lines = [
        "# Strata Gate Report",
        "",
        "## Status",
        "",
        f"- `{report_data.get('status', 'FAIL')}`",
    ]

    if report_data.get("status") in {"FAIL", "WARN"}:
        lines.append("- Run recommended verification before commit.")

    lines.extend(
        [
            "",
            "## Failures",
            "",
            *_format_markdown_items(failures),
            "",
            "## Warnings",
            "",
            *_format_markdown_items(warnings),
            "",
            "## Summary",
            "",
            f"- File count: `{summary.get('file_count', 0)}`",
            f"- Edge count: `{summary.get('edge_count', 0)}`",
            f"- Unresolved import count: `{summary.get('unresolved_import_count', 0)}`",
            f"- Error count: `{summary.get('error_count', 0)}`",
            f"- Route count: `{summary.get('route_count', 0)}`",
            f"- Duplicate route warning count: `{summary.get('duplicate_route_warning_count', 0)}`",
            f"- Route import risk count: `{summary.get('route_import_risk_count', 0)}`",
            "",
            "## Recommended Verification",
            "",
            *[f"- `{command}`" for command in commands],
        ]
    )

    return "\n".join(lines)


def write_gate_report(root: str | Path, report: dict) -> dict:
    """Write the gate report JSON and Markdown files under .aidc."""

    root_path = Path(root)
    aidc_dir = root_path / ".aidc"
    json_path = aidc_dir / "gate_report.json"
    markdown_path = aidc_dir / "gate_report.md"

    aidc_dir.mkdir(parents=True, exist_ok=True)

    payload = report if isinstance(report, dict) else {}

    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    markdown_path.write_text(build_gate_markdown(payload), encoding="utf-8")

    return {
        "root": str(root_path),
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
    }


def _status_from_findings(failures: list[str], warnings: list[str]) -> str:
    if failures:
        return "FAIL"

    if warnings:
        return "WARN"

    return "PASS"


def _count_source_files(files: list) -> int:
    count = 0

    for file_info in files:
        if not isinstance(file_info, dict):
            continue

        if file_info.get("path"):
            count += 1

    return count


def _count_edges(edges: list) -> int:
    count = 0

    for edge in edges:
        if not isinstance(edge, dict):
            continue

        if edge.get("from") and edge.get("to"):
            count += 1

    return count


def _count_unresolved_imports(files: list) -> int:
    count = 0

    for file_info in files:
        if not isinstance(file_info, dict):
            continue

        if "unresolved_imports" in file_info:
            unresolved_imports = file_info.get("unresolved_imports", [])

            if isinstance(unresolved_imports, list):
                count += len(unresolved_imports)
            elif unresolved_imports:
                count += 1

        elif "unresolved_import_details" in file_info:
            unresolved_details = file_info.get("unresolved_import_details", [])

            if isinstance(unresolved_details, list):
                count += len(unresolved_details)
            elif unresolved_details:
                count += 1

    return count


def _count_file_errors(files: list) -> int:
    count = 0

    for file_info in files:
        if not isinstance(file_info, dict):
            continue

        if _file_has_error_fields(file_info):
            count += 1

    return count


def _file_has_error_fields(file_info: dict) -> bool:
    for key in ("error", "errors", "syntax_error", "syntax_errors"):
        if key not in file_info:
            continue

        value = file_info.get(key)

        if isinstance(value, list):
            if value:
                return True
        elif value:
            return True

    return False


def _summarize_routes_data(routes_data: dict | list | None) -> dict:
    summary = {
        "route_count": 0,
        "duplicate_route_warning_count": 0,
        "route_import_risk_count": 0,
        "missing_or_malformed": False,
    }

    if routes_data is None:
        summary["missing_or_malformed"] = True
        return summary

    if isinstance(routes_data, list):
        if not all(isinstance(item, dict) for item in routes_data):
            summary["missing_or_malformed"] = True
            return summary

        summary["route_count"] = len(routes_data)
        summary["duplicate_route_warning_count"] = _count_duplicate_routes(routes_data)
        return summary

    if isinstance(routes_data, dict):
        recognized = False

        routes = routes_data.get("routes")
        if "routes" in routes_data:
            recognized = True

            if isinstance(routes, list) and all(isinstance(item, dict) for item in routes):
                summary["route_count"] = len(routes)
                summary["duplicate_route_warning_count"] = _count_duplicate_routes(routes)
            elif routes is not None:
                summary["missing_or_malformed"] = True
                return summary

        route_count = _safe_int(routes_data.get("route_count"))
        if route_count is not None:
            recognized = True
            summary["route_count"] = route_count

        duplicate_count = _count_summary_or_list(routes_data, (
            "duplicate_route_warning_count",
            "duplicate_routes",
            "duplicate_route_warnings",
        ))
        if duplicate_count is not None:
            recognized = True
            summary["duplicate_route_warning_count"] = duplicate_count

        risk_count = _count_summary_or_list(routes_data, (
            "route_import_risk_count",
            "route_import_risks",
            "import_risks",
        ))
        if risk_count is not None:
            recognized = True
            summary["route_import_risk_count"] = risk_count

        if not recognized:
            summary["missing_or_malformed"] = True

        return summary

    summary["missing_or_malformed"] = True
    return summary


def _count_duplicate_routes(routes: list[dict]) -> int:
    grouped = {}

    for route in routes:
        method = str(route.get("method", ""))
        path = str(route.get("path", ""))
        key = (method, path)
        grouped[key] = grouped.get(key, 0) + 1

    duplicates = 0

    for count in grouped.values():
        if count > 1:
            duplicates += 1

    return duplicates


def _count_summary_or_list(data: dict, keys: tuple[str, ...]) -> int | None:
    for key in keys:
        if key not in data:
            continue

        value = data.get(key)

        if isinstance(value, list):
            return len(value)

        if isinstance(value, int):
            return value

        return None

    return None


def _safe_int(value) -> int | None:
    if isinstance(value, int):
        return value

    return None


def _extract_cycle_count(summary: dict | None) -> int:
    if not isinstance(summary, dict):
        return 0

    cycle_count = summary.get("cycle_count")
    if isinstance(cycle_count, int):
        return cycle_count

    cycles = summary.get("cycles")
    if isinstance(cycles, list):
        return len(cycles)

    return 0


def _format_markdown_items(items: list[str]) -> list[str]:
    if not items:
        return ["None."]

    return [f"- {item}" for item in items]
