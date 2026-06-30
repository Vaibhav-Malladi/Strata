import subprocess
from pathlib import Path

from strata.patch.applier import apply_patch_file
from strata.patch.contract import inspect_patch, resolve_patch_path
from strata.patch.validator import validate_patch_file
from strata.utils.output import (
    format_error,
    format_path,
    format_success,
    format_warning,
    print_command_header,
    print_status_card,
    print_warning,
)

_GIT_TIMEOUT_SECONDS = 5
_STALE_PATCH_WARNING = (
    "Patch may be stale because it is older than generated context or source files. "
    "Review or regenerate the patch if you are unsure."
)
_DIRTY_TREE_WARNING = (
    "Git working tree has uncommitted changes. Commit, stash, or revert them before "
    "running `strata apply`."
)
_TRACKED_AIDC_WARNING = (
    "Git is tracking files under `.aidc/`. Generated prompts, context, reports, and "
    "patches should normally not be committed. Add `.aidc/` to `.gitignore`."
)


def inspect_apply_state(root_path: str = ".") -> dict:
    patch_summary = inspect_patch(root_path)
    validation = None

    if str(patch_summary.get("status", "missing")).lower() == "ready":
        validation = validate_patch_file(root_path)

    status = str(patch_summary.get("status", "missing")).lower()
    if validation is not None:
        status = str(validation.get("status", "invalid")).lower()

    targets = validation.get("targets", []) if validation is not None else []
    message = (
        validation.get("message", "")
        if validation is not None
        else patch_summary.get("message", "")
    )

    warnings = []
    dirty_tree = False

    if validation is not None and validation.get("valid"):
        warnings.extend(_collect_stale_patch_warnings(root_path, targets))
        git_state = _inspect_git_state(root_path)
        dirty_tree = bool(git_state["dirty"])
        if dirty_tree:
            warnings.append(_DIRTY_TREE_WARNING)
        if git_state["aidc_tracked"]:
            warnings.append(_TRACKED_AIDC_WARNING)

    return {
        "patch_summary": patch_summary,
        "validation": validation,
        "status": status,
        "targets": targets,
        "message": message,
        "safe": bool(validation and validation.get("valid")),
        "warnings": warnings,
        "dirty_tree": dirty_tree,
    }


def write_apply_dry_run_command(root_path: str = ".") -> int:
    state = inspect_apply_state(root_path)
    patch_summary = state["patch_summary"]
    validation = state["validation"]
    status = str(state["status"]).lower()
    display_status = _format_status(status)
    validation_status = validation["status"] if validation is not None else patch_summary.get("status", "missing")
    targets = validation.get("targets", []) if validation is not None else []
    warnings = list(state["warnings"])
    message = _format_message(validation if validation is not None else patch_summary)
    next_label = "Next" if validation is not None and validation.get("valid") else "Fix"
    next_step = "Run `strata apply`." if validation is not None and validation.get("valid") else 'Run `strata ask "your task"` first.'
    rows = [
        ("Patch", format_path(patch_summary.get("patch_path", ".aidc/agent_patch.diff"))),
        ("Exists", _format_exists(bool(patch_summary.get("exists")))),
        ("Size", _format_size(patch_summary.get("size", 0))),
        ("Validation", _format_validation(validation_status)),
        ("Targets", _format_targets(targets)),
        ("Applies patch", "no"),
        (next_label, next_step),
        ("Message", message),
    ]

    if validation is not None and validation.get("warnings"):
        warnings.extend(validation.get("warnings", []))

    if warnings:
        rows.append(("Warnings", _format_notes(warnings)))

    if validation is not None and validation.get("errors"):
        rows.append(("Errors", _format_notes(validation.get("errors", []))))

    print_command_header("Apply", "Validate and apply patch", mode="compact")
    print_status_card("Apply dry-run", rows, status=display_status)

    return 0 if validation is not None and validation.get("valid") else 1


def write_apply_command(root_path: str = ".", yes: bool = False) -> int:
    state = inspect_apply_state(root_path)
    patch_summary = state["patch_summary"]
    validation = state["validation"]
    status = str(state["status"]).lower()
    targets = validation.get("targets", []) if validation is not None else []
    message = (
        validation.get("message", "")
        if validation is not None
        else patch_summary.get("message", "")
    )
    errors = validation.get("errors", []) if validation is not None else []
    warnings = list(state["warnings"])

    if validation is None or not validation.get("valid"):
        rows = [
            ("Patch", format_path(patch_summary.get("patch_path", ".aidc/agent_patch.diff"))),
            ("Exists", _format_exists(bool(patch_summary.get("exists")))),
            ("Size", _format_size(patch_summary.get("size", 0))),
            ("Validation", _format_validation(validation["status"] if validation is not None else patch_summary.get("status", "missing"))),
            ("Targets", _format_targets(targets)),
            ("Message", _format_message(validation if validation is not None else patch_summary)),
        ]

        if errors:
            rows.append(("Errors", _format_notes(errors)))

        print_command_header("Apply", "Confirm before applying patch", mode="compact")
        print_status_card("Apply patch", rows, status=_format_apply_status(status))
        return 1

    warnings.extend(validation.get("warnings", []))
    rows = [
        ("Patch", format_path(patch_summary.get("patch_path", ".aidc/agent_patch.diff"))),
        ("Exists", _format_exists(True)),
        ("Size", _format_size(patch_summary.get("size", 0))),
        ("Validation", _format_validation(validation.get("status", "invalid"))),
        ("Targets", _format_targets(targets)),
        ("Changed files", "-"),
        ("Confirmation", "yes" if yes else "required"),
        ("Message", message),
    ]

    if warnings:
        rows.append(("Warnings", _format_notes(warnings)))

    print_command_header("Apply", "Confirm before applying patch", mode="compact")
    apply_status = "blocked" if state["dirty_tree"] else "ready"
    print_status_card("Apply patch", rows, status=_format_apply_status(apply_status))

    if state["dirty_tree"]:
        print_warning("Patch not applied because the Git working tree has uncommitted changes.")
        return 1

    if not yes and not _confirm_apply(targets):
        print_warning("Patch not applied.")
        return 1

    apply_result = apply_patch_file(root_path)
    summary_status = str(apply_result.get("status", "failed")).lower()
    changed_files = apply_result.get("changed_files", [])
    applies_patch = "yes" if apply_result.get("applied") else "no"
    success_message = _apply_success_message(apply_result.get("message"))

    result_rows = [
        ("Patch", format_path(patch_summary.get("patch_path", ".aidc/agent_patch.diff"))),
        ("Validation", _format_validation(validation.get("status", "invalid"))),
        ("Targets", _format_targets(targets)),
        ("Changed files", _format_targets(changed_files)),
        ("Applies patch", applies_patch),
        ("Message", success_message),
    ]

    if apply_result.get("errors"):
        result_rows.append(("Errors", _format_notes(apply_result.get("errors", []))))

    print_status_card("Apply complete", result_rows, status=_format_apply_status(summary_status))

    return 0 if apply_result.get("applied") else 1


def _format_status(status: str) -> str:
    if status == "ready":
        return format_success("ready")

    if status == "valid":
        return format_success("ready")

    if status == "invalid":
        return format_error("invalid")

    if status == "empty":
        return format_warning("empty")

    if status == "missing":
        return format_warning("missing")

    return format_warning("missing")


def _format_exists(value: bool) -> str:
    return "yes" if value else "no"


def _format_size(value: object) -> str:
    try:
        size = int(value)
    except (TypeError, ValueError):
        size = 0

    return f"{size} bytes"


def _format_validation(status: object) -> str:
    normalized = str(status).lower()

    if normalized == "valid":
        return format_success("valid")

    if normalized == "invalid":
        return format_error("invalid")

    if normalized == "empty":
        return format_warning("empty")

    return format_warning("missing")


def _format_apply_status(status: str) -> str:
    if status == "applied":
        return format_success("applied")

    if status == "failed":
        return format_error("failed")

    if status == "invalid":
        return format_error("invalid")

    if status == "empty":
        return format_warning("empty")

    if status == "missing":
        return format_warning("missing")

    return format_warning(status)


def _format_targets(targets: object) -> str:
    if not targets:
        return "-"

    return ", ".join(str(target) for target in targets)


def _format_notes(notes: object) -> str:
    if not notes:
        return "-"

    return "; ".join(str(note) for note in notes)


def _format_message(result: object) -> str:
    if not isinstance(result, dict):
        return ""

    status = str(result.get("status", "")).lower()
    if status in {"valid", "invalid"}:
        return str(result.get("message", ""))

    return str(result.get("message", ""))


def _confirm_apply(targets: object) -> bool:
    prompt_targets = _format_targets(targets)
    suffix = f" to {prompt_targets}" if prompt_targets and prompt_targets != "-" else ""

    try:
        response = input(f"Apply this patch{suffix}? [y/N]: ")
    except EOFError:
        return False

    normalized = response.strip().lower()
    return normalized in {"y", "yes"}


def _apply_success_message(message: object) -> str:
    base = str(message or "Patch applied successfully.")
    note = "Next: Run your project tests, review `git diff`, then commit when ready. Strata did not commit or push anything."

    if note in base:
        return base

    return f"{base} {note}"


def _collect_stale_patch_warnings(root_path: str, targets: list[str]) -> list[str]:
    root = Path(root_path).resolve()
    patch_path = resolve_patch_path(root=root)

    try:
        patch_mtime = patch_path.stat().st_mtime_ns
    except OSError:
        return []

    newer_paths: list[str] = []
    context_paths = (
        root / ".aidc" / "context_pack.md",
        root / ".aidc" / "context_pack.json",
    )

    for context_path in context_paths:
        if _is_newer_than(context_path, patch_mtime):
            newer_paths.append(context_path.relative_to(root).as_posix())

    for target in targets:
        target_path = (root / target).resolve()
        try:
            target_path.relative_to(root)
        except ValueError:
            continue

        if target_path.is_file() and _is_newer_than(target_path, patch_mtime):
            newer_paths.append(Path(target).as_posix())

    if not newer_paths:
        return []

    paths = ", ".join(dict.fromkeys(newer_paths))
    return [f"{_STALE_PATCH_WARNING} Newer file(s): {paths}."]


def _is_newer_than(path: Path, mtime_ns: int) -> bool:
    try:
        return path.is_file() and path.stat().st_mtime_ns > mtime_ns
    except OSError:
        return False


def _inspect_git_state(root_path: str) -> dict:
    root = str(Path(root_path).resolve())
    status = _run_git(root, "status", "--porcelain", "--untracked-files=normal")

    if status is None:
        return {"dirty": False, "aidc_tracked": False}

    tracked_aidc = _run_git(root, "ls-files", "--", ".aidc")
    return {
        "dirty": bool(status.strip()),
        "aidc_tracked": bool(tracked_aidc and tracked_aidc.strip()),
    }


def _run_git(root: str, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", root, *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    if result.returncode != 0:
        return None

    return result.stdout
