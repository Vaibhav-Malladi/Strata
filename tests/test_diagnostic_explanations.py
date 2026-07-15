import copy
import json

from strata.core.diagnostic_explanations import (
    AFFECTED_ITEM_LIMIT,
    CODE_GATE_UNRESOLVED_IMPORTS,
    CODE_REVIEW_PATCH_UNSAFE_PATH,
    NEXT_ACTION_INSPECT_DETAILS,
    explain_diagnostic_event,
    explain_diagnostic_events,
    extract_affected_items,
    gate_result_to_diagnostic_events,
    review_result_to_diagnostic_events,
    summarize_diagnostic_explanations,
)
from strata.core.diagnostics import (
    DIAGNOSTIC_SOURCE_GATE,
    DIAGNOSTIC_SOURCE_REVIEW,
    DIAGNOSTIC_SOURCE_WORKFLOW_STATE,
    DIAGNOSTIC_SEVERITY_ERROR,
    DIAGNOSTIC_SEVERITY_INFO,
    DIAGNOSTIC_SEVERITY_WARNING,
    build_diagnostic_event,
)


def test_recognized_gate_error_produces_specific_explanation():
    event = build_diagnostic_event(
        CODE_GATE_UNRESOLVED_IMPORTS,
        DIAGNOSTIC_SEVERITY_ERROR,
        "graph has 1 unresolved imports",
        source=DIAGNOSTIC_SOURCE_GATE,
        details={"imports": ["missing_module"]},
    )

    explanation = explain_diagnostic_event(event)

    assert explanation["title"] == "The project has imports Strata cannot resolve."
    assert explanation["next_action"] == "fix_imports"
    assert explanation["affected_items"] == ["missing_module"]


def test_recognized_review_error_produces_specific_explanation():
    event = build_diagnostic_event(
        CODE_REVIEW_PATCH_UNSAFE_PATH,
        DIAGNOSTIC_SEVERITY_ERROR,
        "Unsafe patch path '../../outside.txt': patch paths must stay inside the repository.",
        source=DIAGNOSTIC_SOURCE_REVIEW,
        details={"targets": ["../../outside.txt"]},
    )

    explanation = explain_diagnostic_event(event)

    assert explanation["title"] == "The patch targets an unsafe path."
    assert explanation["next_action"] == "remove_out_of_scope_changes"
    assert explanation["affected_items"] == ["../../outside.txt"]


def test_unknown_codes_produce_conservative_generic_explanation():
    explanation = explain_diagnostic_event(
        build_diagnostic_event(
            "unknown_gate_code",
            DIAGNOSTIC_SEVERITY_ERROR,
            "Something happened.",
            source=DIAGNOSTIC_SOURCE_GATE,
        )
    )

    assert explanation["next_action"] == NEXT_ACTION_INSPECT_DETAILS
    assert "does not have a specific explanation" in explanation["explanation"]


def test_original_code_severity_and_source_are_preserved():
    explanation = explain_diagnostic_event(
        build_diagnostic_event(
            "unknown_gate_code",
            DIAGNOSTIC_SEVERITY_WARNING,
            "Something happened.",
            source=DIAGNOSTIC_SOURCE_GATE,
        )
    )

    assert explanation["code"] == "unknown_gate_code"
    assert explanation["severity"] == "warning"
    assert explanation["source"] == "gate"


def test_inputs_normalize_through_m2_contract():
    explanation = explain_diagnostic_event(
        {
            "code": CODE_GATE_UNRESOLVED_IMPORTS,
            "severity": "error",
            "message": "graph has 1 unresolved imports",
            "source": "gate",
            "details": {"imports": ["missing_module"]},
        }
    )

    assert explanation["next_action"] == "fix_imports"


def test_affected_paths_are_extracted_deterministically():
    items, _ = extract_affected_items(
        build_diagnostic_event(
            "code",
            DIAGNOSTIC_SEVERITY_ERROR,
            "message",
            source=DIAGNOSTIC_SOURCE_GATE,
            path="src\\b.py",
            field="task",
            details={"paths": ["src/a.py"]},
        )
    )

    assert items == ["src/a.py", "src/b.py", "task"]


def test_exact_duplicate_affected_items_are_removed():
    items, _ = extract_affected_items(
        build_diagnostic_event(
            "code",
            DIAGNOSTIC_SEVERITY_ERROR,
            "message",
            source=DIAGNOSTIC_SOURCE_GATE,
            details={"paths": ["src/a.py", "src/a.py"]},
        )
    )

    assert items == ["src/a.py"]


def test_affected_items_are_sorted():
    items, _ = extract_affected_items(
        build_diagnostic_event(
            "code",
            DIAGNOSTIC_SEVERITY_ERROR,
            "message",
            source=DIAGNOSTIC_SOURCE_GATE,
            details={"paths": ["src/z.py", "src/a.py"]},
        )
    )

    assert items == ["src/a.py", "src/z.py"]


def test_affected_items_are_capped():
    items, metadata = extract_affected_items(
        build_diagnostic_event(
            "code",
            DIAGNOSTIC_SEVERITY_ERROR,
            "message",
            source=DIAGNOSTIC_SOURCE_GATE,
            details={"paths": [f"src/{index:02d}.py" for index in range(AFFECTED_ITEM_LIMIT + 5)]},
        )
    )

    assert len(items) == AFFECTED_ITEM_LIMIT
    assert metadata["affected_item_count"] == AFFECTED_ITEM_LIMIT + 5


def test_truncation_metadata_is_correct():
    _, metadata = extract_affected_items(
        build_diagnostic_event(
            "code",
            DIAGNOSTIC_SEVERITY_ERROR,
            "message",
            source=DIAGNOSTIC_SOURCE_GATE,
            details={"paths": [f"src/{index:02d}.py" for index in range(AFFECTED_ITEM_LIMIT + 1)]},
        )
    )

    assert metadata == {
        "affected_item_count": AFFECTED_ITEM_LIMIT + 1,
        "affected_items_shown": AFFECTED_ITEM_LIMIT,
        "affected_items_truncated": True,
    }


def test_missing_affected_item_data_is_safe():
    explanation = explain_diagnostic_event(
        build_diagnostic_event(
            "unknown",
            DIAGNOSTIC_SEVERITY_ERROR,
            "message",
            source=DIAGNOSTIC_SOURCE_GATE,
        )
    )

    assert explanation["affected_items"] == []
    assert explanation["technical_details"]["affected_item_count"] == 0


def test_explanation_output_is_json_ready():
    explanation = explain_diagnostic_event(
        build_diagnostic_event(
            CODE_GATE_UNRESOLVED_IMPORTS,
            DIAGNOSTIC_SEVERITY_ERROR,
            "graph has 1 unresolved imports",
            source=DIAGNOSTIC_SOURCE_GATE,
            details={"imports": ["missing_module"]},
        )
    )

    assert json.loads(json.dumps(explanation, allow_nan=False)) == explanation


def test_input_mappings_are_not_mutated():
    event = build_diagnostic_event(
        CODE_GATE_UNRESOLVED_IMPORTS,
        DIAGNOSTIC_SEVERITY_ERROR,
        "graph has 1 unresolved imports",
        source=DIAGNOSTIC_SOURCE_GATE,
        details={"imports": ["missing_module"]},
    )
    original = copy.deepcopy(event)

    explain_diagnostic_event(event)

    assert event == original


def test_exact_duplicate_events_are_removed_before_explanation():
    event = build_diagnostic_event(
        CODE_GATE_UNRESOLVED_IMPORTS,
        DIAGNOSTIC_SEVERITY_ERROR,
        "graph has 1 unresolved imports",
        source=DIAGNOSTIC_SOURCE_GATE,
    )

    assert len(explain_diagnostic_events([event, dict(event)])) == 1


def test_event_severity_ordering_is_preserved():
    explanations = explain_diagnostic_events(
        [
            build_diagnostic_event("info_code", DIAGNOSTIC_SEVERITY_INFO, "info", source=DIAGNOSTIC_SOURCE_GATE),
            build_diagnostic_event(CODE_GATE_UNRESOLVED_IMPORTS, DIAGNOSTIC_SEVERITY_ERROR, "error", source=DIAGNOSTIC_SOURCE_GATE),
            build_diagnostic_event("warn_code", DIAGNOSTIC_SEVERITY_WARNING, "warning", source=DIAGNOSTIC_SOURCE_GATE),
        ]
    )

    assert [item["severity"] for item in explanations] == ["error", "warning", "info"]


def test_batch_output_is_deterministic():
    events = [
        build_diagnostic_event("z", DIAGNOSTIC_SEVERITY_WARNING, "z", source=DIAGNOSTIC_SOURCE_GATE),
        build_diagnostic_event("a", DIAGNOSTIC_SEVERITY_ERROR, "a", source=DIAGNOSTIC_SOURCE_GATE),
    ]

    assert explain_diagnostic_events(events) == explain_diagnostic_events(list(reversed(events)))


def test_summary_counts_are_correct():
    explanations = explain_diagnostic_events(
        [
            build_diagnostic_event("a", DIAGNOSTIC_SEVERITY_ERROR, "a", source=DIAGNOSTIC_SOURCE_GATE),
            build_diagnostic_event("b", DIAGNOSTIC_SEVERITY_ERROR, "b", source=DIAGNOSTIC_SOURCE_REVIEW),
            build_diagnostic_event("c", DIAGNOSTIC_SEVERITY_WARNING, "c", source=DIAGNOSTIC_SOURCE_GATE),
        ]
    )

    assert summarize_diagnostic_explanations(explanations) == {
        "total": 3,
        "errors": 2,
        "warnings": 1,
        "has_blocking_issues": True,
        "primary_next_action": "inspect_details",
    }


def test_primary_next_action_is_deterministic():
    explanations = explain_diagnostic_events(
        [
            build_diagnostic_event(CODE_REVIEW_PATCH_UNSAFE_PATH, DIAGNOSTIC_SEVERITY_ERROR, "unsafe", source=DIAGNOSTIC_SOURCE_REVIEW),
            build_diagnostic_event(CODE_GATE_UNRESOLVED_IMPORTS, DIAGNOSTIC_SEVERITY_ERROR, "imports", source=DIAGNOSTIC_SOURCE_GATE),
        ]
    )

    assert summarize_diagnostic_explanations(explanations)["primary_next_action"] == "fix_imports"


def test_unknown_failures_use_inspect_details():
    explanation = explain_diagnostic_event(
        build_diagnostic_event("unknown", DIAGNOSTIC_SEVERITY_ERROR, "unknown", source=DIAGNOSTIC_SOURCE_REVIEW)
    )

    assert explanation["next_action"] == "inspect_details"


def test_no_explanation_recommends_unsafe_actions():
    unsafe = {"apply_patch", "force_apply", "ignore_warning", "disable_gate", "bypass_review"}
    explanations = explain_diagnostic_events(
        [
            build_diagnostic_event(CODE_GATE_UNRESOLVED_IMPORTS, DIAGNOSTIC_SEVERITY_ERROR, "imports", source=DIAGNOSTIC_SOURCE_GATE),
            build_diagnostic_event(CODE_REVIEW_PATCH_UNSAFE_PATH, DIAGNOSTIC_SEVERITY_ERROR, "unsafe", source=DIAGNOSTIC_SOURCE_REVIEW),
            build_diagnostic_event("unknown", DIAGNOSTIC_SEVERITY_ERROR, "unknown", source=DIAGNOSTIC_SOURCE_REVIEW),
        ]
    )

    assert not (unsafe & {explanation["next_action"] for explanation in explanations})


def test_m1_style_diagnostics_can_be_normalized_and_explained():
    explanation = explain_diagnostic_event(
        {
            "code": "missing_required_field",
            "severity": "error",
            "message": "Run state is missing the required field 'task'.",
            "field": "task",
        }
    )

    assert explanation["source"] == DIAGNOSTIC_SOURCE_WORKFLOW_STATE
    assert explanation["next_action"] == "inspect_details"
    assert explanation["affected_items"] == ["task"]


def test_gate_result_converter_uses_existing_gate_shapes():
    events = gate_result_to_diagnostic_events(
        {
            "status": "FAIL",
            "failures": ["graph has 1 unresolved imports"],
            "warnings": [],
            "summary": {"unresolved_import_count": 1},
        }
    )

    assert events[0]["code"] == CODE_GATE_UNRESOLVED_IMPORTS
    assert events[0]["source"] == DIAGNOSTIC_SOURCE_GATE


def test_review_result_converter_uses_existing_patch_shapes():
    events = review_result_to_diagnostic_events(
        {
            "status": "invalid",
            "targets": [],
            "errors": ["Unsafe patch path '../outside.py': patch paths must stay inside the repository."],
            "warnings": [],
            "message": "Patch failed validation.",
        }
    )

    assert events[0]["code"] == CODE_REVIEW_PATCH_UNSAFE_PATH
    assert events[0]["source"] == DIAGNOSTIC_SOURCE_REVIEW


TESTS = [
    test_recognized_gate_error_produces_specific_explanation,
    test_recognized_review_error_produces_specific_explanation,
    test_unknown_codes_produce_conservative_generic_explanation,
    test_original_code_severity_and_source_are_preserved,
    test_inputs_normalize_through_m2_contract,
    test_affected_paths_are_extracted_deterministically,
    test_exact_duplicate_affected_items_are_removed,
    test_affected_items_are_sorted,
    test_affected_items_are_capped,
    test_truncation_metadata_is_correct,
    test_missing_affected_item_data_is_safe,
    test_explanation_output_is_json_ready,
    test_input_mappings_are_not_mutated,
    test_exact_duplicate_events_are_removed_before_explanation,
    test_event_severity_ordering_is_preserved,
    test_batch_output_is_deterministic,
    test_summary_counts_are_correct,
    test_primary_next_action_is_deterministic,
    test_unknown_failures_use_inspect_details,
    test_no_explanation_recommends_unsafe_actions,
    test_m1_style_diagnostics_can_be_normalized_and_explained,
    test_gate_result_converter_uses_existing_gate_shapes,
    test_review_result_converter_uses_existing_patch_shapes,
]
