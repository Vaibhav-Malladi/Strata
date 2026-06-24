from pathlib import Path

SNAPSHOT_LATEST_FILE = ".aidc/snapshots/latest.txt"
SNAPSHOT_CACHE_FILE = ".aidc/cache/repo_snapshot.json"

GENERATED_FILES = [
    ".aidc/graph.json",
    ".aidc/project_map.md",
    ".aidc/task_brief.md",
    ".aidc/preflight.md",
    ".aidc/context_pack.md",
    ".aidc/agent_prompt.md",
    ".aidc/routes.md",
    ".aidc/routes.json",
    ".aidc/diff_report.md",
    ".aidc/diff_report.json",
    ".aidc/verification_report.md",
    ".aidc/verification_report.json",
    ".aidc/gate_report.md",
    ".aidc/gate_report.json",
    SNAPSHOT_LATEST_FILE,
    SNAPSHOT_CACHE_FILE,
]


IGNORED_DIRS = {
    ".git",
    ".cache",
    ".mypy_cache",
    ".nox",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "build",
    "coverage",
    "dist",
    "htmlcov",
    "node_modules",
    "venv",
    "__pycache__",
    ".aidc",
}


def analyze_status(root: str = ".") -> dict:
    root_path = Path(root)
    generated = _analyze_generated_files(root_path)
    newest_source = _newest_source_mtime(root_path)

    missing = [
        item["path"]
        for item in generated
        if not item["exists"]
    ]

    stale = [
        item["path"]
        for item in generated
        if item["exists"]
        and newest_source is not None
        and item["modified_time"] is not None
        and item["modified_time"] < newest_source
    ]

    if missing:
        state = "incomplete"
    elif stale:
        state = "stale"
    else:
        state = "current"

    return {
        "root": str(root_path),
        "state": state,
        "generated_files": generated,
        "missing_files": missing,
        "stale_files": stale,
        "newest_source_mtime": newest_source,
    }


def format_status_report(status: dict) -> str:
    lines = [
        "# Strata Status",
        "",
        f"Root: `{status.get('root', '.')}`",
        f"State: **{status.get('state', 'unknown')}**",
        "",
        "## Generated Files",
        "",
    ]

    for item in status.get("generated_files", []):
        path = item.get("path", "<unknown>")

        if not item.get("exists"):
            lines.append(f"- Missing: `{path}`")
            continue

        if path in status.get("stale_files", []):
            lines.append(f"- Stale: `{path}`")
        else:
            lines.append(f"- Present: `{path}`")

    lines.append("")

    missing = status.get("missing_files", [])
    stale = status.get("stale_files", [])

    if missing:
        lines.extend(
            [
                "## Missing Outputs",
                "",
            ]
        )
        for path in missing:
            lines.append(f"- `{path}`")
        lines.append("")

    if stale:
        lines.extend(
            [
                "## Possibly Stale Outputs",
                "",
                "These generated files are older than at least one source file.",
                "",
            ]
        )
        for path in stale:
            lines.append(f"- `{path}`")
        lines.append("")

    lines.extend(_format_recommended_actions(status))

    return "\n".join(lines).rstrip() + "\n"


def _format_recommended_actions(status: dict) -> list[str]:
    state = status.get("state")

    lines = [
        "## Recommended Actions",
        "",
    ]

    if state == "current":
        lines.append("- Generated Strata outputs look current.")
        return lines

    if state == "incomplete":
        lines.append("- Run `strata scan` to regenerate `.aidc/graph.json`.")
        lines.append("- Run `strata map` if you need a project map.")
        lines.append("- Run `strata routes` if you need a backend route map.")
        lines.append("- Run `strata snapshot` to save a baseline for diff and verify.")
        lines.append("- Run `strata diff` to review changes against the latest snapshot.")
        lines.append("- Run `strata verify` to validate current structure against the latest snapshot.")
        lines.append("- Run `strata gate` for a snapshot-free readiness check.")
        lines.append("- Run `strata preflight \"task\"` before an AI edit.")
        lines.append("- Run `strata agent-prompt \"task\" local` if you need an agent-ready prompt.")
        return lines

    if state == "stale":
        lines.append("- Run `strata scan` to refresh the graph.")
        lines.append("- Regenerate any stale reports you need.")
        lines.append("- Run `strata snapshot` if the repository structure changed intentionally.")
        lines.append("- Run `strata diff` and `strata verify` to review the new baseline.")
        lines.append("- Run `strata gate` if you just need a readiness check.")
        lines.append("- Run `strata preflight \"task\"` before continuing AI-assisted edits.")
        return lines

    lines.append("- Run `strata scan` to refresh Strata outputs.")
    return lines


def _analyze_generated_files(root_path: Path) -> list[dict]:
    results = []

    for relative_path in GENERATED_FILES:
        path = root_path / relative_path
        exists = path.exists()

        results.append(
            {
                "path": relative_path,
                "exists": exists,
                "modified_time": path.stat().st_mtime if exists else None,
            }
        )

    return results


def _newest_source_mtime(root_path: Path) -> float | None:
    newest = None

    for path in root_path.rglob("*.py"):
        if _is_ignored(path, root_path):
            continue

        modified_time = path.stat().st_mtime

        if newest is None or modified_time > newest:
            newest = modified_time

    return newest


def _is_ignored(path: Path, root_path: Path) -> bool:
    try:
        relative_parts = path.relative_to(root_path).parts
    except ValueError:
        return True

    return any(part in IGNORED_DIRS for part in relative_parts)
