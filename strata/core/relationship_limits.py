"""Deterministic bounding helpers for relationship extraction output.

L3 keeps frontend/backend relationship payloads from growing without bound.
It operates only on already-created relationship records and does not scan
repositories, read files, call extractors, or change context artifacts.
"""

import json
from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Iterable, Mapping

from strata.core.performance_budget import MAX_RELATIONSHIP_RECORDS


RELATIONSHIP_LIMIT_PROFILE_VERSION = 1

MAX_TOTAL_RELATIONSHIPS = MAX_RELATIONSHIP_RECORDS
MAX_RELATIONSHIPS_PER_SOURCE = 100
MAX_RELATIONSHIPS_PER_TARGET = 100
MAX_RELATIONSHIPS_PER_FRAMEWORK = 1_000
MAX_RELATIONSHIPS_PER_TYPE = 1_000
MAX_WARNINGS = 10
MAX_DUPLICATE_RECORDS = 20
MAX_ROUTE_PATHS = 500
MAX_SUMMARY_PAYLOAD_RELATIONSHIPS = 250

RELATIONSHIP_LIMIT_STATUS_PASS = "pass"
RELATIONSHIP_LIMIT_STATUS_WARN = "warn"
RELATIONSHIP_LIMIT_STATUS_FAIL = "fail"
RELATIONSHIP_LIMIT_STATUSES = (
    RELATIONSHIP_LIMIT_STATUS_PASS,
    RELATIONSHIP_LIMIT_STATUS_WARN,
    RELATIONSHIP_LIMIT_STATUS_FAIL,
)

DROP_REASON_TOTAL_RELATIONSHIP_LIMIT = "total_relationship_limit"
DROP_REASON_PER_SOURCE_LIMIT = "per_source_limit"
DROP_REASON_PER_TARGET_LIMIT = "per_target_limit"
DROP_REASON_PER_FRAMEWORK_LIMIT = "per_framework_limit"
DROP_REASON_PER_TYPE_LIMIT = "per_type_limit"
DROP_REASON_MALFORMED_RELATIONSHIP = "malformed_relationship"
DROP_REASON_SUMMARY_PAYLOAD_LIMIT = "summary_payload_limit"
DROP_REASON_ROUTE_PATH_LIMIT = "route_path_limit"
RELATIONSHIP_DROP_REASONS = (
    DROP_REASON_TOTAL_RELATIONSHIP_LIMIT,
    DROP_REASON_PER_SOURCE_LIMIT,
    DROP_REASON_PER_TARGET_LIMIT,
    DROP_REASON_PER_FRAMEWORK_LIMIT,
    DROP_REASON_PER_TYPE_LIMIT,
    DROP_REASON_MALFORMED_RELATIONSHIP,
    DROP_REASON_SUMMARY_PAYLOAD_LIMIT,
    DROP_REASON_ROUTE_PATH_LIMIT,
)

RELATIONSHIP_FIELD_ORDER = (
    "framework",
    "relationship_type",
    "source_path",
    "target_path",
    "route_path",
    "http_method",
    "target_symbol",
    "handler_symbol",
    "service_symbol",
    "model_symbol",
    "confidence",
    "evidence",
    "warnings",
    "reason",
)


@dataclass(frozen=True, slots=True)
class RelationshipLimitProfile:
    profile_version: int = RELATIONSHIP_LIMIT_PROFILE_VERSION
    profile_name: str = "default"
    max_total_relationships: int = MAX_TOTAL_RELATIONSHIPS
    max_relationships_per_source: int = MAX_RELATIONSHIPS_PER_SOURCE
    max_relationships_per_target: int = MAX_RELATIONSHIPS_PER_TARGET
    max_relationships_per_framework: int = MAX_RELATIONSHIPS_PER_FRAMEWORK
    max_relationships_per_type: int = MAX_RELATIONSHIPS_PER_TYPE
    max_warnings: int = MAX_WARNINGS
    max_duplicate_records: int = MAX_DUPLICATE_RECORDS
    max_route_paths: int = MAX_ROUTE_PATHS
    max_summary_payload_relationships: int = MAX_SUMMARY_PAYLOAD_RELATIONSHIPS

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "profile_version",
            _validate_nonnegative_integer(self.profile_version, "profile_version"),
        )
        object.__setattr__(
            self,
            "profile_name",
            _validate_nonempty_string(self.profile_name, "profile_name"),
        )
        for field_name in (
            "max_total_relationships",
            "max_relationships_per_source",
            "max_relationships_per_target",
            "max_relationships_per_framework",
            "max_relationships_per_type",
            "max_warnings",
            "max_duplicate_records",
            "max_route_paths",
            "max_summary_payload_relationships",
        ):
            object.__setattr__(
                self,
                field_name,
                _validate_nonnegative_integer(getattr(self, field_name), field_name),
            )

    def to_dict(self) -> dict[str, int | str]:
        """Return the stable JSON-ready limit profile."""

        return {
            "profile_version": self.profile_version,
            "profile_name": self.profile_name,
            "max_total_relationships": self.max_total_relationships,
            "max_relationships_per_source": self.max_relationships_per_source,
            "max_relationships_per_target": self.max_relationships_per_target,
            "max_relationships_per_framework": self.max_relationships_per_framework,
            "max_relationships_per_type": self.max_relationships_per_type,
            "max_warnings": self.max_warnings,
            "max_duplicate_records": self.max_duplicate_records,
            "max_route_paths": self.max_route_paths,
            "max_summary_payload_relationships": self.max_summary_payload_relationships,
        }


def default_relationship_limit_profile() -> dict[str, int | str]:
    """Return a fresh JSON-ready copy of the default relationship limits."""

    return DEFAULT_RELATIONSHIP_LIMIT_PROFILE.to_dict()


def normalize_relationship_payload(relationship: Any) -> dict[str, Any]:
    """Normalize one dict/object/dataclass-like relationship into stable fields."""

    source = _relationship_to_mapping(relationship)
    source_path = _normalize_required_path(source.get("source_path"), "source_path")
    target_path = _normalize_optional_path(source.get("target_path"), "target_path")

    return {
        "framework": _normalize_optional_text(source.get("framework")) or "unknown",
        "relationship_type": (
            _normalize_optional_text(source.get("relationship_type")) or "unknown"
        ),
        "source_path": source_path,
        "target_path": target_path,
        "route_path": _normalize_optional_text(source.get("route_path")),
        "http_method": _normalize_optional_text(source.get("http_method")) or "unknown",
        "target_symbol": _normalize_optional_text(source.get("target_symbol")),
        "handler_symbol": _normalize_optional_text(source.get("handler_symbol")),
        "service_symbol": _normalize_optional_text(source.get("service_symbol")),
        "model_symbol": _normalize_optional_text(source.get("model_symbol")),
        "confidence": _normalize_optional_text(source.get("confidence")) or "unknown",
        "evidence": _normalize_text_items(source.get("evidence")),
        "warnings": _normalize_text_items(source.get("warnings")),
        "reason": _normalize_optional_text(source.get("reason")) or "",
    }


def sort_relationship_payloads(relationships: Iterable[Any]) -> list[dict[str, Any]]:
    """Normalize and return relationships in deterministic order."""

    normalized = [normalize_relationship_payload(item) for item in _validate_iterable(relationships)]
    return sorted(normalized, key=_relationship_sort_key)


def apply_relationship_limits(
    relationships: Iterable[Any],
    profile: RelationshipLimitProfile | None = None,
) -> dict[str, Any]:
    """Apply deterministic relationship output limits to existing payloads."""

    resolved_profile = _resolve_profile(profile)
    normalized: list[dict[str, Any]] = []
    malformed_count = 0
    malformed_warnings: list[str] = []

    for index, relationship in enumerate(_validate_iterable(relationships)):
        try:
            normalized.append(normalize_relationship_payload(relationship))
        except (TypeError, ValueError) as error:
            malformed_count += 1
            malformed_warnings.append(f"relationship[{index}] malformed: {error}")

    ordered = sorted(normalized, key=_relationship_sort_key)
    duplicate_summary = count_duplicate_relationships(
        ordered,
        max_records=resolved_profile.max_duplicate_records,
    )
    kept: list[dict[str, Any]] = []
    drop_reasons = {reason: 0 for reason in RELATIONSHIP_DROP_REASONS}
    if malformed_count:
        drop_reasons[DROP_REASON_MALFORMED_RELATIONSHIP] = malformed_count

    counts_by_source: dict[str, int] = {}
    counts_by_target: dict[str, int] = {}
    counts_by_framework: dict[str, int] = {}
    counts_by_type: dict[str, int] = {}
    route_paths: set[str] = set()

    for relationship in ordered:
        drop_reason = _first_limit_drop_reason(
            relationship,
            kept_count=len(kept),
            counts_by_source=counts_by_source,
            counts_by_target=counts_by_target,
            counts_by_framework=counts_by_framework,
            counts_by_type=counts_by_type,
            route_paths=route_paths,
            profile=resolved_profile,
        )
        if drop_reason is not None:
            drop_reasons[drop_reason] += 1
            continue

        kept.append(relationship)
        source = relationship["source_path"]
        target = relationship.get("target_path") or "unknown"
        framework = relationship.get("framework") or "unknown"
        relationship_type = relationship.get("relationship_type") or "unknown"
        counts_by_source[source] = counts_by_source.get(source, 0) + 1
        counts_by_target[target] = counts_by_target.get(target, 0) + 1
        counts_by_framework[framework] = counts_by_framework.get(framework, 0) + 1
        counts_by_type[relationship_type] = counts_by_type.get(relationship_type, 0) + 1
        if relationship.get("route_path"):
            route_paths.add(str(relationship["route_path"]))

    warnings = _build_warnings(
        drop_reasons,
        duplicate_summary,
        malformed_warnings,
        max_warnings=resolved_profile.max_warnings,
    )
    total_input_count = len(ordered) + malformed_count
    total_kept_count = len(kept)

    return {
        "kept_relationships": kept,
        "dropped_relationships_count": total_input_count - total_kept_count,
        "total_input_count": total_input_count,
        "total_kept_count": total_kept_count,
        "status": _status_for(drop_reasons),
        "warnings": warnings,
        "limit_profile": resolved_profile.to_dict(),
        "counts_by_source": _sorted_count_map(counts_by_source),
        "counts_by_framework": _sorted_count_map(counts_by_framework),
        "counts_by_type": _sorted_count_map(counts_by_type),
        "drop_reasons": _sorted_drop_reasons(drop_reasons),
        "duplicate_relationship_count": duplicate_summary["duplicate_count"],
        "duplicate_records": duplicate_summary["duplicate_records"],
        "duplicate_records_truncated_count": duplicate_summary["truncated_count"],
    }


def bound_relationship_warnings(
    warnings: Iterable[str],
    *,
    max_warnings: int = MAX_WARNINGS,
) -> list[str]:
    """Return warnings capped to a stable maximum with a truncation marker."""

    limit = _validate_nonnegative_integer(max_warnings, "max_warnings")
    normalized = [_validate_nonempty_string(item, "warning") for item in warnings]
    if len(normalized) <= limit:
        return normalized
    if limit == 0:
        return []
    kept = normalized[:limit]
    kept[-1] = f"...and {len(normalized) - limit + 1} more warnings"
    return kept


def count_duplicate_relationships(
    relationships: Iterable[Any],
    *,
    max_records: int = MAX_DUPLICATE_RECORDS,
) -> dict[str, Any]:
    """Count exact duplicate normalized relationship payloads deterministically."""

    limit = _validate_nonnegative_integer(max_records, "max_records")
    counts: dict[str, int] = {}
    payloads: dict[str, dict[str, Any]] = {}
    for relationship in sort_relationship_payloads(relationships):
        payload = _stable_payload(relationship)
        counts[payload] = counts.get(payload, 0) + 1
        payloads.setdefault(payload, relationship)

    duplicate_records = [
        {
            "count": counts[payload],
            "relationship": payloads[payload],
        }
        for payload in sorted(counts)
        if counts[payload] > 1
    ]
    duplicate_count = sum(record["count"] - 1 for record in duplicate_records)
    bounded = duplicate_records[:limit]
    return {
        "duplicate_count": duplicate_count,
        "duplicate_record_count": len(duplicate_records),
        "duplicate_records": bounded,
        "truncated_count": max(0, len(duplicate_records) - len(bounded)),
    }


def bound_relationship_summary_payload(
    relationships: Iterable[Any],
    profile: RelationshipLimitProfile | None = None,
) -> dict[str, Any]:
    """Bound already-created relationship payloads for compact summaries."""

    resolved_profile = _resolve_profile(profile)
    ordered = sort_relationship_payloads(relationships)
    limit = resolved_profile.max_summary_payload_relationships
    kept = ordered[:limit]
    dropped = len(ordered) - len(kept)
    warnings = []
    if dropped:
        warnings.append(
            "summary_payload_limit dropped "
            f"{dropped} relationships after {limit} kept"
        )
    return {
        "relationships": kept,
        "total_input_count": len(ordered),
        "total_kept_count": len(kept),
        "dropped_relationships_count": dropped,
        "drop_reasons": {
            DROP_REASON_SUMMARY_PAYLOAD_LIMIT: dropped,
        },
        "warnings": bound_relationship_warnings(
            warnings,
            max_warnings=resolved_profile.max_warnings,
        ),
    }


def _first_limit_drop_reason(
    relationship: dict[str, Any],
    *,
    kept_count: int,
    counts_by_source: dict[str, int],
    counts_by_target: dict[str, int],
    counts_by_framework: dict[str, int],
    counts_by_type: dict[str, int],
    route_paths: set[str],
    profile: RelationshipLimitProfile,
) -> str | None:
    if kept_count >= profile.max_total_relationships:
        return DROP_REASON_TOTAL_RELATIONSHIP_LIMIT
    if kept_count >= profile.max_summary_payload_relationships:
        return DROP_REASON_SUMMARY_PAYLOAD_LIMIT

    source = relationship["source_path"]
    target = relationship.get("target_path") or "unknown"
    framework = relationship.get("framework") or "unknown"
    relationship_type = relationship.get("relationship_type") or "unknown"
    route_path = relationship.get("route_path")

    if counts_by_source.get(source, 0) >= profile.max_relationships_per_source:
        return DROP_REASON_PER_SOURCE_LIMIT
    if counts_by_target.get(target, 0) >= profile.max_relationships_per_target:
        return DROP_REASON_PER_TARGET_LIMIT
    if counts_by_framework.get(framework, 0) >= profile.max_relationships_per_framework:
        return DROP_REASON_PER_FRAMEWORK_LIMIT
    if counts_by_type.get(relationship_type, 0) >= profile.max_relationships_per_type:
        return DROP_REASON_PER_TYPE_LIMIT
    if (
        route_path
        and route_path not in route_paths
        and len(route_paths) >= profile.max_route_paths
    ):
        return DROP_REASON_ROUTE_PATH_LIMIT
    return None


def _status_for(drop_reasons: dict[str, int]) -> str:
    if drop_reasons.get(DROP_REASON_MALFORMED_RELATIONSHIP, 0):
        return RELATIONSHIP_LIMIT_STATUS_FAIL
    if any(count > 0 for count in drop_reasons.values()):
        return RELATIONSHIP_LIMIT_STATUS_WARN
    return RELATIONSHIP_LIMIT_STATUS_PASS


def _build_warnings(
    drop_reasons: dict[str, int],
    duplicate_summary: dict[str, Any],
    malformed_warnings: list[str],
    *,
    max_warnings: int,
) -> list[str]:
    warnings: list[str] = []
    warnings.extend(malformed_warnings)
    for reason in RELATIONSHIP_DROP_REASONS:
        count = drop_reasons.get(reason, 0)
        if count:
            warnings.append(f"{reason} dropped {count} relationship records")
    duplicate_count = int(duplicate_summary.get("duplicate_count", 0) or 0)
    if duplicate_count:
        warnings.append(f"duplicate_relationships found {duplicate_count} extra records")
    return bound_relationship_warnings(warnings, max_warnings=max_warnings)


def _relationship_to_mapping(relationship: Any) -> Mapping[str, Any]:
    if isinstance(relationship, Mapping):
        return relationship
    to_dict = getattr(relationship, "to_dict", None)
    if callable(to_dict):
        payload = to_dict()
        if not isinstance(payload, Mapping):
            raise TypeError("relationship.to_dict() must return a mapping")
        return payload

    values: dict[str, Any] = {}
    for field_name in RELATIONSHIP_FIELD_ORDER:
        if hasattr(relationship, field_name):
            values[field_name] = getattr(relationship, field_name)
    if not values:
        raise TypeError("relationship must be a mapping or relationship-like object")
    return values


def _relationship_sort_key(relationship: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        relationship.get("source_path") or "",
        relationship.get("target_path") or "",
        relationship.get("route_path") or "",
        relationship.get("relationship_type") or "",
        relationship.get("framework") or "",
        relationship.get("http_method") or "",
        relationship.get("target_symbol") or "",
        relationship.get("handler_symbol") or "",
        relationship.get("service_symbol") or "",
        relationship.get("model_symbol") or "",
        relationship.get("confidence") or "",
        relationship.get("reason") or "",
        tuple(relationship.get("evidence") or ()),
        tuple(relationship.get("warnings") or ()),
    )


def _stable_payload(relationship: Mapping[str, Any]) -> str:
    return json.dumps(relationship, sort_keys=True, separators=(",", ":"))


def _sorted_count_map(counts: dict[str, int]) -> dict[str, int]:
    return {key: counts[key] for key in sorted(counts)}


def _sorted_drop_reasons(drop_reasons: dict[str, int]) -> dict[str, int]:
    return {reason: drop_reasons.get(reason, 0) for reason in RELATIONSHIP_DROP_REASONS}


def _resolve_profile(
    profile: RelationshipLimitProfile | None,
) -> RelationshipLimitProfile:
    if profile is None:
        return DEFAULT_RELATIONSHIP_LIMIT_PROFILE
    if not isinstance(profile, RelationshipLimitProfile):
        raise TypeError("profile must be a RelationshipLimitProfile")
    return profile


def _validate_iterable(relationships: Iterable[Any]) -> tuple[Any, ...]:
    if isinstance(relationships, (str, bytes)):
        raise TypeError("relationships must be an iterable of relationship records")
    try:
        return tuple(relationships)
    except TypeError as error:
        raise TypeError(
            "relationships must be an iterable of relationship records"
        ) from error


def _normalize_required_path(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    text = value.strip()
    if not text:
        raise ValueError(f"{name} must be a non-empty relative path")
    if text != value or "\x00" in text:
        raise ValueError(f"{name} must not contain whitespace padding or null bytes")
    windows_path = PureWindowsPath(text)
    posix_path = PurePosixPath(text.replace("\\", "/"))
    if posix_path.is_absolute() or windows_path.is_absolute() or windows_path.drive:
        raise ValueError(f"{name} must be relative")
    if ".." in posix_path.parts:
        raise ValueError(f"{name} must not escape its root with '..'")
    normalized = posix_path.as_posix()
    if normalized in ("", "."):
        raise ValueError(f"{name} must identify a repository file")
    return normalized


def _normalize_optional_path(value: Any, name: str) -> str | None:
    if value is None:
        return None
    return _normalize_required_path(value, name)


def _normalize_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("relationship text fields must be strings or None")
    text = value.strip()
    if text != value:
        raise ValueError("relationship text fields must not have surrounding whitespace")
    return text or None


def _normalize_text_items(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (str, bytes)):
        raise TypeError("relationship text item fields must be iterables of strings")
    try:
        items = list(value)
    except TypeError as error:
        raise TypeError(
            "relationship text item fields must be iterables of strings"
        ) from error
    normalized = [_validate_nonempty_string(item, "relationship text item") for item in items]
    return sorted(set(normalized))


def _validate_nonempty_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    if value != value.strip():
        raise ValueError(f"{name} must not have surrounding whitespace")
    return value


def _validate_nonnegative_integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value


DEFAULT_RELATIONSHIP_LIMIT_PROFILE = RelationshipLimitProfile()
