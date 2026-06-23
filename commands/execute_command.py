from __future__ import annotations

from adapter_doctor import check_adapter
from ui import (
    build_banner,
    build_kv_table,
    build_section,
    format_error,
    format_path,
)

_PLANNED_ADAPTERS = {"ollama", "openai_compatible_http", "aider", "codex_cli"}


def write_execute_command(root_path: str = ".") -> int:
    result = check_adapter(root_path)
    adapter = str(result.get("adapter", "") or "")
    status = str(result.get("status", "invalid")).lower()
    ready = bool(result.get("ready"))

    display_status, message = _build_display_status_and_message(result)
    prompt = _format_path_or_dash(result.get("prompt"))
    patch = _format_path_or_dash(result.get("patch"))
    command = _format_command(result.get("command"))

    rows = [
        ("Status", display_status),
        ("Mode", _format_value(result.get("mode"))),
        ("Agent", _format_value(result.get("agent"))),
        ("Adapter", _format_value(adapter)),
        ("Prompt", prompt),
        ("Patch", patch),
        ("Command", command),
        ("Executes command", "no"),
        ("Applies patch", "no"),
        ("Message", message),
    ]

    print(build_banner())
    print()
    print(build_section("Execute adapter"))
    print(build_kv_table(rows))

    if ready and adapter == "prompt_file":
        return 1

    if ready and adapter == "command":
        return 1

    if adapter in _PLANNED_ADAPTERS:
        return 1

    if status == "ready":
        return 1

    return 1


def _build_display_status_and_message(result: dict[str, object]) -> tuple[str, str]:
    adapter = str(result.get("adapter", "") or "")
    status = str(result.get("status", "invalid")).lower()
    ready = bool(result.get("ready"))

    if ready and adapter == "prompt_file":
        return format_error("manual"), "prompt_file is manual. Paste the prompt into your AI tool, then run `strata patch`."

    if ready and adapter == "command":
        return format_error("not_implemented"), "Command execution is not implemented yet."

    if adapter in _PLANNED_ADAPTERS:
        return format_error("not_implemented"), "Adapter is planned. Command execution is not implemented yet."

    if status == "invalid":
        errors = result.get("errors") or []
        if errors:
            return format_error("invalid"), "; ".join(str(error) for error in errors)
        return format_error("invalid"), str(result.get("message", "Adapter configuration is invalid."))

    if not ready:
        errors = result.get("errors") or []
        message = str(result.get("message", "Adapter configuration is not ready."))
        if errors:
            return format_error("not_ready"), f"{message} {'; '.join(str(error) for error in errors)}"
        return format_error("not_ready"), message

    return format_error("not_ready"), str(result.get("message", "Adapter configuration is not ready. Run `strata doctor adapter`."))


def _format_value(value: object) -> object:
    if value is None or value == "":
        return "-"

    return value


def _format_path_or_dash(value: object) -> object:
    if value is None or value == "":
        return "-"

    return format_path(value)


def _format_command(value: object) -> object:
    if value is None or value == "":
        return "-"

    return format_path(value)
