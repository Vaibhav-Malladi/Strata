from patch_contract import inspect_patch
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
    ready = status == "ready"

    print(build_banner())
    print()
    print(build_section("Apply dry-run"))
    print(
        build_kv_table(
            [
                ("Status", _format_status(status)),
                ("Patch", format_path(patch_summary.get("patch_path", ".aidc/agent_patch.diff"))),
                ("Exists", _format_exists(bool(patch_summary.get("exists")))),
                ("Size", _format_size(patch_summary.get("size", 0))),
                ("Message", _format_message(status, patch_summary.get("message", ""))),
                ("Applies patch", "no"),
            ]
        )
    )

    return 0 if ready else 1


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

    if status == "empty":
        return format_warning("empty")

    return format_warning("missing")


def _format_exists(value: bool) -> str:
    return "yes" if value else "no"


def _format_size(value: object) -> str:
    try:
        size = int(value)
    except (TypeError, ValueError):
        size = 0

    return f"{size} bytes"


def _format_message(status: str, message: object) -> str:
    if status == "ready":
        return "Patch file is ready for apply dry-run."

    return str(message)
