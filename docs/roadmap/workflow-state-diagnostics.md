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

## Ownership Boundaries

M owns workflow state and diagnostics.

O owns adapter, model-capability, prompt, AI-response, retry, and
delivery-surface control.

N owns guided UX and workflow polish.

M1 does not complete M2-M6 behavior. Broader diagnostic events, plain-language
gate/review explanations, user-facing workflow status commands, persistence and
recovery, and final handoff remain later Part M work.
