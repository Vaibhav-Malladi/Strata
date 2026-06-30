"""Helpers for reading, validating, and persisting local workflow config."""

from collections.abc import Mapping
from copy import deepcopy
import json
import math
from pathlib import Path
from typing import Any

from agent_adapters import validate_adapter_name
from secret_redaction import validate_env_var_name

CONFIG_DIR_NAME = ".aidc"
CONFIG_FILE_NAME = "config.json"

DEFAULT_CONFIG = {
    "mode": "manual",
    "agent": "manual",
    "adapter": "prompt_file",
    "prompt_path": ".aidc/agent_prompt.md",
    "model": None,
    "command": None,
    "base_url": None,
    "api_key_env": None,
    "command_timeout_seconds": 120,
    "http_timeout_seconds": 120,
    "auto_snapshot": True,
    "auto_verify": True,
    "require_gate_pass_before_commit": True,
}

_ALLOWED_MODES = {"manual", "hybrid", "auto"}
_ALLOWED_AGENTS = {"manual", "local", "codex", "aider"}
_CONFIG_KEY_ALIASES = {
    "timeout": "command_timeout_seconds",
    "http_timeout": "http_timeout_seconds",
}
_SAFETY_FLAGS = {
    "auto_snapshot",
    "auto_verify",
    "require_gate_pass_before_commit",
}


def default_config() -> dict:
    """Return a fresh copy of the module defaults."""

    return deepcopy(DEFAULT_CONFIG)


def config_path(root: str | Path = ".") -> Path:
    """Return the config file path without creating anything on disk."""

    return Path(root) / CONFIG_DIR_NAME / CONFIG_FILE_NAME


def load_config(root: str | Path = ".") -> dict:
    """Load the workflow config, filling in missing defaults."""

    path = config_path(root)
    if not path.exists():
        return default_config()

    try:
        raw_text = path.read_text(encoding="utf-8")
        data = json.loads(raw_text)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Invalid workflow config at {path}: {error}") from error

    if not isinstance(data, Mapping):
        raise ValueError(f"Invalid workflow config at {path}: top-level JSON object is required")

    merged = default_config()
    merged.update(data)
    return validate_config(merged)


def save_config(config: Mapping[str, Any], root: str | Path = ".") -> Path:
    """Validate and persist a workflow config as pretty JSON."""

    normalized = validate_config(config)
    path = config_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        payload = json.dumps(
            normalized,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise ValueError(f"Config contains values that are not JSON-compatible: {error}") from error

    path.write_text(payload + "\n", encoding="utf-8")
    return path


def validate_config(config: Mapping[str, Any]) -> dict:
    """Validate a workflow config and return a plain normalized dict."""

    if not isinstance(config, Mapping):
        raise ValueError("config must be a mapping")

    normalized = default_config()

    for key, value in config.items():
        if not isinstance(key, str):
            raise ValueError("config keys must be strings")

        canonical_key = _CONFIG_KEY_ALIASES.get(key, key)

        if canonical_key == "mode":
            normalized[canonical_key] = _validate_mode(value)
        elif canonical_key == "agent":
            normalized[canonical_key] = _validate_agent(value)
        elif canonical_key == "adapter":
            normalized[canonical_key] = validate_adapter_name(value)
        elif canonical_key == "prompt_path":
            normalized[canonical_key] = _validate_nonempty_string(canonical_key, value)
        elif canonical_key == "model":
            normalized[canonical_key] = _validate_optional_nonempty_string(canonical_key, value)
        elif canonical_key == "command":
            normalized[canonical_key] = _validate_optional_nonempty_string(canonical_key, value)
        elif canonical_key == "base_url":
            normalized[canonical_key] = _validate_optional_nonempty_string(canonical_key, value)
        elif canonical_key == "api_key_env":
            normalized[canonical_key] = _validate_api_key_env(value)
        elif canonical_key == "command_timeout_seconds":
            normalized[canonical_key] = _validate_timeout_seconds(canonical_key, value)
        elif canonical_key == "http_timeout_seconds":
            normalized[canonical_key] = _validate_timeout_seconds(canonical_key, value)
        elif canonical_key in _SAFETY_FLAGS:
            normalized[canonical_key] = _validate_bool(canonical_key, value)
        else:
            normalized[canonical_key] = _normalize_json_value(value, canonical_key)

    return normalized


def ensure_config(root: str | Path = ".") -> Path:
    """Create the default config if needed and validate any existing config."""

    path = config_path(root)
    if path.exists():
        load_config(root)
    else:
        save_config(default_config(), root)
    return path


def _validate_mode(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("mode must be a string")
    if value not in _ALLOWED_MODES:
        raise ValueError("mode must be one of: manual, hybrid, auto")
    return value


def _validate_agent(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("agent must be a string")
    if value not in _ALLOWED_AGENTS:
        raise ValueError("agent must be one of: manual, local, codex, aider")
    return value


def _validate_nonempty_string(key: str, value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")

    if not value:
        raise ValueError(f"{key} must be a non-empty string")

    return value


def _validate_optional_nonempty_string(key: str, value: Any) -> str | None:
    if value is None:
        return None

    return _validate_nonempty_string(key, value)


def _validate_api_key_env(value: Any) -> str | None:
    if value is None:
        return None

    if not isinstance(value, str):
        raise ValueError("api_key_env must be a string environment variable name")

    candidate = value.strip()
    if not candidate:
        raise ValueError("api_key_env must be a non-empty string")

    if not validate_env_var_name(candidate):
        raise ValueError(
            "api_key_env must be a valid environment variable name such as OPENAI_API_KEY or ANTHROPIC_API_KEY"
        )

    return candidate


def _validate_timeout_seconds(key: str, value: Any) -> int:
    if type(value) is not int:
        raise ValueError(f"{key} must be an integer")

    if value <= 0:
        raise ValueError(f"{key} must be greater than 0")

    if value > 3600:
        raise ValueError(f"{key} must be at most 3600")

    return value


def _validate_bool(key: str, value: Any) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{key} must be a boolean")
    return value


def _normalize_json_value(value: Any, path: str) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value

    if isinstance(value, int):
        return value

    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} must be a finite number")
        return value

    if isinstance(value, Mapping):
        normalized = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{path} has a non-string key: {key!r}")
            normalized[key] = _normalize_json_value(item, f"{path}.{key}")
        return normalized

    if isinstance(value, list):
        return [
            _normalize_json_value(item, f"{path}[{index}]")
            for index, item in enumerate(value)
        ]

    raise ValueError(f"{path} must be JSON-compatible")
