import json
import os
import tempfile
from pathlib import Path

from strata.core.context_artifacts import build_run_state
from strata.core.diagnostic_explanations import explain_diagnostic_events
from strata.core.diagnostics import (
    DIAGNOSTIC_SOURCE_GATE,
    DIAGNOSTIC_SEVERITY_ERROR,
    DIAGNOSTIC_SEVERITY_INFO,
    DIAGNOSTIC_SEVERITY_WARNING,
    build_diagnostic_event,
)
from strata.core.error_artifacts import (
    DEFAULT_RUN_ERROR_JSON_PATH,
    DEFAULT_RUN_ERROR_MARKDOWN_PATH,
    MAX_RECOVERY_GUIDANCE,
    MAX_RUN_ERROR_DIAGNOSTICS,
    MAX_RUN_ERROR_EXPLANATIONS,
    RUN_ERROR_ARTIFACT_TYPE,
    RUN_ERROR_SCHEMA_VERSION,
    build_run_error_artifact,
    build_recovery_guidance,
    render_run_error_json,
    render_run_error_markdown,
    validate_run_error_artifact,
    write_run_error_json,
    write_run_error_markdown,
)
from tests.helpers import try_symlink_or_skip


def _state(**overrides) -> dict:
    state = build_run_state(
        task="Fix auth guard",
        created_at="2026-07-15T00:00:00Z",
        baseline_commit="abc123",
        baseline_commit_attached=True,
        baseline_status="attached",
        in_scope_files=["src/auth.py"],
        expected_related_files=[],
        allowed_new_files=[],
        prompt_hash="hash",
        adapter="codex",
        patch_received=True,
    )
    state.update(overrides)
    return state


def _diagnostic(code: str, severity: str = DIAGNOSTIC_SEVERITY_ERROR, *, next_action: str | None = None) -> dict:
    return build_diagnostic_event(
        code,
        severity,
        f"{code} message.",
        source=DIAGNOSTIC_SOURCE_GATE,
        next_action=next_action,
        details={"imports": [code]},
    )


def test_valid_run_error_artifact_is_json_ready():
    artifact = build_run_error_artifact(
        _state(),
        stage="review",
        diagnostics=[_diagnostic("gate_unresolved_imports")],
    )

    assert artifact["schema_version"] == RUN_ERROR_SCHEMA_VERSION
    assert artifact["artifact_type"] == RUN_ERROR_ARTIFACT_TYPE
    assert json.loads(json.dumps(artifact, allow_nan=False)) == artifact


def test_repeated_builds_with_identical_input_are_identical():
    diagnostics = [_diagnostic("gate_unresolved_imports")]

    assert build_run_error_artifact(_state(), stage="gate", diagnostics=diagnostics) == build_run_error_artifact(_state(), stage="gate", diagnostics=diagnostics)


def test_input_mappings_and_lists_are_not_mutated():
    state = _state()
    diagnostics = [_diagnostic("gate_unresolved_imports")]
    metadata = {"items": ["a"]}
    before = (json.loads(json.dumps(state)), json.loads(json.dumps(diagnostics)), json.loads(json.dumps(metadata)))

    build_run_error_artifact(state, stage="gate", diagnostics=diagnostics, metadata=metadata)

    assert (state, diagnostics, metadata) == before


def test_invalid_stage_values_are_rejected():
    try:
        build_run_error_artifact(_state(), stage="adapter")
    except ValueError as error:
        assert "stage must be one of" in str(error)
    else:
        raise AssertionError("invalid stage was accepted")


def test_m1_run_state_diagnostics_are_included_when_appropriate():
    artifact = build_run_error_artifact({}, stage="workflow")

    assert artifact["primary_code"] == "invalid_run_state"
    assert artifact["diagnostic_summary"]["errors"] > 0


def test_m2_diagnostics_are_normalized_and_summarized():
    artifact = build_run_error_artifact(
        _state(),
        stage="gate",
        diagnostics=[
            {
                "code": "gate_unresolved_imports",
                "severity": "error",
                "message": "missing",
                "source": "gate",
            }
        ],
    )

    assert artifact["diagnostic_summary"]["total"] == 1
    assert artifact["diagnostics"][0]["details"] == {}


def test_m3_explanations_are_bounded_and_deterministic():
    diagnostics = [_diagnostic(f"unknown_{index}") for index in range(MAX_RUN_ERROR_EXPLANATIONS + 3)]

    artifact = build_run_error_artifact(_state(), stage="gate", diagnostics=diagnostics)

    assert len(artifact["explanations"]) == MAX_RUN_ERROR_EXPLANATIONS
    assert artifact == build_run_error_artifact(_state(), stage="gate", diagnostics=diagnostics)


def test_m4_status_data_is_reused():
    artifact = build_run_error_artifact(_state(error="failed"), stage="workflow")

    assert artifact["workflow_status"] == "blocked"
    assert artifact["health"] == "blocked"


def test_primary_failure_selection_is_deterministic():
    diagnostics = [
        _diagnostic("z_warning", DIAGNOSTIC_SEVERITY_WARNING),
        _diagnostic("b_error"),
        _diagnostic("a_error"),
    ]

    artifact = build_run_error_artifact(_state(), stage="gate", diagnostics=diagnostics)

    assert artifact["primary_code"] == "a_error"


def test_invalid_run_state_selects_repair_guidance():
    artifact = build_run_error_artifact({}, stage="workflow")

    assert artifact["next_action"] == "repair_or_regenerate_run_state"
    assert artifact["recovery_guidance"][0]["action"] == "repair_or_regenerate_run_state"


def test_unknown_diagnostic_actions_degrade_safely():
    artifact = build_run_error_artifact(
        _state(),
        stage="gate",
        diagnostics=[_diagnostic("unknown", next_action="launch_rocket")],
    )

    assert artifact["next_action"] == "inspect_details"


def test_unsafe_actions_are_never_emitted_in_recovery_guidance():
    guidance = build_recovery_guidance("apply_patch", [{"next_action": "force_apply"}])

    assert {item["action"] for item in guidance} == {"inspect_details"}


def test_duplicate_recovery_actions_are_removed():
    guidance = build_recovery_guidance("inspect_details", [{"next_action": "inspect_details"}])

    assert len(guidance) == 1


def test_recovery_guidance_ordering_is_deterministic():
    first = build_recovery_guidance("run_tests", [{"next_action": "fix_imports"}])
    second = build_recovery_guidance("run_tests", [{"next_action": "fix_imports"}])

    assert first == second
    assert [item["priority"] for item in first] == sorted(item["priority"] for item in first)


def test_diagnostic_list_is_capped():
    artifact = build_run_error_artifact(
        _state(),
        stage="gate",
        diagnostics=[_diagnostic(f"code_{index}") for index in range(MAX_RUN_ERROR_DIAGNOSTICS + 5)],
    )

    assert len(artifact["diagnostics"]) == MAX_RUN_ERROR_DIAGNOSTICS


def test_explanation_list_is_capped():
    artifact = build_run_error_artifact(
        _state(),
        stage="gate",
        diagnostics=[_diagnostic(f"code_{index}") for index in range(MAX_RUN_ERROR_EXPLANATIONS + 5)],
    )

    assert len(artifact["explanations"]) == MAX_RUN_ERROR_EXPLANATIONS


def test_recovery_guidance_list_is_capped():
    explanations = [
        {
            "code": f"code_{index}",
            "severity": "error",
            "source": "gate",
            "title": "Title",
            "explanation": "Explanation",
            "why_it_matters": "Why",
            "affected_items": [],
            "next_action": action,
            "technical_details": {},
        }
        for index, action in enumerate(
            [
                "inspect_details",
                "revise_patch",
                "remove_out_of_scope_changes",
                "approve_expected_file",
                "fix_imports",
                "run_tests",
                "run_verification",
                "regenerate_context",
                "repair_or_regenerate_run_state",
                "prepare_context",
                "request_ai_response",
                "review_response",
            ]
        )
    ]
    artifact = build_run_error_artifact(_state(), stage="gate", diagnostics=[], explanations=explanations)

    assert len(artifact["recovery_guidance"]) == MAX_RECOVERY_GUIDANCE


def test_truncation_metadata_is_correct():
    artifact = build_run_error_artifact(
        _state(),
        stage="gate",
        diagnostics=[_diagnostic(f"code_{index}") for index in range(MAX_RUN_ERROR_DIAGNOSTICS + 1)],
    )

    assert artifact["metadata"]["diagnostics_truncated"] is True
    assert artifact["metadata"]["diagnostic_count_total"] == MAX_RUN_ERROR_DIAGNOSTICS + 1


def test_empty_diagnostics_are_handled_safely():
    artifact = build_run_error_artifact(_state(), stage="context", diagnostics=[])

    assert artifact["primary_code"] is None
    assert artifact["diagnostic_summary"]["total"] == 0


def test_healthy_incomplete_state_is_not_falsely_labeled_failed():
    artifact = build_run_error_artifact(_state(patch_received=False), stage="context", diagnostics=[])

    assert artifact["workflow_status"] == "context_ready"
    assert artifact["health"] == "healthy"
    assert artifact["primary_code"] is None


def test_json_rendering_is_deterministic():
    artifact = build_run_error_artifact(_state(), stage="gate", diagnostics=[_diagnostic("gate_unresolved_imports")])

    assert render_run_error_json(artifact) == render_run_error_json(artifact)


def test_json_output_ends_with_newline():
    artifact = build_run_error_artifact(_state(), stage="gate", diagnostics=[])

    assert render_run_error_json(artifact).endswith("\n")


def test_markdown_rendering_is_deterministic():
    artifact = build_run_error_artifact(_state(), stage="gate", diagnostics=[_diagnostic("gate_unresolved_imports")])

    assert render_run_error_markdown(artifact) == render_run_error_markdown(artifact)


def test_markdown_contains_summary_status_next_action_and_recovery_guidance():
    markdown = render_run_error_markdown(build_run_error_artifact(_state(), stage="gate", diagnostics=[_diagnostic("gate_unresolved_imports")]))

    assert "## Summary" in markdown
    assert "## Current Status" in markdown
    assert "Next action" in markdown
    assert "## Recovery Guidance" in markdown


def test_markdown_contains_no_ansi_escape_codes():
    markdown = render_run_error_markdown(build_run_error_artifact(_state(), stage="gate", diagnostics=[]))

    assert "\x1b[" not in markdown


def test_markdown_remains_bounded():
    artifact = build_run_error_artifact(
        _state(),
        stage="gate",
        diagnostics=[_diagnostic(f"code_{index}") for index in range(100)],
    )

    assert len(render_run_error_markdown(artifact).splitlines()) < 120


def test_writers_create_only_expected_repository_local_paths():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        artifact = build_run_error_artifact(_state(), stage="gate", diagnostics=[])

        json_path = write_run_error_json(root, artifact)
        markdown_path = write_run_error_markdown(root, artifact)

        assert json_path == root / ".aidc" / DEFAULT_RUN_ERROR_JSON_PATH
        assert markdown_path == root / ".aidc" / DEFAULT_RUN_ERROR_MARKDOWN_PATH


def test_absolute_output_paths_are_rejected():
    with tempfile.TemporaryDirectory() as temp_dir:
        artifact = build_run_error_artifact(_state(), stage="gate", diagnostics=[])
        try:
            write_run_error_json(temp_dir, artifact, relative_path=Path(temp_dir) / "outside.json")
        except ValueError as error:
            assert "relative to .aidc" in str(error)
        else:
            raise AssertionError("absolute output path was accepted")


def test_parent_traversal_is_rejected():
    with tempfile.TemporaryDirectory() as temp_dir:
        artifact = build_run_error_artifact(_state(), stage="gate", diagnostics=[])
        try:
            write_run_error_json(temp_dir, artifact, relative_path="../outside.json")
        except ValueError as error:
            assert "parent traversal" in str(error)
        else:
            raise AssertionError("parent traversal was accepted")


def test_symlink_escape_is_rejected_where_supported():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "repo"
        outside = Path(temp_dir) / "outside"
        root.mkdir()
        outside.mkdir()
        if not try_symlink_or_skip(root / ".aidc", outside, target_is_directory=True):
            return
        artifact = build_run_error_artifact(_state(), stage="gate", diagnostics=[])
        try:
            write_run_error_json(root, artifact)
        except ValueError as error:
            assert "symbolic link" in str(error)
        else:
            raise AssertionError("symlink escape was accepted")


def test_writers_do_not_alter_part_i_context_artifacts():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        artifact = build_run_error_artifact(_state(), stage="gate", diagnostics=[])

        write_run_error_json(root, artifact)
        write_run_error_markdown(root, artifact)

        assert not (root / ".aidc" / "context").exists()


def test_no_secrets_prompts_source_files_or_stack_traces_are_added_automatically():
    artifact = build_run_error_artifact(
        _state(),
        stage="gate",
        diagnostics=[_diagnostic("gate_unresolved_imports")],
        metadata={"safe": True},
    )
    rendered = json.dumps(artifact)

    for forbidden in ("API_KEY", "BEGIN REPOSITORY CONTENT", "Traceback", "def secret"):
        assert forbidden not in rendered


def test_existing_m1_to_m4_behavior_remains_compatible():
    diagnostics = [_diagnostic("gate_unresolved_imports")]
    explanations = explain_diagnostic_events(diagnostics)
    artifact = build_run_error_artifact(_state(), stage="gate", diagnostics=diagnostics, explanations=explanations)

    assert validate_run_error_artifact(artifact) == artifact


TESTS = [
    test_valid_run_error_artifact_is_json_ready,
    test_repeated_builds_with_identical_input_are_identical,
    test_input_mappings_and_lists_are_not_mutated,
    test_invalid_stage_values_are_rejected,
    test_m1_run_state_diagnostics_are_included_when_appropriate,
    test_m2_diagnostics_are_normalized_and_summarized,
    test_m3_explanations_are_bounded_and_deterministic,
    test_m4_status_data_is_reused,
    test_primary_failure_selection_is_deterministic,
    test_invalid_run_state_selects_repair_guidance,
    test_unknown_diagnostic_actions_degrade_safely,
    test_unsafe_actions_are_never_emitted_in_recovery_guidance,
    test_duplicate_recovery_actions_are_removed,
    test_recovery_guidance_ordering_is_deterministic,
    test_diagnostic_list_is_capped,
    test_explanation_list_is_capped,
    test_recovery_guidance_list_is_capped,
    test_truncation_metadata_is_correct,
    test_empty_diagnostics_are_handled_safely,
    test_healthy_incomplete_state_is_not_falsely_labeled_failed,
    test_json_rendering_is_deterministic,
    test_json_output_ends_with_newline,
    test_markdown_rendering_is_deterministic,
    test_markdown_contains_summary_status_next_action_and_recovery_guidance,
    test_markdown_contains_no_ansi_escape_codes,
    test_markdown_remains_bounded,
    test_writers_create_only_expected_repository_local_paths,
    test_absolute_output_paths_are_rejected,
    test_parent_traversal_is_rejected,
    test_symlink_escape_is_rejected_where_supported,
    test_writers_do_not_alter_part_i_context_artifacts,
    test_no_secrets_prompts_source_files_or_stack_traces_are_added_automatically,
    test_existing_m1_to_m4_behavior_remains_compatible,
]
