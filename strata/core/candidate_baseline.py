"""Baseline reporting for the current candidate-selection engine."""

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from strata.core.candidate_evaluation import (
    CandidateEvaluationTask,
    load_candidate_evaluation_manifest,
)
from strata.core.candidate_metrics import (
    CandidateQualityMetrics,
    calculate_candidate_quality_metrics,
)
from strata.core.candidate_pipeline import analyze_candidates_for_task
from strata.core.stage_report import StageReport, elapsed_milliseconds


BASELINE_REPORT_VERSION = 1
BASELINE_ENGINE_NAME = "current_candidate_selection"


@dataclass(frozen=True, slots=True)
class CandidateBaselineTaskReport:
    fixture_name: str
    task_id: str
    task_text: str
    k: int
    selected_paths: tuple[str, ...]
    metrics: CandidateQualityMetrics
    stage_report: StageReport

    def to_dict(self) -> dict[str, Any]:
        """Return a stable JSON-ready task report."""

        return {
            "fixture_name": self.fixture_name,
            "task_id": self.task_id,
            "task_text": self.task_text,
            "k": self.k,
            "selected_paths": list(self.selected_paths),
            "metrics": self.metrics.to_dict(),
            "stage_report": self.stage_report.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class CandidateBaselineReport:
    report_version: int
    engine: str
    k: int
    task_reports: tuple[CandidateBaselineTaskReport, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a stable JSON-ready aggregate baseline report."""

        return {
            "report_version": self.report_version,
            "engine": self.engine,
            "k": self.k,
            "task_count": len(self.task_reports),
            "tasks": [report.to_dict() for report in self.task_reports],
        }


def run_candidate_baseline_task(
    fixture_name: str,
    fixture_root: str | Path,
    task: CandidateEvaluationTask,
    k: int,
    *,
    clock_ns: Callable[[], int] | None = None,
) -> CandidateBaselineTaskReport:
    """Measure the unchanged candidate engine for one fixture task."""

    if not isinstance(fixture_name, str) or not fixture_name.strip():
        raise ValueError("fixture_name must be a non-empty string")
    if not isinstance(task, CandidateEvaluationTask):
        raise TypeError("task must be a CandidateEvaluationTask")

    root = Path(fixture_root)
    _validate_fixture_repo(root, fixture_name, task.task_id)
    start_ns = clock_ns() if clock_ns is not None else None

    analysis = analyze_candidates_for_task(
        root,
        task.task_text,
        candidate_limit=k,
    )
    selected_paths = tuple(
        _portable_relative_path(candidate.path)
        for candidate in analysis.selection.candidates
    )
    metrics = calculate_candidate_quality_metrics(task, selected_paths, k)

    elapsed_ms = 0.0
    if clock_ns is not None and start_ns is not None:
        elapsed_ms = elapsed_milliseconds(start_ns, clock_ns())

    warnings = ()
    if analysis.selection.truncated:
        warnings = (f"candidate selection was capped at K={k}",)

    stage_report = StageReport(
        stage_name="candidate_baseline",
        inputs={
            "fixture_name": fixture_name,
            "task_id": task.task_id,
            "task_text": task.task_text,
            "k": k,
        },
        outputs={
            "files_considered": analysis.selection.files_considered,
            "selected_paths": selected_paths,
            "selection_truncated": analysis.selection.truncated,
        },
        metrics=metrics.to_dict(),
        warnings=warnings,
        confidence="high",
        elapsed_ms=elapsed_ms,
        bytes_read=0,
        files_touched=analysis.inventory_records_count,
    )
    return CandidateBaselineTaskReport(
        fixture_name=fixture_name,
        task_id=task.task_id,
        task_text=task.task_text,
        k=k,
        selected_paths=selected_paths,
        metrics=metrics,
        stage_report=stage_report,
    )


def run_candidate_baseline_suite(
    fixtures_root: str | Path,
    k: int,
    *,
    clock_ns: Callable[[], int] | None = None,
) -> CandidateBaselineReport:
    """Run every manifest task under a candidate-quality fixture directory."""

    root = Path(fixtures_root)
    _validate_fixture_directory(root)
    manifest_paths = tuple(sorted(root.glob("*/manifest.json")))
    if not manifest_paths:
        raise ValueError(
            f"candidate baseline fixture directory contains no manifests: {root}"
        )

    task_reports: list[CandidateBaselineTaskReport] = []
    for manifest_path in manifest_paths:
        fixture_name = manifest_path.parent.name
        manifest = load_candidate_evaluation_manifest(manifest_path)
        for task in manifest.tasks:
            fixture_root = manifest_path.parent.joinpath(
                *PurePosixPath(task.fixture_path).parts
            )
            task_reports.append(
                run_candidate_baseline_task(
                    fixture_name,
                    fixture_root,
                    task,
                    k,
                    clock_ns=clock_ns,
                )
            )

    if not task_reports:
        raise ValueError(
            f"candidate baseline fixture manifests contain no tasks: {root}"
        )
    return CandidateBaselineReport(
        report_version=BASELINE_REPORT_VERSION,
        engine=BASELINE_ENGINE_NAME,
        k=k,
        task_reports=tuple(task_reports),
    )


def _portable_relative_path(path: str) -> str:
    return PurePosixPath(path.replace("\\", "/")).as_posix()


def _validate_fixture_directory(root: Path) -> None:
    if not root.exists():
        raise FileNotFoundError(
            f"candidate baseline fixture directory does not exist: {root}"
        )
    if not root.is_dir():
        raise NotADirectoryError(
            f"candidate baseline fixture path is not a directory: {root}"
        )


def _validate_fixture_repo(root: Path, fixture_name: str, task_id: str) -> None:
    if not root.exists():
        raise FileNotFoundError(
            f"fixture repo does not exist for {fixture_name}/{task_id}: {root}"
        )
    if not root.is_dir():
        raise NotADirectoryError(
            f"fixture repo is not a directory for {fixture_name}/{task_id}: {root}"
        )
