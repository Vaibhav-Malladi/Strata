from collections.abc import Mapping

from strata.core.capability_profiles import CAPABILITY_TIERS
from strata.core.context_rendering import RENDERING_VARIANTS
from strata.core.prompt_templates import (
    PROMPT_TEMPLATE_IDS,
    PROMPT_TEMPLATE_SCHEMA_VERSION,
    PROMPT_TEMPLATE_VERSION,
)


DELIVERY_PAYLOAD_SCHEMA_VERSION = 1

DELIVERY_SURFACE_BROWSER_COPY = "browser_copy"
DELIVERY_SURFACE_CLI = "cli"
DELIVERY_SURFACE_VSCODE = "vscode"
DELIVERY_SURFACES = (
    DELIVERY_SURFACE_BROWSER_COPY,
    DELIVERY_SURFACE_CLI,
    DELIVERY_SURFACE_VSCODE,
)

CONTENT_TYPE_TEXT = "text/plain"
CONTENT_TYPE_VSCODE_PROMPT = "application/vnd.strata.prompt+json"

VSCODE_DISPLAY_TITLE = "Strata patch request"

DELIVERY_PAYLOAD_FIELD_ORDER = (
    "schema_version",
    "surface",
    "content_type",
    "prompt",
    "instructions",
    "metadata",
)


def _validate_prompt_result(prompt_result) -> Mapping:
    if not isinstance(prompt_result, Mapping):
        raise ValueError("prompt_result must be a mapping.")

    required_fields = (
        "schema_version",
        "template_id",
        "template_version",
        "profile_tier",
        "context_variant",
        "prompt",
        "metadata",
    )
    for field in required_fields:
        if field not in prompt_result:
            raise ValueError(f"prompt_result is missing required field: {field}")

    if prompt_result["schema_version"] != PROMPT_TEMPLATE_SCHEMA_VERSION:
        raise ValueError("prompt_result schema_version is unsupported.")
    _validate_choice(prompt_result["template_id"], "template_id", PROMPT_TEMPLATE_IDS)
    if prompt_result["template_version"] != PROMPT_TEMPLATE_VERSION:
        raise ValueError("prompt_result template_version is unsupported.")
    _validate_choice(prompt_result["profile_tier"], "profile_tier", CAPABILITY_TIERS)
    _validate_choice(prompt_result["context_variant"], "context_variant", RENDERING_VARIANTS)
    _validate_prompt(prompt_result["prompt"])
    metadata = _validate_metadata(prompt_result["metadata"])
    _validate_prompt_character_count(metadata, prompt_result["prompt"])
    return prompt_result


def _validate_surface(surface) -> str:
    return _validate_choice(surface, "surface", DELIVERY_SURFACES)


def _validate_choice(value, field_name: str, choices: tuple[str, ...]) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string.")
    if value not in choices:
        raise ValueError(f"{field_name} must be one of: {', '.join(choices)}.")
    return value


def _validate_prompt(prompt) -> str:
    if not isinstance(prompt, str) or not prompt:
        raise ValueError("prompt_result prompt must be a non-empty string.")
    return prompt


def _validate_metadata(metadata) -> Mapping:
    if not isinstance(metadata, Mapping):
        raise ValueError("prompt_result metadata must be a mapping.")
    return metadata


def _validate_prompt_character_count(metadata: Mapping, prompt: str) -> None:
    count = metadata.get("prompt_character_count")
    if isinstance(count, bool) or not isinstance(count, int):
        raise ValueError("prompt_result metadata prompt_character_count must be an integer.")
    if count != len(prompt):
        raise ValueError("prompt_result metadata prompt_character_count does not match prompt.")


def build_delivery_payload(
    prompt_result,
    surface,
) -> dict[str, object]:
    prompt_result = _validate_prompt_result(prompt_result)
    surface = _validate_surface(surface)

    prompt = prompt_result["prompt"]
    manual_transfer_required = _manual_transfer_required(surface)
    result = {
        "schema_version": DELIVERY_PAYLOAD_SCHEMA_VERSION,
        "surface": surface,
        "content_type": _content_type_for_surface(surface),
        "prompt": prompt,
        "instructions": _instructions_for_surface(surface),
        "metadata": _metadata_for_surface(
            prompt_result,
            surface,
            manual_transfer_required,
        ),
    }
    _validate_json_ready(result)
    return result


def _content_type_for_surface(surface: str) -> str:
    if surface == DELIVERY_SURFACE_VSCODE:
        return CONTENT_TYPE_VSCODE_PROMPT
    return CONTENT_TYPE_TEXT


def _manual_transfer_required(surface: str) -> bool:
    return surface == DELIVERY_SURFACE_BROWSER_COPY


def _instructions_for_surface(surface: str) -> list[str]:
    if surface == DELIVERY_SURFACE_BROWSER_COPY:
        return [
            "Copy the complete prompt into the selected chat.",
            "Submit it as one message.",
            "Copy the complete response back into Strata for validation.",
        ]
    if surface == DELIVERY_SURFACE_CLI:
        return [
            "Send the complete prompt as one input.",
            "Capture the complete response.",
            "Pass the response to Strata validation before review or apply.",
        ]
    return [
        "Send the complete prompt through the Strata editor surface.",
        "Keep the prompt content unchanged.",
        "Return the complete response to Strata validation before review or apply.",
    ]


def _metadata_for_surface(
    prompt_result: Mapping,
    surface: str,
    manual_transfer_required: bool,
) -> dict[str, object]:
    metadata = {
        "template_id": prompt_result["template_id"],
        "template_version": prompt_result["template_version"],
        "profile_tier": prompt_result["profile_tier"],
        "context_variant": prompt_result["context_variant"],
        "prompt_character_count": prompt_result["metadata"]["prompt_character_count"],
        "manual_transfer_required": manual_transfer_required,
    }
    if surface == DELIVERY_SURFACE_VSCODE:
        metadata["display_title"] = VSCODE_DISPLAY_TITLE
    return metadata


def _validate_json_ready(value) -> None:
    if _copy_json_value(value) is _UNSUPPORTED:
        raise ValueError("Delivery payload must be JSON-ready.")


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
        for key in sorted(value.keys(), key=str):
            if not isinstance(key, str):
                return _UNSUPPORTED
            rendered = _copy_json_value(value[key])
            if rendered is _UNSUPPORTED:
                return _UNSUPPORTED
            copied[key] = rendered
        return copied
    return _UNSUPPORTED
