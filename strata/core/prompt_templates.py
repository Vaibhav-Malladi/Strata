import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from strata.core.capability_profiles import (
    CAPABILITY_TIER_MEDIUM,
    CAPABILITY_TIER_STRONG,
    CAPABILITY_TIER_UNKNOWN,
    CAPABILITY_TIER_WEAK,
    CAPABILITY_TIERS,
    CapabilityProfile,
)
from strata.core.context_rendering import (
    RENDERING_VARIANTS,
    render_context_pack_markdown,
    select_context_variant,
)


PROMPT_TEMPLATE_SCHEMA_VERSION = 1
PROMPT_TEMPLATE_VERSION = 1

PROMPT_TEMPLATE_WEAK_PATCH = "weak_patch"
PROMPT_TEMPLATE_MEDIUM_PATCH = "medium_patch"
PROMPT_TEMPLATE_STRONG_PATCH = "strong_patch"
PROMPT_TEMPLATE_UNKNOWN_PATCH = "unknown_patch"
PROMPT_TEMPLATE_IDS = (
    PROMPT_TEMPLATE_WEAK_PATCH,
    PROMPT_TEMPLATE_MEDIUM_PATCH,
    PROMPT_TEMPLATE_STRONG_PATCH,
    PROMPT_TEMPLATE_UNKNOWN_PATCH,
)

PROMPT_TEMPLATE_VARIABLE_TASK = "task"
PROMPT_TEMPLATE_VARIABLE_RENDERED_CONTEXT = "rendered_context"
PROMPT_TEMPLATE_VARIABLE_APPROVED_FILE_COUNT = "approved_file_count"
PROMPT_TEMPLATE_VARIABLE_RELATIONSHIP_COUNT = "relationship_count"
PROMPT_TEMPLATE_VARIABLE_OMISSION_COUNT = "omission_count"
PROMPT_TEMPLATE_VARIABLE_PROFILE_TIER = "profile_tier"
PROMPT_TEMPLATE_VARIABLE_CONTEXT_VARIANT = "context_variant"
PROMPT_TEMPLATE_VARIABLES = (
    PROMPT_TEMPLATE_VARIABLE_TASK,
    PROMPT_TEMPLATE_VARIABLE_RENDERED_CONTEXT,
    PROMPT_TEMPLATE_VARIABLE_APPROVED_FILE_COUNT,
    PROMPT_TEMPLATE_VARIABLE_RELATIONSHIP_COUNT,
    PROMPT_TEMPLATE_VARIABLE_OMISSION_COUNT,
    PROMPT_TEMPLATE_VARIABLE_PROFILE_TIER,
    PROMPT_TEMPLATE_VARIABLE_CONTEXT_VARIANT,
)

PROMPT_OUTPUT_FIELD_ORDER = (
    "schema_version",
    "template_id",
    "template_version",
    "profile_tier",
    "context_variant",
    "prompt",
    "sections",
    "metadata",
)

PROMPT_SECTION_ORDER = (
    "role",
    "task",
    "instructions",
    "context",
    "scope",
    "output",
    "safety",
    "diff_example",
)

_PLACEHOLDER_PATTERN = re.compile(r"\{\{([a-z_]+)\}\}")

UNIFIED_DIFF_OUTPUT_INSTRUCTION = (
    "Return only a valid unified diff using repository-relative paths. "
    "Modify only approved files unless an allowed related or new file is "
    "explicitly listed in the supplied context. Do not mix Markdown "
    "explanation into the diff."
)

SCOPE_INSTRUCTION = (
    "Work only from the supplied approved evidence. Do not alter unrelated "
    "files. Preserve existing behavior unless the task requires a change."
)

SAFETY_INSTRUCTION = (
    "Do not invent files, APIs, dependencies, or repository facts. Do not "
    "include secrets. If the supplied evidence is insufficient, say so instead "
    "of guessing."
)

STATIC_DIFF_EXAMPLE = (
    "```diff\n"
    "--- a/example.py\n"
    "+++ b/example.py\n"
    "@@ -1 +1 @@\n"
    "-old_value = 1\n"
    "+old_value = 2\n"
    "```"
)


def _validate_choice(value: str, field_name: str, choices: tuple[str, ...]) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string.")
    if value not in choices:
        raise ValueError(f"{field_name} must be one of: {', '.join(choices)}.")
    return value


@dataclass(frozen=True)
class PromptTemplate:
    template_id: str
    template_version: int
    profile_tier: str
    system_instruction: str
    task_section: str
    context_section: str
    scope_section: str
    output_section: str
    safety_section: str
    diff_example: str | None = None

    def __post_init__(self) -> None:
        _validate_choice(self.template_id, "template_id", PROMPT_TEMPLATE_IDS)
        if self.template_version != PROMPT_TEMPLATE_VERSION:
            raise ValueError(f"template_version must be {PROMPT_TEMPLATE_VERSION}.")
        _validate_choice(self.profile_tier, "profile_tier", CAPABILITY_TIERS)
        for field_name in (
            "system_instruction",
            "task_section",
            "context_section",
            "scope_section",
            "output_section",
            "safety_section",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string.")
        if self.diff_example is not None and not isinstance(self.diff_example, str):
            raise ValueError("diff_example must be a string or null.")


WEAK_PROMPT_TEMPLATE = PromptTemplate(
    template_id=PROMPT_TEMPLATE_WEAK_PATCH,
    template_version=PROMPT_TEMPLATE_VERSION,
    profile_tier=CAPABILITY_TIER_WEAK,
    system_instruction=(
        "You are a careful code-editing assistant. Follow the supplied evidence "
        "step by step and produce a safe patch."
    ),
    task_section="Task: {{task}}",
    context_section="Approved context:\n\n{{rendered_context}}",
    scope_section=SCOPE_INSTRUCTION,
    output_section=UNIFIED_DIFF_OUTPUT_INSTRUCTION,
    safety_section=(
        SAFETY_INSTRUCTION
        + " First identify the approved files, then decide whether the evidence is sufficient, then return the diff."
    ),
    diff_example=STATIC_DIFF_EXAMPLE,
)

MEDIUM_PROMPT_TEMPLATE = PromptTemplate(
    template_id=PROMPT_TEMPLATE_MEDIUM_PATCH,
    template_version=PROMPT_TEMPLATE_VERSION,
    profile_tier=CAPABILITY_TIER_MEDIUM,
    system_instruction="You are a code-editing assistant producing a scoped repository patch.",
    task_section="Task: {{task}}",
    context_section="Approved context:\n\n{{rendered_context}}",
    scope_section=SCOPE_INSTRUCTION,
    output_section=UNIFIED_DIFF_OUTPUT_INSTRUCTION,
    safety_section=SAFETY_INSTRUCTION,
)

STRONG_PROMPT_TEMPLATE = PromptTemplate(
    template_id=PROMPT_TEMPLATE_STRONG_PATCH,
    template_version=PROMPT_TEMPLATE_VERSION,
    profile_tier=CAPABILITY_TIER_STRONG,
    system_instruction="Produce a scoped patch from the approved context.",
    task_section="Task: {{task}}",
    context_section="Approved context:\n\n{{rendered_context}}",
    scope_section="Stay within the approved evidence and avoid out-of-scope changes.",
    output_section=UNIFIED_DIFF_OUTPUT_INSTRUCTION,
    safety_section="Do not invent files or repository facts. Do not include secrets.",
)

UNKNOWN_PROMPT_TEMPLATE = PromptTemplate(
    template_id=PROMPT_TEMPLATE_UNKNOWN_PATCH,
    template_version=PROMPT_TEMPLATE_VERSION,
    profile_tier=CAPABILITY_TIER_UNKNOWN,
    system_instruction=(
        "You are a careful code-editing assistant. Treat capability as unknown "
        "and follow the supplied evidence explicitly."
    ),
    task_section="Task: {{task}}",
    context_section="Approved context:\n\n{{rendered_context}}",
    scope_section=SCOPE_INSTRUCTION,
    output_section=UNIFIED_DIFF_OUTPUT_INSTRUCTION,
    safety_section=SAFETY_INSTRUCTION,
    diff_example=STATIC_DIFF_EXAMPLE,
)

BUILT_IN_PROMPT_TEMPLATES = MappingProxyType(
    {
        PROMPT_TEMPLATE_WEAK_PATCH: WEAK_PROMPT_TEMPLATE,
        PROMPT_TEMPLATE_MEDIUM_PATCH: MEDIUM_PROMPT_TEMPLATE,
        PROMPT_TEMPLATE_STRONG_PATCH: STRONG_PROMPT_TEMPLATE,
        PROMPT_TEMPLATE_UNKNOWN_PATCH: UNKNOWN_PROMPT_TEMPLATE,
    }
)

_TEMPLATE_ID_BY_TIER = MappingProxyType(
    {
        CAPABILITY_TIER_WEAK: PROMPT_TEMPLATE_WEAK_PATCH,
        CAPABILITY_TIER_MEDIUM: PROMPT_TEMPLATE_MEDIUM_PATCH,
        CAPABILITY_TIER_STRONG: PROMPT_TEMPLATE_STRONG_PATCH,
        CAPABILITY_TIER_UNKNOWN: PROMPT_TEMPLATE_UNKNOWN_PATCH,
    }
)


def get_prompt_template(template_id: str) -> PromptTemplate:
    template_id = _validate_choice(template_id, "template_id", PROMPT_TEMPLATE_IDS)
    return BUILT_IN_PROMPT_TEMPLATES[template_id]


def select_prompt_template(profile: CapabilityProfile) -> PromptTemplate:
    _validate_profile(profile)
    return get_prompt_template(_TEMPLATE_ID_BY_TIER[profile.tier])


def render_prompt(
    rendered_context,
    profile: CapabilityProfile,
) -> dict[str, object]:
    if not isinstance(rendered_context, Mapping):
        raise ValueError("rendered_context must be a mapping.")
    _validate_profile(profile)
    _validate_rendered_context(rendered_context, profile)

    template = select_prompt_template(profile)
    context_variant = str(rendered_context["variant"])
    rendered_context_markdown = render_context_pack_markdown(rendered_context)
    variables = {
        PROMPT_TEMPLATE_VARIABLE_TASK: str(rendered_context["task"]),
        PROMPT_TEMPLATE_VARIABLE_RENDERED_CONTEXT: rendered_context_markdown,
        PROMPT_TEMPLATE_VARIABLE_APPROVED_FILE_COUNT: len(rendered_context["files"]),
        PROMPT_TEMPLATE_VARIABLE_RELATIONSHIP_COUNT: len(rendered_context["relationships"]),
        PROMPT_TEMPLATE_VARIABLE_OMISSION_COUNT: len(rendered_context["omissions"]),
        PROMPT_TEMPLATE_VARIABLE_PROFILE_TIER: profile.tier,
        PROMPT_TEMPLATE_VARIABLE_CONTEXT_VARIANT: context_variant,
    }

    sections = _render_sections(template, variables)
    prompt = _compose_prompt(sections, template.diff_example is not None)
    _reject_unresolved_placeholders(prompt)
    static_character_count = sum(
        len(value)
        for key, value in sections.items()
        if key != "context" and isinstance(value, str)
    )

    result = {
        "schema_version": PROMPT_TEMPLATE_SCHEMA_VERSION,
        "template_id": template.template_id,
        "template_version": template.template_version,
        "profile_tier": profile.tier,
        "context_variant": context_variant,
        "prompt": prompt,
        "sections": sections,
        "metadata": {
            "approved_file_count": len(rendered_context["files"]),
            "relationship_count": len(rendered_context["relationships"]),
            "omission_count": len(rendered_context["omissions"]),
            "includes_diff_example": template.diff_example is not None,
            "needs_explicit_steps": profile.needs_explicit_steps,
            "static_instruction_character_count": static_character_count,
            "rendered_context_character_count": len(rendered_context_markdown),
            "prompt_character_count": len(prompt),
        },
    }
    _validate_json_ready(result)
    return result


def render_template_text(template_text: str, variables: Mapping[str, object]) -> str:
    if not isinstance(template_text, str):
        raise ValueError("template_text must be a string.")
    if not isinstance(variables, Mapping):
        raise ValueError("variables must be a mapping.")

    for key in variables:
        _validate_choice(str(key), "variable", PROMPT_TEMPLATE_VARIABLES)

    placeholders = tuple(_PLACEHOLDER_PATTERN.findall(template_text))
    for placeholder in placeholders:
        _validate_choice(placeholder, "placeholder", PROMPT_TEMPLATE_VARIABLES)
        if placeholder not in variables:
            raise ValueError(f"Missing required template variable: {placeholder}")

    rendered = template_text
    for placeholder in placeholders:
        rendered = rendered.replace(
            "{{" + placeholder + "}}",
            str(variables[placeholder]),
        )

    _reject_unresolved_placeholders(rendered)
    return rendered


def _render_sections(
    template: PromptTemplate,
    variables: Mapping[str, object],
) -> dict[str, str | None]:
    sections: dict[str, str | None] = {
        "role": render_template_text(template.system_instruction, variables),
        "task": render_template_text(template.task_section, variables),
        "instructions": _instruction_summary(template.profile_tier),
        "context": render_template_text(template.context_section, variables),
        "scope": render_template_text(template.scope_section, variables),
        "output": render_template_text(template.output_section, variables),
        "safety": render_template_text(template.safety_section, variables),
        "diff_example": template.diff_example,
    }
    return sections


def _compose_prompt(sections: Mapping[str, str | None], include_diff_example: bool) -> str:
    lines: list[str] = []
    headings = {
        "role": "## Role",
        "task": "## Task",
        "instructions": "## Instructions",
        "context": "## Approved Context",
        "scope": "## Scope",
        "output": "## Output Format",
        "safety": "## Safety",
        "diff_example": "## Unified Diff Example",
    }
    for section_name in PROMPT_SECTION_ORDER:
        if section_name == "diff_example" and not include_diff_example:
            continue
        value = sections.get(section_name)
        if value is None:
            continue
        lines.append(headings[section_name])
        lines.append("")
        lines.append(str(value).rstrip())
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _instruction_summary(profile_tier: str) -> str:
    if profile_tier == CAPABILITY_TIER_WEAK:
        return (
            "Follow these steps: read the task, inspect only the approved context, "
            "decide whether evidence is sufficient, then return only the unified diff."
        )
    if profile_tier == CAPABILITY_TIER_UNKNOWN:
        return (
            "Use the approved context carefully. If evidence is insufficient, say so. "
            "Return only the unified diff when making changes."
        )
    if profile_tier == CAPABILITY_TIER_MEDIUM:
        return "Use the approved context and return a scoped unified diff."
    return "Return a scoped unified diff from the approved context."


def _validate_rendered_context(rendered_context: Mapping, profile: CapabilityProfile) -> None:
    required_fields = (
        "variant",
        "profile_tier",
        "task",
        "instructions",
        "files",
        "relationships",
        "budget",
        "omissions",
        "metadata",
    )
    for field in required_fields:
        if field not in rendered_context:
            raise ValueError(f"rendered_context is missing required field: {field}")

    if rendered_context["variant"] not in RENDERING_VARIANTS:
        raise ValueError("rendered_context variant is unsupported.")
    if rendered_context["variant"] != select_context_variant(profile):
        raise ValueError("rendered_context variant does not match profile.")
    if rendered_context["profile_tier"] not in CAPABILITY_TIERS:
        raise ValueError("rendered_context profile_tier is unsupported.")
    if rendered_context["profile_tier"] != profile.tier:
        raise ValueError("rendered_context profile_tier does not match profile.")
    for field in ("instructions", "files", "relationships", "omissions"):
        if not isinstance(rendered_context[field], list):
            raise ValueError(f"rendered_context field '{field}' must be a list.")
    for field in ("budget", "metadata"):
        if not isinstance(rendered_context[field], Mapping):
            raise ValueError(f"rendered_context field '{field}' must be a mapping.")
    if not isinstance(rendered_context["task"], str):
        raise ValueError("rendered_context field 'task' must be a string.")


def _reject_unresolved_placeholders(value: str) -> None:
    if "{{" in value or "}}" in value or _PLACEHOLDER_PATTERN.search(value):
        raise ValueError("Rendered prompt contains unresolved placeholders.")


def _validate_profile(profile: CapabilityProfile) -> None:
    if not isinstance(profile, CapabilityProfile):
        raise ValueError("profile must be a CapabilityProfile.")


def _validate_json_ready(value) -> None:
    if _copy_json_value(value) is _UNSUPPORTED:
        raise ValueError("rendered prompt must be JSON-ready.")


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


def _stable_json(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False)
