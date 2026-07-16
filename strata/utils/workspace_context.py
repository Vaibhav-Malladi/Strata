"""Budgeted workspace context representation contracts for Part Q7.

Q7 consumes already-produced workspace intelligence and builds compact,
JSON-ready context candidates. It does not read files, scan repositories,
discover repositories, extract references, compare contracts, write artifacts,
or allocate outside the caller supplied Part I budget profile.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import json
import math
import re
from typing import Any

import strata.utils.workspace_contracts as workspace_contracts
import strata.utils.workspace_graph as workspace_graph


WORKSPACE_CONTEXT_SCHEMA_VERSION = 1

DEFAULT_MAX_WORKSPACE_SHARE = 0.20
DEFAULT_MAX_REPOSITORIES = 12
DEFAULT_MAX_RELATIONSHIPS = 30
DEFAULT_MAX_CONTRACTS = 20
DEFAULT_MAX_UNRESOLVED = 10
DEFAULT_MAX_DIAGNOSTICS = 15
DEFAULT_MAX_EVIDENCE_PER_ITEM = 3

DEFAULT_TARGET_CONTEXT_TOKENS = 12000
DEFAULT_RESERVED_OUTPUT_TOKENS = 2000
DEFAULT_MAX_CONTEXT_PACK_TOKENS = 10000
DEFAULT_SAFETY_MARGIN = 0.15

TIER_WORKSPACE_SUMMARY = "workspace_summary"
TIER_RELATIONSHIP_SUMMARY = "relationship_summary"
TIER_CONTRACT_SUMMARY = "contract_summary"
TIER_IDENTITY_ONLY = "identity_only"
TIER_SKIPPED = "skipped"
REPRESENTATION_TIERS = (
    TIER_WORKSPACE_SUMMARY,
    TIER_RELATIONSHIP_SUMMARY,
    TIER_CONTRACT_SUMMARY,
    TIER_IDENTITY_ONLY,
    TIER_SKIPPED,
)

OMITTED_KEYS = (
    "repositories",
    "relationships",
    "contracts",
    "unresolved_relationships",
    "diagnostics",
    "evidence",
    "downgraded",
    "skipped",
)
BUDGET_FIELD_ORDER = (
    "target_workspace_token_allocation",
    "estimated_workspace_tokens_used",
    "reserved_output_tokens",
    "safety_margin",
    "max_workspace_share",
    "repository_representation_counts_by_tier",
    "relationship_representation_counts_by_tier",
    "contract_representation_counts_by_tier",
    "omitted_counts",
    "largest_workspace_token_savings",
    "budget_exhausted",
    "tokenizer_strategy",
)
RESULT_FIELD_ORDER = (
    "schema_version",
    "task",
    "workspace_summary",
    "repositories",
    "relationships",
    "contracts",
    "unresolved_relationships",
    "diagnostics",
    "omitted_counts",
    "budget_summary",
    "metadata",
)

SECRET_KEYWORDS = ("secret", "token", "password", "passwd", "pwd", "apikey", "api_key", "private_key", "cookie", "credential")
SECRET_VALUE = "[redacted]"


class WorkspaceContextError(ValueError):
    """Raised when Q7 workspace context inputs are invalid."""


@dataclass(frozen=True, slots=True)
class WorkspaceContextRepresentation:
    schema_version: int
    task: str
    workspace_summary: Mapping[str, Any]
    repositories: tuple[Mapping[str, Any], ...]
    relationships: tuple[Mapping[str, Any], ...]
    contracts: tuple[Mapping[str, Any], ...]
    unresolved_relationships: tuple[Mapping[str, Any], ...]
    diagnostics: tuple[Mapping[str, Any], ...]
    omitted_counts: Mapping[str, int]
    budget_summary: Mapping[str, Any]
    metadata: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.schema_version != WORKSPACE_CONTEXT_SCHEMA_VERSION:
            raise WorkspaceContextError("workspace context schema_version must be 1")
        object.__setattr__(self, "task", _string(self.task))
        object.__setattr__(self, "workspace_summary", _copy_json_mapping(self.workspace_summary, "workspace_summary"))
        object.__setattr__(self, "repositories", _copy_mapping_tuple(self.repositories, "repositories"))
        object.__setattr__(self, "relationships", _copy_mapping_tuple(self.relationships, "relationships"))
        object.__setattr__(self, "contracts", _copy_mapping_tuple(self.contracts, "contracts"))
        object.__setattr__(self, "unresolved_relationships", _copy_mapping_tuple(self.unresolved_relationships, "unresolved_relationships"))
        object.__setattr__(self, "diagnostics", _copy_mapping_tuple(self.diagnostics, "diagnostics"))
        object.__setattr__(self, "omitted_counts", _copy_omitted_counts(self.omitted_counts))
        object.__setattr__(self, "budget_summary", _copy_json_mapping(self.budget_summary, "budget_summary"))
        object.__setattr__(self, "metadata", _copy_json_mapping(self.metadata or {}, "metadata"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task": self.task,
            "workspace_summary": _json_ready(self.workspace_summary),
            "repositories": [_json_ready(item) for item in self.repositories],
            "relationships": [_json_ready(item) for item in self.relationships],
            "contracts": [_json_ready(item) for item in self.contracts],
            "unresolved_relationships": [_json_ready(item) for item in self.unresolved_relationships],
            "diagnostics": [_json_ready(item) for item in self.diagnostics],
            "omitted_counts": {key: int(self.omitted_counts.get(key, 0)) for key in OMITTED_KEYS},
            "budget_summary": {key: _json_ready(self.budget_summary[key]) for key in BUDGET_FIELD_ORDER if key in self.budget_summary},
            "metadata": _json_ready(self.metadata or {}),
        }


def build_workspace_context_representation(
    task: str | Iterable[str] | None,
    graph: Any,
    *,
    contract_findings: Any = (),
    diagnostics: Iterable[Any] = (),
    budget_profile: Mapping[str, Any] | None = None,
    max_workspace_share: float = DEFAULT_MAX_WORKSPACE_SHARE,
    max_repositories: int = DEFAULT_MAX_REPOSITORIES,
    max_relationships: int = DEFAULT_MAX_RELATIONSHIPS,
    max_contracts: int = DEFAULT_MAX_CONTRACTS,
    max_unresolved: int = DEFAULT_MAX_UNRESOLVED,
    max_diagnostics: int = DEFAULT_MAX_DIAGNOSTICS,
    max_evidence_per_item: int = DEFAULT_MAX_EVIDENCE_PER_ITEM,
) -> WorkspaceContextRepresentation:
    """Build bounded workspace context candidates under the supplied budget profile."""

    task_text = _task_text(task)
    task_tokens = _tokens(task_text)
    budget = _budget_profile(budget_profile)
    max_workspace_share = _validate_share(max_workspace_share)
    max_repositories = _validate_limit(max_repositories, "max_repositories")
    max_relationships = _validate_limit(max_relationships, "max_relationships")
    max_contracts = _validate_limit(max_contracts, "max_contracts")
    max_unresolved = _validate_limit(max_unresolved, "max_unresolved")
    max_diagnostics = _validate_limit(max_diagnostics, "max_diagnostics")
    max_evidence_per_item = _validate_limit(max_evidence_per_item, "max_evidence_per_item")

    graph_payload = _graph_to_dict(graph)
    omitted = {key: 0 for key in OMITTED_KEYS}
    workspace_summary = _workspace_summary(graph_payload, task_text)
    repositories = _select_repositories(graph_payload, task_tokens, max_repositories, max_evidence_per_item, omitted)
    selected_ids = {item["repository_id"] for item in repositories if item.get("representation_tier") != TIER_SKIPPED}
    relationships = _select_relationships(graph_payload, task_tokens, selected_ids, max_relationships, max_evidence_per_item, omitted)
    contracts = _select_contracts(contract_findings, task_tokens, selected_ids, max_contracts, omitted)
    unresolved = _select_unresolved(graph_payload, task_tokens, selected_ids, max_unresolved, max_evidence_per_item, omitted)
    diagnostic_items = _select_diagnostics((*tuple(diagnostics), *tuple(graph_payload.get("diagnostics", ()))), task_tokens, selected_ids, max_diagnostics, omitted)

    workspace_summary["representation_tier"] = TIER_WORKSPACE_SUMMARY
    items = {
        "repositories": repositories,
        "relationships": relationships,
        "contracts": contracts,
        "unresolved_relationships": unresolved,
        "diagnostics": diagnostic_items,
    }
    allocation = _workspace_token_allocation(budget, max_workspace_share)
    used = _estimate_representation_tokens(workspace_summary, items)
    savings: list[dict[str, Any]] = []
    exhausted = False
    while used > allocation and _downgrade_one(items, omitted, savings):
        used = _estimate_representation_tokens(workspace_summary, items)
    if used > allocation:
        exhausted = True
        while used > allocation and _skip_one(items, omitted, savings):
            used = _estimate_representation_tokens(workspace_summary, items)
    if used > allocation:
        exhausted = True

    budget_summary = _budget_summary(budget, allocation, used, max_workspace_share, items, omitted, savings, exhausted)
    return WorkspaceContextRepresentation(
        schema_version=WORKSPACE_CONTEXT_SCHEMA_VERSION,
        task=task_text,
        workspace_summary=workspace_summary,
        repositories=tuple(item for item in items["repositories"] if item.get("representation_tier") != TIER_SKIPPED),
        relationships=tuple(item for item in items["relationships"] if item.get("representation_tier") != TIER_SKIPPED),
        contracts=tuple(item for item in items["contracts"] if item.get("representation_tier") != TIER_SKIPPED),
        unresolved_relationships=tuple(item for item in items["unresolved_relationships"] if item.get("representation_tier") != TIER_SKIPPED),
        diagnostics=tuple(item for item in items["diagnostics"] if item.get("representation_tier") != TIER_SKIPPED),
        omitted_counts=omitted,
        budget_summary=budget_summary,
        metadata={
            "builder": "workspace_context",
            "part_i_authoritative": True,
            "bounded_workspace_share": max_workspace_share,
        },
    )


def workspace_context_to_dict(context: WorkspaceContextRepresentation | Mapping[str, Any]) -> dict[str, Any]:
    """Return the stable JSON-ready workspace context representation."""

    if isinstance(context, WorkspaceContextRepresentation):
        return context.to_dict()
    if isinstance(context, Mapping):
        return WorkspaceContextRepresentation(
            schema_version=context["schema_version"],
            task=context.get("task", ""),
            workspace_summary=context.get("workspace_summary", {}),
            repositories=tuple(context.get("repositories", ())),
            relationships=tuple(context.get("relationships", ())),
            contracts=tuple(context.get("contracts", ())),
            unresolved_relationships=tuple(context.get("unresolved_relationships", ())),
            diagnostics=tuple(context.get("diagnostics", ())),
            omitted_counts=context.get("omitted_counts", {}),
            budget_summary=context.get("budget_summary", {}),
            metadata=context.get("metadata"),
        ).to_dict()
    raise TypeError("context must be a WorkspaceContextRepresentation or mapping")


def render_workspace_context_markdown(context: WorkspaceContextRepresentation | Mapping[str, Any]) -> str:
    """Render the compact workspace context section for canonical context artifacts."""

    payload = workspace_context_to_dict(context)
    lines = ["## Workspace context", ""]
    summary = payload["workspace_summary"]
    lines.append("### Workspace summary")
    lines.append("")
    lines.append(f"- Nodes: {summary.get('node_count', 0)}")
    lines.append(f"- Edges: {summary.get('edge_count', 0)}")
    lines.append(f"- Cycles: {summary.get('cycle_count', 0)}")
    lines.append(f"- Unresolved relationships: {summary.get('unresolved_relationship_count', 0)}")
    lines.append("")
    _append_items(lines, "### Relevant repositories", payload["repositories"], ("repository_id", "role", "role_confidence"))
    _append_items(lines, "### Cross-repository relationships", payload["relationships"], ("source_repository_id", "relationship_type", "target_repository_id", "confidence"))
    _append_items(lines, "### Shared-contract findings", payload["contracts"], ("name", "status", "severity"))
    _append_items(lines, "### Workspace warnings", [*payload["unresolved_relationships"], *payload["diagnostics"]], ("code", "reason", "summary"))
    lines.append("### Workspace budget summary")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(payload["budget_summary"], indent=2, sort_keys=True))
    lines.append("```")
    return "\n".join(lines).rstrip() + "\n"


def _graph_to_dict(graph: Any) -> dict[str, Any]:
    if isinstance(graph, workspace_graph.WorkspaceDependencyGraph):
        return graph.to_dict()
    if isinstance(graph, Mapping):
        return {str(key): value for key, value in graph.items()}
    raise TypeError("graph must be a WorkspaceDependencyGraph or mapping")


def _contract_findings_to_dicts(value: Any) -> tuple[dict[str, Any], ...]:
    if value is None:
        return ()
    if isinstance(value, workspace_contracts.SharedContractComparisonResult):
        return tuple(item.to_dict() for item in value.contract_findings)
    if isinstance(value, Mapping) and "contract_findings" in value:
        return tuple(dict(item) for item in value.get("contract_findings", ()))
    return tuple(item.to_dict() if isinstance(item, workspace_contracts.SharedContractFinding) else dict(item) for item in value)


def _workspace_summary(graph: Mapping[str, Any], task: str) -> dict[str, Any]:
    summary = dict(graph.get("summary", {}) if isinstance(graph.get("summary"), Mapping) else {})
    return _redact_json(
        {
            "task": task,
            "node_count": int(summary.get("node_count", len(graph.get("nodes", ()) or ()))),
            "edge_count": int(summary.get("edge_count", len(graph.get("edges", ()) or ()))),
            "cycle_count": int(summary.get("cycle_count", len(graph.get("cycles", ()) or ()))),
            "isolated_repository_count": int(summary.get("isolated_repository_count", len(graph.get("isolated_repository_ids", ()) or ()))),
            "unresolved_relationship_count": int(summary.get("unresolved_relationship_count", len(graph.get("unresolved_relationships", ()) or ()))),
            "contract_edge_count": int(summary.get("contract_edge_count", 0)),
        }
    )


def _select_repositories(graph: Mapping[str, Any], task_tokens: set[str], limit: int, evidence_limit: int, omitted: dict[str, int]) -> tuple[dict[str, Any], ...]:
    scored = []
    relationship_counts: dict[str, int] = {}
    for edge in graph.get("edges", ()) or ():
        if isinstance(edge, Mapping):
            relationship_counts[str(edge.get("source_repository_id"))] = relationship_counts.get(str(edge.get("source_repository_id")), 0) + 1
            relationship_counts[str(edge.get("target_repository_id"))] = relationship_counts.get(str(edge.get("target_repository_id")), 0) + 1
    for node in graph.get("nodes", ()) or ():
        if not isinstance(node, Mapping):
            continue
        evidence, omitted_evidence = _evidence_summaries(node.get("evidence", ()), evidence_limit)
        omitted["evidence"] += omitted_evidence
        item = {
            "repository_id": _string(node.get("repository_id")),
            "display_name": _optional_string(node.get("display_name")),
            "role": _string(node.get("role")),
            "role_confidence": _string(node.get("role_confidence")),
            "role_confidence_score": _score(node.get("role_confidence_score")),
            "configured": bool(node.get("configured")),
            "discovered": bool(node.get("discovered")),
            "relevant_relationship_count": relationship_counts.get(_string(node.get("repository_id")), 0),
            "evidence": evidence,
            "representation_tier": TIER_WORKSPACE_SUMMARY,
        }
        score = _repository_relevance(node, task_tokens)
        scored.append((score, item))
    return _take_scored(scored, limit, "repositories", omitted)


def _select_relationships(graph: Mapping[str, Any], task_tokens: set[str], selected_ids: set[str], limit: int, evidence_limit: int, omitted: dict[str, int]) -> tuple[dict[str, Any], ...]:
    scored = []
    for edge in graph.get("edges", ()) or ():
        if not isinstance(edge, Mapping):
            continue
        evidence, omitted_evidence = _evidence_summaries(edge.get("evidence", ()), evidence_limit)
        omitted["evidence"] += omitted_evidence
        item = {
            "source_repository_id": _string(edge.get("source_repository_id")),
            "target_repository_id": _string(edge.get("target_repository_id")),
            "relationship_type": _string(edge.get("relationship_type")),
            "origin": _string(edge.get("origin")),
            "confidence": _string(edge.get("confidence")),
            "confidence_score": _score(edge.get("confidence_score")),
            "explicit": bool(edge.get("explicit")),
            "inferred": bool(edge.get("inferred")),
            "contract_names": _string_tuple(edge.get("contract_names", ())),
            "evidence": evidence,
            "warnings": _string_tuple(edge.get("warnings", ())),
            "representation_tier": TIER_RELATIONSHIP_SUMMARY,
        }
        score = _relationship_relevance(edge, task_tokens, selected_ids)
        scored.append((score, item))
    return _take_scored(scored, limit, "relationships", omitted)


def _select_contracts(value: Any, task_tokens: set[str], selected_ids: set[str], limit: int, omitted: dict[str, int]) -> tuple[dict[str, Any], ...]:
    scored = []
    for finding in _contract_findings_to_dicts(value):
        repos = tuple(sorted({str(item.get("repository_id")) for item in finding.get("location_findings", ()) if isinstance(item, Mapping) and item.get("repository_id")}))
        item = _redact_json(
            {
                "name": _string(finding.get("name")),
                "contract_type": _string(finding.get("contract_type")),
                "status": _string(finding.get("status")),
                "severity": _string(finding.get("severity")),
                "affected_repository_ids": repos,
                "mismatch_summary": _contract_mismatch_summary(finding),
                "representation_tier": TIER_CONTRACT_SUMMARY,
            }
        )
        score = _contract_relevance(finding, task_tokens, selected_ids)
        scored.append((score, item))
    return _take_scored(scored, limit, "contracts", omitted)


def _select_unresolved(graph: Mapping[str, Any], task_tokens: set[str], selected_ids: set[str], limit: int, evidence_limit: int, omitted: dict[str, int]) -> tuple[dict[str, Any], ...]:
    scored = []
    for unresolved in graph.get("unresolved_relationships", ()) or ():
        if not isinstance(unresolved, Mapping):
            continue
        evidence, omitted_evidence = _evidence_summaries(unresolved.get("evidence", ()), evidence_limit)
        omitted["evidence"] += omitted_evidence
        item = {
            "source_repository_id": _optional_string(unresolved.get("source_repository_id")),
            "target_repository_id": _optional_string(unresolved.get("target_repository_id")),
            "relationship_type": _optional_string(unresolved.get("relationship_type")),
            "reason": _string(unresolved.get("reason")),
            "origin": _string(unresolved.get("origin")),
            "evidence": evidence,
            "representation_tier": TIER_RELATIONSHIP_SUMMARY,
        }
        score = _relationship_relevance(unresolved, task_tokens, selected_ids) + 20
        scored.append((score, item))
    return _take_scored(scored, limit, "unresolved_relationships", omitted)


def _select_diagnostics(diagnostics: Iterable[Any], task_tokens: set[str], selected_ids: set[str], limit: int, omitted: dict[str, int]) -> tuple[dict[str, Any], ...]:
    scored = []
    for diagnostic in diagnostics:
        item = diagnostic.to_dict() if hasattr(diagnostic, "to_dict") else dict(diagnostic) if isinstance(diagnostic, Mapping) else None
        if not isinstance(item, Mapping):
            continue
        normalized = _redact_json(
            {
                "stage": _string(item.get("stage", "workspace")),
                "code": _string(item.get("code")),
                "severity": _string(item.get("severity", "warning")),
                "summary": _string(item.get("summary", item.get("message", ""))),
                "repository_ids": _string_tuple(item.get("repository_ids", ())),
                "representation_tier": TIER_RELATIONSHIP_SUMMARY,
            }
        )
        score = _diagnostic_relevance(normalized, task_tokens, selected_ids)
        scored.append((score, normalized))
    return _take_scored(scored, limit, "diagnostics", omitted)


def _take_scored(scored: list[tuple[float, dict[str, Any]]], limit: int, key: str, omitted: dict[str, int]) -> tuple[dict[str, Any], ...]:
    ordered = sorted(scored, key=lambda pair: (-pair[0], _json_key(pair[1])))
    if len(ordered) > limit:
        omitted[key] += len(ordered) - limit
    return tuple(_redact_json(item) for _, item in ordered[:limit])


def _repository_relevance(node: Mapping[str, Any], task_tokens: set[str]) -> float:
    text_tokens = _tokens(" ".join(str(node.get(key, "")) for key in ("repository_id", "display_name", "role", "path")))
    score = 10.0 * len(task_tokens & text_tokens)
    if node.get("configured"):
        score += 5
    if node.get("role_confidence") == "high":
        score += 3
    return score


def _relationship_relevance(edge: Mapping[str, Any], task_tokens: set[str], selected_ids: set[str]) -> float:
    text_tokens = _tokens(" ".join(str(edge.get(key, "")) for key in ("source_repository_id", "target_repository_id", "relationship_type", "origin", "description")))
    for name in edge.get("contract_names", ()) or ():
        text_tokens.update(_tokens(str(name)))
    score = 8.0 * len(task_tokens & text_tokens)
    if edge.get("source_repository_id") in selected_ids or edge.get("target_repository_id") in selected_ids:
        score += 12
    if edge.get("explicit"):
        score += 20
    if edge.get("confidence") == "high":
        score += 8
    elif edge.get("confidence") == "medium":
        score += 4
    return score


def _contract_relevance(finding: Mapping[str, Any], task_tokens: set[str], selected_ids: set[str]) -> float:
    repos = {str(item.get("repository_id")) for item in finding.get("location_findings", ()) if isinstance(item, Mapping)}
    text_tokens = _tokens(" ".join(str(finding.get(key, "")) for key in ("name", "contract_type", "status", "severity")))
    score = 8.0 * len(task_tokens & text_tokens)
    if repos & selected_ids:
        score += 10
    if finding.get("severity") == "error" and finding.get("status") not in {"consistent", "missing", ""}:
        score += 30
    elif finding.get("status") not in {"consistent", "", None}:
        score += 15
    return score


def _diagnostic_relevance(item: Mapping[str, Any], task_tokens: set[str], selected_ids: set[str]) -> float:
    text_tokens = _tokens(" ".join(str(item.get(key, "")) for key in ("code", "summary", "stage", "severity")))
    score = 6.0 * len(task_tokens & text_tokens)
    if set(item.get("repository_ids", ()) or ()) & selected_ids:
        score += 8
    if item.get("severity") == "error":
        score += 25
    elif item.get("severity") == "warning":
        score += 10
    return score


def _contract_mismatch_summary(finding: Mapping[str, Any]) -> str:
    status = str(finding.get("status") or "")
    if status == "consistent":
        return "consistent across configured locations"
    if status:
        return f"{status} across configured locations; values redacted"
    return "contract status unavailable"


def _evidence_summaries(evidence: Iterable[Any], limit: int) -> tuple[tuple[dict[str, Any], ...], int]:
    items = []
    for raw in evidence or ():
        item = raw.to_dict() if hasattr(raw, "to_dict") else dict(raw) if isinstance(raw, Mapping) else None
        if not isinstance(item, Mapping):
            continue
        items.append(
            _redact_json(
                {
                    "signal_type": _string(item.get("signal_type")),
                    "source_repository_id": _string(item.get("source_repository_id")),
                    "target_repository_id": _optional_string(item.get("target_repository_id")),
                    "source_path": _optional_string(item.get("source_path")),
                    "summary": _string(item.get("summary")),
                    "strength": _string(item.get("strength")),
                }
            )
        )
    ordered = tuple(sorted(items, key=_json_key))
    return ordered[:limit], max(0, len(ordered) - limit)


def _workspace_token_allocation(profile: Mapping[str, Any], share: float) -> int:
    target = int(profile["target_context_tokens"])
    reserved = int(profile["reserved_output_tokens"])
    safety = float(profile["safety_margin"])
    max_pack = int(profile["max_context_pack_tokens"])
    usable = max(0, min(max_pack, target - reserved) - int(target * safety))
    return max(1, int(usable * share))


def _estimate_representation_tokens(summary: Mapping[str, Any], items: Mapping[str, tuple[dict[str, Any], ...]]) -> int:
    return estimate_tokens_conservative(json.dumps({"workspace_summary": summary, **items}, sort_keys=True, separators=(",", ":")))


def estimate_tokens_conservative(text: str | None) -> int:
    length = len(str(text or ""))
    if length <= 0:
        return 0
    return max(1, (length + 2) // 3)


def _downgrade_one(items: dict[str, tuple[dict[str, Any], ...]], omitted: dict[str, int], savings: list[dict[str, Any]]) -> bool:
    candidates = []
    for collection, values in items.items():
        for index, item in enumerate(values):
            if item.get("representation_tier") not in {TIER_WORKSPACE_SUMMARY, TIER_RELATIONSHIP_SUMMARY, TIER_CONTRACT_SUMMARY}:
                continue
            candidates.append((collection, index, _item_priority(item)))
    if not candidates:
        return False
    collection, index, _ = sorted(candidates, key=lambda value: (value[2], value[0], _json_key(items[value[0]][value[1]])))[0]
    values = list(items[collection])
    before = estimate_tokens_conservative(json.dumps(values[index], sort_keys=True))
    values[index] = _identity_only(values[index])
    after = estimate_tokens_conservative(json.dumps(values[index], sort_keys=True))
    items[collection] = tuple(values)
    omitted["downgraded"] += 1
    savings.append(_savings_entry(collection, values[index], before, after, "downgraded to identity only"))
    return True


def _skip_one(items: dict[str, tuple[dict[str, Any], ...]], omitted: dict[str, int], savings: list[dict[str, Any]]) -> bool:
    candidates = []
    for collection, values in items.items():
        for index, item in enumerate(values):
            if item.get("representation_tier") == TIER_SKIPPED:
                continue
            candidates.append((collection, index, _item_priority(item)))
    if not candidates:
        return False
    collection, index, _ = sorted(candidates, key=lambda value: (value[2], value[0], _json_key(items[value[0]][value[1]])))[0]
    values = list(items[collection])
    before = estimate_tokens_conservative(json.dumps(values[index], sort_keys=True))
    values[index] = {**_identity_only(values[index]), "representation_tier": TIER_SKIPPED, "skip_reason": "workspace budget exhausted"}
    items[collection] = tuple(values)
    omitted["skipped"] += 1
    savings.append(_savings_entry(collection, values[index], before, 0, "skipped after downgrade"))
    return True


def _identity_only(item: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "repository_id",
        "display_name",
        "role",
        "source_repository_id",
        "target_repository_id",
        "relationship_type",
        "name",
        "contract_type",
        "status",
        "severity",
        "reason",
        "code",
        "summary",
    )
    return {key: item[key] for key in keys if key in item and item[key] is not None} | {"representation_tier": TIER_IDENTITY_ONLY}


def _item_priority(item: Mapping[str, Any]) -> float:
    if item.get("severity") == "error":
        return 100
    if item.get("explicit"):
        return 90
    if item.get("confidence") == "high":
        return 70
    if item.get("status") not in {None, "", "consistent"}:
        return 60
    return 10


def _savings_entry(collection: str, item: Mapping[str, Any], before: int, after: int, reason: str) -> dict[str, Any]:
    return {
        "item": _item_label(collection, item),
        "collection": collection,
        "savings_estimated_tokens": max(0, before - after),
        "original_estimated_tokens": before,
        "estimated_tokens": after,
        "reason": reason,
    }


def _item_label(collection: str, item: Mapping[str, Any]) -> str:
    if "repository_id" in item:
        return str(item["repository_id"])
    if "source_repository_id" in item or "target_repository_id" in item:
        return f"{item.get('source_repository_id')}->{item.get('target_repository_id')}:{item.get('relationship_type')}"
    if "name" in item:
        return str(item["name"])
    return f"{collection}:{item.get('code', item.get('reason', 'item'))}"


def _budget_summary(
    profile: Mapping[str, Any],
    allocation: int,
    used: int,
    share: float,
    items: Mapping[str, tuple[dict[str, Any], ...]],
    omitted: Mapping[str, int],
    savings: list[dict[str, Any]],
    exhausted: bool,
) -> dict[str, Any]:
    return {
        "target_workspace_token_allocation": allocation,
        "estimated_workspace_tokens_used": used,
        "reserved_output_tokens": int(profile["reserved_output_tokens"]),
        "safety_margin": float(profile["safety_margin"]),
        "max_workspace_share": share,
        "repository_representation_counts_by_tier": _counts_by_tier(items["repositories"]),
        "relationship_representation_counts_by_tier": _counts_by_tier((*items["relationships"], *items["unresolved_relationships"], *items["diagnostics"])),
        "contract_representation_counts_by_tier": _counts_by_tier(items["contracts"]),
        "omitted_counts": {key: int(omitted.get(key, 0)) for key in OMITTED_KEYS},
        "largest_workspace_token_savings": sorted(savings, key=lambda item: (-item["savings_estimated_tokens"], item["collection"], item["item"]))[:5],
        "budget_exhausted": bool(exhausted or used > allocation),
        "tokenizer_strategy": "conservative_char_estimate",
    }


def _counts_by_tier(items: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counts = {tier: 0 for tier in REPRESENTATION_TIERS}
    for item in items:
        tier = item.get("representation_tier")
        if tier in counts:
            counts[str(tier)] += 1
    return counts


def _budget_profile(value: Mapping[str, Any] | None) -> dict[str, Any]:
    value = value or {}
    return {
        "target_context_tokens": _nonnegative_int(value.get("target_context_tokens", DEFAULT_TARGET_CONTEXT_TOKENS), "target_context_tokens"),
        "reserved_output_tokens": _nonnegative_int(value.get("reserved_output_tokens", DEFAULT_RESERVED_OUTPUT_TOKENS), "reserved_output_tokens"),
        "max_context_pack_tokens": _nonnegative_int(value.get("max_context_pack_tokens", DEFAULT_MAX_CONTEXT_PACK_TOKENS), "max_context_pack_tokens"),
        "safety_margin": _nonnegative_number(value.get("safety_margin", DEFAULT_SAFETY_MARGIN), "safety_margin"),
    }


def _append_items(lines: list[str], heading: str, items: Iterable[Mapping[str, Any]], keys: tuple[str, ...]) -> None:
    lines.append(heading)
    lines.append("")
    count = 0
    for item in items:
        parts = [str(item.get(key)) for key in keys if item.get(key) not in {None, ""}]
        if parts:
            lines.append(f"- {' | '.join(parts)}")
            count += 1
    if count == 0:
        lines.append("- none")
    lines.append("")


def _redact_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        copied = {}
        for key in sorted(value):
            if _looks_sensitive_key(str(key)):
                copied[str(key)] = SECRET_VALUE
            else:
                copied[str(key)] = _redact_json(value[key])
        return copied
    if isinstance(value, (list, tuple)):
        return tuple(_redact_json(item) for item in value)
    if isinstance(value, str):
        return SECRET_VALUE if _looks_sensitive_value(value) else value
    return value


def _looks_sensitive_key(value: str) -> bool:
    lower = value.lower()
    return any(keyword in lower for keyword in SECRET_KEYWORDS)


def _looks_sensitive_value(value: str) -> bool:
    lower = value.lower()
    if any(keyword in lower for keyword in SECRET_KEYWORDS):
        return True
    return bool(re.search(r"(?i)(sk-[a-z0-9_-]{12,}|github_pat_[a-z0-9_]{12,}|bearer\s+[a-z0-9._-]{12,})", value))


def _copy_mapping_tuple(value: Iterable[Mapping[str, Any]], name: str) -> tuple[Mapping[str, Any], ...]:
    if isinstance(value, (str, bytes)):
        raise WorkspaceContextError(f"{name} must be a sequence of mappings")
    return tuple(_copy_json_mapping(item, name) for item in value)


def _copy_json_mapping(value: Mapping[str, Any], name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise WorkspaceContextError(f"{name} must be a mapping")
    return {str(key): _copy_json(_redact_json(value[key]), f"{name}.{key}") for key in sorted(value)}


def _copy_omitted_counts(value: Mapping[str, Any]) -> dict[str, int]:
    return {key: _nonnegative_int(value.get(key, 0), key) for key in OMITTED_KEYS}


def _copy_json(value: Any, name: str) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise WorkspaceContextError(f"{name} must be finite")
        return value
    if isinstance(value, Mapping):
        return {str(key): _copy_json(value[key], f"{name}.{key}") for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return tuple(_copy_json(item, f"{name}[]") for item in value)
    raise WorkspaceContextError(f"{name} must be JSON-ready")


def _json_ready(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _json_ready(value[key]) for key in sorted(value)}
    return value


def _json_key(value: Any) -> str:
    return json.dumps(_json_ready(value), sort_keys=True, separators=(",", ":"))


def _task_text(value: str | Iterable[str] | None) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return " ".join(str(item).strip() for item in value if str(item).strip())


def _tokens(value: str) -> set[str]:
    return {token for token in re.split(r"[^a-z0-9]+", str(value).lower()) if len(token) >= 2}


def _string(value: Any) -> str:
    return "" if value is None else str(value)


def _optional_string(value: Any) -> str | None:
    return None if value is None else str(value)


def _string_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        return (str(value),) if str(value) else ()
    return tuple(sorted({str(item) for item in value if str(item)}))


def _score(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        return 0.0
    return round(max(0.0, min(1.0, float(value))), 3)


def _validate_limit(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise WorkspaceContextError(f"{name} must be a positive integer")
    return value


def _validate_share(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WorkspaceContextError("max_workspace_share must be numeric")
    share = float(value)
    if not math.isfinite(share) or share <= 0 or share > 1:
        raise WorkspaceContextError("max_workspace_share must be between 0 and 1")
    return round(share, 3)


def _nonnegative_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise WorkspaceContextError(f"{name} must be a non-negative integer")
    return value


def _nonnegative_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WorkspaceContextError(f"{name} must be numeric")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized < 0:
        raise WorkspaceContextError(f"{name} must be non-negative")
    return round(normalized, 3)
