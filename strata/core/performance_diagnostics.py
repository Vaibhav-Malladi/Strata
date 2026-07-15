"""Concise performance diagnostics for scale hardening outputs.

L5 turns L1/L2/L3/L4 data into bounded reports. It does not scan repositories,
write artifacts, add CLI workflows, call models, or change context contracts.
"""

import math
from dataclasses import dataclass
from typing import Any, Mapping


DIAGNOSTIC_SEVERITY_INFO = "info"
DIAGNOSTIC_SEVERITY_WARN = "warn"
DIAGNOSTIC_SEVERITY_FAIL = "fail"
DIAGNOSTIC_SEVERITIES = (
    DIAGNOSTIC_SEVERITY_INFO,
    DIAGNOSTIC_SEVERITY_WARN,
    DIAGNOSTIC_SEVERITY_FAIL,
)

DIAGNOSTIC_CATEGORY_REPOSITORY_SIZE = "repository_size"
DIAGNOSTIC_CATEGORY_CONTEXT_BUDGET = "context_budget"
DIAGNOSTIC_CATEGORY_CANDIDATE_PRESSURE = "candidate_pressure"
DIAGNOSTIC_CATEGORY_RELATIONSHIP_PRESSURE = "relationship_pressure"
DIAGNOSTIC_CATEGORY_CACHE_REUSE = "cache_reuse"
DIAGNOSTIC_CATEGORY_CACHE_STALENESS = "cache_staleness"
DIAGNOSTIC_CATEGORY_SYNTHETIC_STRESS = "synthetic_stress"
DIAGNOSTIC_CATEGORY_UNKNOWN = "unknown"
DIAGNOSTIC_CATEGORIES = (
    DIAGNOSTIC_CATEGORY_REPOSITORY_SIZE,
    DIAGNOSTIC_CATEGORY_CONTEXT_BUDGET,
    DIAGNOSTIC_CATEGORY_CANDIDATE_PRESSURE,
    DIAGNOSTIC_CATEGORY_RELATIONSHIP_PRESSURE,
    DIAGNOSTIC_CATEGORY_CACHE_REUSE,
    DIAGNOSTIC_CATEGORY_CACHE_STALENESS,
    DIAGNOSTIC_CATEGORY_SYNTHETIC_STRESS,
    DIAGNOSTIC_CATEGORY_UNKNOWN,
)

MAX_DIAGNOSTICS = 20
MAX_TOP_RISKS = 5
MAX_NEXT_ACTIONS = 5
MAX_EVIDENCE_ITEMS = 5


@dataclass(frozen=True, slots=True)
class PerformanceDiagnostic:
    severity: str
    category: str
    code: str
    message: str
    evidence: tuple[Any, ...] = ()
    next_action: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "severity",
            _validate_choice(self.severity, "severity", DIAGNOSTIC_SEVERITIES),
        )
        object.__setattr__(
            self,
            "category",
            _validate_choice(self.category, "category", DIAGNOSTIC_CATEGORIES),
        )
        object.__setattr__(self, "code", _validate_nonempty_string(self.code, "code"))
        object.__setattr__(
            self,
            "message",
            _validate_nonempty_string(self.message, "message"),
        )
        object.__setattr__(
            self,
            "evidence",
            tuple(_freeze_json(item, f"evidence[{index}]") for index, item in enumerate(self.evidence)),
        )
        object.__setattr__(
            self,
            "next_action",
            _validate_nonempty_string(self.next_action, "next_action"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a stable JSON-ready diagnostic record."""

        return {
            "severity": self.severity,
            "category": self.category,
            "code": self.code,
            "message": self.message,
            "evidence": [_thaw_json(item) for item in self.evidence],
            "next_action": self.next_action,
        }


def create_performance_diagnostic(
    *,
    severity: str,
    category: str,
    code: str,
    message: str,
    evidence: list[Any] | tuple[Any, ...] = (),
    next_action: str,
) -> dict[str, Any]:
    """Create one JSON-ready performance diagnostic record."""

    return PerformanceDiagnostic(
        severity=severity,
        category=category,
        code=code,
        message=message,
        evidence=tuple(evidence),
        next_action=next_action,
    ).to_dict()


def build_performance_diagnostics(
    *,
    budget_summary: Mapping[str, Any] | None = None,
    cache_decision: Mapping[str, Any] | None = None,
    relationship_limit_summary: Mapping[str, Any] | None = None,
    stress_evaluation: Mapping[str, Any] | None = None,
    max_diagnostics: int = MAX_DIAGNOSTICS,
    max_top_risks: int = MAX_TOP_RISKS,
    max_next_actions: int = MAX_NEXT_ACTIONS,
    max_evidence_items: int = MAX_EVIDENCE_ITEMS,
) -> dict[str, Any]:
    """Build a bounded JSON-ready performance diagnostic summary."""

    limits = _normalize_limits(
        max_diagnostics=max_diagnostics,
        max_top_risks=max_top_risks,
        max_next_actions=max_next_actions,
        max_evidence_items=max_evidence_items,
    )
    diagnostics: list[dict[str, Any]] = []
    diagnostics.extend(_diagnostics_from_budget(budget_summary))
    diagnostics.extend(_diagnostics_from_cache(cache_decision))
    diagnostics.extend(_diagnostics_from_relationships(relationship_limit_summary))
    diagnostics.extend(_diagnostics_from_stress(stress_evaluation))

    if not diagnostics:
        diagnostics.append(
            create_performance_diagnostic(
                severity=DIAGNOSTIC_SEVERITY_INFO,
                category=DIAGNOSTIC_CATEGORY_UNKNOWN,
                code="no_scale_risks",
                message="No scale risks were reported by the supplied inputs.",
                evidence=[],
                next_action="No scale action needed.",
            )
        )

    ordered = sorted(diagnostics, key=_diagnostic_sort_key)
    bounded = [
        _bound_diagnostic_evidence(diagnostic, limits["max_evidence_items"])
        for diagnostic in ordered[:limits["max_diagnostics"]]
    ]
    truncated = len(ordered) > len(bounded) or any(
        len(diagnostic.get("evidence", [])) > limits["max_evidence_items"]
        for diagnostic in ordered
    )
    status = _status_from_diagnostics(bounded)
    top_risks = _top_risks(bounded, limits["max_top_risks"])
    next_actions = _next_actions(bounded, limits["max_next_actions"])

    return {
        "status": status,
        "diagnostics": bounded,
        "counts_by_severity": _counts_by_severity(bounded),
        "top_risks": top_risks,
        "next_actions": next_actions,
        "source_summaries": _source_summaries(
            budget_summary,
            cache_decision,
            relationship_limit_summary,
            stress_evaluation,
        ),
        "truncated": truncated,
    }


def render_performance_diagnostics_markdown(summary: Mapping[str, Any]) -> str:
    """Render a concise deterministic Markdown performance diagnostics report."""

    data = summary if isinstance(summary, Mapping) else {}
    status = str(data.get("status") or "pass")
    top_risks = _string_list(data.get("top_risks"))
    next_actions = _string_list(data.get("next_actions"))
    diagnostics = data.get("diagnostics") if isinstance(data.get("diagnostics"), list) else []
    source_summaries = data.get("source_summaries") if isinstance(data.get("source_summaries"), Mapping) else {}

    lines = [
        "# Strata Performance Diagnostics",
        "",
        "## Status",
        "",
        f"- `{status}`",
        "",
        "## Top Risks",
        "",
    ]
    lines.extend(_markdown_items(top_risks))
    lines.extend(["", "## Next Actions", ""])
    lines.extend(_markdown_items(next_actions))
    lines.extend(["", "## Evidence Summary", ""])
    lines.extend(_render_evidence_summary(source_summaries))

    if diagnostics:
        lines.extend(["", "## Diagnostics", ""])
        for diagnostic in diagnostics[:MAX_TOP_RISKS]:
            if not isinstance(diagnostic, Mapping):
                continue
            lines.append(
                "- "
                f"`{diagnostic.get('severity', 'info')}` "
                f"{diagnostic.get('category', 'unknown')}: "
                f"{diagnostic.get('message', '')}"
            )

    return "\n".join(lines)


def _diagnostics_from_budget(
    budget_summary: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    if not isinstance(budget_summary, Mapping):
        return []

    diagnostics: list[dict[str, Any]] = []
    warnings = _string_list(budget_summary.get("warnings"))
    warning_text = "\n".join(warnings)
    budget_status = str(budget_summary.get("budget_status") or "pass")
    if budget_status == "fail" and "max_context_tokens_default" in warning_text:
        diagnostics.append(
            create_performance_diagnostic(
                severity=DIAGNOSTIC_SEVERITY_FAIL,
                category=DIAGNOSTIC_CATEGORY_CONTEXT_BUDGET,
                code="context_token_budget_exceeded",
                message="Estimated context tokens exceed the default budget.",
                evidence=[
                    _pick(
                        budget_summary,
                        (
                            "estimated_context_tokens",
                            "repo_size_class",
                            "file_count",
                        ),
                    ),
                    {"warnings": warnings},
                ],
                next_action="Reduce default context output or tighten candidate selection before expanding prompts.",
            )
        )

    if "max_context_tokens_strict" in warning_text and "max_context_tokens_default" not in warning_text:
        diagnostics.append(
            create_performance_diagnostic(
                severity=DIAGNOSTIC_SEVERITY_WARN,
                category=DIAGNOSTIC_CATEGORY_CONTEXT_BUDGET,
                code="strict_context_budget_pressure",
                message="Estimated context tokens exceed the strict budget.",
                evidence=[_pick(budget_summary, ("estimated_context_tokens", "repo_size_class"))],
                next_action="Keep context sections compact and avoid adding prompt content by default.",
            )
        )

    if "max_candidate_files" in warning_text:
        diagnostics.append(
            create_performance_diagnostic(
                severity=DIAGNOSTIC_SEVERITY_WARN,
                category=DIAGNOSTIC_CATEGORY_CANDIDATE_PRESSURE,
                code="candidate_count_exceeds_budget",
                message="Candidate count exceeds the performance budget.",
                evidence=[_pick(budget_summary, ("candidate_count", "file_count", "repo_size_class"))],
                next_action="Cap candidate selection or use narrower matching before deeper analysis.",
            )
        )

    if "large_repo_file_count" in warning_text:
        diagnostics.append(
            create_performance_diagnostic(
                severity=DIAGNOSTIC_SEVERITY_WARN,
                category=DIAGNOSTIC_CATEGORY_REPOSITORY_SIZE,
                code="very_large_repository",
                message="Repository file count is above the large-repo budget.",
                evidence=[_pick(budget_summary, ("file_count", "repo_size_class"))],
                next_action="Prefer count-aware and cache-aware paths before broad repository operations.",
            )
        )
    return diagnostics


def _diagnostics_from_cache(
    cache_decision: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    if not isinstance(cache_decision, Mapping):
        return []

    status = str(cache_decision.get("status") or "")
    if status == "hit":
        return [
            create_performance_diagnostic(
                severity=DIAGNOSTIC_SEVERITY_INFO,
                category=DIAGNOSTIC_CATEGORY_CACHE_REUSE,
                code="cache_hit",
                message="Cached scan inputs are reusable.",
                evidence=[_pick(cache_decision, ("status", "reuse"))],
                next_action="Reuse safe cached scan inputs for repeated local work.",
            )
        ]

    if status in {"miss", "stale", "invalid"}:
        return [
            create_performance_diagnostic(
                severity=DIAGNOSTIC_SEVERITY_WARN,
                category=DIAGNOSTIC_CATEGORY_CACHE_STALENESS,
                code=f"cache_{status}",
                message="Cached scan inputs are not reusable.",
                evidence=[
                    _pick(cache_decision, ("status", "reuse")),
                    {"reasons": _string_list(cache_decision.get("reasons"))},
                ],
                next_action="Refresh cache metadata before relying on incremental scan results.",
            )
        ]
    return []


def _diagnostics_from_relationships(
    relationship_limit_summary: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    if not isinstance(relationship_limit_summary, Mapping):
        return []

    dropped = _safe_int(relationship_limit_summary.get("dropped_relationships_count"))
    if dropped <= 0:
        return []
    return [
        create_performance_diagnostic(
            severity=DIAGNOSTIC_SEVERITY_WARN,
            category=DIAGNOSTIC_CATEGORY_RELATIONSHIP_PRESSURE,
            code="relationship_records_dropped",
            message="Relationship output was bounded by scale limits.",
            evidence=[
                _pick(
                    relationship_limit_summary,
                    (
                        "total_input_count",
                        "total_kept_count",
                        "dropped_relationships_count",
                    ),
                ),
                {"drop_reasons": relationship_limit_summary.get("drop_reasons", {})},
            ],
            next_action="Inspect drop reasons and keep relationship summaries bounded.",
        )
    ]


def _diagnostics_from_stress(
    stress_evaluation: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    if not isinstance(stress_evaluation, Mapping):
        return []

    status = str(stress_evaluation.get("status") or "pass")
    if status not in {"warn", "fail"}:
        return []
    scenario = stress_evaluation.get("scenario") if isinstance(stress_evaluation.get("scenario"), Mapping) else {}
    return [
        create_performance_diagnostic(
            severity=status,
            category=DIAGNOSTIC_CATEGORY_SYNTHETIC_STRESS,
            code=f"synthetic_stress_{status}",
            message="Synthetic stress evaluation reported scale pressure.",
            evidence=[
                _pick(scenario, ("repo_name", "file_count", "source_file_count")),
                {"warnings": _string_list(stress_evaluation.get("warnings"))},
            ],
            next_action="Use bounded cache, candidate, and relationship paths for this scale class.",
        )
    ]


def _source_summaries(
    budget_summary: Mapping[str, Any] | None,
    cache_decision: Mapping[str, Any] | None,
    relationship_limit_summary: Mapping[str, Any] | None,
    stress_evaluation: Mapping[str, Any] | None,
) -> dict[str, Any]:
    return {
        "budget": _budget_source_summary(budget_summary),
        "cache": _cache_source_summary(cache_decision),
        "relationships": _relationship_source_summary(relationship_limit_summary),
        "stress": _stress_source_summary(stress_evaluation),
    }


def _budget_source_summary(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return _pick(
        value,
        (
            "budget_status",
            "repo_size_class",
            "file_count",
            "candidate_count",
            "relationship_count",
            "estimated_context_tokens",
        ),
    )


def _cache_source_summary(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    summary = _pick(value, ("status", "reuse"))
    summary["reason_count"] = len(_string_list(value.get("reasons")))
    return summary


def _relationship_source_summary(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return _pick(
        value,
        (
            "status",
            "total_input_count",
            "total_kept_count",
            "dropped_relationships_count",
            "duplicate_relationship_count",
        ),
    )


def _stress_source_summary(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    scenario = value.get("scenario") if isinstance(value.get("scenario"), Mapping) else {}
    return {
        "status": value.get("status"),
        "scenario": _pick(scenario, ("repo_name", "file_count", "source_file_count")),
        "warning_count": len(_string_list(value.get("warnings"))),
    }


def _bound_diagnostic_evidence(
    diagnostic: Mapping[str, Any],
    max_evidence_items: int,
) -> dict[str, Any]:
    payload = dict(diagnostic)
    evidence = list(payload.get("evidence", []) or [])
    if len(evidence) > max_evidence_items:
        if max_evidence_items == 0:
            evidence = []
        else:
            evidence = evidence[:max_evidence_items]
            evidence[-1] = {
                "truncated_evidence_items": len(payload.get("evidence", [])) - max_evidence_items + 1
            }
    payload["evidence"] = [_thaw_json(_freeze_json(item, "evidence item")) for item in evidence]
    return payload


def _top_risks(diagnostics: list[dict[str, Any]], limit: int) -> list[str]:
    risks = [
        f"{diagnostic['category']}: {diagnostic['message']}"
        for diagnostic in sorted(diagnostics, key=_diagnostic_sort_key)
        if diagnostic["severity"] in {DIAGNOSTIC_SEVERITY_FAIL, DIAGNOSTIC_SEVERITY_WARN}
    ]
    if not risks:
        risks = ["No warn/fail scale risks reported."]
    return risks[:limit]


def _next_actions(diagnostics: list[dict[str, Any]], limit: int) -> list[str]:
    actions: list[str] = []
    seen: set[str] = set()
    for diagnostic in sorted(diagnostics, key=_diagnostic_sort_key):
        action = str(diagnostic.get("next_action") or "").strip()
        if not action or action in seen:
            continue
        seen.add(action)
        actions.append(action)
        if len(actions) >= limit:
            break
    return actions


def _counts_by_severity(diagnostics: list[dict[str, Any]]) -> dict[str, int]:
    return {
        severity: sum(1 for diagnostic in diagnostics if diagnostic.get("severity") == severity)
        for severity in DIAGNOSTIC_SEVERITIES
    }


def _status_from_diagnostics(diagnostics: list[dict[str, Any]]) -> str:
    severities = {diagnostic.get("severity") for diagnostic in diagnostics}
    if DIAGNOSTIC_SEVERITY_FAIL in severities:
        return "fail"
    if DIAGNOSTIC_SEVERITY_WARN in severities:
        return "warn"
    return "pass"


def _diagnostic_sort_key(diagnostic: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        _severity_index(str(diagnostic.get("severity") or "")),
        str(diagnostic.get("category") or ""),
        str(diagnostic.get("code") or ""),
        str(diagnostic.get("message") or ""),
    )


def _severity_index(value: str) -> int:
    order = {
        DIAGNOSTIC_SEVERITY_FAIL: 0,
        DIAGNOSTIC_SEVERITY_WARN: 1,
        DIAGNOSTIC_SEVERITY_INFO: 2,
    }
    return order.get(value, 3)


def _render_evidence_summary(source_summaries: Mapping[str, Any]) -> list[str]:
    if not source_summaries:
        return ["- none"]
    lines: list[str] = []
    for key in ("budget", "cache", "relationships", "stress"):
        value = source_summaries.get(key)
        if not value:
            continue
        lines.append(f"- {key}: {_compact_mapping(value)}")
    return lines or ["- none"]


def _compact_mapping(value: Any) -> str:
    if not isinstance(value, Mapping):
        return str(value)
    parts = []
    for key in sorted(value):
        item = value[key]
        if isinstance(item, Mapping):
            item = "{" + ", ".join(f"{child}={item[child]}" for child in sorted(item)) + "}"
        parts.append(f"{key}={item}")
    return ", ".join(parts)


def _markdown_items(items: list[str]) -> list[str]:
    if not items:
        return ["- none"]
    return [f"- {item}" for item in items]


def _pick(source: Mapping[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    if not isinstance(source, Mapping):
        return {}
    return {
        key: _thaw_json(_freeze_json(source[key], key))
        for key in keys
        if key in source
    }


def _normalize_limits(
    *,
    max_diagnostics: int,
    max_top_risks: int,
    max_next_actions: int,
    max_evidence_items: int,
) -> dict[str, int]:
    return {
        "max_diagnostics": _validate_nonnegative_integer(max_diagnostics, "max_diagnostics"),
        "max_top_risks": _validate_nonnegative_integer(max_top_risks, "max_top_risks"),
        "max_next_actions": _validate_nonnegative_integer(max_next_actions, "max_next_actions"),
        "max_evidence_items": _validate_nonnegative_integer(max_evidence_items, "max_evidence_items"),
    }


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _safe_int(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return value


def _freeze_json(value: Any, location: str) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{location} must contain finite JSON numbers")
        return value
    if isinstance(value, Mapping):
        return {
            _validate_nonempty_string(key, f"{location} key"): _freeze_json(
                value[key],
                f"{location}.{key}",
            )
            for key in sorted(value)
        }
    if isinstance(value, (list, tuple)):
        return tuple(
            _freeze_json(item, f"{location}[{index}]")
            for index, item in enumerate(value)
        )
    raise TypeError(f"{location} must contain only JSON-ready values")


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_json(value[key]) for key in sorted(value)}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    if isinstance(value, list):
        return [_thaw_json(item) for item in value]
    return value


def _validate_choice(value: Any, name: str, allowed: tuple[str, ...]) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if value not in allowed:
        raise ValueError(f"{name} must be one of: {', '.join(allowed)}")
    return value


def _validate_nonempty_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    if value != value.strip():
        raise ValueError(f"{name} must not have surrounding whitespace")
    return value


def _validate_nonnegative_integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value
