from __future__ import annotations

import math

from context_efficiency import estimate_tokens
from context_matching import _normalize_path
from selected_context import build_selected_file_entries


BUDGET_PRESETS = {
    "tiny": 2_000,
    "small": 4_000,
    "medium": 8_000,
    "large": 16_000,
}


class BudgetParseError(ValueError):
    pass


def parse_budget_value(raw_value: str | None) -> dict:
    raw_text = str(raw_value or "").strip()

    if not raw_text:
        return {
            "raw": raw_text,
            "name": None,
            "target_tokens": None,
            "mode": "best effort",
        }

    normalized = raw_text.lower()
    if normalized in BUDGET_PRESETS:
        return {
            "raw": raw_text,
            "name": normalized,
            "target_tokens": BUDGET_PRESETS[normalized],
            "mode": "best effort",
        }

    if raw_text.isdigit():
        target_tokens = int(raw_text)
        if target_tokens <= 0:
            raise BudgetParseError(
                "Invalid budget value. Use tiny, small, medium, large, or a positive integer."
            )
        return {
            "raw": raw_text,
            "name": raw_text,
            "target_tokens": target_tokens,
            "mode": "best effort",
        }

    raise BudgetParseError(
        f"Invalid budget value: {raw_text}. Use tiny, small, medium, large, or a positive integer."
    )


def build_budget_report(
    graph: dict,
    task: str,
    *,
    selected_paths: list[str] | None = None,
    budget_value: str | None = None,
    max_candidates: int = 10,
    max_excluded: int = 8,
) -> dict:
    budget = parse_budget_value(budget_value)
    selected_entries = build_selected_file_entries(graph, selected_paths or [])
    ranked_entries = _rank_candidates(graph, task, max_candidates)
    selected_paths_set = {
        _normalize_path(entry.get("file", {}).get("path", ""))
        for entry in selected_entries
    }

    included: list[dict] = []
    excluded: list[dict] = []
    seen: set[str] = set()
    included_tokens = 0
    selected_tokens = 0

    for entry in selected_entries:
        normalized_path = _normalize_path(entry.get("file", {}).get("path", ""))
        if not normalized_path or normalized_path in seen:
            continue

        cost = _estimate_entry_tokens(entry)
        selected_tokens += cost
        included_tokens += cost
        seen.add(normalized_path)
        included.append(_annotate_entry(entry, cost, "selected"))

    target_tokens = budget.get("target_tokens")
    selected_over_budget = bool(target_tokens is not None and selected_tokens > target_tokens)

    for entry in ranked_entries:
        normalized_path = _normalize_path(entry.get("file", {}).get("path", ""))
        if not normalized_path or normalized_path in seen or normalized_path in selected_paths_set:
            continue

        cost = _estimate_entry_tokens(entry)
        if target_tokens is not None and included_tokens + cost > target_tokens:
            if len(excluded) < max_excluded:
                excluded.append(_annotate_entry(entry, cost, "budget full"))
            continue

        included_tokens += cost
        seen.add(normalized_path)
        included.append(_annotate_entry(entry, cost, "included"))

    excluded_total_count = max(0, len(ranked_entries) - (len(included) - len(selected_entries)))

    return {
        "budget": budget,
        "selected_entries": selected_entries,
        "ranked_entries": ranked_entries,
        "included_entries": included,
        "excluded_entries": excluded,
        "excluded_total_count": excluded_total_count,
        "included_total_count": len(included),
        "selected_total_count": len(selected_entries),
        "selected_estimated_tokens": selected_tokens,
        "estimated_context_tokens": included_tokens,
        "selected_over_budget": selected_over_budget,
        "budget_mode": budget["mode"],
    }


def build_budget_summary_rows(report: dict) -> list[tuple[str, object]]:
    budget = report.get("budget", {})
    target_tokens = budget.get("target_tokens")
    included_entries = list(report.get("included_entries", []) or [])
    excluded_entries = list(report.get("excluded_entries", []) or [])
    budgeted_context_tokens = report.get("budgeted_context_tokens")
    if budgeted_context_tokens is None:
        budgeted_context_tokens = report.get("estimated_context_tokens", 0)
        budgeted_context_label = "Budgeted context section estimate"
    else:
        budgeted_context_label = "Budgeted generated content estimate"

    rows: list[tuple[str, object]] = [
        ("Budget preset", budget_label(budget)),
        ("Target estimated tokens", _format_budget_target(target_tokens)),
        (budgeted_context_label, f"~{int(budgeted_context_tokens):,}"),
        ("Files included", _format_file_list(included_entries, total_count=len(included_entries))),
        (
            "Files skipped by budget",
            _format_file_list(
                excluded_entries,
                empty_value="none",
                total_count=int(report.get("excluded_total_count", len(excluded_entries)) or 0),
            ),
        ),
        ("Budget exceeded by selected files", _format_yes_no(bool(report.get("selected_over_budget")))),
        ("Budget mode", str(report.get("budget_mode") or "best effort")),
    ]

    return rows


def build_structured_intent_section(task: str) -> list[str]:
    return [
        "## Structured Intent",
        "",
        "- Task intent: best-effort repo context for the requested change.",
        f"- Task: {task}",
        "",
    ]


def build_change_boundary_section(selected_paths: list[str], report: dict) -> list[str]:
    lines = ["## Change Boundary", ""]

    if selected_paths:
        lines.append("- User-selected files are pinned first and never dropped by budget.")
        lines.append(f"- Selected files: {', '.join(f'`{path}`' for path in selected_paths)}")
    else:
        lines.append("- No user-selected files were provided.")

    if report.get("selected_over_budget"):
        lines.append("- Budget exceeded by selected files, so lower-ranked files may be skipped.")
    else:
        lines.append("- Lower-ranked files are trimmed first when the budget fills up.")

    lines.append("")
    return lines


def build_context_budget_section(report: dict) -> list[str]:
    budget = report.get("budget", {})
    target_tokens = budget.get("target_tokens")
    budgeted_context_tokens = report.get("budgeted_context_tokens")
    if budgeted_context_tokens is None:
        budgeted_context_tokens = report.get("estimated_context_tokens", 0)
        budgeted_context_label = "Budgeted context section estimate"
    else:
        budgeted_context_label = "Budgeted generated content estimate"
    lines = ["## Context Budget", ""]
    lines.append(f"- Budget mode: {report.get('budget_mode') or 'best effort'}")
    lines.append(f"- Budget preset: {budget_label(budget)}")
    lines.append(f"- Target estimated tokens: {_format_budget_target(target_tokens)}")
    lines.append(f"- {budgeted_context_label}: ~{int(budgeted_context_tokens):,}")
    lines.append(
        f"- Budget exceeded by selected files: {_format_yes_no(bool(report.get('selected_over_budget')))}"
    )
    lines.append("")
    return lines


def build_included_context_section(report: dict, *, max_items: int = 10) -> list[str]:
    lines = ["## Included Context", ""]
    entries = list(report.get("included_entries", []) or [])

    if not entries:
        lines.append("- none")
        lines.append("")
        return lines

    for entry in entries[:max_items]:
        lines.append(f"- {describe_entry(entry)}")

    if len(entries) > max_items:
        lines.append(f"- ...and {len(entries) - max_items} more")

    lines.append("")
    return lines


def build_excluded_context_section(report: dict, *, max_items: int = 8) -> list[str]:
    lines = ["## Excluded Context", ""]
    entries = list(report.get("excluded_entries", []) or [])
    total = int(report.get("excluded_total_count", 0) or 0)

    if not entries:
        lines.append("- none")
        lines.append("")
        return lines

    for entry in entries[:max_items]:
        lines.append(f"- {describe_entry(entry)}")

    if total > len(entries):
        lines.append(f"- ...and {total - len(entries)} more skipped by budget")

    lines.append("")
    return lines


def describe_entry(entry: dict) -> str:
    path = str(entry.get("file", {}).get("path", "<unknown>"))
    score = entry.get("score")
    confidence = entry.get("confidence")
    estimated_tokens = entry.get("estimated_tokens")
    reason = entry.get("budget_reason") or entry.get("reason") or "matched task context"

    pieces = [f"`{path}`"]
    if score is not None:
        pieces.append(f"score {score}")
    if confidence:
        pieces.append(str(confidence))
    if estimated_tokens is not None:
        pieces.append(f"~{int(estimated_tokens):,} tokens")
    if reason:
        pieces.append(str(reason))

    return " - ".join(pieces)


def budget_label(budget: dict) -> str:
    name = budget.get("name")
    if name:
        return str(name)
    return "unbounded"


def _rank_candidates(graph: dict, task: str, max_candidates: int) -> list[dict]:
    from context_pack import rank_relevant_files

    return rank_relevant_files(graph, task, limit=max_candidates)


def _estimate_entry_tokens(entry: dict) -> int:
    file_info = entry.get("file", {})
    path = str(file_info.get("path", "")).strip()
    score = entry.get("score")
    confidence = str(entry.get("confidence", "")).strip()
    selected = "selected" if entry.get("selected_by_user") else ""
    matched_terms = entry.get("matched_terms", []) or []
    reason = str(entry.get("reason") or entry.get("budget_reason") or "").strip()
    parts = [path, str(score or ""), confidence, selected, reason, ", ".join(str(term) for term in matched_terms[:3])]
    return estimate_tokens(" | ".join(part for part in parts if part))


def _annotate_entry(entry: dict, estimated_tokens: int, budget_reason: str) -> dict:
    annotated = dict(entry)
    annotated["estimated_tokens"] = estimated_tokens
    annotated["budget_reason"] = budget_reason
    return annotated


def _format_budget_target(target_tokens: int | None) -> str:
    if target_tokens is None:
        return "not set"

    return f"~{int(target_tokens):,} tokens"


def _format_file_list(
    entries: list[dict],
    *,
    empty_value: str = "none",
    total_count: int | None = None,
) -> str:
    if not entries:
        return empty_value

    paths = [str(entry.get("file", {}).get("path", "")).strip() for entry in entries if str(entry.get("file", {}).get("path", "")).strip()]
    if not paths:
        return empty_value

    preview = ", ".join(paths[:5])
    if len(paths) > 5:
        preview += f", ...and {len(paths) - 5} more"

    count = len(paths) if total_count is None else total_count
    return f"{count}: {preview}"


def _format_yes_no(value: bool) -> str:
    return "yes" if value else "no"
