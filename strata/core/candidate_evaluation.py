"""Schema and validation for candidate-selection evaluation fixtures."""

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any


SCHEMA_VERSION = 1


class ExpectedFileTier(StrEnum):
    CRITICAL = "critical"
    USEFUL = "useful"
    DISTRACTOR = "distractor"
    IRRELEVANT = "irrelevant"


EXPECTED_FILE_TIERS = tuple(tier.value for tier in ExpectedFileTier)


class CandidateEvaluationManifestError(ValueError):
    """Raised when a candidate-evaluation manifest does not match the schema."""


@dataclass(frozen=True, slots=True)
class ExpectedFile:
    path: str
    note: str | None = None


@dataclass(frozen=True, slots=True)
class ExpectedFiles:
    critical: tuple[ExpectedFile, ...]
    useful: tuple[ExpectedFile, ...]
    distractor: tuple[ExpectedFile, ...]
    irrelevant: tuple[ExpectedFile, ...]

    def for_tier(self, tier: ExpectedFileTier) -> tuple[ExpectedFile, ...]:
        return getattr(self, tier.value)


@dataclass(frozen=True, slots=True)
class CandidateEvaluationTags:
    stacks: tuple[str, ...]
    languages: tuple[str, ...]
    frameworks: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CandidateEvaluationTask:
    task_id: str
    task_text: str
    fixture_path: str
    tags: CandidateEvaluationTags
    expected_files: ExpectedFiles


@dataclass(frozen=True, slots=True)
class CandidateEvaluationManifest:
    schema_version: int
    tasks: tuple[CandidateEvaluationTask, ...]


def load_candidate_evaluation_manifest(
    path: str | Path,
) -> CandidateEvaluationManifest:
    """Load and validate a UTF-8 JSON candidate-evaluation manifest."""

    manifest_path = Path(path)
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise CandidateEvaluationManifestError(
            f"manifest: invalid JSON at line {error.lineno}, column {error.colno}"
        ) from error
    return validate_candidate_evaluation_manifest(payload)


def validate_candidate_evaluation_manifest(
    payload: Any,
) -> CandidateEvaluationManifest:
    """Validate a decoded manifest and return its immutable representation."""

    data = _require_object(payload, "manifest")
    _require_keys(data, "manifest", {"schema_version", "tasks"})

    schema_version = data["schema_version"]
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version != SCHEMA_VERSION
    ):
        raise CandidateEvaluationManifestError(
            f"manifest.schema_version: expected {SCHEMA_VERSION}"
        )

    task_values = _require_list(data["tasks"], "manifest.tasks")
    tasks = tuple(
        _validate_task(task, f"manifest.tasks[{index}]")
        for index, task in enumerate(task_values)
    )
    task_ids: set[str] = set()
    for index, task in enumerate(tasks):
        if task.task_id in task_ids:
            raise CandidateEvaluationManifestError(
                f"manifest.tasks[{index}].id: duplicate task id {task.task_id!r}"
            )
        task_ids.add(task.task_id)

    return CandidateEvaluationManifest(schema_version=schema_version, tasks=tasks)


def _validate_task(value: Any, location: str) -> CandidateEvaluationTask:
    task = _require_object(value, location)
    _require_keys(
        task,
        location,
        {"id", "task", "fixture_path", "tags", "expected_files"},
    )
    return CandidateEvaluationTask(
        task_id=_require_nonempty_string(task["id"], f"{location}.id"),
        task_text=_require_nonempty_string(task["task"], f"{location}.task"),
        fixture_path=_require_relative_path(
            task["fixture_path"], f"{location}.fixture_path", allow_current=True
        ),
        tags=_validate_tags(task["tags"], f"{location}.tags"),
        expected_files=_validate_expected_files(
            task["expected_files"], f"{location}.expected_files"
        ),
    )


def _validate_tags(value: Any, location: str) -> CandidateEvaluationTags:
    tags = _require_object(value, location)
    tag_names = {"stacks", "languages", "frameworks"}
    _require_keys(tags, location, tag_names)
    validated = {
        name: _validate_string_list(tags[name], f"{location}.{name}")
        for name in sorted(tag_names)
    }
    return CandidateEvaluationTags(
        stacks=validated["stacks"],
        languages=validated["languages"],
        frameworks=validated["frameworks"],
    )


def _validate_expected_files(value: Any, location: str) -> ExpectedFiles:
    expected = _require_object(value, location)
    tier_names = set(EXPECTED_FILE_TIERS)
    _require_keys(expected, location, tier_names)

    by_tier: dict[str, tuple[ExpectedFile, ...]] = {}
    seen_paths: dict[str, str] = {}
    for tier in EXPECTED_FILE_TIERS:
        entries = _require_list(expected[tier], f"{location}.{tier}")
        validated_entries: list[ExpectedFile] = []
        for index, entry in enumerate(entries):
            entry_location = f"{location}.{tier}[{index}]"
            validated = _validate_expected_file(entry, entry_location)
            previous_tier = seen_paths.get(validated.path)
            if previous_tier is not None:
                raise CandidateEvaluationManifestError(
                    f"{entry_location}.path: duplicate expected file {validated.path!r}; "
                    f"already listed in {previous_tier}"
                )
            seen_paths[validated.path] = tier
            validated_entries.append(validated)
        by_tier[tier] = tuple(validated_entries)

    return ExpectedFiles(
        critical=by_tier[ExpectedFileTier.CRITICAL],
        useful=by_tier[ExpectedFileTier.USEFUL],
        distractor=by_tier[ExpectedFileTier.DISTRACTOR],
        irrelevant=by_tier[ExpectedFileTier.IRRELEVANT],
    )


def _validate_expected_file(value: Any, location: str) -> ExpectedFile:
    entry = _require_object(value, location)
    _require_keys(entry, location, {"path"}, optional={"note"})
    note = None
    if "note" in entry:
        note = _require_nonempty_string(entry["note"], f"{location}.note")
    return ExpectedFile(
        path=_require_relative_path(entry["path"], f"{location}.path"),
        note=note,
    )


def _validate_string_list(value: Any, location: str) -> tuple[str, ...]:
    values = _require_list(value, location)
    result = tuple(
        _require_nonempty_string(item, f"{location}[{index}]")
        for index, item in enumerate(values)
    )
    duplicate = next(
        (item for index, item in enumerate(result) if item in result[:index]),
        None,
    )
    if duplicate is not None:
        raise CandidateEvaluationManifestError(
            f"{location}: duplicate tag {duplicate!r}"
        )
    return result


def _require_relative_path(
    value: Any,
    location: str,
    *,
    allow_current: bool = False,
) -> str:
    raw_path = _require_nonempty_string(value, location)
    if "\\" in raw_path:
        raise CandidateEvaluationManifestError(
            f"{location}: must use forward slashes"
        )

    path = PurePosixPath(raw_path)
    windows_path = PureWindowsPath(raw_path)
    if path.is_absolute() or windows_path.is_absolute() or windows_path.drive:
        raise CandidateEvaluationManifestError(f"{location}: must be relative")
    if ".." in path.parts:
        raise CandidateEvaluationManifestError(
            f"{location}: must not escape its root with '..'"
        )
    if path.as_posix() != raw_path or (raw_path == "." and not allow_current):
        raise CandidateEvaluationManifestError(
            f"{location}: must be a normalized relative path"
        )
    return raw_path


def _require_nonempty_string(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CandidateEvaluationManifestError(
            f"{location}: expected a non-empty string"
        )
    if value != value.strip():
        raise CandidateEvaluationManifestError(
            f"{location}: must not have surrounding whitespace"
        )
    return value


def _require_list(value: Any, location: str) -> list[Any]:
    if not isinstance(value, list):
        raise CandidateEvaluationManifestError(f"{location}: expected an array")
    return value


def _require_object(value: Any, location: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CandidateEvaluationManifestError(f"{location}: expected an object")
    if any(not isinstance(key, str) for key in value):
        raise CandidateEvaluationManifestError(
            f"{location}: field names must be strings"
        )
    return value


def _require_keys(
    value: dict[str, Any],
    location: str,
    required: set[str],
    *,
    optional: set[str] | None = None,
) -> None:
    missing = sorted(required - value.keys())
    if missing:
        raise CandidateEvaluationManifestError(
            f"{location}: missing required field(s): {', '.join(missing)}"
        )
    allowed = required | (optional or set())
    unexpected = sorted(value.keys() - allowed)
    if unexpected:
        raise CandidateEvaluationManifestError(
            f"{location}: unexpected field(s): {', '.join(unexpected)}"
        )
