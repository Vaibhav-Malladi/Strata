import json

from strata.core.diagnostics import (
    DIAGNOSTIC_SOURCE_APPLY,
    DIAGNOSTIC_SOURCE_GATE,
    DIAGNOSTIC_SOURCE_REVIEW,
    DIAGNOSTIC_SOURCE_SYSTEM,
    DIAGNOSTIC_SOURCE_WORKFLOW_STATE,
    DIAGNOSTIC_SEVERITY_ERROR,
    DIAGNOSTIC_SEVERITY_INFO,
    DIAGNOSTIC_SEVERITY_WARNING,
    build_diagnostic_event,
    deduplicate_diagnostic_events,
    normalize_diagnostic_event,
    sort_diagnostic_events,
    summarize_diagnostic_events,
)


def test_valid_event_returns_stable_canonical_shape():
    event = build_diagnostic_event(
        "missing_required_field",
        DIAGNOSTIC_SEVERITY_ERROR,
        "Run state is missing a required field.",
        source=DIAGNOSTIC_SOURCE_WORKFLOW_STATE,
        field="task",
        next_action="repair_or_regenerate_run_state",
        details={"expected": ["task"]},
    )

    assert event == {
        "code": "missing_required_field",
        "severity": "error",
        "message": "Run state is missing a required field.",
        "source": "workflow_state",
        "field": "task",
        "path": None,
        "next_action": "repair_or_regenerate_run_state",
        "details": {"expected": ["task"]},
    }
    assert json.loads(json.dumps(event, allow_nan=False)) == event


def test_required_fields_are_validated():
    for kwargs in (
        {"code": "", "severity": DIAGNOSTIC_SEVERITY_ERROR, "message": "message"},
        {"code": "code", "severity": DIAGNOSTIC_SEVERITY_ERROR, "message": ""},
    ):
        try:
            build_diagnostic_event(**kwargs, source=DIAGNOSTIC_SOURCE_SYSTEM)
        except ValueError as error:
            assert "non-empty string" in str(error)
        else:
            raise AssertionError("Invalid required field was accepted")


def test_severity_vocabulary_is_enforced():
    try:
        build_diagnostic_event(
            "code",
            "fail",
            "message",
            source=DIAGNOSTIC_SOURCE_SYSTEM,
        )
    except ValueError as error:
        assert "severity must be one of" in str(error)
    else:
        raise AssertionError("Unsupported severity was accepted")


def test_source_vocabulary_is_enforced():
    try:
        build_diagnostic_event(
            "code",
            DIAGNOSTIC_SEVERITY_ERROR,
            "message",
            source="adapter",
        )
    except ValueError as error:
        assert "source must be one of" in str(error)
    else:
        raise AssertionError("Unsupported source was accepted")


def test_optional_strings_are_validated():
    for kwargs in (
        {"field": 1},
        {"path": 1},
        {"next_action": 1},
    ):
        try:
            build_diagnostic_event(
                "code",
                DIAGNOSTIC_SEVERITY_ERROR,
                "message",
                source=DIAGNOSTIC_SOURCE_SYSTEM,
                **kwargs,
            )
        except ValueError as error:
            assert "must be a string or null" in str(error)
        else:
            raise AssertionError("Invalid optional string was accepted")


def test_details_must_be_a_mapping():
    try:
        build_diagnostic_event(
            "code",
            DIAGNOSTIC_SEVERITY_ERROR,
            "message",
            source=DIAGNOSTIC_SOURCE_SYSTEM,
            details=[],
        )
    except ValueError as error:
        assert "details must be a mapping or null" in str(error)
    else:
        raise AssertionError("Non-mapping details were accepted")


def test_details_reject_non_string_mapping_keys():
    try:
        build_diagnostic_event(
            "code",
            DIAGNOSTIC_SEVERITY_ERROR,
            "message",
            source=DIAGNOSTIC_SOURCE_SYSTEM,
            details={1: "bad"},
        )
    except ValueError as error:
        assert "details keys must be strings" in str(error)
    else:
        raise AssertionError("Non-string details key was accepted")


def test_details_reject_unsupported_values():
    for value in ({1, 2}, (1, 2), 1.5, b"bytes"):
        try:
            build_diagnostic_event(
                "code",
                DIAGNOSTIC_SEVERITY_ERROR,
                "message",
                source=DIAGNOSTIC_SOURCE_SYSTEM,
                details={"value": value},
            )
        except ValueError as error:
            assert "must be JSON-ready" in str(error)
        else:
            raise AssertionError("Unsupported details value was accepted")


def test_empty_list_remains_empty_list():
    event = build_diagnostic_event(
        "code",
        DIAGNOSTIC_SEVERITY_INFO,
        "message",
        source=DIAGNOSTIC_SOURCE_SYSTEM,
        details={"items": []},
    )

    assert event["details"]["items"] == []
    assert isinstance(event["details"]["items"], list)


def test_empty_mapping_remains_empty_mapping():
    event = build_diagnostic_event(
        "code",
        DIAGNOSTIC_SEVERITY_INFO,
        "message",
        source=DIAGNOSTIC_SOURCE_SYSTEM,
        details={"meta": {}},
    )

    assert event["details"]["meta"] == {}
    assert isinstance(event["details"]["meta"], dict)


def test_nested_mappings_and_lists_retain_exact_types():
    event = build_diagnostic_event(
        "code",
        DIAGNOSTIC_SEVERITY_INFO,
        "message",
        source=DIAGNOSTIC_SOURCE_SYSTEM,
        details={"outer": {"items": [{"ok": True}, None]}},
    )

    outer = event["details"]["outer"]
    assert isinstance(outer, dict)
    assert isinstance(outer["items"], list)
    assert isinstance(outer["items"][0], dict)


def test_list_order_is_preserved():
    event = build_diagnostic_event(
        "code",
        DIAGNOSTIC_SEVERITY_INFO,
        "message",
        source=DIAGNOSTIC_SOURCE_SYSTEM,
        details={"items": ["b", "a", "c"]},
    )

    assert event["details"]["items"] == ["b", "a", "c"]


def test_mapping_keys_are_normalized_deterministically():
    event = build_diagnostic_event(
        "code",
        DIAGNOSTIC_SEVERITY_INFO,
        "message",
        source=DIAGNOSTIC_SOURCE_SYSTEM,
        details={"z": 1, "a": 2, "m": {"b": 1, "a": 2}},
    )

    assert list(event["details"].keys()) == ["a", "m", "z"]
    assert list(event["details"]["m"].keys()) == ["a", "b"]


def test_original_details_mutation_does_not_affect_event():
    details = {"items": [{"name": "first"}]}
    event = build_diagnostic_event(
        "code",
        DIAGNOSTIC_SEVERITY_INFO,
        "message",
        source=DIAGNOSTIC_SOURCE_SYSTEM,
        details=details,
    )
    details["items"][0]["name"] = "changed"

    assert event["details"] == {"items": [{"name": "first"}]}


def test_sorting_is_deterministic():
    events = [
        _event("z", DIAGNOSTIC_SEVERITY_WARNING, DIAGNOSTIC_SOURCE_REVIEW),
        _event("a", DIAGNOSTIC_SEVERITY_WARNING, DIAGNOSTIC_SOURCE_REVIEW),
        _event("b", DIAGNOSTIC_SEVERITY_ERROR, DIAGNOSTIC_SOURCE_GATE),
    ]

    assert sort_diagnostic_events(events) == sort_diagnostic_events(list(reversed(events)))


def test_sorting_does_not_mutate_inputs():
    event = _event("z", DIAGNOSTIC_SEVERITY_WARNING, DIAGNOSTIC_SOURCE_REVIEW)
    events = [event]
    before = [dict(event)]

    sort_diagnostic_events(events)

    assert events == before


def test_severity_precedence_is_error_warning_info():
    ordered = sort_diagnostic_events(
        [
            _event("info", DIAGNOSTIC_SEVERITY_INFO, DIAGNOSTIC_SOURCE_SYSTEM),
            _event("warning", DIAGNOSTIC_SEVERITY_WARNING, DIAGNOSTIC_SOURCE_SYSTEM),
            _event("error", DIAGNOSTIC_SEVERITY_ERROR, DIAGNOSTIC_SOURCE_SYSTEM),
        ]
    )

    assert [event["severity"] for event in ordered] == ["error", "warning", "info"]


def test_exact_duplicates_are_removed():
    event = _event("same", DIAGNOSTIC_SEVERITY_WARNING, DIAGNOSTIC_SOURCE_APPLY)

    assert deduplicate_diagnostic_events([event, dict(event)]) == [event]


def test_events_differing_in_any_canonical_field_are_retained():
    base = _event("same", DIAGNOSTIC_SEVERITY_WARNING, DIAGNOSTIC_SOURCE_APPLY)
    variants = [
        dict(base, severity=DIAGNOSTIC_SEVERITY_ERROR),
        dict(base, source=DIAGNOSTIC_SOURCE_REVIEW),
        dict(base, message="different message"),
        dict(base, field="field"),
        dict(base, path="path.py"),
        dict(base, next_action="inspect_diagnostics"),
        dict(base, details={"value": "different"}),
    ]

    assert len(deduplicate_diagnostic_events([base, *variants])) == 8


def test_summary_counts_are_correct():
    summary = summarize_diagnostic_events(
        [
            _event("a", DIAGNOSTIC_SEVERITY_ERROR, DIAGNOSTIC_SOURCE_GATE),
            _event("b", DIAGNOSTIC_SEVERITY_ERROR, DIAGNOSTIC_SOURCE_REVIEW),
            _event("c", DIAGNOSTIC_SEVERITY_WARNING, DIAGNOSTIC_SOURCE_APPLY),
            _event("d", DIAGNOSTIC_SEVERITY_INFO, DIAGNOSTIC_SOURCE_SYSTEM),
        ]
    )

    assert summary == {
        "total": 4,
        "errors": 2,
        "warnings": 1,
        "info": 1,
        "has_errors": True,
        "has_warnings": True,
    }


def test_m1_style_legacy_diagnostic_normalizes_with_workflow_state_source():
    event = normalize_diagnostic_event(
        {
            "code": "missing_required_field",
            "severity": "error",
            "message": "Run state is missing the required field 'task'.",
            "field": "task",
        },
        default_source=DIAGNOSTIC_SOURCE_WORKFLOW_STATE,
    )

    assert event["source"] == "workflow_state"
    assert event["field"] == "task"
    assert event["details"] == {}


def test_legacy_value_is_placed_only_in_details_value():
    event = normalize_diagnostic_event(
        {
            "code": "unsupported_schema_version",
            "severity": "error",
            "message": "Run state schema_version must be 1.",
            "field": "schema_version",
            "value": 2,
        },
        default_source=DIAGNOSTIC_SOURCE_WORKFLOW_STATE,
    )

    assert "value" not in event
    assert event["details"] == {"value": 2}


def test_invalid_legacy_mappings_fail_predictably():
    for legacy in (
        {"severity": "error", "message": "missing code"},
        {"code": "code", "message": "missing severity"},
        {"code": "code", "severity": "error"},
        {"code": "code", "severity": "error", "message": "missing source"},
    ):
        try:
            normalize_diagnostic_event(legacy)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid legacy diagnostic was accepted")


def _event(code: str, severity: str, source: str) -> dict[str, object]:
    return build_diagnostic_event(
        code,
        severity,
        f"{code} message.",
        source=source,
    )


TESTS = [
    test_valid_event_returns_stable_canonical_shape,
    test_required_fields_are_validated,
    test_severity_vocabulary_is_enforced,
    test_source_vocabulary_is_enforced,
    test_optional_strings_are_validated,
    test_details_must_be_a_mapping,
    test_details_reject_non_string_mapping_keys,
    test_details_reject_unsupported_values,
    test_empty_list_remains_empty_list,
    test_empty_mapping_remains_empty_mapping,
    test_nested_mappings_and_lists_retain_exact_types,
    test_list_order_is_preserved,
    test_mapping_keys_are_normalized_deterministically,
    test_original_details_mutation_does_not_affect_event,
    test_sorting_is_deterministic,
    test_sorting_does_not_mutate_inputs,
    test_severity_precedence_is_error_warning_info,
    test_exact_duplicates_are_removed,
    test_events_differing_in_any_canonical_field_are_retained,
    test_summary_counts_are_correct,
    test_m1_style_legacy_diagnostic_normalizes_with_workflow_state_source,
    test_legacy_value_is_placed_only_in_details_value,
    test_invalid_legacy_mappings_fail_predictably,
]
