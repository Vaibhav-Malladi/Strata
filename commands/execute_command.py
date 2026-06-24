from __future__ import annotations

from pathlib import Path

from adapter_doctor import check_adapter
from command_executor import DEFAULT_TIMEOUT_SECONDS, execute_command_adapter
from http_adapter_contract import build_http_contract_summary
from http_executor import execute_openai_compatible_http_adapter
from ollama_adapter import execute_ollama_adapter
from workflow_config import load_config
from ui import (
    format_error,
    format_path,
    format_success,
    format_warning,
    print_banner,
    print_command_header,
    print_lifecycle,
    print_status_card,
    render_step,
    status_spinner,
)

_PLANNED_COMMAND_ADAPTERS = {"aider", "codex_cli"}
_PLANNED_HTTP_ADAPTERS: set[str] = set()
_PLANNED_ADAPTERS = _PLANNED_COMMAND_ADAPTERS | _PLANNED_HTTP_ADAPTERS


def write_execute_command(root_path: str = ".", dry_run: bool = False) -> int:
    result = check_adapter(root_path)
    adapter = str(result.get("adapter", "") or "")
    adapter_family = str(result.get("adapter_family", "") or "")
    ready = bool(result.get("ready"))
    execution_result = None
    config = None
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

    http_contract = build_http_contract_summary(config or {}, prompt_exists=prompt_exists)

    display_status, message = _build_display_status_and_message(result)
    prompt = _format_path_or_dash(result.get("prompt"))
    patch = _format_path_or_dash(result.get("patch"))
    command = _format_command(result.get("command"))
    timeout = _format_value(config.get("command_timeout_seconds") if config is not None else None)
    executes_command = "no"
    executes_http = "no"
    applies_patch = "no"
    return_code = "-"
    http_status = "-"
    patch_status = "-"
    patch_valid = "no"
    targets = "-"
    next_step = None

    if dry_run and ready:
        display_status = format_success("dry-run")
        message = _dry_run_message(adapter, adapter_family)

    if not dry_run:
        if ready and adapter == "command":
            timeout_seconds = config.get("command_timeout_seconds") if config is not None else None
            if type(timeout_seconds) is not int or timeout_seconds <= 0:
                timeout_seconds = DEFAULT_TIMEOUT_SECONDS
            with status_spinner(render_step("Executing adapter", "running")) as spinner:
                execution_result = execute_command_adapter(
                    root_path,
                    command=result.get("command"),
                    timeout_seconds=timeout_seconds,
                )
                spinner.update(render_step("Inspecting patch", "running"))
            display_status = _format_execution_status(str(execution_result.get("status", "failed")).lower())
            message = str(execution_result.get("message", ""))
            executes_command = "yes" if execution_result.get("executed") else "no"
            return_code = _format_return_code(execution_result.get("returncode"))
            patch_status = _format_patch_status(execution_result.get("patch_status"))
            patch_valid = _format_yes_no(bool(execution_result.get("patch_valid")))
            targets = _format_targets(execution_result.get("targets", []))
            if execution_result.get("status") == "patch_ready":
                next_step = "Run `strata patch`, then `strata apply --dry-run`, then `strata apply`."

        if ready and adapter == "ollama":
            with status_spinner(render_step("Executing adapter", "running")) as spinner:
                execution_result = execute_ollama_adapter(root_path, config=config or {})
                spinner.update(render_step("Inspecting patch", "running"))
            display_status = _format_execution_status(str(execution_result.get("status", "failed")).lower())
            message = str(execution_result.get("message", ""))
            executes_http = "yes" if execution_result.get("executed") else "no"
            http_status = _format_return_code(execution_result.get("http_status"))
            patch_status = _format_patch_status(execution_result.get("patch_status"))
            patch_valid = _format_yes_no(bool(execution_result.get("patch_valid")))
            targets = _format_targets(execution_result.get("targets", []))
            if execution_result.get("status") == "patch_ready":
                next_step = "Run `strata patch`, then `strata apply --dry-run`, then `strata apply`."

        if ready and adapter == "openai_compatible_http":
            with status_spinner(render_step("Executing adapter", "running")) as spinner:
                execution_result = execute_openai_compatible_http_adapter(root_path, config=config or {})
                spinner.update(render_step("Inspecting patch", "running"))
            display_status = _format_execution_status(str(execution_result.get("status", "failed")).lower())
            message = str(execution_result.get("message", ""))
            executes_http = "yes" if execution_result.get("executed") else "no"
            http_status = _format_return_code(execution_result.get("http_status"))
            patch_status = _format_patch_status(execution_result.get("patch_status"))
            patch_valid = _format_yes_no(bool(execution_result.get("patch_valid")))
            targets = _format_targets(execution_result.get("targets", []))
            if execution_result.get("status") == "patch_ready":
                next_step = "Run `strata patch`, then `strata apply --dry-run`, then `strata apply`."

    if adapter == "ollama":
        rows = _build_ollama_rows(
            result=result,
            message=message,
            executes_http=executes_http,
            applies_patch=applies_patch,
            http_status=http_status,
            patch_status=patch_status,
            patch_valid=patch_valid,
            targets=targets,
        )
    elif adapter_family == "http":
        rows = _build_http_rows(
            result=result,
            http_contract=http_contract,
            message=message,
            executes_http=executes_http,
            applies_patch=applies_patch,
            http_status=http_status,
            patch_status=patch_status,
            patch_valid=patch_valid,
            targets=targets,
        )
    else:
        rows = [
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

    print_banner()
    print_command_header("Execute", "Patch-first adapter execution", mode="compact")
    print_lifecycle(
        "Lifecycle",
        [
            "Check adapter readiness",
            "Run configured adapter",
            "Inspect generated patch",
            "Report next step",
        ],
    )
    print_status_card("Execute adapter", rows, status=display_status)

    if dry_run:
        return 0 if ready else 1

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

    if ready and adapter == "openai_compatible_http":
        return format_success("ready"), "HTTP adapter appears ready for execution."

    if ready and adapter == "ollama":
        return format_success("ready"), "Ollama adapter appears ready. Runtime availability is checked during execute."

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

    if status in {
        "invalid_patch",
        "command_failed",
        "timeout",
        "invalid_command",
        "http_error",
        "missing_api_key",
        "invalid_json",
        "invalid_response",
        "missing_base_url",
        "missing_prompt",
    }:
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


def _build_ollama_rows(
    *,
    result: dict[str, object],
    message: str,
    executes_http: str,
    applies_patch: str,
    http_status: str,
    patch_status: str,
    patch_valid: str,
    targets: str,
) -> list[tuple[str, object]]:
    rows = [
        ("Mode", _format_value(result.get("mode"))),
        ("Agent", _format_value(result.get("agent"))),
        ("Adapter", _format_value(result.get("adapter"))),
        ("Adapter family", _format_value(result.get("adapter_family"))),
        ("Prompt", _format_path_or_dash(result.get("prompt"))),
        ("Patch", _format_path_or_dash(result.get("patch"))),
        ("Base URL", _format_value(result.get("base_url"))),
        ("URL", "/api/generate"),
        ("Model", _format_value(result.get("model"))),
        ("HTTP timeout seconds", _format_value(result.get("http_timeout_seconds"))),
        ("Executes HTTP", executes_http),
        ("Applies patch", applies_patch),
        ("HTTP status", http_status),
        ("Patch status", patch_status),
        ("Patch valid", patch_valid),
        ("Targets", targets),
        ("Message", message),
    ]

    return rows


def _build_http_rows(
    *,
    result: dict[str, object],
    http_contract: dict[str, object],
    message: str,
    executes_http: str,
    applies_patch: str,
    http_status: str,
    patch_status: str,
    patch_valid: str,
    targets: str,
) -> list[tuple[str, object]]:
    rows = [
        ("Mode", _format_value(result.get("mode"))),
        ("Agent", _format_value(result.get("agent"))),
        ("Adapter", _format_value(result.get("adapter"))),
        ("Adapter family", _format_value(result.get("adapter_family"))),
        ("Prompt", _format_path_or_dash(result.get("prompt"))),
        ("Prompt exists", _format_yes_no(bool(http_contract.get("prompt_exists")))),
        ("Patch", _format_path_or_dash(result.get("patch"))),
        ("Base URL", _format_value(http_contract.get("base_url"))),
        ("URL", _format_value(http_contract.get("request_url"))),
        ("Model", _format_value(http_contract.get("model"))),
        ("API key env", _format_value(http_contract.get("api_key_env"))),
        ("HTTP timeout seconds", _format_value(http_contract.get("http_timeout_seconds"))),
        ("Executes HTTP", executes_http),
        ("Applies patch", applies_patch),
        ("HTTP status", http_status),
        ("Patch status", patch_status),
        ("Patch valid", patch_valid),
        ("Targets", targets),
        ("Message", message),
    ]

    return rows


def _dry_run_message(adapter: str, adapter_family: str) -> str:
    if adapter == "ollama":
        return "Ollama request is ready. No HTTP request was made."

    if adapter_family == "http":
        return "Dry run only. No HTTP request was made."

    if adapter == "command":
        return "Dry run only. No command was executed."

    if adapter == "prompt_file":
        return "Dry run only. Prompt file execution was not started."

    return "Dry run only. No execution was performed."


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
