"""Synthetic count-only fixtures for performance budget tests."""

from typing import Any


DEFAULT_SYNTHETIC_LANGUAGES = ("python", "javascript", "typescript", "go")
SYNTHETIC_FIXTURE_KIND = "synthetic_counts_only"


def build_synthetic_fixture_counts(
    file_count: int,
    *,
    languages: tuple[str, ...] = DEFAULT_SYNTHETIC_LANGUAGES,
) -> dict[str, Any]:
    """Return deterministic repository counts without creating fixture files."""

    normalized_file_count = _validate_nonnegative_integer(file_count, "file_count")
    normalized_languages = _validate_languages(languages)
    language_counts = _distribute_count(normalized_file_count, normalized_languages)
    candidate_count = _ceil_divide(normalized_file_count, 5)
    edge_count = max(0, normalized_file_count - 1) + normalized_file_count // 2
    relationship_count = normalized_file_count * 2 + edge_count
    estimated_context_tokens = normalized_file_count * 6 + candidate_count * 12

    return {
        "fixture_kind": SYNTHETIC_FIXTURE_KIND,
        "file_count": normalized_file_count,
        "edge_count": edge_count,
        "candidate_count": candidate_count,
        "relationship_count": relationship_count,
        "estimated_context_tokens": estimated_context_tokens,
        "language_counts": language_counts,
    }


def _distribute_count(file_count: int, languages: tuple[str, ...]) -> dict[str, int]:
    base_count = file_count // len(languages)
    remainder = file_count % len(languages)
    return {
        language: base_count + (1 if index < remainder else 0)
        for index, language in enumerate(languages)
    }


def _ceil_divide(value: int, divisor: int) -> int:
    if value == 0:
        return 0
    return (value + divisor - 1) // divisor


def _validate_languages(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        raise TypeError("languages must be a tuple of strings")
    try:
        languages = tuple(value)
    except TypeError as error:
        raise TypeError("languages must be a tuple of strings") from error
    if not languages:
        raise ValueError("languages must not be empty")
    for index, language in enumerate(languages):
        if not isinstance(language, str) or not language.strip():
            raise ValueError(f"languages[{index}] must be a non-empty string")
        if language != language.strip():
            raise ValueError(f"languages[{index}] must not have surrounding whitespace")
    duplicate = next(
        (
            language
            for index, language in enumerate(languages)
            if language in languages[:index]
        ),
        None,
    )
    if duplicate is not None:
        raise ValueError(f"languages must not contain duplicates: {duplicate}")
    return languages


def _validate_nonnegative_integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value
