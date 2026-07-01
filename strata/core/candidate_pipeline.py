from dataclasses import dataclass
from pathlib import Path

from strata.core.candidates import (
    DEFAULT_SHORTLIST_LIMIT,
    DEFAULT_SUMMARY_CANDIDATES,
    DEFAULT_SUMMARY_REASONS,
    CandidateSelection,
    CandidateSummary,
    CandidateSummaryItem,
    select_candidates,
    summarize_candidate_selection,
)
from strata.core.inventory import collect_inventory


@dataclass(frozen=True, slots=True)
class CandidateAnalysis:
    inventory_records_count: int
    selection: CandidateSelection
    summary: CandidateSummary
    inventory_limit: int | None
    candidate_limit: int
    truncated_inventory: bool


@dataclass(frozen=True, slots=True)
class CandidateAnalysisSummary:
    files_considered: int
    inventory_cap: int | None
    inventory_truncated: bool
    candidate_cap: int
    candidates_selected: int
    candidate_selection_truncated: bool
    top_candidates: tuple[CandidateSummaryItem, ...]


def analyze_candidates_for_task(
    root: str | Path,
    task: str,
    *,
    inventory_limit: int | None = None,
    candidate_limit: int = DEFAULT_SHORTLIST_LIMIT,
    include_hidden: bool = False,
) -> CandidateAnalysis:
    """Inventory a repository and build a bounded value-ranked selection."""

    _validate_optional_limit(inventory_limit, "inventory_limit")
    _validate_limit(candidate_limit, "candidate_limit")
    probe_limit = inventory_limit + 1 if inventory_limit is not None else None
    records = collect_inventory(
        root,
        max_files=probe_limit,
        include_hidden=include_hidden,
    )
    truncated_inventory = (
        inventory_limit is not None and len(records) > inventory_limit
    )
    if truncated_inventory:
        records = records[:inventory_limit]

    selection = select_candidates(records, task, limit=candidate_limit)
    return CandidateAnalysis(
        inventory_records_count=len(records),
        selection=selection,
        summary=summarize_candidate_selection(selection),
        inventory_limit=inventory_limit,
        candidate_limit=candidate_limit,
        truncated_inventory=truncated_inventory,
    )


def summarize_candidate_analysis(
    analysis: CandidateAnalysis,
    top_n: int = DEFAULT_SUMMARY_CANDIDATES,
    reasons_per_candidate: int = DEFAULT_SUMMARY_REASONS,
) -> CandidateAnalysisSummary:
    """Build a bounded structured report for a candidate analysis."""

    candidate_summary = summarize_candidate_selection(
        analysis.selection,
        top_n=top_n,
        reasons_per_candidate=reasons_per_candidate,
    )
    return CandidateAnalysisSummary(
        files_considered=analysis.inventory_records_count,
        inventory_cap=analysis.inventory_limit,
        inventory_truncated=analysis.truncated_inventory,
        candidate_cap=analysis.candidate_limit,
        candidates_selected=candidate_summary.candidates_selected,
        candidate_selection_truncated=candidate_summary.truncated,
        top_candidates=candidate_summary.top_candidates,
    )


def _validate_optional_limit(value: int | None, name: str) -> None:
    if value is None:
        return
    _validate_limit(value, name)


def _validate_limit(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
