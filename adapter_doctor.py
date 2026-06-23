from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_adapters import (
    DEFAULT_PATCH_PATH,
    DEFAULT_PROMPT_PATH,
    adapter_family,
    prompt_path,
    supported_adapters,
)
from http_adapter_contract import build_http_contract_summary
from workflow_config import load_config

_PLANNED_COMMAND_ADAPTERS = {"aider", "codex_cli"}
_PLANNED_HTTP_ADAPTERS = {"ollama", "openai_compatible_http"}
_PLANNED_ADAPTERS = _PLANNED_COMMAND_ADAPTERS | _PLANNED_HTTP_ADAPTERS
_ALL_SUPPORTED_ADAPTERS = supported_adapters()


def check_adapter(root: str | Path = ".") -> dict[str, Any]:
    root_path = Path(root)

    if not root_path.exists():
        return _build_invalid_result(
            message="Adapter configuration is invalid.",
            errors=[f"Root path does not exist: {root_path}"],
        )

    if not root_path.is_dir():
        return _build_invalid_result(
            message="Adapter configuration is invalid.",
            errors=[f"Root path is not a directory: {root_path}"],
        )

    try:
        config = load_config(root_path)
    except ValueError as error:
        return _build_invalid_result(
            message="Workflow config is invalid.",
            errors=[str(error)],
        )

    adapter = str(config.get("adapter", "") or "")
    mode = str(config.get("mode", "") or "")
    agent = str(config.get("agent", "") or "")
    prompt_config = config.get("prompt_path")
    command_config = config.get("command")

    if adapter not in _ALL_SUPPORTED_ADAPTERS:
        supported = ", ".join(sorted(_ALL_SUPPORTED_ADAPTERS))
        return _build_invalid_result(
            message="Adapter configuration is invalid.",
            errors=[f"Unknown adapter '{adapter}'. Supported adapters: {supported}."],
            adapter=adapter or None,
            mode=mode or None,
            agent=agent or None,
            prompt=_display_prompt(prompt_config),
            patch=_display_patch(),
            command=_display_command(command_config),
            command_timeout_seconds=None,
            adapter_family=None,
            checks=[
                _check("config", "fail", "Workflow config loaded, but the adapter is unsupported."),
            ],
        )

    family = adapter_family(adapter)

    if adapter in _PLANNED_HTTP_ADAPTERS:
        return _check_http(root_path, config, mode, agent, adapter)

    if adapter in _PLANNED_COMMAND_ADAPTERS:
        prompt_display = _display_prompt(prompt_config)
        patch_display = _display_patch()
        check_message = "Command-family preset execution is not implemented yet."
        return _build_result(
            status="not_ready",
            ready=False,
            adapter=adapter,
            adapter_family=family,
            mode=mode,
            agent=agent,
            prompt=prompt_display,
            patch=patch_display,
            command="-",
            command_timeout_seconds=None,
            base_url=None,
            api_key_env=None,
            http_timeout_seconds=None,
            message=check_message,
            checks=[
                _check("config", "pass", "Workflow config loaded."),
                _check("adapter", "info", check_message),
                _check("prompt", "info", "Prompt path is configured."),
                _check("patch", "info", "Patch path is configured."),
            ],
            errors=[check_message],
        )

    if adapter == "prompt_file":
        return _check_prompt_file(root_path, config, mode, agent)

    if adapter == "command":
        return _check_command(root_path, config, mode, agent)

    return _build_invalid_result(
        message="Adapter configuration is invalid.",
        errors=[f"Unknown adapter '{adapter}'."],
        adapter=adapter or None,
        adapter_family=family if adapter else None,
        mode=mode or None,
        agent=agent or None,
        prompt=_display_prompt(prompt_config),
        patch=_display_patch(),
        command=_display_command(command_config),
        command_timeout_seconds=None,
        base_url=None,
        api_key_env=None,
        http_timeout_seconds=None,
    )


def _check_prompt_file(root_path: Path, config: dict[str, Any], mode: str, agent: str) -> dict[str, Any]:
    prompt_config = config.get("prompt_path")
    resolved_prompt_path = prompt_path(root_path, prompt_config)
    prompt_display = _display_prompt(prompt_config)
    patch_display = _display_patch()

    if resolved_prompt_path.exists():
        return _build_result(
            status="ready",
            ready=True,
            adapter="prompt_file",
            adapter_family="prompt_file",
            mode=mode,
            agent=agent,
            prompt=prompt_display,
            patch=patch_display,
            command="-",
            command_timeout_seconds=None,
            base_url=None,
            api_key_env=None,
            http_timeout_seconds=None,
            message="Adapter configuration looks ready.",
            checks=[
                _check("config", "pass", "Workflow config loaded."),
                _check("adapter", "pass", "Adapter is supported."),
                _check("prompt", "pass", "Prompt file exists."),
                _check("patch", "info", "Patch path is configured."),
            ],
        )

    return _build_result(
        status="not_ready",
        ready=False,
        adapter="prompt_file",
        adapter_family="prompt_file",
        mode=mode,
        agent=agent,
        prompt=prompt_display,
        patch=patch_display,
        command="-",
        command_timeout_seconds=None,
        base_url=None,
        api_key_env=None,
        http_timeout_seconds=None,
        message="Adapter configuration is not ready.",
        checks=[
            _check("config", "pass", "Workflow config loaded."),
            _check("adapter", "pass", "Adapter is supported."),
            _check("prompt", "fail", "Prompt file is missing."),
            _check("patch", "info", "Patch path is configured."),
        ],
        errors=[f"Prompt file not found: {prompt_display}"],
    )


def _check_command(root_path: Path, config: dict[str, Any], mode: str, agent: str) -> dict[str, Any]:
    prompt_config = config.get("prompt_path")
    command_config = config.get("command")
    resolved_prompt_path = prompt_path(root_path, prompt_config)
    prompt_display = _display_prompt(prompt_config)
    patch_display = _display_patch()
    command_display = _display_command(command_config)
    timeout_display = _display_timeout(config.get("command_timeout_seconds"))
    errors: list[str] = []
    checks = [
        _check("config", "pass", "Workflow config loaded."),
        _check("adapter", "pass", "Adapter is supported."),
    ]

    if not command_display or command_display == "-":
        errors.append("Command adapter requires a configured command.")
        checks.append(_check("command", "fail", "Command is missing."))
    else:
        checks.append(_check("command", "pass", "Command is configured."))

    checks.append(_check("timeout", "pass", "Command timeout is configured."))

    if resolved_prompt_path.exists():
        checks.append(_check("prompt", "pass", "Prompt file exists."))
    else:
        errors.append(f"Prompt file not found: {prompt_display}")
        checks.append(_check("prompt", "fail", "Prompt file is missing."))

    checks.append(_check("patch", "info", "Patch path is configured."))

    if errors:
        return _build_result(
            status="not_ready",
            ready=False,
            adapter="command",
            adapter_family="command",
            mode=mode,
            agent=agent,
            prompt=prompt_display,
            patch=patch_display,
            command=command_display,
            command_timeout_seconds=timeout_display,
            base_url=None,
            api_key_env=None,
            http_timeout_seconds=None,
            message="Adapter configuration is not ready.",
            checks=checks,
            errors=errors,
        )

    return _build_result(
        status="ready",
        ready=True,
        adapter="command",
        adapter_family="command",
        mode=mode,
        agent=agent,
        prompt=prompt_display,
        patch=patch_display,
        command=command_display,
        command_timeout_seconds=timeout_display,
        base_url=None,
        api_key_env=None,
        http_timeout_seconds=None,
        message="Adapter configuration looks ready.",
        checks=checks,
    )


def _check_http(root_path: Path, config: dict[str, Any], mode: str, agent: str, adapter: str) -> dict[str, Any]:
    prompt_config = config.get("prompt_path")
    prompt_display = _display_prompt(prompt_config)
    patch_display = _display_patch()
    contract = build_http_contract_summary(config, prompt_exists=prompt_path(root_path, prompt_config).exists())
    base_url = contract.get("base_url")
    api_key_env = contract.get("api_key_env")
    http_timeout = contract.get("http_timeout_seconds")
    checks = [
        _check("config", "pass", "Workflow config loaded."),
        _check(
            "adapter",
            "info",
            "HTTP adapter execution is not implemented yet. "
            "HTTP request/response contract is available locally; network execution is not implemented yet.",
        ),
        _check("prompt", "info", "Prompt path is configured."),
        _check("patch", "info", "Patch path is configured."),
    ]
    errors: list[str] = []
    warnings: list[str] = []
    message = (
        "HTTP adapter execution is not implemented yet. "
        "HTTP request/response contract is available locally; network execution is not implemented yet."
    )

    if adapter == "openai_compatible_http":
        if base_url is None:
            errors.append("base_url is required for HTTP adapters.")
            checks.append(_check("base_url", "fail", "base_url is required for HTTP adapters."))
        else:
            checks.append(_check("base_url", "pass", "Base URL is configured."))

        if api_key_env is not None:
            checks.append(
                _check("api_key_env", "info", "API key environment variable name is configured.")
            )
    else:
        if base_url is None:
            warning = "Base URL is not configured. Ollama commonly uses http://localhost:11434."
            warnings.append(warning)
            checks.append(_check("base_url", "info", warning))
        else:
            checks.append(_check("base_url", "pass", "Base URL is configured."))

        if api_key_env is not None:
            checks.append(
                _check("api_key_env", "info", "API key environment variable name is configured.")
            )

        message = (
            "Ollama health checks are not implemented yet. "
            "HTTP request/response contract is available locally; network execution is not implemented yet."
        )

    return _build_result(
        status="not_ready",
        ready=False,
        adapter=adapter,
        adapter_family="http",
        mode=mode,
        agent=agent,
        prompt=prompt_display,
        patch=patch_display,
        command="-",
        command_timeout_seconds=None,
        base_url=base_url,
        api_key_env=api_key_env,
        http_timeout_seconds=http_timeout,
        message=message,
        checks=checks,
        errors=errors,
        warnings=warnings,
    )


def _build_invalid_result(
    *,
    message: str,
    errors: list[str],
    adapter: str | None = None,
    mode: str | None = None,
    agent: str | None = None,
    prompt: str | None = None,
    patch: str | None = None,
    command: str | None = None,
    command_timeout_seconds: int | None = None,
    base_url: str | None = None,
    api_key_env: str | None = None,
    http_timeout_seconds: int | None = None,
    adapter_family: str | None = None,
    checks: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    return _build_result(
        status="invalid",
        ready=False,
        adapter=adapter,
        adapter_family=adapter_family,
        mode=mode,
        agent=agent,
        prompt=prompt,
        patch=patch,
        command=command,
        command_timeout_seconds=command_timeout_seconds,
        base_url=base_url,
        api_key_env=api_key_env,
        http_timeout_seconds=http_timeout_seconds,
        message=message,
        checks=checks
        or [
            _check("config", "fail", "Workflow config could not be loaded."),
        ],
        errors=errors,
    )


def _build_result(
    *,
    status: str,
    ready: bool,
    adapter: str | None,
    adapter_family: str | None,
    mode: str | None,
    agent: str | None,
    prompt: str | None,
    patch: str | None,
    command: str | None,
    command_timeout_seconds: int | None,
    base_url: str | None,
    api_key_env: str | None,
    http_timeout_seconds: int | None,
    message: str,
    checks: list[dict[str, str]],
    errors: list[str] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "ready": ready,
        "adapter": adapter,
        "adapter_family": adapter_family,
        "mode": mode,
        "agent": agent,
        "prompt": prompt,
        "patch": patch,
        "command": command,
        "command_timeout_seconds": command_timeout_seconds,
        "base_url": base_url,
        "api_key_env": api_key_env,
        "http_timeout_seconds": http_timeout_seconds,
        "checks": [dict(check) for check in checks],
        "errors": list(errors or []),
        "warnings": list(warnings or []),
        "message": message,
    }


def _check(name: str, status: str, message: str) -> dict[str, str]:
    return {
        "name": name,
        "status": status,
        "message": message,
    }


def _display_prompt(configured_path: object) -> str:
    if isinstance(configured_path, str) and configured_path:
        return configured_path

    return str(DEFAULT_PROMPT_PATH)


def _display_patch() -> str:
    return str(DEFAULT_PATCH_PATH)


def _display_command(configured_command: object) -> str:
    if isinstance(configured_command, str) and configured_command:
        return configured_command

    return "-"


def _display_optional_string(configured_value: object) -> str | None:
    if isinstance(configured_value, str) and configured_value:
        return configured_value

    return None


def _display_timeout(configured_timeout: object) -> int | None:
    if type(configured_timeout) is int and configured_timeout > 0:
        return configured_timeout

    return None
