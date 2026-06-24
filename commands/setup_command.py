from __future__ import annotations

from http_adapter_contract import normalize_base_url
from adapter_presets import get_adapter_preset
from ollama_adapter import DEFAULT_OLLAMA_BASE_URL, DEFAULT_OLLAMA_MODEL, normalize_ollama_base_url
from ui import (
    build_banner,
    build_kv_table,
    build_section,
    format_error,
    format_path,
    format_success,
    format_warning,
    print_command_header,
    print_next_steps,
    print_status_card,
)
from workflow_config import config_path, load_config, save_config, validate_config

_NEXT_STEPS = [
    'strata run "fix bug"',
    "strata doctor adapter",
    "strata execute --dry-run",
    "strata execute",
    "strata patch",
    "strata apply --dry-run",
    "strata apply",
]

_CANCEL_CHOICES = {"q", "quit", "cancel"}
_CHOICE_LOOKUP = {
    "1": "manual",
    "manual": "manual",
    "prompt_file": "manual",
    "prompt": "manual",
    "file": "manual",
    "2": "command",
    "command": "command",
    "3": "http",
    "http": "http",
    "openai": "http",
    "openai_compatible_http": "http",
    "openai-compatible-http": "http",
    "4": "ollama",
    "ollama": "ollama",
    "5": "aider",
    "aider": "aider",
    "6": "codex_cli",
    "codex": "codex_cli",
    "codex_cli": "codex_cli",
    "codex-cli": "codex_cli",
}


def setup_manual(root: str = ".") -> dict:
    try:
        current = load_config(root)
        updated = dict(current)
        updated["mode"] = _manual_mode(current.get("mode"))
        updated["agent"] = _manual_agent(current.get("agent"))
        updated["adapter"] = "prompt_file"
        updated["command"] = None
        updated["base_url"] = None
        updated["api_key_env"] = None

        normalized = validate_config(updated)
        save_config(normalized, root)
    except ValueError as error:
        return _error_result("prompt_file", "Manual setup failed.", [str(error)])

    result = _result(
        status="configured",
        adapter="prompt_file",
        message="Manual / prompt-file setup saved.",
        changes=[
            f"mode={normalized['mode']}",
            f"agent={normalized['agent']}",
            "adapter=prompt_file",
            "command=null",
            "base_url=null",
            "api_key_env=null",
        ],
        next_steps=_next_steps(),
    )
    _print_setup_summary(root, normalized, result, title="Setup complete")
    return result


def setup_command(root: str = ".", command: str | None = None) -> dict:
    try:
        current = load_config(root)
        updated = dict(current)
        resolved_command = _resolve_optional_text(command, current.get("command"))

        updated["mode"] = _manual_mode(current.get("mode"))
        updated["agent"] = _manual_agent(current.get("agent"))
        updated["adapter"] = "command"
        updated["command"] = resolved_command
        updated["base_url"] = None
        updated["api_key_env"] = None
        updated["command_timeout_seconds"] = _timeout_value(
            current.get("command_timeout_seconds"),
            120,
        )

        normalized = validate_config(updated)
        save_config(normalized, root)
    except ValueError as error:
        return _error_result("command", "Command setup failed.", [str(error)])

    warnings: list[str] = []
    if resolved_command is None:
        warnings.append('No command configured yet. Run `strata config set command "..."`.')

    result = _result(
        status="needs_input" if resolved_command is None else "configured",
        adapter="command",
        message="Command adapter setup saved.",
        changes=[
            f"mode={normalized['mode']}",
            f"agent={normalized['agent']}",
            "adapter=command",
            f"command={normalized['command'] if normalized['command'] is not None else 'null'}",
            "base_url=null",
            "api_key_env=null",
        ],
        warnings=warnings,
        next_steps=_next_steps(),
    )
    _print_setup_summary(root, normalized, result, title="Setup complete")
    return result


def setup_aider(root: str = ".", command: str | None = None) -> dict:
    return _setup_command_preset(
        root,
        preset_name="aider",
        command=command,
        title="Aider preset",
        setup_message="Aider preset setup saved.",
    )


def setup_codex_cli(root: str = ".", command: str | None = None) -> dict:
    return _setup_command_preset(
        root,
        preset_name="codex_cli",
        command=command,
        title="Codex CLI preset",
        setup_message="Codex CLI preset setup saved.",
    )


def setup_http(
    root: str = ".",
    base_url: str | None = None,
    model: str | None = None,
    api_key_env: str | None = None,
) -> dict:
    try:
        current = load_config(root)
        updated = dict(current)
        resolved_base_url = _resolve_optional_text(base_url, current.get("base_url"))
        resolved_model = _resolve_optional_text(model, current.get("model"))
        resolved_api_key_env = _resolve_optional_text(api_key_env, current.get("api_key_env"))

        if resolved_base_url is not None:
            resolved_base_url = normalize_base_url(resolved_base_url)

        updated["mode"] = _manual_mode(current.get("mode"))
        updated["agent"] = _manual_agent(current.get("agent"))
        updated["adapter"] = "openai_compatible_http"
        updated["command"] = None
        updated["base_url"] = resolved_base_url
        updated["api_key_env"] = resolved_api_key_env
        updated["model"] = resolved_model
        updated["http_timeout_seconds"] = _timeout_value(current.get("http_timeout_seconds"), 120)

        normalized = validate_config(updated)
        save_config(normalized, root)
    except ValueError as error:
        return _error_result("openai_compatible_http", "HTTP setup failed.", [str(error)])

    warnings: list[str] = []
    if normalized["base_url"] is None:
        warnings.append("Base URL is not configured yet. Run `strata config set base_url <url>`.")

    result = _result(
        status="needs_input" if normalized["base_url"] is None else "configured",
        adapter="openai_compatible_http",
        message="OpenAI-compatible HTTP setup saved.",
        changes=[
            f"mode={normalized['mode']}",
            f"agent={normalized['agent']}",
            "adapter=openai_compatible_http",
            f"base_url={normalized['base_url'] if normalized['base_url'] is not None else 'null'}",
            f"model={normalized['model'] if normalized['model'] is not None else 'null'}",
            f"api_key_env={normalized['api_key_env'] if normalized['api_key_env'] is not None else 'null'}",
        ],
        warnings=warnings,
        next_steps=_next_steps(),
    )
    _print_setup_summary(root, normalized, result, title="Setup complete")
    return result


def setup_ollama(root: str = ".", model: str | None = None, base_url: str | None = None) -> dict:
    try:
        current = load_config(root)
        updated = dict(current)
        resolved_model = _resolve_optional_text(model, current.get("model"))
        if resolved_model is None:
            resolved_model = DEFAULT_OLLAMA_MODEL

        resolved_base_url = _resolve_optional_text(base_url, current.get("base_url"))
        if resolved_base_url is not None:
            resolved_base_url = normalize_ollama_base_url(resolved_base_url)

        updated["mode"] = _manual_mode(current.get("mode"))
        updated["agent"] = _manual_agent(current.get("agent"))
        updated["adapter"] = "ollama"
        updated["command"] = None
        updated["base_url"] = resolved_base_url
        updated["api_key_env"] = None
        updated["model"] = resolved_model
        updated["http_timeout_seconds"] = _timeout_value(current.get("http_timeout_seconds"), 120)

        normalized = validate_config(updated)
        save_config(normalized, root)
    except ValueError as error:
        return _error_result("ollama", "Ollama setup failed.", [str(error)])

    result = _result(
        status="configured",
        adapter="ollama",
        message="Ollama setup saved.",
        changes=[
            f"mode={normalized['mode']}",
            f"agent={normalized['agent']}",
            "adapter=ollama",
            f"model={normalized['model']}",
            f"base_url={normalized['base_url'] if normalized['base_url'] is not None else 'null'}",
            "api_key_env=null",
        ],
        next_steps=_next_steps(),
    )
    _print_setup_summary(root, normalized, result, title="Setup complete")
    return result


def setup_show(root: str = ".") -> dict:
    try:
        config = load_config(root)
    except ValueError as error:
        result = _error_result("prompt_file", "Setup summary unavailable.", [str(error)])
        _print_setup_summary(root, {}, result, title="Setup summary")
        return result

    result = _result(
        status="configured",
        adapter=str(config.get("adapter", "") or "prompt_file"),
        message="Current setup summary.",
        next_steps=_next_steps(),
    )
    _print_setup_summary(root, config, result, title="Current setup")
    return result


def write_setup_command(root: str = ".") -> int:
    return _run_interactive_setup(root)


def write_setup_summary_command(root: str = ".") -> int:
    setup_show(root)
    return 0


def _run_interactive_setup(root: str) -> int:
    try:
        current = load_config(root)
    except ValueError as error:
        result = _error_result("prompt_file", "Setup failed.", [str(error)])
        _print_setup_summary(root, {}, result, title="Setup error")
        return 1

    print(build_banner())
    print()
    print(build_section("Choose how Strata should work with your AI tool"))
    print(
        build_kv_table(
            [
                ("1. Manual / prompt file", "Best when copying prompts into ChatGPT, Claude, or Copilot."),
                (
                    "2. Command adapter",
                    "Best when a local AI CLI reads .aidc/agent_prompt.md and writes .aidc/agent_patch.diff.",
                ),
                (
                    "3. OpenAI-compatible HTTP",
                    "Best for LM Studio, vLLM, and other compatible servers.",
                ),
                (
                    "4. Ollama",
                    f"Best for local Qwen/Ollama models. Default base URL: {DEFAULT_OLLAMA_BASE_URL}.",
                ),
                (
                    "5. Aider preset",
                    "Best when Aider can write .aidc/agent_patch.diff for a patch-first workflow.",
                ),
                (
                    "6. Codex CLI preset",
                    "Best when your Codex CLI command can write .aidc/agent_patch.diff.",
                ),
            ]
        )
    )

    choice = _prompt_choice(_default_choice(current.get("adapter")))
    if choice is None:
        result = _result(
            status="cancelled",
            adapter=str(current.get("adapter", "") or "prompt_file"),
            message="Setup cancelled.",
            next_steps=_next_steps(),
        )
        _print_setup_summary(root, current, result, title="Setup cancelled")
        return 1

    if choice == "manual":
        result = setup_manual(root)
        return 0 if result["status"] in {"configured", "needs_input"} else 1

    if choice == "command":
        command = _prompt_text(
            "Enter the command string used to write .aidc/agent_patch.diff",
            default=_string_or_empty(current.get("command")),
        )
        if command is None:
            result = _result(
                status="cancelled",
                adapter="command",
                message="Setup cancelled.",
                next_steps=_next_steps(),
            )
            _print_setup_summary(root, current, result, title="Setup cancelled")
            return 1
        result = setup_command(root, command=command or None)
        return 0 if result["status"] in {"configured", "needs_input"} else 1

    if choice == "aider":
        result = setup_aider(root)
        return 0 if result["status"] in {"configured", "needs_input"} else 1

    if choice == "codex_cli":
        result = setup_codex_cli(root)
        return 0 if result["status"] in {"configured", "needs_input"} else 1

    if choice == "http":
        base_url = _prompt_text(
            "Enter the OpenAI-compatible base URL",
            default=_string_or_empty(current.get("base_url")),
            examples=("http://localhost:1234/v1", "http://localhost:8000/v1"),
        )
        if base_url is None:
            result = _result(
                status="cancelled",
                adapter="openai_compatible_http",
                message="Setup cancelled.",
                next_steps=_next_steps(),
            )
            _print_setup_summary(root, current, result, title="Setup cancelled")
            return 1

        model = _prompt_text("Enter the model name", default=_string_or_empty(current.get("model")))
        if model is None:
            result = _result(
                status="cancelled",
                adapter="openai_compatible_http",
                message="Setup cancelled.",
                next_steps=_next_steps(),
            )
            _print_setup_summary(root, current, result, title="Setup cancelled")
            return 1

        api_key_env = _prompt_text(
            "Enter the API key environment variable name",
            default=_string_or_empty(current.get("api_key_env")),
        )
        if api_key_env is None:
            result = _result(
                status="cancelled",
                adapter="openai_compatible_http",
                message="Setup cancelled.",
                next_steps=_next_steps(),
            )
            _print_setup_summary(root, current, result, title="Setup cancelled")
            return 1

        result = setup_http(root, base_url=base_url or None, model=model or None, api_key_env=api_key_env or None)
        return 0 if result["status"] in {"configured", "needs_input"} else 1

    if choice == "ollama":
        model = _prompt_text(
            "Enter the Ollama model name",
            default=_string_or_empty(current.get("model")) or DEFAULT_OLLAMA_MODEL,
        )
        if model is None:
            result = _result(
                status="cancelled",
                adapter="ollama",
                message="Setup cancelled.",
                next_steps=_next_steps(),
            )
            _print_setup_summary(root, current, result, title="Setup cancelled")
            return 1

        base_url = _prompt_text(
            "Enter the Ollama base URL or press Enter to use the default",
            default=_string_or_empty(current.get("base_url")),
        )
        if base_url is None:
            result = _result(
                status="cancelled",
                adapter="ollama",
                message="Setup cancelled.",
                next_steps=_next_steps(),
            )
            _print_setup_summary(root, current, result, title="Setup cancelled")
            return 1

        result = setup_ollama(root, model=model or None, base_url=base_url or None)
        return 0 if result["status"] in {"configured", "needs_input"} else 1

    result = _error_result(
        "prompt_file",
        "Unknown setup choice.",
        [f"Unsupported choice: {choice}"],
    )
    _print_setup_summary(root, current, result, title="Setup error")
    return 1


def _print_setup_summary(root: str, config: dict, result: dict, title: str) -> None:
    print(build_banner())
    print()
    print_command_header("Setup", title, mode="compact")
    print_status_card(
        "Setup summary",
        _build_summary_rows(root, config, result),
        status=_status_marker(result["status"]),
    )
    if result["warnings"]:
        print()
        for warning in result["warnings"]:
            print(format_warning(warning))
    if result["errors"]:
        print()
        for error in result["errors"]:
            print(format_error(error))
    print_next_steps(result["next_steps"])


def _build_summary_rows(root: str, config: dict, result: dict) -> list[tuple[str, object]]:
    return [
        ("Config path", format_path(config_path(root))),
        ("Status", result["status"]),
        ("Adapter", _display_value(config.get("adapter"))),
        ("Mode", _display_value(config.get("mode"))),
        ("Agent", _display_value(config.get("agent"))),
        ("Prompt path", _display_value(config.get("prompt_path"))),
        ("Command", _display_value(config.get("command"), null_text="null")),
        ("Base URL", _display_value(config.get("base_url"), null_text="null")),
        ("Model", _display_value(config.get("model"), null_text="null")),
        ("API key env", _display_value(config.get("api_key_env"), null_text="null")),
        ("Command timeout seconds", _display_value(config.get("command_timeout_seconds"))),
        ("HTTP timeout seconds", _display_value(config.get("http_timeout_seconds"))),
        ("Message", result["message"]),
        ("Changes", ", ".join(result["changes"]) if result["changes"] else "none"),
        ("Warnings", "; ".join(result["warnings"]) if result["warnings"] else "none"),
    ]


def _prompt_choice(default_choice: str) -> str | None:
    prompt = (
        "Choose a setup option "
        f"[{default_choice} / 1 manual / 2 command / 3 http / 4 ollama / 5 aider / 6 codex-cli, q to cancel]: "
    )

    while True:
        raw = input(prompt)
        normalized = raw.strip().lower()

        if not normalized:
            normalized = default_choice

        if normalized in _CANCEL_CHOICES:
            return None

        choice = _CHOICE_LOOKUP.get(normalized)
        if choice is not None:
            return choice

        print(
            format_error(
                "Invalid choice. Enter 1, 2, 3, 4, 5, 6, manual, command, http, ollama, aider, codex, codex_cli, or q."
            )
        )


def _prompt_text(prompt_text: str, *, default: str = "", examples: tuple[str, ...] = ()) -> str | None:
    if examples:
        print("Examples:")
        for example in examples:
            print(f"  {example}")

    suffix = f" [{default}]" if default else ""
    raw = input(f"{prompt_text}{suffix}: ")
    normalized = raw.strip()

    if normalized.lower() in _CANCEL_CHOICES:
        return None

    if not normalized:
        return default

    return normalized


def _default_choice(adapter: object) -> str:
    normalized = _string_or_empty(adapter).lower()
    if normalized in {"command", "openai_compatible_http", "ollama", "aider", "codex_cli"}:
        return {
            "command": "command",
            "openai_compatible_http": "http",
            "ollama": "ollama",
            "aider": "aider",
            "codex_cli": "codex_cli",
        }[normalized]
    return "manual"


def _manual_mode(mode: object) -> str:
    value = _string_or_empty(mode)
    return "hybrid" if value in {"", "manual"} else value


def _manual_agent(agent: object) -> str:
    value = _string_or_empty(agent)
    return "codex" if value in {"", "manual"} else value


def _resolve_optional_text(value: str | None, fallback: object) -> str | None:
    if isinstance(value, str):
        normalized = value.strip()
        if normalized:
            return normalized
        return None

    fallback_text = _string_or_empty(fallback)
    return fallback_text or None


def _timeout_value(value: object, default: int) -> int:
    if type(value) is int and value > 0:
        return value
    return default


def _display_value(value: object, null_text: str = "-") -> object:
    if value is None:
        return null_text
    if isinstance(value, str) and value == "":
        return null_text
    return value


def _string_or_empty(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


def _status_marker(status: str) -> str:
    if status == "configured":
        return format_success("configured")
    if status == "needs_input":
        return format_warning("needs_input")
    if status == "cancelled":
        return format_warning("cancelled")
    return format_error(status)


def _result(
    *,
    status: str,
    adapter: str,
    message: str,
    changes: list[str] | None = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
    next_steps: list[str] | None = None,
) -> dict:
    return {
        "status": status,
        "adapter": adapter,
        "changes": list(changes or []),
        "warnings": list(warnings or []),
        "errors": list(errors or []),
        "message": message,
        "next_steps": list(next_steps or []),
    }


def _error_result(adapter: str, message: str, errors: list[str]) -> dict:
    return _result(
        status="error",
        adapter=adapter,
        message=message,
        errors=errors,
        next_steps=_next_steps(),
    )


def _setup_command_preset(
    root: str,
    *,
    preset_name: str,
    command: str | None,
    title: str,
    setup_message: str,
) -> dict:
    try:
        current = load_config(root)
        preset = get_adapter_preset(preset_name)
        updated = dict(current)
        resolved_command = _resolve_optional_text(command, preset["command"])
        if resolved_command is None:
            resolved_command = str(preset["command"])

        updated["mode"] = _manual_mode(current.get("mode"))
        updated["agent"] = _manual_agent(current.get("agent"))
        updated["adapter"] = str(preset["adapter"])
        updated["command"] = resolved_command
        updated["base_url"] = None
        updated["api_key_env"] = None
        updated["command_timeout_seconds"] = 120

        normalized = validate_config(updated)
        save_config(normalized, root)
    except ValueError as error:
        return _error_result(preset_name, f"{title} setup failed.", [str(error)])

    warnings = [str(preset["warning"])]

    result = _result(
        status="configured",
        adapter=str(preset["adapter"]),
        message=setup_message,
        changes=[
            f"mode={normalized['mode']}",
            f"agent={normalized['agent']}",
            f"adapter={preset['adapter']}",
            f"command={normalized['command'] if normalized['command'] is not None else 'null'}",
            "base_url=null",
            "api_key_env=null",
            "command_timeout_seconds=120",
        ],
        warnings=warnings,
        next_steps=_next_steps(),
    )
    _print_setup_summary(root, normalized, result, title=f"{title} complete")
    return result


def _next_steps() -> list[str]:
    return list(_NEXT_STEPS)
