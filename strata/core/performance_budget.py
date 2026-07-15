"""Deterministic performance budget primitives for scale hardening.

L1 measures known counts against stable budgets only. It does not scan
repositories, time real work, optimize extractors, or create context artifacts.
"""

import math
from dataclasses import dataclass
from typing import Any


PERFORMANCE_BUDGET_PROFILE_VERSION = 1

SMALL_REPO_FILE_COUNT = 100
MEDIUM_REPO_FILE_COUNT = 1_000
LARGE_REPO_FILE_COUNT = 5_000
MAX_CANDIDATE_FILES = 250
MAX_RELATIONSHIP_RECORDS = 2_000
MAX_SUMMARY_ITEMS = 50
MAX_SCAN_SECONDS_SOFT = 20.0
MAX_CONTEXT_TOKENS_DEFAULT = 8_000
MAX_CONTEXT_TOKENS_STRICT = 4_000

REPO_SIZE_SMALL = "small"
REPO_SIZE_MEDIUM = "medium"
REPO_SIZE_LARGE = "large"
REPO_SIZE_VERY_LARGE = "very_large"
REPO_SIZE_CLASSES = (
    REPO_SIZE_SMALL,
    REPO_SIZE_MEDIUM,
    REPO_SIZE_LARGE,
    REPO_SIZE_VERY_LARGE,
)

BUDGET_STATUS_PASS = "pass"
BUDGET_STATUS_WARN = "warn"
BUDGET_STATUS_FAIL = "fail"
BUDGET_STATUSES = (
    BUDGET_STATUS_PASS,
    BUDGET_STATUS_WARN,
    BUDGET_STATUS_FAIL,
)


@dataclass(frozen=True, slots=True)
class PerformanceBudgetProfile:
    profile_version: int = PERFORMANCE_BUDGET_PROFILE_VERSION
    profile_name: str = "default"
    small_repo_file_count: int = SMALL_REPO_FILE_COUNT
    medium_repo_file_count: int = MEDIUM_REPO_FILE_COUNT
    large_repo_file_count: int = LARGE_REPO_FILE_COUNT
    max_candidate_files: int = MAX_CANDIDATE_FILES
    max_relationship_records: int = MAX_RELATIONSHIP_RECORDS
    max_summary_items: int = MAX_SUMMARY_ITEMS
    max_scan_seconds_soft: float = MAX_SCAN_SECONDS_SOFT
    max_context_tokens_default: int = MAX_CONTEXT_TOKENS_DEFAULT
    max_context_tokens_strict: int = MAX_CONTEXT_TOKENS_STRICT

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "profile_version",
            _validate_positive_integer(self.profile_version, "profile_version"),
        )
        object.__setattr__(
            self,
            "profile_name",
            _validate_nonempty_string(self.profile_name, "profile_name"),
        )
        object.__setattr__(
            self,
            "small_repo_file_count",
            _validate_positive_integer(
                self.small_repo_file_count,
                "small_repo_file_count",
            ),
        )
        object.__setattr__(
            self,
            "medium_repo_file_count",
            _validate_positive_integer(
                self.medium_repo_file_count,
                "medium_repo_file_count",
            ),
        )
        object.__setattr__(
            self,
            "large_repo_file_count",
            _validate_positive_integer(
                self.large_repo_file_count,
                "large_repo_file_count",
            ),
        )
        object.__setattr__(
            self,
            "max_candidate_files",
            _validate_positive_integer(self.max_candidate_files, "max_candidate_files"),
        )
        object.__setattr__(
            self,
            "max_relationship_records",
            _validate_positive_integer(
                self.max_relationship_records,
                "max_relationship_records",
            ),
        )
        object.__setattr__(
            self,
            "max_summary_items",
            _validate_positive_integer(self.max_summary_items, "max_summary_items"),
        )
        object.__setattr__(
            self,
            "max_scan_seconds_soft",
            _validate_positive_number(
                self.max_scan_seconds_soft,
                "max_scan_seconds_soft",
            ),
        )
        object.__setattr__(
            self,
            "max_context_tokens_default",
            _validate_positive_integer(
                self.max_context_tokens_default,
                "max_context_tokens_default",
            ),
        )
        object.__setattr__(
            self,
            "max_context_tokens_strict",
            _validate_positive_integer(
                self.max_context_tokens_strict,
                "max_context_tokens_strict",
            ),
        )

        if self.small_repo_file_count >= self.medium_repo_file_count:
            raise ValueError(
                "small_repo_file_count must be less than medium_repo_file_count"
            )
        if self.medium_repo_file_count >= self.large_repo_file_count:
            raise ValueError(
                "medium_repo_file_count must be less than large_repo_file_count"
            )
        if self.max_context_tokens_strict > self.max_context_tokens_default:
            raise ValueError(
                "max_context_tokens_strict must be less than or equal to "
                "max_context_tokens_default"
            )

    def to_dict(self) -> dict[str, int | float | str]:
        """Return the stable JSON-ready performance budget profile."""

        return {
            "profile_version": self.profile_version,
            "profile_name": self.profile_name,
            "small_repo_file_count": self.small_repo_file_count,
            "medium_repo_file_count": self.medium_repo_file_count,
            "large_repo_file_count": self.large_repo_file_count,
            "max_candidate_files": self.max_candidate_files,
            "max_relationship_records": self.max_relationship_records,
            "max_summary_items": self.max_summary_items,
            "max_scan_seconds_soft": self.max_scan_seconds_soft,
            "max_context_tokens_default": self.max_context_tokens_default,
            "max_context_tokens_strict": self.max_context_tokens_strict,
        }


def default_performance_budget_profile() -> dict[str, int | float | str]:
    """Return a fresh JSON-ready copy of the default performance budget."""

    return DEFAULT_PERFORMANCE_BUDGET_PROFILE.to_dict()


def classify_repository_size(
    file_count: int,
    *,
    profile: PerformanceBudgetProfile | None = None,
) -> str:
    """Classify a repository size from a known source-file count."""

    count = _validate_nonnegative_integer(file_count, "file_count")
    resolved_profile = _resolve_profile(profile)
    if count <= resolved_profile.small_repo_file_count:
        return REPO_SIZE_SMALL
    if count <= resolved_profile.medium_repo_file_count:
        return REPO_SIZE_MEDIUM
    if count <= resolved_profile.large_repo_file_count:
        return REPO_SIZE_LARGE
    return REPO_SIZE_VERY_LARGE


def build_performance_budget_summary(
    *,
    file_count: int,
    edge_count: int,
    candidate_count: int,
    relationship_count: int,
    estimated_context_tokens: int,
    profile: PerformanceBudgetProfile | None = None,
) -> dict[str, Any]:
    """Measure known repository counts against the stable L1 budget profile."""

    normalized_file_count = _validate_nonnegative_integer(file_count, "file_count")
    normalized_edge_count = _validate_nonnegative_integer(edge_count, "edge_count")
    normalized_candidate_count = _validate_nonnegative_integer(
        candidate_count,
        "candidate_count",
    )
    normalized_relationship_count = _validate_nonnegative_integer(
        relationship_count,
        "relationship_count",
    )
    normalized_context_tokens = _validate_nonnegative_integer(
        estimated_context_tokens,
        "estimated_context_tokens",
    )
    resolved_profile = _resolve_profile(profile)

    repo_size_class = classify_repository_size(
        normalized_file_count,
        profile=resolved_profile,
    )
    warnings = _budget_warnings(
        file_count=normalized_file_count,
        candidate_count=normalized_candidate_count,
        relationship_count=normalized_relationship_count,
        estimated_context_tokens=normalized_context_tokens,
        repo_size_class=repo_size_class,
        profile=resolved_profile,
    )
    budget_status = _budget_status(warnings)

    return {
        "file_count": normalized_file_count,
        "edge_count": normalized_edge_count,
        "candidate_count": normalized_candidate_count,
        "relationship_count": normalized_relationship_count,
        "estimated_context_tokens": normalized_context_tokens,
        "repo_size_class": repo_size_class,
        "budget_status": budget_status,
        "warnings": warnings,
    }


def _budget_warnings(
    *,
    file_count: int,
    candidate_count: int,
    relationship_count: int,
    estimated_context_tokens: int,
    repo_size_class: str,
    profile: PerformanceBudgetProfile,
) -> list[str]:
    warnings: list[str] = []

    if repo_size_class == REPO_SIZE_VERY_LARGE:
        warnings.append(
            "file_count "
            f"{file_count} exceeds large_repo_file_count "
            f"{profile.large_repo_file_count}"
        )

    if candidate_count > profile.max_candidate_files:
        warnings.append(
            "candidate_count "
            f"{candidate_count} exceeds max_candidate_files "
            f"{profile.max_candidate_files}"
        )

    if relationship_count > profile.max_relationship_records:
        warnings.append(
            "relationship_count "
            f"{relationship_count} exceeds max_relationship_records "
            f"{profile.max_relationship_records}"
        )

    if estimated_context_tokens > profile.max_context_tokens_strict:
        warnings.append(
            "estimated_context_tokens "
            f"{estimated_context_tokens} exceeds max_context_tokens_strict "
            f"{profile.max_context_tokens_strict}"
        )

    if estimated_context_tokens > profile.max_context_tokens_default:
        warnings.append(
            "estimated_context_tokens "
            f"{estimated_context_tokens} exceeds max_context_tokens_default "
            f"{profile.max_context_tokens_default}"
        )

    return warnings


def _budget_status(warnings: list[str]) -> str:
    if any("max_context_tokens_default" in warning for warning in warnings):
        return BUDGET_STATUS_FAIL
    if warnings:
        return BUDGET_STATUS_WARN
    return BUDGET_STATUS_PASS


def _resolve_profile(profile: PerformanceBudgetProfile | None) -> PerformanceBudgetProfile:
    if profile is None:
        return DEFAULT_PERFORMANCE_BUDGET_PROFILE
    if not isinstance(profile, PerformanceBudgetProfile):
        raise TypeError("profile must be a PerformanceBudgetProfile")
    return profile


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


def _validate_positive_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized <= 0:
        raise ValueError(f"{name} must be positive")
    return normalized


DEFAULT_PERFORMANCE_BUDGET_PROFILE = PerformanceBudgetProfile()
