import json


CONTEXT_ARTIFACT_PATH = ".aidc/context/strata_context.md"
RUN_STATE_ARTIFACT_PATH = ".aidc/context/run_state.json"
CANONICAL_CONTEXT_ARTIFACT_PATHS = (
    CONTEXT_ARTIFACT_PATH,
    RUN_STATE_ARTIFACT_PATH,
)

REPOSITORY_CONTENT_BEGIN = "--- BEGIN REPOSITORY CONTENT ---"
REPOSITORY_CONTENT_END = "--- END REPOSITORY CONTENT ---"

STRATA_CONTEXT_SECTION_ORDER = (
    "# Strata Context",
    "## Task",
    "## Suggested Instructions",
    REPOSITORY_CONTENT_BEGIN,
    "## Relevant Files",
    "## Dependency Traces",
    "## Internal Library APIs",
    "## Cross-Repo / External App References",
    REPOSITORY_CONTENT_END,
    "## Scope Guard",
    "## Warnings",
)

REPOSITORY_DERIVED_SECTIONS = (
    "## Relevant Files",
    "## Dependency Traces",
    "## Internal Library APIs",
    "## Cross-Repo / External App References",
)

RUN_STATE_SCHEMA_VERSION = 1
DEFAULT_WORKSPACE_MODE = "single_repo"
RUN_STATE_FIELD_ORDER = (
    "schema_version",
    "task",
    "created_at",
    "baseline_commit",
    "baseline_commit_attached",
    "in_scope_files",
    "expected_related_files",
    "allowed_new_files",
    "prompt_hash",
    "adapter",
    "patch_received",
    "error",
    "workspace_mode",
    "workspace",
    "cross_repo_references",
    "internal_libraries",
)


def render_strata_context(
    *,
    task: str = "",
    suggested_instructions: str | list | tuple | None = None,
    relevant_files: str | list | tuple | dict | None = None,
    dependency_traces: str | list | tuple | dict | None = None,
    internal_library_apis: str | list | tuple | dict | None = None,
    cross_repo_external_references: str | list | tuple | dict | None = None,
    scope_guard: str | list | tuple | None = None,
    warnings: str | list | tuple | None = None,
) -> str:
    """Render the canonical AI-ready Strata context contract."""

    lines: list[str] = ["# Strata Context", ""]
    _append_section(lines, "## Task", task, empty_text="")
    _append_section(lines, "## Suggested Instructions", suggested_instructions)

    lines.append(REPOSITORY_CONTENT_BEGIN)
    lines.append("")
    _append_section(lines, "## Relevant Files", relevant_files)
    _append_section(lines, "## Dependency Traces", dependency_traces)
    _append_section(lines, "## Internal Library APIs", internal_library_apis)
    _append_section(lines, "## Cross-Repo / External App References", cross_repo_external_references)
    lines.append(REPOSITORY_CONTENT_END)
    lines.append("")

    _append_section(lines, "## Scope Guard", scope_guard)
    _append_section(lines, "## Warnings", warnings)

    return "\n".join(lines).rstrip() + "\n"


def build_run_state(
    *,
    schema_version: int = RUN_STATE_SCHEMA_VERSION,
    task: str = "",
    created_at: str | None = None,
    baseline_commit: str | None = None,
    baseline_commit_attached: bool = False,
    in_scope_files: list[str] | tuple[str, ...] | None = None,
    expected_related_files: list[str] | tuple[str, ...] | None = None,
    allowed_new_files: list[str] | tuple[str, ...] | None = None,
    prompt_hash: str | None = None,
    adapter: str | None = None,
    patch_received: bool = False,
    error: str | None = None,
    workspace_mode: str = DEFAULT_WORKSPACE_MODE,
    workspace: dict | None = None,
    cross_repo_references: list | tuple | None = None,
    internal_libraries: list | tuple | None = None,
) -> dict:
    """Build the deterministic run_state.json contract payload."""

    return {
        "schema_version": schema_version,
        "task": str(task or ""),
        "created_at": created_at,
        "baseline_commit": baseline_commit,
        "baseline_commit_attached": bool(baseline_commit_attached),
        "in_scope_files": _list_copy(in_scope_files),
        "expected_related_files": _list_copy(expected_related_files),
        "allowed_new_files": _list_copy(allowed_new_files),
        "prompt_hash": prompt_hash,
        "adapter": adapter,
        "patch_received": bool(patch_received),
        "error": error,
        "workspace_mode": str(workspace_mode or DEFAULT_WORKSPACE_MODE),
        "workspace": workspace,
        "cross_repo_references": _list_copy(cross_repo_references),
        "internal_libraries": _list_copy(internal_libraries),
    }


def render_run_state_json(run_state: dict) -> str:
    """Render run_state.json with stable formatting."""

    return json.dumps(run_state, indent=2, ensure_ascii=False) + "\n"


def _append_section(lines: list[str], heading: str, content, *, empty_text: str = "- none") -> None:
    lines.append(heading)
    lines.append("")
    lines.extend(_markdown_lines(content, empty_text=empty_text))
    lines.append("")


def _markdown_lines(content, *, empty_text: str) -> list[str]:
    if content is None:
        return [empty_text] if empty_text != "" else []

    if isinstance(content, str):
        text = content.strip()
        if not text:
            return [empty_text] if empty_text != "" else []
        return [_neutralize_delimiter_collision(line) for line in text.splitlines()]

    if isinstance(content, dict):
        return _json_block(content)

    if isinstance(content, (list, tuple)):
        if not content:
            return [empty_text] if empty_text != "" else []

        rendered: list[str] = []
        for item in content:
            if isinstance(item, dict):
                rendered.append(f"- `{_stable_json(item)}`")
            else:
                rendered.append(f"- {_neutralize_delimiter_collision(str(item))}")
        return rendered

    return [_neutralize_delimiter_collision(str(content))]


def _json_block(value: dict) -> list[str]:
    return [
        "```json",
        *(_neutralize_delimiter_collision(line) for line in _stable_json(value, pretty=True).splitlines()),
        "```",
    ]


def _stable_json(value, *, pretty: bool = False) -> str:
    if pretty:
        return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False)
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _neutralize_delimiter_collision(value: str) -> str:
    return (
        str(value)
        .replace(REPOSITORY_CONTENT_BEGIN, "[repository content begin delimiter]")
        .replace(REPOSITORY_CONTENT_END, "[repository content end delimiter]")
    )


def _list_copy(values) -> list:
    if values is None:
        return []
    return list(values)
