"""Immutable contracts for classifying internal library resolution evidence.

This module is intentionally filesystem-free.  Producers may populate these
contracts later, but creating, sorting, and merging them performs no discovery.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Iterable


class ResolutionClassification(StrEnum):
    """How a package-style import was resolved, if it was resolved at all."""

    RESOLVED_REPO_SOURCE = "resolved_repo_source"
    RESOLVED_TSCONFIG_ALIAS_SOURCE = "resolved_tsconfig_alias_source"
    RESOLVED_NODE_MODULES_DECLARATION = "resolved_node_modules_declaration"
    RESOLVED_VENDOR_DIRECTORY_DECLARATION = "resolved_vendor_directory_declaration"
    RESOLVED_VENDOR_ZIP_REFERENCE = "resolved_vendor_zip_reference"
    EXTERNAL_PUBLIC_PACKAGE = "external_public_package"
    OPAQUE_PRIVATE_PACKAGE = "opaque_private_package"
    UNRESOLVED_ALIAS = "unresolved_alias"
    MISSING_PACKAGE = "missing_package"


class SourceAvailability(StrEnum):
    """The most useful readable representation available to later stages."""

    SOURCE_AVAILABLE = "source_available"
    DECLARATION_ONLY = "declaration_only"
    ZIP_REFERENCE_ONLY = "zip_reference_only"
    METADATA_ONLY = "metadata_only"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


CLASSIFICATIONS = tuple(value.value for value in ResolutionClassification)
SOURCE_AVAILABILITIES = tuple(value.value for value in SourceAvailability)
VERSION_CONFIDENCES = ("unknown", "low", "medium", "high")
VERSION_CONFIDENCE_AFFECTS_RANKING = False


@dataclass(frozen=True, slots=True)
class LibraryVersionMetadata:
    """Optional package version evidence; confidence is metadata only."""

    version: str | None = None
    version_source: str | None = None
    version_confidence: str = "unknown"

    def __post_init__(self) -> None:
        object.__setattr__(self, "version", _validate_optional_text(self.version, "version"))
        object.__setattr__(
            self,
            "version_source",
            _validate_optional_text(self.version_source, "version_source"),
        )
        object.__setattr__(
            self,
            "version_confidence",
            _validate_choice(
                self.version_confidence, "version_confidence", VERSION_CONFIDENCES
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "version_source": self.version_source,
            "version_confidence": self.version_confidence,
        }


@dataclass(frozen=True, slots=True)
class LibraryResolutionEvidence:
    """Bounded paths and notes supporting one library classification."""

    import_paths: tuple[str, ...] = ()
    resolved_path: str | None = None
    package_json_path: str | None = None
    declaration_paths: tuple[str, ...] = ()
    vendor_path: str | None = None
    archive_path: str | None = None
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "import_paths", _normalize_text_items(self.import_paths, "import_paths")
        )
        for name in (
            "resolved_path",
            "package_json_path",
            "vendor_path",
            "archive_path",
        ):
            object.__setattr__(
                self, name, _normalize_optional_path(getattr(self, name), name)
            )
        object.__setattr__(
            self,
            "declaration_paths",
            _normalize_paths(self.declaration_paths, "declaration_paths"),
        )
        object.__setattr__(self, "notes", _normalize_text_items(self.notes, "notes"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "import_paths": list(self.import_paths),
            "resolved_path": self.resolved_path,
            "package_json_path": self.package_json_path,
            "declaration_paths": list(self.declaration_paths),
            "vendor_path": self.vendor_path,
            "archive_path": self.archive_path,
            "notes": list(self.notes),
        }


@dataclass(frozen=True, slots=True)
class LibraryResolutionSafety:
    """Bounded work accounting supplied by a future resolution producer."""

    files_inspected: int = 0
    bytes_read: int = 0
    skipped_items: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "files_inspected", _validate_count(self.files_inspected, "files_inspected")
        )
        object.__setattr__(self, "bytes_read", _validate_count(self.bytes_read, "bytes_read"))
        object.__setattr__(
            self,
            "skipped_items",
            _normalize_text_items(self.skipped_items, "skipped_items"),
        )
        object.__setattr__(
            self, "warnings", _normalize_text_items(self.warnings, "warnings")
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "files_inspected": self.files_inspected,
            "bytes_read": self.bytes_read,
            "skipped_items": list(self.skipped_items),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class InternalLibraryResolution:
    """One JSON-ready library resolution result for later Strata stages."""

    library_name: str
    classification: str
    source_availability: str
    version: LibraryVersionMetadata = field(default_factory=LibraryVersionMetadata)
    evidence: LibraryResolutionEvidence = field(default_factory=LibraryResolutionEvidence)
    safety: LibraryResolutionSafety = field(default_factory=LibraryResolutionSafety)
    context_paths: tuple[str, ...] = ()
    usage_inference_required: bool = False
    diagnostic_notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "library_name", normalize_package_name(self.library_name))
        object.__setattr__(
            self,
            "classification",
            validate_classification(self.classification),
        )
        object.__setattr__(
            self,
            "source_availability",
            validate_source_availability(self.source_availability),
        )
        if not isinstance(self.version, LibraryVersionMetadata):
            raise TypeError("version must be LibraryVersionMetadata")
        if not isinstance(self.evidence, LibraryResolutionEvidence):
            raise TypeError("evidence must be LibraryResolutionEvidence")
        if not isinstance(self.safety, LibraryResolutionSafety):
            raise TypeError("safety must be LibraryResolutionSafety")
        object.__setattr__(
            self, "context_paths", _normalize_paths(self.context_paths, "context_paths")
        )
        if not isinstance(self.usage_inference_required, bool):
            raise TypeError("usage_inference_required must be a boolean")
        object.__setattr__(
            self,
            "diagnostic_notes",
            _normalize_text_items(self.diagnostic_notes, "diagnostic_notes"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return the deterministic JSON-ready representation."""

        return {
            "library_name": self.library_name,
            "classification": self.classification,
            "source_availability": self.source_availability,
            "version": self.version.to_dict(),
            "evidence": self.evidence.to_dict(),
            "safety": self.safety.to_dict(),
            "context_paths": list(self.context_paths),
            "usage_inference_required": self.usage_inference_required,
            "diagnostic_notes": list(self.diagnostic_notes),
        }


def normalize_package_name(import_name: str) -> str:
    """Return the npm package root for a package import or package subpath."""

    value = _validate_text(import_name, "import_name").replace("\\", "/")
    if value.startswith((".", "/")) or "//" in value:
        raise ValueError("import_name must be a package-style import")
    parts = value.split("/")
    if value.startswith("@"):
        if len(parts) < 2 or not parts[0][1:] or not parts[1]:
            raise ValueError("scoped import_name must include scope and package")
        return "/".join(parts[:2])
    if not parts[0]:
        raise ValueError("import_name must identify a package")
    return parts[0]


def validate_classification(value: str) -> str:
    """Validate and return a supported resolution classification."""

    return _validate_choice(value, "classification", CLASSIFICATIONS)


def validate_source_availability(value: str) -> str:
    """Validate and return a supported source-availability value."""

    return _validate_choice(value, "source_availability", SOURCE_AVAILABILITIES)


def sort_resolution_results(
    results: Iterable[InternalLibraryResolution],
) -> tuple[InternalLibraryResolution, ...]:
    """Sort results deterministically without using version confidence."""

    values = _validate_results(results)
    return tuple(sorted(values, key=_resolution_sort_key))


def dedupe_resolution_results(
    results: Iterable[InternalLibraryResolution],
) -> tuple[InternalLibraryResolution, ...]:
    """Merge duplicate evidence for the same normalized library resolution."""

    groups: dict[tuple[Any, ...], list[InternalLibraryResolution]] = {}
    for result in set(_validate_results(results)):
        groups.setdefault(_resolution_identity_key(result), []).append(result)

    merged = []
    for group in groups.values():
        exemplar = group[0]
        merged.append(
            InternalLibraryResolution(
                library_name=exemplar.library_name,
                classification=exemplar.classification,
                source_availability=exemplar.source_availability,
                version=exemplar.version,
                evidence=LibraryResolutionEvidence(
                    import_paths=_union(item.evidence.import_paths for item in group),
                    resolved_path=exemplar.evidence.resolved_path,
                    package_json_path=exemplar.evidence.package_json_path,
                    declaration_paths=_union(
                        item.evidence.declaration_paths for item in group
                    ),
                    vendor_path=exemplar.evidence.vendor_path,
                    archive_path=exemplar.evidence.archive_path,
                    notes=_union(item.evidence.notes for item in group),
                ),
                safety=LibraryResolutionSafety(
                    files_inspected=sum(item.safety.files_inspected for item in group),
                    bytes_read=sum(item.safety.bytes_read for item in group),
                    skipped_items=_union(
                        item.safety.skipped_items for item in group
                    ),
                    warnings=_union(item.safety.warnings for item in group),
                ),
                context_paths=_union(item.context_paths for item in group),
                usage_inference_required=exemplar.usage_inference_required,
                diagnostic_notes=_union(item.diagnostic_notes for item in group),
            )
        )
    return sort_resolution_results(merged)


def _resolution_identity_key(result: InternalLibraryResolution) -> tuple[Any, ...]:
    """Identify merge-compatible results without using bounded list evidence."""

    return (
        result.library_name,
        result.classification,
        result.source_availability,
        result.version,
        result.evidence.resolved_path,
        result.evidence.package_json_path,
        result.evidence.vendor_path,
        result.evidence.archive_path,
        result.usage_inference_required,
    )


def _resolution_sort_key(result: InternalLibraryResolution) -> tuple[Any, ...]:
    return (
        result.library_name,
        result.classification,
        result.source_availability,
        result.version.version or "",
        result.version.version_source or "",
        result.evidence.import_paths,
        result.evidence.resolved_path or "",
        result.evidence.package_json_path or "",
        result.evidence.declaration_paths,
        result.evidence.vendor_path or "",
        result.evidence.archive_path or "",
        result.evidence.notes,
        result.context_paths,
        result.usage_inference_required,
        result.diagnostic_notes,
        result.safety.files_inspected,
        result.safety.bytes_read,
        result.safety.skipped_items,
        result.safety.warnings,
    )


def _validate_results(
    results: Iterable[InternalLibraryResolution],
) -> tuple[InternalLibraryResolution, ...]:
    if isinstance(results, (str, bytes)):
        raise TypeError("results must be an iterable of InternalLibraryResolution values")
    try:
        values = tuple(results)
    except TypeError as error:
        raise TypeError(
            "results must be an iterable of InternalLibraryResolution values"
        ) from error
    if not all(isinstance(value, InternalLibraryResolution) for value in values):
        raise TypeError("results must contain only InternalLibraryResolution values")
    return values


def _union(groups: Iterable[tuple[str, ...]]) -> tuple[str, ...]:
    return tuple(sorted({item for group in groups for item in group}))


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
    normalized = _validate_optional_text(value, name)
    return None if normalized is None else normalized.replace("\\", "/")


def _normalize_paths(values: Any, name: str) -> tuple[str, ...]:
    items = _normalize_text_items(values, name)
    return tuple(sorted({item.replace("\\", "/") for item in items}))


def _normalize_text_items(values: Any, name: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{name} must be an iterable of strings")
    try:
        items = tuple(values)
    except TypeError as error:
        raise TypeError(f"{name} must be an iterable of strings") from error
    normalized = (_validate_text(item, f"{name} item") for item in items)
    return tuple(sorted(set(normalized)))


def _validate_count(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value
