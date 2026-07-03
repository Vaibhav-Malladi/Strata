"""Fixture-level comparison of baseline, mixed, and probed candidate strategies."""

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from strata.core.candidate_baseline import run_candidate_baseline_task
from strata.core.candidate_evaluation import (
    CandidateEvaluationTask,
    load_candidate_evaluation_manifest,
)
from strata.core.candidate_metrics import (
    CandidateQualityMetrics,
    calculate_candidate_quality_metrics,
)
from strata.core.content_probe import (
    DEFAULT_CONTENT_PROBE_CAPS,
    ContentProbeCaps,
    ContentProbeResult,
    probe_content,
)
from strata.core.inventory import collect_inventory
from strata.core.probe_pool import ProbePool, ProbePoolEntry, build_probe_pool
from strata.core.probe_scoring import (
    ProbeScoreResult,
    score_probe_entry,
    sort_probe_scores,
)
from strata.core.stage_report import StageReport


PROBE_EVALUATION_REPORT_VERSION = 1
STRATEGIES = ("baseline", "mixed_pool", "mixed_pool_probe")
_RESCUE_SOURCES = {
    "framework_config",
    "framework_adjacent",
    "task_folder",
    "role_relevant",
    "generic_name",
    "directory_shape",
}


@dataclass(frozen=True, slots=True)
class ProbeStrategyTaskReport:
    fixture_name: str
    task_id: str
    task_text: str
    strategy: str
    k: int
    selected_paths: tuple[str, ...]
    metrics: CandidateQualityMetrics
    stage_report: StageReport
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Return a stable JSON-ready strategy result."""

        return {
            "fixture_name": self.fixture_name,
            "task_id": self.task_id,
            "task_text": self.task_text,
            "strategy": self.strategy,
            "k": self.k,
            "selected_paths": list(self.selected_paths),
            "metrics": self.metrics.to_dict(),
            "stage_report": self.stage_report.to_dict(),
            "notes": list(self.notes),
        }


@dataclass(frozen=True, slots=True)
class ProbeStrategySummary:
    strategy: str
    task_count: int
    average_critical_recall: float
    total_missed_critical_count: int
    average_useful_coverage: float
    average_distractor_rate: float
    average_context_waste: float
    total_bytes_read: int
    total_files_touched: int
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a stable JSON-ready aggregate strategy summary."""

        return {
            "strategy": self.strategy,
            "task_count": self.task_count,
            "average_critical_recall": self.average_critical_recall,
            "total_missed_critical_count": self.total_missed_critical_count,
            "average_useful_coverage": self.average_useful_coverage,
            "average_distractor_rate": self.average_distractor_rate,
            "average_context_waste": self.average_context_waste,
            "total_bytes_read": self.total_bytes_read,
            "total_files_touched": self.total_files_touched,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class ProbeCostAssessment:
    earned_cost: bool
    compared_to: str
    added_bytes_read: int
    added_files_touched: int
    reason: str

    def to_dict(self) -> dict[str, str | bool | int]:
        return {
            "earned_cost": self.earned_cost,
            "compared_to": self.compared_to,
            "added_bytes_read": self.added_bytes_read,
            "added_files_touched": self.added_files_touched,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class ProbeEvaluationReport:
    report_version: int
    k: int
    task_reports: tuple[ProbeStrategyTaskReport, ...]
    strategy_summaries: tuple[ProbeStrategySummary, ...]
    probe_cost_assessment: ProbeCostAssessment

    def to_dict(self) -> dict[str, Any]:
        """Return a stable JSON-ready comparison report."""

        return {
            "report_version": self.report_version,
            "k": self.k,
            "task_count": len(self.task_reports) // len(STRATEGIES),
            "strategies": list(STRATEGIES),
            "results": [report.to_dict() for report in self.task_reports],
            "strategy_summaries": [
                summary.to_dict() for summary in self.strategy_summaries
            ],
            "probe_cost_assessment": self.probe_cost_assessment.to_dict(),
        }


def evaluate_probe_strategies_for_task(
    fixture_name: str,
    fixture_root: str | Path,
    task: CandidateEvaluationTask,
    k: int,
    *,
    probe_caps: ContentProbeCaps = DEFAULT_CONTENT_PROBE_CAPS,
) -> tuple[ProbeStrategyTaskReport, ...]:
    """Evaluate all three strategies for one fixture task."""

    baseline = run_candidate_baseline_task(fixture_name, fixture_root, task, k)
    baseline_report = ProbeStrategyTaskReport(
        fixture_name=fixture_name,
        task_id=task.task_id,
        task_text=task.task_text,
        strategy="baseline",
        k=k,
        selected_paths=baseline.selected_paths,
        metrics=baseline.metrics,
        stage_report=baseline.stage_report,
        notes=("current engine reference",),
    )

    records = collect_inventory(fixture_root)
    pool = build_probe_pool(records, task.task_text, baseline.selected_paths)
    mixed_paths = tuple(entry.path for entry in pool.entries[:k])
    mixed_metrics = calculate_candidate_quality_metrics(task, mixed_paths, k)
    pool_warnings = ("mixed probe pool was capped",) if pool.truncated else ()
    mixed_stage = StageReport(
        stage_name="mixed_pool",
        inputs={"fixture_name": fixture_name, "task_id": task.task_id, "k": k},
        outputs={"pool_size": len(pool.entries), "selected_paths": mixed_paths},
        metrics=mixed_metrics.to_dict(),
        warnings=pool_warnings,
        confidence="high",
        elapsed_ms=0.0,
        bytes_read=0,
        files_touched=len(records),
    )
    mixed_report = ProbeStrategyTaskReport(
        fixture_name=fixture_name,
        task_id=task.task_id,
        task_text=task.task_text,
        strategy="mixed_pool",
        k=k,
        selected_paths=mixed_paths,
        metrics=mixed_metrics,
        stage_report=mixed_stage,
        notes=_selection_notes(mixed_paths, baseline.selected_paths),
    )

    content_result = probe_content(
        fixture_root,
        pool,
        task.task_text,
        caps=probe_caps,
    )
    scored = score_probe_pool_entries(pool, content_result)
    probe_paths = tuple(result.path for result in scored[:k])
    probe_metrics = calculate_candidate_quality_metrics(task, probe_paths, k)
    probe_warnings = tuple(
        dict.fromkeys((*pool_warnings, *content_result.stage_report.warnings))
    )
    probe_stage = StageReport(
        stage_name="mixed_pool_probe",
        inputs={
            "fixture_name": fixture_name,
            "task_id": task.task_id,
            "k": k,
            "probe_caps": probe_caps.to_dict(),
        },
        outputs={"pool_size": len(pool.entries), "selected_paths": probe_paths},
        metrics=probe_metrics.to_dict(),
        warnings=probe_warnings,
        skipped_items=content_result.stage_report.skipped_items,
        confidence=content_result.stage_report.confidence,
        elapsed_ms=content_result.stage_report.elapsed_ms,
        bytes_read=content_result.stage_report.bytes_read,
        files_touched=len(records) + content_result.stage_report.files_touched,
    )
    probe_report = ProbeStrategyTaskReport(
        fixture_name=fixture_name,
        task_id=task.task_id,
        task_text=task.task_text,
        strategy="mixed_pool_probe",
        k=k,
        selected_paths=probe_paths,
        metrics=probe_metrics,
        stage_report=probe_stage,
        notes=_selection_notes(probe_paths, baseline.selected_paths),
    )
    return baseline_report, mixed_report, probe_report


def score_probe_pool_entries(
    pool: ProbePool,
    content_result: ContentProbeResult,
) -> tuple[ProbeScoreResult, ...]:
    """Map G6/G8 evidence into G7 components and deterministic scores."""

    if not isinstance(pool, ProbePool):
        raise TypeError("pool must be a ProbePool")
    if not isinstance(content_result, ContentProbeResult):
        raise TypeError("content_result must be a ContentProbeResult")
    content_by_path = {result.path: result for result in content_result.files}
    scored: list[ProbeScoreResult] = []
    for entry in pool.entries:
        content = content_by_path[entry.path]
        scored.append(
            score_probe_entry(
                entry.path,
                cheap_relevance=_cheap_relevance(entry, pool),
                probe_relevance=content.probe_relevance,
                structural_relevance=_structural_relevance(entry),
                normalized_cost=min(
                    1.0,
                    content.bytes_read / content_result.caps.max_bytes_per_file,
                ),
                confidence=content.confidence,
            )
        )
    return sort_probe_scores(scored)


def run_probe_evaluation_suite(
    fixtures_root: str | Path,
    k: int,
    *,
    probe_caps: ContentProbeCaps = DEFAULT_CONTENT_PROBE_CAPS,
) -> ProbeEvaluationReport:
    """Compare all strategies for every manifest task under a fixture root."""

    root = Path(fixtures_root)
    if not root.exists():
        raise FileNotFoundError(f"probe evaluation fixture directory does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"probe evaluation root is not a directory: {root}")
    manifest_paths = tuple(sorted(root.glob("*/manifest.json")))
    if not manifest_paths:
        raise ValueError(f"probe evaluation fixture directory has no manifests: {root}")

    task_reports: list[ProbeStrategyTaskReport] = []
    for manifest_path in manifest_paths:
        manifest = load_candidate_evaluation_manifest(manifest_path)
        fixture_name = manifest_path.parent.name
        for task in manifest.tasks:
            fixture_root = manifest_path.parent.joinpath(
                *PurePosixPath(task.fixture_path).parts
            )
            task_reports.extend(
                evaluate_probe_strategies_for_task(
                    fixture_name,
                    fixture_root,
                    task,
                    k,
                    probe_caps=probe_caps,
                )
            )
    if not task_reports:
        raise ValueError(f"probe evaluation manifests contain no tasks: {root}")

    summaries = tuple(
        _summarize_strategy(strategy, task_reports) for strategy in STRATEGIES
    )
    summary_by_strategy = {summary.strategy: summary for summary in summaries}
    assessment = _assess_probe_cost(
        summary_by_strategy["mixed_pool"],
        summary_by_strategy["mixed_pool_probe"],
    )
    return ProbeEvaluationReport(
        report_version=PROBE_EVALUATION_REPORT_VERSION,
        k=k,
        task_reports=tuple(task_reports),
        strategy_summaries=summaries,
        probe_cost_assessment=assessment,
    )


def _cheap_relevance(entry: ProbePoolEntry, pool: ProbePool) -> float:
    if entry.obvious_rank is None:
        return 0.0
    return max(0.0, 1.0 - (entry.obvious_rank - 1) / pool.max_obvious)


def _structural_relevance(entry: ProbePoolEntry) -> float:
    rescue_sources = _RESCUE_SOURCES & set(entry.sources)
    return len(rescue_sources) / len(_RESCUE_SOURCES)


def _selection_notes(
    selected_paths: tuple[str, ...],
    baseline_paths: tuple[str, ...],
) -> tuple[str, ...]:
    if selected_paths == baseline_paths:
        return ("selection matches baseline",)
    return ("selection differs from baseline",)


def _summarize_strategy(
    strategy: str,
    reports: list[ProbeStrategyTaskReport],
) -> ProbeStrategySummary:
    selected = [report for report in reports if report.strategy == strategy]
    count = len(selected)
    warnings = tuple(
        dict.fromkeys(
            warning
            for report in selected
            for warning in report.stage_report.warnings
        )
    )
    return ProbeStrategySummary(
        strategy=strategy,
        task_count=count,
        average_critical_recall=sum(
            report.metrics.critical_recall_at_k for report in selected
        )
        / count,
        total_missed_critical_count=sum(
            report.metrics.missed_critical_count for report in selected
        ),
        average_useful_coverage=sum(
            report.metrics.useful_coverage_at_k for report in selected
        )
        / count,
        average_distractor_rate=sum(
            report.metrics.distractor_rate_at_k for report in selected
        )
        / count,
        average_context_waste=sum(
            report.metrics.context_waste_at_k for report in selected
        )
        / count,
        total_bytes_read=sum(report.stage_report.bytes_read for report in selected),
        total_files_touched=sum(
            report.stage_report.files_touched for report in selected
        ),
        warnings=warnings,
    )


def _assess_probe_cost(
    mixed: ProbeStrategySummary,
    probe: ProbeStrategySummary,
) -> ProbeCostAssessment:
    added_bytes = probe.total_bytes_read - mixed.total_bytes_read
    added_files = probe.total_files_touched - mixed.total_files_touched
    earned = False
    reason = "probe quality did not improve enough over mixed_pool"
    if probe.average_critical_recall > mixed.average_critical_recall + 1e-12:
        earned = True
        reason = "probe improved average critical recall"
    elif probe.total_missed_critical_count < mixed.total_missed_critical_count:
        earned = True
        reason = "probe reduced missed critical files"
    elif (
        abs(probe.average_critical_recall - mixed.average_critical_recall) <= 1e-12
        and probe.average_useful_coverage > mixed.average_useful_coverage + 1e-12
        and probe.average_context_waste <= mixed.average_context_waste + 1e-12
    ):
        earned = True
        reason = "probe improved useful coverage without increasing context waste"
    return ProbeCostAssessment(
        earned_cost=earned,
        compared_to="mixed_pool",
        added_bytes_read=added_bytes,
        added_files_touched=added_files,
        reason=reason,
    )
