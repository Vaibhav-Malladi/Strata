import copy
import json

import strata.core.delivery_surfaces as delivery_surfaces
from strata.core.capability_profiles import CAPABILITY_TIERS
from strata.core.context_rendering import RENDERING_VARIANTS
from strata.core.delivery_surfaces import (
    CONTENT_TYPE_TEXT,
    CONTENT_TYPE_VSCODE_PROMPT,
    DELIVERY_SURFACE_BROWSER_COPY,
    DELIVERY_SURFACE_CLI,
    DELIVERY_SURFACE_VSCODE,
    DELIVERY_SURFACES,
    build_delivery_payload,
)
from strata.core.prompt_templates import (
    PROMPT_TEMPLATE_IDS,
    PROMPT_TEMPLATE_SCHEMA_VERSION,
    PROMPT_TEMPLATE_VERSION,
)


def test_stable_surfaces_are_browser_copy_cli_vscode():
    assert DELIVERY_SURFACES == (
        "browser_copy",
        "cli",
        "vscode",
    )


def test_browser_copy_payload_is_json_ready():
    prompt_result = _prompt_result()
    payload = build_delivery_payload(prompt_result, DELIVERY_SURFACE_BROWSER_COPY)

    assert json.loads(json.dumps(payload, allow_nan=False)) == payload
    assert _is_json_ready(payload)
    assert tuple(payload.keys()) == (
        "schema_version",
        "surface",
        "content_type",
        "prompt",
        "instructions",
        "metadata",
    )
    assert payload["schema_version"] == 1
    assert payload["metadata"]["template_id"] == prompt_result["template_id"]
    assert payload["metadata"]["template_version"] == prompt_result["template_version"]
    assert payload["metadata"]["profile_tier"] == prompt_result["profile_tier"]
    assert payload["metadata"]["context_variant"] == prompt_result["context_variant"]
    assert payload["metadata"]["prompt_character_count"] == len(prompt_result["prompt"])


def test_cli_payload_is_json_ready():
    payload = build_delivery_payload(_prompt_result(), DELIVERY_SURFACE_CLI)

    assert json.loads(json.dumps(payload, allow_nan=False)) == payload
    assert _is_json_ready(payload)


def test_vscode_payload_is_json_ready():
    payload = build_delivery_payload(_prompt_result(), DELIVERY_SURFACE_VSCODE)

    assert json.loads(json.dumps(payload, allow_nan=False)) == payload
    assert _is_json_ready(payload)


def test_browser_copy_content_type_is_text_plain():
    payload = build_delivery_payload(_prompt_result(), DELIVERY_SURFACE_BROWSER_COPY)

    assert payload["content_type"] == CONTENT_TYPE_TEXT


def test_cli_content_type_is_text_plain():
    payload = build_delivery_payload(_prompt_result(), DELIVERY_SURFACE_CLI)

    assert payload["content_type"] == CONTENT_TYPE_TEXT


def test_vscode_content_type_is_strata_prompt_json():
    payload = build_delivery_payload(_prompt_result(), DELIVERY_SURFACE_VSCODE)

    assert payload["content_type"] == CONTENT_TYPE_VSCODE_PROMPT


def test_browser_copy_requires_manual_transfer():
    payload = build_delivery_payload(_prompt_result(), DELIVERY_SURFACE_BROWSER_COPY)

    assert payload["metadata"]["manual_transfer_required"] is True


def test_cli_does_not_require_manual_transfer():
    payload = build_delivery_payload(_prompt_result(), DELIVERY_SURFACE_CLI)

    assert payload["metadata"]["manual_transfer_required"] is False


def test_vscode_does_not_require_manual_transfer():
    payload = build_delivery_payload(_prompt_result(), DELIVERY_SURFACE_VSCODE)

    assert payload["metadata"]["manual_transfer_required"] is False


def test_prompt_text_is_preserved_exactly_for_every_surface():
    prompt_result = _prompt_result(prompt="Line one\r\nLine two\n")

    for surface in DELIVERY_SURFACES:
        payload = build_delivery_payload(prompt_result, surface)
        assert payload["prompt"] == prompt_result["prompt"]


def test_prompt_appears_only_once_in_payload():
    prompt_result = _prompt_result(prompt="Unique trusted prompt text.")
    payload = build_delivery_payload(prompt_result, DELIVERY_SURFACE_BROWSER_COPY)

    assert json.dumps(payload, sort_keys=True).count(prompt_result["prompt"]) == 1


def test_browser_instructions_describe_manual_copy_and_return():
    payload = build_delivery_payload(_prompt_result(), DELIVERY_SURFACE_BROWSER_COPY)
    text = " ".join(payload["instructions"]).lower()

    assert "copy" in text
    assert "submit" in text
    assert "back into strata" in text


def test_cli_instructions_remain_provider_neutral():
    payload = build_delivery_payload(_prompt_result(), DELIVERY_SURFACE_CLI)
    text = " ".join(payload["instructions"]).lower()

    assert "send the complete prompt" in text
    assert "capture the complete response" in text
    assert "command" not in text
    assert "api" not in text


def test_vscode_metadata_contains_display_title():
    payload = build_delivery_payload(_prompt_result(), DELIVERY_SURFACE_VSCODE)

    assert payload["metadata"]["display_title"] == "Strata patch request"


def test_no_model_or_provider_names_appear():
    forbidden = (
        "openai",
        "claude",
        "anthropic",
        "gemini",
        "copilot",
        "cursor",
        "terminal_ai",
        "web_chat",
        "provider",
        "model_name",
    )

    for surface in DELIVERY_SURFACES:
        payload = build_delivery_payload(_prompt_result(), surface)
        text = json.dumps(payload, sort_keys=True).lower()
        for word in forbidden:
            assert word not in text


def test_unsupported_surface_raises_value_error():
    try:
        build_delivery_payload(_prompt_result(), "openai")
    except ValueError:
        pass
    else:
        raise AssertionError("Unsupported surface was accepted")


def test_missing_prompt_raises_value_error():
    prompt_result = _prompt_result()
    del prompt_result["prompt"]

    _assert_value_error(lambda: build_delivery_payload(prompt_result, DELIVERY_SURFACE_CLI))


def test_empty_prompt_raises_value_error():
    _assert_value_error(
        lambda: build_delivery_payload(
            _prompt_result(prompt=""),
            DELIVERY_SURFACE_CLI,
        )
    )


def test_invalid_prompt_result_type_raises_value_error():
    _assert_value_error(lambda: build_delivery_payload([], DELIVERY_SURFACE_CLI))


def test_invalid_metadata_type_raises_value_error():
    prompt_result = _prompt_result()
    prompt_result["metadata"] = []

    _assert_value_error(lambda: build_delivery_payload(prompt_result, DELIVERY_SURFACE_CLI))


def test_invalid_profile_tier_raises_value_error():
    prompt_result = _prompt_result()
    prompt_result["profile_tier"] = "large"

    _assert_value_error(lambda: build_delivery_payload(prompt_result, DELIVERY_SURFACE_CLI))


def test_invalid_context_variant_raises_value_error():
    prompt_result = _prompt_result()
    prompt_result["context_variant"] = "full"

    _assert_value_error(lambda: build_delivery_payload(prompt_result, DELIVERY_SURFACE_CLI))


def test_inputs_are_not_mutated():
    prompt_result = _prompt_result()
    before = copy.deepcopy(prompt_result)

    build_delivery_payload(prompt_result, DELIVERY_SURFACE_BROWSER_COPY)

    assert prompt_result == before


def test_repeated_calls_are_deterministic():
    prompt_result = _prompt_result()

    assert build_delivery_payload(prompt_result, DELIVERY_SURFACE_VSCODE) == build_delivery_payload(
        prompt_result,
        DELIVERY_SURFACE_VSCODE,
    )


def test_output_collections_are_fresh():
    first = build_delivery_payload(_prompt_result(), DELIVERY_SURFACE_BROWSER_COPY)
    second = build_delivery_payload(_prompt_result(), DELIVERY_SURFACE_BROWSER_COPY)

    assert first["instructions"] is not second["instructions"]
    assert first["metadata"] is not second["metadata"]


def test_no_runtime_integration_access_is_required():
    public_names = {
        name
        for name in vars(delivery_surfaces)
        if not name.startswith("_")
    }

    for forbidden in ("Path", "open", "os", "subprocess", "requests", "webbrowser", "clipboard", "pyperclip"):
        assert forbidden not in public_names


def test_existing_o1_o4_contracts_remain_unchanged():
    assert CAPABILITY_TIERS == ("unknown", "weak", "medium", "strong")
    assert RENDERING_VARIANTS == ("compact", "balanced", "expanded")
    assert PROMPT_TEMPLATE_IDS == ("weak_patch", "medium_patch", "strong_patch", "unknown_patch")
    assert "validate_ai_response" not in vars(delivery_surfaces)


def test_package_layering_invariant_has_no_new_violation():
    public_names = set(vars(delivery_surfaces))

    assert delivery_surfaces.__name__ == "strata.core.delivery_surfaces"
    assert "validate_ai_response" not in public_names
    assert "strata.patch" not in public_names


def _prompt_result(prompt: str = "Trusted O3 prompt.\nReturn only a unified diff.\n") -> dict[str, object]:
    return {
        "schema_version": PROMPT_TEMPLATE_SCHEMA_VERSION,
        "template_id": "medium_patch",
        "template_version": PROMPT_TEMPLATE_VERSION,
        "profile_tier": "medium",
        "context_variant": "balanced",
        "prompt": prompt,
        "sections": {
            "role": "Role",
            "task": "Task",
        },
        "metadata": {
            "approved_file_count": 1,
            "relationship_count": 0,
            "omission_count": 0,
            "includes_diff_example": False,
            "needs_explicit_steps": False,
            "static_instruction_character_count": 42,
            "rendered_context_character_count": 101,
            "prompt_character_count": len(prompt),
        },
    }


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
    test_stable_surfaces_are_browser_copy_cli_vscode,
    test_browser_copy_payload_is_json_ready,
    test_cli_payload_is_json_ready,
    test_vscode_payload_is_json_ready,
    test_browser_copy_content_type_is_text_plain,
    test_cli_content_type_is_text_plain,
    test_vscode_content_type_is_strata_prompt_json,
    test_browser_copy_requires_manual_transfer,
    test_cli_does_not_require_manual_transfer,
    test_vscode_does_not_require_manual_transfer,
    test_prompt_text_is_preserved_exactly_for_every_surface,
    test_prompt_appears_only_once_in_payload,
    test_browser_instructions_describe_manual_copy_and_return,
    test_cli_instructions_remain_provider_neutral,
    test_vscode_metadata_contains_display_title,
    test_no_model_or_provider_names_appear,
    test_unsupported_surface_raises_value_error,
    test_missing_prompt_raises_value_error,
    test_empty_prompt_raises_value_error,
    test_invalid_prompt_result_type_raises_value_error,
    test_invalid_metadata_type_raises_value_error,
    test_invalid_profile_tier_raises_value_error,
    test_invalid_context_variant_raises_value_error,
    test_inputs_are_not_mutated,
    test_repeated_calls_are_deterministic,
    test_output_collections_are_fresh,
    test_no_runtime_integration_access_is_required,
    test_existing_o1_o4_contracts_remain_unchanged,
    test_package_layering_invariant_has_no_new_violation,
]
