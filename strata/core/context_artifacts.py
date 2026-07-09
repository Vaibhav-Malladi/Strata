import json
from pathlib import Path
from subprocess import SubprocessError

from strata.utils.shell import run_argv


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
    "baseline_status",
    "baseline_warning",
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

BASELINE_STATUS_ATTACHED = "attached"
BASELINE_STATUS_DETACHED = "detached"
BASELINE_STATUS_NO_COMMITS = "no_commits"
BASELINE_STATUS_NOT_GIT = "not_git"
BASELINE_STATUS_GIT_UNAVAILABLE = "git_unavailable"
BASELINE_STATUS_AVAILABLE = "available"
BASELINE_STATUS_MISSING = "missing"
BASELINE_STATUS_NOT_PROVIDED = "not_provided"

NO_COMMITS_BASELINE_WARNING = (
    "Review diff is disabled until the repository has at least one commit."
)
DETACHED_HEAD_BASELINE_WARNING = (
    "HEAD is detached; review can compare against the captured commit, but branch tracking is unavailable."
)
MISSING_BASELINE_WARNING = (
    "Stored baseline commit is missing or unreachable; re-run context before review diff."
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
    baseline_status: str | None = None,
    baseline_warning: str | None = None,
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
        "baseline_status": baseline_status,
        "baseline_warning": baseline_warning,
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


def capture_git_baseline(root_path: str | Path) -> dict:
    """Capture the current git HEAD state for run_state.json."""

    root = Path(root_path)
    repo_check = _run_git(root, "rev-parse", "--is-inside-work-tree")
    if repo_check is None:
        return _baseline_state(
            None,
            False,
            BASELINE_STATUS_GIT_UNAVAILABLE,
            "Git is unavailable; review diff baseline cannot be captured.",
        )
    if repo_check.returncode != 0:
        return _baseline_state(
            None,
            False,
            BASELINE_STATUS_NOT_GIT,
            "Review diff baseline is unavailable because this path is not a git repository.",
        )

    attached = _is_head_attached(root)
    head = _run_git(root, "rev-parse", "--verify", "HEAD")
    if head is None:
        return _baseline_state(
            None,
            attached,
            BASELINE_STATUS_GIT_UNAVAILABLE,
            "Git is unavailable; review diff baseline cannot be captured.",
        )

    if head.returncode != 0:
        return _baseline_state(
            None,
            attached,
            BASELINE_STATUS_NO_COMMITS,
            NO_COMMITS_BASELINE_WARNING,
        )

    commit = _first_output_line(head.stdout)
    if attached:
        return _baseline_state(commit, True, BASELINE_STATUS_ATTACHED, None)

    return _baseline_state(
        commit,
        False,
        BASELINE_STATUS_DETACHED,
        DETACHED_HEAD_BASELINE_WARNING,
    )


def build_run_state_for_repo(root_path: str | Path, **values) -> dict:
    """Build run_state.json fields with the current git baseline attached."""

    baseline = capture_git_baseline(root_path)
    merged = dict(values)
    merged.setdefault("baseline_commit", baseline["baseline_commit"])
    merged.setdefault("baseline_commit_attached", baseline["baseline_commit_attached"])
    merged.setdefault("baseline_status", baseline["baseline_status"])
    merged.setdefault("baseline_warning", baseline["baseline_warning"])
    return build_run_state(**merged)


def validate_stored_baseline(root_path: str | Path, baseline_commit: str | None) -> dict:
    """Validate that a stored baseline commit can still be used safely."""

    commit = str(baseline_commit or "").strip()
    if not commit:
        return _baseline_validation(
            None,
            False,
            BASELINE_STATUS_NOT_PROVIDED,
            "No stored baseline commit is available; re-run context before review diff.",
        )

    if not _looks_like_commit_id(commit):
        return _baseline_validation(commit, False, BASELINE_STATUS_MISSING, MISSING_BASELINE_WARNING)

    root = Path(root_path)
    repo_check = _run_git(root, "rev-parse", "--is-inside-work-tree")
    if repo_check is None:
        return _baseline_validation(
            commit,
            False,
            BASELINE_STATUS_GIT_UNAVAILABLE,
            "Git is unavailable; stored baseline cannot be validated.",
        )
    if repo_check.returncode != 0:
        return _baseline_validation(
            commit,
            False,
            BASELINE_STATUS_NOT_GIT,
            "Stored baseline cannot be validated because this path is not a git repository.",
        )

    result = _run_git(root, "cat-file", "-e", f"{commit}^{{commit}}")
    if result is not None and result.returncode == 0:
        return _baseline_validation(commit, True, BASELINE_STATUS_AVAILABLE, None)

    return _baseline_validation(commit, False, BASELINE_STATUS_MISSING, MISSING_BASELINE_WARNING)


def render_run_state_json(run_state: dict) -> str:
    """Render run_state.json with stable formatting."""

    return json.dumps(run_state, indent=2, ensure_ascii=False) + "\n"


def _baseline_state(commit: str | None, attached: bool, status: str, warning: str | None) -> dict:
    return {
        "baseline_commit": commit,
        "baseline_commit_attached": bool(attached),
        "baseline_status": status,
        "baseline_warning": warning,
    }


def _baseline_validation(commit: str | None, available: bool, status: str, warning: str | None) -> dict:
    return {
        "baseline_commit": commit,
        "baseline_available": bool(available),
        "baseline_status": status,
        "baseline_warning": warning,
    }


def _run_git(root: Path, *args: str):
    try:
        return run_argv(
            ["git", *args],
            cwd=root,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except (FileNotFoundError, OSError, SubprocessError):
        return None


def _is_head_attached(root: Path) -> bool:
    result = _run_git(root, "symbolic-ref", "-q", "HEAD")
    return result is not None and result.returncode == 0


def _first_output_line(value: str) -> str | None:
    for line in str(value or "").splitlines():
        text = line.strip()
        if text:
            return text
    return None


def _looks_like_commit_id(value: str) -> bool:
    text = str(value or "").strip()
    if len(text) < 4:
        return False
    return all(character in "0123456789abcdefABCDEF" for character in text)


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
