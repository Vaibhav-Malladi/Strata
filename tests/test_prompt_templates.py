import copy
import json

import strata.core.prompt_templates as prompt_templates
from strata.core.capability_profiles import (
    CAPABILITY_TIER_MEDIUM,
    CAPABILITY_TIER_STRONG,
    CAPABILITY_TIER_UNKNOWN,
    CAPABILITY_TIER_WEAK,
    get_capability_profile,
)
from strata.core.context_artifacts import (
    CONTEXT_ARTIFACT_PATH,
    RUN_STATE_ARTIFACT_PATH,
    build_represented_item,
)
from strata.core.context_rendering import (
    RENDERING_VARIANT_BALANCED,
    RENDERING_VARIANT_COMPACT,
    RENDERING_VARIANT_EXPANDED,
    render_context_pack,
    render_context_pack_markdown,
)
from strata.core.diagnostics import DIAGNOSTIC_SEVERITIES
from strata.core.prompt_templates import (
    PROMPT_TEMPLATE_IDS,
    PROMPT_TEMPLATE_MEDIUM_PATCH,
    PROMPT_TEMPLATE_SCHEMA_VERSION,
    PROMPT_TEMPLATE_STRONG_PATCH,
    PROMPT_TEMPLATE_UNKNOWN_PATCH,
    PROMPT_TEMPLATE_VERSION,
    PROMPT_TEMPLATE_WEAK_PATCH,
    STATIC_DIFF_EXAMPLE,
    get_prompt_template,
    render_prompt,
    render_template_text,
    select_prompt_template,
)


def test_stable_template_ids_exist():
    assert PROMPT_TEMPLATE_IDS == (
        "weak_patch",
        "medium_patch",
        "strong_patch",
        "unknown_patch",
    )


def test_template_schema_version_is_stable():
    assert PROMPT_TEMPLATE_SCHEMA_VERSION == 1
    assert PROMPT_TEMPLATE_VERSION == 1


def test_weak_profile_selects_weak_template():
    template = select_prompt_template(get_capability_profile(CAPABILITY_TIER_WEAK))

    assert template.template_id == PROMPT_TEMPLATE_WEAK_PATCH


def test_medium_profile_selects_medium_template():
    template = select_prompt_template(get_capability_profile(CAPABILITY_TIER_MEDIUM))

    assert template.template_id == PROMPT_TEMPLATE_MEDIUM_PATCH


def test_strong_profile_selects_strong_template():
    template = select_prompt_template(get_capability_profile(CAPABILITY_TIER_STRONG))

    assert template.template_id == PROMPT_TEMPLATE_STRONG_PATCH


def test_unknown_profile_selects_unknown_template():
    template = select_prompt_template(get_capability_profile(CAPABILITY_TIER_UNKNOWN))

    assert template.template_id == PROMPT_TEMPLATE_UNKNOWN_PATCH


def test_unknown_never_selects_strong_template():
    template = select_prompt_template(get_capability_profile(CAPABILITY_TIER_UNKNOWN))

    assert template.template_id != PROMPT_TEMPLATE_STRONG_PATCH


def test_weak_prompt_includes_explicit_steps():
    result = _prompt(CAPABILITY_TIER_WEAK)

    assert "step" in result["prompt"].lower()
    assert result["metadata"]["needs_explicit_steps"] is True


def test_weak_prompt_includes_unified_diff_example():
    result = _prompt(CAPABILITY_TIER_WEAK)

    assert result["metadata"]["includes_diff_example"] is True
    assert STATIC_DIFF_EXAMPLE in result["prompt"]


def test_unknown_prompt_includes_unified_diff_example():
    result = _prompt(CAPABILITY_TIER_UNKNOWN)

    assert result["metadata"]["includes_diff_example"] is True
    assert STATIC_DIFF_EXAMPLE in result["prompt"]


def test_medium_prompt_does_not_require_diff_example():
    result = _prompt(CAPABILITY_TIER_MEDIUM)

    assert result["metadata"]["includes_diff_example"] is False
    assert STATIC_DIFF_EXAMPLE not in result["prompt"]


def test_strong_prompt_does_not_require_diff_example():
    result = _prompt(CAPABILITY_TIER_STRONG)

    assert result["metadata"]["includes_diff_example"] is False
    assert STATIC_DIFF_EXAMPLE not in result["prompt"]


def test_all_templates_require_unified_diff_output():
    for tier in (CAPABILITY_TIER_WEAK, CAPABILITY_TIER_MEDIUM, CAPABILITY_TIER_STRONG, CAPABILITY_TIER_UNKNOWN):
        result = _prompt(tier)
        assert "valid unified diff" in result["prompt"]
        assert "repository-relative paths" in result["prompt"]


def test_all_templates_prohibit_invented_files():
    for tier in (CAPABILITY_TIER_WEAK, CAPABILITY_TIER_MEDIUM, CAPABILITY_TIER_STRONG, CAPABILITY_TIER_UNKNOWN):
        assert "invent" in _prompt(tier)["prompt"].lower()


def test_all_templates_preserve_scope_boundaries():
    for tier in (CAPABILITY_TIER_WEAK, CAPABILITY_TIER_MEDIUM, CAPABILITY_TIER_STRONG, CAPABILITY_TIER_UNKNOWN):
        prompt = _prompt(tier)["prompt"].lower()
        assert "approved" in prompt
        assert "scope" in prompt or "unrelated" in prompt or "out-of-scope" in prompt


def test_rendered_o2_context_appears_exactly_once():
    profile = get_capability_profile(CAPABILITY_TIER_MEDIUM)
    rendered = _rendered_context(profile)
    result = render_prompt(rendered, profile)

    assert result["prompt"].count("# Strata AI Context") == 1
    assert result["sections"]["context"].count("# Strata AI Context") == 1
    assert render_context_pack_markdown(rendered).strip() in result["prompt"]


def test_prompt_section_ordering_is_deterministic():
    result = _prompt(CAPABILITY_TIER_MEDIUM)
    positions = [
        result["prompt"].index(heading)
        for heading in (
            "## Role",
            "## Task",
            "## Instructions",
            "## Approved Context",
            "## Scope",
            "## Output Format",
            "## Safety",
        )
    ]

    assert positions == sorted(positions)


def test_prompt_output_is_json_ready():
    result = _prompt(CAPABILITY_TIER_MEDIUM)

    assert json.loads(json.dumps(result, allow_nan=False)) == result
    assert _is_json_ready(result)


def test_repeated_rendering_is_deterministic():
    profile = get_capability_profile(CAPABILITY_TIER_MEDIUM)
    rendered = _rendered_context(profile)

    assert render_prompt(rendered, profile) == render_prompt(rendered, profile)


def test_input_profile_is_not_mutated():
    profile = get_capability_profile(CAPABILITY_TIER_MEDIUM)
    before = profile.to_dict()

    render_prompt(_rendered_context(profile), profile)

    assert profile.to_dict() == before


def test_input_rendered_context_is_not_mutated():
    profile = get_capability_profile(CAPABILITY_TIER_MEDIUM)
    rendered = _rendered_context(profile)
    before = copy.deepcopy(rendered)

    render_prompt(rendered, profile)

    assert rendered == before


def test_missing_required_variable_raises_value_error():
    try:
        render_template_text("Task: {{task}} for {{profile_tier}}", {"task": "Fix auth"})
    except ValueError as error:
        assert "Missing required template variable" in str(error)
    else:
        raise AssertionError("Missing template variable was accepted")


def test_unsupported_variable_raises_value_error():
    try:
        render_template_text("Task: {{task}}", {"task": "Fix auth", "provider": "x"})
    except ValueError as error:
        assert "variable must be one of" in str(error)
    else:
        raise AssertionError("Unsupported template variable was accepted")


def test_unresolved_placeholder_raises_value_error():
    try:
        render_template_text("Task: {{task", {"task": "Fix auth"})
    except ValueError as error:
        assert "unresolved placeholders" in str(error)
    else:
        raise AssertionError("Unresolved placeholder was accepted")


def test_unsupported_template_id_raises_value_error():
    try:
        get_prompt_template("openai")
    except ValueError as error:
        assert "template_id must be one of" in str(error)
    else:
        raise AssertionError("Unsupported template id was accepted")


def test_invalid_rendered_context_variant_raises_value_error():
    profile = get_capability_profile(CAPABILITY_TIER_MEDIUM)
    rendered = _rendered_context(profile)
    rendered["variant"] = "verbose"

    try:
        render_prompt(rendered, profile)
    except ValueError as error:
        assert "variant" in str(error)
    else:
        raise AssertionError("Invalid rendered-context variant was accepted")


def test_invalid_profile_input_raises_value_error():
    try:
        select_prompt_template("medium")
    except ValueError as error:
        assert "profile must be a CapabilityProfile" in str(error)
    else:
        raise AssertionError("Invalid profile was accepted")


def test_template_metadata_records_template_id_and_version():
    result = _prompt(CAPABILITY_TIER_MEDIUM)

    assert result["schema_version"] == PROMPT_TEMPLATE_SCHEMA_VERSION
    assert result["template_id"] == PROMPT_TEMPLATE_MEDIUM_PATCH
    assert result["template_version"] == PROMPT_TEMPLATE_VERSION


def test_metadata_records_context_and_profile_values():
    result = _prompt(CAPABILITY_TIER_MEDIUM)

    assert result["profile_tier"] == CAPABILITY_TIER_MEDIUM
    assert result["context_variant"] == RENDERING_VARIANT_BALANCED
    assert result["metadata"]["approved_file_count"] == 3
    assert result["metadata"]["relationship_count"] == 2
    assert result["metadata"]["omission_count"] == 0


def test_character_counts_are_deterministic():
    first = _prompt(CAPABILITY_TIER_MEDIUM)["metadata"]
    second = _prompt(CAPABILITY_TIER_MEDIUM)["metadata"]

    assert first["static_instruction_character_count"] == second["static_instruction_character_count"]
    assert first["rendered_context_character_count"] == second["rendered_context_character_count"]
    assert first["prompt_character_count"] == second["prompt_character_count"]


def test_weak_static_guidance_is_longer_than_strong_guidance():
    weak = _prompt(CAPABILITY_TIER_WEAK)["metadata"]
    strong = _prompt(CAPABILITY_TIER_STRONG)["metadata"]

    assert weak["static_instruction_character_count"] > strong["static_instruction_character_count"]


def test_diff_example_is_static_and_synthetic():
    assert STATIC_DIFF_EXAMPLE == (
        "```diff\n"
        "--- a/example.py\n"
        "+++ b/example.py\n"
        "@@ -1 +1 @@\n"
        "-old_value = 1\n"
        "+old_value = 2\n"
        "```"
    )
    assert "src/" not in STATIC_DIFF_EXAMPLE
    assert "strata" not in STATIC_DIFF_EXAMPLE.lower()


def test_no_provider_or_exact_model_names_appear():
    text = json.dumps(_prompt(CAPABILITY_TIER_MEDIUM), sort_keys=True).lower()

    for forbidden in ("openai", "anthropic", "google", "gpt", "claude", "gemini", "provider", "model_name"):
        assert forbidden not in text


def test_no_filesystem_or_environment_access_is_required():
    public_names = {
        name
        for name in vars(prompt_templates)
        if not name.startswith("_")
    }

    assert "os" not in public_names
    assert "Path" not in public_names
    assert "open" not in public_names
    assert callable(render_prompt)


def test_no_api_key_or_secret_fields_appear():
    text = json.dumps(_prompt(CAPABILITY_TIER_MEDIUM), sort_keys=True).lower()

    for forbidden in ("api_key", "token_secret", "password", "credential"):
        assert forbidden not in text


def test_existing_part_i_part_m_o1_and_o2_contracts_remain_compatible():
    assert CONTEXT_ARTIFACT_PATH == ".aidc/context/strata_context.md"
    assert RUN_STATE_ARTIFACT_PATH == ".aidc/context/run_state.json"
    assert DIAGNOSTIC_SEVERITIES == ("info", "warning", "error")
    assert select_prompt_template(get_capability_profile(CAPABILITY_TIER_WEAK)).template_id == PROMPT_TEMPLATE_WEAK_PATCH
    assert _prompt(CAPABILITY_TIER_WEAK)["context_variant"] == RENDERING_VARIANT_COMPACT
    assert _prompt(CAPABILITY_TIER_STRONG)["context_variant"] == RENDERING_VARIANT_EXPANDED


def _prompt(tier: str) -> dict:
    profile = get_capability_profile(tier)
    return render_prompt(_rendered_context(profile), profile)


def _rendered_context(profile) -> dict:
    return render_context_pack(
        {
            "task": "Fix authentication header handling",
            "relevant_files": [
                build_represented_item(
                    path=f"src/file_{index}.py",
                    tier="symbol_slice",
                    reason=f"Relevant auth file {index}.",
                    priority=index,
                    score=10 - index,
                    excerpt=f"def auth_{index}(): pass",
                )
                for index in range(3)
            ],
            "relationships": [
                {
                    "source_path": "src/file_0.py",
                    "target_path": "src/file_1.py",
                    "relationship_type": "imports",
                },
                {
                    "source_path": "src/file_1.py",
                    "target_path": "src/file_2.py",
                    "relationship_type": "imports",
                },
            ],
            "budget_summary": {
                "target_context_tokens": 12000,
                "estimated_used_tokens": 3000,
                "reserved_output_tokens": 2000,
            },
        },
        profile,
    )


def _is_json_ready(value) -> bool:
    if value is None or isinstance(value, (str, int, bool)):
        return True
    if isinstance(value, list):
        return all(_is_json_ready(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _is_json_ready(item) for key, item in value.items())
    return False


TESTS = [
    test_stable_template_ids_exist,
    test_template_schema_version_is_stable,
    test_weak_profile_selects_weak_template,
    test_medium_profile_selects_medium_template,
    test_strong_profile_selects_strong_template,
    test_unknown_profile_selects_unknown_template,
    test_unknown_never_selects_strong_template,
    test_weak_prompt_includes_explicit_steps,
    test_weak_prompt_includes_unified_diff_example,
    test_unknown_prompt_includes_unified_diff_example,
    test_medium_prompt_does_not_require_diff_example,
    test_strong_prompt_does_not_require_diff_example,
    test_all_templates_require_unified_diff_output,
    test_all_templates_prohibit_invented_files,
    test_all_templates_preserve_scope_boundaries,
    test_rendered_o2_context_appears_exactly_once,
    test_prompt_section_ordering_is_deterministic,
    test_prompt_output_is_json_ready,
    test_repeated_rendering_is_deterministic,
    test_input_profile_is_not_mutated,
    test_input_rendered_context_is_not_mutated,
    test_missing_required_variable_raises_value_error,
    test_unsupported_variable_raises_value_error,
    test_unresolved_placeholder_raises_value_error,
    test_unsupported_template_id_raises_value_error,
    test_invalid_rendered_context_variant_raises_value_error,
    test_invalid_profile_input_raises_value_error,
    test_template_metadata_records_template_id_and_version,
    test_metadata_records_context_and_profile_values,
    test_character_counts_are_deterministic,
    test_weak_static_guidance_is_longer_than_strong_guidance,
    test_diff_example_is_static_and_synthetic,
    test_no_provider_or_exact_model_names_appear,
    test_no_filesystem_or_environment_access_is_required,
    test_no_api_key_or_secret_fields_appear,
    test_existing_part_i_part_m_o1_and_o2_contracts_remain_compatible,
]
