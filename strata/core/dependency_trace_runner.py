"""Direct-edge extraction orchestration for selected repository seed files."""

from pathlib import Path, PurePosixPath
from typing import Iterable

from strata.core.dependency_tracing import (
    DependencyEdge,
    DependencyTraceReport,
    merge_dependency_edges,
    normalize_relative_path,
)
from strata.core.js_ts_dependency_edges import (
    JS_TS_EXTENSIONS,
    extract_js_ts_import_edges,
)
from strata.core.python_dependency_edges import extract_python_import_edges
from strata.core.stage_report import StageReport


DEFAULT_MAX_SEED_FILES = 20
SUPPORTED_SEED_EXTENSIONS = (".py", *JS_TS_EXTENSIONS)


def run_dependency_trace(
    repo_root: str | Path,
    seed_files: Iterable[str | Path],
    *,
    max_seed_files: int | None = DEFAULT_MAX_SEED_FILES,
    supported_extensions: Iterable[str] | None = None,
) -> DependencyTraceReport:
    """Extract and merge direct dependency edges from selected seed files only."""

    root = _validate_root(repo_root)
    _validate_max_seed_files(max_seed_files)
    extension_policy = _normalize_extension_policy(supported_extensions)
    normalized_seeds, initial_skips = _normalize_seed_files(seed_files)

    if max_seed_files is None:
        selected_seeds = normalized_seeds
        capped_seeds: tuple[str, ...] = ()
    else:
        selected_seeds = normalized_seeds[:max_seed_files]
        capped_seeds = normalized_seeds[max_seed_files:]

    edges: list[DependencyEdge] = []
    skipped_items = list(initial_skips)
    skipped_items.extend(f"seed cap exceeded: {seed}" for seed in capped_seeds)
    warnings: list[str] = []
    bytes_read = 0
    files_touched = 0
    elapsed_ms = 0.0
    inspected_seed_count = 0

    for seed in selected_seeds:
        extension = PurePosixPath(seed).suffix.lower()
        if extension not in extension_policy:
            skipped_items.append(f"unsupported seed extension: {seed}")
            continue
        try:
            child_report = _extract_seed(root, seed, extension)
        except FileNotFoundError:
            skipped_items.append(f"missing seed file: {seed}")
            continue
        except ValueError:
            skipped_items.append(f"unsafe seed file: {seed}")
            continue
        except OSError as error:
            skipped_items.append(f"unreadable seed file: {seed}")
            warnings.append(f"{seed}: {type(error).__name__}")
            continue

        inspected_seed_count += 1
        edges.extend(child_report.edges)
        skipped_items.extend(
            f"{seed}: {item}" for item in child_report.skipped_items
        )
        warnings.extend(f"{seed}: {warning}" for warning in child_report.warnings)
        if child_report.stage_report is not None:
            bytes_read += child_report.stage_report.bytes_read
            files_touched += child_report.stage_report.files_touched
            elapsed_ms += child_report.stage_report.elapsed_ms

    merged_edges = merge_dependency_edges(edges)
    stable_skips = tuple(sorted(set(skipped_items)))
    stable_warnings = tuple(sorted(set(warnings)))
    stage_report = StageReport(
        "dependency_trace_runner",
        inputs={
            "max_seed_files": max_seed_files,
            "normalized_seed_count": len(normalized_seeds),
            "supported_extensions": extension_policy,
        },
        outputs={
            "edge_count": len(merged_edges),
            "inspected_seed_count": inspected_seed_count,
            "selected_seed_count": len(selected_seeds),
        },
        metrics={
            "estimated_edge_cost": sum(
                edge.estimated_cost for edge in merged_edges
            ),
        },
        warnings=stable_warnings,
        skipped_items=stable_skips,
        confidence="medium" if stable_skips or stable_warnings else "high",
        elapsed_ms=elapsed_ms,
        bytes_read=bytes_read,
        files_touched=files_touched,
    )
    return DependencyTraceReport(
        seed_files=selected_seeds,
        edges=merged_edges,
        skipped_items=stable_skips,
        warnings=stable_warnings,
        stage_report=stage_report,
    )


def _extract_seed(
    root: Path,
    seed: str,
    extension: str,
) -> DependencyTraceReport:
    if extension == ".py":
        return extract_python_import_edges(root, seed)
    return extract_js_ts_import_edges(root, seed)


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
            raise ValueError(f"unsupported trace extension policy: {value}")
        normalized.add(extension)
    return tuple(
        extension
        for extension in SUPPORTED_SEED_EXTENSIONS
        if extension in normalized
    )


def _validate_max_seed_files(value: int | None) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("max_seed_files must be an integer or None")
    if value <= 0:
        raise ValueError("max_seed_files must be greater than zero")


def _validate_root(repo_root: str | Path) -> Path:
    root = Path(repo_root)
    if not root.exists():
        raise FileNotFoundError(f"repository root does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"repository root is not a directory: {root}")
    return root.resolve()
