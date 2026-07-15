from collections.abc import Mapping

from strata.core.diagnostics import (
    DIAGNOSTIC_SEVERITY_ERROR,
    DIAGNOSTIC_SOURCE_REVIEW,
    build_diagnostic_event,
    sort_diagnostic_events,
)
from strata.patch.validator import extract_patch_targets, validate_patch_text


AI_RESPONSE_STATUS_ACCEPTED_FOR_REVIEW = "accepted_for_review"
AI_RESPONSE_STATUS_REJECTED = "rejected"
AI_RESPONSE_STATUS_RETRY_RECOMMENDED = "retry_recommended"
AI_RESPONSE_STATUSES = (
    AI_RESPONSE_STATUS_ACCEPTED_FOR_REVIEW,
    AI_RESPONSE_STATUS_REJECTED,
    AI_RESPONSE_STATUS_RETRY_RECOMMENDED,
)

FAILURE_EMPTY_RESPONSE = "empty_response"
FAILURE_NO_DIFF = "no_diff"
FAILURE_MALFORMED_DIFF = "malformed_diff"
FAILURE_OUT_OF_SCOPE_FILES = "out_of_scope_files"
FAILURE_BLOCKED_NEW_FILES = "blocked_new_files"
FAILURE_UNSAFE_PATH = "unsafe_path"
FAILURE_EXCESSIVE_CHANGES = "excessive_changes"
FAILURE_INJECTION_DETECTED = "injection_detected"
AI_RESPONSE_FAILURE_TYPES = (
    FAILURE_EMPTY_RESPONSE,
    FAILURE_NO_DIFF,
    FAILURE_MALFORMED_DIFF,
    FAILURE_OUT_OF_SCOPE_FILES,
    FAILURE_BLOCKED_NEW_FILES,
    FAILURE_UNSAFE_PATH,
    FAILURE_EXCESSIVE_CHANGES,
    FAILURE_INJECTION_DETECTED,
)

AI_RESPONSE_RESULT_FIELD_ORDER = (
    "status",
    "is_valid",
    "failure_types",
    "diagnostics",
    "patch",
    "target_files",
    "change_summary",
    "retry",
    "metadata",
)

RETRYABLE_FAILURES = (
    FAILURE_NO_DIFF,
    FAILURE_MALFORMED_DIFF,
    FAILURE_OUT_OF_SCOPE_FILES,
    FAILURE_BLOCKED_NEW_FILES,
    FAILURE_EXCESSIVE_CHANGES,
)
NON_RETRYABLE_FAILURES = (
    FAILURE_EMPTY_RESPONSE,
    FAILURE_UNSAFE_PATH,
    FAILURE_INJECTION_DETECTED,
)

SUSPICIOUS_RESPONSE_PHRASES = (
    "ignore previous instructions",
    "ignore the approved scope",
    "disable validation",
    "bypass review",
    "force apply",
    "do not run tests",
    "reveal system prompt",
)

DEFAULT_MAX_FILES_CHANGED = 20
DEFAULT_MAX_TOTAL_CHANGED_LINES = 800


def validate_ai_response(
    response_text,
    *,
    allowed_files,
    expected_related_files=None,
    allowed_new_files=None,
    max_files_changed=DEFAULT_MAX_FILES_CHANGED,
    max_total_changed_lines=DEFAULT_MAX_TOTAL_CHANGED_LINES,
) -> dict[str, object]:
    if not isinstance(response_text, str):
        raise ValueError("response_text must be a string.")

    allowed = _validate_path_collection(allowed_files, "allowed_files")
    related = _validate_path_collection(
        expected_related_files or (),
        "expected_related_files",
    )
    allowed_new = _validate_path_collection(allowed_new_files or (), "allowed_new_files")
    max_files = _validate_positive_int(max_files_changed, "max_files_changed")
    max_changed_lines = _validate_positive_int(
        max_total_changed_lines,
        "max_total_changed_lines",
    )

    failures: list[str] = []
    details_by_failure: dict[str, dict[str, object]] = {}
    response = response_text.strip()
    injection_detected = _detect_injection(response_text)

    if not response:
        _add_failure(
            failures,
            details_by_failure,
            FAILURE_EMPTY_RESPONSE,
            {"response_character_count": len(response_text)},
        )

    if injection_detected:
        _add_failure(
            failures,
            details_by_failure,
            FAILURE_INJECTION_DETECTED,
            {"matched_phrases": injection_detected},
        )

    patch = None
    target_files: list[str] = []
    change_summary = _empty_change_summary()

    if response:
        patch_validation = validate_patch_text(response_text)
        if not _contains_unified_diff(response_text):
            _add_failure(failures, details_by_failure, FAILURE_NO_DIFF, {})
        elif patch_validation.get("status") == "valid":
            patch = response_text.strip() + "\n"
            target_files = sorted(extract_patch_targets(response_text))
            change_summary = _summarize_changes(response_text, target_files)
            _validate_scope(
                response_text,
                target_files,
                allowed,
                related,
                allowed_new,
                failures,
                details_by_failure,
            )
            _validate_change_limits(
                change_summary,
                max_files,
                max_changed_lines,
                failures,
                details_by_failure,
            )
        else:
            failure = _failure_from_patch_validation(patch_validation)
            _add_failure(
                failures,
                details_by_failure,
                failure,
                _patch_validation_details(patch_validation),
            )

    failure_types = _ordered_failures(failures)
    diagnostics = sort_diagnostic_events(
        [
            _diagnostic_for_failure(failure, details_by_failure.get(failure, {}))
            for failure in failure_types
        ]
    )
    retry = _retry_recommendation(failure_types)
    status = _status_for_failures(failure_types, retry["allowed"])
    is_valid = status == AI_RESPONSE_STATUS_ACCEPTED_FOR_REVIEW
    if not is_valid:
        patch = None

    result = {
        "status": status,
        "is_valid": is_valid,
        "failure_types": failure_types,
        "diagnostics": diagnostics,
        "patch": patch,
        "target_files": target_files if is_valid else sorted(target_files),
        "change_summary": change_summary,
        "retry": retry,
        "metadata": {
            "response_character_count": len(response_text),
            "diff_character_count": len(patch or ""),
            "approved_scope_count": len(allowed),
            "expected_related_count": len(related),
            "allowed_new_file_count": len(allowed_new),
            "failure_count": len(failure_types),
        },
    }
    _validate_json_ready(result)
    return result


def _validate_path_collection(values, field_name: str) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, (str, bytes)) or not isinstance(values, (list, tuple, set, frozenset)):
        raise ValueError(f"{field_name} must be a collection of repository-relative strings.")

    normalized: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field_name} must contain only non-empty strings.")
        path = value.replace("\\", "/").strip()
        if _is_unsafe_path_text(path):
            raise ValueError(f"{field_name} must contain repository-relative paths.")
        normalized.append(path)
    return tuple(sorted(set(normalized)))


def _validate_positive_int(value, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be a positive integer.")
    if value <= 0:
        raise ValueError(f"{field_name} must be a positive integer.")
    return value


def _is_unsafe_path_text(path: str) -> bool:
    text = path.replace("\\", "/")
    parts = [part for part in text.split("/") if part]
    return (
        not text
        or text.startswith("/")
        or (len(text) >= 2 and text[1] == ":")
        or ".." in parts
    )


def _contains_unified_diff(text: str) -> bool:
    lines = text.splitlines()
    return any(line.startswith("diff --git ") for line in lines) or (
        any(line.startswith("--- ") for line in lines)
        and any(line.startswith("+++ ") for line in lines)
    )


def _failure_from_patch_validation(validation: Mapping) -> str:
    text = " ".join(str(item) for item in validation.get("errors", []) or [])
    lowered = text.lower()
    if (
        "unsafe patch path" in lowered
        or "dangerous" in lowered
        or "forbidden" in lowered
        or "absolute" in lowered
    ):
        return FAILURE_UNSAFE_PATH
    return FAILURE_MALFORMED_DIFF


def _patch_validation_details(validation: Mapping) -> dict[str, object]:
    errors = [
        str(error)
        for error in validation.get("errors", []) or []
    ][:3]
    return {
        "patch_status": str(validation.get("status") or ""),
        "errors": errors,
    }


def _validate_scope(
    patch_text: str,
    target_files: list[str],
    allowed: tuple[str, ...],
    related: tuple[str, ...],
    allowed_new: tuple[str, ...],
    failures: list[str],
    details_by_failure: dict[str, dict[str, object]],
) -> None:
    approved_existing = set(allowed) | set(related)
    create_targets = set(_extract_created_targets(patch_text))
    out_of_scope = sorted(
        target for target in target_files
        if target not in create_targets and target not in approved_existing
    )
    blocked_new = sorted(
        target for target in create_targets
        if target not in set(allowed_new)
    )

    if out_of_scope:
        _add_failure(
            failures,
            details_by_failure,
            FAILURE_OUT_OF_SCOPE_FILES,
            {"target_files": out_of_scope[:20], "target_count": len(out_of_scope)},
        )
    if blocked_new:
        _add_failure(
            failures,
            details_by_failure,
            FAILURE_BLOCKED_NEW_FILES,
            {"target_files": blocked_new[:20], "target_count": len(blocked_new)},
        )


def _extract_created_targets(patch_text: str) -> tuple[str, ...]:
    created: list[str] = []
    current_old = None
    current_new = None
    new_file_mode = False

    for line in patch_text.splitlines():
        if line.startswith("diff --git "):
            _append_created_target(created, current_old, current_new, new_file_mode)
            current_old = None
            current_new = None
            new_file_mode = False
            parts = line.split()
            if len(parts) >= 4:
                current_old = _normalize_patch_path(parts[2])
                current_new = _normalize_patch_path(parts[3])
            continue
        if line.startswith("new file mode "):
            new_file_mode = True
            continue
        if line.startswith("--- "):
            current_old = _normalize_patch_path(line[4:])
            continue
        if line.startswith("+++ "):
            current_new = _normalize_patch_path(line[4:])

    _append_created_target(created, current_old, current_new, new_file_mode)
    return tuple(sorted(set(target for target in created if target)))


def _append_created_target(
    created: list[str],
    old_path: str | None,
    new_path: str | None,
    new_file_mode: bool,
) -> None:
    if new_path is None or new_path == "/dev/null":
        return
    if old_path == "/dev/null" or new_file_mode:
        created.append(new_path)


def _normalize_patch_path(path: str | None) -> str | None:
    if path is None:
        return None
    text = path.split("\t", 1)[0].strip().replace("\\", "/")
    if text.startswith("a/") or text.startswith("b/"):
        text = text[2:]
    if text == "/dev/null" or not text:
        return text or None
    while "//" in text:
        text = text.replace("//", "/")
    return text


def _validate_change_limits(
    summary: Mapping,
    max_files_changed: int,
    max_total_changed_lines: int,
    failures: list[str],
    details_by_failure: dict[str, dict[str, object]],
) -> None:
    if (
        summary["file_count"] > max_files_changed
        or summary["total_changed_lines"] > max_total_changed_lines
    ):
        _add_failure(
            failures,
            details_by_failure,
            FAILURE_EXCESSIVE_CHANGES,
            {
                "file_count": summary["file_count"],
                "total_changed_lines": summary["total_changed_lines"],
                "max_files_changed": max_files_changed,
                "max_total_changed_lines": max_total_changed_lines,
            },
        )


def _summarize_changes(patch_text: str, target_files: list[str]) -> dict[str, int]:
    added = 0
    removed = 0
    for line in patch_text.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            removed += 1
    return {
        "file_count": len(target_files),
        "added_lines": added,
        "removed_lines": removed,
        "total_changed_lines": added + removed,
    }


def _empty_change_summary() -> dict[str, int]:
    return {
        "file_count": 0,
        "added_lines": 0,
        "removed_lines": 0,
        "total_changed_lines": 0,
    }


def _detect_injection(response_text: str) -> list[str]:
    prose = "\n".join(
        line for line in response_text.splitlines()
        if not _is_diff_line(line)
    ).lower()
    return [
        phrase
        for phrase in SUSPICIOUS_RESPONSE_PHRASES
        if phrase in prose
    ]


def _is_diff_line(line: str) -> bool:
    return line.startswith((
        "diff --git ",
        "--- ",
        "+++ ",
        "@@",
        "+",
        "-",
        "index ",
        "new file mode ",
        "deleted file mode ",
    ))


def _add_failure(
    failures: list[str],
    details_by_failure: dict[str, dict[str, object]],
    failure: str,
    details: dict[str, object],
) -> None:
    if failure not in AI_RESPONSE_FAILURE_TYPES:
        raise ValueError(f"Unsupported failure type: {failure}")
    if failure not in failures:
        failures.append(failure)
        details_by_failure[failure] = dict(details)


def _ordered_failures(failures: list[str]) -> list[str]:
    seen = set(failures)
    return [failure for failure in AI_RESPONSE_FAILURE_TYPES if failure in seen]


def _status_for_failures(failure_types: list[str], retry_allowed: bool) -> str:
    if not failure_types:
        return AI_RESPONSE_STATUS_ACCEPTED_FOR_REVIEW
    if retry_allowed:
        return AI_RESPONSE_STATUS_RETRY_RECOMMENDED
    return AI_RESPONSE_STATUS_REJECTED


def _retry_recommendation(failure_types: list[str]) -> dict[str, object]:
    if not failure_types:
        return {
            "allowed": False,
            "reason": "The response is valid for review; no retry is needed.",
            "instruction": None,
        }

    if any(failure in NON_RETRYABLE_FAILURES for failure in failure_types):
        return {
            "allowed": False,
            "reason": "The response includes a non-retryable safety failure.",
            "instruction": None,
        }

    primary = failure_types[0]
    return {
        "allowed": True,
        "reason": "The response can be corrected with one retry.",
        "instruction": _retry_instruction(primary),
    }


def _retry_instruction(failure: str) -> str:
    if failure == FAILURE_NO_DIFF:
        return "Return only a valid unified diff for approved files."
    if failure == FAILURE_MALFORMED_DIFF:
        return "Return a structurally valid unified diff with repository-relative paths."
    if failure == FAILURE_OUT_OF_SCOPE_FILES:
        return "Return a unified diff that modifies only approved or expected related files."
    if failure == FAILURE_BLOCKED_NEW_FILES:
        return "Return a unified diff that creates only explicitly allowed new files."
    if failure == FAILURE_EXCESSIVE_CHANGES:
        return "Return a smaller unified diff within the requested change limits."
    return "Return only a valid unified diff for approved files."


def _diagnostic_for_failure(
    failure: str,
    details: dict[str, object],
) -> dict[str, object]:
    return build_diagnostic_event(
        f"ai_response_{failure}",
        DIAGNOSTIC_SEVERITY_ERROR,
        _failure_message(failure),
        source=DIAGNOSTIC_SOURCE_REVIEW,
        next_action="review_response",
        details=details,
    )


def _failure_message(failure: str) -> str:
    messages = {
        FAILURE_EMPTY_RESPONSE: "AI response is empty.",
        FAILURE_NO_DIFF: "AI response does not contain a unified diff.",
        FAILURE_MALFORMED_DIFF: "AI response contains a malformed unified diff.",
        FAILURE_OUT_OF_SCOPE_FILES: "AI response modifies files outside the approved scope.",
        FAILURE_BLOCKED_NEW_FILES: "AI response creates files that are not explicitly allowed.",
        FAILURE_UNSAFE_PATH: "AI response targets an unsafe path.",
        FAILURE_EXCESSIVE_CHANGES: "AI response exceeds configured change limits.",
        FAILURE_INJECTION_DETECTED: "AI response contains suspicious instruction text.",
    }
    return messages[failure]


def _validate_json_ready(value) -> None:
    if _copy_json_value(value) is _UNSUPPORTED:
        raise ValueError("AI response validation result must be JSON-ready.")


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
        for key in sorted(value.keys(), key=str):
            if not isinstance(key, str):
                return _UNSUPPORTED
            rendered = _copy_json_value(value[key])
            if rendered is _UNSUPPORTED:
                return _UNSUPPORTED
            copied[key] = rendered
        return copied
    return _UNSUPPORTED
