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

REPRESENTATION_TIER_WHOLE_FILE = "whole_file"
REPRESENTATION_TIER_SYMBOL_SLICE = "symbol_slice"
REPRESENTATION_TIER_METHOD_CLASS_SLICE = "method_class_slice"
REPRESENTATION_TIER_FILE_OUTLINE = "file_outline"
REPRESENTATION_TIER_PATH_ONLY = "path_only"
REPRESENTATION_TIER_SKIPPED = "skipped"
REPRESENTATION_TIERS = (
    REPRESENTATION_TIER_WHOLE_FILE,
    REPRESENTATION_TIER_SYMBOL_SLICE,
    REPRESENTATION_TIER_METHOD_CLASS_SLICE,
    REPRESENTATION_TIER_FILE_OUTLINE,
    REPRESENTATION_TIER_PATH_ONLY,
    REPRESENTATION_TIER_SKIPPED,
)
REPRESENTATION_TIER_LABELS = {
    REPRESENTATION_TIER_WHOLE_FILE: "whole file",
    REPRESENTATION_TIER_SYMBOL_SLICE: "symbol slice",
    REPRESENTATION_TIER_METHOD_CLASS_SLICE: "method/class slice",
    REPRESENTATION_TIER_FILE_OUTLINE: "file outline",
    REPRESENTATION_TIER_PATH_ONLY: "path-only with reason",
    REPRESENTATION_TIER_SKIPPED: "skipped with reason",
}
REPRESENTATION_TIER_PLAIN_LANGUAGE = {
    REPRESENTATION_TIER_WHOLE_FILE: "full content",
    REPRESENTATION_TIER_SYMBOL_SLICE: "useful symbols",
    REPRESENTATION_TIER_METHOD_CLASS_SLICE: "relevant method/class only",
    REPRESENTATION_TIER_FILE_OUTLINE: "outline",
    REPRESENTATION_TIER_PATH_ONLY: "path and reason only",
    REPRESENTATION_TIER_SKIPPED: "skipped",
}
REPRESENTATION_TIERS_REQUIRING_REASON = (
    REPRESENTATION_TIER_PATH_ONLY,
    REPRESENTATION_TIER_SKIPPED,
)

SOURCE_TYPE_CANDIDATE = "candidate"
SOURCE_TYPE_TRACE = "trace"
SOURCE_TYPE_INTERNAL_LIBRARY = "internal_library"
SOURCE_TYPE_WARNING = "warning"
SOURCE_TYPE_WORKSPACE_PLACEHOLDER = "workspace_placeholder"
REPRESENTATION_SOURCE_TYPES = (
    SOURCE_TYPE_CANDIDATE,
    SOURCE_TYPE_TRACE,
    SOURCE_TYPE_INTERNAL_LIBRARY,
    SOURCE_TYPE_WARNING,
    SOURCE_TYPE_WORKSPACE_PLACEHOLDER,
)

REPRESENTED_ITEM_FIELD_ORDER = (
    "path",
    "tier",
    "tier_label",
    "plain_language",
    "reason",
    "source_type",
    "priority",
    "score",
    "estimated_tokens",
    "original_estimated_tokens",
    "savings_estimated_tokens",
    "warnings",
    "content",
    "excerpt",
)

BUDGET_PROFILE_FIELD_ORDER = (
    "target_context_tokens",
    "reserved_output_tokens",
    "max_context_pack_tokens",
    "tokenizer_strategy",
    "safety_margin",
)
BUDGET_SUMMARY_FIELD_ORDER = (
    "target_context_tokens",
    "estimated_used_tokens",
    "reserved_output_tokens",
    "safety_margin",
    "representation_counts",
    "largest_token_savings",
    "skipped_or_downgraded",
    "warnings",
)
DEFAULT_TARGET_CONTEXT_TOKENS = 12000
DEFAULT_RESERVED_OUTPUT_TOKENS = 2000
DEFAULT_MAX_CONTEXT_PACK_TOKENS = 10000
DEFAULT_TOKENIZER_STRATEGY = "conservative_char_estimate"
DEFAULT_SAFETY_MARGIN = 0.15

REPRESENTATION_FAILURE_SYNTAX_ERROR = "syntax_error"
REPRESENTATION_FAILURE_PARSE_TIMEOUT = "parse_timeout"
REPRESENTATION_FAILURE_EMPTY_LARGE_FILE = "empty_large_file"
REPRESENTATION_FAILURE_EXCEPTION = "exception"
REPRESENTATION_FAILURE_UNSAFE_DECODE = "unsafe_decode"
REPRESENTATION_FAILURE_REASONS = (
    REPRESENTATION_FAILURE_SYNTAX_ERROR,
    REPRESENTATION_FAILURE_PARSE_TIMEOUT,
    REPRESENTATION_FAILURE_EMPTY_LARGE_FILE,
    REPRESENTATION_FAILURE_EXCEPTION,
    REPRESENTATION_FAILURE_UNSAFE_DECODE,
)
REPRESENTATION_FAILURE_LABELS = {
    REPRESENTATION_FAILURE_SYNTAX_ERROR: "syntax error",
    REPRESENTATION_FAILURE_PARSE_TIMEOUT: "parse timeout over 5 seconds",
    REPRESENTATION_FAILURE_EMPTY_LARGE_FILE: "empty extraction result for a file over 100 lines",
    REPRESENTATION_FAILURE_EXCEPTION: "symbol extraction exception",
    REPRESENTATION_FAILURE_UNSAFE_DECODE: "unsafe decode",
}

REPRESENTATION_SKIP_IRRELEVANT = "irrelevant"
REPRESENTATION_SKIP_UNSAFE = "unsafe"
REPRESENTATION_SKIP_MISSING = "missing"
REPRESENTATION_SKIP_UNAVAILABLE = "unavailable"
REPRESENTATION_SKIP_REASONS = (
    REPRESENTATION_SKIP_IRRELEVANT,
    REPRESENTATION_SKIP_UNSAFE,
    REPRESENTATION_SKIP_MISSING,
    REPRESENTATION_SKIP_UNAVAILABLE,
)

REPRESENTATION_DOWNGRADE_MAP = {
    REPRESENTATION_TIER_WHOLE_FILE: REPRESENTATION_TIER_SYMBOL_SLICE,
    REPRESENTATION_TIER_SYMBOL_SLICE: REPRESENTATION_TIER_METHOD_CLASS_SLICE,
    REPRESENTATION_TIER_METHOD_CLASS_SLICE: REPRESENTATION_TIER_FILE_OUTLINE,
    REPRESENTATION_TIER_FILE_OUTLINE: REPRESENTATION_TIER_PATH_ONLY,
    REPRESENTATION_TIER_PATH_ONLY: REPRESENTATION_TIER_PATH_ONLY,
    REPRESENTATION_TIER_SKIPPED: REPRESENTATION_TIER_SKIPPED,
}


def render_strata_context(
    *,
    task: str = "",
    suggested_instructions: str | list | tuple | None = None,
    relevant_files: str | list | tuple | dict | None = None,
    dependency_traces: str | list | tuple | dict | None = None,
    internal_library_apis: str | list | tuple | dict | None = None,
    cross_repo_external_references: str | list | tuple | dict | None = None,
    budget_summary: dict | None = None,
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

    if budget_summary is not None:
        _append_section(lines, "## Context Budget Summary", budget_summary)
    _append_section(lines, "## Scope Guard", scope_guard)
    _append_section(lines, "## Warnings", warnings)

    return "\n".join(lines).rstrip() + "\n"


def build_represented_item(
    *,
    path: str,
    tier: str,
    reason: str = "",
    source_type: str = SOURCE_TYPE_CANDIDATE,
    priority: int | None = None,
    score: int | float | None = None,
    estimated_tokens: int | None = None,
    original_estimated_tokens: int | None = None,
    savings_estimated_tokens: int | None = None,
    warnings: list[str] | tuple[str, ...] | None = None,
    content: str | None = None,
    excerpt: str | None = None,
) -> dict:
    """Build a deterministic JSON-ready represented item contract."""

    tier = str(tier or "").strip()
    source_type = str(source_type or "").strip()
    reason = str(reason or "").strip()

    if tier not in REPRESENTATION_TIERS:
        raise ValueError(f"Unknown representation tier: {tier}")
    if source_type not in REPRESENTATION_SOURCE_TYPES:
        raise ValueError(f"Unknown representation source type: {source_type}")
    if tier in REPRESENTATION_TIERS_REQUIRING_REASON and not reason:
        raise ValueError(f"Representation tier requires a reason: {tier}")

    return {
        "path": str(path or "").replace("\\", "/").strip(),
        "tier": tier,
        "tier_label": REPRESENTATION_TIER_LABELS[tier],
        "plain_language": REPRESENTATION_TIER_PLAIN_LANGUAGE[tier],
        "reason": reason,
        "source_type": source_type,
        "priority": priority,
        "score": score,
        "estimated_tokens": estimated_tokens,
        "original_estimated_tokens": original_estimated_tokens,
        "savings_estimated_tokens": savings_estimated_tokens,
        "warnings": _string_list(warnings),
        "content": content,
        "excerpt": excerpt,
    }


def order_represented_items(items: list[dict] | tuple[dict, ...]) -> list[dict]:
    """Return represented items in stable display order without allocating budget."""

    return sorted(
        [dict(item) for item in items],
        key=lambda item: (
            _none_last_number(item.get("priority")),
            _none_last_number(item.get("score")),
            _tier_index(item.get("tier")),
            str(item.get("path") or ""),
            str(item.get("source_type") or ""),
            str(item.get("reason") or ""),
        ),
    )


def build_budget_profile(
    *,
    target_context_tokens: int | None = None,
    reserved_output_tokens: int | None = None,
    max_context_pack_tokens: int | None = None,
    tokenizer_strategy: str = DEFAULT_TOKENIZER_STRATEGY,
    safety_margin: int | float | None = None,
) -> dict:
    """Build the deterministic token-firewall budget profile contract."""

    return {
        "target_context_tokens": _nonnegative_int(
            DEFAULT_TARGET_CONTEXT_TOKENS if target_context_tokens is None else target_context_tokens,
            "target_context_tokens",
        ),
        "reserved_output_tokens": _nonnegative_int(
            DEFAULT_RESERVED_OUTPUT_TOKENS if reserved_output_tokens is None else reserved_output_tokens,
            "reserved_output_tokens",
        ),
        "max_context_pack_tokens": _nonnegative_int(
            DEFAULT_MAX_CONTEXT_PACK_TOKENS if max_context_pack_tokens is None else max_context_pack_tokens,
            "max_context_pack_tokens",
        ),
        "tokenizer_strategy": str(tokenizer_strategy or DEFAULT_TOKENIZER_STRATEGY),
        "safety_margin": _nonnegative_number(
            DEFAULT_SAFETY_MARGIN if safety_margin is None else safety_margin,
            "safety_margin",
        ),
    }


def estimate_tokens_conservative(text: str | None) -> int:
    """Approximate tokens with a conservative stdlib-only character estimate."""

    length = len(str(text or ""))
    if length <= 0:
        return 0
    return max(1, (length + 2) // 3)


def count_representations_by_tier(items: list[dict] | tuple[dict, ...] | None) -> dict:
    counts = {tier: 0 for tier in REPRESENTATION_TIERS}

    for item in items or []:
        tier = item.get("tier") if isinstance(item, dict) else None
        if tier in counts:
            counts[tier] += 1

    return counts


def build_token_savings_entry(
    *,
    path: str,
    tier: str,
    savings_estimated_tokens: int | None = None,
    original_estimated_tokens: int | None = None,
    estimated_tokens: int | None = None,
    reason: str = "",
) -> dict:
    return {
        "path": str(path or "").replace("\\", "/").strip(),
        "tier": str(tier or "").strip(),
        "savings_estimated_tokens": _optional_nonnegative_int(
            savings_estimated_tokens,
            "savings_estimated_tokens",
        ),
        "original_estimated_tokens": _optional_nonnegative_int(
            original_estimated_tokens,
            "original_estimated_tokens",
        ),
        "estimated_tokens": _optional_nonnegative_int(estimated_tokens, "estimated_tokens"),
        "reason": str(reason or "").strip(),
    }


def build_skipped_or_downgraded_entry(
    *,
    path: str,
    tier: str,
    reason: str,
    source_type: str = SOURCE_TYPE_CANDIDATE,
) -> dict:
    if not str(reason or "").strip():
        raise ValueError("Skipped or downgraded entries require a reason.")

    return {
        "path": str(path or "").replace("\\", "/").strip(),
        "tier": str(tier or "").strip(),
        "source_type": str(source_type or "").strip(),
        "reason": str(reason or "").strip(),
    }


def build_budget_summary(
    *,
    profile: dict | None = None,
    represented_items: list[dict] | tuple[dict, ...] | None = None,
    estimated_used_tokens: int | None = None,
    largest_token_savings: list[dict] | tuple[dict, ...] | None = None,
    skipped_or_downgraded: list[dict] | tuple[dict, ...] | None = None,
    warnings: list[str] | tuple[str, ...] | None = None,
) -> dict:
    """Build a deterministic budget summary without allocating budget."""

    profile = build_budget_profile(**(profile or {}))
    used = estimated_used_tokens
    if used is None:
        used = sum(
            _optional_nonnegative_int(item.get("estimated_tokens"), "estimated_tokens") or 0
            for item in represented_items or []
            if isinstance(item, dict)
        )

    return {
        "target_context_tokens": profile["target_context_tokens"],
        "estimated_used_tokens": _nonnegative_int(used, "estimated_used_tokens"),
        "reserved_output_tokens": profile["reserved_output_tokens"],
        "safety_margin": profile["safety_margin"],
        "representation_counts": count_representations_by_tier(represented_items),
        "largest_token_savings": order_token_savings_entries(largest_token_savings or []),
        "skipped_or_downgraded": order_budget_entries(skipped_or_downgraded or []),
        "warnings": _string_list(warnings),
    }


def order_token_savings_entries(items: list[dict] | tuple[dict, ...]) -> list[dict]:
    return sorted(
        [dict(item) for item in items],
        key=lambda item: (
            -(_optional_nonnegative_int(item.get("savings_estimated_tokens"), "savings_estimated_tokens") or 0),
            str(item.get("path") or ""),
            str(item.get("tier") or ""),
            str(item.get("reason") or ""),
        ),
    )


def order_budget_entries(items: list[dict] | tuple[dict, ...]) -> list[dict]:
    return sorted(
        [dict(item) for item in items],
        key=lambda item: (
            str(item.get("path") or ""),
            str(item.get("tier") or ""),
            str(item.get("source_type") or ""),
            str(item.get("reason") or ""),
        ),
    )


def next_lighter_tier(current_tier: str, *, skip_reason: str | None = None) -> str:
    """Return the next lighter representation tier without allocating budget."""

    tier = _require_representation_tier(current_tier)
    if tier == REPRESENTATION_TIER_PATH_ONLY and skip_reason is not None:
        if skip_reason not in REPRESENTATION_SKIP_REASONS:
            raise ValueError(f"Skipped representation requires an explicit skip reason: {skip_reason}")
        return REPRESENTATION_TIER_SKIPPED
    return REPRESENTATION_DOWNGRADE_MAP[tier]


def representation_after_failure(
    current_tier: str,
    failure_reason: str,
    *,
    path: str = "",
) -> dict:
    """Describe a safe fall-through after extraction failure."""

    tier = _require_representation_tier(current_tier)
    reason_code = str(failure_reason or "").strip()
    if reason_code not in REPRESENTATION_FAILURE_REASONS:
        raise ValueError(f"Unknown representation failure reason: {failure_reason}")

    next_tier = next_lighter_tier(tier)
    failure_label = REPRESENTATION_FAILURE_LABELS[reason_code]
    current_label = REPRESENTATION_TIER_LABELS[tier]
    next_label = REPRESENTATION_TIER_LABELS[next_tier]
    target = str(path or "").replace("\\", "/").strip()
    prefix = f"{target}: " if target else ""
    reason = f"{prefix}{failure_label}; downgraded from {current_label} to {next_label}."

    return {
        "path": target,
        "from_tier": tier,
        "tier": next_tier,
        "failure_reason": reason_code,
        "reason": reason,
        "warning": reason,
    }


def explicit_skip_representation(
    *,
    path: str,
    skip_reason: str,
    reason: str,
    source_type: str = SOURCE_TYPE_WARNING,
) -> dict:
    """Build a skipped represented item only for explicit skip reasons."""

    reason_code = str(skip_reason or "").strip()
    if reason_code not in REPRESENTATION_SKIP_REASONS:
        raise ValueError(f"Unknown explicit skip reason: {skip_reason}")
    return build_represented_item(
        path=path,
        tier=REPRESENTATION_TIER_SKIPPED,
        reason=reason,
        source_type=source_type,
        warnings=[f"Skipped because {reason_code}: {reason}"],
    )


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


def render_represented_items(items: list[dict] | tuple[dict, ...]) -> list[str]:
    lines: list[str] = []

    for item in order_represented_items(items):
        path = _neutralize_delimiter_collision(str(item.get("path") or ""))
        tier_label = _neutralize_delimiter_collision(str(item.get("tier_label") or item.get("tier") or ""))
        plain_language = _neutralize_delimiter_collision(str(item.get("plain_language") or ""))
        source_type = _neutralize_delimiter_collision(str(item.get("source_type") or ""))
        reason = _neutralize_delimiter_collision(str(item.get("reason") or "").strip())

        lines.append(f"- `{path}` - {tier_label} ({plain_language})")
        lines.append(f"  - Source: `{source_type}`")
        if reason:
            lines.append(f"  - Reason: {reason}")
        _append_optional_number(lines, "Priority", item.get("priority"))
        _append_optional_number(lines, "Score", item.get("score"))
        _append_optional_number(lines, "Estimated tokens", item.get("estimated_tokens"))
        _append_optional_number(lines, "Original estimated tokens", item.get("original_estimated_tokens"))
        _append_optional_number(lines, "Savings estimated tokens", item.get("savings_estimated_tokens"))

        for warning in _string_list(item.get("warnings")):
            lines.append(f"  - Warning: {_neutralize_delimiter_collision(warning)}")

        excerpt = item.get("excerpt")
        if excerpt:
            lines.append("  - Excerpt:")
            lines.extend(f"    {line}" for line in _content_lines(excerpt))

        content = item.get("content")
        if content:
            lines.append("  - Content:")
            lines.extend(f"    {line}" for line in _content_lines(content))

    return lines or ["- none"]


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
        if all(isinstance(item, dict) and _is_represented_item(item) for item in content):
            return render_represented_items(content)

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


def _nonnegative_int(value, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a non-negative integer.")
    try:
        number = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be a non-negative integer.") from error
    if number < 0:
        raise ValueError(f"{field_name} must be a non-negative integer.")
    return number


def _optional_nonnegative_int(value, field_name: str) -> int | None:
    if value is None:
        return None
    return _nonnegative_int(value, field_name)


def _nonnegative_number(value, field_name: str) -> int | float:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a non-negative number.")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be a non-negative number.") from error
    if number < 0:
        raise ValueError(f"{field_name} must be a non-negative number.")
    if number.is_integer():
        return int(number)
    return number


def _string_list(values) -> list[str]:
    if values is None:
        return []
    return [str(value) for value in values if str(value)]


def _is_represented_item(value: dict) -> bool:
    return (
        value.get("tier") in REPRESENTATION_TIERS
        and value.get("source_type") in REPRESENTATION_SOURCE_TYPES
        and "path" in value
    )


def _append_optional_number(lines: list[str], label: str, value) -> None:
    if value is None:
        return
    lines.append(f"  - {label}: `{value}`")


def _content_lines(value) -> list[str]:
    return [
        _neutralize_delimiter_collision(line)
        for line in str(value).splitlines()
    ] or [""]


def _none_last_number(value):
    if value is None:
        return (1, 0.0, "")
    try:
        return (0, float(value), "")
    except (TypeError, ValueError):
        return (0, 0.0, str(value))


def _tier_index(value) -> int:
    try:
        return REPRESENTATION_TIERS.index(value)
    except ValueError:
        return len(REPRESENTATION_TIERS)


def _require_representation_tier(value: str) -> str:
    tier = str(value or "").strip()
    if tier not in REPRESENTATION_TIERS:
        raise ValueError(f"Unknown representation tier: {value}")
    return tier
