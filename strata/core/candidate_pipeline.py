from dataclasses import dataclass
from pathlib import Path

from strata.core.candidates import (
    DEFAULT_SHORTLIST_LIMIT,
    CandidateSelection,
    CandidateSummary,
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


def _validate_optional_limit(value: int | None, name: str) -> None:
    if value is None:
        return
    _validate_limit(value, name)


def _validate_limit(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
