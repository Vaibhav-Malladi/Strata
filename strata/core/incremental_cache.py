"""Deterministic incremental scan cache primitives.

L2 defines safe cache reuse decisions from supplied metadata only. It does not
read repository files, scan directories, or integrate with live scanner flows.
"""

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Mapping


INCREMENTAL_CACHE_SCHEMA_VERSION = 1
INCREMENTAL_CACHE_VERSION = "incremental-cache-v1"

CACHE_STATUS_HIT = "hit"
CACHE_STATUS_MISS = "miss"
CACHE_STATUS_STALE = "stale"
CACHE_STATUS_INVALID = "invalid"
CACHE_STATUSES = (
    CACHE_STATUS_HIT,
    CACHE_STATUS_MISS,
    CACHE_STATUS_STALE,
    CACHE_STATUS_INVALID,
)

INVALIDATION_MISSING_CACHE = "missing_cache"
INVALIDATION_SCHEMA_MISMATCH = "schema_mismatch"
INVALIDATION_ROOT_CHANGED = "root_changed"
INVALIDATION_SCAN_OPTIONS_CHANGED = "scan_options_changed"
INVALIDATION_INPUT_FINGERPRINT_CHANGED = "input_fingerprint_changed"
INVALIDATION_FILE_COUNT_CHANGED = "file_count_changed"
INVALIDATION_CACHE_TOO_OLD = "cache_too_old"
INVALIDATION_MALFORMED_CACHE_METADATA = "malformed_cache_metadata"
INVALIDATION_REASONS = (
    INVALIDATION_MISSING_CACHE,
    INVALIDATION_SCHEMA_MISMATCH,
    INVALIDATION_ROOT_CHANGED,
    INVALIDATION_SCAN_OPTIONS_CHANGED,
    INVALIDATION_INPUT_FINGERPRINT_CHANGED,
    INVALIDATION_FILE_COUNT_CHANGED,
    INVALIDATION_CACHE_TOO_OLD,
    INVALIDATION_MALFORMED_CACHE_METADATA,
)


@dataclass(frozen=True, slots=True)
class IncrementalCacheMetadata:
    schema_version: int
    cache_version: str
    root_fingerprint: str
    scan_options_fingerprint: str
    file_count: int
    source_file_count: int
    ignored_file_count: int
    created_at: int | float | str
    strata_version: str | None
    language_counts: Mapping[str, int]
    input_fingerprints: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return a stable JSON-ready cache metadata payload."""

        return {
            "schema_version": self.schema_version,
            "cache_version": self.cache_version,
            "root_fingerprint": self.root_fingerprint,
            "scan_options_fingerprint": self.scan_options_fingerprint,
            "file_count": self.file_count,
            "source_file_count": self.source_file_count,
            "ignored_file_count": self.ignored_file_count,
            "created_at": self.created_at,
            "strata_version": self.strata_version,
            "language_counts": {
                key: self.language_counts[key]
                for key in sorted(self.language_counts)
            },
            "input_fingerprints": _thaw_json(self.input_fingerprints),
        }


def fingerprint_scan_inputs(records: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...]) -> dict[str, Any]:
    """Return a deterministic fingerprint for already-known file facts."""

    normalized_records = _normalize_input_records(records)
    digest = _stable_digest(normalized_records)
    return {
        "schema_version": INCREMENTAL_CACHE_SCHEMA_VERSION,
        "record_count": len(normalized_records),
        "digest": digest,
        "records": normalized_records,
    }


def fingerprint_scan_options(scan_options: Mapping[str, Any] | None) -> str:
    """Return a deterministic fingerprint for scan option values."""

    options = {} if scan_options is None else _freeze_json(scan_options, "scan_options")
    return _stable_digest(options)


def build_incremental_cache_metadata(
    *,
    root_fingerprint: str,
    scan_options: Mapping[str, Any] | None,
    input_records: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...],
    created_at: int | float | str,
    source_file_count: int | None = None,
    ignored_file_count: int = 0,
    strata_version: str | None = None,
    schema_version: int = INCREMENTAL_CACHE_SCHEMA_VERSION,
    cache_version: str = INCREMENTAL_CACHE_VERSION,
) -> dict[str, Any]:
    """Build stable cache metadata from caller-supplied scan input facts."""

    root = _validate_nonempty_string(root_fingerprint, "root_fingerprint")
    normalized_schema = _validate_positive_integer(schema_version, "schema_version")
    normalized_cache_version = _validate_nonempty_string(cache_version, "cache_version")
    normalized_ignored_count = _validate_nonnegative_integer(
        ignored_file_count,
        "ignored_file_count",
    )
    input_fingerprints = fingerprint_scan_inputs(input_records)
    inferred_source_count = int(input_fingerprints["record_count"])
    normalized_source_count = (
        inferred_source_count
        if source_file_count is None
        else _validate_nonnegative_integer(source_file_count, "source_file_count")
    )
    metadata = IncrementalCacheMetadata(
        schema_version=normalized_schema,
        cache_version=normalized_cache_version,
        root_fingerprint=root,
        scan_options_fingerprint=fingerprint_scan_options(scan_options),
        file_count=normalized_source_count + normalized_ignored_count,
        source_file_count=normalized_source_count,
        ignored_file_count=normalized_ignored_count,
        created_at=_validate_timestamp_value(created_at, "created_at"),
        strata_version=_validate_optional_string(strata_version, "strata_version"),
        language_counts=_language_counts(input_fingerprints["records"]),
        input_fingerprints=input_fingerprints,
    )
    return metadata.to_dict()


def build_incremental_cache_key(metadata: Mapping[str, Any]) -> str:
    """Return a stable cache key from validated incremental cache metadata."""

    normalized = _normalize_metadata(metadata)
    key_payload = {
        "schema_version": normalized["schema_version"],
        "cache_version": normalized["cache_version"],
        "root_fingerprint": normalized["root_fingerprint"],
        "scan_options_fingerprint": normalized["scan_options_fingerprint"],
        "input_fingerprint_digest": normalized["input_fingerprints"]["digest"],
    }
    return _stable_digest(key_payload)


def decide_incremental_cache_reuse(
    previous_metadata: Mapping[str, Any] | None,
    current_metadata: Mapping[str, Any],
    *,
    current_time: int | float | str | None = None,
    max_age_seconds: int | float | None = None,
) -> dict[str, Any]:
    """Return a JSON-ready decision for reusing previous scan cache data."""

    if previous_metadata is None:
        return _decision(
            reuse=False,
            status=CACHE_STATUS_MISS,
            reasons=[INVALIDATION_MISSING_CACHE],
            warnings=[],
            changed_counts={},
        )

    previous, previous_error = _try_normalize_metadata(previous_metadata)
    current, current_error = _try_normalize_metadata(current_metadata)
    if previous_error or current_error:
        warnings = []
        if previous_error:
            warnings.append(f"previous metadata is malformed: {previous_error}")
        if current_error:
            warnings.append(f"current metadata is malformed: {current_error}")
        return _decision(
            reuse=False,
            status=CACHE_STATUS_INVALID,
            reasons=[INVALIDATION_MALFORMED_CACHE_METADATA],
            warnings=warnings,
            changed_counts={},
        )

    reasons: list[str] = []
    if (
        previous["schema_version"] != current["schema_version"]
        or previous["cache_version"] != current["cache_version"]
    ):
        reasons.append(INVALIDATION_SCHEMA_MISMATCH)
    if previous["root_fingerprint"] != current["root_fingerprint"]:
        reasons.append(INVALIDATION_ROOT_CHANGED)
    if previous["scan_options_fingerprint"] != current["scan_options_fingerprint"]:
        reasons.append(INVALIDATION_SCAN_OPTIONS_CHANGED)
    if previous["input_fingerprints"]["digest"] != current["input_fingerprints"]["digest"]:
        reasons.append(INVALIDATION_INPUT_FINGERPRINT_CHANGED)
    if previous["file_count"] != current["file_count"]:
        reasons.append(INVALIDATION_FILE_COUNT_CHANGED)
    if _ttl_expired_for_decision(
        previous["created_at"],
        current_time=current_time,
        max_age_seconds=max_age_seconds,
    ):
        reasons.append(INVALIDATION_CACHE_TOO_OLD)

    changed_counts = _changed_counts(previous, current)
    if reasons:
        return _decision(
            reuse=False,
            status=CACHE_STATUS_STALE,
            reasons=reasons,
            warnings=[],
            changed_counts=changed_counts,
        )

    return _decision(
        reuse=True,
        status=CACHE_STATUS_HIT,
        reasons=[],
        warnings=[],
        changed_counts=changed_counts,
    )


def is_cache_metadata_expired(
    *,
    created_at: int | float | str,
    current_time: int | float | str,
    max_age_seconds: int | float,
) -> bool:
    """Return whether a cache entry is expired using supplied timestamps only."""

    max_age = _validate_nonnegative_number(max_age_seconds, "max_age_seconds")
    created_seconds = _timestamp_to_seconds(created_at, "created_at")
    current_seconds = _timestamp_to_seconds(current_time, "current_time")
    return current_seconds - created_seconds > max_age


def summarize_incremental_cache_diagnostics(
    metadata: Mapping[str, Any] | None,
    decision: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Return deterministic cache diagnostics for UI or report layers."""

    normalized_metadata, metadata_error = _try_normalize_metadata(metadata)
    decision_data = decision if isinstance(decision, Mapping) else {}

    status = str(decision_data.get("status") or CACHE_STATUS_INVALID)
    reasons = _string_list(decision_data.get("reasons"))
    warnings = _string_list(decision_data.get("warnings"))
    if metadata_error:
        status = CACHE_STATUS_INVALID
        reasons = [INVALIDATION_MALFORMED_CACHE_METADATA]
        warnings = [f"metadata is malformed: {metadata_error}"]
        normalized_metadata = None

    return {
        "status": status,
        "reuse": bool(decision_data.get("reuse")) if not metadata_error else False,
        "reason_count": len(reasons),
        "reasons": reasons,
        "warning_count": len(warnings),
        "warnings": warnings,
        "schema_version": (
            normalized_metadata["schema_version"] if normalized_metadata else None
        ),
        "cache_version": (
            normalized_metadata["cache_version"] if normalized_metadata else None
        ),
        "file_count": normalized_metadata["file_count"] if normalized_metadata else 0,
        "source_file_count": (
            normalized_metadata["source_file_count"] if normalized_metadata else 0
        ),
        "ignored_file_count": (
            normalized_metadata["ignored_file_count"] if normalized_metadata else 0
        ),
        "language_counts": (
            normalized_metadata["language_counts"] if normalized_metadata else {}
        ),
    }


def _normalize_input_records(
    records: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...],
) -> list[dict[str, Any]]:
    if isinstance(records, (str, bytes)) or not isinstance(records, (list, tuple)):
        raise TypeError("records must be a list or tuple of mappings")

    normalized_records = [
        _normalize_input_record(record, f"records[{index}]")
        for index, record in enumerate(records)
    ]
    return sorted(
        normalized_records,
        key=lambda record: (
            record["path"],
            record.get("language") or "",
            record.get("content_hash") or "",
            str(record.get("mtime_ns") or ""),
            str(record.get("modified_at") or ""),
            record.get("size") if record.get("size") is not None else -1,
        ),
    )


def _normalize_input_record(record: Mapping[str, Any], location: str) -> dict[str, Any]:
    if not isinstance(record, Mapping):
        raise TypeError(f"{location} must be a mapping")

    result: dict[str, Any] = {
        "path": _normalize_relative_path(record.get("path"), f"{location}.path"),
    }
    if "size" in record and record.get("size") is not None:
        result["size"] = _validate_nonnegative_integer(
            record.get("size"),
            f"{location}.size",
        )
    if "mtime_ns" in record and record.get("mtime_ns") is not None:
        result["mtime_ns"] = _validate_nonnegative_integer(
            record.get("mtime_ns"),
            f"{location}.mtime_ns",
        )
    if "modified_at" in record and record.get("modified_at") is not None:
        result["modified_at"] = _validate_timestamp_value(
            record.get("modified_at"),
            f"{location}.modified_at",
        )
    if "content_hash" in record and record.get("content_hash") is not None:
        result["content_hash"] = _validate_nonempty_string(
            record.get("content_hash"),
            f"{location}.content_hash",
        )
    if "language" in record and record.get("language") is not None:
        result["language"] = _validate_nonempty_string(
            record.get("language"),
            f"{location}.language",
        ).lower()
    return result


def _normalize_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(metadata, Mapping):
        raise TypeError("metadata must be a mapping")

    input_fingerprints = metadata.get("input_fingerprints")
    if not isinstance(input_fingerprints, Mapping):
        raise TypeError("metadata.input_fingerprints must be a mapping")
    digest = _validate_nonempty_string(
        input_fingerprints.get("digest"),
        "metadata.input_fingerprints.digest",
    )
    record_count = _validate_nonnegative_integer(
        input_fingerprints.get("record_count"),
        "metadata.input_fingerprints.record_count",
    )

    return {
        "schema_version": _validate_positive_integer(
            metadata.get("schema_version"),
            "metadata.schema_version",
        ),
        "cache_version": _validate_nonempty_string(
            metadata.get("cache_version"),
            "metadata.cache_version",
        ),
        "root_fingerprint": _validate_nonempty_string(
            metadata.get("root_fingerprint"),
            "metadata.root_fingerprint",
        ),
        "scan_options_fingerprint": _validate_nonempty_string(
            metadata.get("scan_options_fingerprint"),
            "metadata.scan_options_fingerprint",
        ),
        "file_count": _validate_nonnegative_integer(
            metadata.get("file_count"),
            "metadata.file_count",
        ),
        "source_file_count": _validate_nonnegative_integer(
            metadata.get("source_file_count"),
            "metadata.source_file_count",
        ),
        "ignored_file_count": _validate_nonnegative_integer(
            metadata.get("ignored_file_count"),
            "metadata.ignored_file_count",
        ),
        "created_at": _validate_timestamp_value(
            metadata.get("created_at"),
            "metadata.created_at",
        ),
        "strata_version": _validate_optional_string(
            metadata.get("strata_version"),
            "metadata.strata_version",
        ),
        "language_counts": _normalize_language_counts(
            metadata.get("language_counts"),
        ),
        "input_fingerprints": {
            "schema_version": _validate_positive_integer(
                input_fingerprints.get("schema_version"),
                "metadata.input_fingerprints.schema_version",
            ),
            "record_count": record_count,
            "digest": digest,
            "records": _freeze_json(
                input_fingerprints.get("records", []),
                "metadata.input_fingerprints.records",
            ),
        },
    }


def _try_normalize_metadata(
    metadata: Mapping[str, Any] | None,
) -> tuple[dict[str, Any] | None, str | None]:
    try:
        return _normalize_metadata(metadata), None
    except (TypeError, ValueError) as error:
        return None, str(error)


def _ttl_expired_for_decision(
    created_at: int | float | str,
    *,
    current_time: int | float | str | None,
    max_age_seconds: int | float | None,
) -> bool:
    if current_time is None or max_age_seconds is None:
        return False
    return is_cache_metadata_expired(
        created_at=created_at,
        current_time=current_time,
        max_age_seconds=max_age_seconds,
    )


def _changed_counts(previous: Mapping[str, Any], current: Mapping[str, Any]) -> dict[str, dict[str, int]]:
    changed: dict[str, dict[str, int]] = {}
    for field in ("file_count", "source_file_count", "ignored_file_count"):
        previous_value = int(previous[field])
        current_value = int(current[field])
        if previous_value != current_value:
            changed[field] = {
                "previous": previous_value,
                "current": current_value,
                "delta": current_value - previous_value,
            }
    return changed


def _decision(
    *,
    reuse: bool,
    status: str,
    reasons: list[str],
    warnings: list[str],
    changed_counts: dict[str, Any],
) -> dict[str, Any]:
    return {
        "reuse": reuse,
        "status": status,
        "reasons": reasons,
        "warnings": warnings,
        "changed_counts": changed_counts,
    }


def _language_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        language = record.get("language")
        if not language:
            continue
        counts[language] = counts.get(language, 0) + 1
    return {key: counts[key] for key in sorted(counts)}


def _normalize_language_counts(value: Any) -> dict[str, int]:
    if not isinstance(value, Mapping):
        raise TypeError("metadata.language_counts must be a mapping")
    normalized: dict[str, int] = {}
    for key in sorted(value):
        language = _validate_nonempty_string(key, "metadata.language_counts key")
        normalized[language] = _validate_nonnegative_integer(
            value[key],
            f"metadata.language_counts.{language}",
        )
    return normalized


def _normalize_relative_path(value: Any, name: str) -> str:
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
        raise ValueError(f"{name} must identify a file")
    return normalized


def _stable_digest(value: Any) -> str:
    encoded = json.dumps(
        _thaw_json(_freeze_json(value, "digest_payload")),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _freeze_json(value: Any, location: str) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{location} must contain finite JSON numbers")
        return value
    if isinstance(value, Mapping):
        return {
            _validate_nonempty_string(key, f"{location} key"): _freeze_json(
                value[key],
                f"{location}.{key}",
            )
            for key in sorted(value)
        }
    if isinstance(value, (list, tuple)):
        return [
            _freeze_json(item, f"{location}[{index}]")
            for index, item in enumerate(value)
        ]
    raise TypeError(f"{location} must contain only JSON-ready values")


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_json(value[key]) for key in sorted(value)}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    if isinstance(value, list):
        return [_thaw_json(item) for item in value]
    return value


def _timestamp_to_seconds(value: Any, name: str) -> float:
    value = _validate_timestamp_value(value, name)
    if isinstance(value, (int, float)):
        return float(value)
    text = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as error:
        raise ValueError(f"{name} must be numeric seconds or ISO timestamp") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _validate_timestamp_value(value: Any, name: str) -> int | float | str:
    if isinstance(value, bool):
        raise TypeError(f"{name} must be numeric seconds or an ISO timestamp")
    if isinstance(value, int):
        if value < 0:
            raise ValueError(f"{name} must be non-negative")
        return value
    if isinstance(value, float):
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"{name} must be finite and non-negative")
        return value
    return _validate_nonempty_string(value, name)


def _validate_optional_string(value: Any, name: str) -> str | None:
    if value is None:
        return None
    return _validate_nonempty_string(value, name)


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


def _validate_positive_integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _validate_nonnegative_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized < 0:
        raise ValueError(f"{name} must be finite and non-negative")
    return normalized


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]
