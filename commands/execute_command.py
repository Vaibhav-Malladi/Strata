from __future__ import annotations

from pathlib import Path

from adapter_doctor import check_adapter
from command_executor import DEFAULT_TIMEOUT_SECONDS, execute_command_adapter
from http_adapter_contract import build_http_contract_summary
from workflow_config import load_config
from ui import (
    build_banner,
    build_kv_table,
    build_section,
    format_error,
    format_path,
    format_success,
    format_warning,
)

_PLANNED_COMMAND_ADAPTERS = {"aider", "codex_cli"}
_PLANNED_HTTP_ADAPTERS = {"ollama", "openai_compatible_http"}
_PLANNED_ADAPTERS = _PLANNED_COMMAND_ADAPTERS | _PLANNED_HTTP_ADAPTERS


def write_execute_command(root_path: str = ".") -> int:
    result = check_adapter(root_path)
    adapter = str(result.get("adapter", "") or "")
    adapter_family = str(result.get("adapter_family", "") or "")
    status = str(result.get("status", "invalid")).lower()
    ready = bool(result.get("ready"))
    execution_result = None
    config = None
    timeout_seconds = None
    prompt_exists = False

    try:
        config = load_config(root_path)
    except ValueError:
        config = None
    else:
        if config is not None:
            prompt_config = config.get("prompt_path")
            if isinstance(prompt_config, str) and prompt_config:
                prompt_exists = (Path(root_path) / prompt_config).is_file()

    display_status, message = _build_display_status_and_message(result)
    prompt = _format_path_or_dash(result.get("prompt"))
    patch = _format_path_or_dash(result.get("patch"))
    command = _format_command(result.get("command"))
    timeout = _format_value(config.get("command_timeout_seconds") if config is not None else None)
    base_url = _format_value(config.get("base_url") if config is not None else None)
    api_key_env = _format_value(config.get("api_key_env") if config is not None else None)
    http_timeout = _format_value(config.get("http_timeout_seconds") if config is not None else None)
    http_contract = build_http_contract_summary(config or {}, prompt_exists=prompt_exists)
    executes_command = "no"
    applies_patch = "no"
    return_code = "-"
    patch_status = "-"
    patch_valid = "no"
    targets = "-"
    next_step = None

    if ready and adapter == "command":
        timeout_seconds = config.get("command_timeout_seconds") if config is not None else None
        if type(timeout_seconds) is not int or timeout_seconds <= 0:
            timeout_seconds = DEFAULT_TIMEOUT_SECONDS
        execution_result = execute_command_adapter(
            root_path,
            command=result.get("command"),
            timeout_seconds=timeout_seconds,
        )
        display_status = _format_execution_status(str(execution_result.get("status", "failed")).lower())
        message = str(execution_result.get("message", ""))
        executes_command = "yes" if execution_result.get("executed") else "no"
        return_code = _format_return_code(execution_result.get("returncode"))
        patch_status = _format_patch_status(execution_result.get("patch_status"))
        patch_valid = _format_yes_no(bool(execution_result.get("patch_valid")))
        targets = _format_targets(execution_result.get("targets", []))
        if execution_result.get("status") == "patch_ready":
            next_step = "Run `strata patch`, then `strata apply --dry-run`, then `strata apply`."

    rows = [
        ("Status", display_status),
        ("Mode", _format_value(result.get("mode"))),
        ("Agent", _format_value(result.get("agent"))),
        ("Adapter", _format_value(adapter)),
        ("Prompt", prompt),
        ("Patch", patch),
        ("Command", command),
        ("Timeout seconds", timeout),
        ("Executes command", executes_command),
        ("Applies patch", applies_patch),
        ("Return code", return_code),
        ("Patch status", patch_status),
        ("Patch valid", patch_valid),
        ("Targets", targets),
        ("Message", message),
    ]

    if adapter_family == "http":
        rows.insert(8, ("Base URL", base_url))
        rows.insert(9, ("API key env", api_key_env))
        rows.insert(10, ("HTTP timeout seconds", http_timeout))
        rows.insert(11, ("HTTP request URL", _format_value(http_contract.get("request_url"))))
        rows.insert(12, ("HTTP response text", _format_value(http_contract.get("response_text_path"))))

    if execution_result is None:
        rows[0] = ("Status", display_status)

    if next_step is not None:
        rows.append(("Next", next_step))

    errors = (
        list(execution_result.get("errors", []))
        if execution_result is not None
        else list(result.get("errors", []))
    )

    if errors:
        rows.append(("Errors", _format_notes(errors)))

    if execution_result is not None:
        stdout_preview = _preview_text(execution_result.get("stdout", ""))
        stderr_preview = _preview_text(execution_result.get("stderr", ""))
        if stdout_preview:
            rows.append(("Stdout", stdout_preview))
        if stderr_preview:
            rows.append(("Stderr", stderr_preview))

    print(build_banner())
    print()
    print(build_section("Execute adapter"))
    print(build_kv_table(rows))

    if execution_result is not None and execution_result.get("status") == "patch_ready":
        return 0

    return 1


def _build_display_status_and_message(result: dict[str, object]) -> tuple[str, str]:
    adapter = str(result.get("adapter", "") or "")
    adapter_family = str(result.get("adapter_family", "") or "")
    status = str(result.get("status", "invalid")).lower()
    ready = bool(result.get("ready"))

    if ready and adapter == "prompt_file":
        return format_error("manual"), "prompt_file is manual. Paste the prompt into your AI tool, then run `strata patch`."

    if ready and adapter == "command":
        return format_error("not_implemented"), "Command execution is not implemented yet."

    if adapter in _PLANNED_ADAPTERS:
        if adapter_family == "command":
            return format_error("not_implemented"), "Command-family preset execution is not implemented yet."

        if adapter_family == "http":
            return (
                format_error("not_implemented"),
                "HTTP adapter execution is not implemented yet. "
                "HTTP request/response contract is available locally; network execution is not implemented yet.",
            )

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


def _format_execution_status(status: str) -> str:
    if status == "patch_ready":
        return format_success("patch_ready")

    if status in {"invalid_patch", "command_failed", "timeout", "invalid_command"}:
        return format_error(status)

    if status in {"missing_patch", "empty_patch", "not_ready"}:
        return format_warning(status)

    return format_warning(status)


def _format_return_code(value: object) -> str:
    if value is None:
        return "-"

    return str(value)


def _format_patch_status(value: object) -> str:
    status = str(value).lower()

    if status == "ready":
        return format_success("ready")

    if status == "empty":
        return format_warning("empty")

    if status == "missing":
        return format_warning("missing")

    return format_warning(status or "-")


def _format_yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _format_targets(targets: object) -> str:
    if not targets:
        return "-"

    return ", ".join(str(target) for target in targets)


def _format_notes(notes: object) -> str:
    if not notes:
        return "-"

    return "; ".join(str(note) for note in notes)


def _preview_text(text: object, max_chars: int = 500) -> str:
    if text is None:
        return ""

    normalized = str(text).replace("\r\n", "\n").replace("\r", "\n")
    compact = " | ".join(part.strip() for part in normalized.split("\n") if part.strip())

    if not compact:
        return ""

    if len(compact) <= max_chars:
        return compact

    if max_chars <= 3:
        return compact[:max_chars]

    return compact[: max_chars - 3] + "..."
