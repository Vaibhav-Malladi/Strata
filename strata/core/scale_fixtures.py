"""Synthetic scale fixtures for performance hardening.

L4 models large repository pressure with count-only scenarios and small
in-memory generated records. It does not create files, scan repositories, call
extractors, clone real repos, or touch context artifacts.
"""

import hashlib
from typing import Any, Mapping

from strata.core.incremental_cache import (
    build_incremental_cache_key,
    build_incremental_cache_metadata,
)
from strata.core.performance_budget import build_performance_budget_summary
from strata.core.performance_fixtures import build_synthetic_fixture_counts
from strata.core.relationship_limits import apply_relationship_limits


SCALE_FIXTURE_KIND = "synthetic_scale_fixture"
DEFAULT_FILE_FACT_LIMIT = 64
DEFAULT_RELATIONSHIP_RECORD_LIMIT = 300

SCENARIO_SMALL_PYTHON_REPO = "small_python_repo"
SCENARIO_MEDIUM_FRONTEND_REPO = "medium_frontend_repo"
SCENARIO_LARGE_FULLSTACK_REPO = "large_fullstack_repo"
SCENARIO_VERY_LARGE_ENTERPRISE_WORKSPACE = "very_large_enterprise_workspace"
STRESS_SCENARIO_NAMES = (
    SCENARIO_SMALL_PYTHON_REPO,
    SCENARIO_MEDIUM_FRONTEND_REPO,
    SCENARIO_LARGE_FULLSTACK_REPO,
    SCENARIO_VERY_LARGE_ENTERPRISE_WORKSPACE,
)

BACKEND_FRAMEWORKS_FOR_SCALE = (
    "fastapi",
    "flask",
    "django",
    "django_rest_framework",
    "express",
    "nestjs",
    "go",
)
BACKEND_RELATIONSHIP_TYPES_FOR_SCALE = (
    "backend_route",
    "route_handler",
    "handler_service",
    "route_middleware",
)

LANGUAGE_EXTENSIONS = {
    "python": ".py",
    "javascript": ".js",
    "typescript": ".ts",
    "go": ".go",
}


def build_synthetic_repo_shape(
    repo_name: str,
    *,
    file_count: int,
    languages: tuple[str, ...],
    ignored_file_count: int = 0,
) -> dict[str, Any]:
    """Return a deterministic JSON-ready synthetic repository shape."""

    name = _validate_name(repo_name, "repo_name")
    total_count = _validate_nonnegative_integer(file_count, "file_count")
    ignored_count = _validate_nonnegative_integer(
        ignored_file_count,
        "ignored_file_count",
    )
    if ignored_count > total_count:
        raise ValueError("ignored_file_count must be less than or equal to file_count")

    source_count = total_count - ignored_count
    fixture_counts = build_synthetic_fixture_counts(source_count, languages=languages)
    return {
        "fixture_kind": SCALE_FIXTURE_KIND,
        "repo_name": name,
        "file_count": total_count,
        "source_file_count": source_count,
        "ignored_file_count": ignored_count,
        "language_counts": fixture_counts["language_counts"],
        "relationship_count": fixture_counts["relationship_count"],
        "edge_count": fixture_counts["edge_count"],
        "candidate_count": fixture_counts["candidate_count"],
        "estimated_context_tokens": fixture_counts["estimated_context_tokens"],
    }


def generate_synthetic_file_facts(
    shape: Mapping[str, Any],
    *,
    record_count: int | None = None,
    seed: str = "scale-fixture",
) -> list[dict[str, Any]]:
    """Generate deterministic in-memory file facts without creating files."""

    normalized_shape = _normalize_shape(shape)
    requested_count = (
        min(normalized_shape["source_file_count"], DEFAULT_FILE_FACT_LIMIT)
        if record_count is None
        else _validate_nonnegative_integer(record_count, "record_count")
    )
    count = min(requested_count, normalized_shape["source_file_count"])
    languages = _expanded_languages(normalized_shape["language_counts"])
    if count and not languages:
        languages = ("unknown",)

    facts: list[dict[str, Any]] = []
    for index in range(count):
        language = languages[index % len(languages)]
        extension = LANGUAGE_EXTENSIONS.get(language, ".txt")
        path = f"src/{language}/file_{index:05d}{extension}"
        digest = _short_digest(f"{seed}:{normalized_shape['repo_name']}:{path}:{index}")
        facts.append(
            {
                "path": path,
                "size": 128 + (index * 37) % 8_192,
                "mtime_ns": 1_700_000_000_000_000_000 + index * 1_000_000,
                "language": language,
                "content_hash": digest,
            }
        )
    return facts


def build_count_only_stress_scenarios() -> dict[str, dict[str, Any]]:
    """Return deterministic count-only scale scenarios."""

    scenarios = {
        SCENARIO_SMALL_PYTHON_REPO: build_synthetic_repo_shape(
            SCENARIO_SMALL_PYTHON_REPO,
            file_count=50,
            ignored_file_count=5,
            languages=("python",),
        ),
        SCENARIO_MEDIUM_FRONTEND_REPO: build_synthetic_repo_shape(
            SCENARIO_MEDIUM_FRONTEND_REPO,
            file_count=800,
            ignored_file_count=80,
            languages=("javascript", "typescript"),
        ),
        SCENARIO_LARGE_FULLSTACK_REPO: build_synthetic_repo_shape(
            SCENARIO_LARGE_FULLSTACK_REPO,
            file_count=3_000,
            ignored_file_count=300,
            languages=("python", "javascript", "typescript", "go"),
        ),
        SCENARIO_VERY_LARGE_ENTERPRISE_WORKSPACE: build_synthetic_repo_shape(
            SCENARIO_VERY_LARGE_ENTERPRISE_WORKSPACE,
            file_count=12_000,
            ignored_file_count=1_500,
            languages=("python", "javascript", "typescript", "go"),
        ),
    }
    return {key: scenarios[key] for key in STRESS_SCENARIO_NAMES}


def generate_synthetic_relationships(
    shape: Mapping[str, Any],
    *,
    relationship_count: int | None = None,
    seed: str = "scale-fixture",
) -> list[dict[str, Any]]:
    """Generate deterministic backend-compatible relationship dictionaries."""

    normalized_shape = _normalize_shape(shape)
    requested_count = (
        min(normalized_shape["relationship_count"], DEFAULT_RELATIONSHIP_RECORD_LIMIT)
        if relationship_count is None
        else _validate_nonnegative_integer(relationship_count, "relationship_count")
    )
    count = min(requested_count, normalized_shape["relationship_count"])
    relationships: list[dict[str, Any]] = []
    for index in range(count):
        framework = BACKEND_FRAMEWORKS_FOR_SCALE[index % len(BACKEND_FRAMEWORKS_FOR_SCALE)]
        relationship_type = BACKEND_RELATIONSHIP_TYPES_FOR_SCALE[
            index % len(BACKEND_RELATIONSHIP_TYPES_FOR_SCALE)
        ]
        extension = _framework_extension(framework)
        source_path = f"services/{framework}/routes_{index // len(BACKEND_FRAMEWORKS_FOR_SCALE):04d}{extension}"
        relationships.append(
            {
                "framework": framework,
                "relationship_type": relationship_type,
                "source_path": source_path,
                "target_path": f"services/{framework}/handlers_{index % 97:04d}{extension}",
                "route_path": f"/synthetic/{framework}/{index % 251}",
                "http_method": _http_method_for(index),
                "target_symbol": f"Target{index % 113}",
                "handler_symbol": f"handle_{framework}_{index % 89}",
                "service_symbol": f"Service{index % 71}",
                "model_symbol": f"Model{index % 53}",
                "confidence": "high" if index % 3 else "medium",
                "evidence": [f"synthetic:{seed}:{index}"],
                "warnings": [],
                "reason": "synthetic scale relationship",
            }
        )
    return relationships


def evaluate_scale_stress_scenario(
    shape: Mapping[str, Any],
    *,
    file_fact_limit: int = DEFAULT_FILE_FACT_LIMIT,
    relationship_record_limit: int = DEFAULT_RELATIONSHIP_RECORD_LIMIT,
    created_at: int = 1_700_000_000,
    seed: str = "scale-fixture",
) -> dict[str, Any]:
    """Combine L1/L2/L3 primitives for one synthetic stress scenario."""

    normalized_shape = _normalize_shape(shape)
    file_facts = generate_synthetic_file_facts(
        normalized_shape,
        record_count=file_fact_limit,
        seed=seed,
    )
    cache_metadata = build_incremental_cache_metadata(
        root_fingerprint=f"synthetic:{normalized_shape['repo_name']}",
        scan_options={
            "fixture_kind": SCALE_FIXTURE_KIND,
            "scenario": normalized_shape["repo_name"],
        },
        input_records=file_facts,
        created_at=created_at,
        source_file_count=normalized_shape["source_file_count"],
        ignored_file_count=normalized_shape["ignored_file_count"],
        strata_version="synthetic",
    )
    cache_key = build_incremental_cache_key(cache_metadata)
    relationships = generate_synthetic_relationships(
        normalized_shape,
        relationship_count=relationship_record_limit,
        seed=seed,
    )
    relationship_limit_summary = apply_relationship_limits(relationships)
    budget_summary = build_performance_budget_summary(
        file_count=normalized_shape["file_count"],
        edge_count=normalized_shape["edge_count"],
        candidate_count=normalized_shape["candidate_count"],
        relationship_count=normalized_shape["relationship_count"],
        estimated_context_tokens=normalized_shape["estimated_context_tokens"],
    )
    warnings = _combined_warnings(budget_summary, relationship_limit_summary)
    return {
        "scenario": normalized_shape,
        "budget_summary": budget_summary,
        "cache_metadata_summary": {
            "cache_key": cache_key,
            "file_fact_count": len(file_facts),
            "source_file_count": cache_metadata["source_file_count"],
            "ignored_file_count": cache_metadata["ignored_file_count"],
            "input_fingerprint_record_count": cache_metadata["input_fingerprints"]["record_count"],
        },
        "relationship_limit_summary": {
            "status": relationship_limit_summary["status"],
            "total_input_count": relationship_limit_summary["total_input_count"],
            "total_kept_count": relationship_limit_summary["total_kept_count"],
            "dropped_relationships_count": relationship_limit_summary[
                "dropped_relationships_count"
            ],
            "drop_reasons": relationship_limit_summary["drop_reasons"],
            "duplicate_relationship_count": relationship_limit_summary[
                "duplicate_relationship_count"
            ],
            "warnings": relationship_limit_summary["warnings"],
        },
        "status": _combined_status(
            budget_summary["budget_status"],
            relationship_limit_summary["status"],
        ),
        "warnings": warnings,
    }


def evaluate_named_scale_stress_scenario(
    scenario_name: str,
    **kwargs: Any,
) -> dict[str, Any]:
    """Evaluate one named count-only stress scenario."""

    scenarios = build_count_only_stress_scenarios()
    name = _validate_name(scenario_name, "scenario_name")
    if name not in scenarios:
        raise ValueError(f"unknown scale stress scenario: {name}")
    return evaluate_scale_stress_scenario(scenarios[name], **kwargs)


def _combined_status(budget_status: str, relationship_status: str) -> str:
    statuses = {budget_status, relationship_status}
    if "fail" in statuses:
        return "fail"
    if "warn" in statuses:
        return "warn"
    return "pass"


def _combined_warnings(
    budget_summary: Mapping[str, Any],
    relationship_limit_summary: Mapping[str, Any],
) -> list[str]:
    warnings: list[str] = []
    warnings.extend(str(item) for item in budget_summary.get("warnings", []) or [])
    warnings.extend(
        str(item) for item in relationship_limit_summary.get("warnings", []) or []
    )
    return warnings


def _normalize_shape(shape: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(shape, Mapping):
        raise TypeError("shape must be a mapping")
    language_counts = shape.get("language_counts")
    if not isinstance(language_counts, Mapping):
        raise TypeError("shape.language_counts must be a mapping")
    normalized_language_counts = {
        _validate_name(language, "language"): _validate_nonnegative_integer(
            count,
            f"language_counts.{language}",
        )
        for language, count in sorted(language_counts.items())
    }
    return {
        "fixture_kind": str(shape.get("fixture_kind") or SCALE_FIXTURE_KIND),
        "repo_name": _validate_name(shape.get("repo_name"), "repo_name"),
        "file_count": _validate_nonnegative_integer(shape.get("file_count"), "file_count"),
        "source_file_count": _validate_nonnegative_integer(
            shape.get("source_file_count"),
            "source_file_count",
        ),
        "ignored_file_count": _validate_nonnegative_integer(
            shape.get("ignored_file_count"),
            "ignored_file_count",
        ),
        "language_counts": normalized_language_counts,
        "relationship_count": _validate_nonnegative_integer(
            shape.get("relationship_count"),
            "relationship_count",
        ),
        "edge_count": _validate_nonnegative_integer(shape.get("edge_count"), "edge_count"),
        "candidate_count": _validate_nonnegative_integer(
            shape.get("candidate_count"),
            "candidate_count",
        ),
        "estimated_context_tokens": _validate_nonnegative_integer(
            shape.get("estimated_context_tokens"),
            "estimated_context_tokens",
        ),
    }


def _expanded_languages(language_counts: Mapping[str, int]) -> tuple[str, ...]:
    languages = [
        language
        for language, count in sorted(language_counts.items())
        if count > 0
    ]
    return tuple(languages)


def _framework_extension(framework: str) -> str:
    if framework in {"express", "nestjs"}:
        return ".ts"
    if framework == "go":
        return ".go"
    return ".py"


def _http_method_for(index: int) -> str:
    methods = ("GET", "POST", "PUT", "PATCH", "DELETE")
    return methods[index % len(methods)]


def _short_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _validate_name(value: Any, name: str) -> str:
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
