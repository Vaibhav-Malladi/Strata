from dataclasses import dataclass
from typing import Iterable

from strata.core.angular_starting_files import select_angular_starting_files
from strata.core.frontend_frameworks import detect_frontend_frameworks
from strata.core.inventory import InventoryRecord
from strata.core.react_starting_files import select_react_starting_files


DEFAULT_FRONTEND_STARTING_FILE_LIMIT = 20
_SUPPORTED_FRAMEWORKS = ("react", "angular")
_FRAMEWORK_ORDER = {framework: index for index, framework in enumerate(_SUPPORTED_FRAMEWORKS)}


@dataclass(frozen=True, slots=True)
class FrontendStartingFile:
    path: str
    framework: str
    role: str
    score: int
    reasons: tuple[str, ...]
    confidence: str


@dataclass(frozen=True, slots=True)
class FrontendStartingFileSelection:
    files: tuple[FrontendStartingFile, ...]
    frameworks_considered: tuple[str, ...]
    files_considered: int
    limit: int
    truncated: bool


def select_frontend_starting_files(
    records: Iterable[InventoryRecord],
    task: str,
    frameworks: Iterable[str] | str = _SUPPORTED_FRAMEWORKS,
    limit: int = DEFAULT_FRONTEND_STARTING_FILE_LIMIT,
) -> FrontendStartingFileSelection:
    """Select normalized frontend starting files without reading file contents."""

    _validate_limit(limit)
    requested_frameworks = _normalize_frameworks(frameworks)
    inventory = tuple(records)
    if requested_frameworks == ("auto",):
        detection = detect_frontend_frameworks(inventory)
        enabled_frameworks = tuple(
            framework
            for framework in _SUPPORTED_FRAMEWORKS
            if framework in detection.frameworks
        )
    else:
        enabled_frameworks = requested_frameworks
    selector_limit = limit + 1
    selected: list[FrontendStartingFile] = []

    if "react" in enabled_frameworks:
        selected.extend(
            FrontendStartingFile(
                path=item.path,
                framework="react",
                role=item.role,
                score=item.score,
                reasons=item.reasons,
                confidence=item.confidence,
            )
            for item in select_react_starting_files(
                inventory,
                task,
                limit=selector_limit,
            )
        )

    if "angular" in enabled_frameworks:
        selected.extend(
            FrontendStartingFile(
                path=item.path,
                framework="angular",
                role=item.role,
                score=item.score,
                reasons=item.reasons,
                confidence=item.confidence,
            )
            for item in select_angular_starting_files(
                inventory,
                task,
                limit=selector_limit,
            )
        )

    merged = _deduplicate(selected)
    merged.sort(
        key=lambda item: (
            -item.score,
            _FRAMEWORK_ORDER[item.framework],
            item.path.lower(),
            item.path,
        )
    )
    return FrontendStartingFileSelection(
        files=tuple(merged[:limit]),
        frameworks_considered=enabled_frameworks,
        files_considered=len(inventory),
        limit=limit,
        truncated=len(merged) > limit,
    )


def _deduplicate(files: Iterable[FrontendStartingFile]) -> list[FrontendStartingFile]:
    by_path: dict[str, FrontendStartingFile] = {}
    for item in files:
        key = _path_key(item.path)
        existing = by_path.get(key)
        if existing is None:
            by_path[key] = item
            continue

        if _preferred(item, existing):
            by_path[key] = _with_framework_note(item, existing)
        else:
            by_path[key] = _with_framework_note(existing, item)
    return list(by_path.values())


def _preferred(left: FrontendStartingFile, right: FrontendStartingFile) -> bool:
    return (-left.score, _FRAMEWORK_ORDER[left.framework], left.path.lower(), left.path) < (
        -right.score,
        _FRAMEWORK_ORDER[right.framework],
        right.path.lower(),
        right.path,
    )


def _with_framework_note(
    winner: FrontendStartingFile,
    other: FrontendStartingFile,
) -> FrontendStartingFile:
    if winner.framework == other.framework:
        return winner
    note = f"also selected by {other.framework} (score {other.score})"
    if note in winner.reasons:
        return winner
    return FrontendStartingFile(
        path=winner.path,
        framework=winner.framework,
        role=winner.role,
        score=winner.score,
        reasons=winner.reasons + (note,),
        confidence=winner.confidence,
    )


def _normalize_frameworks(frameworks: Iterable[str] | str) -> tuple[str, ...]:
    values = (frameworks,) if isinstance(frameworks, str) else tuple(frameworks)
    invalid = sorted(
        {
            str(framework)
            for framework in values
            if framework not in (*_SUPPORTED_FRAMEWORKS, "auto")
        }
    )
    if invalid:
        raise ValueError(f"unsupported frontend framework(s): {', '.join(invalid)}")
    if "auto" in values:
        if any(framework != "auto" for framework in values):
            raise ValueError("auto framework mode cannot be combined with explicit frameworks")
        return ("auto",)
    enabled = set(values)
    return tuple(framework for framework in _SUPPORTED_FRAMEWORKS if framework in enabled)


def _validate_limit(limit: int) -> None:
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise TypeError("limit must be an integer")
    if limit <= 0:
        raise ValueError("limit must be greater than zero")


def _path_key(path: str) -> str:
    return str(path).replace("\\", "/").lower()
