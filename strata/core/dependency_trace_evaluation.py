"""Evaluate bounded dependency tracing against Part G quality fixtures."""

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from strata.core.candidate_baseline import run_candidate_baseline_suite
from strata.core.candidate_evaluation import (
    CandidateEvaluationTask,
    load_candidate_evaluation_manifest,
)
from strata.core.candidate_metrics import (
    CandidateQualityMetrics,
    calculate_candidate_quality_metrics,
)
from strata.core.dependency_priority import (
    DEFAULT_MAX_DEPTH,
    DEFAULT_MAX_EDGES,
    DEFAULT_MAX_ESTIMATED_COST,
    DEFAULT_MAX_FILES,
)
from strata.core.dependency_trace_runner import SUPPORTED_SEED_EXTENSIONS
from strata.core.dependency_tracing import DependencyEdge
from strata.core.dependency_traversal import traverse_dependencies
from strata.core.stage_report import StageReport


TRACE_EVALUATION_REPORT_VERSION = 1
DEFAULT_TRACE_EVALUATION_K = 3
DEFAULT_TRACE_SEED_COUNT = 1


@dataclass(frozen=True, slots=True)
class CandidateQualityDelta:
    evaluated_count: int
    critical_recall_at_k: float
    useful_coverage_at_k: float
    distractor_rate_at_k: float
    missed_critical_count: int
    context_waste_at_k: float

    def to_dict(self) -> dict[str, int | float]:
        return {
            "evaluated_count": self.evaluated_count,
            "critical_recall_at_k": self.critical_recall_at_k,
            "useful_coverage_at_k": self.useful_coverage_at_k,
            "distractor_rate_at_k": self.distractor_rate_at_k,
            "missed_critical_count": self.missed_critical_count,
            "context_waste_at_k": self.context_waste_at_k,
        }


@dataclass(frozen=True, slots=True)
class DependencyTraceEvaluationTaskReport:
    fixture_name: str
    task_id: str
    task_text: str
    k: int
    baseline_selected_paths: tuple[str, ...]
    seed_files: tuple[str, ...]
    visited_files: tuple[str, ...]
    traced_edges: tuple[DependencyEdge, ...]
    metrics_before: CandidateQualityMetrics
    metrics_after: CandidateQualityMetrics
    deltas: CandidateQualityDelta
    stage_report: StageReport
    warnings: tuple[str, ...] = ()
    skipped_items: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_name": self.fixture_name,
            "task_id": self.task_id,
            "task_text": self.task_text,
            "k": self.k,
            "baseline_selected_paths": list(self.baseline_selected_paths),
            "seed_files": list(self.seed_files),
            "visited_files": list(self.visited_files),
            "traced_edges": [edge.to_dict() for edge in self.traced_edges],
            "metrics_before": self.metrics_before.to_dict(),
            "metrics_after": self.metrics_after.to_dict(),
            "deltas": self.deltas.to_dict(),
            "stage_report": self.stage_report.to_dict(),
            "warnings": list(self.warnings),
            "skipped_items": list(self.skipped_items),
        }


@dataclass(frozen=True, slots=True)
class DependencyTraceAggregateSummary:
    task_count: int
    average_critical_recall_before: float
    average_critical_recall_after: float
    missed_critical_before: int
    missed_critical_after: int
    average_useful_coverage_before: float
    average_useful_coverage_after: float
    average_distractor_rate_before: float
    average_distractor_rate_after: float
    average_context_waste_before: float
    average_context_waste_after: float
    total_files_touched: int
    total_estimated_cost: float
    tracing_improved_quality: bool
    tracing_appears_to_earn_cost: bool
    conclusion: str

    def to_dict(self) -> dict[str, int | float | bool | str]:
        return {
            "task_count": self.task_count,
            "average_critical_recall_before": self.average_critical_recall_before,
            "average_critical_recall_after": self.average_critical_recall_after,
            "missed_critical_before": self.missed_critical_before,
            "missed_critical_after": self.missed_critical_after,
            "average_useful_coverage_before": self.average_useful_coverage_before,
            "average_useful_coverage_after": self.average_useful_coverage_after,
            "average_distractor_rate_before": self.average_distractor_rate_before,
            "average_distractor_rate_after": self.average_distractor_rate_after,
            "average_context_waste_before": self.average_context_waste_before,
            "average_context_waste_after": self.average_context_waste_after,
            "total_files_touched": self.total_files_touched,
            "total_estimated_cost": self.total_estimated_cost,
            "tracing_improved_quality": self.tracing_improved_quality,
            "tracing_appears_to_earn_cost": self.tracing_appears_to_earn_cost,
            "conclusion": self.conclusion,
        }


@dataclass(frozen=True, slots=True)
class DependencyTraceEvaluationReport:
    report_version: int
    k: int
    seed_count: int
    task_reports: tuple[DependencyTraceEvaluationTaskReport, ...]
    summary: DependencyTraceAggregateSummary
    stage_report: StageReport

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_version": self.report_version,
            "k": self.k,
            "seed_count": self.seed_count,
            "task_count": len(self.task_reports),
            "tasks": [report.to_dict() for report in self.task_reports],
            "summary": self.summary.to_dict(),
            "stage_report": self.stage_report.to_dict(),
        }


def evaluate_dependency_tracing(
    fixtures_root: str | Path,
    *,
    k: int = DEFAULT_TRACE_EVALUATION_K,
    seed_count: int = DEFAULT_TRACE_SEED_COUNT,
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_files: int = DEFAULT_MAX_FILES,
    max_edges: int = DEFAULT_MAX_EDGES,
    max_estimated_cost: int | float | None = DEFAULT_MAX_ESTIMATED_COST,
) -> DependencyTraceEvaluationReport:
    """Evaluate marginal bounded-trace quality from current baseline seeds."""

    _validate_positive_integer(k, "k")
    _validate_positive_integer(seed_count, "seed_count")
    root = Path(fixtures_root)
    if not root.exists():
        raise FileNotFoundError(f"trace evaluation fixtures do not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"trace evaluation fixtures are not a directory: {root}")

    baseline = run_candidate_baseline_suite(root, k)
    tasks = _load_fixture_tasks(root)
    task_reports: list[DependencyTraceEvaluationTaskReport] = []
    for baseline_task in baseline.task_reports:
        key = (baseline_task.fixture_name, baseline_task.task_id)
        task, fixture_root = tasks[key]
        seeds = _select_supported_seeds(
            baseline_task.selected_paths,
            limit=seed_count,
        )
        traversal = traverse_dependencies(
            fixture_root,
            seeds,
            max_depth=max_depth,
            max_files=max_files,
            max_edges=max_edges,
            max_estimated_cost=max_estimated_cost,
        )
        metrics_before = calculate_candidate_quality_metrics(task, seeds, k)
        metrics_after = calculate_candidate_quality_metrics(
            task,
            traversal.visited_files,
            k,
        )
        deltas = _metric_deltas(metrics_before, metrics_after)
        warnings = list(traversal.warnings)
        if not seeds:
            warnings.append("no supported baseline seed files")
        stable_warnings = tuple(sorted(set(warnings)))
        estimated_cost = float(
            traversal.stage_report.metrics["estimated_edge_cost"]
            if traversal.stage_report is not None
            else 0.0
        )
        stage_report = StageReport(
            "dependency_trace_evaluation_task",
            inputs={
                "fixture_name": baseline_task.fixture_name,
                "k": k,
                "seed_count": seed_count,
                "task_id": task.task_id,
            },
            outputs={
                "edge_count": len(traversal.edges),
                "seed_files": seeds,
                "visited_files": traversal.visited_files,
            },
            metrics={
                "deltas": deltas.to_dict(),
                "estimated_edge_cost": estimated_cost,
                "metrics_after": metrics_after.to_dict(),
                "metrics_before": metrics_before.to_dict(),
            },
            warnings=stable_warnings,
            skipped_items=traversal.skipped_items,
            confidence="medium",
            elapsed_ms=(
                traversal.stage_report.elapsed_ms
                if traversal.stage_report is not None
                else 0.0
            ),
            bytes_read=(
                traversal.stage_report.bytes_read
                if traversal.stage_report is not None
                else 0
            ),
            files_touched=(
                traversal.stage_report.files_touched
                if traversal.stage_report is not None
                else 0
            ),
        )
        task_reports.append(
            DependencyTraceEvaluationTaskReport(
                fixture_name=baseline_task.fixture_name,
                task_id=task.task_id,
                task_text=task.task_text,
                k=k,
                baseline_selected_paths=baseline_task.selected_paths,
                seed_files=seeds,
                visited_files=traversal.visited_files,
                traced_edges=traversal.edges,
                metrics_before=metrics_before,
                metrics_after=metrics_after,
                deltas=deltas,
                stage_report=stage_report,
                warnings=stable_warnings,
                skipped_items=traversal.skipped_items,
            )
        )

    reports = tuple(task_reports)
    summary = _aggregate_summary(reports)
    aggregate_warnings = tuple(
        sorted(
            {
                f"{report.fixture_name}/{report.task_id}: {warning}"
                for report in reports
                for warning in report.warnings
            }
        )
    )
    aggregate_skips = tuple(
        sorted(
            {
                f"{report.fixture_name}/{report.task_id}: {item}"
                for report in reports
                for item in report.skipped_items
            }
        )
    )
    stage_report = StageReport(
        "dependency_trace_evaluation",
        inputs={"k": k, "seed_count": seed_count},
        outputs={
            "conclusion": summary.conclusion,
            "task_count": len(reports),
        },
        metrics=summary.to_dict(),
        warnings=aggregate_warnings,
        skipped_items=aggregate_skips,
        confidence="medium",
        elapsed_ms=sum(report.stage_report.elapsed_ms for report in reports),
        bytes_read=sum(report.stage_report.bytes_read for report in reports),
        files_touched=summary.total_files_touched,
    )
    return DependencyTraceEvaluationReport(
        report_version=TRACE_EVALUATION_REPORT_VERSION,
        k=k,
        seed_count=seed_count,
        task_reports=reports,
        summary=summary,
        stage_report=stage_report,
    )


def _load_fixture_tasks(
    root: Path,
) -> dict[tuple[str, str], tuple[CandidateEvaluationTask, Path]]:
    tasks: dict[tuple[str, str], tuple[CandidateEvaluationTask, Path]] = {}
    for manifest_path in sorted(root.glob("*/manifest.json")):
        fixture_name = manifest_path.parent.name
        manifest = load_candidate_evaluation_manifest(manifest_path)
        for task in manifest.tasks:
            fixture_root = manifest_path.parent.joinpath(
                *PurePosixPath(task.fixture_path).parts
            )
            tasks[(fixture_name, task.task_id)] = (task, fixture_root)
    return tasks


def _select_supported_seeds(
    selected_paths: tuple[str, ...],
    *,
    limit: int,
) -> tuple[str, ...]:
    seeds = [
        path
        for path in selected_paths
        if PurePosixPath(path).suffix.lower() in SUPPORTED_SEED_EXTENSIONS
    ]
    return tuple(seeds[:limit])


def _metric_deltas(
    before: CandidateQualityMetrics,
    after: CandidateQualityMetrics,
) -> CandidateQualityDelta:
    return CandidateQualityDelta(
        evaluated_count=after.evaluated_count - before.evaluated_count,
        critical_recall_at_k=(
            after.critical_recall_at_k - before.critical_recall_at_k
        ),
        useful_coverage_at_k=(
            after.useful_coverage_at_k - before.useful_coverage_at_k
        ),
        distractor_rate_at_k=(
            after.distractor_rate_at_k - before.distractor_rate_at_k
        ),
        missed_critical_count=(
            after.missed_critical_count - before.missed_critical_count
        ),
        context_waste_at_k=after.context_waste_at_k - before.context_waste_at_k,
    )


def _aggregate_summary(
    reports: tuple[DependencyTraceEvaluationTaskReport, ...],
) -> DependencyTraceAggregateSummary:
    if not reports:
        raise ValueError("trace evaluation requires at least one task report")
    count = len(reports)
    critical_before = _average(
        report.metrics_before.critical_recall_at_k for report in reports
    )
    critical_after = _average(
        report.metrics_after.critical_recall_at_k for report in reports
    )
    useful_before = _average(
        report.metrics_before.useful_coverage_at_k for report in reports
    )
    useful_after = _average(
        report.metrics_after.useful_coverage_at_k for report in reports
    )
    distractor_before = _average(
        report.metrics_before.distractor_rate_at_k for report in reports
    )
    distractor_after = _average(
        report.metrics_after.distractor_rate_at_k for report in reports
    )
    waste_before = _average(
        report.metrics_before.context_waste_at_k for report in reports
    )
    waste_after = _average(
        report.metrics_after.context_waste_at_k for report in reports
    )
    missed_before = sum(
        report.metrics_before.missed_critical_count for report in reports
    )
    missed_after = sum(
        report.metrics_after.missed_critical_count for report in reports
    )
    total_cost = sum(
        float(report.stage_report.metrics["estimated_edge_cost"])
        for report in reports
    )
    quality_improved = (
        critical_after > critical_before
        or useful_after > useful_before
        or missed_after < missed_before
    )
    no_regression = (
        critical_after >= critical_before
        and missed_after <= missed_before
        and distractor_after <= distractor_before
        and waste_after <= waste_before
    )
    earns_cost = quality_improved and no_regression and total_cost > 0
    if earns_cost:
        conclusion = "tracing_improved_fixture_quality_with_bounded_cost"
    elif quality_improved:
        conclusion = "tracing_quality_gain_did_not_clearly_earn_cost"
    elif no_regression:
        conclusion = "tracing_did_not_improve_fixture_quality"
    else:
        conclusion = "tracing_regressed_fixture_quality"
    return DependencyTraceAggregateSummary(
        task_count=count,
        average_critical_recall_before=critical_before,
        average_critical_recall_after=critical_after,
        missed_critical_before=missed_before,
        missed_critical_after=missed_after,
        average_useful_coverage_before=useful_before,
        average_useful_coverage_after=useful_after,
        average_distractor_rate_before=distractor_before,
        average_distractor_rate_after=distractor_after,
        average_context_waste_before=waste_before,
        average_context_waste_after=waste_after,
        total_files_touched=sum(report.stage_report.files_touched for report in reports),
        total_estimated_cost=total_cost,
        tracing_improved_quality=quality_improved,
        tracing_appears_to_earn_cost=earns_cost,
        conclusion=conclusion,
    )


def _average(values: Any) -> float:
    collected = tuple(values)
    return sum(collected) / len(collected)


def _validate_positive_integer(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
