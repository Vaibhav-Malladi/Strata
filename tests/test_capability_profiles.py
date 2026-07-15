import json
from dataclasses import FrozenInstanceError

import strata.core.capability_profiles as capability_profiles
from strata.core.capability_profiles import (
    BUILT_IN_CAPABILITY_PROFILES,
    CAPABILITY_PROFILE_FIELD_ORDER,
    CAPABILITY_TIER_MEDIUM,
    CAPABILITY_TIER_STRONG,
    CAPABILITY_TIER_UNKNOWN,
    CAPABILITY_TIER_WEAK,
    CAPABILITY_TIERS,
    CONSERVATIVE_UNKNOWN_PROFILE,
    CONTEXT_VARIANT_BALANCED,
    CONTEXT_VARIANT_COMPACT,
    CONTEXT_VARIANT_EXPANDED,
    MAX_RECOMMENDED_FILES_LIMIT,
    CapabilityProfile,
    get_capability_profile,
    get_conservative_unknown_profile,
    with_capability_overrides,
)
from strata.core.context_artifacts import (
    CONTEXT_ARTIFACT_PATH,
    RUN_STATE_ARTIFACT_PATH,
)
from strata.core.diagnostics import (
    DIAGNOSTIC_SEVERITIES,
    DIAGNOSTIC_SOURCES,
)


def test_all_four_capability_tiers_exist():
    assert set(CAPABILITY_TIERS) == {"unknown", "weak", "medium", "strong"}
    assert set(BUILT_IN_CAPABILITY_PROFILES) == set(CAPABILITY_TIERS)


def test_tier_ordering_is_deterministic():
    assert CAPABILITY_TIERS == (
        CAPABILITY_TIER_UNKNOWN,
        CAPABILITY_TIER_WEAK,
        CAPABILITY_TIER_MEDIUM,
        CAPABILITY_TIER_STRONG,
    )


def test_builtin_weak_profile_has_compact_guidance_behavior():
    profile = get_capability_profile(CAPABILITY_TIER_WEAK)

    assert profile.preferred_context_variant == CONTEXT_VARIANT_COMPACT
    assert profile.needs_explicit_steps is True
    assert profile.needs_diff_example is True
    assert profile.diff_reliability == "low"
    assert profile.structured_output_reliability == "low"
    assert profile.max_recommended_files < get_capability_profile(CAPABILITY_TIER_MEDIUM).max_recommended_files


def test_builtin_medium_profile_uses_balanced_behavior():
    profile = get_capability_profile(CAPABILITY_TIER_MEDIUM)

    assert profile.preferred_context_variant == CONTEXT_VARIANT_BALANCED
    assert profile.needs_explicit_steps is False
    assert profile.needs_diff_example is False
    assert profile.diff_reliability == "medium"
    assert profile.structured_output_reliability == "medium"


def test_builtin_strong_profile_uses_expanded_behavior():
    profile = get_capability_profile(CAPABILITY_TIER_STRONG)

    assert profile.preferred_context_variant == CONTEXT_VARIANT_EXPANDED
    assert profile.needs_explicit_steps is False
    assert profile.needs_diff_example is False
    assert profile.diff_reliability == "high"
    assert profile.structured_output_reliability == "high"


def test_unknown_profile_is_conservative():
    profile = get_capability_profile(CAPABILITY_TIER_UNKNOWN)

    assert profile == CONSERVATIVE_UNKNOWN_PROFILE
    assert profile == get_conservative_unknown_profile()
    assert profile.preferred_context_variant == CONTEXT_VARIANT_BALANCED
    assert profile.needs_explicit_steps is True
    assert profile.needs_diff_example is True
    assert profile.context_window_class == "unknown"
    assert profile.max_recommended_files <= get_capability_profile(CAPABILITY_TIER_MEDIUM).max_recommended_files


def test_unknown_profile_is_not_treated_as_strong():
    unknown = get_capability_profile(CAPABILITY_TIER_UNKNOWN)
    strong = get_capability_profile(CAPABILITY_TIER_STRONG)

    assert unknown != strong
    assert unknown.preferred_context_variant != strong.preferred_context_variant
    assert unknown.structured_output_reliability != strong.structured_output_reliability
    assert unknown.max_recommended_files < strong.max_recommended_files


def test_profiles_serialize_to_json_ready_mappings():
    profile = get_capability_profile(CAPABILITY_TIER_MEDIUM)
    data = profile.to_dict()

    assert list(data.keys()) == list(CAPABILITY_PROFILE_FIELD_ORDER)
    assert json.loads(json.dumps(data, allow_nan=False)) == data
    assert all(_is_json_ready(value) for value in data.values())


def test_repeated_serialization_is_deterministic():
    profile = get_capability_profile(CAPABILITY_TIER_STRONG)

    assert profile.to_dict() == profile.to_dict()
    assert list(profile.to_dict().keys()) == list(profile.to_dict().keys())


def test_repeated_profile_lookup_returns_equivalent_values():
    first = get_capability_profile(CAPABILITY_TIER_WEAK)
    second = get_capability_profile(CAPABILITY_TIER_WEAK)

    assert first == second
    assert first.to_dict() == second.to_dict()


def test_unsupported_tier_lookup_raises_value_error():
    try:
        get_capability_profile("frontier")
    except ValueError as error:
        assert "tier must be one of" in str(error)
    else:
        raise AssertionError("Unsupported tier was accepted")


def test_invalid_context_window_class_is_rejected():
    try:
        _profile(context_window_class="huge")
    except ValueError as error:
        assert "context_window_class must be one of" in str(error)
    else:
        raise AssertionError("Invalid context window class was accepted")


def test_invalid_reliability_values_are_rejected():
    for field in (
        "instruction_adherence",
        "diff_reliability",
        "structured_output_reliability",
        "multi_file_reasoning",
    ):
        try:
            _profile(**{field: "perfect"})
        except ValueError as error:
            assert f"{field} must be one of" in str(error)
        else:
            raise AssertionError(f"Invalid {field} was accepted")


def test_invalid_context_variant_is_rejected():
    try:
        _profile(preferred_context_variant="auto")
    except ValueError as error:
        assert "preferred_context_variant must be one of" in str(error)
    else:
        raise AssertionError("Invalid context variant was accepted")


def test_non_boolean_guidance_flags_are_rejected():
    for field in ("needs_explicit_steps", "needs_diff_example"):
        try:
            _profile(**{field: "true"})
        except ValueError as error:
            assert f"{field} must be a boolean" in str(error)
        else:
            raise AssertionError(f"Invalid {field} was accepted")


def test_zero_max_recommended_files_is_rejected():
    try:
        _profile(max_recommended_files=0)
    except ValueError as error:
        assert "positive integer" in str(error)
    else:
        raise AssertionError("Zero max_recommended_files was accepted")


def test_negative_max_recommended_files_is_rejected():
    try:
        _profile(max_recommended_files=-1)
    except ValueError as error:
        assert "positive integer" in str(error)
    else:
        raise AssertionError("Negative max_recommended_files was accepted")


def test_values_over_hard_upper_bound_are_rejected():
    try:
        _profile(max_recommended_files=MAX_RECOMMENDED_FILES_LIMIT + 1)
    except ValueError as error:
        assert f"at most {MAX_RECOMMENDED_FILES_LIMIT}" in str(error)
    else:
        raise AssertionError("Oversized max_recommended_files was accepted")


def test_profiles_are_immutable():
    profile = get_capability_profile(CAPABILITY_TIER_MEDIUM)

    try:
        profile.tier = CAPABILITY_TIER_STRONG
    except FrozenInstanceError:
        pass
    else:
        raise AssertionError("CapabilityProfile was mutable")


def test_builtin_profile_data_cannot_be_mutated_through_returned_results():
    profile = get_capability_profile(CAPABILITY_TIER_WEAK)
    data = profile.to_dict()
    data["preferred_context_variant"] = CONTEXT_VARIANT_EXPANDED

    assert profile.preferred_context_variant == CONTEXT_VARIANT_COMPACT
    assert profile.to_dict()["preferred_context_variant"] == CONTEXT_VARIANT_COMPACT


def test_overrides_return_a_new_profile():
    profile = get_capability_profile(CAPABILITY_TIER_MEDIUM)
    overridden = with_capability_overrides(
        profile,
        preferred_context_variant=CONTEXT_VARIANT_COMPACT,
        max_recommended_files=4,
    )

    assert overridden is not profile
    assert overridden.tier == profile.tier
    assert overridden.preferred_context_variant == CONTEXT_VARIANT_COMPACT
    assert overridden.max_recommended_files == 4


def test_overrides_do_not_mutate_the_original():
    profile = get_capability_profile(CAPABILITY_TIER_MEDIUM)
    before = profile.to_dict()

    with_capability_overrides(profile, max_recommended_files=4)

    assert profile.to_dict() == before


def test_invalid_override_values_are_rejected():
    profile = get_capability_profile(CAPABILITY_TIER_MEDIUM)

    for call in (
        lambda: with_capability_overrides(profile, preferred_context_variant="auto"),
        lambda: with_capability_overrides(profile, max_recommended_files=0),
        lambda: with_capability_overrides("medium"),
    ):
        try:
            call()
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid override was accepted")


def test_no_model_names_or_provider_names_appear_in_builtin_profile_data():
    forbidden = {
        "openai",
        "anthropic",
        "google",
        "microsoft",
        "ollama",
        "gpt",
        "claude",
        "gemini",
        "copilot",
        "provider",
        "model_name",
    }
    strings = {
        str(value).lower()
        for profile in BUILT_IN_CAPABILITY_PROFILES.values()
        for value in profile.to_dict().values()
        if isinstance(value, str)
    }

    assert not (strings & forbidden)


def test_no_filesystem_or_environment_access_is_required():
    public_names = {
        name
        for name in vars(capability_profiles)
        if not name.startswith("_")
    }

    assert "os" not in public_names
    assert "Path" not in public_names
    assert "open" not in public_names
    assert "settings" not in public_names
    assert callable(get_capability_profile)


def test_existing_part_i_and_part_m_contracts_remain_unchanged():
    assert CONTEXT_ARTIFACT_PATH == ".aidc/context/strata_context.md"
    assert RUN_STATE_ARTIFACT_PATH == ".aidc/context/run_state.json"
    assert DIAGNOSTIC_SEVERITIES == ("info", "warning", "error")
    assert DIAGNOSTIC_SOURCES == (
        "workflow_state",
        "context",
        "review",
        "apply",
        "verify",
        "gate",
        "system",
    )


def _profile(**overrides) -> CapabilityProfile:
    values = {
        "tier": CAPABILITY_TIER_MEDIUM,
        "context_window_class": "medium",
        "instruction_adherence": "medium",
        "diff_reliability": "medium",
        "structured_output_reliability": "medium",
        "multi_file_reasoning": "medium",
        "needs_explicit_steps": False,
        "needs_diff_example": False,
        "preferred_context_variant": CONTEXT_VARIANT_BALANCED,
        "max_recommended_files": 10,
    }
    values.update(overrides)
    return CapabilityProfile(**values)


def _is_json_ready(value) -> bool:
    if value is None or isinstance(value, (str, int, bool)):
        return True
    if isinstance(value, list):
        return all(_is_json_ready(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _is_json_ready(item) for key, item in value.items())
    return False


TESTS = [
    test_all_four_capability_tiers_exist,
    test_tier_ordering_is_deterministic,
    test_builtin_weak_profile_has_compact_guidance_behavior,
    test_builtin_medium_profile_uses_balanced_behavior,
    test_builtin_strong_profile_uses_expanded_behavior,
    test_unknown_profile_is_conservative,
    test_unknown_profile_is_not_treated_as_strong,
    test_profiles_serialize_to_json_ready_mappings,
    test_repeated_serialization_is_deterministic,
    test_repeated_profile_lookup_returns_equivalent_values,
    test_unsupported_tier_lookup_raises_value_error,
    test_invalid_context_window_class_is_rejected,
    test_invalid_reliability_values_are_rejected,
    test_invalid_context_variant_is_rejected,
    test_non_boolean_guidance_flags_are_rejected,
    test_zero_max_recommended_files_is_rejected,
    test_negative_max_recommended_files_is_rejected,
    test_values_over_hard_upper_bound_are_rejected,
    test_profiles_are_immutable,
    test_builtin_profile_data_cannot_be_mutated_through_returned_results,
    test_overrides_return_a_new_profile,
    test_overrides_do_not_mutate_the_original,
    test_invalid_override_values_are_rejected,
    test_no_model_names_or_provider_names_appear_in_builtin_profile_data,
    test_no_filesystem_or_environment_access_is_required,
    test_existing_part_i_and_part_m_contracts_remain_unchanged,
]
