from collections.abc import Mapping

from strata.core.capability_profiles import CAPABILITY_TIERS
from strata.core.context_rendering import RENDERING_VARIANTS
from strata.core.delivery_surfaces import DELIVERY_SURFACES
from strata.core.prompt_templates import PROMPT_TEMPLATE_IDS, PROMPT_TEMPLATE_VERSION


SESSION_STATE_SCHEMA_VERSION = 1

SESSION_STATUS_PREPARED = "prepared"
SESSION_STATUS_DELIVERED = "delivered"
SESSION_STATUS_RESPONSE_RECEIVED = "response_received"
SESSION_STATUS_RETRY_READY = "retry_ready"
SESSION_STATUS_ACCEPTED_FOR_REVIEW = "accepted_for_review"
SESSION_STATUS_REJECTED = "rejected"
SESSION_STATUS_CLOSED = "closed"
SESSION_STATUSES = (
    SESSION_STATUS_PREPARED,
    SESSION_STATUS_DELIVERED,
    SESSION_STATUS_RESPONSE_RECEIVED,
    SESSION_STATUS_RETRY_READY,
    SESSION_STATUS_ACCEPTED_FOR_REVIEW,
    SESSION_STATUS_REJECTED,
    SESSION_STATUS_CLOSED,
)

VALIDATION_STATUS_ACCEPTED_FOR_REVIEW = "accepted_for_review"
VALIDATION_STATUS_REJECTED = "rejected"
VALIDATION_STATUS_RETRY_RECOMMENDED = "retry_recommended"
VALIDATION_STATUSES = (
    VALIDATION_STATUS_ACCEPTED_FOR_REVIEW,
    VALIDATION_STATUS_REJECTED,
    VALIDATION_STATUS_RETRY_RECOMMENDED,
)

SESSION_STATE_FIELD_ORDER = (
    "schema_version",
    "session_id",
    "status",
    "task",
    "profile_tier",
    "surface",
    "template_id",
    "template_version",
    "context_variant",
    "turn_count",
    "retry_count",
    "max_retries",
    "turns",
    "latest_validation",
    "closed_reason",
    "metadata",
)

TURN_FIELD_ORDER = (
    "turn",
    "response_character_count",
    "validation_status",
    "failure_types",
    "retry_allowed",
)

TARGET_FILE_SUMMARY_LIMIT = 20
FAILURE_TYPE_SUMMARY_LIMIT = 20
SUPPORTED_MAX_RETRIES = (0, 1)

ALLOWED_SESSION_TRANSITIONS = {
    SESSION_STATUS_PREPARED: (SESSION_STATUS_DELIVERED,),
    SESSION_STATUS_DELIVERED: (SESSION_STATUS_RESPONSE_RECEIVED,),
    SESSION_STATUS_RESPONSE_RECEIVED: (
        SESSION_STATUS_RETRY_READY,
        SESSION_STATUS_ACCEPTED_FOR_REVIEW,
        SESSION_STATUS_REJECTED,
    ),
    SESSION_STATUS_RETRY_READY: (SESSION_STATUS_RESPONSE_RECEIVED,),
    SESSION_STATUS_ACCEPTED_FOR_REVIEW: (SESSION_STATUS_CLOSED,),
    SESSION_STATUS_REJECTED: (SESSION_STATUS_CLOSED,),
    SESSION_STATUS_CLOSED: (),
}


def _validate_state(state) -> dict[str, object]:
    if not isinstance(state, Mapping):
        raise ValueError("state must be a mapping.")
    for field in SESSION_STATE_FIELD_ORDER:
        if field not in state:
            raise ValueError(f"state is missing required field: {field}")

    if state["schema_version"] != SESSION_STATE_SCHEMA_VERSION:
        raise ValueError("state schema_version is unsupported.")
    _validate_nonempty_string(state["session_id"], "session_id")
    _validate_nonempty_string(state["task"], "task")
    _validate_choice(state["status"], "status", SESSION_STATUSES)
    _validate_choice(state["profile_tier"], "profile_tier", CAPABILITY_TIERS)
    _validate_choice(state["surface"], "surface", DELIVERY_SURFACES)
    _validate_choice(state["template_id"], "template_id", PROMPT_TEMPLATE_IDS)
    if state["template_version"] != PROMPT_TEMPLATE_VERSION:
        raise ValueError("state template_version is unsupported.")
    _validate_choice(state["context_variant"], "context_variant", RENDERING_VARIANTS)

    turn_count = _validate_nonnegative_int(state["turn_count"], "turn_count")
    retry_count = _validate_nonnegative_int(state["retry_count"], "retry_count")
    max_retries = _validate_max_retries(state["max_retries"])
    if retry_count > max_retries:
        raise ValueError("retry_count cannot exceed max_retries.")

    turns = _validate_turns(state["turns"])
    if turn_count != len(turns):
        raise ValueError("turn_count must match turns length.")
    if len(turns) > 1 + max_retries:
        raise ValueError("turns exceed the configured retry limit.")

    if state["latest_validation"] is not None and not isinstance(state["latest_validation"], Mapping):
        raise ValueError("latest_validation must be a mapping or null.")
    if state["closed_reason"] is not None and not isinstance(state["closed_reason"], str):
        raise ValueError("closed_reason must be a string or null.")
    if state["status"] == SESSION_STATUS_CLOSED and not _is_nonempty_string(state["closed_reason"]):
        raise ValueError("closed sessions must include a closed_reason.")
    if not isinstance(state["metadata"], Mapping):
        raise ValueError("metadata must be a mapping.")

    copied = _copy_json_mapping(state, "state")
    _validate_json_ready(copied)
    return copied


def _validate_prompt_result(prompt_result) -> Mapping:
    if not isinstance(prompt_result, Mapping):
        raise ValueError("prompt_result must be a mapping.")
    for field in (
        "template_id",
        "template_version",
        "profile_tier",
        "context_variant",
        "prompt",
        "metadata",
    ):
        if field not in prompt_result:
            raise ValueError(f"prompt_result is missing required field: {field}")
    _validate_choice(prompt_result["template_id"], "template_id", PROMPT_TEMPLATE_IDS)
    if prompt_result["template_version"] != PROMPT_TEMPLATE_VERSION:
        raise ValueError("prompt_result template_version is unsupported.")
    _validate_choice(prompt_result["profile_tier"], "profile_tier", CAPABILITY_TIERS)
    _validate_choice(prompt_result["context_variant"], "context_variant", RENDERING_VARIANTS)
    _validate_nonempty_string(prompt_result["prompt"], "prompt_result prompt")
    if not isinstance(prompt_result["metadata"], Mapping):
        raise ValueError("prompt_result metadata must be a mapping.")
    _validate_prompt_character_count(prompt_result["metadata"], prompt_result["prompt"])
    return prompt_result


def _validate_delivery_payload(delivery_payload) -> Mapping:
    if not isinstance(delivery_payload, Mapping):
        raise ValueError("delivery_payload must be a mapping.")
    for field in ("surface", "prompt", "metadata"):
        if field not in delivery_payload:
            raise ValueError(f"delivery_payload is missing required field: {field}")
    _validate_choice(delivery_payload["surface"], "surface", DELIVERY_SURFACES)
    _validate_nonempty_string(delivery_payload["prompt"], "delivery_payload prompt")
    if not isinstance(delivery_payload["metadata"], Mapping):
        raise ValueError("delivery_payload metadata must be a mapping.")
    if "manual_transfer_required" not in delivery_payload["metadata"]:
        raise ValueError("delivery_payload metadata is missing required field: manual_transfer_required")
    _validate_bool(
        delivery_payload["metadata"]["manual_transfer_required"],
        "manual_transfer_required",
    )
    return delivery_payload


def _validate_prompt_delivery_agreement(prompt_result: Mapping, delivery_payload: Mapping) -> None:
    metadata = delivery_payload["metadata"]
    for field in ("template_id", "template_version", "profile_tier", "context_variant"):
        if prompt_result[field] != metadata.get(field):
            raise ValueError(f"prompt_result and delivery_payload disagree on {field}.")
    if prompt_result["prompt"] != delivery_payload["prompt"]:
        raise ValueError("prompt_result and delivery_payload disagree on prompt.")
    _validate_prompt_character_count(metadata, prompt_result["prompt"])


def _validate_validation_result(validation_result) -> Mapping:
    if not isinstance(validation_result, Mapping):
        raise ValueError("validation_result must be a mapping.")
    for field in (
        "status",
        "is_valid",
        "failure_types",
        "retry",
        "change_summary",
        "target_files",
    ):
        if field not in validation_result:
            raise ValueError(f"validation_result is missing required field: {field}")
    status = _validate_choice(validation_result["status"], "validation status", VALIDATION_STATUSES)
    is_valid = _validate_bool(validation_result["is_valid"], "is_valid")
    if status == VALIDATION_STATUS_ACCEPTED_FOR_REVIEW and not is_valid:
        raise ValueError("accepted validation results must be valid.")
    if status == VALIDATION_STATUS_REJECTED and is_valid:
        raise ValueError("rejected validation results cannot be valid.")
    _validate_string_list(validation_result["failure_types"], "failure_types")
    retry = validation_result["retry"]
    if not isinstance(retry, Mapping):
        raise ValueError("validation_result retry must be a mapping.")
    if "allowed" not in retry:
        raise ValueError("validation_result retry is missing required field: allowed")
    _validate_bool(retry["allowed"], "retry.allowed")
    if "reason" in retry and retry["reason"] is not None and not isinstance(retry["reason"], str):
        raise ValueError("retry.reason must be a string or null.")
    if not isinstance(validation_result["change_summary"], Mapping):
        raise ValueError("validation_result change_summary must be a mapping.")
    _validate_string_list(validation_result["target_files"], "target_files")
    return validation_result


def _validate_turns(turns) -> list[dict[str, object]]:
    if not isinstance(turns, list):
        raise ValueError("turns must be a list.")
    copied = []
    for index, turn in enumerate(turns):
        if not isinstance(turn, Mapping):
            raise ValueError(f"turns[{index}] must be a mapping.")
        for field in TURN_FIELD_ORDER:
            if field not in turn:
                raise ValueError(f"turns[{index}] is missing required field: {field}")
        turn_number = _validate_positive_int(turn["turn"], f"turns[{index}].turn")
        if turn_number != index + 1:
            raise ValueError("turn records must be sequential.")
        _validate_nonnegative_int(
            turn["response_character_count"],
            f"turns[{index}].response_character_count",
        )
        if turn["validation_status"] is not None:
            _validate_choice(turn["validation_status"], "validation_status", VALIDATION_STATUSES)
        _validate_string_list(turn["failure_types"], f"turns[{index}].failure_types")
        if turn["retry_allowed"] is not None:
            _validate_bool(turn["retry_allowed"], f"turns[{index}].retry_allowed")
        copied.append(_copy_json_mapping(turn, f"turns[{index}]"))
    return copied


def _validate_nonempty_string(value, field_name: str) -> str:
    if not _is_nonempty_string(value):
        raise ValueError(f"{field_name} must be a non-empty string.")
    return value


def _is_nonempty_string(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_choice(value, field_name: str, choices: tuple[str, ...]) -> str:
    text = _validate_nonempty_string(value, field_name)
    if text not in choices:
        raise ValueError(f"{field_name} must be one of: {', '.join(choices)}.")
    return text


def _validate_bool(value, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be a boolean.")
    return value


def _validate_nonnegative_int(value, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be a non-negative integer.")
    if value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer.")
    return value


def _validate_positive_int(value, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be a positive integer.")
    if value <= 0:
        raise ValueError(f"{field_name} must be a positive integer.")
    return value


def _validate_max_retries(value) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("max_retries must be 0 or 1.")
    if value not in SUPPORTED_MAX_RETRIES:
        raise ValueError("max_retries must be 0 or 1.")
    return value


def _validate_prompt_character_count(metadata: Mapping, prompt: str) -> int:
    count = metadata.get("prompt_character_count")
    if isinstance(count, bool) or not isinstance(count, int):
        raise ValueError("prompt_character_count must be an integer.")
    if count != len(prompt):
        raise ValueError("prompt_character_count must match the prompt.")
    return count


def _validate_string_list(values, field_name: str) -> list[str]:
    if not isinstance(values, list):
        raise ValueError(f"{field_name} must be a list.")
    copied = []
    for index, value in enumerate(values):
        if not isinstance(value, str):
            raise ValueError(f"{field_name}[{index}] must be a string.")
        copied.append(value)
    return copied


def create_session_state(
    *,
    session_id,
    task,
    prompt_result,
    delivery_payload,
    max_retries=1,
) -> dict[str, object]:
    session_id = _validate_nonempty_string(session_id, "session_id")
    task = _validate_nonempty_string(task, "task")
    prompt_result = _validate_prompt_result(prompt_result)
    delivery_payload = _validate_delivery_payload(delivery_payload)
    _validate_prompt_delivery_agreement(prompt_result, delivery_payload)
    max_retries = _validate_max_retries(max_retries)

    metadata = delivery_payload["metadata"]
    state = {
        "schema_version": SESSION_STATE_SCHEMA_VERSION,
        "session_id": session_id,
        "status": SESSION_STATUS_PREPARED,
        "task": task,
        "profile_tier": prompt_result["profile_tier"],
        "surface": delivery_payload["surface"],
        "template_id": prompt_result["template_id"],
        "template_version": prompt_result["template_version"],
        "context_variant": prompt_result["context_variant"],
        "turn_count": 0,
        "retry_count": 0,
        "max_retries": max_retries,
        "turns": [],
        "latest_validation": None,
        "closed_reason": None,
        "metadata": {
            "prompt_character_count": metadata["prompt_character_count"],
            "manual_transfer_required": metadata["manual_transfer_required"],
        },
    }
    _validate_json_ready(state)
    return state


def record_session_delivery(state) -> dict[str, object]:
    state = _validate_state(state)
    _ensure_transition(state["status"], SESSION_STATUS_DELIVERED)
    updated = _copy_state_with(state, status=SESSION_STATUS_DELIVERED)
    _validate_json_ready(updated)
    return updated


def record_session_response(
    state,
    *,
    response_character_count,
) -> dict[str, object]:
    state = _validate_state(state)
    response_character_count = _validate_nonnegative_int(
        response_character_count,
        "response_character_count",
    )
    _ensure_transition(state["status"], SESSION_STATUS_RESPONSE_RECEIVED)
    if state["turn_count"] >= 1 + state["max_retries"]:
        raise ValueError("session has reached the maximum response turn count.")

    turns = _copy_json_value(state["turns"])
    turns.append(
        {
            "turn": len(turns) + 1,
            "response_character_count": response_character_count,
            "validation_status": None,
            "failure_types": [],
            "retry_allowed": None,
        }
    )
    updated = _copy_state_with(
        state,
        status=SESSION_STATUS_RESPONSE_RECEIVED,
        turn_count=len(turns),
        turns=turns,
        latest_validation=None,
    )
    _validate_json_ready(updated)
    return updated


def record_session_validation(
    state,
    validation_result,
) -> dict[str, object]:
    state = _validate_state(state)
    validation_result = _validate_validation_result(validation_result)
    if state["status"] != SESSION_STATUS_RESPONSE_RECEIVED:
        raise ValueError("validation can only be recorded after a response is received.")
    if not state["turns"]:
        raise ValueError("validation requires at least one response turn.")

    failure_types = _bounded_string_list(
        validation_result["failure_types"],
        FAILURE_TYPE_SUMMARY_LIMIT,
    )
    retry_allowed = bool(validation_result["retry"]["allowed"])
    next_status, retry_count = _status_after_validation(
        state,
        validation_result["status"],
        retry_allowed,
    )
    summary = _validation_summary(
        validation_result,
        failure_types,
        retry_allowed,
        retry_count if next_status == SESSION_STATUS_RETRY_READY else None,
    )
    turns = _copy_json_value(state["turns"])
    turns[-1] = dict(turns[-1])
    turns[-1]["validation_status"] = validation_result["status"]
    turns[-1]["failure_types"] = list(failure_types)
    turns[-1]["retry_allowed"] = retry_allowed

    _ensure_transition(state["status"], next_status)
    updated = _copy_state_with(
        state,
        status=next_status,
        retry_count=retry_count,
        turns=turns,
        latest_validation=summary,
    )
    _validate_json_ready(updated)
    return updated


def close_session_state(
    state,
    *,
    reason,
) -> dict[str, object]:
    state = _validate_state(state)
    reason = _validate_nonempty_string(reason, "reason")
    _ensure_transition(state["status"], SESSION_STATUS_CLOSED)
    updated = _copy_state_with(
        state,
        status=SESSION_STATUS_CLOSED,
        closed_reason=reason,
    )
    _validate_json_ready(updated)
    return updated


def _ensure_transition(current_status: str, next_status: str) -> None:
    if next_status not in ALLOWED_SESSION_TRANSITIONS.get(current_status, ()):
        raise ValueError(f"Invalid session transition: {current_status} -> {next_status}.")


def _status_after_validation(
    state: Mapping,
    validation_status: str,
    retry_allowed: bool,
) -> tuple[str, int]:
    retry_count = state["retry_count"]
    if validation_status == VALIDATION_STATUS_ACCEPTED_FOR_REVIEW:
        return SESSION_STATUS_ACCEPTED_FOR_REVIEW, retry_count
    if validation_status == VALIDATION_STATUS_RETRY_RECOMMENDED and retry_allowed:
        if retry_count < state["max_retries"]:
            return SESSION_STATUS_RETRY_READY, retry_count + 1
        return SESSION_STATUS_REJECTED, retry_count
    return SESSION_STATUS_REJECTED, retry_count


def _validation_summary(
    validation_result: Mapping,
    failure_types: list[str],
    retry_allowed: bool,
    retry_number: int | None,
) -> dict[str, object]:
    target_files = _bounded_string_list(
        validation_result["target_files"],
        TARGET_FILE_SUMMARY_LIMIT,
    )
    summary = {
        "status": validation_result["status"],
        "is_valid": validation_result["is_valid"],
        "failure_types": failure_types,
        "retry_allowed": retry_allowed,
        "retry_reason": validation_result["retry"].get("reason"),
        "retry_number": retry_number,
        "change_summary": _copy_change_summary(validation_result["change_summary"]),
        "target_files": target_files,
        "target_file_count": len(validation_result["target_files"]),
        "target_files_truncated": len(validation_result["target_files"]) > TARGET_FILE_SUMMARY_LIMIT,
    }
    return summary


def _copy_change_summary(change_summary: Mapping) -> dict[str, int]:
    copied = {}
    for key in sorted(change_summary.keys()):
        value = change_summary[key]
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("change_summary values must be integers.")
        copied[str(key)] = value
    return copied


def _bounded_string_list(values: list[str], limit: int) -> list[str]:
    return sorted(str(value) for value in values)[:limit]


def _copy_state_with(state: Mapping, **updates) -> dict[str, object]:
    copied = _copy_json_mapping(state, "state")
    for key, value in updates.items():
        copied[key] = _copy_json_value(value)
    return copied


def _copy_json_mapping(mapping, field_name: str) -> dict[str, object]:
    if not isinstance(mapping, Mapping):
        raise ValueError(f"{field_name} must be a mapping.")
    copied = {}
    for key in mapping:
        if not isinstance(key, str):
            raise ValueError(f"{field_name} keys must be strings.")
    for key in mapping:
        copied[key] = _copy_json_value(mapping[key])
    return copied


def _validate_json_ready(value) -> None:
    if _copy_json_value(value) is _UNSUPPORTED:
        raise ValueError("session state must be JSON-ready.")


_UNSUPPORTED = object()


def _copy_json_value(value):
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, list):
        copied = []
        for item in value:
            rendered = _copy_json_value(item)
            if rendered is _UNSUPPORTED:
                return _UNSUPPORTED
            copied.append(rendered)
        return copied
    if isinstance(value, Mapping):
        copied = {}
        for key in value:
            if not isinstance(key, str):
                return _UNSUPPORTED
            rendered = _copy_json_value(value[key])
            if rendered is _UNSUPPORTED:
                return _UNSUPPORTED
            copied[key] = rendered
        return copied
    return _UNSUPPORTED
