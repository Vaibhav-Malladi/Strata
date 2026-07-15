import copy
import json

import strata.core.context_rendering as context_rendering
from strata.core.capability_profiles import (
    CAPABILITY_TIER_MEDIUM,
    CAPABILITY_TIER_STRONG,
    CAPABILITY_TIER_UNKNOWN,
    CAPABILITY_TIER_WEAK,
    get_capability_profile,
)
from strata.core.context_artifacts import (
    CONTEXT_ARTIFACT_PATH,
    REPRESENTATION_TIER_FILE_OUTLINE,
    REPRESENTATION_TIER_PATH_ONLY,
    REPRESENTATION_TIER_SKIPPED,
    REPRESENTATION_TIER_SYMBOL_SLICE,
    REPRESENTATION_TIER_WHOLE_FILE,
    RUN_STATE_ARTIFACT_PATH,
    build_represented_item,
)
from strata.core.context_rendering import (
    RELATIONSHIP_LIMITS_BY_VARIANT,
    RENDERING_VARIANT_BALANCED,
    RENDERING_VARIANT_COMPACT,
    RENDERING_VARIANT_EXPANDED,
    RENDERING_VARIANTS,
    render_context_pack,
    render_context_pack_markdown,
    select_context_variant,
)
from strata.core.diagnostics import DIAGNOSTIC_SEVERITIES


def test_rendering_variants_are_compact_balanced_expanded():
    assert RENDERING_VARIANTS == ("compact", "balanced", "expanded")


def test_weak_profile_selects_compact():
    assert select_context_variant(get_capability_profile(CAPABILITY_TIER_WEAK)) == RENDERING_VARIANT_COMPACT


def test_medium_profile_selects_balanced():
    assert select_context_variant(get_capability_profile(CAPABILITY_TIER_MEDIUM)) == RENDERING_VARIANT_BALANCED


def test_strong_profile_selects_expanded():
    assert select_context_variant(get_capability_profile(CAPABILITY_TIER_STRONG)) == RENDERING_VARIANT_EXPANDED


def test_unknown_profile_selects_balanced():
    assert select_context_variant(get_capability_profile(CAPABILITY_TIER_UNKNOWN)) == RENDERING_VARIANT_BALANCED


def test_unknown_never_silently_selects_expanded():
    rendered = render_context_pack(_context_pack(file_count=20), get_capability_profile(CAPABILITY_TIER_UNKNOWN))

    assert rendered["variant"] == RENDERING_VARIANT_BALANCED
    assert rendered["variant"] != RENDERING_VARIANT_EXPANDED


def test_rendered_output_is_json_ready():
    rendered = render_context_pack(_context_pack(), get_capability_profile(CAPABILITY_TIER_MEDIUM))

    assert json.loads(json.dumps(rendered, allow_nan=False)) == rendered
    assert _is_json_ready(rendered)


def test_repeated_rendering_is_deterministic():
    context_pack = _context_pack(file_count=12, relationship_count=12)
    profile = get_capability_profile(CAPABILITY_TIER_MEDIUM)

    assert render_context_pack(context_pack, profile) == render_context_pack(context_pack, profile)


def test_input_context_pack_is_not_mutated():
    context_pack = _context_pack(file_count=12, relationship_count=12)
    before = copy.deepcopy(context_pack)

    render_context_pack(context_pack, get_capability_profile(CAPABILITY_TIER_MEDIUM))

    assert context_pack == before


def test_input_profile_is_not_mutated():
    profile = get_capability_profile(CAPABILITY_TIER_MEDIUM)
    before = profile.to_dict()

    render_context_pack(_context_pack(), profile)

    assert profile.to_dict() == before


def test_file_ordering_is_deterministic():
    context_pack = {
        "task": "Fix auth",
        "relevant_files": [
            _file("src/b.py", priority=2, score=99),
            _file("src/c.py", priority=1, score=3),
            _file("src/a.py", priority=1, score=10),
        ],
    }

    rendered = render_context_pack(context_pack, get_capability_profile(CAPABILITY_TIER_MEDIUM))

    assert [item["path"] for item in rendered["files"]] == ["src/a.py", "src/c.py", "src/b.py"]


def test_file_limits_are_respected():
    rendered = render_context_pack(_context_pack(file_count=20), get_capability_profile(CAPABILITY_TIER_MEDIUM))

    assert len(rendered["files"]) == 16
    assert rendered["budget"]["profile_file_limit"] == 16


def test_compact_includes_fewer_files_than_balanced_when_enough_files_exist():
    context_pack = _context_pack(file_count=12)

    compact = render_context_pack(context_pack, get_capability_profile(CAPABILITY_TIER_WEAK))
    balanced = render_context_pack(context_pack, get_capability_profile(CAPABILITY_TIER_MEDIUM))

    assert len(compact["files"]) == 8
    assert len(balanced["files"]) == 12
    assert len(compact["files"]) < len(balanced["files"])


def test_expanded_remains_bounded():
    rendered = render_context_pack(_context_pack(file_count=35), get_capability_profile(CAPABILITY_TIER_STRONG))

    assert len(rendered["files"]) == 30


def test_path_only_items_are_never_upgraded():
    context_pack = {"task": "Fix auth", "relevant_files": [_file("src/path_only.py", tier=REPRESENTATION_TIER_PATH_ONLY)]}

    rendered = render_context_pack(context_pack, get_capability_profile(CAPABILITY_TIER_STRONG))
    item = rendered["files"][0]

    assert item["representation_tier"] == REPRESENTATION_TIER_PATH_ONLY
    assert "content" not in item
    assert "excerpt" not in item


def test_skipped_items_do_not_become_rendered_content():
    context_pack = {"task": "Fix auth", "relevant_files": [_file("dist/bundle.js", tier=REPRESENTATION_TIER_SKIPPED)]}

    rendered = render_context_pack(context_pack, get_capability_profile(CAPABILITY_TIER_STRONG))

    assert rendered["files"] == []
    assert any(item["kind"] == "representation_downgrade" for item in rendered["omissions"])


def test_compact_downgrades_richer_representations_conservatively():
    context_pack = {"task": "Fix auth", "relevant_files": [_file("src/auth.py", tier=REPRESENTATION_TIER_WHOLE_FILE)]}

    rendered = render_context_pack(context_pack, get_capability_profile(CAPABILITY_TIER_WEAK))
    item = rendered["files"][0]

    assert "content" not in item
    assert "excerpt" not in item
    assert item["summary"]
    assert any(omission["kind"] == "representation_downgrade" for omission in rendered["omissions"])


def test_balanced_preserves_bounded_approved_summaries():
    context_pack = {"task": "Fix auth", "relevant_files": [_file("src/auth.py", tier=REPRESENTATION_TIER_FILE_OUTLINE)]}

    rendered = render_context_pack(context_pack, get_capability_profile(CAPABILITY_TIER_MEDIUM))
    item = rendered["files"][0]

    assert item["summary"] == "Summary for src/auth.py"
    assert item["excerpt"] == "excerpt for src/auth.py"
    assert "content" not in item


def test_expanded_preserves_richer_approved_evidence_when_available():
    context_pack = {"task": "Fix auth", "relevant_files": [_file("src/auth.py", tier=REPRESENTATION_TIER_WHOLE_FILE)]}

    rendered = render_context_pack(context_pack, get_capability_profile(CAPABILITY_TIER_STRONG))
    item = rendered["files"][0]

    assert item["content"] == "content for src/auth.py"
    assert item["excerpt"] == "excerpt for src/auth.py"


def test_relationship_ordering_is_deterministic():
    context_pack = {
        "task": "Fix auth",
        "relationships": [
            {"source_path": "src/b.py", "target_path": "src/c.py", "relationship_type": "imports"},
            {"source_path": "src/a.py", "target_path": "src/c.py", "relationship_type": "imports"},
        ],
    }

    rendered = render_context_pack(context_pack, get_capability_profile(CAPABILITY_TIER_STRONG))

    assert [item["source_path"] for item in rendered["relationships"]] == ["src/a.py", "src/b.py"]


def test_relationship_limits_differ_by_variant():
    assert RELATIONSHIP_LIMITS_BY_VARIANT[RENDERING_VARIANT_COMPACT] < RELATIONSHIP_LIMITS_BY_VARIANT[RENDERING_VARIANT_BALANCED]
    assert RELATIONSHIP_LIMITS_BY_VARIANT[RENDERING_VARIANT_BALANCED] < RELATIONSHIP_LIMITS_BY_VARIANT[RENDERING_VARIANT_EXPANDED]


def test_relationship_truncation_metadata_is_correct():
    rendered = render_context_pack(_context_pack(relationship_count=10), get_capability_profile(CAPABILITY_TIER_WEAK))

    assert len(rendered["relationships"]) == 4
    omission = _omission(rendered, "relationship_limit")
    assert omission["count"] == 6


def test_file_truncation_metadata_is_correct():
    rendered = render_context_pack(_context_pack(file_count=20), get_capability_profile(CAPABILITY_TIER_MEDIUM))

    omission = _omission(rendered, "file_limit")
    assert omission["count"] == 4


def test_missing_budget_data_is_handled_safely():
    rendered = render_context_pack({"task": "Fix auth", "relevant_files": []}, get_capability_profile(CAPABILITY_TIER_MEDIUM))

    assert rendered["budget"]["budget_data_present"] is False
    assert rendered["budget"]["canonical_target_tokens"] is None
    assert rendered["budget"]["canonical_estimated_tokens"] is None


def test_canonical_budget_metadata_is_reused_without_becoming_second_authority():
    rendered = render_context_pack(_context_pack(), get_capability_profile(CAPABILITY_TIER_MEDIUM))

    assert rendered["budget"]["canonical_target_tokens"] == 12000
    assert rendered["budget"]["canonical_estimated_tokens"] == 3000
    assert "rendered_token_count" not in rendered["budget"]


def test_malformed_top_level_input_raises_value_error():
    try:
        render_context_pack([], get_capability_profile(CAPABILITY_TIER_MEDIUM))
    except ValueError as error:
        assert "context_pack must be a mapping" in str(error)
    else:
        raise AssertionError("Malformed context_pack was accepted")


def test_malformed_optional_items_are_handled_conservatively():
    context_pack = {
        "task": "Fix auth",
        "relevant_files": ["not a mapping", _file("src/auth.py")],
        "relationships": [object(), {"source_path": "src/auth.py", "target_path": "src/user.py"}],
    }

    rendered = render_context_pack(context_pack, get_capability_profile(CAPABILITY_TIER_MEDIUM))

    assert len(rendered["files"]) == 1
    assert len(rendered["relationships"]) == 1
    assert any(item["kind"] == "unsupported_item_shape" for item in rendered["omissions"])


def test_instructions_are_more_explicit_for_compact_than_expanded():
    compact = render_context_pack(_context_pack(), get_capability_profile(CAPABILITY_TIER_WEAK))
    expanded = render_context_pack(_context_pack(), get_capability_profile(CAPABILITY_TIER_STRONG))

    assert len(compact["instructions"]) > len(expanded["instructions"])
    assert "Do not invent files" in " ".join(item["text"] for item in compact["instructions"])


def test_no_provider_or_model_names_appear():
    rendered = render_context_pack(_context_pack(), get_capability_profile(CAPABILITY_TIER_MEDIUM))
    text = json.dumps(rendered, sort_keys=True).lower()

    for forbidden in ("openai", "anthropic", "google", "gpt", "claude", "gemini", "provider", "model_name"):
        assert forbidden not in text


def test_no_filesystem_access_is_required():
    public_names = {
        name
        for name in vars(context_rendering)
        if not name.startswith("_")
    }

    assert "os" not in public_names
    assert "Path" not in public_names
    assert "open" not in public_names
    assert callable(render_context_pack)


def test_markdown_rendering_is_deterministic():
    rendered = render_context_pack(_context_pack(), get_capability_profile(CAPABILITY_TIER_MEDIUM))

    assert render_context_pack_markdown(rendered) == render_context_pack_markdown(rendered)


def test_markdown_contains_task_instructions_files_relationships_budget_and_omissions():
    rendered = render_context_pack(_context_pack(file_count=20, relationship_count=10), get_capability_profile(CAPABILITY_TIER_WEAK))
    markdown = render_context_pack_markdown(rendered)

    for heading in (
        "## Task",
        "## Instructions",
        "## Approved Files",
        "## Relationships",
        "## Budget",
        "## Omitted Evidence",
    ):
        assert heading in markdown


def test_markdown_contains_no_ansi_escape_sequences():
    rendered = render_context_pack(_context_pack(), get_capability_profile(CAPABILITY_TIER_MEDIUM))

    assert "\x1b[" not in render_context_pack_markdown(rendered)


def test_existing_part_i_part_m_and_o1_contracts_remain_compatible():
    assert CONTEXT_ARTIFACT_PATH == ".aidc/context/strata_context.md"
    assert RUN_STATE_ARTIFACT_PATH == ".aidc/context/run_state.json"
    assert DIAGNOSTIC_SEVERITIES == ("info", "warning", "error")
    assert select_context_variant(get_capability_profile(CAPABILITY_TIER_WEAK)) == RENDERING_VARIANT_COMPACT


def _context_pack(file_count: int = 4, relationship_count: int = 3) -> dict:
    return {
        "task": "Fix authentication header handling",
        "relevant_files": [
            _file(f"src/file_{index:02d}.py", priority=index, score=100 - index)
            for index in range(file_count)
        ],
        "relationships": [
            {
                "source_path": f"src/file_{index:02d}.py",
                "target_path": f"src/dep_{index:02d}.py",
                "relationship_type": "imports",
            }
            for index in range(relationship_count)
        ],
        "budget_summary": {
            "target_context_tokens": 12000,
            "estimated_used_tokens": 3000,
            "reserved_output_tokens": 2000,
            "max_context_pack_tokens": 10000,
        },
    }


def _file(
    path: str,
    *,
    tier: str = REPRESENTATION_TIER_SYMBOL_SLICE,
    priority: int = 1,
    score: int = 50,
) -> dict:
    return build_represented_item(
        path=path,
        tier=tier,
        reason=f"Reason for {path}",
        source_type="candidate",
        priority=priority,
        score=score,
        warnings=[],
        excerpt=f"excerpt for {path}",
        content=f"content for {path}",
    ) | {
        "role": "source",
        "summary": f"Summary for {path}",
        "symbols": ["AuthHeader", "build_headers", "TokenStore", "RequestClient", "HeaderMap", "extra"],
    }


def _omission(rendered: dict, kind: str) -> dict:
    for item in rendered["omissions"]:
        if item["kind"] == kind:
            return item
    raise AssertionError(f"Missing omission kind: {kind}")


def _is_json_ready(value) -> bool:
    if value is None or isinstance(value, (str, int, bool)):
        return True
    if isinstance(value, list):
        return all(_is_json_ready(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _is_json_ready(item) for key, item in value.items())
    return False


TESTS = [
    test_rendering_variants_are_compact_balanced_expanded,
    test_weak_profile_selects_compact,
    test_medium_profile_selects_balanced,
    test_strong_profile_selects_expanded,
    test_unknown_profile_selects_balanced,
    test_unknown_never_silently_selects_expanded,
    test_rendered_output_is_json_ready,
    test_repeated_rendering_is_deterministic,
    test_input_context_pack_is_not_mutated,
    test_input_profile_is_not_mutated,
    test_file_ordering_is_deterministic,
    test_file_limits_are_respected,
    test_compact_includes_fewer_files_than_balanced_when_enough_files_exist,
    test_expanded_remains_bounded,
    test_path_only_items_are_never_upgraded,
    test_skipped_items_do_not_become_rendered_content,
    test_compact_downgrades_richer_representations_conservatively,
    test_balanced_preserves_bounded_approved_summaries,
    test_expanded_preserves_richer_approved_evidence_when_available,
    test_relationship_ordering_is_deterministic,
    test_relationship_limits_differ_by_variant,
    test_relationship_truncation_metadata_is_correct,
    test_file_truncation_metadata_is_correct,
    test_missing_budget_data_is_handled_safely,
    test_canonical_budget_metadata_is_reused_without_becoming_second_authority,
    test_malformed_top_level_input_raises_value_error,
    test_malformed_optional_items_are_handled_conservatively,
    test_instructions_are_more_explicit_for_compact_than_expanded,
    test_no_provider_or_model_names_appear,
    test_no_filesystem_access_is_required,
    test_markdown_rendering_is_deterministic,
    test_markdown_contains_task_instructions_files_relationships_budget_and_omissions,
    test_markdown_contains_no_ansi_escape_sequences,
    test_existing_part_i_part_m_and_o1_contracts_remain_compatible,
]
