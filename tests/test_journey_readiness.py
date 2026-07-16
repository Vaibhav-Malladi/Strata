import json

import strata.utils.journey_readiness as readiness
import strata.utils.user_journey as journey


def _request():
    return journey.JourneyRequest(task="Trace login")


def _step(step_type=journey.STEP_TYPE_USER_ACTION):
    return journey.JourneyStep("frontend", "Login.tsx", step_type, "Step.", journey.CONFIDENCE_HIGH, 0.9, symbol=step_type, semantic_discriminator=step_type)


def _result(*, gaps=(), diagnostics=(), readiness_value=journey.READINESS_COMPLETE):
    return journey.build_user_journey_result(_request(), steps=(_step(),), gaps=gaps, diagnostics=diagnostics, readiness=readiness_value)


def _payload(result):
    return result.to_dict()


def test_ready_complete_journey_and_stage_summaries():
    result = readiness.build_journey_readiness(request=_request(), journey_assembly=_result())
    payload = _payload(result)
    assert payload["status"] == readiness.STATUS_READY
    assert payload["safe_fallback"]["normal_repository_context_available"] is True
    assert any(stage["stage"] == readiness.STAGE_JOURNEY_ASSEMBLY for stage in payload["stages"])


def test_partial_with_gaps_and_deterministic_recommendation():
    gap = journey.JourneyGap(journey.GAP_REASON_API_TARGET_AMBIGUOUS, "Ambiguous API target.", journey.DIAGNOSTIC_SEVERITY_WARNING)
    result = readiness.build_journey_readiness(request=_request(), journey_assembly=_result(gaps=(gap,), readiness_value=journey.READINESS_PARTIAL))
    payload = _payload(result)
    assert payload["status"] == readiness.STATUS_PARTIAL
    assert payload["recommended_action"] == "Resolve ambiguous API port ownership."
    assert payload == readiness.build_journey_readiness(request=_request(), journey_assembly=_result(gaps=(gap,), readiness_value=journey.READINESS_PARTIAL)).to_dict()


def test_blocked_safety_critical_boundary():
    diagnostic = journey.JourneyDiagnostic(journey.DIAGNOSTIC_TARGET_REPOSITORY_UNKNOWN, journey.DIAGNOSTIC_SEVERITY_ERROR, "Target repository unknown.")
    result = readiness.build_journey_readiness(request=_request(), api_boundary_linking=_result(diagnostics=(diagnostic,), readiness_value=journey.READINESS_BLOCKED))
    payload = _payload(result)
    assert payload["status"] == readiness.STATUS_BLOCKED
    assert payload["recommended_action"] == "Add the backend repository to workspace configuration."


def test_not_found_unsupported_and_unavailable_stage_failure():
    not_found = readiness.build_journey_readiness()
    assert _payload(not_found)["status"] == readiness.STATUS_NOT_FOUND
    unsupported = readiness.build_journey_readiness(request=_request(), unsupported_patterns=("java",))
    assert _payload(unsupported)["status"] == readiness.STATUS_UNSUPPORTED
    unavailable = readiness.build_journey_readiness(request=_request(), stage_failures={readiness.STAGE_BACKEND_TRACING: "boom"})
    assert _payload(unavailable)["status"] == readiness.STATUS_UNAVAILABLE
    assert _payload(unavailable)["safe_fallback"]["journey_context_safe_to_skip"] is True


def test_single_repository_workspace_context_fallback_and_diagnostic_cap():
    diagnostics = tuple(
        journey.JourneyDiagnostic(journey.DIAGNOSTIC_JOURNEY_BOUNDARY_UNRESOLVED, journey.DIAGNOSTIC_SEVERITY_WARNING, f"warning {index}")
        for index in range(5)
    )
    result = readiness.build_journey_readiness(request=_request(), journey_assembly=_result(diagnostics=diagnostics, readiness_value=journey.READINESS_PARTIAL), max_diagnostics=3)
    payload = _payload(result)
    assert len(payload["diagnostics"]) == 3
    assert payload["safe_fallback"]["workspace_context_available"] is True
    assert any(item["code"] == journey.DIAGNOSTIC_JOURNEY_DIAGNOSTIC_CAP_REACHED for item in payload["diagnostics"])


def test_redaction_and_serialization_are_deterministic():
    diagnostic = journey.JourneyDiagnostic(journey.DIAGNOSTIC_JOURNEY_BOUNDARY_UNRESOLVED, journey.DIAGNOSTIC_SEVERITY_WARNING, "Authorization token=super-secret")
    first = readiness.build_journey_readiness(request=_request(), journey_assembly=_result(diagnostics=(diagnostic,), readiness_value=journey.READINESS_PARTIAL)).to_dict()
    second = readiness.build_journey_readiness(request=_request(), journey_assembly=_result(diagnostics=(diagnostic,), readiness_value=journey.READINESS_PARTIAL)).to_dict()
    assert first == second
    assert "super-secret" not in json.dumps(first, sort_keys=True)


TESTS = [
    test_ready_complete_journey_and_stage_summaries,
    test_partial_with_gaps_and_deterministic_recommendation,
    test_blocked_safety_critical_boundary,
    test_not_found_unsupported_and_unavailable_stage_failure,
    test_single_repository_workspace_context_fallback_and_diagnostic_cap,
    test_redaction_and_serialization_are_deterministic,
]
