from patch_applier import apply_patch_file
from patch_contract import inspect_patch
from patch_validator import validate_patch_file
from ui import (
    format_error,
    format_path,
    format_success,
    format_warning,
    print_command_header,
    print_status_card,
    print_warning,
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

    return {
        "patch_summary": patch_summary,
        "validation": validation,
        "status": status,
        "targets": targets,
        "message": message,
        "safe": bool(validation and validation.get("valid")),
    }


def write_apply_dry_run_command(root_path: str = ".") -> int:
    state = inspect_apply_state(root_path)
    patch_summary = state["patch_summary"]
    validation = state["validation"]
    status = str(state["status"]).lower()
    display_status = _format_status(status)
    validation_status = validation["status"] if validation is not None else patch_summary.get("status", "missing")
    targets = validation.get("targets", []) if validation is not None else []
    message = _format_message(validation if validation is not None else patch_summary)
    rows = [
        ("Status", display_status),
        ("Patch", format_path(patch_summary.get("patch_path", ".aidc/agent_patch.diff"))),
        ("Exists", _format_exists(bool(patch_summary.get("exists")))),
        ("Size", _format_size(patch_summary.get("size", 0))),
        ("Validation", _format_validation(validation_status)),
        ("Targets", _format_targets(targets)),
        ("Applies patch", "no"),
        ("Message", message),
    ]

    if validation is not None and validation.get("warnings"):
        rows.append(("Warnings", _format_notes(validation.get("warnings", []))))

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

    print_command_header("Apply", "Confirm before applying patch", mode="compact")
    print_status_card("Apply patch", rows, status=_format_status("ready"))

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
    note = "Strata did not commit or push anything. Run your project tests and commit when ready."

    if note in base:
        return base

    return f"{base} {note}"
