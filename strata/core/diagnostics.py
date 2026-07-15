from collections.abc import Mapping


DIAGNOSTIC_SEVERITY_INFO = "info"
DIAGNOSTIC_SEVERITY_WARNING = "warning"
DIAGNOSTIC_SEVERITY_ERROR = "error"
DIAGNOSTIC_SEVERITIES = (
    DIAGNOSTIC_SEVERITY_INFO,
    DIAGNOSTIC_SEVERITY_WARNING,
    DIAGNOSTIC_SEVERITY_ERROR,
)

DIAGNOSTIC_SOURCE_WORKFLOW_STATE = "workflow_state"
DIAGNOSTIC_SOURCE_CONTEXT = "context"
DIAGNOSTIC_SOURCE_REVIEW = "review"
DIAGNOSTIC_SOURCE_APPLY = "apply"
DIAGNOSTIC_SOURCE_VERIFY = "verify"
DIAGNOSTIC_SOURCE_GATE = "gate"
DIAGNOSTIC_SOURCE_SYSTEM = "system"
DIAGNOSTIC_SOURCES = (
    DIAGNOSTIC_SOURCE_WORKFLOW_STATE,
    DIAGNOSTIC_SOURCE_CONTEXT,
    DIAGNOSTIC_SOURCE_REVIEW,
    DIAGNOSTIC_SOURCE_APPLY,
    DIAGNOSTIC_SOURCE_VERIFY,
    DIAGNOSTIC_SOURCE_GATE,
    DIAGNOSTIC_SOURCE_SYSTEM,
)

DIAGNOSTIC_EVENT_FIELD_ORDER = (
    "code",
    "severity",
    "message",
    "source",
    "field",
    "path",
    "next_action",
    "details",
)

_SEVERITY_ORDER = {
    DIAGNOSTIC_SEVERITY_ERROR: 0,
    DIAGNOSTIC_SEVERITY_WARNING: 1,
    DIAGNOSTIC_SEVERITY_INFO: 2,
}


def build_diagnostic_event(
    code,
    severity,
    message,
    *,
    source,
    field=None,
    path=None,
    next_action=None,
    details=None,
) -> dict[str, object]:
    """Build one deterministic JSON-ready diagnostic event."""

    return {
        "code": _validate_nonempty_string(code, "code"),
        "severity": _validate_choice(severity, "severity", DIAGNOSTIC_SEVERITIES),
        "message": _validate_nonempty_string(message, "message"),
        "source": _validate_choice(source, "source", DIAGNOSTIC_SOURCES),
        "field": _validate_optional_string(field, "field"),
        "path": _validate_optional_string(path, "path"),
        "next_action": _validate_optional_string(next_action, "next_action"),
        "details": _copy_details(details),
    }


def normalize_diagnostic_event(
    event,
    *,
    default_source=None,
) -> dict[str, object]:
    """Return a canonical M2 event from a canonical or M1-style diagnostic mapping."""

    if not isinstance(event, Mapping):
        raise ValueError("diagnostic event must be a mapping.")

    source = event.get("source", default_source)
    details = _copy_details(event.get("details"))
    if "value" in event:
        details["value"] = _copy_json_ready(event.get("value"), "value")

    return build_diagnostic_event(
        event.get("code"),
        event.get("severity"),
        event.get("message"),
        source=source,
        field=event.get("field"),
        path=event.get("path"),
        next_action=event.get("next_action"),
        details=details,
    )


def sort_diagnostic_events(events) -> list[dict[str, object]]:
    """Return canonical diagnostic events in deterministic order."""

    normalized = _normalize_event_list(events)
    return sorted(normalized, key=_event_sort_key)


def deduplicate_diagnostic_events(events) -> list[dict[str, object]]:
    """Return exact unique diagnostic events in deterministic order."""

    deduplicated = []
    seen = set()
    for event in sort_diagnostic_events(events):
        key = _event_identity_key(event)
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(event)
    return deduplicated


def summarize_diagnostic_events(events) -> dict[str, object]:
    """Return compact deterministic diagnostic counts."""

    normalized = _normalize_event_list(events)
    errors = _severity_count(normalized, DIAGNOSTIC_SEVERITY_ERROR)
    warnings = _severity_count(normalized, DIAGNOSTIC_SEVERITY_WARNING)
    info = _severity_count(normalized, DIAGNOSTIC_SEVERITY_INFO)

    return {
        "total": len(normalized),
        "errors": errors,
        "warnings": warnings,
        "info": info,
        "has_errors": errors > 0,
        "has_warnings": warnings > 0,
    }


def _normalize_event_list(events) -> list[dict[str, object]]:
    if not isinstance(events, (list, tuple)):
        raise ValueError("diagnostic events must be a list or tuple.")
    return [normalize_diagnostic_event(event) for event in events]


def _event_sort_key(event: Mapping) -> tuple[object, ...]:
    return (
        _SEVERITY_ORDER[event["severity"]],
        event["source"],
        event["code"],
        _none_to_empty(event["path"]),
        _none_to_empty(event["field"]),
        event["message"],
        _none_to_empty(event["next_action"]),
        _json_sort_key(event["details"]),
    )


def _event_identity_key(event: Mapping) -> tuple[object, ...]:
    return tuple(
        _json_sort_key(event[field])
        for field in DIAGNOSTIC_EVENT_FIELD_ORDER
    )


def _severity_count(events: list[dict[str, object]], severity: str) -> int:
    return sum(1 for event in events if event["severity"] == severity)


def _validate_nonempty_string(value, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string.")
    return value


def _validate_optional_string(value, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string or null.")
    return value


def _validate_choice(value, field_name: str, choices: tuple[str, ...]) -> str:
    text = _validate_nonempty_string(value, field_name)
    if text not in choices:
        raise ValueError(f"{field_name} must be one of: {', '.join(choices)}.")
    return text


def _copy_details(details) -> dict[str, object]:
    if details is None:
        return {}
    if not isinstance(details, Mapping):
        raise ValueError("details must be a mapping or null.")
    return _copy_mapping(details, "details")


def _copy_mapping(mapping, field_name: str) -> dict[str, object]:
    keys = list(mapping.keys())
    for key in keys:
        if not isinstance(key, str):
            raise ValueError(f"{field_name} keys must be strings.")

    copied = {}
    for key in sorted(keys):
        copied[key] = _copy_json_ready(mapping[key], f"{field_name}.{key}")
    return copied


def _copy_json_ready(value, field_name: str):
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, list):
        return [
            _copy_json_ready(item, f"{field_name}[{index}]")
            for index, item in enumerate(value)
        ]
    if isinstance(value, Mapping):
        return _copy_mapping(value, field_name)
    raise ValueError(f"{field_name} must be JSON-ready.")


def _json_sort_key(value) -> tuple[object, ...]:
    if value is None:
        return ("none",)
    if isinstance(value, bool):
        return ("bool", value)
    if isinstance(value, int):
        return ("int", value)
    if isinstance(value, str):
        return ("str", value)
    if isinstance(value, list):
        return ("list", tuple(_json_sort_key(item) for item in value))
    if isinstance(value, Mapping):
        return (
            "dict",
            tuple(
                (key, _json_sort_key(value[key]))
                for key in sorted(value)
            ),
        )
    raise ValueError("diagnostic event contains a non-JSON-ready value.")


def _none_to_empty(value) -> str:
    if value is None:
        return ""
    return str(value)
