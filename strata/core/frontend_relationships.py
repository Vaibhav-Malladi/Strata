"""Stable frontend relationship contracts without discovery or parsing.

J1 defines bounded vocabulary and JSON-ready shapes that later frontend deep
linking batches can populate. Evidence values are repository-derived and must
remain untrusted if rendered into prompts by a later stage.
"""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Iterable


class FrontendRelationshipType(StrEnum):
    """Supported frontend relationship categories for later producers."""

    COMPONENT_TEMPLATE = "component_template"
    COMPONENT_STYLE = "component_style"
    COMPONENT_TEST = "component_test"
    COMPONENT_ROUTE = "component_route"
    ROUTE_LAZY_TARGET = "route_lazy_target"
    COMPONENT_CHILD_COMPONENT = "component_child_component"
    COMPONENT_SERVICE = "component_service"
    COMPONENT_API_CLIENT = "component_api_client"
    HOOK_COMPONENT = "hook_component"
    HOOK_API_CLIENT = "hook_api_client"
    REACT_ROUTE_COMPONENT = "react_route_component"
    INTERNAL_LIBRARY_USAGE = "internal_library_usage"
    MODULE_FEDERATION_REMOTE = "module_federation_remote"
    CUSTOM_ELEMENT_USAGE = "custom_element_usage"


class FrontendFramework(StrEnum):
    """Frontend framework labels used by relationship producers."""

    ANGULAR = "angular"
    REACT = "react"
    GENERIC_FRONTEND = "generic_frontend"
    UNKNOWN = "unknown"


class FrontendRelationshipConfidence(StrEnum):
    """Bounded confidence labels for one relationship observation."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


RELATIONSHIP_TYPES = tuple(value.value for value in FrontendRelationshipType)
FRONTEND_FRAMEWORKS = tuple(value.value for value in FrontendFramework)
RELATIONSHIP_CONFIDENCES = tuple(
    value.value for value in FrontendRelationshipConfidence
)

ANGULAR_RELATIONSHIP_PLACEHOLDERS = (
    FrontendRelationshipType.COMPONENT_TEMPLATE.value,
    FrontendRelationshipType.COMPONENT_STYLE.value,
    FrontendRelationshipType.COMPONENT_TEST.value,
    FrontendRelationshipType.COMPONENT_ROUTE.value,
    FrontendRelationshipType.ROUTE_LAZY_TARGET.value,
    FrontendRelationshipType.COMPONENT_CHILD_COMPONENT.value,
    FrontendRelationshipType.COMPONENT_SERVICE.value,
    FrontendRelationshipType.COMPONENT_API_CLIENT.value,
)
REACT_RELATIONSHIP_PLACEHOLDERS = (
    FrontendRelationshipType.HOOK_COMPONENT.value,
    FrontendRelationshipType.HOOK_API_CLIENT.value,
    FrontendRelationshipType.REACT_ROUTE_COMPONENT.value,
    FrontendRelationshipType.COMPONENT_CHILD_COMPONENT.value,
    FrontendRelationshipType.COMPONENT_API_CLIENT.value,
    FrontendRelationshipType.COMPONENT_TEST.value,
)
INTERNAL_LIBRARY_RELATIONSHIP_PLACEHOLDERS = (
    FrontendRelationshipType.INTERNAL_LIBRARY_USAGE.value,
)
MODULE_FEDERATION_RELATIONSHIP_PLACEHOLDERS = (
    FrontendRelationshipType.MODULE_FEDERATION_REMOTE.value,
)
CUSTOM_ELEMENT_RELATIONSHIP_PLACEHOLDERS = (
    FrontendRelationshipType.CUSTOM_ELEMENT_USAGE.value,
)


@dataclass(frozen=True, slots=True)
class FrontendRelationship:
    """One immutable, JSON-ready frontend relationship observation."""

    framework: str
    source_path: str
    relationship_type: str
    confidence: str
    reason: str
    target_path: str | None = None
    target_symbol: str | None = None
    evidence: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "framework",
            _validate_choice(self.framework, "framework", FRONTEND_FRAMEWORKS),
        )
        object.__setattr__(
            self, "source_path", normalize_relative_path(self.source_path)
        )
        object.__setattr__(
            self,
            "target_path",
            _normalize_optional_path(self.target_path, "target_path"),
        )
        object.__setattr__(
            self,
            "target_symbol",
            _validate_optional_text(self.target_symbol, "target_symbol"),
        )
        if self.target_path is None and self.target_symbol is None:
            raise ValueError("target_path or target_symbol must be provided")
        object.__setattr__(
            self,
            "relationship_type",
            _validate_choice(
                self.relationship_type,
                "relationship_type",
                RELATIONSHIP_TYPES,
            ),
        )
        object.__setattr__(
            self,
            "confidence",
            _validate_choice(
                self.confidence,
                "confidence",
                RELATIONSHIP_CONFIDENCES,
            ),
        )
        object.__setattr__(self, "reason", _validate_text(self.reason, "reason"))
        object.__setattr__(
            self, "evidence", _normalize_text_items(self.evidence, "evidence")
        )
        object.__setattr__(
            self, "warnings", _normalize_text_items(self.warnings, "warnings")
        )

    def to_dict(self) -> dict[str, Any]:
        """Return the stable JSON-ready relationship representation."""

        return {
            "framework": self.framework,
            "source_path": self.source_path,
            "target_path": self.target_path,
            "target_symbol": self.target_symbol,
            "relationship_type": self.relationship_type,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
            "warnings": list(self.warnings),
            "reason": self.reason,
        }


def create_frontend_relationship(
    framework: str,
    source_path: str,
    relationship_type: str,
    confidence: str,
    reason: str,
    target_path: str | None = None,
    target_symbol: str | None = None,
    evidence: Iterable[str] = (),
    warnings: Iterable[str] = (),
) -> FrontendRelationship:
    """Create and validate one frontend relationship contract value."""

    return FrontendRelationship(
        framework=framework,
        source_path=source_path,
        target_path=target_path,
        target_symbol=target_symbol,
        relationship_type=relationship_type,
        confidence=confidence,
        evidence=tuple(evidence),
        warnings=tuple(warnings),
        reason=reason,
    )


def frontend_relationship_to_dict(
    relationship: FrontendRelationship,
) -> dict[str, Any]:
    """Convert a frontend relationship to its stable JSON-ready shape."""

    if not isinstance(relationship, FrontendRelationship):
        raise TypeError("relationship must be a FrontendRelationship")
    return relationship.to_dict()


def sort_frontend_relationships(
    relationships: Iterable[FrontendRelationship],
) -> tuple[FrontendRelationship, ...]:
    """Return relationships in deterministic order."""

    values = _validate_relationships(relationships)
    return tuple(sorted(values, key=_relationship_sort_key))


def merge_frontend_relationships(
    relationships: Iterable[FrontendRelationship],
) -> tuple[FrontendRelationship, ...]:
    """Remove exactly identical relationships and return deterministic order."""

    return sort_frontend_relationships(set(_validate_relationships(relationships)))


def group_relationships_by_source_path(
    relationships: Iterable[FrontendRelationship],
) -> dict[str, tuple[FrontendRelationship, ...]]:
    """Group relationships by source path using deterministic group order."""

    return _group_relationships(relationships, lambda item: item.source_path)


def group_relationships_by_type(
    relationships: Iterable[FrontendRelationship],
) -> dict[str, tuple[FrontendRelationship, ...]]:
    """Group relationships by relationship type using deterministic group order."""

    return _group_relationships(relationships, lambda item: item.relationship_type)


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


def _group_relationships(
    relationships: Iterable[FrontendRelationship],
    key_function,
) -> dict[str, tuple[FrontendRelationship, ...]]:
    groups: dict[str, list[FrontendRelationship]] = {}
    for relationship in sort_frontend_relationships(relationships):
        groups.setdefault(key_function(relationship), []).append(relationship)
    return {key: tuple(groups[key]) for key in sorted(groups)}


def _relationship_sort_key(relationship: FrontendRelationship) -> tuple[Any, ...]:
    return (
        relationship.source_path,
        relationship.relationship_type,
        relationship.target_path or "",
        relationship.target_symbol or "",
        relationship.framework,
        relationship.confidence,
        relationship.reason,
        relationship.evidence,
        relationship.warnings,
    )


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


def _validate_choice(value: Any, name: str, allowed: tuple[str, ...]) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if value not in allowed:
        raise ValueError(f"{name} must be one of: {', '.join(allowed)}")
    return value


def _validate_text(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if not value or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    if value != value.strip() or "\x00" in value:
        raise ValueError(f"{name} must not contain padding or null bytes")
    return value


def _validate_optional_text(value: Any, name: str) -> str | None:
    if value is None:
        return None
    return _validate_text(value, name)


def _normalize_optional_path(value: Any, name: str) -> str | None:
    if value is None:
        return None
    return normalize_relative_path(value)


def _normalize_text_items(values: Any, name: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{name} must be an iterable of strings")
    try:
        items = tuple(values)
    except TypeError as error:
        raise TypeError(f"{name} must be an iterable of strings") from error
    normalized = (_validate_text(item, f"{name} item") for item in items)
    return tuple(sorted(set(normalized)))
