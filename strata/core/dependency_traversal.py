"""Deterministic priority-bounded traversal over direct dependency edges."""

import heapq
import math
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from strata.core.dependency_trace_runner import (
    SUPPORTED_SEED_EXTENSIONS,
    run_dependency_trace,
)
from strata.core.dependency_priority import (
    DEFAULT_MAX_DEPTH,
    DEFAULT_MAX_EDGES,
    DEFAULT_MAX_ESTIMATED_COST,
    DEFAULT_MAX_FILES,
    traversal_order_key,
)
from strata.core.dependency_tracing import (
    DependencyEdge,
    DependencyTraceReport,
    merge_dependency_edges,
    normalize_relative_path,
)
from strata.core.stage_report import StageReport


_SEED_PRIORITY = -1


@dataclass(frozen=True, slots=True)
class DependencyTraversalReport:
    """H1 trace report plus deterministic visit order and depth metadata."""

    trace_report: DependencyTraceReport
    visited_files: tuple[str, ...] = ()
    file_depths: Mapping[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.trace_report, DependencyTraceReport):
            raise TypeError("trace_report must be a DependencyTraceReport")
        visited = tuple(normalize_relative_path(path) for path in self.visited_files)
        if len(visited) != len(set(visited)):
            raise ValueError("visited_files must not contain duplicates")
        object.__setattr__(self, "visited_files", visited)

        if not isinstance(self.file_depths, Mapping):
            raise TypeError("file_depths must be a mapping")
        normalized_depths: dict[str, int] = {}
        for path, depth in self.file_depths.items():
            normalized_path = normalize_relative_path(path)
            if isinstance(depth, bool) or not isinstance(depth, int) or depth < 0:
                raise ValueError("file depths must be non-negative integers")
            normalized_depths[normalized_path] = depth
        if set(normalized_depths) != set(visited):
            raise ValueError("file_depths must contain every visited file exactly once")
        object.__setattr__(
            self,
            "file_depths",
            MappingProxyType(dict(sorted(normalized_depths.items()))),
        )

    @property
    def seed_files(self) -> tuple[str, ...]:
        return self.trace_report.seed_files

    @property
    def edges(self) -> tuple[DependencyEdge, ...]:
        return self.trace_report.edges

    @property
    def skipped_items(self) -> tuple[str, ...]:
        return self.trace_report.skipped_items

    @property
    def warnings(self) -> tuple[str, ...]:
        return self.trace_report.warnings

    @property
    def stage_report(self) -> StageReport | None:
        return self.trace_report.stage_report

    def to_dict(self) -> dict[str, Any]:
        """Return a stable JSON-ready traversal representation."""

        payload = self.trace_report.to_dict()
        return {
            "seed_files": payload["seed_files"],
            "visited_files": list(self.visited_files),
            "file_depths": dict(self.file_depths),
            "edges": payload["edges"],
            "skipped_items": payload["skipped_items"],
            "warnings": payload["warnings"],
            "stage_report": payload["stage_report"],
        }


def traverse_dependencies(
    repo_root: str | Path,
    seed_files: Iterable[str | Path],
    *,
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_files: int = DEFAULT_MAX_FILES,
    max_edges: int = DEFAULT_MAX_EDGES,
    max_estimated_cost: int | float | None = DEFAULT_MAX_ESTIMATED_COST,
    supported_extensions: Iterable[str] | None = None,
) -> DependencyTraversalReport:
    """Follow direct edges in priority order within strict traversal caps."""

    root = _validate_root(repo_root)
    _validate_caps(max_depth, max_files, max_edges, max_estimated_cost)
    extension_policy = _normalize_extension_policy(supported_extensions)
    normalized_seeds, initial_skips = _normalize_seed_files(seed_files)

    skipped_items = list(initial_skips)
    warnings: list[str] = []
    accepted_seeds: list[str] = []
    frontier: list[tuple[int, float, int, str]] = []
    frontier_keys: dict[str, tuple[int, float, int]] = {}
    for seed in normalized_seeds:
        status = _source_status(root, seed, extension_policy)
        if status is not None:
            skipped_items.append(f"{status}: {seed}")
            continue
        accepted_seeds.append(seed)
        _offer_frontier(
            frontier,
            frontier_keys,
            seed,
            order_key=(_SEED_PRIORITY, 0.0, 0),
        )

    visited: list[str] = []
    visited_set: set[str] = set()
    file_depths: dict[str, int] = {}
    edges: list[DependencyEdge] = []
    edge_set: set[DependencyEdge] = set()
    estimated_cost = 0.0
    bytes_read = 0
    files_touched = 0
    elapsed_ms = 0.0
    stop_reason: str | None = None

    while frontier:
        priority, frontier_cost, depth, source_file = heapq.heappop(frontier)
        if frontier_keys.get(source_file) != (priority, frontier_cost, depth):
            continue
        del frontier_keys[source_file]
        if source_file in visited_set:
            continue
        if len(visited) >= max_files:
            skipped_items.extend(
                f"max_files cap reached: {path}"
                for path in sorted({source_file, *frontier_keys})
            )
            stop_reason = "max_files cap reached"
            break

        status = _source_status(root, source_file, extension_policy)
        if status is not None:
            skipped_items.append(f"{status}: {source_file}")
            continue

        visited.append(source_file)
        visited_set.add(source_file)
        file_depths[source_file] = depth
        if depth >= max_depth:
            continue

        child = run_dependency_trace(
            root,
            (source_file,),
            max_seed_files=1,
            supported_extensions=extension_policy,
        )
        skipped_items.extend(
            _qualify_message(source_file, item) for item in child.skipped_items
        )
        warnings.extend(
            _qualify_message(source_file, warning) for warning in child.warnings
        )
        if child.stage_report is not None:
            bytes_read += child.stage_report.bytes_read
            files_touched += child.stage_report.files_touched
            elapsed_ms += child.stage_report.elapsed_ms

        for edge in child.edges:
            if edge in edge_set:
                continue
            if len(edges) >= max_edges:
                stop_reason = "max_edges cap reached"
                break
            next_cost = estimated_cost + edge.estimated_cost
            if (
                max_estimated_cost is not None
                and next_cost > float(max_estimated_cost)
            ):
                stop_reason = "max_estimated_cost cap reached"
                break

            edges.append(edge)
            edge_set.add(edge)
            estimated_cost = next_cost
            target_extension = PurePosixPath(edge.target_file).suffix.lower()
            if target_extension not in extension_policy:
                skipped_items.append(
                    f"unsupported traversal target: {edge.target_file}"
                )
                continue
            _offer_frontier(
                frontier,
                frontier_keys,
                edge.target_file,
                order_key=traversal_order_key(edge, depth + 1)[:3],
            )
            if len(edges) >= max_edges:
                stop_reason = "max_edges cap reached"
                break

        if stop_reason is not None:
            skipped_items.append(stop_reason)
            break

    merged_edges = merge_dependency_edges(edges)
    stable_skips = tuple(sorted(set(skipped_items)))
    stable_warnings = tuple(sorted(set(warnings)))
    visited_seed_files = tuple(
        seed for seed in accepted_seeds if seed in visited_set
    )
    stage_report = StageReport(
        "dependency_traversal",
        inputs={
            "max_depth": max_depth,
            "max_edges": max_edges,
            "max_estimated_cost": max_estimated_cost,
            "max_files": max_files,
            "supported_extensions": extension_policy,
        },
        outputs={
            "edge_count": len(merged_edges),
            "file_depths": file_depths,
            "visited_file_count": len(visited),
            "visited_files": visited,
        },
        metrics={"estimated_edge_cost": estimated_cost},
        warnings=stable_warnings,
        skipped_items=stable_skips,
        confidence="medium" if stable_skips or stable_warnings else "high",
        elapsed_ms=elapsed_ms,
        bytes_read=bytes_read,
        files_touched=files_touched,
    )
    trace_report = DependencyTraceReport(
        seed_files=visited_seed_files,
        edges=merged_edges,
        skipped_items=stable_skips,
        warnings=stable_warnings,
        stage_report=stage_report,
    )
    return DependencyTraversalReport(
        trace_report=trace_report,
        visited_files=tuple(visited),
        file_depths=file_depths,
    )


def _offer_frontier(
    frontier: list[tuple[int, float, int, str]],
    frontier_keys: dict[str, tuple[int, float, int]],
    path: str,
    *,
    order_key: tuple[int, float, int],
) -> None:
    previous = frontier_keys.get(path)
    if previous is not None and previous <= order_key:
        return
    frontier_keys[path] = order_key
    heapq.heappush(frontier, (*order_key, path))


def _qualify_message(source_file: str, message: str) -> str:
    prefix = f"{source_file}: "
    return message if message.startswith(prefix) else f"{prefix}{message}"


def _source_status(
    root: Path,
    path: str,
    extension_policy: tuple[str, ...],
) -> str | None:
    pure_path = PurePosixPath(path)
    if pure_path.suffix.lower() not in extension_policy:
        return "unsupported traversal file"
    if "node_modules" in pure_path.parts:
        return "unsafe traversal file"
    candidate = root.joinpath(*pure_path.parts)
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except FileNotFoundError:
        return "missing traversal file"
    except (OSError, ValueError):
        return "unsafe traversal file"
    if not resolved.is_file():
        return "unsupported traversal file"
    return None


def _normalize_seed_files(
    seed_files: Iterable[str | Path],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if isinstance(seed_files, (str, bytes)):
        raise TypeError("seed_files must be an iterable of relative paths")
    try:
        values = tuple(seed_files)
    except TypeError as error:
        raise TypeError("seed_files must be an iterable of relative paths") from error

    normalized: set[str] = set()
    skipped: list[str] = []
    for value in values:
        if not isinstance(value, (str, Path)):
            raise TypeError("seed_files must contain only strings or Path values")
        raw_path = str(value)
        try:
            normalized.add(normalize_relative_path(raw_path))
        except (TypeError, ValueError):
            skipped.append(f"unsafe seed path: {raw_path!r}")
    return tuple(sorted(normalized)), tuple(sorted(set(skipped)))


def _normalize_extension_policy(
    supported_extensions: Iterable[str] | None,
) -> tuple[str, ...]:
    if supported_extensions is None:
        return SUPPORTED_SEED_EXTENSIONS
    if isinstance(supported_extensions, (str, bytes)):
        raise TypeError("supported_extensions must be an iterable of extensions")
    try:
        values = tuple(supported_extensions)
    except TypeError as error:
        raise TypeError(
            "supported_extensions must be an iterable of extensions"
        ) from error

    normalized: set[str] = set()
    for value in values:
        if not isinstance(value, str) or not value.startswith("."):
            raise ValueError("supported extensions must be dot-prefixed strings")
        extension = value.lower()
        if extension not in SUPPORTED_SEED_EXTENSIONS:
            raise ValueError(f"unsupported traversal extension policy: {value}")
        normalized.add(extension)
    return tuple(
        extension
        for extension in SUPPORTED_SEED_EXTENSIONS
        if extension in normalized
    )


def _validate_caps(
    max_depth: int,
    max_files: int,
    max_edges: int,
    max_estimated_cost: int | float | None,
) -> None:
    if isinstance(max_depth, bool) or not isinstance(max_depth, int):
        raise TypeError("max_depth must be an integer")
    if max_depth < 0:
        raise ValueError("max_depth must be non-negative")
    for name, value in (("max_files", max_files), ("max_edges", max_edges)):
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{name} must be an integer")
        if value <= 0:
            raise ValueError(f"{name} must be greater than zero")
    if max_estimated_cost is None:
        return
    if isinstance(max_estimated_cost, bool) or not isinstance(
        max_estimated_cost, (int, float)
    ):
        raise TypeError("max_estimated_cost must be a number or None")
    if not math.isfinite(float(max_estimated_cost)) or max_estimated_cost < 0:
        raise ValueError("max_estimated_cost must be finite and non-negative")


def _validate_root(repo_root: str | Path) -> Path:
    root = Path(repo_root)
    if not root.exists():
        raise FileNotFoundError(f"repository root does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"repository root is not a directory: {root}")
    return root.resolve()
