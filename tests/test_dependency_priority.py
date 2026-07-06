import math

from strata.core.dependency_priority import (
    CONFIDENCE_AFFECTS_PRIORITY,
    EDGE_TYPE_BASE_COSTS,
    EVIDENCE_PRIORITIES,
    estimate_dependency_cost,
    priority_for_evidence,
    priority_rank,
    traversal_order_key,
)
from strata.core.dependency_tracing import create_dependency_edge


def _edge(*, priority="medium", confidence="unknown", cost=1.0, target="b.py"):
    return create_dependency_edge(
        "a.py", target, "import", priority, "test edge", confidence, cost
    )


def test_priority_order_is_deterministic_and_bounded():
    assert [
        priority_rank(value) for value in ("critical", "high", "medium", "low")
    ] == [0, 1, 2, 3]
    assert priority_for_evidence("exact_import") == "medium"
    assert priority_for_evidence("dynamic_import") == "low"
    assert tuple(EVIDENCE_PRIORITIES) == (
        "exact_import",
        "exact_re_export",
        "symbol_import",
        "dynamic_import",
        "commonjs_require",
        "unknown",
    )


def test_cost_estimates_are_finite_and_nonnegative():
    costs = [
        estimate_dependency_cost(edge_type, "unknown")
        for edge_type in EDGE_TYPE_BASE_COSTS
    ]

    assert all(math.isfinite(cost) and cost >= 0 for cost in costs)
    assert estimate_dependency_cost("import", "exact_import") == 1.0
    assert estimate_dependency_cost("re_export", "exact_re_export") == 1.0


def test_confidence_is_metadata_only():
    low = _edge(confidence="low")
    high = _edge(confidence="high")

    assert CONFIDENCE_AFFECTS_PRIORITY is False
    assert traversal_order_key(low, 1) == traversal_order_key(high, 1)
    assert low.estimated_cost == high.estimated_cost


def test_traversal_key_uses_priority_then_cost_then_depth_and_path():
    edges = (
        _edge(priority="low", cost=0.1, target="a.py"),
        _edge(priority="high", cost=2.0, target="z.py"),
        _edge(priority="high", cost=1.0, target="b.py"),
    )

    ordered = sorted(edges, key=lambda edge: traversal_order_key(edge, 1))

    assert [edge.target_file for edge in ordered] == ["b.py", "z.py", "a.py"]


TESTS = [
    test_priority_order_is_deterministic_and_bounded,
    test_cost_estimates_are_finite_and_nonnegative,
    test_confidence_is_metadata_only,
    test_traversal_key_uses_priority_then_cost_then_depth_and_path,
]
