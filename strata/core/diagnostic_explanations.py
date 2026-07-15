from collections.abc import Mapping

from strata.core.diagnostics import (
    DIAGNOSTIC_SOURCE_GATE,
    DIAGNOSTIC_SOURCE_REVIEW,
    DIAGNOSTIC_SOURCE_WORKFLOW_STATE,
    DIAGNOSTIC_SEVERITY_ERROR,
    DIAGNOSTIC_SEVERITY_WARNING,
    build_diagnostic_event,
    deduplicate_diagnostic_events,
    normalize_diagnostic_event,
)


AFFECTED_ITEM_LIMIT = 20

NEXT_ACTION_INSPECT_DETAILS = "inspect_details"
NEXT_ACTION_REVISE_PATCH = "revise_patch"
NEXT_ACTION_REMOVE_OUT_OF_SCOPE_CHANGES = "remove_out_of_scope_changes"
NEXT_ACTION_APPROVE_EXPECTED_FILE = "approve_expected_file"
NEXT_ACTION_FIX_IMPORTS = "fix_imports"
NEXT_ACTION_RUN_TESTS = "run_tests"
NEXT_ACTION_RUN_VERIFICATION = "run_verification"
NEXT_ACTION_REGENERATE_CONTEXT = "regenerate_context"
NEXT_ACTION_REPAIR_RUN_STATE = "repair_run_state"
EXPLANATION_NEXT_ACTIONS = (
    NEXT_ACTION_INSPECT_DETAILS,
    NEXT_ACTION_REVISE_PATCH,
    NEXT_ACTION_REMOVE_OUT_OF_SCOPE_CHANGES,
    NEXT_ACTION_APPROVE_EXPECTED_FILE,
    NEXT_ACTION_FIX_IMPORTS,
    NEXT_ACTION_RUN_TESTS,
    NEXT_ACTION_RUN_VERIFICATION,
    NEXT_ACTION_REGENERATE_CONTEXT,
    NEXT_ACTION_REPAIR_RUN_STATE,
)
UNSAFE_NEXT_ACTIONS = {
    "apply_patch",
    "force_apply",
    "ignore_warning",
    "disable_gate",
    "bypass_review",
}

CODE_GATE_UNRESOLVED_IMPORTS = "gate_unresolved_imports"
CODE_GATE_FILE_ERRORS = "gate_file_errors"
CODE_GATE_GRAPH_INVALID = "gate_graph_invalid"
CODE_GATE_NO_SOURCE_FILES = "gate_no_source_files"
CODE_GATE_ROUTES_DATA_MALFORMED = "gate_routes_data_malformed"
CODE_GATE_DUPLICATE_ROUTES = "gate_duplicate_routes"
CODE_GATE_ROUTE_IMPORT_RISKS = "gate_route_import_risks"
CODE_GATE_DEPENDENCY_CYCLES = "gate_dependency_cycles"
CODE_REVIEW_PATCH_MISSING = "review_patch_missing"
CODE_REVIEW_PATCH_EMPTY = "review_patch_empty"
CODE_REVIEW_PATCH_MALFORMED = "review_patch_malformed"
CODE_REVIEW_PATCH_UNSAFE_PATH = "review_patch_unsafe_path"
CODE_REVIEW_PATCH_DANGEROUS_TARGET = "review_patch_dangerous_target"
CODE_REVIEW_PATCH_FORBIDDEN_TARGET = "review_patch_forbidden_target"
CODE_REVIEW_PATCH_TARGET_EXISTS = "review_patch_target_exists"
CODE_REVIEW_PATCH_GENERATED_TARGET = "review_patch_generated_target"

_EXPLANATIONS = {
    CODE_GATE_UNRESOLVED_IMPORTS: {
        "title": "The project has imports Strata cannot resolve.",
        "explanation": "Strata found code that imports modules or files that are not available in the scanned project.",
        "why_it_matters": "Missing imports can break the application or hide problems in the generated patch.",
        "next_action": NEXT_ACTION_FIX_IMPORTS,
    },
    CODE_GATE_FILE_ERRORS: {
        "title": "Strata found source files with syntax or scan errors.",
        "explanation": "The gate detected files that could not be scanned cleanly.",
        "why_it_matters": "Strata cannot safely reason about a project while important files contain parse or scan errors.",
        "next_action": NEXT_ACTION_RUN_VERIFICATION,
    },
    CODE_GATE_GRAPH_INVALID: {
        "title": "The project scan result is malformed.",
        "explanation": "Strata could not validate the structured project graph used by the gate.",
        "why_it_matters": "A malformed graph can make safety checks incomplete or misleading.",
        "next_action": NEXT_ACTION_REGENERATE_CONTEXT,
    },
    CODE_GATE_NO_SOURCE_FILES: {
        "title": "Strata did not find source files to check.",
        "explanation": "The gate ran, but the scan result did not include any source files.",
        "why_it_matters": "Without source files, Strata has little evidence for repository safety.",
        "next_action": NEXT_ACTION_REGENERATE_CONTEXT,
    },
    CODE_GATE_ROUTES_DATA_MALFORMED: {
        "title": "Route information is missing or malformed.",
        "explanation": "Strata could not use route data while checking the project.",
        "why_it_matters": "Missing route data can hide web entry-point risks.",
        "next_action": NEXT_ACTION_REGENERATE_CONTEXT,
    },
    CODE_GATE_DUPLICATE_ROUTES: {
        "title": "The project has duplicate route definitions.",
        "explanation": "Strata found routes that appear to handle the same endpoint more than once.",
        "why_it_matters": "Duplicate routes can cause requests to use the wrong handler or behave unpredictably.",
        "next_action": NEXT_ACTION_RUN_TESTS,
    },
    CODE_GATE_ROUTE_IMPORT_RISKS: {
        "title": "Some route handlers have import risks.",
        "explanation": "Strata found route-related import issues during gate checks.",
        "why_it_matters": "A route can fail at runtime if its handler depends on missing code.",
        "next_action": NEXT_ACTION_FIX_IMPORTS,
    },
    CODE_GATE_DEPENDENCY_CYCLES: {
        "title": "The project has dependency cycles.",
        "explanation": "Strata found files or modules that depend on each other in a cycle.",
        "why_it_matters": "Cycles can make changes harder to reason about and can cause runtime import problems.",
        "next_action": NEXT_ACTION_RUN_TESTS,
    },
    CODE_REVIEW_PATCH_MISSING: {
        "title": "No patch was available for review.",
        "explanation": "Strata could not find the AI patch file that review expects.",
        "why_it_matters": "Review cannot confirm safety until there is a patch to inspect.",
        "next_action": NEXT_ACTION_REGENERATE_CONTEXT,
    },
    CODE_REVIEW_PATCH_EMPTY: {
        "title": "The patch file is empty.",
        "explanation": "Strata found a patch file, but it does not contain any changes.",
        "why_it_matters": "An empty patch cannot satisfy the requested code change.",
        "next_action": NEXT_ACTION_REVISE_PATCH,
    },
    CODE_REVIEW_PATCH_MALFORMED: {
        "title": "The patch is not a valid unified diff.",
        "explanation": "Strata could not read the patch as a normal diff.",
        "why_it_matters": "Malformed patches cannot be reviewed or applied safely.",
        "next_action": NEXT_ACTION_REVISE_PATCH,
    },
    CODE_REVIEW_PATCH_UNSAFE_PATH: {
        "title": "The patch targets an unsafe path.",
        "explanation": "Strata blocked the patch because at least one path is outside the allowed repository area or otherwise unsafe.",
        "why_it_matters": "Applying it could change files Strata is not allowed to manage.",
        "next_action": NEXT_ACTION_REMOVE_OUT_OF_SCOPE_CHANGES,
    },
    CODE_REVIEW_PATCH_DANGEROUS_TARGET: {
        "title": "The patch targets a sensitive file or directory.",
        "explanation": "Strata blocked the patch because it touches a path such as secrets or SSH configuration.",
        "why_it_matters": "Changing sensitive files can expose secrets or compromise the development environment.",
        "next_action": NEXT_ACTION_REMOVE_OUT_OF_SCOPE_CHANGES,
    },
    CODE_REVIEW_PATCH_FORBIDDEN_TARGET: {
        "title": "The patch targets a forbidden Strata or Git path.",
        "explanation": "Strata blocked the patch because it modifies files that should not be changed by an AI patch.",
        "why_it_matters": "Changing generated control files can weaken later safety checks.",
        "next_action": NEXT_ACTION_REMOVE_OUT_OF_SCOPE_CHANGES,
    },
    CODE_REVIEW_PATCH_TARGET_EXISTS: {
        "title": "The patch tries to create a file that already exists.",
        "explanation": "Strata found a create-file patch for a path that is already present.",
        "why_it_matters": "Applying it could overwrite or conflict with existing work.",
        "next_action": NEXT_ACTION_REVISE_PATCH,
    },
    CODE_REVIEW_PATCH_GENERATED_TARGET: {
        "title": "The patch targets generated Strata output.",
        "explanation": "Strata found changes under generated `.aidc` output.",
        "why_it_matters": "Generated reports and prompts are usually not source changes and should not be committed accidentally.",
        "next_action": NEXT_ACTION_REVISE_PATCH,
    },
}


def explain_diagnostic_event(event) -> dict[str, object]:
    """Return one deterministic plain-language explanation for a diagnostic event."""

    diagnostic = normalize_diagnostic_event(
        event,
        default_source=DIAGNOSTIC_SOURCE_WORKFLOW_STATE,
    )
    template = _EXPLANATIONS.get(diagnostic["code"])
    affected_items, item_details = extract_affected_items(diagnostic)
    technical_details = _technical_details(diagnostic, item_details)

    if template is None:
        return _build_explanation(
            diagnostic,
            title="Strata detected a diagnostic that needs attention.",
            explanation="Strata reported this issue, but M3 does not have a specific explanation for it yet.",
            why_it_matters="The safest next step is to inspect the technical details before changing anything.",
            affected_items=affected_items,
            next_action=NEXT_ACTION_INSPECT_DETAILS,
            technical_details=technical_details,
        )

    return _build_explanation(
        diagnostic,
        title=template["title"],
        explanation=template["explanation"],
        why_it_matters=template["why_it_matters"],
        affected_items=affected_items,
        next_action=template["next_action"],
        technical_details=technical_details,
    )


def explain_diagnostic_events(events) -> list[dict[str, object]]:
    """Return deterministic explanations for exact unique diagnostic events."""

    return [
        explain_diagnostic_event(event)
        for event in deduplicate_diagnostic_events(events)
    ]


def summarize_diagnostic_explanations(explanations) -> dict[str, object]:
    """Return compact counts and the primary safe next action."""

    if not isinstance(explanations, (list, tuple)):
        raise ValueError("diagnostic explanations must be a list or tuple.")

    normalized = [_normalize_explanation(explanation) for explanation in explanations]
    errors = sum(1 for explanation in normalized if explanation["severity"] == "error")
    warnings = sum(1 for explanation in normalized if explanation["severity"] == "warning")
    primary = sorted(normalized, key=_explanation_sort_key)[0]["next_action"] if normalized else None
    return {
        "total": len(normalized),
        "errors": errors,
        "warnings": warnings,
        "has_blocking_issues": errors > 0,
        "primary_next_action": primary,
    }


def extract_affected_items(event) -> tuple[list[str], dict[str, object]]:
    """Extract a bounded deterministic affected-item list from a diagnostic event."""

    diagnostic = normalize_diagnostic_event(
        event,
        default_source=DIAGNOSTIC_SOURCE_WORKFLOW_STATE,
    )
    candidates: list[str] = []
    for field in ("path", "field"):
        _collect_strings(diagnostic.get(field), candidates)

    details = diagnostic.get("details")
    if isinstance(details, Mapping):
        for key in ("paths", "files", "targets", "imports", "failures", "errors", "warnings"):
            _collect_strings(details.get(key), candidates)

    unique = sorted(dict.fromkeys(_normalize_affected_item(item) for item in candidates if str(item)))
    shown = unique[:AFFECTED_ITEM_LIMIT]
    metadata = {
        "affected_item_count": len(unique),
        "affected_items_shown": len(shown),
        "affected_items_truncated": len(unique) > AFFECTED_ITEM_LIMIT,
    }
    return shown, metadata


def gate_result_to_diagnostic_events(report) -> list[dict[str, object]]:
    """Convert the current gate report shape into canonical diagnostic events."""

    if not isinstance(report, Mapping):
        raise ValueError("gate report must be a mapping.")

    events: list[dict[str, object]] = []
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    for failure in _string_list(report.get("failures")):
        events.append(_gate_event(_gate_failure_code(failure), "error", failure, summary))

    for warning in _string_list(report.get("warnings")):
        events.append(_gate_event(_gate_warning_code(warning), "warning", warning, summary))

    return events


def review_result_to_diagnostic_events(result) -> list[dict[str, object]]:
    """Convert current patch review validation shapes into canonical diagnostic events."""

    if not isinstance(result, Mapping):
        raise ValueError("review result must be a mapping.")

    validation = result.get("validation") if isinstance(result.get("validation"), Mapping) else result
    status = str(validation.get("status") or result.get("status") or "").lower()
    targets = _string_list(validation.get("targets") or result.get("targets"))
    errors = _string_list(validation.get("errors"))
    warnings = _string_list(validation.get("warnings"))
    message = str(validation.get("message") or result.get("message") or "Patch review reported a problem.")
    events: list[dict[str, object]] = []

    if status in {"missing", "empty"}:
        events.append(
            _review_event(
                CODE_REVIEW_PATCH_MISSING if status == "missing" else CODE_REVIEW_PATCH_EMPTY,
                "error",
                message,
                targets,
                errors,
                warnings,
            )
        )
        return events

    for error in errors:
        events.append(
            _review_event(
                _review_error_code(error),
                "error",
                error,
                targets,
                [error],
                warnings,
            )
        )

    for warning in warnings:
        events.append(
            _review_event(
                _review_warning_code(warning),
                "warning",
                warning,
                targets,
                errors,
                [warning],
            )
        )

    if status == "invalid" and not events:
        events.append(
            _review_event(
                CODE_REVIEW_PATCH_MALFORMED,
                "error",
                message,
                targets,
                errors,
                warnings,
            )
        )

    return events


def _build_explanation(
    diagnostic: Mapping,
    *,
    title: str,
    explanation: str,
    why_it_matters: str,
    affected_items: list[str],
    next_action: str,
    technical_details: dict[str, object],
) -> dict[str, object]:
    if next_action not in EXPLANATION_NEXT_ACTIONS or next_action in UNSAFE_NEXT_ACTIONS:
        raise ValueError("next_action is not safe for diagnostic explanations.")
    return {
        "code": diagnostic["code"],
        "severity": diagnostic["severity"],
        "source": diagnostic["source"],
        "title": title,
        "explanation": explanation,
        "why_it_matters": why_it_matters,
        "affected_items": list(affected_items),
        "next_action": next_action,
        "technical_details": technical_details,
    }


def _technical_details(diagnostic: Mapping, item_details: Mapping) -> dict[str, object]:
    details = dict(diagnostic.get("details") or {})
    details.update(item_details)
    details["original_message"] = diagnostic["message"]
    return _copy_json(details)


def _normalize_explanation(explanation) -> dict[str, object]:
    if not isinstance(explanation, Mapping):
        raise ValueError("diagnostic explanation must be a mapping.")
    return _copy_json(dict(explanation))


def _explanation_sort_key(explanation: Mapping) -> tuple[object, ...]:
    severity_order = {"error": 0, "warning": 1, "info": 2}
    return (
        severity_order.get(str(explanation.get("severity") or ""), 3),
        str(explanation.get("source") or ""),
        str(explanation.get("code") or ""),
        str(explanation.get("next_action") or ""),
        str(explanation.get("title") or ""),
    )


def _gate_event(code: str, severity: str, message: str, summary: Mapping) -> dict[str, object]:
    return build_diagnostic_event(
        code,
        severity,
        message,
        source=DIAGNOSTIC_SOURCE_GATE,
        details={"summary": _copy_json(dict(summary))},
    )


def _review_event(
    code: str,
    severity: str,
    message: str,
    targets: list[str],
    errors: list[str],
    warnings: list[str],
) -> dict[str, object]:
    return build_diagnostic_event(
        code,
        severity,
        message,
        source=DIAGNOSTIC_SOURCE_REVIEW,
        details={
            "targets": targets,
            "errors": errors,
            "warnings": warnings,
        },
    )


def _gate_failure_code(message: str) -> str:
    text = message.lower()
    if "unresolved imports" in text:
        return CODE_GATE_UNRESOLVED_IMPORTS
    if "syntax/error fields" in text:
        return CODE_GATE_FILE_ERRORS
    return CODE_GATE_GRAPH_INVALID


def _gate_warning_code(message: str) -> str:
    text = message.lower()
    if "no source files" in text:
        return CODE_GATE_NO_SOURCE_FILES
    if "routes_data is missing or malformed" in text:
        return CODE_GATE_ROUTES_DATA_MALFORMED
    if "duplicate route warnings" in text:
        return CODE_GATE_DUPLICATE_ROUTES
    if "route import risks" in text:
        return CODE_GATE_ROUTE_IMPORT_RISKS
    if "dependency cycles" in text:
        return CODE_GATE_DEPENDENCY_CYCLES
    return CODE_GATE_GRAPH_INVALID


def _review_error_code(message: str) -> str:
    text = message.lower()
    if "patch file not found" in text:
        return CODE_REVIEW_PATCH_MISSING
    if "patch file is empty" in text:
        return CODE_REVIEW_PATCH_EMPTY
    if "unsafe patch path" in text:
        return CODE_REVIEW_PATCH_UNSAFE_PATH
    if "dangerous" in text:
        return CODE_REVIEW_PATCH_DANGEROUS_TARGET
    if "forbidden" in text:
        return CODE_REVIEW_PATCH_FORBIDDEN_TARGET
    if "already exists for creation" in text:
        return CODE_REVIEW_PATCH_TARGET_EXISTS
    return CODE_REVIEW_PATCH_MALFORMED


def _review_warning_code(message: str) -> str:
    text = message.lower()
    if "generated file" in text or ".aidc/" in text:
        return CODE_REVIEW_PATCH_GENERATED_TARGET
    return CODE_REVIEW_PATCH_MALFORMED


def _collect_strings(value, items: list[str]) -> None:
    if value is None:
        return
    if isinstance(value, str):
        if value:
            items.append(value)
        return
    if isinstance(value, list):
        for item in value:
            _collect_strings(item, items)
        return
    if isinstance(value, Mapping):
        for key in ("path", "file", "target", "name", "import", "message"):
            _collect_strings(value.get(key), items)
        return


def _normalize_affected_item(value: str) -> str:
    return str(value).replace("\\", "/").strip()


def _string_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def _copy_json(value):
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, list):
        return [_copy_json(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _copy_json(value[key]) for key in sorted(value)}
    return str(value)
