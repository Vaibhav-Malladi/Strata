"""Tier-aware quality metrics for ordered candidate file selections."""

from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Iterable

from strata.core.candidate_evaluation import (
    CandidateEvaluationManifest,
    CandidateEvaluationTask,
)


@dataclass(frozen=True, slots=True)
class CandidateQualityMetrics:
    task_id: str
    k: int
    evaluated_count: int
    critical_recall_at_k: float
    useful_coverage_at_k: float
    distractor_rate_at_k: float
    missed_critical_count: int
    context_waste_at_k: float

    def to_dict(self) -> dict[str, str | int | float]:
        """Return a stable JSON-ready representation of the metrics."""

        return {
            "task_id": self.task_id,
            "k": self.k,
            "evaluated_count": self.evaluated_count,
            "critical_recall_at_k": self.critical_recall_at_k,
            "useful_coverage_at_k": self.useful_coverage_at_k,
            "distractor_rate_at_k": self.distractor_rate_at_k,
            "missed_critical_count": self.missed_critical_count,
            "context_waste_at_k": self.context_waste_at_k,
        }


def calculate_candidate_quality_metrics(
    evaluation: CandidateEvaluationTask | CandidateEvaluationManifest,
    selected_paths: Iterable[str | Path],
    k: int,
    *,
    task_id: str | None = None,
) -> CandidateQualityMetrics:
    """Grade the first K unique selected paths against one evaluation task."""

    _validate_k(k)
    task = _resolve_task(evaluation, task_id)
    selected = _normalize_unique_paths(selected_paths, limit=k)
    selected_set = set(selected)

    critical = {item.path for item in task.expected_files.critical}
    useful = {item.path for item in task.expected_files.useful}
    distractor = {item.path for item in task.expected_files.distractor}
    irrelevant = {item.path for item in task.expected_files.irrelevant}
    classified = critical | useful | distractor | irrelevant

    selected_critical_count = len(selected_set & critical)
    selected_useful_count = len(selected_set & useful)
    selected_distractor_count = len(selected_set & distractor)
    selected_irrelevant_count = len(selected_set & irrelevant)
    selected_unknown_count = len(selected_set - classified)
    evaluated_count = len(selected)

    missed_critical_count = len(critical) - selected_critical_count
    return CandidateQualityMetrics(
        task_id=task.task_id,
        k=k,
        evaluated_count=evaluated_count,
        critical_recall_at_k=_coverage(selected_critical_count, len(critical)),
        useful_coverage_at_k=_coverage(selected_useful_count, len(useful)),
        distractor_rate_at_k=_rate(selected_distractor_count, evaluated_count),
        missed_critical_count=missed_critical_count,
        context_waste_at_k=_rate(
            selected_distractor_count
            + selected_irrelevant_count
            + selected_unknown_count,
            evaluated_count,
        ),
    )


def _resolve_task(
    evaluation: CandidateEvaluationTask | CandidateEvaluationManifest,
    task_id: str | None,
) -> CandidateEvaluationTask:
    if isinstance(evaluation, CandidateEvaluationTask):
        if task_id is not None and task_id != evaluation.task_id:
            raise ValueError(
                f"task_id {task_id!r} does not match task {evaluation.task_id!r}"
            )
        return evaluation

    if not isinstance(evaluation, CandidateEvaluationManifest):
        raise TypeError("evaluation must be a candidate-evaluation task or manifest")

    if task_id is not None:
        for task in evaluation.tasks:
            if task.task_id == task_id:
                return task
        raise ValueError(f"manifest does not contain task_id {task_id!r}")

    if len(evaluation.tasks) != 1:
        raise ValueError("task_id is required when a manifest does not contain one task")
    return evaluation.tasks[0]


def _normalize_unique_paths(
    paths: Iterable[str | Path],
    *,
    limit: int,
) -> tuple[str, ...]:
    if isinstance(paths, (str, Path)):
        raise TypeError("selected_paths must be an iterable of paths")

    try:
        iterator = iter(paths)
    except TypeError as error:
        raise TypeError("selected_paths must be an iterable of paths") from error

    normalized: list[str] = []
    seen: set[str] = set()
    for index, path in enumerate(iterator):
        candidate = _normalize_path(path, f"selected_paths[{index}]")
        if candidate in seen:
            continue
        seen.add(candidate)
        normalized.append(candidate)
        if len(normalized) >= limit:
            break
    return tuple(normalized)


def _normalize_path(value: str | Path, location: str) -> str:
    if not isinstance(value, (str, Path)):
        raise TypeError(f"{location} must be a string or Path")

    raw_path = str(value)
    if not raw_path or raw_path != raw_path.strip():
        raise ValueError(f"{location} must be a non-empty path without outer whitespace")

    normalized_separators = raw_path.replace("\\", "/")
    posix_path = PurePosixPath(normalized_separators)
    windows_path = PureWindowsPath(raw_path)
    if posix_path.is_absolute() or windows_path.is_absolute() or windows_path.drive:
        raise ValueError(f"{location} must be relative")
    if ".." in posix_path.parts:
        raise ValueError(f"{location} must not escape its root with '..'")

    normalized = posix_path.as_posix()
    if normalized == ".":
        raise ValueError(f"{location} must name a file")
    return normalized


def _coverage(selected_count: int, expected_count: int) -> float:
    if expected_count == 0:
        return 1.0
    return selected_count / expected_count


def _rate(selected_count: int, evaluated_count: int) -> float:
    if evaluated_count == 0:
        return 0.0
    return selected_count / evaluated_count


def _validate_k(k: int) -> None:
    if isinstance(k, bool) or not isinstance(k, int):
        raise TypeError("k must be an integer")
    if k <= 0:
        raise ValueError("k must be greater than zero")
