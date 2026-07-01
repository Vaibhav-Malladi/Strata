from pathlib import Path

from strata.utils.secrets import looks_like_secret
from strata.utils.output import (
    build_banner,
    build_kv_table,
    build_section,
    format_error,
    format_path,
    format_success,
)
from strata.utils.config import (
    CONFIG_KEY_ALIASES,
    SUPPORTED_CONFIG_KEYS,
    config_path,
    ensure_config,
    load_config,
    save_config,
    validate_config,
)

_VALID_KEYS = tuple(sorted({*SUPPORTED_CONFIG_KEYS, *CONFIG_KEY_ALIASES}))

_BOOL_TRUE = {"true", "yes", "on", "1"}
_BOOL_FALSE = {"false", "no", "off", "0"}


def write_config_command(root: str = ".") -> int:
    path = config_path(root)

    try:
        config = load_config(root)
    except ValueError as error:
        print(build_banner())
        print()
        print(build_section("Workflow config error"))
        print(format_error(str(error)))
        return 1

    exists = path.exists()

    print(build_banner())
    print()
    print(build_section("Workflow config"))
    print(
        build_kv_table(
            _config_rows(
                path=path,
                config=config,
                exists=exists,
            )
        )
    )

    return 0


def write_config_init_command(root: str = ".") -> int:
    path = config_path(root)

    try:
        ensure_config(root)
        config = load_config(root)
    except ValueError as error:
        print(build_banner())
        print()
        print(build_section("Workflow config error"))
        print(format_error(str(error)))
        return 1

    print(build_banner())
    print()
    print(build_section("Workflow config initialized"))
    print(
        build_kv_table(
            _config_rows(
                path=path,
                config=config,
                exists=True,
                include_exists=False,
                include_status=True,
            )
        )
    )

    return 0


def write_config_set_command(key: str, value: str, root: str = ".") -> int:
    path = config_path(root)

    try:
        current = load_config(root)
    except ValueError as error:
        print(build_banner())
        print()
        print(build_section("Workflow config error"))
        print(format_error(str(error)))
        return 1

    secret_error = _maybe_reject_secret_config_value(key, value)
    if secret_error is not None:
        print(build_banner())
        print()
        print(build_section("Workflow config error"))
        print(format_error(secret_error))
        print()
        print(_usage_text())
        return 1

    try:
        normalized_key = _normalize_key(key)
        parsed_value = _parse_value(normalized_key, value)
    except ValueError as error:
        print(build_banner())
        print()
        print(build_section("Workflow config error"))
        print(format_error(str(error)))
        print()
        print(_usage_text())
        return 1

    updated = dict(current)
    updated[normalized_key] = parsed_value

    try:
        normalized_config = validate_config(updated)
    except ValueError as error:
        print(build_banner())
        print()
        print(build_section("Workflow config error"))
        print(format_error(str(error)))
        return 1

    try:
        save_config(normalized_config, root)
    except ValueError as error:
        print(build_banner())
        print()
        print(build_section("Workflow config error"))
        print(format_error(str(error)))
        return 1

    print(build_banner())
    print()
    print(build_section("Workflow config updated"))
    print(
        build_kv_table(
            _config_rows(
                path=path,
                config=normalized_config,
                updated_key=normalized_key,
                include_exists=False,
            )
        )
    )

    return 0


def _config_rows(
    *,
    path: Path,
    config: dict,
    exists: bool = False,
    updated_key: str | None = None,
    include_exists: bool = True,
    include_status: bool = False,
) -> list[tuple[str, object]]:
    rows: list[tuple[str, object]] = [("Path", format_path(path))]

    if include_status:
        rows.append(("Status", format_success("initialized")))

    if updated_key is not None:
        rows.append(("Updated", updated_key))

    if include_exists:
        rows.append(("Exists", format_success("yes") if exists else format_error("no")))

    rows.extend(
        [
            ("Mode", config["mode"]),
            ("Agent", config["agent"]),
            ("Adapter", config["adapter"]),
            ("Prompt path", config["prompt_path"]),
            ("Model", config["model"] if config["model"] is not None else "null"),
            ("Command", config["command"] if config["command"] is not None else "null"),
            ("Base URL", config["base_url"] if config["base_url"] is not None else "null"),
            ("API key env", config["api_key_env"] if config["api_key_env"] is not None else "null"),
            ("Command timeout seconds", config["command_timeout_seconds"]),
            ("HTTP timeout seconds", config["http_timeout_seconds"]),
            ("Auto snapshot", _bool_text(config["auto_snapshot"])),
            ("Auto verify", _bool_text(config["auto_verify"])),
            (
                "Require gate before commit",
                _bool_text(config["require_gate_pass_before_commit"]),
            ),
        ]
    )
    return rows


def _bool_text(value: object) -> str:
    return "true" if value is True else "false"


def _normalize_key(key: str) -> str:
    normalized = key.strip().lower()
    canonical = CONFIG_KEY_ALIASES.get(normalized, normalized)

    if canonical not in SUPPORTED_CONFIG_KEYS:
        valid = ", ".join(_VALID_KEYS)
        raise ValueError(f"Unsupported config key: {key}. Valid keys: {valid}")

    return canonical


def _parse_value(key: str, value: str) -> object:
    normalized = value.strip()

    if key == "mode":
        candidate = normalized.lower()
        if candidate not in {"manual", "hybrid", "auto"}:
            raise ValueError("Invalid value for mode. Allowed values: manual, hybrid, auto")
        return candidate

    if key == "agent":
        candidate = normalized.lower()
        if candidate not in {"manual", "local", "codex", "aider"}:
            raise ValueError("Invalid value for agent. Allowed values: manual, local, codex, aider")
        return candidate

    if key == "adapter":
        return normalized

    if key == "prompt_path":
        return normalized

    if key in {"model", "command", "base_url", "api_key_env"}:
        candidate = normalized.lower()
        if candidate in {"null", "none"}:
            return None
        return normalized

    if key in {"command_timeout_seconds", "http_timeout_seconds"}:
        try:
            timeout = int(normalized)
        except ValueError as error:
            raise ValueError(
                f"Invalid value for {key}. Expected an integer between 1 and 3600."
            ) from error

        if timeout <= 0 or timeout > 3600:
            raise ValueError(
                f"Invalid value for {key}. Expected an integer between 1 and 3600."
            )

        return timeout

    return _parse_bool(key, normalized)


def _parse_bool(key: str, value: str) -> bool:
    candidate = value.lower()

    if candidate in _BOOL_TRUE:
        return True

    if candidate in _BOOL_FALSE:
        return False

    raise ValueError(
        f"Invalid boolean value for {key}: {value}. Supported values: true, false, yes, no, on, off, 1, 0"
    )


def _usage_text() -> str:
    return "\n".join(
        [
            "Usage:",
            "  strata config [root]",
            "  strata config init [root]",
            "  strata config set <key> <value> [root]",
            "  strata config set command_timeout_seconds 120",
            "  strata config set http_timeout_seconds 120",
            "  strata config set http_timeout 120",
            "  strata config set base_url http://localhost:1234/v1",
            "  strata config set api_key_env OPENAI_API_KEY",
        ]
    )


def _maybe_reject_secret_config_value(raw_key: str, raw_value: str) -> str | None:
    candidate_key = raw_key.strip().lower()
    candidate_value = raw_value.strip()

    if looks_like_secret(candidate_value):
        return (
            "Do not store raw API keys in Strata config. Store the secret in your user environment, "
            "then set api_key_env to the environment variable name."
        )

    if any(token in candidate_key for token in ("api_key", "token", "secret", "password", "authorization")) and looks_like_secret(candidate_value):
        return (
            "Do not store raw API keys in Strata config. Store the secret in your user environment, "
            "then set api_key_env to the environment variable name."
        )

    return None
