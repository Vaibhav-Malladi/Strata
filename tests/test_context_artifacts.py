import strata.core.context_artifacts as context_artifacts
from strata.core.context_artifacts import (
    CONTEXT_ARTIFACT_PATH,
    REPRESENTATION_SOURCE_TYPES,
    REPRESENTATION_TIER_FILE_OUTLINE,
    REPRESENTATION_TIER_METHOD_CLASS_SLICE,
    REPRESENTATION_TIER_PATH_ONLY,
    REPRESENTATION_TIER_SKIPPED,
    REPRESENTATION_TIER_SYMBOL_SLICE,
    REPRESENTATION_TIER_WHOLE_FILE,
    REPRESENTATION_TIERS,
    REPOSITORY_CONTENT_BEGIN,
    REPOSITORY_CONTENT_END,
    RUN_STATE_ARTIFACT_PATH,
    RUN_STATE_FIELD_ORDER,
    build_run_state,
    build_represented_item,
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
        "session.json",
        "scope_guard.json",
        "vscode_prompt.md",
    }
    strings = _collect_public_strings(context_artifacts)

    for artifact_name in forbidden:
        assert artifact_name not in strings


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
    test_representation_tier_names_and_order_are_stable,
    test_representation_source_type_names_are_stable,
    test_represented_item_dict_output_is_deterministic_and_json_ready,
    test_represented_items_render_inside_untrusted_boundary,
    test_path_only_and_skipped_representations_require_and_render_reasons,
    test_representation_contract_introduces_no_budget_allocation_api,
]
