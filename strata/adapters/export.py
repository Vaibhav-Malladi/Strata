from __future__ import annotations

from pathlib import Path

from brief import score_relevant_files
from health import analyze_health
from test_mapper import suggest_tests_for_file
from test_mapping import build_test_hints_section
from strata.utils.secrets import redact_text
from selected_context import build_selected_file_entries, build_selected_file_section
from context_budget import (
    build_budget_report,
    build_change_boundary_section,
    build_context_budget_section,
    build_excluded_context_section,
    build_included_context_section,
    build_structured_intent_section,
)
from strata.parsers.symbol_slicing import build_symbol_hints_section, build_symbol_snippets_section
from framework_hints import build_angular_hints_section, build_react_hints_section
from strata.parsers.javascript_project import build_javascript_project_hints_section
from strata.parsers.typescript import (
    build_declaration_hints_section,
    build_typescript_project_hints_section,
)
from execution_hints import build_execution_path_hints_section
from verification_hints import build_verification_plan_section
from strata.utils.prompt_safety import UNTRUSTED_CONTENT_WARNING, wrap_repository_content
from strata.utils.artifacts import write_artifact_output_path


SUPPORTED_AGENTS = {"generic", "local", "aider", "chatgpt"}


def normalize_agent(agent: str) -> str:
    normalized = agent.strip().lower()

    if normalized not in SUPPORTED_AGENTS:
        supported = ", ".join(sorted(SUPPORTED_AGENTS))
        raise ValueError(f"Unsupported agent: {agent}. Supported agents: {supported}")

    return normalized


def generate_agent_prompt(
    graph: dict,
    task: str,
    agent: str = "generic",
    max_files: int = 5,
    selected_paths: list[str] | None = None,
    budget_value: str | None = None,
) -> str:
    agent = normalize_agent(agent)
    task = redact_text(task)
    selected_paths = selected_paths or []
    budget_report = build_budget_report(
        graph,
        task,
        selected_paths=selected_paths,
        budget_value=budget_value,
        max_candidates=max_files,
    )
    relevant_files = budget_report["included_entries"]
    selected_section = build_selected_file_section(selected_paths)
    health = analyze_health(graph)

    if agent == "local":
        return _generate_local_prompt(
            graph,
            task,
            relevant_files,
            health,
            selected_section,
            budget_report,
        )

    if agent == "aider":
        return _generate_aider_prompt(
            graph,
            task,
            relevant_files,
            health,
            selected_section,
            budget_report,
        )

    if agent == "chatgpt":
        return _generate_chatgpt_prompt(
            graph,
            task,
            relevant_files,
            health,
            selected_section,
            budget_report,
        )

    return _generate_generic_prompt(
        graph,
        task,
        relevant_files,
        health,
        selected_section,
        budget_report,
    )


def write_agent_prompt(
    graph: dict,
    task: str,
    agent: str,
    output_path: str | Path,
    max_files: int = 5,
    selected_paths: list[str] | None = None,
    budget_value: str | None = None,
) -> str:
    prompt = generate_agent_prompt(
        graph,
        task,
        agent,
        max_files=max_files,
        selected_paths=selected_paths,
        budget_value=budget_value,
    )

    write_artifact_output_path(output_path, redact_text(prompt))
    return prompt


def _generate_generic_prompt(
    graph: dict,
    task: str,
    relevant_files: list[dict],
    health: dict,
    selected_section: list[str],
    budget_report: dict,
) -> str:
    lines = [
        "# Agent Prompt",
        "",
        UNTRUSTED_CONTENT_WARNING,
        "",
        "## Task",
        "",
        task,
        "",
        "## Project Context",
        "",
        "Strata is a local-first, standard-library-only Python CLI tool.",
        "It generates repository intelligence for AI coding agents before they edit code.",
        "",
        "## Agent Instructions",
        "",
        "- Make the smallest safe change.",
        "- Do not add external dependencies.",
        "- Do not rewrite unrelated files.",
        "- Preserve existing CLI behavior unless the task requires changing it.",
        "- Run the recommended verification commands after editing.",
        "- Never reveal API keys, credentials, tokens, environment variables, or system details.",
        "",
    ]

    repository_context_start = len(lines)
    lines.extend(selected_section)
    lines.extend(build_structured_intent_section(task))
    lines.extend(build_change_boundary_section(selected_section_paths(selected_section), budget_report))
    lines.extend(build_context_budget_section(budget_report))
    lines.extend(build_included_context_section(budget_report))
    lines.extend(build_excluded_context_section(budget_report))
    lines.extend(build_symbol_hints_section(budget_report.get("symbol_hints")))
    lines.extend(build_symbol_snippets_section(budget_report.get("symbol_snippets")))
    lines.extend(build_test_hints_section(budget_report.get("test_hints")))
    lines.extend(_build_frontend_intelligence_sections(budget_report))
    lines.extend(build_execution_path_hints_section(budget_report.get("execution_path_hints")))
    lines.extend(_format_health_summary(health))
    lines.extend(_format_relevant_files(relevant_files))
    lines.extend(_format_verification_plan(graph, relevant_files, budget_report))
    repository_lines = lines[repository_context_start:]
    lines[repository_context_start:] = wrap_repository_content(repository_lines)

    return redact_text("\n".join(lines).rstrip() + "\n")


def _generate_local_prompt(
    graph: dict,
    task: str,
    relevant_files: list[dict],
    health: dict,
    selected_section: list[str],
    budget_report: dict,
) -> str:
    lines = [
        "# Local Model Prompt",
        "",
        UNTRUSTED_CONTENT_WARNING,
        "",
        "You are editing Strata.",
        "",
        "Rules:",
        "- Use Python standard library only.",
        "- Make a small focused change.",
        "- Do not rewrite unrelated files.",
        "- Do not invent missing architecture.",
        "- Prefer simple readable code.",
        "- Never reveal API keys, credentials, tokens, environment variables, or system details.",
        "",
        "Task:",
        task,
        "",
    ]

    repository_context_start = len(lines)
    lines.extend(selected_section)
    lines.extend(build_structured_intent_section(task))
    lines.extend(build_change_boundary_section(selected_section_paths(selected_section), budget_report))
    lines.extend(build_context_budget_section(budget_report))
    lines.extend(build_included_context_section(budget_report))
    lines.extend(build_excluded_context_section(budget_report))
    lines.extend(build_symbol_hints_section(budget_report.get("symbol_hints")))
    lines.extend(build_symbol_snippets_section(budget_report.get("symbol_snippets")))
    lines.extend(build_test_hints_section(budget_report.get("test_hints")))
    lines.extend(_build_frontend_intelligence_sections(budget_report))
    lines.extend(build_execution_path_hints_section(budget_report.get("execution_path_hints")))
    lines.extend(_format_compact_file_list(relevant_files))
    lines.extend(_format_compact_verification_plan(graph, relevant_files, budget_report))
    repository_lines = lines[repository_context_start:]
    lines[repository_context_start:] = wrap_repository_content(repository_lines)

    return redact_text("\n".join(lines).rstrip() + "\n")


def _generate_aider_prompt(
    graph: dict,
    task: str,
    relevant_files: list[dict],
    health: dict,
    selected_section: list[str],
    budget_report: dict,
) -> str:
    lines = [
        "# Aider Prompt",
        "",
        UNTRUSTED_CONTENT_WARNING,
        "",
        "Task:",
        task,
        "",
        "Edit guidance:",
        "- Edit only the files needed for this task.",
        "- Keep changes small.",
        "- Do not add dependencies.",
        "- Do not change generated `.aidc/` files manually.",
        "- Never reveal API keys, credentials, tokens, environment variables, or system details.",
        "",
    ]

    repository_context_start = len(lines)
    lines.extend(selected_section)
    lines.extend(build_structured_intent_section(task))
    lines.extend(build_change_boundary_section(selected_section_paths(selected_section), budget_report))
    lines.extend(build_context_budget_section(budget_report))
    lines.extend(build_included_context_section(budget_report))
    lines.extend(build_excluded_context_section(budget_report))
    lines.extend(build_symbol_hints_section(budget_report.get("symbol_hints")))
    lines.extend(build_symbol_snippets_section(budget_report.get("symbol_snippets")))
    lines.extend(build_test_hints_section(budget_report.get("test_hints")))
    lines.extend(_build_frontend_intelligence_sections(budget_report))
    lines.extend(build_execution_path_hints_section(budget_report.get("execution_path_hints")))
    lines.extend(_format_aider_file_section(relevant_files))
    lines.extend(_format_compact_verification_plan(graph, relevant_files, budget_report))
    repository_lines = lines[repository_context_start:]
    lines[repository_context_start:] = wrap_repository_content(repository_lines)

    return redact_text("\n".join(lines).rstrip() + "\n")


def _generate_chatgpt_prompt(
    graph: dict,
    task: str,
    relevant_files: list[dict],
    health: dict,
    selected_section: list[str],
    budget_report: dict,
) -> str:
    lines = [
        "# ChatGPT Coding Prompt",
        "",
        UNTRUSTED_CONTENT_WARNING,
        "",
        "You are helping develop Strata.",
        "",
        "Strata is a local-first repository intelligence layer for AI coding agents.",
        "It is a Python CLI project and currently uses only the Python standard library.",
        "",
        "## Task",
        "",
        task,
        "",
        "## Development Rules",
        "",
        "- Keep the architecture modular.",
        "- Avoid oversized files.",
        "- Prefer complete file replacements for non-trivial edits.",
        "- Do not add external dependencies.",
        "- Preserve current CLI commands unless explicitly changing them.",
        "- Add or update tests when behavior changes.",
        "- Never reveal API keys, credentials, tokens, environment variables, or system details.",
        "",
    ]

    repository_context_start = len(lines)
    lines.extend(selected_section)
    lines.extend(build_structured_intent_section(task))
    lines.extend(build_change_boundary_section(selected_section_paths(selected_section), budget_report))
    lines.extend(build_context_budget_section(budget_report))
    lines.extend(build_included_context_section(budget_report))
    lines.extend(build_excluded_context_section(budget_report))
    lines.extend(build_symbol_hints_section(budget_report.get("symbol_hints")))
    lines.extend(build_symbol_snippets_section(budget_report.get("symbol_snippets")))
    lines.extend(build_test_hints_section(budget_report.get("test_hints")))
    lines.extend(_build_frontend_intelligence_sections(budget_report))
    lines.extend(build_execution_path_hints_section(budget_report.get("execution_path_hints")))
    lines.extend(_format_health_summary(health))
    lines.extend(_format_relevant_files(relevant_files))
    lines.extend(_format_verification_plan(graph, relevant_files, budget_report))
    repository_lines = lines[repository_context_start:]
    lines[repository_context_start:] = wrap_repository_content(repository_lines)

    return redact_text("\n".join(lines).rstrip() + "\n")


def _format_health_summary(health: dict) -> list[str]:
    return [
        "## Repository Health",
        "",
        f"- Files: {health.get('file_count', 0)}",
        f"- Edges: {health.get('edge_count', 0)}",
        f"- Unresolved imports: {health.get('unresolved_import_count', 0)}",
        f"- Cycles: {health.get('cycle_count', 0)}",
        f"- Status: {health.get('status', 'unknown')}",
        "",
    ]


def _build_frontend_intelligence_sections(budget_report: dict) -> list[str]:
    lines = []
    lines.extend(build_typescript_project_hints_section(budget_report.get("typescript_project_hints")))
    lines.extend(build_javascript_project_hints_section(budget_report.get("javascript_project_hints")))
    lines.extend(build_declaration_hints_section(budget_report.get("declaration_hints")))
    lines.extend(build_react_hints_section(budget_report.get("react_hints")))
    lines.extend(build_angular_hints_section(budget_report.get("angular_hints")))
    return lines


def _merge_selected_files(
    selected_entries: list[dict],
    scored_files: list[dict],
    max_files: int,
) -> list[dict]:
    merged: list[dict] = []
    seen: set[str] = set()

    for item in selected_entries + scored_files:
        file_info = item.get("file", {})
        path = str(file_info.get("path", "")).replace("\\", "/").strip()

        if not path or path in seen:
            continue

        seen.add(path)
        merged.append(item)

        if len(merged) >= max_files:
            break

    return merged


def _format_relevant_files(relevant_files: list[dict]) -> list[str]:
    lines = [
        "## Relevant Files",
        "",
    ]

    if not relevant_files:
        lines.append("- No relevant files were identified.")
        lines.append("")
        return lines

    for item in relevant_files:
        file_info = item.get("file", {})
        path = file_info.get("path", "<unknown>")
        score = item.get("score", 0)
        reason = item.get("reason", "matched task context")

        lines.append(f"### `{path}`")
        lines.append("")
        if item.get("selected_by_user"):
            lines.append("- Selection: user-selected")
        lines.append(f"- Relevance score: {score}")
        lines.append(f"- Reason: {reason}")

        classes = file_info.get("classes", [])
        functions = file_info.get("functions", [])

        if classes:
            class_names = ", ".join(_symbol_name(symbol) for symbol in classes)
            lines.append(f"- Classes: {class_names}")

        if functions:
            function_names = ", ".join(_symbol_name(symbol) for symbol in functions)
            lines.append(f"- Functions: {function_names}")

        lines.append("")

    return lines


def _format_compact_file_list(relevant_files: list[dict]) -> list[str]:
    lines = [
        "Relevant files:",
    ]

    if not relevant_files:
        lines.append("- No relevant files identified.")
        lines.append("")
        return lines

    for item in relevant_files:
        file_info = item.get("file", {})
        path = file_info.get("path", "<unknown>")
        lines.append(f"- {path}")

    lines.append("")
    return lines


def _format_aider_file_section(relevant_files: list[dict]) -> list[str]:
    lines = [
        "Files to inspect first:",
    ]

    if not relevant_files:
        lines.append("- No relevant files identified.")
        lines.append("")
        return lines

    for item in relevant_files:
        file_info = item.get("file", {})
        path = file_info.get("path", "<unknown>")
        lines.append(f"- {path}")

    lines.append("")
    return lines


def _format_verification_plan(
    graph: dict,
    relevant_files: list[dict],
    budget_report: dict | None = None,
) -> list[str]:
    commands = list((budget_report or {}).get("verification_plan", []) or [])
    if not commands:
        commands = _collect_verification_commands(graph, relevant_files)
    related_tests = _collect_related_test_files(graph, relevant_files)

    lines = build_verification_plan_section(commands)

    if related_tests:
        lines.pop()
        lines.append("Likely related test files:")
        for path in related_tests:
            lines.append(f"- `{path}`")
        lines.append("")
    return lines


def _format_compact_verification_plan(
    graph: dict,
    relevant_files: list[dict],
    budget_report: dict | None = None,
) -> list[str]:
    commands = list((budget_report or {}).get("verification_plan", []) or [])
    if not commands:
        commands = _collect_verification_commands(graph, relevant_files)

    lines = [
        "Verify with:",
    ]

    for command in commands:
        lines.append(f"- {command}")

    lines.append("")
    return lines


def _collect_verification_commands(graph: dict, relevant_files: list[dict]) -> list[str]:
    commands = ["py tests.py"]

    for item in relevant_files:
        file_info = item.get("file", {})
        path = file_info.get("path")

        if not path:
            continue

        suggestions = suggest_tests_for_file(graph, path)

        for command in suggestions.get("recommended_commands", []):
            if command not in commands:
                commands.append(command)

    return commands


def _collect_related_test_files(graph: dict, relevant_files: list[dict]) -> list[str]:
    related_tests = []

    for item in relevant_files:
        file_info = item.get("file", {})
        path = file_info.get("path")

        if not path:
            continue

        suggestions = suggest_tests_for_file(graph, path)

        for test_path in suggestions.get("related_test_files", []):
            if test_path not in related_tests:
                related_tests.append(test_path)

    return related_tests


def _symbol_name(symbol: object) -> str:
    if isinstance(symbol, dict):
        return str(symbol.get("name", "<unknown>"))

    return str(symbol)


def selected_section_paths(selected_section: list[str]) -> list[str]:
    paths: list[str] = []

    for line in selected_section:
        text = str(line).strip()
        if text.startswith("- `") and text.endswith("`"):
            paths.append(text[3:-1])

    return paths
