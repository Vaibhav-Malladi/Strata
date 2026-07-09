from pathlib import Path

import strata.core.context_artifacts as context_artifacts
from strata.core.context_artifacts import (
    ADAPTER_NEUTRAL_CONTEXT_NOTE,
    CONTEXT_ARTIFACT_PATH,
    SUPPORTED_CONTEXT_SURFACES,
    REPRESENTATION_SOURCE_TYPES,
    REPRESENTATION_TIER_FILE_OUTLINE,
    REPRESENTATION_TIER_METHOD_CLASS_SLICE,
    REPRESENTATION_TIER_PATH_ONLY,
    REPRESENTATION_TIER_SKIPPED,
    REPRESENTATION_TIER_SYMBOL_SLICE,
    REPRESENTATION_TIER_WHOLE_FILE,
    REPRESENTATION_TIERS,
    REPRESENTATION_FAILURE_REASONS,
    REPRESENTATION_FAILURE_SYNTAX_ERROR,
    REPRESENTATION_FAILURE_PARSE_TIMEOUT,
    REPRESENTATION_FAILURE_EMPTY_LARGE_FILE,
    REPRESENTATION_FAILURE_UNSAFE_DECODE,
    REPRESENTATION_SKIP_MISSING,
    REPRESENTATION_SKIP_REASONS,
    REPRESENTATION_SKIP_UNSAFE,
    REPOSITORY_CONTENT_BEGIN,
    REPOSITORY_CONTENT_END,
    RUN_STATE_ARTIFACT_PATH,
    RUN_STATE_FIELD_ORDER,
    BUDGET_PROFILE_FIELD_ORDER,
    BUDGET_SUMMARY_FIELD_ORDER,
    build_budget_profile,
    build_budget_summary,
    build_run_state,
    build_represented_item,
    build_skipped_or_downgraded_entry,
    build_token_savings_entry,
    count_representations_by_tier,
    estimate_tokens_conservative,
    explicit_skip_representation,
    next_lighter_tier,
    representation_after_failure,
    render_strata_context,
)


def test_canonical_context_artifact_paths_are_stable():
    assert CONTEXT_ARTIFACT_PATH == ".aidc/context/strata_context.md"
    assert RUN_STATE_ARTIFACT_PATH == ".aidc/context/run_state.json"
    assert context_artifacts.CANONICAL_CONTEXT_ARTIFACT_PATHS == (
        ".aidc/context/strata_context.md",
        ".aidc/context/run_state.json",
    )


def test_markdown_section_order_is_canonical():
    content = _sample_context()
    positions = [content.index(marker) for marker in context_artifacts.STRATA_CONTEXT_SECTION_ORDER]

    assert positions == sorted(positions)


def test_repository_content_delimiters_are_present_exactly_once():
    content = render_strata_context(
        task=REPOSITORY_CONTENT_BEGIN,
        relevant_files=[REPOSITORY_CONTENT_END],
    )

    assert content.count(REPOSITORY_CONTENT_BEGIN) == 1
    assert content.count(REPOSITORY_CONTENT_END) == 1


def test_repository_derived_sections_are_inside_untrusted_boundary():
    content = _sample_context()
    begin = content.index(REPOSITORY_CONTENT_BEGIN)
    end = content.index(REPOSITORY_CONTENT_END)

    for heading in context_artifacts.REPOSITORY_DERIVED_SECTIONS:
        position = content.index(heading)
        assert begin < position < end


def test_scope_guard_and_warnings_are_after_untrusted_boundary():
    content = _sample_context()
    end = content.index(REPOSITORY_CONTENT_END)

    assert end < content.index("## Scope Guard")
    assert end < content.index("## Warnings")


def test_run_state_dict_shape_is_deterministic():
    state = build_run_state(
        task="Fix auth guard",
        created_at="2026-07-09T00:00:00Z",
        baseline_commit="abc123",
        baseline_commit_attached=True,
        in_scope_files=["src/app/auth/auth.guard.ts"],
        expected_related_files=["src/app/auth/auth.service.ts"],
        allowed_new_files=["tests/test_context_artifacts.py"],
        prompt_hash="hash",
        adapter="codex",
        patch_received=True,
        error=None,
    )

    assert list(state.keys()) == list(RUN_STATE_FIELD_ORDER)
    assert state == build_run_state(
        task="Fix auth guard",
        created_at="2026-07-09T00:00:00Z",
        baseline_commit="abc123",
        baseline_commit_attached=True,
        in_scope_files=["src/app/auth/auth.guard.ts"],
        expected_related_files=["src/app/auth/auth.service.ts"],
        allowed_new_files=["tests/test_context_artifacts.py"],
        prompt_hash="hash",
        adapter="codex",
        patch_received=True,
        error=None,
    )


def test_workspace_placeholders_exist_in_run_state():
    state = build_run_state()

    assert state["workspace_mode"] == "single_repo"
    assert state["workspace"] is None
    assert state["cross_repo_references"] == []


def test_internal_library_placeholders_exist_in_context_and_run_state():
    content = render_strata_context(internal_library_apis=[])
    state = build_run_state()

    assert "## Internal Library APIs" in content
    assert state["internal_libraries"] == []


def test_context_artifact_module_introduces_no_competing_artifact_names():
    forbidden = {
        "browser_prompt.md",
        "session.json",
        "scope_guard.json",
        "terminal_prompt.md",
        "vscode_prompt.md",
    }
    strings = _collect_public_strings(context_artifacts)

    for artifact_name in forbidden:
        assert artifact_name not in strings


def test_supported_context_surface_constants_are_stable():
    assert SUPPORTED_CONTEXT_SURFACES == (
        "browser_ai",
        "cli_ai",
        "vscode_terminal",
        "vscode_side_chat",
        "future_vscode_extension",
    )
    assert "canonical context artifacts" in ADAPTER_NEUTRAL_CONTEXT_NOTE
    assert "independent sources of truth" in ADAPTER_NEUTRAL_CONTEXT_NOTE


def test_context_markdown_remains_plain_deterministic_markdown():
    item = build_represented_item(
        path="src/app.py",
        tier=REPRESENTATION_TIER_FILE_OUTLINE,
        reason="Relevant owner.",
        excerpt="class App",
    )
    summary = build_budget_summary(represented_items=[item])
    first = render_strata_context(
        task="fix app",
        suggested_instructions=["Use canonical context."],
        relevant_files=[item],
        budget_summary=summary,
        scope_guard=["Stay in scope."],
        warnings=["No adapter-specific prompt files."],
    )
    second = render_strata_context(
        task="fix app",
        suggested_instructions=["Use canonical context."],
        relevant_files=[item],
        budget_summary=summary,
        scope_guard=["Stay in scope."],
        warnings=["No adapter-specific prompt files."],
    )

    assert first == second
    assert first.startswith("# Strata Context\n")
    assert "\r" not in first
    assert all(ord(character) < 128 for character in first)
    assert "<script" not in first.lower()


def test_i6_boundaries_budget_and_represented_content_positions_are_stable():
    item = build_represented_item(
        path="src/app.py",
        tier=REPRESENTATION_TIER_FILE_OUTLINE,
        reason="Repository-derived representation.",
        excerpt="class App",
    )
    summary = build_budget_summary(
        represented_items=[item],
        warnings=["Trusted Strata budget metadata."],
    )
    content = render_strata_context(
        task="fix app",
        relevant_files=[item],
        budget_summary=summary,
    )
    begin = content.index(REPOSITORY_CONTENT_BEGIN)
    end = content.index(REPOSITORY_CONTENT_END)
    represented_position = content.index("Repository-derived representation.")
    budget_position = content.index("## Context Budget Summary")

    assert content.count(REPOSITORY_CONTENT_BEGIN) == 1
    assert content.count(REPOSITORY_CONTENT_END) == 1
    assert begin < represented_position < end
    assert end < budget_position


def test_representation_tier_names_and_order_are_stable():
    assert REPRESENTATION_TIERS == (
        REPRESENTATION_TIER_WHOLE_FILE,
        REPRESENTATION_TIER_SYMBOL_SLICE,
        REPRESENTATION_TIER_METHOD_CLASS_SLICE,
        REPRESENTATION_TIER_FILE_OUTLINE,
        REPRESENTATION_TIER_PATH_ONLY,
        REPRESENTATION_TIER_SKIPPED,
    )
    assert context_artifacts.REPRESENTATION_TIER_LABELS == {
        "whole_file": "whole file",
        "symbol_slice": "symbol slice",
        "method_class_slice": "method/class slice",
        "file_outline": "file outline",
        "path_only": "path-only with reason",
        "skipped": "skipped with reason",
    }
    assert context_artifacts.REPRESENTATION_TIER_PLAIN_LANGUAGE == {
        "whole_file": "full content",
        "symbol_slice": "useful symbols",
        "method_class_slice": "relevant method/class only",
        "file_outline": "outline",
        "path_only": "path and reason only",
        "skipped": "skipped",
    }


def test_representation_source_type_names_are_stable():
    assert REPRESENTATION_SOURCE_TYPES == (
        "candidate",
        "trace",
        "internal_library",
        "warning",
        "workspace_placeholder",
    )


def test_represented_item_dict_output_is_deterministic_and_json_ready():
    item = build_represented_item(
        path="src\\app.py",
        tier=REPRESENTATION_TIER_SYMBOL_SLICE,
        reason="Task mentions app startup.",
        source_type="candidate",
        priority=2,
        score=91,
        estimated_tokens=40,
        original_estimated_tokens=200,
        savings_estimated_tokens=160,
        warnings=["Generated estimates are placeholders."],
        excerpt="def main(): pass",
    )

    assert list(item.keys()) == list(context_artifacts.REPRESENTED_ITEM_FIELD_ORDER)
    assert item == build_represented_item(
        path="src/app.py",
        tier=REPRESENTATION_TIER_SYMBOL_SLICE,
        reason="Task mentions app startup.",
        source_type="candidate",
        priority=2,
        score=91,
        estimated_tokens=40,
        original_estimated_tokens=200,
        savings_estimated_tokens=160,
        warnings=["Generated estimates are placeholders."],
        excerpt="def main(): pass",
    )
    assert context_artifacts._stable_json(item)


def test_represented_items_render_inside_untrusted_boundary():
    item = build_represented_item(
        path="src/app.py",
        tier=REPRESENTATION_TIER_FILE_OUTLINE,
        reason="Relevant route owner.",
        source_type="trace",
        excerpt="class App",
    )
    content = render_strata_context(
        task="fix app route",
        relevant_files=[item],
        scope_guard=["Stay within app route."],
    )
    begin = content.index(REPOSITORY_CONTENT_BEGIN)
    end = content.index(REPOSITORY_CONTENT_END)
    rendered_path = content.index("src/app.py")
    rendered_reason = content.index("Relevant route owner.")

    assert begin < rendered_path < end
    assert begin < rendered_reason < end
    assert end < content.index("## Scope Guard")


def test_path_only_and_skipped_representations_require_and_render_reasons():
    path_only = build_represented_item(
        path="src/large.py",
        tier=REPRESENTATION_TIER_PATH_ONLY,
        reason="Too large for I3 contract example.",
        source_type="candidate",
    )
    skipped = build_represented_item(
        path="dist/generated.js",
        tier=REPRESENTATION_TIER_SKIPPED,
        reason="Generated output.",
        source_type="warning",
    )
    content = render_strata_context(relevant_files=[path_only, skipped])

    assert "Too large for I3 contract example." in content
    assert "Generated output." in content

    for tier in (REPRESENTATION_TIER_PATH_ONLY, REPRESENTATION_TIER_SKIPPED):
        try:
            build_represented_item(path="src/app.py", tier=tier)
        except ValueError as error:
            assert "requires a reason" in str(error)
        else:
            raise AssertionError(f"{tier} accepted a missing reason")


def test_representation_contract_introduces_no_budget_allocation_api():
    public_names = {
        name
        for name in vars(context_artifacts)
        if not name.startswith("_")
    }

    assert "allocate_budget" not in public_names
    assert "build_budget_allocation" not in public_names
    assert not any("budget" in name.lower() and "representation" in name.lower() for name in public_names)


def test_budget_profile_default_shape_is_deterministic():
    profile = build_budget_profile()

    assert list(profile.keys()) == list(BUDGET_PROFILE_FIELD_ORDER)
    assert profile == {
        "target_context_tokens": 12000,
        "reserved_output_tokens": 2000,
        "max_context_pack_tokens": 10000,
        "tokenizer_strategy": "conservative_char_estimate",
        "safety_margin": 0.15,
    }
    assert profile == build_budget_profile()


def test_budget_summary_dict_shape_is_deterministic():
    item = build_represented_item(
        path="src/app.py",
        tier=REPRESENTATION_TIER_FILE_OUTLINE,
        reason="Relevant owner.",
        estimated_tokens=30,
    )
    savings = build_token_savings_entry(
        path="src/large.py",
        tier=REPRESENTATION_TIER_PATH_ONLY,
        savings_estimated_tokens=300,
        original_estimated_tokens=330,
        estimated_tokens=30,
        reason="Path-only contract example.",
    )
    skipped = build_skipped_or_downgraded_entry(
        path="dist/bundle.js",
        tier=REPRESENTATION_TIER_SKIPPED,
        source_type="warning",
        reason="Generated output.",
    )
    summary = build_budget_summary(
        represented_items=[item],
        largest_token_savings=[savings],
        skipped_or_downgraded=[skipped],
        warnings=["Conservative estimate only."],
    )

    assert list(summary.keys()) == list(BUDGET_SUMMARY_FIELD_ORDER)
    assert summary == build_budget_summary(
        represented_items=[item],
        largest_token_savings=[savings],
        skipped_or_downgraded=[skipped],
        warnings=["Conservative estimate only."],
    )
    assert summary["estimated_used_tokens"] == 30


def test_conservative_token_estimate_is_stdlib_and_overestimates_simple_text():
    assert estimate_tokens_conservative("") == 0
    assert estimate_tokens_conservative("abc") == 1
    assert estimate_tokens_conservative("abcd") == 2
    assert estimate_tokens_conservative("abcdefghijkl") == 4


def test_representation_counts_by_tier_are_complete_and_stable():
    items = [
        build_represented_item(path="a.py", tier=REPRESENTATION_TIER_WHOLE_FILE),
        build_represented_item(path="b.py", tier=REPRESENTATION_TIER_FILE_OUTLINE),
        build_represented_item(path="c.py", tier=REPRESENTATION_TIER_FILE_OUTLINE),
        build_represented_item(path="d.py", tier=REPRESENTATION_TIER_SKIPPED, reason="Generated."),
    ]

    assert count_representations_by_tier(items) == {
        "whole_file": 1,
        "symbol_slice": 0,
        "method_class_slice": 0,
        "file_outline": 2,
        "path_only": 0,
        "skipped": 1,
    }


def test_budget_summary_renders_savings_and_skipped_entries_outside_untrusted_boundary():
    summary = build_budget_summary(
        largest_token_savings=[
            build_token_savings_entry(
                path="src/large.py",
                tier=REPRESENTATION_TIER_PATH_ONLY,
                savings_estimated_tokens=500,
                reason="Large file represented by path.",
            )
        ],
        skipped_or_downgraded=[
            build_skipped_or_downgraded_entry(
                path="dist/bundle.js",
                tier=REPRESENTATION_TIER_SKIPPED,
                source_type="warning",
                reason="Generated output.",
            )
        ],
    )
    content = render_strata_context(
        task="fit prompt",
        relevant_files=[
            build_represented_item(
                path="src/large.py",
                tier=REPRESENTATION_TIER_PATH_ONLY,
                reason="Large file represented by path.",
            )
        ],
        budget_summary=summary,
    )
    begin = content.index(REPOSITORY_CONTENT_BEGIN)
    end = content.index(REPOSITORY_CONTENT_END)
    budget_heading = content.index("## Context Budget Summary")
    savings_position = content.rindex("src/large.py")
    skipped_position = content.index("dist/bundle.js")

    assert begin < content.index("Large file represented by path.") < end
    assert end < budget_heading
    assert budget_heading < savings_position
    assert budget_heading < skipped_position


def test_invalid_negative_token_values_are_rejected_safely():
    cases = [
        lambda: build_budget_profile(target_context_tokens=-1),
        lambda: build_budget_profile(reserved_output_tokens=-1),
        lambda: build_budget_profile(max_context_pack_tokens=-1),
        lambda: build_budget_profile(safety_margin=-0.1),
        lambda: build_budget_summary(estimated_used_tokens=-1),
        lambda: build_token_savings_entry(path="a.py", tier=REPRESENTATION_TIER_FILE_OUTLINE, savings_estimated_tokens=-1),
    ]

    for call in cases:
        try:
            call()
        except ValueError as error:
            assert "non-negative" in str(error)
        else:
            raise AssertionError("Negative token value was accepted")


def test_budget_contract_introduces_no_allocator_api():
    public_names = {
        name
        for name in vars(context_artifacts)
        if not name.startswith("_")
    }

    assert "allocate_budget" not in public_names
    assert "allocate_context_budget" not in public_names
    assert "apply_budget_policy" not in public_names
    assert "downgrade_representations_for_budget" not in public_names


def test_lazy_outline_downgrade_order_is_stable():
    assert next_lighter_tier(REPRESENTATION_TIER_WHOLE_FILE) == REPRESENTATION_TIER_SYMBOL_SLICE
    assert next_lighter_tier(REPRESENTATION_TIER_SYMBOL_SLICE) == REPRESENTATION_TIER_METHOD_CLASS_SLICE
    assert next_lighter_tier(REPRESENTATION_TIER_METHOD_CLASS_SLICE) == REPRESENTATION_TIER_FILE_OUTLINE
    assert next_lighter_tier(REPRESENTATION_TIER_FILE_OUTLINE) == REPRESENTATION_TIER_PATH_ONLY


def test_path_only_and_skipped_terminal_behavior_is_safe():
    assert next_lighter_tier(REPRESENTATION_TIER_PATH_ONLY) == REPRESENTATION_TIER_PATH_ONLY
    assert next_lighter_tier(REPRESENTATION_TIER_SKIPPED) == REPRESENTATION_TIER_SKIPPED
    assert next_lighter_tier(REPRESENTATION_TIER_PATH_ONLY, skip_reason=REPRESENTATION_SKIP_MISSING) == REPRESENTATION_TIER_SKIPPED


def test_skipped_is_allowed_only_for_explicit_skip_reasons():
    assert REPRESENTATION_SKIP_REASONS == (
        "irrelevant",
        "unsafe",
        "missing",
        "unavailable",
    )
    skipped = explicit_skip_representation(
        path="secret.env",
        skip_reason=REPRESENTATION_SKIP_UNSAFE,
        reason="Secret-like file.",
    )

    assert skipped["tier"] == REPRESENTATION_TIER_SKIPPED
    assert skipped["reason"] == "Secret-like file."
    assert skipped["warnings"] == ["Skipped because unsafe: Secret-like file."]

    for call in (
        lambda: next_lighter_tier(REPRESENTATION_TIER_PATH_ONLY, skip_reason="large"),
        lambda: explicit_skip_representation(path="x.py", skip_reason="large", reason="Large file."),
    ):
        try:
            call()
        except ValueError as error:
            assert "skip reason" in str(error)
        else:
            raise AssertionError("Skipped representation accepted a non-explicit skip reason")


def test_failure_reason_constants_are_stable():
    assert REPRESENTATION_FAILURE_REASONS == (
        "syntax_error",
        "parse_timeout",
        "empty_large_file",
        "exception",
        "unsafe_decode",
    )


def test_syntax_error_failure_downgrades_safely_with_warning():
    result = representation_after_failure(
        REPRESENTATION_TIER_WHOLE_FILE,
        REPRESENTATION_FAILURE_SYNTAX_ERROR,
        path="src/app.py",
    )

    assert result["tier"] == REPRESENTATION_TIER_SYMBOL_SLICE
    assert result["failure_reason"] == "syntax_error"
    assert "syntax error" in result["reason"]
    assert "downgraded from whole file to symbol slice" in result["warning"]


def test_timeout_empty_large_and_unsafe_decode_failures_downgrade_safely():
    cases = [
        (REPRESENTATION_FAILURE_PARSE_TIMEOUT, "parse timeout over 5 seconds"),
        (REPRESENTATION_FAILURE_EMPTY_LARGE_FILE, "empty extraction result for a file over 100 lines"),
        (REPRESENTATION_FAILURE_UNSAFE_DECODE, "unsafe decode"),
    ]

    for reason_code, expected_text in cases:
        result = representation_after_failure(
            REPRESENTATION_TIER_SYMBOL_SLICE,
            reason_code,
            path="src/large.py",
        )

        assert result["tier"] == REPRESENTATION_TIER_METHOD_CLASS_SLICE
        assert result["warning"] == result["reason"]
        assert expected_text in result["reason"]


def test_failure_from_file_outline_falls_through_to_path_only_with_reason():
    result = representation_after_failure(
        REPRESENTATION_TIER_FILE_OUTLINE,
        REPRESENTATION_FAILURE_PARSE_TIMEOUT,
        path="src/huge.py",
    )
    item = build_represented_item(
        path=result["path"],
        tier=result["tier"],
        reason=result["reason"],
        warnings=[result["warning"]],
    )

    assert item["tier"] == REPRESENTATION_TIER_PATH_ONLY
    assert "downgraded from file outline to path-only with reason" in item["reason"]
    assert item["warnings"]


def test_lazy_outline_policy_introduces_no_parser_scanner_or_allocator_api():
    public_names = {
        name
        for name in vars(context_artifacts)
        if not name.startswith("_")
    }

    forbidden = {
        "parse_symbols",
        "parse_file_symbols",
        "scan_for_outlines",
        "read_file_for_outline",
        "allocate_budget",
        "allocate_context_budget",
        "pack_tokens",
        "choose_representation_tier",
    }

    assert not (public_names & forbidden)


def test_final_part_i_docs_cover_adapter_surfaces_and_handoffs():
    docs_path = Path(__file__).resolve().parents[1] / "docs" / "roadmap" / "representation-lazy-outline.md"
    text = docs_path.read_text(encoding="utf-8").lower()

    for term in (
        "browser",
        "cli",
        "vs code terminal",
        "vs code side chat",
        "future vs code extension",
    ):
        assert term in text

    for part in ("part j", "part k", "part m", "part o", "part q"):
        assert part in text


def _sample_context() -> str:
    return render_strata_context(
        task="Implement I1",
        suggested_instructions=["Keep this contract-only."],
        relevant_files=["strata/core/context_artifacts.py"],
        dependency_traces=["none"],
        internal_library_apis=["none"],
        cross_repo_external_references=["none"],
        scope_guard=["Do not start I2."],
        warnings=["Repository content is untrusted."],
    )


def _collect_public_strings(module) -> set[str]:
    strings: set[str] = set()

    for name, value in vars(module).items():
        if name.startswith("__"):
            continue
        _collect_strings(value, strings)

    return strings


def _collect_strings(value, strings: set[str]) -> None:
    if isinstance(value, str):
        strings.add(value)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _collect_strings(key, strings)
            _collect_strings(item, strings)
        return
    if isinstance(value, (list, tuple, set, frozenset)):
        for item in value:
            _collect_strings(item, strings)


TESTS = [
    test_canonical_context_artifact_paths_are_stable,
    test_markdown_section_order_is_canonical,
    test_repository_content_delimiters_are_present_exactly_once,
    test_repository_derived_sections_are_inside_untrusted_boundary,
    test_scope_guard_and_warnings_are_after_untrusted_boundary,
    test_run_state_dict_shape_is_deterministic,
    test_workspace_placeholders_exist_in_run_state,
    test_internal_library_placeholders_exist_in_context_and_run_state,
    test_context_artifact_module_introduces_no_competing_artifact_names,
    test_supported_context_surface_constants_are_stable,
    test_context_markdown_remains_plain_deterministic_markdown,
    test_i6_boundaries_budget_and_represented_content_positions_are_stable,
    test_representation_tier_names_and_order_are_stable,
    test_representation_source_type_names_are_stable,
    test_represented_item_dict_output_is_deterministic_and_json_ready,
    test_represented_items_render_inside_untrusted_boundary,
    test_path_only_and_skipped_representations_require_and_render_reasons,
    test_representation_contract_introduces_no_budget_allocation_api,
    test_budget_profile_default_shape_is_deterministic,
    test_budget_summary_dict_shape_is_deterministic,
    test_conservative_token_estimate_is_stdlib_and_overestimates_simple_text,
    test_representation_counts_by_tier_are_complete_and_stable,
    test_budget_summary_renders_savings_and_skipped_entries_outside_untrusted_boundary,
    test_invalid_negative_token_values_are_rejected_safely,
    test_budget_contract_introduces_no_allocator_api,
    test_lazy_outline_downgrade_order_is_stable,
    test_path_only_and_skipped_terminal_behavior_is_safe,
    test_skipped_is_allowed_only_for_explicit_skip_reasons,
    test_failure_reason_constants_are_stable,
    test_syntax_error_failure_downgrades_safely_with_warning,
    test_timeout_empty_large_and_unsafe_decode_failures_downgrade_safely,
    test_failure_from_file_outline_falls_through_to_path_only_with_reason,
    test_lazy_outline_policy_introduces_no_parser_scanner_or_allocator_api,
    test_final_part_i_docs_cover_adapter_surfaces_and_handoffs,
]
