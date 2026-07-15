# Workflow State and Diagnostics

Part M owns workflow state and diagnostics. Its purpose is to make the existing
canonical run state reliable, deterministic, easy to validate, and useful for
later diagnostic explanation.

## M1: Run State Contract Hardening

M1 adds pure data-level workflow-state primitives in
`strata/core/workflow_state.py`. It does not add a command, persist diagnostic
events, call an AI provider, or change the generated context artifacts.

The bounded workflow status vocabulary is:

- `not_started`
- `context_ready`
- `awaiting_ai_response`
- `response_received`
- `review_required`
- `ready_to_apply`
- `verification_required`
- `complete`
- `blocked`
- `failed`

Run-state validation checks the existing canonical `run_state.json` contract
defined by Part I. It returns deterministic JSON-ready diagnostics for missing
required fields, invalid field types, invalid bounded values, malformed
collection entries, and unsupported schema versions. Unknown extra fields are
left alone so later parts can add data without breaking M1.

The next-action helper returns one conservative machine-readable action. Invalid
core state asks for repair or regeneration. Context-ready state without a
response asks for an AI response. A received response asks for review. Reviewed
state asks for apply. Applied state asks for verification. Completion is returned
only when explicit successful verification evidence exists.

Part I remains the token firewall. M1 consumes `run_state.json` but does not
increase prompt size, add default prompt evidence, duplicate representation or
budgeting authority, or create a competing state artifact.

## M2: Diagnostic Event Model

M2 adds a small canonical diagnostic event mapping in
`strata/core/diagnostics.py`. The public representation is plain JSON-ready data
only: dictionaries, lists, strings, integers, booleans, and nulls.

The canonical event shape is:

- `code`
- `severity`
- `message`
- `source`
- `field`
- `path`
- `next_action`
- `details`

`code`, `severity`, `message`, and `source` are required. `field`, `path`, and
`next_action` are optional string fields represented as null when absent.
`details` is always a deterministic mapping, empty when absent.

The bounded severity vocabulary is:

- `info`
- `warning`
- `error`

The bounded source vocabulary is:

- `workflow_state`
- `context`
- `review`
- `apply`
- `verify`
- `gate`
- `system`

Normalization validates events, copies caller-owned details, preserves list
order, and emits mapping keys in deterministic sorted order. Sorting is exact and
deterministic: error, warning, info, then source, code, path, field, message,
next action, and canonical details. Deduplication removes only exactly
equivalent canonical mappings. Summaries contain only compact counts: total,
errors, warnings, info, has_errors, and has_warnings.

M2 does not change M1 diagnostic output. M1-style diagnostics can be adapted with
`normalize_diagnostic_event(..., default_source="workflow_state")`; legacy
`value` is placed only in `details["value"]` in canonical M2 form.

M2 diagnostic events do not automatically enter Part I context artifacts. Part I
remains the token firewall.

## M3: Gate and Review Explanation Layer

M3 adds pure explanation helpers in `strata/core/diagnostic_explanations.py`.
The helpers turn canonical M2 diagnostics, or M1-style diagnostics normalized
through M2, into concise JSON-ready plain-language explanations.

Each explanation records the original code, severity, and source, plus a title,
plain explanation, why-it-matters text, bounded affected items, one safe next
action, and technical details. Recognized gate and review diagnostics get
specific explanations. Unknown diagnostics get a conservative generic
explanation that asks the user to inspect details rather than guessing a cause.

Affected-item extraction reads only existing diagnostic data such as path, field,
targets, paths, files, imports, failures, errors, and warnings. It removes exact
duplicates, sorts deterministically, and shows at most 20 items while recording
truncation metadata.

M3 next actions are intentionally conservative, such as `inspect_details`,
`revise_patch`, `remove_out_of_scope_changes`, `fix_imports`, `run_tests`,
`run_verification`, `regenerate_context`, and `repair_run_state`. M3 never
recommends applying, forcing, bypassing, or ignoring safety checks.

Batch helpers deduplicate exact diagnostic events before explanation, preserve
deterministic severity ordering, and provide compact summary counts with a
deterministic primary next action. M3 does not change gate failure detection,
review classifications, scope rules, apply safety, verification behavior, or
exit codes.

M3 explanations do not automatically enter Part I context artifacts. Part I
remains the token firewall.

## M4: Workflow Status Summary

M4 adds pure workflow-status helpers in `strata/core/workflow_status.py`. The
status result is a deterministic JSON-ready mapping with status, health, title,
summary, current step, completed steps, pending steps, blocking issue count,
warning count, one safe next action, a next-action label, and compact details.

The health vocabulary is:

- `healthy`
- `attention`
- `blocked`
- `invalid`
- `complete`

Current, completed, and pending steps are derived conservatively from explicit
workflow evidence. The ordered workflow steps are `prepare_context`,
`request_ai_response`, `review_response`, `apply_patch`, `run_verification`, and
`workflow_complete`. Invalid state uses `repair_run_state`, and blocking issues
use `inspect_diagnostics`.

M4 reuses M1 validation and next-action suggestions, M2 diagnostic normalization
and compact counts, and M3 explanation summaries when supplied. It does not infer
review success from patch receipt, does not infer verification success from patch
application, and does not treat `workflow_status="complete"` as complete without
explicit verification success.

The text renderer returns a concise deterministic plain-text block with status,
current step, blocking issue count, warning count, and next action. It does not
print, use colors, inspect terminal width, or depend on Rich.

M4 provides status data and pure rendering helpers only. M4 does not add or
redesign a CLI command, does not automatically write status artifacts, and does
not automatically enter Part I context artifacts. Part I remains the token
firewall.

## M5: Error Artifact and Recovery Guidance

M5 adds local run-error artifact helpers in `strata/core/error_artifacts.py`.
The artifact contract records schema version, artifact type, workflow status,
health, stage, summary, primary code, next action, diagnostic summary, bounded
diagnostics, bounded explanations, bounded recovery guidance, and metadata.

Run-error artifacts are local-only and use `schema_version` 1 with
`artifact_type` set to `run_error`. Supported stages are `prepare`, `context`,
`ai_response`, `review`, `apply`, `verify`, `gate`, `workflow`, and `unknown`.

M5 composes M1 validation, M2 diagnostic normalization and summaries, M3
explanations, and M4 workflow status summaries. Diagnostic and explanation lists
are capped at 25 entries each. Recovery guidance is capped at 10 entries.
Truncation is recorded in compact metadata rather than silently discarded.

Recovery guidance is derived only from existing diagnostic, explanation, and
workflow next actions. Unsafe actions such as force apply, bypass review, disable
gate, ignore warnings, or skip verification are never emitted; unknown actions
fall back to inspecting details.

Explicit JSON and Markdown writers target fixed repository-local paths under
`.aidc/diagnostics/run_error.json` and `.aidc/diagnostics/run_error.md` by
default. They reuse Strata artifact-writing helpers for repository-local path
safety, traversal rejection, symlink checks, UTF-8 writing, and atomic
replacement.

M5 excludes API keys, environment values, full prompts, full model responses,
complete patches, full source files, stack traces, user-home paths, and telemetry
identifiers. M5 artifacts do not automatically enter Part I context artifacts.
Part I remains the token firewall.

M5 provides local error artifact builders, renderers, and explicit writers. M5
does not create a logging system, does not add telemetry, does not automatically
wire artifact writing into all commands, and does not change gate, review, apply,
or verification enforcement.

## Ownership Boundaries

M owns workflow state and diagnostics.

O owns adapters, model capability, prompts, AI response validation, retry, and
delivery surfaces.

N owns guided UX and workflow polish.

M1, M2, M3, M4, and M5 are implemented. M6 is not implemented. Final Part M
handoff remains later Part M work.
