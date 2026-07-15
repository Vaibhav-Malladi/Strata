from collections.abc import Mapping

from strata.core.capability_profiles import (
    CAPABILITY_TIERS,
    CAPABILITY_TIER_UNKNOWN,
    get_capability_profile,
    get_conservative_unknown_profile,
    with_capability_overrides,
)
from strata.core.delivery_surfaces import DELIVERY_SURFACE_BROWSER_COPY, DELIVERY_SURFACES


USER_SETTINGS_SCHEMA_VERSION = 1

CAPABILITY_SELECTION_AUTO = "auto"
CAPABILITY_SELECTION_UNKNOWN = "unknown"
CAPABILITY_SELECTION_WEAK = "weak"
CAPABILITY_SELECTION_MEDIUM = "medium"
CAPABILITY_SELECTION_STRONG = "strong"
CAPABILITY_SELECTIONS = (
    CAPABILITY_SELECTION_AUTO,
    CAPABILITY_SELECTION_UNKNOWN,
    CAPABILITY_SELECTION_WEAK,
    CAPABILITY_SELECTION_MEDIUM,
    CAPABILITY_SELECTION_STRONG,
)

SELECTION_SOURCE_MANUAL = "manual"
SELECTION_SOURCE_DETECTED = "detected"
SELECTION_SOURCE_UNKNOWN_FALLBACK = "unknown_fallback"
SELECTION_SOURCES = (
    SELECTION_SOURCE_MANUAL,
    SELECTION_SOURCE_DETECTED,
    SELECTION_SOURCE_UNKNOWN_FALLBACK,
)

USER_SETTINGS_FIELD_ORDER = (
    "schema_version",
    "capability_selection",
    "delivery_surface",
    "profile_overrides",
)

PROFILE_OVERRIDE_FIELDS = (
    "preferred_context_variant",
    "max_recommended_files",
)


def _validate_choice(value, field_name: str, choices: tuple[str, ...]) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string.")
    if value not in choices:
        raise ValueError(f"{field_name} must be one of: {', '.join(choices)}.")
    return value


def _validate_schema_version(value) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("schema_version must be an integer.")
    if value != USER_SETTINGS_SCHEMA_VERSION:
        raise ValueError("schema_version is unsupported.")
    return value


def _validate_settings_fields(settings: Mapping) -> None:
    for key in settings:
        if not isinstance(key, str):
            raise ValueError("user settings keys must be strings.")
    keys = set(settings.keys())
    required = set(USER_SETTINGS_FIELD_ORDER)
    missing = sorted(required - keys)
    extras = sorted(keys - required)
    if missing:
        raise ValueError(f"user settings missing required field: {missing[0]}")
    if extras:
        raise ValueError(f"Unsupported user settings field: {extras[0]}")


def _validate_overrides(profile_overrides) -> dict[str, object]:
    if not isinstance(profile_overrides, Mapping):
        raise ValueError("profile_overrides must be a mapping.")
    extras = sorted(str(key) for key in profile_overrides if key not in PROFILE_OVERRIDE_FIELDS)
    if extras:
        raise ValueError(f"Unsupported profile override field: {extras[0]}")

    normalized = {}
    for field in PROFILE_OVERRIDE_FIELDS:
        if field in profile_overrides:
            normalized[field] = _copy_json_value(profile_overrides[field])

    with_capability_overrides(get_conservative_unknown_profile(), **normalized)
    return normalized


def _copy_json_mapping(mapping, field_name: str) -> dict[str, object]:
    if not isinstance(mapping, Mapping):
        raise ValueError(f"{field_name} must be a mapping.")
    copied = {}
    for key in mapping:
        if not isinstance(key, str):
            raise ValueError(f"{field_name} keys must be strings.")
    for key in mapping:
        copied[key] = _copy_json_value(mapping[key])
    return copied


def _validate_json_ready(value) -> None:
    if _copy_json_value(value) is _UNSUPPORTED:
        raise ValueError("user settings result must be JSON-ready.")


_UNSUPPORTED = object()


def _copy_json_value(value):
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, list):
        copied = []
        for item in value:
            rendered = _copy_json_value(item)
            if rendered is _UNSUPPORTED:
                return _UNSUPPORTED
            copied.append(rendered)
        return copied
    if isinstance(value, Mapping):
        copied = {}
        for key in value:
            if not isinstance(key, str):
                return _UNSUPPORTED
            rendered = _copy_json_value(value[key])
            if rendered is _UNSUPPORTED:
                return _UNSUPPORTED
            copied[key] = rendered
        return copied
    return _UNSUPPORTED


def default_user_settings() -> dict[str, object]:
    settings = {
        "schema_version": USER_SETTINGS_SCHEMA_VERSION,
        "capability_selection": CAPABILITY_SELECTION_AUTO,
        "delivery_surface": DELIVERY_SURFACE_BROWSER_COPY,
        "profile_overrides": {},
    }
    _validate_json_ready(settings)
    return settings


def validate_user_settings(settings) -> dict[str, object]:
    if not isinstance(settings, Mapping):
        raise ValueError("settings must be a mapping.")
    _validate_settings_fields(settings)

    normalized = {
        "schema_version": _validate_schema_version(settings["schema_version"]),
        "capability_selection": _validate_choice(
            settings["capability_selection"],
            "capability_selection",
            CAPABILITY_SELECTIONS,
        ),
        "delivery_surface": _validate_choice(
            settings["delivery_surface"],
            "delivery_surface",
            DELIVERY_SURFACES,
        ),
        "profile_overrides": _validate_overrides(settings["profile_overrides"]),
    }
    _validate_json_ready(normalized)
    return normalized


def update_user_settings(
    settings,
    changes,
) -> dict[str, object]:
    current = validate_user_settings(settings)
    if not isinstance(changes, Mapping):
        raise ValueError("changes must be a mapping.")
    supported_changes = {
        "capability_selection",
        "delivery_surface",
        "profile_overrides",
    }
    extras = sorted(str(key) for key in changes if key not in supported_changes)
    if extras:
        raise ValueError(f"Unsupported user settings update field: {extras[0]}")

    merged = _copy_json_mapping(current, "settings")
    for key in supported_changes:
        if key in changes:
            merged[key] = _copy_json_value(changes[key])
    return validate_user_settings(merged)


def resolve_user_capability(
    settings,
    *,
    detected_tier=None,
) -> dict[str, object]:
    normalized = validate_user_settings(settings)
    selected_tier, source = _resolve_tier(
        normalized["capability_selection"],
        detected_tier,
    )
    profile = get_capability_profile(selected_tier)
    overrides = normalized["profile_overrides"]
    if overrides:
        profile = with_capability_overrides(profile, **overrides)

    result = {
        "selected_tier": selected_tier,
        "selection_source": source,
        "profile": profile.to_dict(),
        "profile_overrides_applied": bool(overrides),
        "metadata": {
            "configured_selection": normalized["capability_selection"],
            "detected_tier": detected_tier,
        },
    }
    _validate_json_ready(result)
    return result


def _resolve_tier(configured_selection: str, detected_tier) -> tuple[str, str]:
    if configured_selection != CAPABILITY_SELECTION_AUTO:
        return configured_selection, SELECTION_SOURCE_MANUAL
    if detected_tier is None:
        return CAPABILITY_TIER_UNKNOWN, SELECTION_SOURCE_UNKNOWN_FALLBACK
    detected = _validate_choice(detected_tier, "detected_tier", CAPABILITY_TIERS)
    return detected, SELECTION_SOURCE_DETECTED
