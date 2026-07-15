"""Data-only summaries for backend relationship evaluation."""

from dataclasses import dataclass
from typing import Any, Iterable

from strata.core.backend_relationships import BackendRelationship, sort_backend_relationships


@dataclass(frozen=True, slots=True)
class BackendRelationshipSummary:
    relationships: tuple[BackendRelationship, ...]
    duplicate_relationship_count: int

    def __post_init__(self) -> None:
        relationships = _validate_relationships(self.relationships)
        unique_relationships = sort_backend_relationships(set(relationships))
        duplicate_count = len(relationships) - len(unique_relationships)
        object.__setattr__(self, "relationships", unique_relationships)
        object.__setattr__(
            self,
            "duplicate_relationship_count",
            _nonnegative_integer(
                self.duplicate_relationship_count,
                "duplicate_relationship_count",
            ),
        )
        if self.duplicate_relationship_count != duplicate_count:
            object.__setattr__(self, "duplicate_relationship_count", duplicate_count)

    def to_dict(self) -> dict[str, Any]:
        warnings = tuple(
            sorted({warning for item in self.relationships for warning in item.warnings})
        )
        return {
            "relationship_count": len(self.relationships),
            "duplicate_relationship_count": self.duplicate_relationship_count,
            "frameworks": _count_values(item.framework for item in self.relationships),
            "relationship_types": _count_values(
                item.relationship_type for item in self.relationships
            ),
            "http_methods": _count_values(item.http_method for item in self.relationships),
            "confidences": _count_values(item.confidence for item in self.relationships),
            "source_paths": sorted({item.source_path for item in self.relationships}),
            "route_paths": sorted(
                {item.route_path for item in self.relationships if item.route_path}
            ),
            "warning_count": sum(len(item.warnings) for item in self.relationships),
            "warnings": list(warnings),
            "relationships": [item.to_dict() for item in self.relationships],
        }


def summarize_backend_relationships(
    relationships: Iterable[BackendRelationship],
) -> BackendRelationshipSummary:
    values = _validate_relationships(relationships)
    return BackendRelationshipSummary(relationships=values, duplicate_relationship_count=0)


def backend_relationship_summary_to_dict(
    summary: BackendRelationshipSummary,
) -> dict[str, Any]:
    if not isinstance(summary, BackendRelationshipSummary):
        raise TypeError("summary must be a BackendRelationshipSummary")
    return summary.to_dict()


def _validate_relationships(
    relationships: Iterable[BackendRelationship],
) -> tuple[BackendRelationship, ...]:
    if isinstance(relationships, (str, bytes)):
        raise TypeError("relationships must be an iterable of BackendRelationship values")
    try:
        values = tuple(relationships)
    except TypeError as error:
        raise TypeError(
            "relationships must be an iterable of BackendRelationship values"
        ) from error
    if not all(isinstance(value, BackendRelationship) for value in values):
        raise TypeError("relationships must contain only BackendRelationship values")
    return values


def _count_values(values: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return {key: counts[key] for key in sorted(counts)}


def _nonnegative_integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value
