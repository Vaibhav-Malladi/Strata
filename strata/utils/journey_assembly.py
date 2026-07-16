"""Cross-repository journey assembly for Part P6.

The assembler consumes already-produced journey fragments. It does not rerun
entry detection, tracing, API linking, workspace graph construction, or source
file extraction.
"""

from collections.abc import Iterable, Mapping
from typing import Any

import strata.utils.user_journey as user_journey
import strata.utils.workspace_config as workspace_config


DEFAULT_MAX_STEPS = 200
DEFAULT_MAX_TRANSITIONS = 400
DEFAULT_MAX_GAPS = 150
DEFAULT_MAX_DIAGNOSTICS = 250


def assemble_user_journey(
    request: user_journey.JourneyRequest | Mapping[str, Any],
    *,
    entry_points: Iterable[user_journey.JourneyEntryPoint | Mapping[str, Any]] = (),
    frontend_results: Iterable[Any] = (),
    boundary_results: Iterable[Any] = (),
    backend_results: Iterable[Any] = (),
    workspace_graph: Any = None,
    workspace_relationships: Iterable[Any] = (),
    message_results: Iterable[Any] = (),
    max_steps: int = DEFAULT_MAX_STEPS,
    max_transitions: int = DEFAULT_MAX_TRANSITIONS,
    max_gaps: int = DEFAULT_MAX_GAPS,
    max_diagnostics: int = DEFAULT_MAX_DIAGNOSTICS,
) -> user_journey.UserJourneyResult:
    """Assemble supplied P2-P5 fragments into one deterministic journey."""

    request = _coerce_request(request)
    diagnostics: list[user_journey.JourneyDiagnostic] = []
    entries = list(_coerce_entry_point(item) for item in entry_points)
    steps: list[user_journey.JourneyStep] = []
    transitions: list[user_journey.JourneyTransition] = []
    gaps: list[user_journey.JourneyGap] = []

    fragments = []
    fragments.extend(("frontend", item) for item in frontend_results)
    fragments.extend(("boundary", item) for item in boundary_results)
    fragments.extend(("backend", item) for item in backend_results)
    fragments.extend(("message", item) for item in message_results)
    if not fragments and not entries:
        diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_JOURNEY_FRAGMENT_EMPTY, user_journey.DIAGNOSTIC_SEVERITY_WARNING, "No journey fragments were supplied."))

    for stage, fragment in fragments:
        payload = _result_payload(fragment)
        fragment_entries = tuple(_coerce_entry_point(item) for item in payload.get("entry_points", ()))
        entries.extend(fragment_entries)
        fragment_steps = tuple(_coerce_step(item) for item in payload.get("steps", ()))
        fragment_transitions = tuple(_coerce_transition(item) for item in payload.get("transitions", ()))
        fragment_gaps = tuple(_coerce_gap(item) for item in payload.get("gaps", ()))
        fragment_diagnostics = tuple(_coerce_diagnostic(item) for item in payload.get("diagnostics", ()))
        if not fragment_steps and not fragment_entries and not fragment_transitions:
            diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_JOURNEY_FRAGMENT_EMPTY, user_journey.DIAGNOSTIC_SEVERITY_INFO, f"{stage} fragment is empty."))
        steps.extend(fragment_steps)
        transitions.extend(fragment_transitions)
        gaps.extend(fragment_gaps)
        diagnostics.extend(fragment_diagnostics)

    diagnostics.extend(_conflict_diagnostics(steps, transitions))
    diagnostics.extend(_workspace_edge_diagnostics(transitions, workspace_graph, workspace_relationships))
    diagnostics.extend(_graph_diagnostics(entries, steps, transitions))
    gaps.extend(_response_path_gaps(steps, transitions))

    if gaps or diagnostics:
        diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_JOURNEY_PARTIAL_RESULTS_ASSEMBLED, user_journey.DIAGNOSTIC_SEVERITY_INFO, "Journey fragments were assembled with partial or diagnostic information."))
    if len(entries) > 1:
        diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_JOURNEY_MULTIPLE_ENTRY_POINTS, user_journey.DIAGNOSTIC_SEVERITY_INFO, "Multiple journey entry points were supplied.", details={"count": len(entries)}))
    if len(steps) > max_steps or len(transitions) > max_transitions or len(gaps) > max_gaps:
        diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_JOURNEY_ASSEMBLY_CAP_REACHED, user_journey.DIAGNOSTIC_SEVERITY_WARNING, "Journey assembly caps may truncate supplied fragments.", details={"step_count": len(steps), "transition_count": len(transitions), "gap_count": len(gaps)}))

    result = user_journey.build_user_journey_result(
        request,
        entry_points=entries,
        steps=steps,
        transitions=transitions,
        gaps=gaps,
        diagnostics=diagnostics,
        max_steps=max_steps,
        max_transitions=max_transitions,
        max_gaps=max_gaps,
        max_diagnostics=max_diagnostics,
    )
    result = _with_final_graph_diagnostics(result)
    return _with_assembly_summary(result, _assembly_summary(result, entries, steps, transitions))


def _assembly_summary(result: user_journey.UserJourneyResult, raw_entries, raw_steps, raw_transitions) -> dict[str, Any]:
    payload = result.to_dict()
    steps = payload["steps"]
    transitions = payload["transitions"]
    step_ids = {step["step_id"] for step in steps}
    incoming = {transition["target_step_id"] for transition in transitions}
    outgoing = {transition["source_step_id"] for transition in transitions}
    entry_steps = [step for step in steps if step["step_id"] not in incoming]
    terminal_steps = [step for step in steps if step["step_id"] not in outgoing]
    unreachable = _unreachable_count(entry_steps, transitions, step_ids)
    return {
        "entry_step_count": len(entry_steps),
        "terminal_step_count": len(terminal_steps),
        "unreachable_fragment_count": unreachable,
        "cycle_count": _cycle_count(transitions),
        "resolved_boundary_count": sum(1 for item in transitions if item["cross_repository"]),
        "unresolved_boundary_count": sum(1 for gap in payload["gaps"] if gap["reason"] in {user_journey.GAP_REASON_TARGET_REPOSITORY_UNKNOWN, user_journey.GAP_REASON_TARGET_PATH_UNKNOWN, user_journey.GAP_REASON_API_TARGET_AMBIGUOUS}),
        "raw_entry_point_count": len(tuple(raw_entries)),
        "raw_step_count": len(tuple(raw_steps)),
        "raw_transition_count": len(tuple(raw_transitions)),
        "multiple_terminal_source_count": len(terminal_steps),
    }


def _with_final_graph_diagnostics(result: user_journey.UserJourneyResult) -> user_journey.UserJourneyResult:
    existing_codes = {diagnostic.code for diagnostic in result.diagnostics}
    incoming = {transition.target_step_id for transition in result.transitions}
    outgoing = {transition.source_step_id for transition in result.transitions}
    roots = tuple(step for step in result.steps if step.step_id not in incoming)
    terminals = tuple(step for step in result.steps if step.step_id not in outgoing)
    diagnostics = list(result.diagnostics)
    if len(roots) > 1 and user_journey.DIAGNOSTIC_JOURNEY_MULTIPLE_ENTRY_POINTS not in existing_codes:
        diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_JOURNEY_MULTIPLE_ENTRY_POINTS, user_journey.DIAGNOSTIC_SEVERITY_INFO, "Multiple logical journey entry steps remain after assembly.", details={"count": len(roots)}))
    if len(terminals) > 1 and user_journey.DIAGNOSTIC_JOURNEY_MULTIPLE_TERMINAL_STEPS not in existing_codes:
        diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_JOURNEY_MULTIPLE_TERMINAL_STEPS, user_journey.DIAGNOSTIC_SEVERITY_INFO, "Multiple terminal journey steps remain after assembly.", details={"count": len(terminals)}))
    if len(diagnostics) == len(result.diagnostics):
        return result
    return user_journey.UserJourneyResult(result.schema_version, result.request, result.entry_points, result.steps, result.transitions, result.gaps, tuple(diagnostics), result.summary, result.readiness, result.metadata)


def _with_assembly_summary(result: user_journey.UserJourneyResult, assembly_summary: Mapping[str, Any]) -> user_journey.UserJourneyResult:
    summary = {**dict(result.summary), **dict(assembly_summary)}
    return user_journey.UserJourneyResult(result.schema_version, result.request, result.entry_points, result.steps, result.transitions, result.gaps, result.diagnostics, summary, result.readiness, result.metadata)


def _conflict_diagnostics(steps: Iterable[user_journey.JourneyStep], transitions: Iterable[user_journey.JourneyTransition]) -> tuple[user_journey.JourneyDiagnostic, ...]:
    diagnostics = []
    seen_steps: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    for step in steps:
        key = user_journey.step_identity_key(step)
        payload = step.to_dict()
        if key in seen_steps and seen_steps[key] != payload:
            diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_JOURNEY_FRAGMENT_CONFLICT, user_journey.DIAGNOSTIC_SEVERITY_WARNING, "Conflicting step records share an assembly identity.", details={"identity": key}))
        seen_steps.setdefault(key, payload)
    seen_transitions: dict[tuple[str, str, str], dict[str, Any]] = {}
    for transition in transitions:
        key = user_journey.transition_identity_key(transition)
        payload = transition.to_dict()
        if key in seen_transitions and seen_transitions[key] != payload:
            diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_JOURNEY_FRAGMENT_CONFLICT, user_journey.DIAGNOSTIC_SEVERITY_WARNING, "Conflicting transition records share an assembly identity.", details={"identity": key}))
        seen_transitions.setdefault(key, payload)
    return tuple(diagnostics)


def _workspace_edge_diagnostics(transitions: Iterable[user_journey.JourneyTransition], workspace_graph: Any, workspace_relationships: Iterable[Any]) -> tuple[user_journey.JourneyDiagnostic, ...]:
    graph_edges = _workspace_edges(workspace_graph)
    relationship_edges = _relationship_edges(workspace_relationships)
    available = graph_edges | relationship_edges
    diagnostics = []
    for transition in transitions:
        if not transition.cross_repository:
            continue
        relationship_type = transition.relationship_type or workspace_config.RELATIONSHIP_TYPE_CALLS_API
        if available and relationship_type not in available:
            diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_JOURNEY_WORKSPACE_EDGE_MISSING, user_journey.DIAGNOSTIC_SEVERITY_WARNING, "Cross-repository transition has no matching supplied workspace relationship.", details={"relationship_type": relationship_type}))
    return tuple(diagnostics)


def _workspace_edges(graph: Any) -> set[str]:
    payload = graph.to_dict() if hasattr(graph, "to_dict") else graph if isinstance(graph, Mapping) else {}
    return {str(edge.get("relationship_type")) for edge in payload.get("edges", ()) if edge.get("relationship_type")}


def _relationship_edges(values: Iterable[Any]) -> set[str]:
    edges = set()
    for value in values:
        item = value.to_dict() if hasattr(value, "to_dict") else value if isinstance(value, Mapping) else {}
        relationship_type = item.get("relationship_type")
        if relationship_type:
            edges.add(str(relationship_type))
    return edges


def _graph_diagnostics(entries: Iterable[user_journey.JourneyEntryPoint], steps: Iterable[user_journey.JourneyStep], transitions: Iterable[user_journey.JourneyTransition]) -> tuple[user_journey.JourneyDiagnostic, ...]:
    diagnostics = []
    step_ids = {step.step_id for step in steps}
    if _cycle_count(tuple(transition.to_dict() for transition in transitions)):
        diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_JOURNEY_CYCLE_DETECTED, user_journey.DIAGNOSTIC_SEVERITY_WARNING, "Journey assembly detected a cycle and bounded traversal."))
    entry_step_ids = {step.step_id for step in steps if step.step_type == user_journey.STEP_TYPE_USER_ACTION}
    if entries and not entry_step_ids:
        diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_JOURNEY_BOUNDARY_UNRESOLVED, user_journey.DIAGNOSTIC_SEVERITY_WARNING, "Entry points were supplied without matching user-action steps."))
    unreachable = _unreachable_count(tuple(step for step in steps if step.step_type == user_journey.STEP_TYPE_USER_ACTION), tuple(transition.to_dict() for transition in transitions), step_ids)
    if unreachable:
        diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_JOURNEY_FRAGMENT_UNREACHABLE, user_journey.DIAGNOSTIC_SEVERITY_WARNING, "One or more journey fragments are unreachable from the entry path.", details={"count": unreachable}))
    terminal_count = len([step for step in steps if step.step_id not in {transition.source_step_id for transition in transitions}])
    if terminal_count > 1:
        diagnostics.append(_diagnostic(user_journey.DIAGNOSTIC_JOURNEY_MULTIPLE_TERMINAL_STEPS, user_journey.DIAGNOSTIC_SEVERITY_INFO, "Multiple terminal journey steps remain after assembly.", details={"count": terminal_count}))
    return tuple(diagnostics)


def _response_path_gaps(steps: Iterable[user_journey.JourneyStep], transitions: Iterable[user_journey.JourneyTransition]) -> tuple[user_journey.JourneyGap, ...]:
    response_steps = [step for step in steps if step.step_type == user_journey.STEP_TYPE_RESPONSE]
    frontend_completion = [step for step in steps if step.phase == user_journey.PHASE_FRONTEND_COMPLETION]
    if not response_steps or not frontend_completion:
        return ()
    transition_pairs = {(transition.source_step_id, transition.target_step_id) for transition in transitions}
    for response in response_steps:
        if any((response.step_id, completion.step_id) in transition_pairs for completion in frontend_completion):
            return ()
    return (
        user_journey.JourneyGap(
            reason=user_journey.GAP_REASON_RUNTIME_ROUTE_UNRESOLVED,
            summary="Backend response could not be connected to a frontend completion step.",
            severity=user_journey.DIAGNOSTIC_SEVERITY_WARNING,
            source_step_id=response_steps[0].step_id,
        ),
    )


def _unreachable_count(entry_steps: Iterable[Any], transitions: Iterable[Any], step_ids: set[str]) -> int:
    starts = {step.step_id if hasattr(step, "step_id") else step.get("step_id") for step in entry_steps}
    if not starts:
        return 0
    adjacency: dict[str, set[str]] = {}
    for transition in transitions:
        source = transition.source_step_id if hasattr(transition, "source_step_id") else transition.get("source_step_id")
        target = transition.target_step_id if hasattr(transition, "target_step_id") else transition.get("target_step_id")
        adjacency.setdefault(source, set()).add(target)
    reachable = set(starts)
    stack = list(starts)
    while stack:
        current = stack.pop()
        for target in sorted(adjacency.get(current, ())):
            if target not in reachable:
                reachable.add(target)
                stack.append(target)
    return len(step_ids - reachable)


def _cycle_count(transitions: Iterable[Any]) -> int:
    adjacency: dict[str, set[str]] = {}
    for transition in transitions:
        source = transition.source_step_id if hasattr(transition, "source_step_id") else transition.get("source_step_id")
        target = transition.target_step_id if hasattr(transition, "target_step_id") else transition.get("target_step_id")
        adjacency.setdefault(source, set()).add(target)
    visiting: set[str] = set()
    visited: set[str] = set()
    cycles = 0

    def visit(node: str) -> None:
        nonlocal cycles
        if node in visiting:
            cycles += 1
            return
        if node in visited:
            return
        visiting.add(node)
        for target in sorted(adjacency.get(node, ())):
            visit(target)
        visiting.remove(node)
        visited.add(node)

    for node in sorted(adjacency):
        visit(node)
    return cycles


def _result_payload(value: Any) -> Mapping[str, Any]:
    if isinstance(value, user_journey.UserJourneyResult):
        return value.to_dict()
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, Mapping):
        return value
    raise TypeError("journey fragment must be a journey result or mapping")


def _coerce_request(value: user_journey.JourneyRequest | Mapping[str, Any]) -> user_journey.JourneyRequest:
    if isinstance(value, user_journey.JourneyRequest):
        return value
    return user_journey.JourneyRequest(**dict(value))


def _coerce_entry_point(value: user_journey.JourneyEntryPoint | Mapping[str, Any]) -> user_journey.JourneyEntryPoint:
    if isinstance(value, user_journey.JourneyEntryPoint):
        return value
    return user_journey.JourneyEntryPoint(**dict(value))


def _coerce_step(value: user_journey.JourneyStep | Mapping[str, Any]) -> user_journey.JourneyStep:
    if isinstance(value, user_journey.JourneyStep):
        return value
    return user_journey.JourneyStep(**dict(value))


def _coerce_transition(value: user_journey.JourneyTransition | Mapping[str, Any]) -> user_journey.JourneyTransition:
    if isinstance(value, user_journey.JourneyTransition):
        return value
    return user_journey.JourneyTransition(**dict(value))


def _coerce_gap(value: user_journey.JourneyGap | Mapping[str, Any]) -> user_journey.JourneyGap:
    if isinstance(value, user_journey.JourneyGap):
        return value
    return user_journey.JourneyGap(**dict(value))


def _coerce_diagnostic(value: user_journey.JourneyDiagnostic | Mapping[str, Any]) -> user_journey.JourneyDiagnostic:
    if isinstance(value, user_journey.JourneyDiagnostic):
        return value
    return user_journey.JourneyDiagnostic(**dict(value))


def _diagnostic(code: str, severity: str, summary: str, *, details: Mapping[str, Any] | None = None) -> user_journey.JourneyDiagnostic:
    return user_journey.JourneyDiagnostic(code=code, severity=severity, summary=summary, details=details)
