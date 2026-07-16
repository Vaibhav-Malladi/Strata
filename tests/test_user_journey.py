import json

import strata.utils.user_journey as journey
import strata.utils.workspace_config as workspace_config


def _request(**overrides):
    data = {
        "task": "Trace what happens when the user clicks Login",
        "journey_name": "Login",
        "starting_repository_ids": ("frontend", "backend", "frontend"),
        "starting_paths": ("src\\Login.tsx", "src/./routes/../routes/login.tsx"),
        "starting_symbols": ("LoginButton",),
        "route_hints": ("/login",),
        "ui_hints": ("Login",),
        "expected_destination": "session",
    }
    data.update(overrides)
    return journey.JourneyRequest(**data)


def _evidence(**overrides):
    data = {
        "signal_type": "explicit_hint",
        "repository_id": "frontend",
        "path": "src/Login.tsx",
        "summary": "Login button was supplied by the user.",
        "strength": journey.EVIDENCE_STRENGTH_STRONG,
    }
    data.update(overrides)
    return journey.JourneyEvidence(**data)


def _entry(**overrides):
    data = {
        "repository_id": "frontend",
        "path": "src\\Login.tsx",
        "symbol": "LoginButton",
        "entry_point_type": journey.ENTRY_POINT_TYPE_BUTTON,
        "display_label": "Login",
        "confidence": journey.CONFIDENCE_HIGH,
        "confidence_score": 0.95,
        "evidence": (_evidence(),),
        "origin": journey.ORIGIN_EXPLICIT,
    }
    data.update(overrides)
    return journey.JourneyEntryPoint(**data)


def _step(**overrides):
    data = {
        "sequence_hint": 1,
        "repository_id": "frontend",
        "path": "src/Login.tsx",
        "symbol": "handleLogin",
        "step_type": journey.STEP_TYPE_UI_EVENT_HANDLER,
        "summary": "Handle the login click.",
        "confidence": journey.CONFIDENCE_HIGH,
        "confidence_score": 0.9,
        "evidence": (_evidence(),),
        "origin": journey.ORIGIN_EXPLICIT,
    }
    data.update(overrides)
    return journey.JourneyStep(**data)


def _transition(source=None, target=None, **overrides):
    first = source or _step()
    second = target or _step(sequence_hint=2, path="src/api.ts", symbol="login", step_type=journey.STEP_TYPE_API_CLIENT)
    data = {
        "source_step_id": first.step_id,
        "target_step_id": second.step_id,
        "transition_type": journey.TRANSITION_TYPE_CALLS,
        "confidence": journey.CONFIDENCE_HIGH,
        "confidence_score": 0.85,
        "evidence": (_evidence(),),
        "origin": journey.ORIGIN_EXPLICIT,
    }
    data.update(overrides)
    return journey.JourneyTransition(**data)


def _gap(**overrides):
    data = {
        "reason": journey.GAP_REASON_DYNAMIC_CALL_UNRESOLVED,
        "summary": "Dynamic callback target could not be confirmed.",
        "severity": journey.DIAGNOSTIC_SEVERITY_WARNING,
        "source_step_id": _step().step_id,
        "repository_id": "frontend",
        "path": "src/Login.tsx",
        "symbol": "handleLogin",
        "evidence": (_evidence(),),
    }
    data.update(overrides)
    return journey.JourneyGap(**data)


def _codes(result):
    return {item["code"] for item in result.to_dict()["diagnostics"]}


def test_request_contract_normalizes_and_serializes():
    request = _request(starting_paths=("src\\Login.tsx", "src/./Login.tsx"))
    payload = request.to_dict()
    assert payload["task"] == "Trace what happens when the user clicks Login"
    assert payload["task_keywords"] == ["clicks", "login"]
    assert payload["starting_repository_ids"] == ["backend", "frontend"]
    assert payload["starting_paths"] == ["src/Login.tsx"]
    assert json.loads(json.dumps(payload, sort_keys=True)) == payload


def test_empty_task_rejected_and_path_normalization_is_safe():
    try:
        journey.JourneyRequest(task=" ")
    except journey.UserJourneyError as error:
        assert "task" in str(error)
    else:
        raise AssertionError("empty task was accepted")

    try:
        _request(starting_paths=("../outside.py",))
    except journey.UserJourneyError as error:
        assert "escape" in str(error)
    else:
        raise AssertionError("path traversal was accepted")


def test_entry_point_contract_validation_identity_and_caps():
    entry = _entry()
    assert entry.path == "src/Login.tsx"
    assert journey.entry_point_identity_key(entry) == ("frontend", "src/Login.tsx", "LoginButton", journey.ENTRY_POINT_TYPE_BUTTON)

    try:
        _entry(entry_point_type="tap_zone")
    except journey.UserJourneyError as error:
        assert "entry_point_type" in str(error)
    else:
        raise AssertionError("unsupported entry-point type was accepted")

    try:
        _entry(confidence_score=2.0)
    except journey.UserJourneyError as error:
        assert "confidence_score" in str(error)
    else:
        raise AssertionError("invalid confidence score was accepted")

    entries = tuple(_entry(symbol=f"Button{index}", confidence_score=1.0 - index / 100) for index in range(3))
    result = journey.build_user_journey_result(_request(), entry_points=entries, max_entry_points=2)
    assert result.to_dict()["summary"]["entry_point_count"] == 2
    assert journey.DIAGNOSTIC_JOURNEY_ENTRY_POINT_CAP_REACHED in _codes(result)


def test_duplicate_and_conflicting_entry_points_are_diagnosed():
    entry = _entry()
    conflicting = _entry(display_label="Sign in")
    result = journey.build_user_journey_result(_request(), entry_points=(entry, entry, conflicting))
    payload = result.to_dict()
    assert payload["summary"]["entry_point_count"] == 1
    assert journey.DIAGNOSTIC_JOURNEY_ENTRY_POINT_DUPLICATE in _codes(result)


def test_step_contract_phase_identity_and_all_major_phases():
    cases = {
        journey.STEP_TYPE_USER_ACTION: journey.PHASE_ENTRY,
        journey.STEP_TYPE_COMPONENT_METHOD: journey.PHASE_FRONTEND,
        journey.STEP_TYPE_API_REQUEST: journey.PHASE_BOUNDARY,
        journey.STEP_TYPE_BACKEND_HANDLER: journey.PHASE_BACKEND,
        journey.STEP_TYPE_DATABASE_ACCESS: journey.PHASE_DATA,
        journey.STEP_TYPE_EXTERNAL_SERVICE: journey.PHASE_EXTERNAL,
        journey.STEP_TYPE_RESPONSE: journey.PHASE_RESPONSE,
        journey.STEP_TYPE_FRONTEND_UPDATE: journey.PHASE_FRONTEND_COMPLETION,
        journey.STEP_TYPE_UNKNOWN: journey.PHASE_UNKNOWN,
    }
    for step_type, phase in cases.items():
        step = _step(step_type=step_type, symbol=step_type, semantic_discriminator=step_type)
        assert step.phase == phase
        assert journey.derive_phase(step_type) == phase

    first = _step(path="src\\Login.tsx")
    second = _step(path="src/Login.tsx")
    assert first.step_id == second.step_id
    assert journey.step_identity_key(first) == ("frontend", "src/Login.tsx", "handleLogin", journey.STEP_TYPE_UI_EVENT_HANDLER, "")

    try:
        _step(step_type="java_filter")
    except journey.UserJourneyError as error:
        assert "step_type" in str(error)
    else:
        raise AssertionError("unsupported step type was accepted")


def test_steps_deduplicate_conflict_and_apply_evidence_and_step_caps():
    evidence = tuple(_evidence(signal_type=f"hint_{index}", summary=f"Evidence {index}") for index in range(4))
    step = _step(evidence=evidence)
    conflicting = _step(summary="Different handler summary.", evidence=evidence)
    result = journey.build_user_journey_result(_request(), steps=(step, step, conflicting), max_evidence_per_step=2)
    payload = result.to_dict()
    assert payload["summary"]["step_count"] == 1
    assert len(payload["steps"][0]["evidence"]) == 2
    assert journey.DIAGNOSTIC_JOURNEY_STEP_DUPLICATE in _codes(result)
    assert journey.DIAGNOSTIC_JOURNEY_STEP_CONFLICT in _codes(result)
    assert journey.DIAGNOSTIC_JOURNEY_EVIDENCE_TRUNCATED in _codes(result)

    many = tuple(_step(sequence_hint=index, symbol=f"step_{index}") for index in range(4))
    capped = journey.build_user_journey_result(_request(), steps=many, max_steps=2)
    assert capped.to_dict()["summary"]["step_count"] == 2
    assert journey.DIAGNOSTIC_JOURNEY_STEP_CAP_REACHED in _codes(capped)


def test_transition_contracts_unknown_steps_duplicates_conflicts_and_caps():
    source = _step(sequence_hint=1, symbol="source")
    target = _step(sequence_hint=2, repository_id="backend", path="app/login.py", symbol="target", step_type=journey.STEP_TYPE_BACKEND_HANDLER)
    other = _step(sequence_hint=3, repository_id="backend", path="app/audit.py", symbol="audit", step_type=journey.STEP_TYPE_BACKEND_SERVICE)
    transition = _transition(source, target, cross_repository=True, relationship_type=workspace_config.RELATIONSHIP_TYPE_CALLS_API)
    duplicate = _transition(source, target, cross_repository=True, relationship_type=workspace_config.RELATIONSHIP_TYPE_CALLS_API)
    conflict = _transition(source, target, cross_repository=True, confidence_score=0.4, relationship_type=workspace_config.RELATIONSHIP_TYPE_CALLS_API)
    second_valid = _transition(target, other, transition_type=journey.TRANSITION_TYPE_CALLS)
    unknown = journey.JourneyTransition("missing", target.step_id, journey.TRANSITION_TYPE_CALLS, journey.CONFIDENCE_LOW, 0.2)

    result = journey.build_user_journey_result(
        _request(),
        steps=(source, target, other),
        transitions=(transition, duplicate, conflict, second_valid, unknown),
        max_transitions=2,
    )
    payload = result.to_dict()
    assert payload["summary"]["transition_count"] == 2
    assert payload["summary"]["cross_repository_transition_count"] == 1
    assert any(item["relationship_type"] == workspace_config.RELATIONSHIP_TYPE_CALLS_API for item in payload["transitions"])
    assert journey.DIAGNOSTIC_JOURNEY_TRANSITION_DUPLICATE in _codes(result)
    assert journey.DIAGNOSTIC_JOURNEY_TRANSITION_CONFLICT in _codes(result)
    assert journey.DIAGNOSTIC_JOURNEY_TRANSITION_UNKNOWN_STEP in _codes(result)

    capped = journey.build_user_journey_result(_request(), steps=(source, target, other), transitions=(transition, second_valid), max_transitions=1)
    assert capped.to_dict()["summary"]["transition_count"] == 1
    assert journey.DIAGNOSTIC_JOURNEY_TRANSITION_CAP_REACHED in _codes(capped)

    try:
        journey.JourneyTransition(source.step_id, source.step_id, journey.TRANSITION_TYPE_CALLS, journey.CONFIDENCE_LOW, 0.1)
    except journey.UserJourneyError as error:
        assert "source and target" in str(error)
    else:
        raise AssertionError("self-transition was accepted")


def test_gap_contracts_reasons_identity_duplicates_evidence_and_caps():
    gap = _gap(reason=journey.GAP_REASON_ENTRY_POINT_NOT_FOUND, severity=journey.DIAGNOSTIC_SEVERITY_ERROR)
    api_gap = _gap(reason=journey.GAP_REASON_API_TARGET_AMBIGUOUS, symbol="api")
    unsupported_gap = _gap(reason=journey.GAP_REASON_UNSUPPORTED_LANGUAGE, symbol="lang")
    dynamic_gap = _gap(reason=journey.GAP_REASON_DYNAMIC_CALL_UNRESOLVED, evidence=tuple(_evidence(signal_type=f"gap_{index}", summary=f"Gap evidence {index}") for index in range(3)))
    assert journey.gap_identity_key(gap)[0] == journey.GAP_REASON_ENTRY_POINT_NOT_FOUND

    result = journey.build_user_journey_result(
        _request(),
        gaps=(gap, gap, api_gap, unsupported_gap, dynamic_gap),
        max_gaps=3,
        max_evidence_per_gap=2,
    )
    payload = result.to_dict()
    assert payload["summary"]["gap_count"] == 3
    assert result.readiness == journey.READINESS_BLOCKED
    assert journey.DIAGNOSTIC_JOURNEY_GAP_DUPLICATE in _codes(result)
    assert journey.DIAGNOSTIC_JOURNEY_GAP_CAP_REACHED in _codes(result)
    assert journey.DIAGNOSTIC_JOURNEY_EVIDENCE_TRUNCATED in _codes(result)


def test_result_summary_readiness_and_deterministic_serialization():
    entry = _entry()
    source = _step(sequence_hint=2, step_type=journey.STEP_TYPE_API_REQUEST, symbol="api")
    target = _step(sequence_hint=1, step_type=journey.STEP_TYPE_BACKEND_HANDLER, repository_id="backend", path="app/login.py", symbol="handler")
    transition = _transition(source, target, transition_type=journey.TRANSITION_TYPE_SENDS_REQUEST, cross_repository=True)
    gap = _gap(reason=journey.GAP_REASON_API_TARGET_AMBIGUOUS)

    first = journey.build_user_journey_result(_request(), entry_points=(entry,), steps=(source, target), transitions=(transition,), gaps=(gap,), readiness=journey.READINESS_PARTIAL)
    second = journey.build_user_journey_result(_request(), gaps=(gap,), transitions=(transition,), steps=(target, source), entry_points=(entry,), readiness=journey.READINESS_PARTIAL)
    payload = first.to_dict()
    assert payload == second.to_dict()
    assert payload["readiness"] == journey.READINESS_PARTIAL
    assert payload["summary"]["entry_point_count"] == 1
    assert payload["summary"]["step_count"] == 2
    assert payload["summary"]["transition_count"] == 1
    assert payload["summary"]["repository_count"] == 2
    assert payload["summary"]["boundary_step_count"] == 1
    assert payload["summary"]["backend_step_count"] == 1
    assert json.dumps(payload, sort_keys=True) == json.dumps(second.to_dict(), sort_keys=True)


def test_minimal_blocked_not_found_and_schema_validation():
    complete = journey.build_user_journey_result(_request(), entry_points=(_entry(),), steps=(_step(),))
    assert complete.readiness == journey.READINESS_COMPLETE

    not_found = journey.build_user_journey_result(_request())
    assert not_found.readiness == journey.READINESS_NOT_FOUND

    blocked = journey.build_user_journey_result(_request(), gaps=(_gap(severity=journey.DIAGNOSTIC_SEVERITY_ERROR),))
    assert blocked.readiness == journey.READINESS_BLOCKED

    try:
        journey.UserJourneyResult(2, _request(), (), (), (), (), (), {}, journey.READINESS_COMPLETE)
    except journey.UserJourneyError as error:
        assert "schema_version" in str(error)
    else:
        raise AssertionError("unsupported schema version was accepted")


def test_diagnostic_cap_and_single_repository_workspace_compatibility():
    diagnostics = tuple(
        journey.JourneyDiagnostic(
            journey.DIAGNOSTIC_JOURNEY_REPOSITORY_UNKNOWN,
            journey.DIAGNOSTIC_SEVERITY_WARNING,
            f"Unknown repository {index}.",
        )
        for index in range(5)
    )
    step = _step(workspace_graph_node_id="node:frontend", workspace_contract_name="auth-header")
    target = _step(sequence_hint=2, symbol="client")
    transition = _transition(
        step,
        target,
        relationship_type=workspace_config.RELATIONSHIP_TYPE_IMPORTS_PACKAGE,
        workspace_graph_edge_id="edge:frontend:shared",
        workspace_contract_name="auth-header",
    )
    result = journey.build_user_journey_result(
        _request(starting_repository_ids=("frontend",)),
        steps=(step, target),
        transitions=(transition,),
        diagnostics=diagnostics,
        max_diagnostics=3,
    )
    payload = result.to_dict()
    assert payload["steps"][0]["workspace_graph_node_id"] == "node:frontend"
    assert payload["transitions"][0]["workspace_graph_edge_id"] == "edge:frontend:shared"
    assert payload["transitions"][0]["relationship_type"] == workspace_config.RELATIONSHIP_TYPE_IMPORTS_PACKAGE
    assert journey.DIAGNOSTIC_JOURNEY_DIAGNOSTIC_CAP_REACHED in _codes(result)


def test_architecture_boundary_does_not_require_workspace_graph():
    assert journey.workspace_config is workspace_config
    assert not hasattr(journey, "workspace_graph")
    assert not hasattr(journey, "commands")

    result = journey.build_user_journey_result(
        _request(starting_repository_ids=("frontend",)),
        steps=(_step(repository_id="frontend"),),
    )
    assert result.to_dict()["summary"]["repository_count"] == 1


def test_builder_uses_supplied_data_only_and_redacts_secrets():
    evidence = _evidence(summary="authorization: Bearer abc123", metadata={"api_key": "abc123", "safe": "ok"})
    step = _step(evidence=(evidence,), metadata={"token": "abc123", "mode": "contract"})
    result = journey.build_user_journey_result(_request(), steps=(step,))
    payload = result.to_dict()
    assert payload["steps"][0]["metadata"]["token"] == journey.SECRET_VALUE
    assert payload["steps"][0]["metadata"]["mode"] == "contract"
    assert payload["steps"][0]["evidence"][0]["metadata"]["api_key"] == journey.SECRET_VALUE
    assert journey.SECRET_VALUE in payload["steps"][0]["evidence"][0]["summary"]


TESTS = [
    test_request_contract_normalizes_and_serializes,
    test_empty_task_rejected_and_path_normalization_is_safe,
    test_entry_point_contract_validation_identity_and_caps,
    test_duplicate_and_conflicting_entry_points_are_diagnosed,
    test_step_contract_phase_identity_and_all_major_phases,
    test_steps_deduplicate_conflict_and_apply_evidence_and_step_caps,
    test_transition_contracts_unknown_steps_duplicates_conflicts_and_caps,
    test_gap_contracts_reasons_identity_duplicates_evidence_and_caps,
    test_result_summary_readiness_and_deterministic_serialization,
    test_minimal_blocked_not_found_and_schema_validation,
    test_diagnostic_cap_and_single_repository_workspace_compatibility,
    test_architecture_boundary_does_not_require_workspace_graph,
    test_builder_uses_supplied_data_only_and_redacts_secrets,
]
