import copy
import json

import strata.core.session_state as session_state
from strata.core.delivery_surfaces import DELIVERY_SURFACE_CLI, build_delivery_payload
from strata.core.prompt_templates import PROMPT_TEMPLATE_SCHEMA_VERSION, PROMPT_TEMPLATE_VERSION
from strata.core.session_state import (
    SESSION_STATUS_ACCEPTED_FOR_REVIEW,
    SESSION_STATUS_CLOSED,
    SESSION_STATUS_DELIVERED,
    SESSION_STATUS_PREPARED,
    SESSION_STATUS_REJECTED,
    SESSION_STATUS_RESPONSE_RECEIVED,
    SESSION_STATUS_RETRY_READY,
    SESSION_STATUSES,
    close_session_state,
    create_session_state,
    record_session_delivery,
    record_session_response,
    record_session_validation,
)


def test_stable_session_status_vocabulary():
    assert SESSION_STATUSES == (
        "prepared",
        "delivered",
        "response_received",
        "retry_ready",
        "accepted_for_review",
        "rejected",
        "closed",
    )


def test_session_creation_returns_prepared():
    state = _session()

    assert state["status"] == SESSION_STATUS_PREPARED
    assert state["turn_count"] == 0
    assert state["retry_count"] == 0
    assert state["turns"] == []
    assert state["latest_validation"] is None


def test_caller_supplied_session_id_is_preserved():
    state = _session(session_id="caller-supplied-id")

    assert state["session_id"] == "caller-supplied-id"


def test_prompt_and_delivery_metadata_must_agree():
    prompt_result = _prompt_result()
    delivery_payload = build_delivery_payload(prompt_result, DELIVERY_SURFACE_CLI)
    delivery_payload["metadata"]["profile_tier"] = "strong"

    _assert_value_error(
        lambda: create_session_state(
            session_id="session-1",
            task="Fix auth",
            prompt_result=prompt_result,
            delivery_payload=delivery_payload,
        )
    )


def test_full_prompt_text_is_not_stored():
    prompt_result = _prompt_result(prompt="Do not store this complete prompt.")
    state = _session(prompt_result=prompt_result)

    assert prompt_result["prompt"] not in json.dumps(state, sort_keys=True)
    assert state["metadata"]["prompt_character_count"] == len(prompt_result["prompt"])


def test_delivery_transitions_prepared_to_delivered():
    state = record_session_delivery(_session())

    assert state["status"] == SESSION_STATUS_DELIVERED
    assert state["turn_count"] == 0


def test_response_transitions_delivered_to_response_received():
    state = _delivered()
    state = record_session_response(state, response_character_count=1800)

    assert state["status"] == SESSION_STATUS_RESPONSE_RECEIVED


def test_first_response_increments_turn_count():
    state = record_session_response(_delivered(), response_character_count=1800)

    assert state["turn_count"] == 1
    assert state["turns"][0]["turn"] == 1
    assert state["turns"][0]["response_character_count"] == 1800


def test_response_text_is_not_stored():
    response_text = "Full response should never be stored."
    state = record_session_response(_delivered(), response_character_count=len(response_text))

    assert response_text not in json.dumps(state, sort_keys=True)


def test_accepted_o4_summary_transitions_to_accepted_for_review():
    state = _response_received()
    state = record_session_validation(state, _accepted_validation())

    assert state["status"] == SESSION_STATUS_ACCEPTED_FOR_REVIEW


def test_retry_recommendation_transitions_to_retry_ready():
    state = record_session_validation(_response_received(), _retry_validation())

    assert state["status"] == SESSION_STATUS_RETRY_READY
    assert state["latest_validation"]["retry_number"] == 1


def test_retry_count_increments_once():
    state = record_session_validation(_response_received(), _retry_validation())

    assert state["retry_count"] == 1


def test_second_response_is_accepted_from_retry_ready():
    state = record_session_validation(_response_received(), _retry_validation())
    state = record_session_response(state, response_character_count=900)

    assert state["status"] == SESSION_STATUS_RESPONSE_RECEIVED
    assert state["turn_count"] == 2


def test_third_response_is_rejected_when_max_retries_is_one():
    state = record_session_validation(_response_received(), _retry_validation())
    state = record_session_response(state, response_character_count=900)
    state = record_session_validation(state, _retry_validation())

    assert state["status"] == SESSION_STATUS_REJECTED
    _assert_value_error(lambda: record_session_response(state, response_character_count=300))


def test_retry_after_limit_exhaustion_becomes_rejected():
    state = _response_received(max_retries=0)
    state = record_session_validation(state, _retry_validation())

    assert state["status"] == SESSION_STATUS_REJECTED
    assert state["retry_count"] == 0


def test_non_retryable_validation_becomes_rejected():
    state = record_session_validation(_response_received(), _rejected_validation())

    assert state["status"] == SESSION_STATUS_REJECTED


def test_validation_summary_omits_patch_text():
    validation = _accepted_validation()
    validation["patch"] = "diff --git a/app.py b/app.py\nsecret patch text"
    state = record_session_validation(_response_received(), validation)

    assert "secret patch text" not in json.dumps(state["latest_validation"], sort_keys=True)


def test_validation_summary_omits_complete_diagnostics():
    validation = _rejected_validation()
    validation["diagnostics"] = [{"message": "Long diagnostic should not be copied."}]
    state = record_session_validation(_response_received(), validation)

    assert "Long diagnostic should not be copied." not in json.dumps(state, sort_keys=True)


def test_latest_turn_stores_validation_status():
    state = record_session_validation(_response_received(), _retry_validation())
    turn = state["turns"][-1]

    assert turn["validation_status"] == "retry_recommended"
    assert turn["failure_types"] == ["out_of_scope_files"]
    assert turn["retry_allowed"] is True


def test_target_paths_are_deterministically_bounded():
    target_files = [f"src/file_{index:02d}.py" for index in range(24, -1, -1)]
    validation = _retry_validation(target_files=target_files)
    state = record_session_validation(_response_received(), validation)

    assert state["latest_validation"]["target_files"] == sorted(target_files)[:20]
    assert state["latest_validation"]["target_file_count"] == 25
    assert state["latest_validation"]["target_files_truncated"] is True


def test_accepted_session_can_be_closed():
    state = record_session_validation(_response_received(), _accepted_validation())
    state = close_session_state(state, reason="review started")

    assert state["status"] == SESSION_STATUS_CLOSED
    assert state["closed_reason"] == "review started"


def test_rejected_session_can_be_closed():
    state = record_session_validation(_response_received(), _rejected_validation())
    state = close_session_state(state, reason="response rejected")

    assert state["status"] == SESSION_STATUS_CLOSED


def test_non_terminal_session_cannot_be_closed():
    _assert_value_error(lambda: close_session_state(_delivered(), reason="too early"))


def test_closed_session_cannot_transition_again():
    state = record_session_validation(_response_received(), _accepted_validation())
    state = close_session_state(state, reason="done")

    _assert_value_error(lambda: record_session_delivery(state))
    _assert_value_error(lambda: record_session_response(state, response_character_count=1))


def test_invalid_transition_raises_value_error():
    _assert_value_error(lambda: record_session_response(_session(), response_character_count=1))


def test_invalid_state_type_raises_value_error():
    _assert_value_error(lambda: record_session_delivery([]))


def test_counter_mismatch_raises_value_error():
    state = _response_received()
    state["turn_count"] = 0

    _assert_value_error(lambda: record_session_validation(state, _accepted_validation()))


def test_negative_response_character_count_raises_value_error():
    _assert_value_error(lambda: record_session_response(_delivered(), response_character_count=-1))


def test_inputs_are_not_mutated():
    state = _response_received()
    validation = _retry_validation()
    before = (copy.deepcopy(state), copy.deepcopy(validation))

    record_session_validation(state, validation)

    assert (state, validation) == before


def test_outputs_are_fresh():
    state = _response_received()
    updated = record_session_validation(state, _retry_validation())

    assert updated is not state
    assert updated["turns"] is not state["turns"]
    assert updated["turns"][0] is not state["turns"][0]


def test_repeated_calls_are_deterministic():
    state = _response_received()
    validation = _retry_validation()

    assert record_session_validation(state, validation) == record_session_validation(state, validation)


def test_output_is_json_ready():
    state = record_session_validation(_response_received(), _accepted_validation())

    assert json.loads(json.dumps(state, allow_nan=False)) == state
    assert _is_json_ready(state)


def test_no_filesystem_or_persistence_access_is_required():
    public_names = {
        name
        for name in vars(session_state)
        if not name.startswith("_")
    }

    for forbidden in ("Path", "open", "os", "subprocess", "sqlite3", "requests", "environ"):
        assert forbidden not in public_names


def test_no_import_from_strata_patch_exists_in_o6_module():
    module_text = json.dumps(sorted(vars(session_state)), sort_keys=True)

    assert "strata.patch" not in module_text
    assert "validate_ai_response" not in module_text


def test_package_layering_invariant_has_no_new_violation():
    assert session_state.__name__ == "strata.core.session_state"
    assert "patch" not in {
        name
        for name in vars(session_state)
        if not name.startswith("_")
    }


def _session(
    *,
    session_id: str = "session-1",
    task: str = "Fix authentication header handling",
    prompt_result: dict[str, object] | None = None,
    max_retries: int = 1,
) -> dict[str, object]:
    prompt_result = prompt_result or _prompt_result()
    delivery_payload = build_delivery_payload(prompt_result, DELIVERY_SURFACE_CLI)
    return create_session_state(
        session_id=session_id,
        task=task,
        prompt_result=prompt_result,
        delivery_payload=delivery_payload,
        max_retries=max_retries,
    )


def _delivered(**kwargs) -> dict[str, object]:
    return record_session_delivery(_session(**kwargs))


def _response_received(**kwargs) -> dict[str, object]:
    return record_session_response(_delivered(**kwargs), response_character_count=1800)


def _prompt_result(prompt: str = "Trusted O3 prompt.\nReturn only a unified diff.\n") -> dict[str, object]:
    return {
        "schema_version": PROMPT_TEMPLATE_SCHEMA_VERSION,
        "template_id": "medium_patch",
        "template_version": PROMPT_TEMPLATE_VERSION,
        "profile_tier": "medium",
        "context_variant": "balanced",
        "prompt": prompt,
        "sections": {
            "role": "Role",
            "task": "Task",
        },
        "metadata": {
            "approved_file_count": 1,
            "relationship_count": 0,
            "omission_count": 0,
            "includes_diff_example": False,
            "needs_explicit_steps": False,
            "static_instruction_character_count": 42,
            "rendered_context_character_count": 101,
            "prompt_character_count": len(prompt),
        },
    }


def _accepted_validation(target_files=None) -> dict[str, object]:
    return {
        "status": "accepted_for_review",
        "is_valid": True,
        "failure_types": [],
        "retry": {
            "allowed": False,
            "reason": "The response is valid for review; no retry is needed.",
        },
        "change_summary": {
            "file_count": 1,
            "added_lines": 1,
            "removed_lines": 1,
            "total_changed_lines": 2,
        },
        "target_files": list(target_files or ["src/app.py"]),
        "patch": "patch text should not be copied",
        "diagnostics": [],
    }


def _retry_validation(target_files=None) -> dict[str, object]:
    return {
        "status": "retry_recommended",
        "is_valid": False,
        "failure_types": ["out_of_scope_files"],
        "retry": {
            "allowed": True,
            "reason": "The response can be corrected with one retry.",
        },
        "change_summary": {
            "file_count": 1,
            "added_lines": 1,
            "removed_lines": 1,
            "total_changed_lines": 2,
        },
        "target_files": list(target_files or ["src/other.py"]),
        "patch": "patch text should not be copied",
        "diagnostics": [{"message": "diagnostic should not be copied"}],
    }


def _rejected_validation() -> dict[str, object]:
    return {
        "status": "rejected",
        "is_valid": False,
        "failure_types": ["unsafe_path"],
        "retry": {
            "allowed": False,
            "reason": "The response includes a non-retryable safety failure.",
        },
        "change_summary": {
            "file_count": 0,
            "added_lines": 0,
            "removed_lines": 0,
            "total_changed_lines": 0,
        },
        "target_files": [],
        "patch": "patch text should not be copied",
        "diagnostics": [{"message": "diagnostic should not be copied"}],
    }


def _assert_value_error(call) -> None:
    try:
        call()
    except ValueError:
        return
    raise AssertionError("Expected ValueError")


def _is_json_ready(value) -> bool:
    if value is None or isinstance(value, (str, int, bool)):
        return True
    if isinstance(value, list):
        return all(_is_json_ready(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _is_json_ready(item) for key, item in value.items())
    return False


TESTS = [
    test_stable_session_status_vocabulary,
    test_session_creation_returns_prepared,
    test_caller_supplied_session_id_is_preserved,
    test_prompt_and_delivery_metadata_must_agree,
    test_full_prompt_text_is_not_stored,
    test_delivery_transitions_prepared_to_delivered,
    test_response_transitions_delivered_to_response_received,
    test_first_response_increments_turn_count,
    test_response_text_is_not_stored,
    test_accepted_o4_summary_transitions_to_accepted_for_review,
    test_retry_recommendation_transitions_to_retry_ready,
    test_retry_count_increments_once,
    test_second_response_is_accepted_from_retry_ready,
    test_third_response_is_rejected_when_max_retries_is_one,
    test_retry_after_limit_exhaustion_becomes_rejected,
    test_non_retryable_validation_becomes_rejected,
    test_validation_summary_omits_patch_text,
    test_validation_summary_omits_complete_diagnostics,
    test_latest_turn_stores_validation_status,
    test_target_paths_are_deterministically_bounded,
    test_accepted_session_can_be_closed,
    test_rejected_session_can_be_closed,
    test_non_terminal_session_cannot_be_closed,
    test_closed_session_cannot_transition_again,
    test_invalid_transition_raises_value_error,
    test_invalid_state_type_raises_value_error,
    test_counter_mismatch_raises_value_error,
    test_negative_response_character_count_raises_value_error,
    test_inputs_are_not_mutated,
    test_outputs_are_fresh,
    test_repeated_calls_are_deterministic,
    test_output_is_json_ready,
    test_no_filesystem_or_persistence_access_is_required,
    test_no_import_from_strata_patch_exists_in_o6_module,
    test_package_layering_invariant_has_no_new_violation,
]
