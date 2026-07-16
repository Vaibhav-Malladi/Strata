import json

import strata.utils.journey_assembly as assembly
import strata.utils.user_journey as journey
import strata.utils.workspace_config as workspace_config


def _request():
    return journey.JourneyRequest(task="Trace save journey", ui_hints=("Save",))


def _step(repo, symbol, step_type, sequence=1, path=None, discriminator=None):
    return journey.JourneyStep(repo, path or f"{repo}.py", step_type, f"{symbol} step.", journey.CONFIDENCE_HIGH, 0.9, sequence_hint=sequence, symbol=symbol, semantic_discriminator=discriminator or symbol)


def _transition(source, target, transition_type=journey.TRANSITION_TYPE_CALLS, cross=False):
    return journey.JourneyTransition(source.step_id, target.step_id, transition_type, journey.CONFIDENCE_HIGH, 0.85, cross_repository=cross, relationship_type=workspace_config.RELATIONSHIP_TYPE_CALLS_API if cross else None)


def _result(steps, transitions=(), gaps=(), diagnostics=(), entries=()):
    return journey.build_user_journey_result(_request(), entry_points=entries, steps=steps, transitions=transitions, gaps=gaps, diagnostics=diagnostics)


def test_merge_fragments_deduplicates_steps_and_transitions():
    entry = journey.JourneyEntryPoint("frontend", "Login.tsx", journey.ENTRY_POINT_TYPE_BUTTON, "Save", journey.CONFIDENCE_HIGH, 0.9)
    a = _step("frontend", "click", journey.STEP_TYPE_USER_ACTION)
    b = _step("frontend", "handler", journey.STEP_TYPE_UI_EVENT_HANDLER, 2)
    t = _transition(a, b, journey.TRANSITION_TYPE_HANDLES)
    result = assembly.assemble_user_journey(_request(), entry_points=(entry,), frontend_results=(_result((a, b), (t,), entries=(entry,)),), backend_results=(_result((a, b), (t,)),))
    payload = result.to_dict()
    assert payload["summary"]["step_count"] == 2
    assert payload["summary"]["transition_count"] == 1
    assert payload["summary"]["raw_step_count"] == 4


def test_conflicting_step_and_transition_diagnostics():
    a = _step("frontend", "click", journey.STEP_TYPE_USER_ACTION)
    b = _step("frontend", "handler", journey.STEP_TYPE_UI_EVENT_HANDLER, 2)
    b_conflict = journey.JourneyStep("frontend", "frontend.py", journey.STEP_TYPE_UI_EVENT_HANDLER, "different summary", journey.CONFIDENCE_LOW, 0.2, sequence_hint=2, symbol="handler", semantic_discriminator="handler")
    transition = _transition(a, b)
    conflict_transition = journey.JourneyTransition(a.step_id, b.step_id, journey.TRANSITION_TYPE_CALLS, journey.CONFIDENCE_LOW, 0.2)
    result = assembly.assemble_user_journey(_request(), frontend_results=(_result((a, b), (transition,)),), backend_results=(_result((a, b_conflict), (conflict_transition,)),))
    codes = {item["code"] for item in result.to_dict()["diagnostics"]}
    assert journey.DIAGNOSTIC_JOURNEY_FRAGMENT_CONFLICT in codes
    assert journey.DIAGNOSTIC_JOURNEY_STEP_CONFLICT in codes
    assert journey.DIAGNOSTIC_JOURNEY_TRANSITION_CONFLICT in codes


def test_frontend_to_backend_cross_repository_and_response_gap():
    api = _step("frontend", "/api/save", journey.STEP_TYPE_API_REQUEST, 3)
    boundary = _step("frontend", "/api/save", journey.STEP_TYPE_WORKSPACE_BOUNDARY, 4)
    route = _step("backend", "saveRoute", journey.STEP_TYPE_BACKEND_ROUTE, 5)
    response = _step("backend", "response", journey.STEP_TYPE_RESPONSE, 6)
    update = _step("frontend", "setSaved", journey.STEP_TYPE_FRONTEND_UPDATE, 7)
    result = assembly.assemble_user_journey(
        _request(),
        boundary_results=(_result((api, boundary, route), (_transition(api, boundary, journey.TRANSITION_TYPE_SENDS_REQUEST), _transition(boundary, route, journey.TRANSITION_TYPE_CROSSES_REPOSITORY, True))),),
        backend_results=(_result((response, update), ()),),
    )
    payload = result.to_dict()
    assert payload["summary"]["cross_repository_transition_count"] == 1
    assert payload["summary"]["resolved_boundary_count"] == 1
    assert journey.GAP_REASON_RUNTIME_ROUTE_UNRESOLVED in {gap["reason"] for gap in payload["gaps"]}


def test_iframe_postmessage_single_repo_workspace_optional_and_unreachable():
    host = _step("host", "sendMessage", journey.STEP_TYPE_MESSAGE_SEND)
    iframe = _step("iframe", "receiveMessage", journey.STEP_TYPE_MESSAGE_RECEIVE, 2)
    orphan = _step("shared", "orphan", journey.STEP_TYPE_BACKEND_SERVICE, 3)
    result = assembly.assemble_user_journey(_request(), message_results=(_result((host, iframe, orphan), (_transition(host, iframe, journey.TRANSITION_TYPE_SENDS_MESSAGE, True),)),))
    payload = result.to_dict()
    assert payload["summary"]["repository_count"] == 3
    assert payload["summary"]["unreachable_fragment_count"] >= 0
    assert any(item["transition_type"] == journey.TRANSITION_TYPE_SENDS_MESSAGE for item in payload["transitions"])


def test_cycle_multiple_entry_terminal_ordering_and_caps():
    entry_a = _step("frontend", "a", journey.STEP_TYPE_USER_ACTION, 1)
    entry_b = _step("frontend", "b", journey.STEP_TYPE_USER_ACTION, 2)
    c = _step("frontend", "c", journey.STEP_TYPE_COMPONENT_METHOD, 3)
    result = assembly.assemble_user_journey(_request(), frontend_results=(_result((entry_a, entry_b, c), (_transition(entry_a, c), _transition(c, entry_a))),), max_steps=2, max_transitions=1)
    payload = result.to_dict()
    codes = {item["code"] for item in payload["diagnostics"]}
    assert journey.DIAGNOSTIC_JOURNEY_CYCLE_DETECTED in codes
    assert journey.DIAGNOSTIC_JOURNEY_MULTIPLE_ENTRY_POINTS in codes
    assert journey.DIAGNOSTIC_JOURNEY_ASSEMBLY_CAP_REACHED in codes
    assert json.dumps(payload, sort_keys=True) == json.dumps(result.to_dict(), sort_keys=True)


TESTS = [
    test_merge_fragments_deduplicates_steps_and_transitions,
    test_conflicting_step_and_transition_diagnostics,
    test_frontend_to_backend_cross_repository_and_response_gap,
    test_iframe_postmessage_single_repo_workspace_optional_and_unreachable,
    test_cycle_multiple_entry_terminal_ordering_and_caps,
]
