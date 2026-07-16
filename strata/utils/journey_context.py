"""Journey ranking and bounded context representation for Part P7.

Part I remains authoritative. This module only proposes compact journey context
under a caller supplied budget profile and does not write canonical artifacts.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import json
import math
import re
from typing import Any

import strata.utils.user_journey as user_journey


JOURNEY_CONTEXT_SCHEMA_VERSION = 1
DEFAULT_MAX_JOURNEY_SHARE = 0.25
DEFAULT_TARGET_CONTEXT_TOKENS = 12000
DEFAULT_RESERVED_OUTPUT_TOKENS = 2000
DEFAULT_MAX_CONTEXT_PACK_TOKENS = 10000
DEFAULT_SAFETY_MARGIN = 0.15
DEFAULT_MAX_JOURNEYS = 5
DEFAULT_MAX_STEPS_PER_JOURNEY = 30
DEFAULT_MAX_TRANSITIONS_PER_JOURNEY = 45
DEFAULT_MAX_GAPS_PER_JOURNEY = 12
DEFAULT_MAX_DIAGNOSTICS_PER_JOURNEY = 12
DEFAULT_MAX_EVIDENCE_SUMMARIES_PER_ITEM = 3

TIER_FULL_COMPACT = "full_compact_journey"
TIER_REDUCED_SUMMARY = "reduced_journey_summary"
TIER_CRITICAL_PATH = "critical_path_only"
TIER_IDENTITY_ONLY = "identity_entry_only"
TIER_SKIPPED = "skipped"
REPRESENTATION_TIERS = (TIER_FULL_COMPACT, TIER_REDUCED_SUMMARY, TIER_CRITICAL_PATH, TIER_IDENTITY_ONLY, TIER_SKIPPED)
CRITICAL_STEP_TYPES = (
    user_journey.STEP_TYPE_USER_ACTION,
    user_journey.STEP_TYPE_UI_EVENT_HANDLER,
    user_journey.STEP_TYPE_API_REQUEST,
    user_journey.STEP_TYPE_WORKSPACE_BOUNDARY,
    user_journey.STEP_TYPE_BACKEND_ROUTE,
    user_journey.STEP_TYPE_BACKEND_HANDLER,
    user_journey.STEP_TYPE_AUTHENTICATION,
    user_journey.STEP_TYPE_AUTHORIZATION,
    user_journey.STEP_TYPE_VALIDATION,
    user_journey.STEP_TYPE_BACKEND_SERVICE,
    user_journey.STEP_TYPE_BUSINESS_LOGIC,
    user_journey.STEP_TYPE_DATABASE_ACCESS,
    user_journey.STEP_TYPE_EXTERNAL_SERVICE,
    user_journey.STEP_TYPE_RESPONSE,
    user_journey.STEP_TYPE_FRONTEND_UPDATE,
    user_journey.STEP_TYPE_NAVIGATION,
    user_journey.STEP_TYPE_RENDER,
)
OMITTED_KEYS = ("journeys", "steps", "transitions", "gaps", "diagnostics", "evidence", "downgraded", "skipped")


@dataclass(frozen=True, slots=True)
class JourneyContextRepresentation:
    schema_version: int
    task: str
    journeys: tuple[Mapping[str, Any], ...]
    markdown: str
    omitted_counts: Mapping[str, int]
    budget_summary: Mapping[str, Any]
    metadata: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task": self.task,
            "journeys": [_json_ready(item) for item in self.journeys],
            "markdown": self.markdown,
            "omitted_counts": {key: int(self.omitted_counts.get(key, 0)) for key in OMITTED_KEYS},
            "budget_summary": _json_ready(self.budget_summary),
            "metadata": _json_ready(self.metadata),
        }


def build_journey_context_representation(
    request: user_journey.JourneyRequest | Mapping[str, Any],
    journeys: Iterable[user_journey.UserJourneyResult | Mapping[str, Any]],
    *,
    budget_profile: Mapping[str, Any] | None = None,
    max_journey_share: float = DEFAULT_MAX_JOURNEY_SHARE,
    max_journeys: int = DEFAULT_MAX_JOURNEYS,
    max_steps_per_journey: int = DEFAULT_MAX_STEPS_PER_JOURNEY,
    max_transitions_per_journey: int = DEFAULT_MAX_TRANSITIONS_PER_JOURNEY,
    max_gaps_per_journey: int = DEFAULT_MAX_GAPS_PER_JOURNEY,
    max_diagnostics_per_journey: int = DEFAULT_MAX_DIAGNOSTICS_PER_JOURNEY,
    max_evidence_summaries_per_item: int = DEFAULT_MAX_EVIDENCE_SUMMARIES_PER_ITEM,
) -> JourneyContextRepresentation:
    request = _coerce_request(request)
    budget = _budget_profile(budget_profile)
    max_journey_share = _share(max_journey_share)
    allocation = _journey_allocation(budget, max_journey_share)
    omitted = {key: 0 for key in OMITTED_KEYS}
    ranked = rank_journeys(request, journeys)
    if len(ranked) > max_journeys:
        omitted["journeys"] += len(ranked) - max_journeys
        ranked = ranked[:max_journeys]
    represented = tuple(
        _represent_journey(
            item,
            request,
            omitted,
            max_steps=max_steps_per_journey,
            max_transitions=max_transitions_per_journey,
            max_gaps=max_gaps_per_journey,
            max_diagnostics=max_diagnostics_per_journey,
            max_evidence=max_evidence_summaries_per_item,
        )
        for item in ranked
    )
    represented = _fit_budget(represented, allocation, omitted)
    used = _estimate_tokens(represented)
    exhausted = used > allocation or (bool(ranked) and not represented)
    markdown = render_journey_context_markdown(request, represented, allocation, used, omitted)
    budget_summary = {
        "target_journey_token_allocation": allocation,
        "estimated_journey_tokens_used": used,
        "reserved_output_tokens": budget["reserved_output_tokens"],
        "safety_margin": budget["safety_margin"],
        "max_journey_share": max_journey_share,
        "journey_representation_counts_by_tier": _tier_counts(represented),
        "omitted_counts": dict(omitted),
        "largest_journey_token_savings": _largest_savings(represented),
        "budget_exhausted": exhausted,
        "part_i_authoritative": True,
    }
    return JourneyContextRepresentation(JOURNEY_CONTEXT_SCHEMA_VERSION, request.task, represented, markdown, omitted, budget_summary, {"part_i_authoritative": True, "builder": "journey_context"})


def rank_journeys(request: user_journey.JourneyRequest | Mapping[str, Any], journeys: Iterable[Any]) -> tuple[user_journey.UserJourneyResult, ...]:
    request = _coerce_request(request)
    values = tuple(_coerce_result(item) for item in journeys)
    return tuple(sorted(values, key=lambda item: (-_rank_score(request, item), item.request.journey_name or "", item.request.task, json.dumps(item.summary, sort_keys=True))))


def critical_path(result: user_journey.UserJourneyResult | Mapping[str, Any], *, max_steps: int = DEFAULT_MAX_STEPS_PER_JOURNEY) -> tuple[user_journey.JourneyStep, ...]:
    result = _coerce_result(result)
    steps = {step.step_id: step for step in result.steps}
    adjacency: dict[str, list[str]] = {}
    for transition in result.transitions:
        adjacency.setdefault(transition.source_step_id, []).append(transition.target_step_id)
    for key in adjacency:
        adjacency[key] = sorted(set(adjacency[key]), key=lambda step_id: _critical_sort_key(steps.get(step_id)))
    starts = sorted((step for step in result.steps if step.step_type == user_journey.STEP_TYPE_USER_ACTION), key=user_journey.step_sort_key) or tuple(sorted(result.steps, key=user_journey.step_sort_key)[:1])
    path: list[user_journey.JourneyStep] = []
    seen: set[str] = set()
    current = starts[0] if starts else None
    while current and current.step_id not in seen and len(path) < max_steps:
        path.append(current)
        seen.add(current.step_id)
        candidates = [steps[item] for item in adjacency.get(current.step_id, ()) if item in steps and item not in seen]
        current = sorted(candidates, key=_critical_sort_key)[0] if candidates else None
    return tuple(path)


def render_journey_context_markdown(request: user_journey.JourneyRequest | Mapping[str, Any], journeys: Iterable[Mapping[str, Any]], allocation: int | None = None, used: int | None = None, omitted: Mapping[str, int] | None = None) -> str:
    request = _coerce_request(request)
    items = tuple(journeys)
    if not items:
        return ""
    lines = ["## User journey context", "", "### Requested action", "", f"- {request.task}", ""]
    for index, journey in enumerate(items, start=1):
        lines.append(f"### Journey {index}: {journey.get('readiness', 'partial')}")
        lines.append("")
        lines.append(f"- Tier: {journey.get('representation_tier')}")
        lines.append(f"- Repositories: {', '.join(journey.get('repository_span', ())) or 'none'}")
        lines.append(f"- Confidence: {journey.get('confidence_summary', {}).get('high', 0)} high / {journey.get('confidence_summary', {}).get('medium', 0)} medium / {journey.get('confidence_summary', {}).get('low', 0)} low")
        lines.append("")
        lines.append("#### Critical path")
        for step in journey.get("critical_path", ()):
            lines.append(f"- `{step.get('step_type')}` {step.get('repository_id')}:{step.get('path') or '.'} {step.get('symbol') or ''}".rstrip())
        important_gaps = journey.get("important_gaps", ())
        if important_gaps:
            lines.append("")
            lines.append("#### Important gaps")
            for gap in important_gaps:
                lines.append(f"- `{gap.get('severity')}` `{gap.get('reason')}` {gap.get('summary')}")
        lines.append("")
    lines.append("### Journey budget summary")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps({"target_journey_token_allocation": allocation or 0, "estimated_journey_tokens_used": used or 0, "omitted_counts": dict(omitted or {})}, indent=2, sort_keys=True))
    lines.append("```")
    return "\n".join(lines)


def _represent_journey(result: user_journey.UserJourneyResult, request: user_journey.JourneyRequest, omitted: dict[str, int], *, max_steps: int, max_transitions: int, max_gaps: int, max_diagnostics: int, max_evidence: int) -> Mapping[str, Any]:
    path = critical_path(result, max_steps=max_steps)
    selected_steps = tuple(sorted(result.steps, key=lambda item: (item.step_id not in {step.step_id for step in path}, user_journey.step_sort_key(item))))[:max_steps]
    selected_step_ids = {step.step_id for step in selected_steps}
    selected_transitions = tuple(transition for transition in sorted(result.transitions, key=user_journey.transition_sort_key) if transition.source_step_id in selected_step_ids and transition.target_step_id in selected_step_ids)[:max_transitions]
    important_gaps = _important_gaps(result.gaps)[:max_gaps]
    selected_diagnostics = tuple(sorted(result.diagnostics, key=user_journey.diagnostic_sort_key))[:max_diagnostics]
    omitted["steps"] += max(0, len(result.steps) - len(selected_steps))
    omitted["transitions"] += max(0, len(result.transitions) - len(selected_transitions))
    omitted["gaps"] += max(0, len(result.gaps) - len(important_gaps))
    omitted["diagnostics"] += max(0, len(result.diagnostics) - len(selected_diagnostics))
    return {
        "journey_id": _journey_id(result),
        "score": _rank_score(request, result),
        "representation_tier": TIER_FULL_COMPACT,
        "readiness": result.readiness,
        "selected_entry_point": result.entry_points[0].to_dict() if result.entry_points else None,
        "critical_path": [_step_summary(step, max_evidence) for step in path],
        "selected_steps": [_step_summary(step, max_evidence) for step in selected_steps],
        "selected_transitions": [transition.to_dict() for transition in selected_transitions],
        "important_gaps": [gap.to_dict() for gap in important_gaps],
        "selected_diagnostics": [diagnostic.to_dict() for diagnostic in selected_diagnostics],
        "repository_span": sorted({step.repository_id for step in result.steps}),
        "confidence_summary": {
            "high": sum(1 for step in result.steps if step.confidence == user_journey.CONFIDENCE_HIGH),
            "medium": sum(1 for step in result.steps if step.confidence == user_journey.CONFIDENCE_MEDIUM),
            "low": sum(1 for step in result.steps if step.confidence == user_journey.CONFIDENCE_LOW),
        },
        "omitted_counts": dict(omitted),
    }


def _fit_budget(journeys: tuple[Mapping[str, Any], ...], allocation: int, omitted: dict[str, int]) -> tuple[Mapping[str, Any], ...]:
    values = [dict(item) for item in journeys]
    savings: list[dict[str, Any]] = []
    for tier in (TIER_REDUCED_SUMMARY, TIER_CRITICAL_PATH, TIER_IDENTITY_ONLY, TIER_SKIPPED):
        if _estimate_tokens(values) <= allocation:
            break
        for index, item in enumerate(values):
            if _estimate_tokens(values) <= allocation:
                break
            before = _estimate_tokens((item,))
            values[index] = _downgrade(item, tier)
            after = _estimate_tokens((values[index],))
            if before > after:
                omitted["downgraded"] += 1
                if tier == TIER_SKIPPED:
                    omitted["skipped"] += 1
                savings.append({"journey_id": item.get("journey_id"), "from_tokens": before, "to_tokens": after, "saved_tokens": before - after})
    for item, saving in zip(values, savings):
        item.setdefault("token_savings", []).append(saving)
    return tuple(item for item in values if item.get("representation_tier") != TIER_SKIPPED)


def _downgrade(item: Mapping[str, Any], tier: str) -> Mapping[str, Any]:
    value = dict(item)
    value["representation_tier"] = tier
    if tier == TIER_REDUCED_SUMMARY:
        value["selected_steps"] = value.get("critical_path", ())[:10]
        value["selected_transitions"] = value.get("selected_transitions", ())[:10]
    elif tier == TIER_CRITICAL_PATH:
        value["selected_steps"] = value.get("critical_path", ())
        value["selected_transitions"] = ()
    elif tier == TIER_IDENTITY_ONLY:
        value["selected_steps"] = ()
        value["selected_transitions"] = ()
        value["important_gaps"] = value.get("important_gaps", ())[:3]
        value["selected_diagnostics"] = value.get("selected_diagnostics", ())[:3]
    elif tier == TIER_SKIPPED:
        value["selected_steps"] = ()
        value["selected_transitions"] = ()
        value["critical_path"] = ()
        value["important_gaps"] = ()
        value["selected_diagnostics"] = ()
    return value


def _rank_score(request: user_journey.JourneyRequest, result: user_journey.UserJourneyResult) -> float:
    score = 0.0
    task_tokens = set(request.task_keywords)
    serialized = json.dumps(result.to_dict(), sort_keys=True).lower()
    score += len(task_tokens & set(re.findall(r"[a-z0-9][a-z0-9_-]*", serialized))) * 2
    if result.entry_points and any(entry.origin == user_journey.ORIGIN_EXPLICIT for entry in result.entry_points):
        score += 20
    if result.readiness == user_journey.READINESS_COMPLETE:
        score += 18
    if any(step.step_type == user_journey.STEP_TYPE_API_REQUEST for step in result.steps):
        score += 12
    if any(step.step_type in {user_journey.STEP_TYPE_AUTHORIZATION, user_journey.STEP_TYPE_AUTHENTICATION, user_journey.STEP_TYPE_VALIDATION, user_journey.STEP_TYPE_DATABASE_ACCESS} for step in result.steps):
        score += 8
    score += sum(1 for step in result.steps if step.confidence == user_journey.CONFIDENCE_HIGH)
    score -= sum(1 for gap in result.gaps if gap.severity == user_journey.DIAGNOSTIC_SEVERITY_WARNING) * 0.5
    return round(score, 3)


def _important_gaps(gaps: Iterable[user_journey.JourneyGap]) -> tuple[user_journey.JourneyGap, ...]:
    return tuple(sorted(gaps, key=lambda gap: (gap.severity != user_journey.DIAGNOSTIC_SEVERITY_ERROR, user_journey.gap_sort_key(gap))))


def _step_summary(step: user_journey.JourneyStep, max_evidence: int) -> dict[str, Any]:
    payload = step.to_dict()
    payload["evidence"] = payload.get("evidence", ())[:max_evidence]
    return payload


def _critical_sort_key(step: user_journey.JourneyStep | None) -> tuple[object, ...]:
    if step is None:
        return (999, "")
    rank = CRITICAL_STEP_TYPES.index(step.step_type) if step.step_type in CRITICAL_STEP_TYPES else len(CRITICAL_STEP_TYPES)
    return (rank, -step.confidence_score, step.sequence_hint, step.step_id)


def _tier_counts(items: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counts = {tier: 0 for tier in REPRESENTATION_TIERS}
    for item in items:
        counts[str(item.get("representation_tier", TIER_SKIPPED))] += 1
    return counts


def _largest_savings(items: Iterable[Mapping[str, Any]]) -> tuple[Mapping[str, Any], ...]:
    savings = [saving for item in items for saving in item.get("token_savings", ())]
    return tuple(sorted(savings, key=lambda item: (-int(item.get("saved_tokens", 0)), str(item.get("journey_id", ""))))[:5])


def _estimate_tokens(value: Any) -> int:
    text = json.dumps(_json_ready(value), sort_keys=True)
    return max(1, math.ceil(len(text) / 4))


def _journey_allocation(budget: Mapping[str, Any], share: float) -> int:
    usable = min(int(budget["target_context_tokens"]), int(budget["max_context_pack_tokens"])) - int(budget["reserved_output_tokens"])
    usable = max(1, int(usable * (1.0 - float(budget["safety_margin"]))))
    return max(1, int(usable * share))


def _budget_profile(value: Mapping[str, Any] | None) -> dict[str, Any]:
    value = dict(value or {})
    return {
        "target_context_tokens": int(value.get("target_context_tokens", DEFAULT_TARGET_CONTEXT_TOKENS)),
        "reserved_output_tokens": int(value.get("reserved_output_tokens", DEFAULT_RESERVED_OUTPUT_TOKENS)),
        "max_context_pack_tokens": int(value.get("max_context_pack_tokens", DEFAULT_MAX_CONTEXT_PACK_TOKENS)),
        "safety_margin": float(value.get("safety_margin", DEFAULT_SAFETY_MARGIN)),
    }


def _share(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("max_journey_share must be a number")
    if value <= 0 or value > 1:
        raise user_journey.UserJourneyError("max_journey_share must be between 0 and 1")
    return round(float(value), 3)


def _journey_id(result: user_journey.UserJourneyResult) -> str:
    if result.entry_points:
        return "|".join(user_journey.entry_point_identity_key(result.entry_points[0]))
    if result.steps:
        return result.steps[0].step_id
    return result.request.task


def _coerce_request(value: user_journey.JourneyRequest | Mapping[str, Any]) -> user_journey.JourneyRequest:
    if isinstance(value, user_journey.JourneyRequest):
        return value
    return user_journey.JourneyRequest(**dict(value))


def _coerce_result(value: user_journey.UserJourneyResult | Mapping[str, Any]) -> user_journey.UserJourneyResult:
    if isinstance(value, user_journey.UserJourneyResult):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("journey must be a UserJourneyResult or mapping")
    return user_journey.UserJourneyResult(
        schema_version=value["schema_version"],
        request=_coerce_request(value["request"]),
        entry_points=tuple(value.get("entry_points", ())),
        steps=tuple(value.get("steps", ())),
        transitions=tuple(value.get("transitions", ())),
        gaps=tuple(value.get("gaps", ())),
        diagnostics=tuple(value.get("diagnostics", ())),
        summary=value.get("summary", {}),
        readiness=value.get("readiness", user_journey.READINESS_PARTIAL),
        metadata=value.get("metadata"),
    )


def _json_ready(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, Mapping):
        return {key: _json_ready(value[key]) for key in sorted(value)}
    return value
