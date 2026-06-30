from __future__ import annotations

import json
from pathlib import Path

from strata.utils.secrets import redact_text


def verify_diff(diff: dict) -> dict:
    """Evaluate a structural diff and return a repo-safety verification report."""

    recommended_commands = [
        "py tests.py",
        "py tests\\run.py",
    ]

    if not isinstance(diff, dict):
        return _build_report(
            status="FAIL",
            summary={},
            failures=["Diff must be a dictionary."],
            warnings=[],
            improvements=[],
            recommended_commands=recommended_commands,
        )

    summary = diff.get("summary")

    if not isinstance(summary, dict):
        summary = {}

    summary = dict(summary)

    failures = []
    warnings = []
    improvements = []

    unresolved_imports_added = _count(summary, "unresolved_imports_added")
    graph_error_count = _count(summary, "graph_error_count")

    if unresolved_imports_added > 0:
        failures.append(
            f"Unresolved imports added: {unresolved_imports_added}."
        )

    if graph_error_count > 0:
        failures.append(f"Graph errors detected: {graph_error_count}.")

    warning_fields = [
        ("files_removed", "Files removed"),
        ("routes_added", "Routes added"),
        ("routes_removed", "Routes removed"),
        ("edges_added", "Edges added"),
        ("edges_removed", "Edges removed"),
        ("symbols_removed", "Symbols removed"),
        ("files_added", "Files added"),
        ("symbols_added", "Symbols added"),
    ]

    for key, label in warning_fields:
        count = _count(summary, key)

        if count > 0:
            warnings.append(f"{label}: {count}.")

    unresolved_imports_removed = _count(summary, "unresolved_imports_removed")

    if unresolved_imports_removed > 0:
        improvements.append(
            f"Unresolved imports removed: {unresolved_imports_removed}."
        )

    if failures:
        status = "FAIL"
    elif warnings:
        status = "WARN"
    else:
        status = "PASS"

    return _build_report(
        status=status,
        summary=summary,
        failures=failures,
        warnings=warnings,
        improvements=improvements,
        recommended_commands=recommended_commands,
    )


def build_verification_markdown(report: dict) -> str:
    """Build a compact Markdown verification report."""

    if not isinstance(report, dict):
        report = _build_report(
            status="FAIL",
            summary={},
            failures=["Verification report must be a dictionary."],
            warnings=[],
            improvements=[],
            recommended_commands=["py tests.py", "py tests\\run.py"],
        )

    status = str(report.get("status", "FAIL")).upper()
    summary = report.get("summary", {})
    failures = _as_strings(report.get("failures", []))
    warnings = _as_strings(report.get("warnings", []))
    improvements = _as_strings(report.get("improvements", []))
    recommended_commands = _as_strings(report.get("recommended_commands", []))

    lines = [
        "# Strata Verification Report",
        "",
        "## Status",
        "",
        f"- `{status}`",
        "",
        "## Failures",
        "",
        _render_items(failures),
        "",
        "## Warnings",
        "",
        _render_items(warnings),
        "",
        "## Improvements",
        "",
        _render_items(improvements),
        "",
        "## Summary",
        "",
        _render_summary(summary),
        "",
        "## Recommended Verification",
        "",
        _render_commands(recommended_commands),
    ]

    if failures or warnings:
        lines.extend(
            [
                "",
                "Note: run tests before commit because warnings or failures were found.",
            ]
        )

    return redact_text("\n".join(lines))


def write_verification_report(root: str | Path, report: dict) -> dict:
    """Write verification JSON and Markdown reports under .aidc."""

    root_path = Path(root)
    output_dir = root_path / ".aidc"
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / "verification_report.json"
    markdown_path = output_dir / "verification_report.md"

    json_path.write_text(
        redact_text(json.dumps(report, indent=2, sort_keys=True)),
        encoding="utf-8",
    )
    markdown_path.write_text(redact_text(build_verification_markdown(report)), encoding="utf-8")

    return {
        "root": str(root_path),
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
    }


def _build_report(
    *,
    status: str,
    summary: dict,
    failures: list[str],
    warnings: list[str],
    improvements: list[str],
    recommended_commands: list[str],
) -> dict:
    return {
        "status": status,
        "summary": summary,
        "failures": failures,
        "warnings": warnings,
        "improvements": improvements,
        "recommended_commands": recommended_commands,
    }


def _count(summary: dict, key: str) -> int:
    value = summary.get(key, 0)

    if isinstance(value, bool):
        return int(value)

    if isinstance(value, (int, float)):
        return int(value)

    return 0


def _as_strings(values: object) -> list[str]:
    if not isinstance(values, list):
        return []

    return [str(value) for value in values]


def _render_items(values: list[str]) -> str:
    if not values:
        return "None."

    return "\n".join(f"- {value}" for value in values)


def _render_summary(summary: object) -> str:
    if not isinstance(summary, dict) or not summary:
        return "None."

    lines = []

    for key in sorted(summary):
        lines.append(f"- {key}: `{summary[key]}`")

    return "\n".join(lines)


def _render_commands(commands: list[str]) -> str:
    if not commands:
        return "None."

    return "\n".join(f"- `{command}`" for command in commands)
