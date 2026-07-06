"""Central deterministic priority, cost, and traversal policy for dependencies."""

import math
from types import MappingProxyType
from typing import Any

from strata.core.dependency_tracing import EDGE_TYPES, PRIORITIES, DependencyEdge


DEFAULT_MAX_DEPTH = 2
DEFAULT_MAX_FILES = 40
DEFAULT_MAX_EDGES = 100
DEFAULT_MAX_ESTIMATED_COST = 100.0

CONFIDENCE_AFFECTS_PRIORITY = False
UNRESOLVED_TARGET_POLICY = "skip"
UNSUPPORTED_TARGET_POLICY = "skip"

PRIORITY_RANK = MappingProxyType(
    {priority: index for index, priority in enumerate(PRIORITIES)}
)
EVIDENCE_PRIORITIES = MappingProxyType(
    {
        "exact_import": "medium",
        "exact_re_export": "medium",
        "symbol_import": "low",
        "dynamic_import": "low",
        "commonjs_require": "low",
        "unknown": "low",
    }
)
EDGE_TYPE_BASE_COSTS = MappingProxyType(
    {
        "import": 1.0,
        "re_export": 1.0,
        "route": 1.25,
        "template": 1.0,
        "style": 0.75,
        "config": 1.0,
        "unknown": 1.5,
    }
)
EVIDENCE_COST_MULTIPLIERS = MappingProxyType(
    {
        "exact_import": 1.0,
        "exact_re_export": 1.0,
        "symbol_import": 1.0,
        "dynamic_import": 1.0,
        "commonjs_require": 1.0,
        "unknown": 1.0,
    }
)


def priority_for_evidence(evidence_kind: str) -> str:
    """Return the bounded edge priority for one extraction evidence kind."""

    if not isinstance(evidence_kind, str):
        raise TypeError("evidence_kind must be a string")
    try:
        return EVIDENCE_PRIORITIES[evidence_kind]
    except KeyError as error:
        raise ValueError(
            f"unsupported dependency evidence kind: {evidence_kind}"
        ) from error


def priority_rank(priority: str) -> int:
    """Return the stable critical-to-low rank for a bounded priority."""

    if not isinstance(priority, str):
        raise TypeError("priority must be a string")
    try:
        return PRIORITY_RANK[priority]
    except KeyError as error:
        raise ValueError(f"priority must be one of: {', '.join(PRIORITIES)}") from error


def estimate_dependency_cost(edge_type: str, evidence_kind: str) -> float:
    """Estimate finite non-negative relative work without confidence weighting."""

    if not isinstance(edge_type, str):
        raise TypeError("edge_type must be a string")
    if edge_type not in EDGE_TYPES:
        raise ValueError(f"edge_type must be one of: {', '.join(EDGE_TYPES)}")
    if not isinstance(evidence_kind, str):
        raise TypeError("evidence_kind must be a string")
    try:
        multiplier = EVIDENCE_COST_MULTIPLIERS[evidence_kind]
    except KeyError as error:
        raise ValueError(
            f"unsupported dependency evidence kind: {evidence_kind}"
        ) from error
    cost = float(EDGE_TYPE_BASE_COSTS[edge_type] * multiplier)
    if not math.isfinite(cost) or cost < 0:
        raise ValueError("dependency cost policy produced an invalid cost")
    return cost


def traversal_order_key(edge: DependencyEdge, depth: int) -> tuple[Any, ...]:
    """Order by priority, cost, depth, and stable paths; never by confidence."""

    if not isinstance(edge, DependencyEdge):
        raise TypeError("edge must be a DependencyEdge")
    if isinstance(depth, bool) or not isinstance(depth, int):
        raise TypeError("depth must be an integer")
    if depth < 0:
        raise ValueError("depth must be non-negative")
    return (
        priority_rank(edge.priority),
        edge.estimated_cost,
        depth,
        edge.target_file,
        edge.source_file,
        edge.edge_type,
        edge.reason,
    )
