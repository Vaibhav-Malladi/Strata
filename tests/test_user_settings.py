import copy
import json

import strata.core.user_settings as user_settings
from strata.core.capability_profiles import (
    CAPABILITY_TIER_UNKNOWN,
    MAX_RECOMMENDED_FILES_LIMIT,
    get_capability_profile,
)
from strata.core.delivery_surfaces import DELIVERY_SURFACES
from strata.core.user_settings import (
    CAPABILITY_SELECTION_AUTO,
    CAPABILITY_SELECTIONS,
    SELECTION_SOURCES,
    default_user_settings,
    resolve_user_capability,
    update_user_settings,
    validate_user_settings,
)


def test_default_settings_are_json_ready():
    settings = default_user_settings()

    assert json.loads(json.dumps(settings, allow_nan=False)) == settings
    assert _is_json_ready(settings)


def test_defaults_are_fresh_and_deterministic():
    first = default_user_settings()
    second = default_user_settings()

    assert first == second
    assert first is not second
    assert first["profile_overrides"] is not second["profile_overrides"]


def test_default_capability_selection_is_auto():
    assert default_user_settings()["capability_selection"] == CAPABILITY_SELECTION_AUTO


def test_supported_selections_are_stable():
    assert CAPABILITY_SELECTIONS == ("auto", "unknown", "weak", "medium", "strong")


def test_supported_delivery_surfaces_reuse_o5_vocabulary():
    assert validate_user_settings(default_user_settings())["delivery_surface"] in DELIVERY_SURFACES


def test_manual_weak_selection_resolves_weak():
    assert _resolve_manual("weak")["selected_tier"] == "weak"


def test_manual_medium_selection_resolves_medium():
    assert _resolve_manual("medium")["selected_tier"] == "medium"


def test_manual_strong_selection_resolves_strong():
    assert _resolve_manual("strong")["selected_tier"] == "strong"


def test_manual_unknown_selection_resolves_unknown():
    assert _resolve_manual("unknown")["selected_tier"] == "unknown"


def test_manual_selection_ignores_detected_tier():
    result = resolve_user_capability(
        update_user_settings(default_user_settings(), {"capability_selection": "weak"}),
        detected_tier="strong",
    )

    assert result["selected_tier"] == "weak"
    assert result["selection_source"] == "manual"


def test_auto_with_detected_weak_resolves_weak():
    assert resolve_user_capability(default_user_settings(), detected_tier="weak")["selected_tier"] == "weak"


def test_auto_with_detected_medium_resolves_medium():
    assert resolve_user_capability(default_user_settings(), detected_tier="medium")["selected_tier"] == "medium"


def test_auto_with_detected_strong_resolves_strong():
    assert resolve_user_capability(default_user_settings(), detected_tier="strong")["selected_tier"] == "strong"


def test_auto_without_detection_resolves_conservative_unknown():
    result = resolve_user_capability(default_user_settings())

    assert result["selected_tier"] == CAPABILITY_TIER_UNKNOWN
    assert result["selection_source"] == "unknown_fallback"
    assert result["profile"] == get_capability_profile(CAPABILITY_TIER_UNKNOWN).to_dict()


def test_invalid_detected_tier_raises_value_error():
    _assert_value_error(lambda: resolve_user_capability(default_user_settings(), detected_tier="premium"))


def test_selection_source_is_stable():
    assert SELECTION_SOURCES == ("manual", "detected", "unknown_fallback")
    assert resolve_user_capability(default_user_settings(), detected_tier="unknown")["selection_source"] == "detected"


def test_empty_profile_overrides_preserve_base_profile():
    settings = update_user_settings(
        default_user_settings(),
        {"capability_selection": "medium", "profile_overrides": {}},
    )
    result = resolve_user_capability(settings)

    assert result["profile"] == get_capability_profile("medium").to_dict()
    assert result["profile_overrides_applied"] is False


def test_valid_o1_override_is_applied():
    settings = update_user_settings(
        default_user_settings(),
        {
            "capability_selection": "medium",
            "profile_overrides": {
                "preferred_context_variant": "compact",
                "max_recommended_files": 4,
            },
        },
    )
    result = resolve_user_capability(settings)

    assert result["profile"]["preferred_context_variant"] == "compact"
    assert result["profile"]["max_recommended_files"] == 4
    assert result["profile_overrides_applied"] is True


def test_invalid_o1_override_is_rejected():
    _assert_value_error(
        lambda: update_user_settings(
            default_user_settings(),
            {"profile_overrides": {"max_recommended_files": MAX_RECOMMENDED_FILES_LIMIT + 1}},
        )
    )


def test_builtin_o1_profile_is_not_mutated_by_override():
    before = get_capability_profile("medium").to_dict()
    settings = update_user_settings(
        default_user_settings(),
        {"capability_selection": "medium", "profile_overrides": {"max_recommended_files": 4}},
    )

    resolve_user_capability(settings)

    assert get_capability_profile("medium").to_dict() == before


def test_settings_can_be_changed_after_creation():
    settings = update_user_settings(default_user_settings(), {"capability_selection": "strong"})

    assert settings["capability_selection"] == "strong"


def test_partial_update_preserves_unchanged_fields():
    settings = default_user_settings()
    updated = update_user_settings(settings, {"delivery_surface": "cli"})

    assert updated["capability_selection"] == settings["capability_selection"]
    assert updated["delivery_surface"] == "cli"


def test_empty_profile_overrides_clears_previous_overrides():
    settings = update_user_settings(
        default_user_settings(),
        {"profile_overrides": {"max_recommended_files": 4}},
    )
    updated = update_user_settings(settings, {"profile_overrides": {}})

    assert updated["profile_overrides"] == {}


def test_unsupported_settings_field_raises_value_error():
    settings = default_user_settings()
    settings["api_key"] = "secret"

    _assert_value_error(lambda: validate_user_settings(settings))


def test_unsupported_update_field_raises_value_error():
    _assert_value_error(lambda: update_user_settings(default_user_settings(), {"model": "gpt-test"}))


def test_invalid_delivery_surface_raises_value_error():
    _assert_value_error(lambda: update_user_settings(default_user_settings(), {"delivery_surface": "web_chat"}))


def test_inputs_are_not_mutated():
    settings = update_user_settings(
        default_user_settings(),
        {"profile_overrides": {"max_recommended_files": 4}},
    )
    changes = {"profile_overrides": {}}
    before = (copy.deepcopy(settings), copy.deepcopy(changes))

    update_user_settings(settings, changes)

    assert (settings, changes) == before


def test_repeated_resolution_is_deterministic():
    settings = update_user_settings(default_user_settings(), {"capability_selection": "auto"})

    assert resolve_user_capability(settings, detected_tier="medium") == resolve_user_capability(
        settings,
        detected_tier="medium",
    )


def test_no_api_key_or_secret_field_exists():
    settings = default_user_settings()
    result = resolve_user_capability(settings)
    text = json.dumps({"settings": settings, "result": result}, sort_keys=True).lower()

    for forbidden in ("api_key", "token", "password", "credential", "secret"):
        assert forbidden not in text


def test_no_filesystem_environment_network_or_subprocess_access_is_required():
    public_names = {
        name
        for name in vars(user_settings)
        if not name.startswith("_")
    }

    for forbidden in ("Path", "open", "os", "environ", "subprocess", "requests", "socket"):
        assert forbidden not in public_names


def test_no_import_from_strata_patch_or_commands_exists():
    module_names = json.dumps(sorted(vars(user_settings)), sort_keys=True)

    assert "strata.patch" not in module_names
    assert "strata.commands" not in module_names


def test_package_layering_invariant_has_no_new_violation():
    assert user_settings.__name__ == "strata.core.user_settings"
    assert "patch" not in {name for name in vars(user_settings) if not name.startswith("_")}


def _resolve_manual(selection: str) -> dict[str, object]:
    settings = update_user_settings(default_user_settings(), {"capability_selection": selection})
    result = resolve_user_capability(settings, detected_tier="strong")
    assert result["selection_source"] == "manual"
    return result


def _assert_value_error(call) -> None:
    try:
        call()
    except ValueError:
        return
    raise AssertionError("Expected ValueError")


def _is_json_ready(value) -> bool:
    if value is None or isinstance(value, (str, int, bool)):
        return True
    if isinstance(value, list):
        return all(_is_json_ready(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _is_json_ready(item) for key, item in value.items())
    return False


TESTS = [
    test_default_settings_are_json_ready,
    test_defaults_are_fresh_and_deterministic,
    test_default_capability_selection_is_auto,
    test_supported_selections_are_stable,
    test_supported_delivery_surfaces_reuse_o5_vocabulary,
    test_manual_weak_selection_resolves_weak,
    test_manual_medium_selection_resolves_medium,
    test_manual_strong_selection_resolves_strong,
    test_manual_unknown_selection_resolves_unknown,
    test_manual_selection_ignores_detected_tier,
    test_auto_with_detected_weak_resolves_weak,
    test_auto_with_detected_medium_resolves_medium,
    test_auto_with_detected_strong_resolves_strong,
    test_auto_without_detection_resolves_conservative_unknown,
    test_invalid_detected_tier_raises_value_error,
    test_selection_source_is_stable,
    test_empty_profile_overrides_preserve_base_profile,
    test_valid_o1_override_is_applied,
    test_invalid_o1_override_is_rejected,
    test_builtin_o1_profile_is_not_mutated_by_override,
    test_settings_can_be_changed_after_creation,
    test_partial_update_preserves_unchanged_fields,
    test_empty_profile_overrides_clears_previous_overrides,
    test_unsupported_settings_field_raises_value_error,
    test_unsupported_update_field_raises_value_error,
    test_invalid_delivery_surface_raises_value_error,
    test_inputs_are_not_mutated,
    test_repeated_resolution_is_deterministic,
    test_no_api_key_or_secret_field_exists,
    test_no_filesystem_environment_network_or_subprocess_access_is_required,
    test_no_import_from_strata_patch_or_commands_exists,
    test_package_layering_invariant_has_no_new_violation,
]
