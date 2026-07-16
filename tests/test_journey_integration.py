import json
from pathlib import Path

import strata.utils.journey_assembly as assembly
import strata.utils.journey_context as context
import strata.utils.journey_readiness as readiness
import strata.utils.user_journey as journey


SCENARIOS_PATH = Path(__file__).parent / "fixtures" / "journeys" / "scenarios.json"


def _request(name):
    return journey.JourneyRequest(task=f"Trace {name}", ui_hints=("save", "login", "message"))


def _step(repo, symbol, step_type, sequence):
    return journey.JourneyStep(repo, f"{repo}/{symbol}.ts", step_type, f"{symbol} step token=super-secret.", journey.CONFIDENCE_HIGH, 0.9, sequence_hint=sequence, symbol=symbol, semantic_discriminator=f"{symbol}:{sequence}")


def _transition(source, target, transition_type=journey.TRANSITION_TYPE_CALLS, cross=False):
    return journey.JourneyTransition(source.step_id, target.step_id, transition_type, journey.CONFIDENCE_HIGH, 0.85, cross_repository=cross)


def _scenario_result(name):
    user = _step("frontend", "entry", journey.STEP_TYPE_USER_ACTION, 1)
    handler = _step("frontend", "handler", journey.STEP_TYPE_UI_EVENT_HANDLER, 2)
    api = _step("frontend", "api", journey.STEP_TYPE_API_REQUEST, 3)
    boundary = _step("frontend", "boundary", journey.STEP_TYPE_WORKSPACE_BOUNDARY, 4)
    backend = _step("backend", "route", journey.STEP_TYPE_BACKEND_ROUTE, 5)
    service = _step("backend", "service", journey.STEP_TYPE_BACKEND_SERVICE, 6)
    response = _step("backend", "response", journey.STEP_TYPE_RESPONSE, 7)
    steps = [user, handler, api, boundary, backend, service, response]
    transitions = [
        _transition(user, handler, journey.TRANSITION_TYPE_HANDLES),
        _transition(handler, api, journey.TRANSITION_TYPE_SENDS_REQUEST),
        _transition(api, boundary, journey.TRANSITION_TYPE_SENDS_REQUEST),
        _transition(boundary, backend, journey.TRANSITION_TYPE_CROSSES_REPOSITORY, True),
        _transition(backend, service),
        _transition(service, response, journey.TRANSITION_TYPE_RETURNS_RESPONSE),
    ]
    gaps = []
    diagnostics = []
    readiness_value = journey.READINESS_COMPLETE
    if name == "ambiguous_api_target":
        gaps.append(journey.JourneyGap(journey.GAP_REASON_API_TARGET_AMBIGUOUS, "Ambiguous API target.", journey.DIAGNOSTIC_SEVERITY_WARNING))
        readiness_value = journey.READINESS_PARTIAL
    if name == "dynamic_frontend_binding":
        gaps.append(journey.JourneyGap(journey.GAP_REASON_FRAMEWORK_BINDING_UNRESOLVED, "Dynamic frontend binding.", journey.DIAGNOSTIC_SEVERITY_WARNING))
        readiness_value = journey.READINESS_PARTIAL
    if name == "dynamic_backend_dispatch":
        gaps.append(journey.JourneyGap(journey.GAP_REASON_DYNAMIC_CALL_UNRESOLVED, "Dynamic backend dispatch.", journey.DIAGNOSTIC_SEVERITY_WARNING))
        readiness_value = journey.READINESS_PARTIAL
    if name == "missing_backend_repository":
        diagnostics.append(journey.JourneyDiagnostic(journey.DIAGNOSTIC_TARGET_REPOSITORY_UNKNOWN, journey.DIAGNOSTIC_SEVERITY_ERROR, "Missing backend repository."))
        readiness_value = journey.READINESS_BLOCKED
    if name == "auth_uncertainty":
        steps.append(_step("backend", "authorize", journey.STEP_TYPE_AUTHORIZATION, 8))
        gaps.append(journey.JourneyGap(journey.GAP_REASON_DEPENDENCY_UNRESOLVED, "Authorization boundary unresolved.", journey.DIAGNOSTIC_SEVERITY_ERROR))
        readiness_value = journey.READINESS_BLOCKED
    if name == "journey_cycle":
        transitions.append(_transition(response, handler, journey.TRANSITION_TYPE_CONTINUES_AS))
    if name == "single_repository_journey":
        steps = [user, handler, response]
        transitions = [_transition(user, handler), _transition(handler, response)]
    if name == "unsupported_pattern":
        diagnostics.append(journey.JourneyDiagnostic(journey.DIAGNOSTIC_JOURNEY_UNSUPPORTED_PATTERN, journey.DIAGNOSTIC_SEVERITY_WARNING, "Unsupported pattern."))
        readiness_value = journey.READINESS_UNSUPPORTED
    return journey.build_user_journey_result(_request(name), steps=steps, transitions=transitions, gaps=gaps, diagnostics=diagnostics, readiness=readiness_value)


def test_all_synthetic_scenarios_are_exercised_end_to_end():
    scenarios = json.loads(SCENARIOS_PATH.read_text(encoding="utf-8"))["scenarios"]
    assert len(scenarios) == 15
    results = []
    for name in scenarios:
        assembled = assembly.assemble_user_journey(_request(name), frontend_results=(_scenario_result(name),))
        represented = context.build_journey_context_representation(_request(name), (assembled,), budget_profile={"target_context_tokens": 300, "reserved_output_tokens": 50, "max_context_pack_tokens": 300, "safety_margin": 0.1})
        ready = readiness.build_journey_readiness(request=_request(name), journey_assembly=assembled, context_representation=represented, unsupported_patterns=("unsupported",) if name == "unsupported_pattern" else ())
        payload = {"journey": assembled.to_dict(), "context": represented.to_dict(), "readiness": ready.to_dict()}
        text = json.dumps(payload, sort_keys=True)
        assert "super-secret" not in text
        assert payload["context"]["budget_summary"]["part_i_authoritative"] is True
        assert payload["readiness"]["safe_fallback"]["no_automatic_writes"] is True
        results.append(payload)
    assert len(results) == 15
    assert any(item["readiness"]["status"] == readiness.STATUS_BLOCKED for item in results)
    assert any(item["readiness"]["status"] == readiness.STATUS_UNSUPPORTED for item in results)
    assert any(item["journey"]["summary"].get("cycle_count", 0) >= 1 for item in results)


def test_architecture_and_safety_strings_remain_bounded():
    module_paths = [
        Path("strata/utils/journey_backend.py"),
        Path("strata/utils/journey_assembly.py"),
        Path("strata/utils/journey_context.py"),
        Path("strata/utils/journey_readiness.py"),
    ]
    for path in module_paths:
        source = path.read_text(encoding="utf-8")
        assert "strata.core" not in source
        assert "strata.commands" not in source
        assert "requests." not in source
        assert "subprocess" not in source
        assert "rglob(" not in source
        assert "os.walk" not in source


TESTS = [
    test_all_synthetic_scenarios_are_exercised_end_to_end,
    test_architecture_and_safety_strings_remain_bounded,
]
