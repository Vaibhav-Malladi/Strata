# UX Workflow Polish

Part N makes the normal Strata workflow feel guided instead of command-heavy.
It presents existing workflow evidence in plain language and points to one
primary next action at a time.

## Batch Status

- N1 - Guided Workflow UX Contract - implemented.
- N2 - One Primary Guided Command - implemented.
- N3 - Progress and Status Presentation - implemented.
- N4 - Confirmations, Recovery, and Next Actions - implemented.
- N5 - Settings Change Workflow - not implemented.
- N6 - Help Text, Documentation, and Integration Polish - not implemented.

## N1 Contract

N1 adds `strata/core/guided_workflow.py`, a pure presentation helper that turns
caller-supplied workflow state, session state, and diagnostics into a
deterministic JSON-ready guided view. The view contains a plain-language status,
one primary next action, a short explanation, optional warnings, confirmation
metadata, blocking metadata, and compact details.

N1 follows the one-primary-action principle. Every non-complete view returns
exactly one next action. Complete workflows return `next_action = "none"`.
Warnings can explain additional concerns, but they do not create a competing
action menu.

## Stable Vocabulary

N1 uses this deterministic stage vocabulary:

- `setup_required`
- `ready`
- `context_prepared`
- `prompt_ready`
- `awaiting_ai_response`
- `response_received`
- `retry_available`
- `ready_for_review`
- `review_blocked`
- `ready_to_apply`
- `verification_required`
- `complete`

N1 uses this deterministic next-action vocabulary:

- `run_setup`
- `prepare_context`
- `deliver_prompt`
- `provide_ai_response`
- `retry_ai_request`
- `review_changes`
- `resolve_review_issues`
- `apply_changes`
- `run_verification`
- `view_results`
- `none`

## Decision Priority

N1 uses a small conservative priority order:

1. blocking diagnostics
2. contradictory state
3. incomplete setup
4. review blockers
5. verification required
6. complete
7. ready to apply
8. retry available
9. response ready for review
10. response received
11. waiting for AI response
12. prompt prepared but not delivered
13. context prepared
14. missing context
15. ambiguous state

Blocking diagnostics override normal progress. Contradictory or ambiguous state
does not guess that the workflow is safe; it returns a blocking view and asks the
user to resolve the current issues.

## Warnings

Warnings are short deterministic mappings with `code` and `message`. N1 reuses
supplied warning diagnostics and compact workflow warnings where practical. It
deduplicates and orders warnings deterministically, returns at most five, and
records truncation in `details`.

N1 does not include full stack traces, full patches, full prompts, secrets, or
absolute user paths in warning records.

## Confirmation Metadata

N1 sets `confirmation_required = true` only when the primary action is
`apply_changes`, because applying changes may alter repository state. Preparing
context, delivering prompts, reviewing, viewing results, and verification
guidance do not require confirmation at this contract layer.

N1 does not implement confirmation prompts. That belongs to N4.

## Authority Boundaries

N1 does not wire commands.

N1 does not alter workflow state.

N1 does not perform setup, review, apply, or verification.

N1 only converts existing state into a guided user-facing view.

N1 does not replace Part M workflow state, Part M diagnostics, O6 session state,
or O7 user settings. It does not write or persist state, mutate canonical
context artifacts, inspect Git, read files, call commands, call models, validate
patches, apply patches, add terminal rendering, or add new dependencies.

## N2 Primary Command

N2 makes `strata start` the primary normal-flow command. Advanced commands such
as `ask`, `run`, `prepare`, `review`, `apply`, `verify`, `gate`, and `status`
remain available for experienced users, but the ordinary workflow starts with
`strata start` and shows exactly one recommended next action.

N2 loads existing state and delegates stage/action decisions to the N1 guided
workflow contract. It does not duplicate N1 decision logic. Missing optional
session state is treated as absent, because O6 does not persist sessions yet.
Missing setup or run-state artifacts are converted into conservative N1 inputs
so the user gets setup or context guidance instead of a crash.

N2 output is intentionally basic plain text:

- a `Strata` heading
- the N1 headline
- the N1 summary
- deterministic warnings when present
- one `Next step` section for non-complete workflows

When the N1 view is complete, N2 omits the `Next step` section and does not invent a
follow-up action. When N1 marks an action as confirmation-required, N2 displays
confirmation guidance but does not perform the action.

N2 does not automatically apply changes.

N2 does not perform confirmation prompts.

N2 does not execute the recommended next action yet.

N2 does not call AI models, deliver prompts, validate AI responses, run
verification, inspect Git, refresh scan/snapshot artifacts, add Rich
presentation, add progress bars, persist sessions, or modify settings.

N3 improves presentation and progress.

N4 will implement confirmations and recovery behavior.

## N3 Progress Presentation

N3 improves the `strata start` presentation without changing workflow
decisions or command coordination. It renders the N1 guided view through a
small deterministic progress model with eight display steps:

- Setup
- Prepare context
- Send to AI
- Receive response
- Review
- Apply
- Verify
- Complete

N3 maps N1 stages onto those display steps only for presentation:

- `setup_required` -> Setup
- `ready`, `context_prepared` -> Prepare context
- `prompt_ready`, `awaiting_ai_response` -> Send to AI
- `response_received`, `retry_available` -> Receive response
- `ready_for_review`, `review_blocked` -> Review
- `ready_to_apply` -> Apply
- `verification_required` -> Verify
- `complete` -> Complete

Progress items use the stable states `complete`, `current`, `upcoming`, and
`blocked`. The normal text output renders those states with readable labels
such as `[done]`, `[now]`, `[next]`, and `[blocked]`, so captured output and
plain terminals remain understandable without color.

Stage labels are plain language, such as `Ready for review`, `Review blocked`,
and `Verification required`. Normal user output does not expose raw snake_case
stage names, JSON, internal state dumps, or diagnostic payloads.

Warnings are shown only when present, in the deterministic order supplied by
N1. Warning messages are concise list items and do not create additional primary
actions.

N3 shows one `Next step` section for non-complete workflows and omits that
section for complete workflows. Confirmation-required actions show a short note
that confirmation is required before repository files are changed.

N3 does not alter workflow decisions.

N3 does not execute the next action.

N3 does not prompt for confirmation.

N3 does not redesign scan progress.

N3 only improves guided workflow presentation.

## N4 Confirmations And Recovery

N4 keeps plain `strata start` status-only. It shows the guided status,
progress, warnings, and one recommended next step without executing the action.

N4 adds one continuation path:

- `strata start --continue`
- `strata start --continue <root>`

The continuation path attempts exactly the single action selected by N1. It
does not add a command menu, action picker, or multi-action workflow.

N4 classifies the existing N1 action vocabulary into bounded categories:

- informational: `run_setup`, `prepare_context`, `resolve_review_issues`,
  `view_results`, `none`
- delegatable: `review_changes`, `run_verification`
- destructive: `apply_changes`
- unsupported for now: `deliver_prompt`, `provide_ai_response`,
  `retry_ai_request`

Delegatable actions reuse existing command handlers directly. N4 does not shell
out to `python -m strata` or duplicate review, verification, or apply logic.

`apply_changes` always requires explicit confirmation:

```text
Apply the reviewed changes? [y/N]
```

Only `y` or `yes` proceeds. Empty input, `n`, `no`, and unrecognized input
cancel conservatively. Cancellation is normal command completion, does not
change repository files, and says:

```text
Cancelled. No files were changed.
```

Manual AI-transfer actions are not executed. N4 gives one concise instruction,
such as copying the prepared request into the AI tool, pasting the AI response
back into Strata, or sending the corrected request manually.

Action attempts return a deterministic JSON-ready result with:

- `action`
- `status`
- `executed`
- `message`
- `next_action`
- `next_action_label`
- `blocking`
- `recovery`

Stable statuses are `not_executed`, `cancelled`, `completed`, `blocked`, and
`failed`.

Recovery guidance is bounded and concise. Examples include committing or
stashing a dirty worktree before applying, preparing missing context, recreating
malformed state, resolving review issues, and reviewing verification reports.

N4 does not bypass apply safety.

N4 does not call AI models.

N4 does not access the clipboard or browser.

N4 does not execute more than one action.

N4 does not add a command menu.

N4 does not implement settings changes.
