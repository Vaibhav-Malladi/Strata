import json

from strata.core.dependency_tracing import (
    EDGE_TYPES,
    PRIORITIES,
    DependencyTraceReport,
    create_dependency_edge,
    merge_dependency_edges,
    normalize_relative_path,
    sort_dependency_edges,
)
from strata.core.stage_report import CONFIDENCE_LEVELS, StageReport


def _edge(**overrides):
    values = {
        "source_file": "src/app.py",
        "target_file": "src/service.py",
        "edge_type": "import",
        "priority": "high",
        "reason": "direct import",
        "confidence": "medium",
        "estimated_cost": 1.5,
    }
    values.update(overrides)
    return create_dependency_edge(**values)


def _expect_error(error_type, function, *args, contains: str, **kwargs):
    try:
        function(*args, **kwargs)
    except error_type as error:
        assert contains in str(error)
    else:
        raise AssertionError(f"Expected {error_type.__name__}")


def test_valid_edge_creation_normalizes_paths_and_has_stable_shape():
    edge = _edge(source_file="src\\app.py", target_file="src/./service.py")

    assert edge.source_file == "src/app.py"
    assert edge.target_file == "src/service.py"
    assert edge.to_dict() == {
        "source_file": "src/app.py",
        "target_file": "src/service.py",
        "edge_type": "import",
        "priority": "high",
        "reason": "direct import",
        "confidence": "medium",
        "estimated_cost": 1.5,
    }


def test_absolute_and_escaping_paths_are_rejected():
    for path in ("/src/app.py", "C:\\src\\app.py", "../app.py", "src/../app.py"):
        _expect_error(ValueError, normalize_relative_path, path, contains="path must")


def test_edge_type_priority_and_confidence_are_bounded():
    assert EDGE_TYPES == (
        "import",
        "re_export",
        "route",
        "template",
        "style",
        "config",
        "unknown",
    )
    assert PRIORITIES == ("critical", "high", "medium", "low")
    assert CONFIDENCE_LEVELS == ("unknown", "low", "medium", "high")

    _expect_error(ValueError, _edge, edge_type="call", contains="edge_type")
    _expect_error(ValueError, _edge, priority="urgent", contains="priority")
    _expect_error(ValueError, _edge, confidence="certain", contains="confidence")


def test_estimated_cost_is_finite_nonnegative_and_json_ready():
    assert json.loads(json.dumps(_edge(estimated_cost=2).to_dict()))[
        "estimated_cost"
    ] == 2.0
    for value in (-1, float("inf"), float("nan")):
        _expect_error(
            ValueError, _edge, estimated_cost=value, contains="estimated_cost"
        )
    _expect_error(TypeError, _edge, estimated_cost=True, contains="estimated_cost")


def test_edge_sorting_is_deterministic_and_priority_aware():
    low = _edge(source_file="z.py", priority="low")
    critical_b = _edge(source_file="b.py", priority="critical")
    critical_a = _edge(source_file="a.py", priority="critical")

    assert sort_dependency_edges((low, critical_b, critical_a)) == (
        critical_a,
        critical_b,
        low,
    )


def test_merge_removes_only_exact_duplicate_edges():
    edge = _edge()
    other_reason = _edge(reason="re-export evidence")

    assert merge_dependency_edges((edge, other_reason, edge)) == (
        edge,
        other_reason,
    )


def test_trace_report_is_immutable_deterministic_and_json_ready():
    report = DependencyTraceReport(
        seed_files=("src/z.py", "src\\a.py", "src/z.py"),
        edges=(_edge(priority="low"), _edge(priority="critical")),
        skipped_items=("unresolved package alias",),
        warnings=("trace depth unavailable in H1",),
    )
    payload = report.to_dict()

    assert payload["seed_files"] == ["src/a.py", "src/z.py"]
    assert [edge["priority"] for edge in payload["edges"]] == ["critical", "low"]
    assert payload["stage_report"] is None
    assert json.loads(json.dumps(payload, allow_nan=False)) == payload
    _expect_error(
        TypeError,
        DependencyTraceReport,
        seed_files="src/app.py",
        contains="seed_files",
    )


def test_confidence_is_metadata_only_and_does_not_change_priority():
    low_confidence = _edge(confidence="low")
    high_confidence = _edge(confidence="high")

    assert low_confidence.priority == high_confidence.priority
    assert set(low_confidence.to_dict()) == {
        "source_file",
        "target_file",
        "edge_type",
        "priority",
        "reason",
        "confidence",
        "estimated_cost",
    }


def test_trace_report_embeds_stage_report_cost_summary():
    stage_report = StageReport(
        "dependency_trace", bytes_read=128, files_touched=2, confidence="medium"
    )
    payload = DependencyTraceReport(stage_report=stage_report).to_dict()

    assert payload["stage_report"] == stage_report.to_dict()
    assert payload["stage_report"]["bytes_read"] == 128


TESTS = [
    test_valid_edge_creation_normalizes_paths_and_has_stable_shape,
    test_absolute_and_escaping_paths_are_rejected,
    test_edge_type_priority_and_confidence_are_bounded,
    test_estimated_cost_is_finite_nonnegative_and_json_ready,
    test_edge_sorting_is_deterministic_and_priority_aware,
    test_merge_removes_only_exact_duplicate_edges,
    test_trace_report_is_immutable_deterministic_and_json_ready,
    test_confidence_is_metadata_only_and_does_not_change_priority,
    test_trace_report_embeds_stage_report_cost_summary,
]
