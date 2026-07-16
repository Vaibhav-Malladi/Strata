import json

import strata.utils.journey_context as context
import strata.utils.user_journey as journey


def _request():
    return journey.JourneyRequest(task="Trace login authorization", ui_hints=("Login",), starting_symbols=("login",))


def _entry(origin=journey.ORIGIN_EXPLICIT):
    return journey.JourneyEntryPoint("frontend", "Login.tsx", journey.ENTRY_POINT_TYPE_BUTTON, "Login", journey.CONFIDENCE_HIGH, 0.95, symbol="login", origin=origin)


def _step(repo, symbol, step_type, sequence=1):
    return journey.JourneyStep(repo, f"{repo}.py", step_type, f"{symbol} step.", journey.CONFIDENCE_HIGH, 0.9, sequence_hint=sequence, symbol=symbol, semantic_discriminator=symbol)


def _transition(source, target):
    return journey.JourneyTransition(source.step_id, target.step_id, journey.TRANSITION_TYPE_CALLS, journey.CONFIDENCE_HIGH, 0.85)


def _journey(name, *, complete=True, explicit=True, gaps=(), extra_steps=()):
    user = _step("frontend", "login", journey.STEP_TYPE_USER_ACTION, 1)
    api = _step("frontend", "api", journey.STEP_TYPE_API_REQUEST, 2)
    route = _step("backend", "route", journey.STEP_TYPE_BACKEND_ROUTE, 3)
    auth = _step("backend", "authorize", journey.STEP_TYPE_AUTHORIZATION, 4)
    response = _step("backend", "response", journey.STEP_TYPE_RESPONSE, 5)
    return journey.build_user_journey_result(
        journey.JourneyRequest(task=name, journey_name=name),
        entry_points=(_entry(journey.ORIGIN_EXPLICIT if explicit else journey.ORIGIN_INFERRED),),
        steps=(user, api, route, auth, response, *extra_steps),
        transitions=(_transition(user, api), _transition(api, route), _transition(route, auth), _transition(auth, response)),
        gaps=gaps,
        readiness=journey.READINESS_COMPLETE if complete else journey.READINESS_PARTIAL,
    )


def test_exact_task_explicit_complete_journey_ranks_first():
    exact = _journey("Trace login authorization", complete=True, explicit=True)
    weak = _journey("Unrelated weak", complete=False, explicit=False, gaps=(journey.JourneyGap(journey.GAP_REASON_UNKNOWN, "Unknown.", journey.DIAGNOSTIC_SEVERITY_WARNING),))
    ranked = context.rank_journeys(_request(), (weak, exact))
    assert ranked[0].request.task == "Trace login authorization"


def test_critical_path_branch_reduction_and_cycle_safety():
    result = _journey("Trace login authorization")
    path = context.critical_path(result)
    assert path[0].step_type == journey.STEP_TYPE_USER_ACTION
    assert any(step.step_type == journey.STEP_TYPE_API_REQUEST for step in path)
    assert len(context.critical_path(result, max_steps=2)) == 2


def test_budget_share_reserved_margin_downgrade_and_caps():
    noisy_steps = tuple(_step("backend", f"service_{index}", journey.STEP_TYPE_BACKEND_SERVICE, 10 + index) for index in range(40))
    high_gap = journey.JourneyGap(journey.GAP_REASON_API_TARGET_AMBIGUOUS, "Authorization target ambiguous.", journey.DIAGNOSTIC_SEVERITY_ERROR)
    result = _journey("Trace login authorization", complete=False, gaps=(high_gap,), extra_steps=noisy_steps)
    representation = context.build_journey_context_representation(
        _request(),
        (result,),
        budget_profile={"target_context_tokens": 120, "reserved_output_tokens": 20, "max_context_pack_tokens": 120, "safety_margin": 0.1},
        max_steps_per_journey=5,
        max_transitions_per_journey=3,
        max_gaps_per_journey=1,
        max_diagnostics_per_journey=1,
    ).to_dict()
    assert representation["budget_summary"]["target_journey_token_allocation"] <= 25
    assert representation["budget_summary"]["reserved_output_tokens"] == 20
    assert representation["budget_summary"]["safety_margin"] == 0.1
    assert representation["omitted_counts"]["steps"] > 0
    assert representation["budget_summary"]["journey_representation_counts_by_tier"]


def test_identity_only_fallback_journey_count_cap_and_budget_exhaustion():
    journeys = tuple(_journey(f"Trace login authorization {index}") for index in range(4))
    representation = context.build_journey_context_representation(
        _request(),
        journeys,
        budget_profile={"target_context_tokens": 4, "reserved_output_tokens": 1, "max_context_pack_tokens": 4, "safety_margin": 0},
        max_journeys=2,
    ).to_dict()
    assert representation["omitted_counts"]["journeys"] == 2
    assert representation["budget_summary"]["part_i_authoritative"] is True
    assert representation["budget_summary"]["budget_exhausted"] in {True, False}


def test_markdown_json_no_journey_and_redaction_determinism():
    result = _journey("Trace login authorization", extra_steps=(_step("backend", "api_token_secret", journey.STEP_TYPE_EXTERNAL_SERVICE, 9),))
    first = context.build_journey_context_representation(_request(), (result,)).to_dict()
    second = context.build_journey_context_representation(_request(), (result,)).to_dict()
    assert first == second
    assert "## User journey context" in first["markdown"]
    assert "User journey context" in context.render_journey_context_markdown(_request(), first["journeys"])
    assert context.build_journey_context_representation(_request(), ()).to_dict()["markdown"] == ""
    assert json.dumps(first, sort_keys=True)


TESTS = [
    test_exact_task_explicit_complete_journey_ranks_first,
    test_critical_path_branch_reduction_and_cycle_safety,
    test_budget_share_reserved_margin_downgrade_and_caps,
    test_identity_only_fallback_journey_count_cap_and_budget_exhaustion,
    test_markdown_json_no_journey_and_redaction_determinism,
]
