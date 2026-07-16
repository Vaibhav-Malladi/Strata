import json
from collections.abc import Mapping

from strata.core.capability_profiles import (
    CONTEXT_VARIANT_BALANCED,
    CONTEXT_VARIANT_COMPACT,
    CONTEXT_VARIANT_EXPANDED,
    CONTEXT_VARIANTS,
    CapabilityProfile,
)
from strata.core.context_artifacts import (
    REPRESENTATION_TIER_FILE_OUTLINE,
    REPRESENTATION_TIER_METHOD_CLASS_SLICE,
    REPRESENTATION_TIER_PATH_ONLY,
    REPRESENTATION_TIER_SKIPPED,
    REPRESENTATION_TIER_SYMBOL_SLICE,
    REPRESENTATION_TIER_WHOLE_FILE,
    REPRESENTATION_TIERS,
)
import strata.utils.workspace_context as workspace_context_utils


RENDERING_VARIANT_COMPACT = CONTEXT_VARIANT_COMPACT
RENDERING_VARIANT_BALANCED = CONTEXT_VARIANT_BALANCED
RENDERING_VARIANT_EXPANDED = CONTEXT_VARIANT_EXPANDED
RENDERING_VARIANTS = (
    RENDERING_VARIANT_COMPACT,
    RENDERING_VARIANT_BALANCED,
    RENDERING_VARIANT_EXPANDED,
)

RENDERED_CONTEXT_FIELD_ORDER = (
    "variant",
    "profile_tier",
    "task",
    "instructions",
    "files",
    "relationships",
    "workspace_context",
    "budget",
    "omissions",
    "metadata",
)

OMISSION_KIND_FILE_LIMIT = "file_limit"
OMISSION_KIND_RELATIONSHIP_LIMIT = "relationship_limit"
OMISSION_KIND_REPRESENTATION_DOWNGRADE = "representation_downgrade"
OMISSION_KIND_UNSUPPORTED_ITEM_SHAPE = "unsupported_item_shape"
OMISSION_KINDS = (
    OMISSION_KIND_FILE_LIMIT,
    OMISSION_KIND_RELATIONSHIP_LIMIT,
    OMISSION_KIND_REPRESENTATION_DOWNGRADE,
    OMISSION_KIND_UNSUPPORTED_ITEM_SHAPE,
)

RELATIONSHIP_LIMITS_BY_VARIANT = {
    RENDERING_VARIANT_COMPACT: 4,
    RENDERING_VARIANT_BALANCED: 8,
    RENDERING_VARIANT_EXPANDED: 16,
}

COMPACT_FILE_LIMIT = 8

_FILE_COLLECTION_FIELDS = (
    "files",
    "relevant_files",
    "represented_items",
    "included_files",
)
_RELATIONSHIP_COLLECTION_FIELDS = (
    "relationships",
    "dependency_traces",
    "dependency_edges",
    "frontend_relationships",
    "backend_relationships",
    "internal_library_relationships",
    "cross_repo_references",
)


def select_context_variant(profile: CapabilityProfile) -> str:
    """Return the rendering variant preferred by a capability profile."""

    _validate_profile(profile)
    return _validate_variant(profile.preferred_context_variant)


def render_context_pack(
    context_pack,
    profile: CapabilityProfile,
) -> dict[str, object]:
    """Render an approved canonical context-pack mapping for a capability profile."""

    if not isinstance(context_pack, Mapping):
        raise ValueError("context_pack must be a mapping.")
    _validate_profile(profile)

    variant = select_context_variant(profile)
    omissions: list[dict[str, object]] = []
    files = _render_files(context_pack, profile, variant, omissions)
    relationships = _render_relationships(context_pack, variant, omissions)
    workspace_context = _render_workspace_context(context_pack, omissions)
    budget = _render_budget(context_pack, profile, files, relationships)

    result = {
        "variant": variant,
        "profile_tier": profile.tier,
        "task": _string_value(context_pack.get("task")),
        "instructions": _instruction_blocks(variant),
        "files": files,
        "relationships": relationships,
        "budget": budget,
        "omissions": _order_omissions(omissions),
        "metadata": {
            "renderer": "capability_context_rendering",
            "canonical_input": True,
            "rendered_file_count": len(files),
            "rendered_relationship_count": len(relationships),
            "rendered_workspace_context": bool(workspace_context),
        },
    }
    if workspace_context:
        result["workspace_context"] = workspace_context
    _validate_json_ready(result)
    return result


def render_context_pack_markdown(rendered_pack) -> str:
    """Render a deterministic Markdown view of a rendered context pack."""

    if not isinstance(rendered_pack, Mapping):
        raise ValueError("rendered_pack must be a mapping.")

    lines: list[str] = ["# Strata AI Context", ""]
    lines.extend(_markdown_section("## Task", [_string_value(rendered_pack.get("task")) or "- none"]))
    lines.extend(_markdown_instructions(rendered_pack.get("instructions")))
    lines.extend(_markdown_files(rendered_pack.get("files")))
    lines.extend(_markdown_relationships(rendered_pack.get("relationships")))
    if isinstance(rendered_pack.get("workspace_context"), Mapping):
        lines.extend(workspace_context_utils.render_workspace_context_markdown(rendered_pack["workspace_context"]).rstrip().splitlines())
        lines.append("")
    lines.extend(_markdown_mapping("## Budget", rendered_pack.get("budget")))
    lines.extend(_markdown_omissions(rendered_pack.get("omissions")))
    return "\n".join(lines).rstrip() + "\n"


def _render_files(
    context_pack: Mapping,
    profile: CapabilityProfile,
    variant: str,
    omissions: list[dict[str, object]],
) -> list[dict[str, object]]:
    raw_items = _collect_items(context_pack, _FILE_COLLECTION_FIELDS)
    normalized: list[dict[str, object]] = []
    malformed = 0
    skipped = 0

    for item in raw_items:
        file_item = _normalize_file_item(item)
        if file_item is None:
            malformed += 1
            continue
        if file_item["representation_tier"] == REPRESENTATION_TIER_SKIPPED:
            skipped += 1
            continue
        normalized.append(file_item)

    if malformed:
        omissions.append(_omission(
            OMISSION_KIND_UNSUPPORTED_ITEM_SHAPE,
            malformed,
            "Malformed file items were not rendered.",
        ))
    if skipped:
        omissions.append(_omission(
            OMISSION_KIND_REPRESENTATION_DOWNGRADE,
            skipped,
            "Skipped represented items remain omitted from rendered file content.",
        ))

    ordered = sorted(normalized, key=_file_sort_key)
    limit = _file_limit(profile, variant)
    selected = ordered[:limit]
    omitted = max(0, len(ordered) - len(selected))
    if omitted:
        omissions.append(_omission(
            OMISSION_KIND_FILE_LIMIT,
            omitted,
            f"The selected capability profile limits this rendering to {limit} files.",
        ))

    rendered = [_render_file_item(item, variant, omissions) for item in selected]
    return rendered


def _render_relationships(
    context_pack: Mapping,
    variant: str,
    omissions: list[dict[str, object]],
) -> list[dict[str, object]]:
    raw_items = _collect_items(context_pack, _RELATIONSHIP_COLLECTION_FIELDS)
    normalized: list[dict[str, object]] = []
    malformed = 0

    for item in raw_items:
        relationship = _normalize_relationship_item(item)
        if relationship is None:
            malformed += 1
            continue
        normalized.append(relationship)

    if malformed:
        omissions.append(_omission(
            OMISSION_KIND_UNSUPPORTED_ITEM_SHAPE,
            malformed,
            "Malformed relationship items were not rendered.",
        ))

    deduped = _dedupe_mappings(normalized)
    ordered = sorted(deduped, key=_stable_json)
    limit = RELATIONSHIP_LIMITS_BY_VARIANT[variant]
    selected = ordered[:limit]
    omitted = max(0, len(ordered) - len(selected))
    if omitted:
        omissions.append(_omission(
            OMISSION_KIND_RELATIONSHIP_LIMIT,
            omitted,
            f"The {variant} rendering includes at most {limit} relationships.",
        ))
    return selected


def _render_budget(
    context_pack: Mapping,
    profile: CapabilityProfile,
    files: list[dict[str, object]],
    relationships: list[dict[str, object]],
) -> dict[str, object]:
    budget = context_pack.get("budget_summary")
    if budget is None:
        budget = context_pack.get("budget")
    canonical = budget if isinstance(budget, Mapping) else {}

    return {
        "canonical_target_tokens": _optional_int(canonical.get("target_context_tokens")),
        "canonical_estimated_tokens": _optional_int(canonical.get("estimated_used_tokens")),
        "canonical_reserved_output_tokens": _optional_int(canonical.get("reserved_output_tokens")),
        "canonical_max_context_pack_tokens": _optional_int(canonical.get("max_context_pack_tokens")),
        "rendered_file_count": len(files),
        "rendered_relationship_count": len(relationships),
        "profile_file_limit": profile.max_recommended_files,
        "budget_data_present": bool(canonical),
    }


def _render_workspace_context(
    context_pack: Mapping,
    omissions: list[dict[str, object]],
) -> dict[str, object]:
    workspace_context = context_pack.get("workspace_context")
    if workspace_context is None:
        return {}
    if not isinstance(workspace_context, Mapping):
        omissions.append(_omission(OMISSION_KIND_UNSUPPORTED_ITEM_SHAPE, 1, "Malformed workspace context was not rendered."))
        return {}
    try:
        return workspace_context_utils.workspace_context_to_dict(workspace_context)
    except Exception:
        omissions.append(_omission(OMISSION_KIND_UNSUPPORTED_ITEM_SHAPE, 1, "Malformed workspace context was not rendered."))
        return {}


def _instruction_blocks(variant: str) -> list[dict[str, str]]:
    if variant == RENDERING_VARIANT_COMPACT:
        return [
            {"category": "task", "text": "Use only the approved evidence in this rendered context."},
            {"category": "scope", "text": "Work only on the listed files unless a related file is explicitly approved."},
            {"category": "output_format", "text": "Return a unified diff and briefly note any uncertainty."},
            {"category": "safety", "text": "Do not invent files, APIs, dependencies, or repository facts."},
            {"category": "safety", "text": "Explain when the supplied evidence is insufficient."},
        ]
    if variant == RENDERING_VARIANT_BALANCED:
        return [
            {"category": "task", "text": "Use the approved context to make the requested change."},
            {"category": "scope", "text": "Stay within listed files and explicitly approved related files."},
            {"category": "output_format", "text": "Return a unified diff with concise notes if evidence is missing."},
            {"category": "safety", "text": "Do not invent repository facts."},
        ]
    return [
        {"category": "task", "text": "Use the approved context to make the requested change."},
        {"category": "scope", "text": "Stay within the approved evidence."},
        {"category": "output_format", "text": "Return a unified diff."},
    ]


def _normalize_file_item(item) -> dict[str, object] | None:
    if not isinstance(item, Mapping):
        return None

    source = item.get("file") if isinstance(item.get("file"), Mapping) else item
    path = _string_value(source.get("path") if isinstance(source, Mapping) else item.get("path"))
    if not path:
        return None

    tier = _string_value(
        item.get("representation_tier")
        or item.get("tier")
        or source.get("representation_tier")
        or source.get("tier")
        or REPRESENTATION_TIER_FILE_OUTLINE
    )
    if tier not in REPRESENTATION_TIERS:
        return None

    return {
        "path": path.replace("\\", "/"),
        "role": _string_value(item.get("role") or source.get("role") or item.get("source_type")),
        "representation_tier": tier,
        "summary": _string_value(item.get("summary") or source.get("summary") or item.get("reason")),
        "symbols": _string_list(item.get("symbols") or source.get("symbols")),
        "reason": _string_value(item.get("reason") or source.get("reason")),
        "source_type": _string_value(item.get("source_type") or source.get("source_type")),
        "priority": _optional_int(item.get("priority")),
        "score": _score_value(item.get("score")),
        "content": _optional_string(item.get("content") or source.get("content")),
        "excerpt": _optional_string(item.get("excerpt") or source.get("excerpt")),
    }


def _render_file_item(
    item: Mapping,
    variant: str,
    omissions: list[dict[str, object]],
) -> dict[str, object]:
    tier = item["representation_tier"]
    rendered = {
        "path": item["path"],
        "role": item["role"],
        "representation_tier": tier,
        "summary": item["summary"],
        "symbols": list(item["symbols"])[: _symbol_limit(variant)],
        "reason": item["reason"],
        "source_type": item["source_type"],
        "priority": item["priority"],
        "score": item["score"],
    }

    if tier == REPRESENTATION_TIER_PATH_ONLY:
        return rendered

    if variant == RENDERING_VARIANT_EXPANDED:
        if item.get("excerpt") is not None:
            rendered["excerpt"] = item["excerpt"]
        if tier == REPRESENTATION_TIER_WHOLE_FILE and item.get("content") is not None:
            rendered["content"] = item["content"]
        return rendered

    if variant == RENDERING_VARIANT_BALANCED:
        if tier in {
            REPRESENTATION_TIER_SYMBOL_SLICE,
            REPRESENTATION_TIER_METHOD_CLASS_SLICE,
            REPRESENTATION_TIER_FILE_OUTLINE,
        } and item.get("excerpt") is not None:
            rendered["excerpt"] = item["excerpt"]
        if item.get("content") is not None:
            omissions.append(_omission(
                OMISSION_KIND_REPRESENTATION_DOWNGRADE,
                1,
                "Approved file content was rendered as summary or excerpt for this variant.",
            ))
        return rendered

    if item.get("content") is not None or item.get("excerpt") is not None:
        omissions.append(_omission(
            OMISSION_KIND_REPRESENTATION_DOWNGRADE,
            1,
            "Approved file evidence was rendered as path, role, summary, and symbols for compact output.",
        ))
    return rendered


def _normalize_relationship_item(item) -> dict[str, object] | None:
    if not isinstance(item, Mapping):
        return None
    copied = _copy_json_mapping(item)
    if copied is None or not copied:
        return None
    return copied


def _collect_items(context_pack: Mapping, fields: tuple[str, ...]) -> list[object]:
    collected: list[object] = []
    for field in fields:
        value = context_pack.get(field)
        if value is None:
            continue
        if isinstance(value, list) or isinstance(value, tuple):
            collected.extend(value)
            continue
        if isinstance(value, Mapping):
            collected.append(value)
            continue
        raise ValueError(f"context_pack field '{field}' must be a list, tuple, mapping, or null.")
    return collected


def _file_limit(profile: CapabilityProfile, variant: str) -> int:
    if variant == RENDERING_VARIANT_COMPACT:
        return min(profile.max_recommended_files, COMPACT_FILE_LIMIT)
    return profile.max_recommended_files


def _file_sort_key(item: Mapping) -> tuple[object, ...]:
    return (
        _none_last_number(item.get("priority")),
        _score_sort_value(item.get("score")),
        str(item.get("path") or ""),
        str(item.get("representation_tier") or ""),
        str(item.get("role") or ""),
    )


def _score_sort_value(value) -> tuple[int, object]:
    if value is None:
        return (1, 0)
    if isinstance(value, int) and not isinstance(value, bool):
        return (0, -value)
    return (0, str(value))


def _none_last_number(value) -> tuple[int, object]:
    if value is None:
        return (1, 0)
    if isinstance(value, int) and not isinstance(value, bool):
        return (0, value)
    return (0, str(value))


def _symbol_limit(variant: str) -> int:
    if variant == RENDERING_VARIANT_COMPACT:
        return 5
    if variant == RENDERING_VARIANT_BALANCED:
        return 10
    return 20


def _dedupe_mappings(items: list[dict[str, object]]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    seen = set()
    for item in items:
        key = _stable_json(item)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _order_omissions(omissions: list[dict[str, object]]) -> list[dict[str, object]]:
    merged: dict[tuple[str, str], dict[str, object]] = {}
    for item in omissions:
        key = (str(item["kind"]), str(item["reason"]))
        if key not in merged:
            merged[key] = dict(item)
            continue
        merged[key]["count"] = int(merged[key]["count"]) + int(item["count"])
    return sorted(merged.values(), key=lambda item: (str(item["kind"]), str(item["reason"])))


def _omission(kind: str, count: int, reason: str) -> dict[str, object]:
    if kind not in OMISSION_KINDS:
        raise ValueError(f"Unsupported omission kind: {kind}")
    return {
        "kind": kind,
        "count": int(count),
        "reason": str(reason),
    }


def _validate_profile(profile: CapabilityProfile) -> None:
    if not isinstance(profile, CapabilityProfile):
        raise ValueError("profile must be a CapabilityProfile.")


def _validate_variant(variant: str) -> str:
    if variant not in CONTEXT_VARIANTS or variant not in RENDERING_VARIANTS:
        raise ValueError(f"variant must be one of: {', '.join(RENDERING_VARIANTS)}.")
    return variant


def _copy_json_mapping(mapping: Mapping) -> dict[str, object] | None:
    copied: dict[str, object] = {}
    for key in sorted(mapping.keys(), key=str):
        if not isinstance(key, str):
            return None
        value = _copy_json_value(mapping[key])
        if value is _UNSUPPORTED:
            return None
        copied[key] = value
    return copied


_UNSUPPORTED = object()


def _copy_json_value(value):
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        return str(value)
    if isinstance(value, Mapping):
        copied = _copy_json_mapping(value)
        if copied is None:
            return _UNSUPPORTED
        return copied
    if isinstance(value, list) or isinstance(value, tuple):
        copied = []
        for item in value:
            rendered = _copy_json_value(item)
            if rendered is _UNSUPPORTED:
                return _UNSUPPORTED
            copied.append(rendered)
        return copied
    return _UNSUPPORTED


def _validate_json_ready(value) -> None:
    if _copy_json_value(value) is _UNSUPPORTED:
        raise ValueError("rendered context pack must be JSON-ready.")


def _optional_int(value) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    return None


def _score_value(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return str(value)
    if isinstance(value, str):
        return value
    return None


def _optional_string(value) -> str | None:
    if value is None:
        return None
    return str(value)


def _string_value(value) -> str:
    if value is None:
        return ""
    return str(value)


def _string_list(value) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        return [str(value)] if str(value) else []
    return [str(item) for item in value if str(item)]


def _stable_json(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _markdown_section(heading: str, lines: list[str]) -> list[str]:
    return [heading, "", *(lines or ["- none"]), ""]


def _markdown_instructions(instructions) -> list[str]:
    lines = ["## Instructions", ""]
    items = instructions if isinstance(instructions, list) else []
    for item in items:
        if isinstance(item, Mapping):
            lines.append(f"- `{_string_value(item.get('category'))}`: {_string_value(item.get('text'))}")
    if len(lines) == 2:
        lines.append("- none")
    lines.append("")
    return lines


def _markdown_files(files) -> list[str]:
    lines = ["## Approved Files", ""]
    items = files if isinstance(files, list) else []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        lines.append(f"- `{_string_value(item.get('path'))}` ({_string_value(item.get('representation_tier'))})")
        if item.get("role"):
            lines.append(f"  - Role: {_string_value(item.get('role'))}")
        if item.get("summary"):
            lines.append(f"  - Summary: {_string_value(item.get('summary'))}")
        if item.get("symbols"):
            lines.append(f"  - Symbols: {', '.join(_string_list(item.get('symbols')))}")
    if len(lines) == 2:
        lines.append("- none")
    lines.append("")
    return lines


def _markdown_relationships(relationships) -> list[str]:
    lines = ["## Relationships", ""]
    items = relationships if isinstance(relationships, list) else []
    for item in items:
        if isinstance(item, Mapping):
            lines.append(f"- `{_stable_json(item)}`")
    if len(lines) == 2:
        lines.append("- none")
    lines.append("")
    return lines


def _markdown_mapping(heading: str, value) -> list[str]:
    if not isinstance(value, Mapping):
        return [heading, "", "- none", ""]
    return [heading, "", "```json", json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False), "```", ""]


def _markdown_omissions(omissions) -> list[str]:
    lines = ["## Omitted Evidence", ""]
    items = omissions if isinstance(omissions, list) else []
    for item in items:
        if isinstance(item, Mapping):
            lines.append(
                f"- `{_string_value(item.get('kind'))}` ({item.get('count', 0)}): "
                f"{_string_value(item.get('reason'))}"
            )
    if len(lines) == 2:
        lines.append("- none")
    lines.append("")
    return lines
