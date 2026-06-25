from __future__ import annotations

from context_matching import extract_task_terms


VERIFICATION_COMMAND_LIMIT = 8
STRATA_DEFAULT_COMMANDS = ("py tests.py", "py tests\\run.py", "strata gate")


def collect_verification_commands(
    graph: dict,
    task: str,
    relevant_entries: list[dict],
    javascript_project_hints: dict | None,
    *,
    suggest_tests_for_file=None,
) -> list[str]:
    """Return commands that are known to exist for the detected project."""

    project = javascript_project_hints or {}
    scripts = {
        str(item.get("name", "")).strip()
        for item in project.get("scripts", []) or []
        if isinstance(item, dict)
    }
    if project.get("package_path"):
        manager = str(project.get("package_manager") or "npm").lower()
        commands = []
        for script in ("test", "lint", "typecheck", "build"):
            if script in scripts:
                commands.append(_script_command(manager, script))
        if "e2e" in scripts and _e2e_relevant(task):
            commands.append(_script_command(manager, "e2e"))
        return _dedupe(commands)[:VERIFICATION_COMMAND_LIMIT]

    commands = []
    if suggest_tests_for_file is not None:
        for entry in relevant_entries:
            path = str((entry.get("file") or {}).get("path", "")).strip()
            if not path:
                continue
            suggestions = suggest_tests_for_file(graph, path)
            commands.extend(suggestions.get("recommended_commands", []) or [])

    commands.extend(STRATA_DEFAULT_COMMANDS)
    return _dedupe(commands)[:VERIFICATION_COMMAND_LIMIT]


def build_verification_plan_section(commands: list[str] | None) -> list[str]:
    commands = list(commands or [])
    lines = ["## Verification Plan", ""]
    if commands:
        lines.extend(f"- `{command}`" for command in commands)
    else:
        lines.append("- none identified")
    lines.append("")
    return lines


def _script_command(manager: str, script: str) -> str:
    if manager == "npm":
        return "npm test" if script == "test" else f"npm run {script}"
    if manager in {"pnpm", "yarn"}:
        return f"{manager} {script}"
    if manager == "bun":
        return "bun test" if script == "test" else f"bun run {script}"
    return "npm test" if script == "test" else f"npm run {script}"


def _e2e_relevant(task: str) -> bool:
    terms = set(extract_task_terms(task))
    return bool(terms & {"e2e", "end", "integration", "browser", "playwright", "cypress"})


def _dedupe(values: list[str] | tuple[str, ...]) -> list[str]:
    result = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
