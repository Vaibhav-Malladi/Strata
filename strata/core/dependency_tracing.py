"""Stable contracts for dependency tracing without parser or traversal policy."""

import math
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Iterable

from strata.core.stage_report import CONFIDENCE_LEVELS, StageReport


class DependencyEdgeType(StrEnum):
    """Small initial vocabulary for relationships between repository files."""

    IMPORT = "import"
    RE_EXPORT = "re_export"
    ROUTE = "route"
    TEMPLATE = "template"
    STYLE = "style"
    CONFIG = "config"
    UNKNOWN = "unknown"


class DependencyPriority(StrEnum):
    """Bounded importance assigned by a future tracing producer."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


EDGE_TYPES = tuple(value.value for value in DependencyEdgeType)
PRIORITIES = tuple(value.value for value in DependencyPriority)
_PRIORITY_ORDER = {priority: index for index, priority in enumerate(PRIORITIES)}


@dataclass(frozen=True, slots=True)
class DependencyEdge:
    """One immutable, directed relationship between two repository files."""

    source_file: str
    target_file: str
    edge_type: str
    priority: str
    reason: str
    confidence: str
    estimated_cost: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "source_file", normalize_relative_path(self.source_file)
        )
        object.__setattr__(
            self, "target_file", normalize_relative_path(self.target_file)
        )
        object.__setattr__(
            self, "edge_type", _validate_choice(self.edge_type, "edge_type", EDGE_TYPES)
        )
        object.__setattr__(
            self, "priority", _validate_choice(self.priority, "priority", PRIORITIES)
        )
        object.__setattr__(self, "reason", _validate_message(self.reason, "reason"))
        object.__setattr__(
            self,
            "confidence",
            _validate_choice(self.confidence, "confidence", CONFIDENCE_LEVELS),
        )
        object.__setattr__(
            self, "estimated_cost", _validate_estimated_cost(self.estimated_cost)
        )

    def to_dict(self) -> dict[str, Any]:
        """Return the stable JSON-ready edge representation."""

        return {
            "source_file": self.source_file,
            "target_file": self.target_file,
            "edge_type": self.edge_type,
            "priority": self.priority,
            "reason": self.reason,
            "confidence": self.confidence,
            "estimated_cost": self.estimated_cost,
        }


@dataclass(frozen=True, slots=True)
class DependencyTraceReport:
    """Immutable result envelope shared by future tracers and Part I."""

    seed_files: tuple[str, ...] = ()
    edges: tuple[DependencyEdge, ...] = ()
    skipped_items: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    stage_report: StageReport | None = None

    def __post_init__(self) -> None:
        if isinstance(self.seed_files, (str, bytes)):
            raise TypeError("seed_files must be an iterable of relative paths")
        try:
            seed_files = tuple(self.seed_files)
        except TypeError as error:
            raise TypeError(
                "seed_files must be an iterable of relative paths"
            ) from error
        normalized_seeds = tuple(
            sorted({normalize_relative_path(path) for path in seed_files})
        )
        object.__setattr__(self, "seed_files", normalized_seeds)
        object.__setattr__(self, "edges", merge_dependency_edges(self.edges))
        object.__setattr__(
            self,
            "skipped_items",
            _validate_messages(self.skipped_items, "skipped_items"),
        )
        object.__setattr__(
            self, "warnings", _validate_messages(self.warnings, "warnings")
        )
        if self.stage_report is not None and not isinstance(
            self.stage_report, StageReport
        ):
            raise TypeError("stage_report must be a StageReport or None")

    def to_dict(self) -> dict[str, Any]:
        """Return the stable JSON-ready trace representation."""

        return {
            "seed_files": list(self.seed_files),
            "edges": [edge.to_dict() for edge in self.edges],
            "skipped_items": list(self.skipped_items),
            "warnings": list(self.warnings),
            "stage_report": (
                None if self.stage_report is None else self.stage_report.to_dict()
            ),
        }


def normalize_relative_path(value: str) -> str:
    """Normalize a non-empty repository-relative path to forward slashes."""

    if not isinstance(value, str):
        raise TypeError("path must be a string")
    if not value or not value.strip():
        raise ValueError("path must be a non-empty relative path")
    if value != value.strip() or "\x00" in value:
        raise ValueError("path must not contain whitespace padding or null bytes")

    windows_path = PureWindowsPath(value)
    posix_value = value.replace("\\", "/")
    posix_path = PurePosixPath(posix_value)
    if posix_path.is_absolute() or windows_path.is_absolute() or windows_path.drive:
        raise ValueError("path must be relative")
    if ".." in posix_path.parts:
        raise ValueError("path must not escape its root with '..'")

    normalized = posix_path.as_posix()
    if normalized in ("", "."):
        raise ValueError("path must identify a repository file")
    return normalized


def create_dependency_edge(
    source_file: str,
    target_file: str,
    edge_type: str,
    priority: str,
    reason: str,
    confidence: str = "unknown",
    estimated_cost: int | float = 0.0,
) -> DependencyEdge:
    """Create and validate an immutable dependency edge."""

    return DependencyEdge(
        source_file=source_file,
        target_file=target_file,
        edge_type=edge_type,
        priority=priority,
        reason=reason,
        confidence=confidence,
        estimated_cost=estimated_cost,
    )


def dependency_edge_to_dict(edge: DependencyEdge) -> dict[str, Any]:
    """Convert an edge to its stable JSON-ready shape."""

    if not isinstance(edge, DependencyEdge):
        raise TypeError("edge must be a DependencyEdge")
    return edge.to_dict()


def dependency_trace_report_to_dict(
    report: DependencyTraceReport,
) -> dict[str, Any]:
    """Convert a trace report to its stable JSON-ready shape."""

    if not isinstance(report, DependencyTraceReport):
        raise TypeError("report must be a DependencyTraceReport")
    return report.to_dict()


def sort_dependency_edges(
    edges: Iterable[DependencyEdge],
) -> tuple[DependencyEdge, ...]:
    """Return edges in semantic priority order with deterministic tie-breaks."""

    validated = _validate_edges(edges)
    return tuple(
        sorted(
            validated,
            key=lambda edge: (
                _PRIORITY_ORDER[edge.priority],
                edge.source_file,
                edge.target_file,
                edge.edge_type,
                edge.reason,
                edge.estimated_cost,
                edge.confidence,
            ),
        )
    )


def merge_dependency_edges(
    edges: Iterable[DependencyEdge],
) -> tuple[DependencyEdge, ...]:
    """Remove exactly identical edges and return deterministic ordering."""

    return sort_dependency_edges(set(_validate_edges(edges)))


def _validate_edges(edges: Iterable[DependencyEdge]) -> tuple[DependencyEdge, ...]:
    if isinstance(edges, (str, bytes)):
        raise TypeError("edges must be an iterable of DependencyEdge values")
    try:
        result = tuple(edges)
    except TypeError as error:
        raise TypeError("edges must be an iterable of DependencyEdge values") from error
    if not all(isinstance(edge, DependencyEdge) for edge in result):
        raise TypeError("edges must contain only DependencyEdge values")
    return result


def _validate_choice(value: Any, name: str, allowed: tuple[str, ...]) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if value not in allowed:
        raise ValueError(f"{name} must be one of: {', '.join(allowed)}")
    return next(item for item in allowed if item == value)


def _validate_message(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    if value != value.strip():
        raise ValueError(f"{name} must not have surrounding whitespace")
    return value


def _validate_messages(value: Any, name: str) -> tuple[str, ...]:
    if isinstance(value, str):
        raise TypeError(f"{name} must be an iterable of strings")
    try:
        messages = tuple(value)
    except TypeError as error:
        raise TypeError(f"{name} must be an iterable of strings") from error
    for index, message in enumerate(messages):
        _validate_message(message, f"{name}[{index}]")
    return messages


def _validate_estimated_cost(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("estimated_cost must be a number")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized < 0:
        raise ValueError("estimated_cost must be a finite non-negative number")
    return normalized
