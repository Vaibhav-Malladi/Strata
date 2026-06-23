from patch_contract import inspect_patch
from patch_validator import validate_patch_file
from ui import (
    build_banner,
    build_kv_table,
    build_section,
    format_error,
    format_path,
    format_success,
    format_warning,
)


def write_apply_dry_run_command(root_path: str = ".") -> int:
    patch_summary = inspect_patch(root_path)
    status = str(patch_summary.get("status", "missing")).lower()
    validation = None

    if status == "ready":
        validation = validate_patch_file(root_path)
        status = str(validation.get("status", "invalid")).lower()

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

    print(build_banner())
    print()
    print(build_section("Apply dry-run"))
    print(build_kv_table(rows))

    return 0 if validation is not None and validation.get("valid") else 1


def write_apply_command(root_path: str = ".") -> int:
    _ = root_path

    print(build_banner())
    print()
    print(build_section("Apply"))
    print(format_error("real apply is not implemented yet. Use `strata apply --dry-run`."))

    return 1


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
