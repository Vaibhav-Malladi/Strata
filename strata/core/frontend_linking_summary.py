"""Deterministic summaries for frontend relationship evaluation.

J7 summarizes already-inferred FrontendRelationship records. It does not scan
repositories, read files, call frontend linkers itself, or choose context
representation; Part I remains the token firewall.
"""

from dataclasses import dataclass
from typing import Any, Iterable

from strata.core.frontend_relationships import (
    FrontendRelationship,
    sort_frontend_relationships,
)


@dataclass(frozen=True, slots=True)
class FrontendLinkingSummary:
    """Small JSON-ready summary of frontend relationship records."""

    relationships: tuple[FrontendRelationship, ...]
    duplicate_relationship_count: int

    def __post_init__(self) -> None:
        relationships = _validate_relationships(self.relationships)
        unique_relationships = sort_frontend_relationships(set(relationships))
        duplicate_count = len(relationships) - len(unique_relationships)
        object.__setattr__(self, "relationships", unique_relationships)
        object.__setattr__(
            self,
            "duplicate_relationship_count",
            _validate_nonnegative_integer(
                self.duplicate_relationship_count,
                "duplicate_relationship_count",
            ),
        )
        if self.duplicate_relationship_count != duplicate_count:
            object.__setattr__(self, "duplicate_relationship_count", duplicate_count)

    def to_dict(self) -> dict[str, Any]:
        """Return the deterministic JSON-ready summary."""

        warnings = tuple(
            sorted(
                {warning for item in self.relationships for warning in item.warnings}
            )
        )
        return {
            "relationship_count": len(self.relationships),
            "duplicate_relationship_count": self.duplicate_relationship_count,
            "frameworks": _count_values(item.framework for item in self.relationships),
            "relationship_types": _count_values(
                item.relationship_type for item in self.relationships
            ),
            "confidences": _count_values(item.confidence for item in self.relationships),
            "source_paths": sorted({item.source_path for item in self.relationships}),
            "target_paths": sorted(
                {item.target_path for item in self.relationships if item.target_path}
            ),
            "target_symbols": sorted(
                {
                    item.target_symbol
                    for item in self.relationships
                    if item.target_symbol
                }
            ),
            "warning_count": sum(len(item.warnings) for item in self.relationships),
            "warnings": list(warnings),
            "relationships": [item.to_dict() for item in self.relationships],
        }


def summarize_frontend_relationships(
    relationships: Iterable[FrontendRelationship],
) -> FrontendLinkingSummary:
    """Create a deterministic summary from inferred frontend relationships."""

    values = _validate_relationships(relationships)
    return FrontendLinkingSummary(
        relationships=values,
        duplicate_relationship_count=0,
    )


def frontend_linking_summary_to_dict(
    summary: FrontendLinkingSummary,
) -> dict[str, Any]:
    """Convert a frontend linking summary to its stable JSON-ready shape."""

    if not isinstance(summary, FrontendLinkingSummary):
        raise TypeError("summary must be a FrontendLinkingSummary")
    return summary.to_dict()


def _validate_relationships(
    relationships: Iterable[FrontendRelationship],
) -> tuple[FrontendRelationship, ...]:
    if isinstance(relationships, (str, bytes)):
        raise TypeError(
            "relationships must be an iterable of FrontendRelationship values"
        )
    try:
        values = tuple(relationships)
    except TypeError as error:
        raise TypeError(
            "relationships must be an iterable of FrontendRelationship values"
        ) from error
    if not all(isinstance(value, FrontendRelationship) for value in values):
        raise TypeError("relationships must contain only FrontendRelationship values")
    return values


def _count_values(values: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return {key: counts[key] for key in sorted(counts)}


def _validate_nonnegative_integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value
