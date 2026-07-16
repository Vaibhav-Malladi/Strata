from __future__ import annotations

from collections.abc import Mapping

import strata.core.delivery_surfaces as delivery_surfaces
import strata.core.user_settings as user_settings
import strata.utils.config as workflow_config


CONFIG_USER_SETTINGS_KEY = "user_settings"

SETTING_CAPABILITY = "capability"
SETTING_SURFACE = "surface"
SETTING_MODE = "mode"
SUPPORTED_SETTINGS = (
    SETTING_CAPABILITY,
    SETTING_SURFACE,
    SETTING_MODE,
)

SETTING_FIELDS = {
    SETTING_CAPABILITY: "capability_selection",
    SETTING_SURFACE: "delivery_surface",
    SETTING_MODE: "mode",
}
SETTING_LABELS = {
    SETTING_CAPABILITY: "Capability selection",
    SETTING_SURFACE: "Delivery surface",
    SETTING_MODE: "Workflow mode",
}
VALUE_LABELS = {
    "auto": "Automatic",
    "unknown": "Unknown",
    "weak": "Weak",
    "medium": "Medium",
    "strong": "Strong",
    "browser_copy": "Browser copy",
    "cli": "CLI",
    "vscode": "VS Code",
    "manual": "Manual",
    "hybrid": "Balanced",
}
SETTING_VALUES = {
    SETTING_CAPABILITY: user_settings.CAPABILITY_SELECTIONS,
    SETTING_SURFACE: delivery_surfaces.DELIVERY_SURFACES,
    SETTING_MODE: ("manual", "hybrid", "auto"),
}


def _normalize_setting_name(setting: str) -> str:
    normalized = str(setting or "").strip().lower()
    if normalized not in SUPPORTED_SETTINGS:
        raise ValueError(
            f"Unknown setting: {setting}\n"
            f"Supported settings: {', '.join(SUPPORTED_SETTINGS)}"
        )
    return normalized


def _normalize_setting_value(setting: str, value: str) -> str:
    normalized = str(value or "").strip().lower()
    allowed = SETTING_VALUES[setting]
    if normalized not in allowed:
        label = {
            SETTING_CAPABILITY: "capability value",
            SETTING_SURFACE: "delivery surface",
            SETTING_MODE: "workflow mode",
        }[setting]
        raise ValueError(
            f"Invalid {label}: {value}\n"
            f"Choose one of: {', '.join(allowed)}"
        )
    return normalized


def _settings_from_config(config: Mapping[str, object]) -> dict[str, object]:
    raw_settings = config.get(CONFIG_USER_SETTINGS_KEY)
    if raw_settings is None:
        return user_settings.default_user_settings()

    try:
        return user_settings.validate_user_settings(raw_settings)
    except ValueError as error:
        raise ValueError(f"Invalid saved user settings: {error}") from error


def _display_value(value: object) -> str:
    return VALUE_LABELS.get(str(value), str(value))


def _display_path(root: str = ".") -> str:
    return str(workflow_config.config_path(root)).replace("\\", "/")


def _validate_workflow_mode(mode: object) -> str:
    return workflow_config.validate_config({"mode": mode})["mode"]


def render_settings_summary(
    settings,
    *,
    workflow_mode: object | None = None,
    config_location: str = ".aidc/config.json",
) -> str:
    normalized = user_settings.validate_user_settings(settings)
    lines = [
        "Strata settings",
        "",
        f"Config file: {config_location}",
        "",
        f"Capability selection: {_display_value(normalized['capability_selection'])}",
        f"Delivery surface: {_display_value(normalized['delivery_surface'])}",
    ]
    if workflow_mode is not None:
        lines.append(f"Workflow mode: {_display_value(_validate_workflow_mode(workflow_mode))}")
    lines.extend(
        [
            "",
            "Next step",
            "Run `strata settings set <setting> <value>` to change one setting.",
        ]
    )
    return "\n".join(lines) + "\n"


def render_setting_change(
    setting: str,
    old_value: object,
    new_value: object,
    *,
    config_location: str = ".aidc/config.json",
) -> str:
    setting_name = _normalize_setting_name(setting)
    return (
        "Setting updated\n"
        "\n"
        f"{SETTING_LABELS[setting_name]}\n"
        f"{_display_value(old_value)} -> {_display_value(new_value)}\n"
        "\n"
        f"Saved in: {config_location}\n"
        "\n"
        "Next step\n"
        "Run `strata start` to continue with the new setting.\n"
    )


def render_setting_noop(
    setting: str,
    value: object,
    *,
    config_location: str = ".aidc/config.json",
) -> str:
    setting_name = _normalize_setting_name(setting)
    return (
        f"{SETTING_LABELS[setting_name]} is already set to {_display_value(value)}.\n"
        "\n"
        f"Config file: {config_location}\n"
        "\n"
        "Next step\n"
        "Run `strata start` to continue with the new setting.\n"
    )


def load_settings(root: str = ".") -> dict[str, object]:
    config = workflow_config.load_config(root)
    return _settings_from_config(config)


def update_setting(root: str, setting: str, value: str) -> dict[str, object]:
    setting_name = _normalize_setting_name(setting)
    normalized_value = _normalize_setting_value(setting_name, value)
    field_name = SETTING_FIELDS[setting_name]

    config = workflow_config.load_config(root)
    if setting_name == SETTING_MODE:
        old_value = config[field_name]
        if old_value == normalized_value:
            return {
                "setting": setting_name,
                "field": field_name,
                "old_value": old_value,
                "new_value": old_value,
                "saved": False,
            }

        updated_config = dict(config)
        updated_config[field_name] = normalized_value
        normalized_config = workflow_config.validate_config(updated_config)
        workflow_config.save_config(normalized_config, root)
        return {
            "setting": setting_name,
            "field": field_name,
            "old_value": old_value,
            "new_value": normalized_config[field_name],
            "saved": True,
        }

    current_settings = _settings_from_config(config)
    old_value = current_settings[field_name]

    updated_settings = user_settings.update_user_settings(
        current_settings,
        {field_name: normalized_value},
    )
    new_value = updated_settings[field_name]

    if old_value == new_value:
        return {
            "setting": setting_name,
            "field": field_name,
            "old_value": old_value,
            "new_value": new_value,
            "saved": False,
        }

    updated_config = dict(config)
    updated_config[CONFIG_USER_SETTINGS_KEY] = updated_settings
    workflow_config.save_config(updated_config, root)

    return {
        "setting": setting_name,
        "field": field_name,
        "old_value": old_value,
        "new_value": new_value,
        "saved": True,
    }


def write_settings_command(root: str = ".") -> int:
    try:
        config = workflow_config.load_config(root)
        settings = _settings_from_config(config)
    except ValueError as error:
        print("Strata settings")
        print()
        print(str(error))
        return 1

    print(
        render_settings_summary(
            settings,
            workflow_mode=config.get("mode"),
            config_location=_display_path(root),
        ),
        end="",
    )
    return 0


def write_settings_set_command(setting: str, value: str, root: str = ".") -> int:
    try:
        result = update_setting(root, setting, value)
    except ValueError as error:
        print(str(error))
        return 1

    if result["saved"]:
        print(
            render_setting_change(
                str(result["setting"]),
                result["old_value"],
                result["new_value"],
                config_location=_display_path(root),
            ),
            end="",
        )
    else:
        print(
            render_setting_noop(
                str(result["setting"]),
                result["new_value"],
                config_location=_display_path(root),
            ),
            end="",
        )
    return 0
