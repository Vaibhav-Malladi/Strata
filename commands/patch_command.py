from patch_contract import inspect_patch
from ui import format_path, format_success, format_warning, print_command_header, print_status_card


def write_patch_command(root_path: str = ".") -> int:
    patch_summary = inspect_patch(root_path)
    status = str(patch_summary.get("status", "missing")).lower()

    print_command_header("Patch", "Inspect generated patch", mode="compact")
    print_status_card(
        "Patch inspect",
        [
            ("Patch", format_path(patch_summary.get("patch_path", ".aidc/agent_patch.diff"))),
            ("Exists", _format_exists(bool(patch_summary.get("exists")))),
            ("Size", _format_size(patch_summary.get("size", 0))),
            ("Message", patch_summary.get("message", "")),
        ],
        status=_format_status(status),
    )

    return 0 if status == "ready" else 1


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
