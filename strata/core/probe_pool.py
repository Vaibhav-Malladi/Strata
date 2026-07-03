"""Deterministic mixed candidate pools for future content probing."""

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Iterable

from strata.core.frontend_roles import infer_frontend_role_from_path
from strata.core.inventory import InventoryRecord


DEFAULT_MAX_TOTAL = 40
DEFAULT_MAX_OBVIOUS = 20
DEFAULT_MAX_RESCUE = 20
DEFAULT_MAX_PER_DIRECTORY = 5

_FRAMEWORK_CONFIG_NAMES = {
    "angular.json",
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "setup.cfg",
    "setup.py",
    "tsconfig.json",
}
_FRAMEWORK_CONFIG_PREFIXES = (
    "babel.config.",
    "eslint.config.",
    "jest.config.",
    "next.config.",
    "postcss.config.",
    "tailwind.config.",
    "vite.config.",
)
_GENERIC_STEMS = {
    "api",
    "app",
    "config",
    "helper",
    "helpers",
    "index",
    "main",
    "routes",
    "service",
    "util",
    "utils",
}
_SOURCE_DIRECTORY_NAMES = {
    "api",
    "app",
    "components",
    "core",
    "features",
    "hooks",
    "lib",
    "pages",
    "routes",
    "services",
    "src",
}
_TASK_STOPWORDS = {
    "a",
    "add",
    "an",
    "and",
    "change",
    "fix",
    "for",
    "in",
    "of",
    "on",
    "the",
    "to",
    "update",
    "with",
}
_ROLE_TASK_TERMS = {
    "api_client": {"api", "client", "request"},
    "component": {"component", "ui"},
    "config": {"config", "configuration"},
    "form": {"form"},
    "helper": {"helper", "helpers", "util", "utils", "utility"},
    "hook": {"hook", "hooks"},
    "model": {"model", "models", "schema"},
    "page": {"page", "screen", "view"},
    "route": {"route", "router", "routing"},
    "service": {"service", "services"},
    "state_store": {"state", "store"},
    "template": {"html", "template"},
    "test": {"spec", "test", "tests"},
}
_SIGNAL_ORDER = {
    "framework_config": 0,
    "framework_adjacent": 1,
    "task_folder": 2,
    "role_relevant": 3,
    "generic_name": 4,
    "directory_shape": 5,
}


@dataclass(frozen=True, slots=True)
class ProbePoolEntry:
    path: str
    sources: tuple[str, ...]
    reasons: tuple[str, ...]
    obvious_rank: int | None
    rescue_rank: int | None
    from_obvious: bool
    from_rescue: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "sources": list(self.sources),
            "reasons": list(self.reasons),
            "obvious_rank": self.obvious_rank,
            "rescue_rank": self.rescue_rank,
            "from_obvious": self.from_obvious,
            "from_rescue": self.from_rescue,
        }


@dataclass(frozen=True, slots=True)
class ProbePool:
    entries: tuple[ProbePoolEntry, ...]
    files_considered: int
    max_total: int
    max_obvious: int
    max_rescue: int
    max_per_directory: int
    truncated: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "files_considered": self.files_considered,
            "pool_size": len(self.entries),
            "max_total": self.max_total,
            "max_obvious": self.max_obvious,
            "max_rescue": self.max_rescue,
            "max_per_directory": self.max_per_directory,
            "truncated": self.truncated,
            "entries": [entry.to_dict() for entry in self.entries],
        }


@dataclass(slots=True)
class _EntryBuilder:
    path: str
    sources: list[str]
    reasons: list[str]
    obvious_rank: int | None = None
    rescue_rank: int | None = None

    def add(self, source: str, reason: str) -> None:
        if source not in self.sources:
            self.sources.append(source)
        if reason not in self.reasons:
            self.reasons.append(reason)


def build_probe_pool(
    records: Iterable[InventoryRecord],
    task: str,
    obvious_paths: Iterable[str | Path] = (),
    *,
    max_total: int = DEFAULT_MAX_TOTAL,
    max_obvious: int = DEFAULT_MAX_OBVIOUS,
    max_rescue: int = DEFAULT_MAX_RESCUE,
    max_per_directory: int = DEFAULT_MAX_PER_DIRECTORY,
) -> ProbePool:
    """Combine current-engine paths with an independent structural rescue lane."""

    _validate_limit(max_total, "max_total")
    _validate_limit(max_obvious, "max_obvious")
    _validate_limit(max_rescue, "max_rescue")
    _validate_limit(max_per_directory, "max_per_directory")
    if not isinstance(task, str) or not task.strip():
        raise ValueError("task must be a non-empty string")
    task_tokens = _tokens(task) - _TASK_STOPWORDS
    inventory = _normalize_inventory(records)
    inventory_paths = set(inventory)
    obvious = _normalize_obvious_paths(obvious_paths, inventory_paths)

    builders: dict[str, _EntryBuilder] = {}
    selected_obvious = obvious[:max_obvious]
    for rank, path in enumerate(selected_obvious, start=1):
        builder = _builder(builders, path)
        builder.obvious_rank = rank
        builder.add("obvious", f"current engine rank {rank}")

    anchor_directories = {
        PurePosixPath(path).parent.parts
        for path in inventory
        if _is_framework_config(PurePosixPath(path).name.lower())
    }
    rescue_candidates: list[tuple[tuple[int, int, str], str, tuple[tuple[str, str], ...]]] = []
    for path in sorted(inventory):
        signals = _rescue_signals(path, task_tokens, anchor_directories)
        if not signals:
            continue
        priority = min(_SIGNAL_ORDER[source] for source, _reason in signals)
        rescue_candidates.append(((priority, -len(signals), path), path, signals))
    rescue_candidates.sort(key=lambda item: item[0])
    selected_rescue = rescue_candidates[:max_rescue]

    for rank, (_sort_key, path, signals) in enumerate(selected_rescue, start=1):
        builder = _builder(builders, path)
        builder.rescue_rank = rank
        for source, reason in signals:
            builder.add(source, reason)

    candidate_order = [*selected_obvious]
    candidate_order.extend(
        path
        for _sort_key, path, _signals in selected_rescue
        if path not in selected_obvious
    )
    candidate_order = list(dict.fromkeys(candidate_order))

    entries: list[ProbePoolEntry] = []
    per_directory: dict[str, int] = {}
    skipped_by_pool_caps = False
    for path in candidate_order:
        if len(entries) >= max_total:
            skipped_by_pool_caps = True
            break
        directory = PurePosixPath(path).parent.as_posix()
        if per_directory.get(directory, 0) >= max_per_directory:
            skipped_by_pool_caps = True
            continue
        per_directory[directory] = per_directory.get(directory, 0) + 1
        builder = builders[path]
        entries.append(
            ProbePoolEntry(
                path=path,
                sources=tuple(builder.sources),
                reasons=tuple(builder.reasons),
                obvious_rank=builder.obvious_rank,
                rescue_rank=builder.rescue_rank,
                from_obvious=builder.obvious_rank is not None,
                from_rescue=builder.rescue_rank is not None,
            )
        )

    return ProbePool(
        entries=tuple(entries),
        files_considered=len(inventory),
        max_total=max_total,
        max_obvious=max_obvious,
        max_rescue=max_rescue,
        max_per_directory=max_per_directory,
        truncated=(
            len(obvious) > max_obvious
            or len(rescue_candidates) > max_rescue
            or skipped_by_pool_caps
        ),
    )


def _rescue_signals(
    path: str,
    task_tokens: set[str],
    anchor_directories: set[tuple[str, ...]],
) -> tuple[tuple[str, str], ...]:
    pure_path = PurePosixPath(path)
    filename = pure_path.name.lower()
    stem_tokens = _tokens(pure_path.stem)
    folder_tokens = (
        set().union(*(_tokens(part) for part in pure_path.parts[:-1]))
        if len(pure_path.parts) > 1
        else set()
    )
    folders = {part.lower() for part in pure_path.parts[:-1]}
    signals: list[tuple[str, str]] = []

    if _is_framework_config(filename):
        signals.append(("framework_config", "known framework or config filename"))
    elif any(
        _directory_distance(pure_path.parent.parts, anchor_directory) <= 1
        for anchor_directory in anchor_directories
    ):
        signals.append(("framework_adjacent", "near a framework or config anchor"))

    matching_folders = sorted(task_tokens & folder_tokens)
    if matching_folders:
        signals.append(
            ("task_folder", f"folder matches task term '{matching_folders[0]}'")
        )

    role = _path_role(path, stem_tokens, folders)
    if role is not None and task_tokens & _ROLE_TASK_TERMS[role]:
        signals.append(("role_relevant", f"path role '{role}' matches task"))

    normalized_stem = pure_path.stem.lower().split(".", 1)[0]
    if normalized_stem in _GENERIC_STEMS:
        signals.append(("generic_name", f"generic structural filename '{filename}'"))

    matching_shape = sorted(folders & _SOURCE_DIRECTORY_NAMES)
    if matching_shape:
        signals.append(
            ("directory_shape", f"source directory shape includes '{matching_shape[0]}'")
        )
    return tuple(signals)


def _path_role(
    path: str,
    stem_tokens: set[str],
    folders: set[str],
) -> str | None:
    frontend_role = infer_frontend_role_from_path(path)
    if frontend_role in _ROLE_TASK_TERMS:
        return frontend_role
    if stem_tokens & {"service"} or "services" in folders:
        return "service"
    if stem_tokens & {"api", "client", "request"} or folders & {"api", "client"}:
        return "api_client"
    if stem_tokens & {"helper", "helpers", "util", "utils", "utility"}:
        return "helper"
    if stem_tokens & {"model", "models", "schema"}:
        return "model"
    if stem_tokens & {"config", "configuration"}:
        return "config"
    if stem_tokens & {"route", "router", "routes", "routing"}:
        return "route"
    if stem_tokens & {"test", "spec"} or folders & {"test", "tests"}:
        return "test"
    return None


def _normalize_inventory(
    records: Iterable[InventoryRecord],
) -> dict[str, InventoryRecord]:
    normalized: dict[str, InventoryRecord] = {}
    for index, record in enumerate(records):
        if not isinstance(record, InventoryRecord):
            raise TypeError(f"records[{index}] must be an InventoryRecord")
        path = _normalize_path(record.path, f"records[{index}].path")
        normalized.setdefault(path, record)
    return normalized


def _normalize_obvious_paths(
    paths: Iterable[str | Path], inventory_paths: set[str]
) -> tuple[str, ...]:
    if isinstance(paths, (str, Path)):
        raise TypeError("obvious_paths must be an iterable of paths")
    result: list[str] = []
    for index, value in enumerate(paths):
        path = _normalize_path(value, f"obvious_paths[{index}]")
        if path in inventory_paths and path not in result:
            result.append(path)
    return tuple(result)


def _normalize_path(value: str | Path, location: str) -> str:
    if not isinstance(value, (str, Path)):
        raise TypeError(f"{location} must be a string or Path")
    raw_path = str(value)
    if not raw_path or raw_path != raw_path.strip():
        raise ValueError(f"{location} must be a non-empty path without outer whitespace")
    normalized = raw_path.replace("\\", "/")
    path = PurePosixPath(normalized)
    windows_path = PureWindowsPath(raw_path)
    if path.is_absolute() or windows_path.is_absolute() or windows_path.drive:
        raise ValueError(f"{location} must be relative")
    if ".." in path.parts:
        raise ValueError(f"{location} must not escape its root with '..'")
    normalized = path.as_posix()
    if normalized == ".":
        raise ValueError(f"{location} must name a file")
    return normalized


def _builder(builders: dict[str, _EntryBuilder], path: str) -> _EntryBuilder:
    if path not in builders:
        builders[path] = _EntryBuilder(path=path, sources=[], reasons=[])
    return builders[path]


def _is_framework_config(filename: str) -> bool:
    return filename in _FRAMEWORK_CONFIG_NAMES or filename.startswith(
        _FRAMEWORK_CONFIG_PREFIXES
    )


def _directory_distance(left: tuple[str, ...], right: tuple[str, ...]) -> int:
    common = 0
    for left_part, right_part in zip(left, right):
        if left_part.lower() != right_part.lower():
            break
        common += 1
    return (len(left) - common) + (len(right) - common)


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", str(value).lower()))


def _validate_limit(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
