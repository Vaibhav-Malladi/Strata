import json

from strata.core.stage_report import (
    StageReport,
    create_stage_report,
    elapsed_milliseconds,
    stage_report_to_dict,
)


def _expect_error(error_type, function, *args, contains: str, **kwargs):
    try:
        function(*args, **kwargs)
    except error_type as error:
        assert contains in str(error)
    else:
        raise AssertionError(f"Expected {error_type.__name__}")


def test_stage_report_has_deterministic_shape():
    report = create_stage_report(
        "candidate_inventory",
        inputs={"task": "fix auth", "limit": 20},
        outputs={"candidate_paths": ["b.py", "a.py"]},
        metrics={"recall_hint": 0.75, "counts": {"useful": 2, "critical": 1}},
        warnings=("inventory capped",),
        skipped_items=("vendor/library.js",),
        confidence="medium",
        elapsed_ms=1.25,
        bytes_read=128,
        files_touched=2,
    )

    assert stage_report_to_dict(report) == {
        "stage_name": "candidate_inventory",
        "inputs": {"limit": 20, "task": "fix auth"},
        "outputs": {"candidate_paths": ["b.py", "a.py"]},
        "metrics": {
            "counts": {"critical": 1, "useful": 2},
            "recall_hint": 0.75,
        },
        "warnings": ["inventory capped"],
        "skipped_items": ["vendor/library.js"],
        "confidence": "medium",
        "elapsed_ms": 1.25,
        "bytes_read": 128,
        "files_touched": 2,
    }


def test_stage_report_defaults_are_empty_and_zero_cost():
    report = StageReport("inventory")

    assert report.to_dict() == {
        "stage_name": "inventory",
        "inputs": {},
        "outputs": {},
        "metrics": {},
        "warnings": [],
        "skipped_items": [],
        "confidence": "unknown",
        "elapsed_ms": 0.0,
        "bytes_read": 0,
        "files_touched": 0,
    }


def test_stage_report_validates_confidence():
    for confidence in ("unknown", "low", "medium", "high"):
        assert StageReport("inventory", confidence=confidence).confidence == confidence

    _expect_error(
        ValueError,
        StageReport,
        "inventory",
        confidence="certain",
        contains="confidence must be one of",
    )


def test_stage_report_validates_cost_types():
    invalid_values = (True, "1", None)
    for value in invalid_values:
        _expect_error(
            TypeError,
            StageReport,
            "inventory",
            elapsed_ms=value,
            contains="elapsed_ms",
        )
        _expect_error(
            TypeError,
            StageReport,
            "inventory",
            bytes_read=value,
            contains="bytes_read",
        )
        _expect_error(
            TypeError,
            StageReport,
            "inventory",
            files_touched=value,
            contains="files_touched",
        )


def test_stage_report_rejects_negative_and_nonfinite_costs():
    for field_name in ("elapsed_ms", "bytes_read", "files_touched"):
        _expect_error(
            ValueError,
            StageReport,
            "inventory",
            **{field_name: -1},
            contains=field_name,
        )

    for value in (float("inf"), float("nan")):
        _expect_error(
            ValueError,
            StageReport,
            "inventory",
            elapsed_ms=value,
            contains="elapsed_ms",
        )


def test_stage_report_metrics_are_json_ready_sorted_and_immutable():
    source = {"z": [2, 1], "a": {"second": True, "first": None}}
    report = StageReport("inventory", metrics=source)
    source["z"].append(0)

    assert report.to_dict()["metrics"] == {
        "a": {"first": None, "second": True},
        "z": [2, 1],
    }
    _expect_error(
        TypeError,
        StageReport,
        "inventory",
        metrics={"paths": {"a.py"}},
        contains="JSON-ready",
    )


def test_warnings_and_skipped_items_preserve_order():
    report = (
        StageReport("inventory")
        .with_warning("first warning")
        .with_warning("second warning")
        .with_skipped_item("first.py")
        .with_skipped_item("second.py")
    )

    assert report.warnings == ("first warning", "second warning")
    assert report.skipped_items == ("first.py", "second.py")


def test_with_metric_returns_a_new_report_with_stable_metrics():
    original = StageReport("inventory", metrics={"z": 1})
    updated = original.with_metric("a", {"value": 2})

    assert original.to_dict()["metrics"] == {"z": 1}
    assert updated.to_dict()["metrics"] == {"a": {"value": 2}, "z": 1}


def test_stage_report_serializes_without_a_custom_encoder():
    report = StageReport(
        "inventory",
        inputs={"extensions": (".py", ".ts")},
        metrics={"ratio": 0.5},
    )

    serialized = json.dumps(report.to_dict(), allow_nan=False)

    assert json.loads(serialized) == report.to_dict()


def test_elapsed_milliseconds_uses_monotonic_nanosecond_values():
    assert elapsed_milliseconds(1_000_000, 3_500_000) == 2.5
    _expect_error(
        ValueError,
        elapsed_milliseconds,
        3_500_000,
        1_000_000,
        contains="end_ns",
    )


TESTS = [
    test_stage_report_has_deterministic_shape,
    test_stage_report_defaults_are_empty_and_zero_cost,
    test_stage_report_validates_confidence,
    test_stage_report_validates_cost_types,
    test_stage_report_rejects_negative_and_nonfinite_costs,
    test_stage_report_metrics_are_json_ready_sorted_and_immutable,
    test_warnings_and_skipped_items_preserve_order,
    test_with_metric_returns_a_new_report_with_stable_metrics,
    test_stage_report_serializes_without_a_custom_encoder,
    test_elapsed_milliseconds_uses_monotonic_nanosecond_values,
]
