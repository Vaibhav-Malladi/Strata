from pathlib import Path

from ui import (
    build_banner,
    build_kv_table,
    build_section,
    format_error,
    format_path,
    format_success,
)
from workflow_config import config_path, ensure_config, load_config, save_config

_SUPPORTED_KEYS = {
    "mode",
    "agent",
    "auto_snapshot",
    "auto_verify",
    "require_gate_pass_before_commit",
}

_KEY_ALIASES = {
    "require_gate": "require_gate_pass_before_commit",
    "require_gate_pass": "require_gate_pass_before_commit",
    "snapshot": "auto_snapshot",
    "verify": "auto_verify",
}

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
        save_config(updated, root)
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
                config=updated,
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
    canonical = _KEY_ALIASES.get(normalized, normalized)

    if canonical not in _SUPPORTED_KEYS:
        valid = ", ".join(
            [
                "mode",
                "agent",
                "auto_snapshot",
                "auto_verify",
                "require_gate_pass_before_commit",
                "require_gate",
                "require_gate_pass",
                "snapshot",
                "verify",
            ]
        )
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
        ]
    )
