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

## Ownership Boundaries

M owns workflow state and diagnostics.

O owns AI adapters, capability profiles, prompts, response validation, retry,
and delivery surfaces.

N owns guided UX and workflow polish.

M1 and M2 are implemented. M3-M6 are not implemented. Plain-language gate/review
explanations, user-facing workflow status commands, persisted error artifacts,
and final handoff remain later Part M work.
