# Workflow State and Diagnostics

Part M owns workflow state and diagnostics. Its purpose is to make Strata's
workflow evidence reliable, deterministic, easy to validate, and useful for
later explanation without increasing prompt size.

Strata should increase understanding, not prompt size.

## Purpose and Product Value

Part M gives Strata a small, stable diagnostic language for workflow progress
and workflow failure. It turns run-state evidence, gate findings, review
findings, status summaries, and local error artifacts into deterministic
JSON-ready records that later product layers can consume.

Part M does not call model providers, choose adapters, render prompts, retry AI
requests, redesign guided UX, or decide what enters AI context. Part I remains
the token firewall.

## Completed Batch Summary

- M1 - complete. Run-state contract hardening, validation diagnostics,
  workflow status vocabulary, workflow summaries, and conservative next-action
  suggestions.
- M2 - complete. Canonical diagnostic event mappings, bounded severity/source
  vocabularies, deterministic normalization, sorting, exact deduplication, and
  compact summaries.
- M3 - complete. Plain-language gate and review explanations, recognized and
  generic explanation behavior, bounded affected-item extraction, and
  deterministic explanation summaries.
- M4 - complete. Workflow-status summary contract, health vocabulary, explicit
  completed and pending step derivation, one safe next action, and deterministic
  plain-text rendering.
- M5 - complete. Bounded run-error artifact contract, deterministic recovery
  guidance, local JSON and Markdown renderers, explicit safe repository-local
  writers, and privacy/token-firewall exclusions.
- M6 - complete. Final Part M contract documentation, ownership boundaries,
  stable vocabulary lock, and handoff to Part O.

## Public Module Ownership

| Module | Owns | Returns | Does not own |
| --- | --- | --- | --- |
| `strata/core/workflow_state.py` | Canonical run-state validation, workflow-state summaries, and conservative next-action derivation. | JSON-ready validation diagnostics, workflow summaries, and one next-action string. | Commands, artifact writing, model calls, prompts, or applying patches. |
| `strata/core/diagnostics.py` | Canonical diagnostic event mappings and deterministic normalization. | JSON-ready diagnostic events, sorted/deduplicated event lists, and compact count summaries. | User-facing explanations, enforcement, command execution, or prompt expansion. |
| `strata/core/diagnostic_explanations.py` | Plain-language explanations for existing gate/review/workflow diagnostics. | JSON-ready explanation records, explanation summaries, and bounded affected-item data. | Gate/review enforcement, apply safety, verification, or weakening safety decisions. |
| `strata/core/workflow_status.py` | Compact workflow-status data and pure text rendering. | JSON-ready workflow-status summaries and deterministic plain-text status blocks. | CLI command wiring, terminal UI, artifact writing, or AI control flow. |
| `strata/core/error_artifacts.py` | Bounded local run-error artifacts, deterministic recovery guidance, validation, and explicit safe writers. | JSON-ready run-error artifacts, JSON text, Markdown text, and explicit local artifact paths. | Logging frameworks, telemetry, automatic global hooks, prompt/context inclusion, or command redesign. |

## Stable Vocabularies

Workflow statuses:

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

M1 next actions:

- `repair_or_regenerate_run_state`
- `prepare_context`
- `request_ai_response`
- `review_response`
- `apply_patch`
- `run_verification`
- `workflow_complete`
- `inspect_diagnostics`

Safety rule: `apply_patch` is suggested only with explicit successful review
evidence. `workflow_status="ready_to_apply"` is supporting metadata, not proof
of review success by itself.

Diagnostic severities:

- `info`
- `warning`
- `error`

Diagnostic sources:

- `workflow_state`
- `context`
- `review`
- `apply`
- `verify`
- `gate`
- `system`

Workflow health values:

- `healthy`
- `attention`
- `blocked`
- `invalid`
- `complete`

Workflow-status steps:

- `prepare_context`
- `request_ai_response`
- `review_response`
- `apply_patch`
- `run_verification`
- `workflow_complete`
- `repair_run_state`
- `inspect_diagnostics`

Error-artifact stages:

- `prepare`
- `context`
- `ai_response`
- `review`
- `apply`
- `verify`
- `gate`
- `workflow`
- `unknown`

M3 explanation next actions:

- `inspect_details`
- `revise_patch`
- `remove_out_of_scope_changes`
- `approve_expected_file`
- `fix_imports`
- `run_tests`
- `run_verification`
- `regenerate_context`
- `repair_run_state`

M5 recovery guidance safe actions:

- `repair_or_regenerate_run_state`
- `prepare_context`
- `request_ai_response`
- `review_response`
- `revise_patch`
- `remove_out_of_scope_changes`
- `approve_expected_file`
- `fix_imports`
- `run_tests`
- `run_verification`
- `regenerate_context`
- `inspect_details`
- `inspect_diagnostics`

M3 and M5 never recommend applying, forcing, bypassing, disabling safety checks,
or ignoring warnings as recovery guidance.

## Stable Data Contracts

Workflow-state validation diagnostics from M1 contain:

- `code`
- `severity`
- `message`
- `field`
- `value`

Workflow-state summaries from M1 contain:

- `workflow_status`
- `is_valid`
- `task_present`
- `baseline_present`
- `baseline_status`
- `context_ready`
- `response_received`
- `patch_received`
- `review_status`
- `verification_status`
- `diagnostic_count`
- `next_action`
- `diagnostics`

Diagnostic events from M2 contain:

- required: `code`, `severity`, `message`, `source`
- optional string fields represented as null: `field`, `path`, `next_action`
- deterministic mapping: `details`

Diagnostic summaries from M2 contain:

- `total`
- `errors`
- `warnings`
- `info`
- `has_errors`
- `has_warnings`

Diagnostic explanations from M3 contain:

- `code`
- `severity`
- `source`
- `title`
- `explanation`
- `why_it_matters`
- `affected_items`
- `next_action`
- `technical_details`

Explanation summaries from M3 contain:

- `total`
- `errors`
- `warnings`
- `has_blocking_issues`
- `primary_next_action`

Workflow-status summaries from M4 contain:

- `status`
- `health`
- `title`
- `summary`
- `current_step`
- `completed_steps`
- `pending_steps`
- `blocking_issues`
- `warning_count`
- `next_action`
- `next_action_label`
- `details`

Run-error artifacts from M5 contain:

- `schema_version`
- `artifact_type`
- `workflow_status`
- `health`
- `stage`
- `summary`
- `primary_code`
- `next_action`
- `diagnostic_summary`
- `diagnostics`
- `explanations`
- `recovery_guidance`
- `metadata`

Recovery guidance records contain:

- `action`
- `label`
- `reason`
- `priority`

All Part M outputs are deterministic, JSON-ready, bounded where user/project
data could grow, and free of generated timestamps and random IDs.

## Deterministic Behavior

M1 validates run state without reading repository files or running commands.
Unknown extra run-state fields are left alone so later parts can add data
without breaking M1.

M2 normalizes, sorts, and deduplicates diagnostic events deterministically.
Deduplication removes only exactly equivalent canonical mappings.

M3 explains exact unique diagnostics in deterministic order. Recognized gate and
review diagnostics get specific explanations; unknown diagnostics get a generic
inspect-details explanation.

M4 derives status, health, completed steps, pending steps, and next action from
explicit workflow evidence. It does not infer review success from patch receipt,
does not infer verification success from patch application, and does not treat
`workflow_status="complete"` as complete without explicit verification success.

M5 selects a primary failure deterministically, builds bounded recovery guidance
from existing diagnostic/explanation/workflow next actions, and degrades unknown
or unsafe actions to `inspect_details`.

## Bounded-Output Rules

- M3 affected items per explanation: 20.
- M5 diagnostics per run-error artifact: 25.
- M5 explanations per run-error artifact: 25.
- M5 recovery guidance items per run-error artifact: 10.

When M5 truncates diagnostics, explanations, or recovery guidance, it records
compact truncation metadata. Part M does not include unbounded messages, arrays,
graphs, full prompts, full model responses, complete patches, full source files,
or stack traces.

## Path Safety and Privacy Rules

M5 JSON and Markdown writers target fixed repository-local defaults:

- `.aidc/diagnostics/run_error.json`
- `.aidc/diagnostics/run_error.md`

The writers are explicit helpers only. They reuse Strata artifact-writing
helpers for repository-local path safety, parent traversal rejection, symlink
checks, UTF-8 writing, and atomic replacement.

Part M excludes API keys, environment values, complete prompts, complete model
responses, complete patches, full source files, stack traces, user-home paths,
telemetry identifiers, and generated prompt/context expansion.

Part M does not create a logging system, add automatic CLI integration, add
telemetry, background services, daemon behavior, rotating logs, or automatic
global exception hooks.

## Part I Token-Firewall Boundary

Part I remains the token firewall. It alone decides what enters the canonical context artifacts.

- `.aidc/context/strata_context.md`
- `.aidc/context/context_pack.json`
- `.aidc/context/run_state.json`

Part M diagnostics and error artifacts do not automatically enter AI prompts.
Part O may render approved Part I context differently by capability profile, but
Part O must not treat Part M diagnostic storage as new prompt-budget authority.

Part M increases recoverability and understanding; it does not increase default
prompt size.

## Command and Integration Boundaries

Part M provides pure helpers, deterministic data contracts, renderers, and
explicit writers. It does not automatically wire artifact writing into every
failure path.

Part M does not implement:

- model or provider selection
- prompt rendering
- AI-response validation
- retries or fallback policy
- browser, CLI, or VS Code delivery surfaces
- multi-turn sessions
- user-level settings
- primary guided UX redesign
- workspace intelligence
- journey tracing
- telemetry
- background services

M5 writers are explicit helpers only. Part M does not automatically write error
artifacts on every failure.

## Handoff to Part O - Adapter and AI Workflow Control

Part O may consume these Part M contracts:

- validated workflow state
- canonical diagnostic events
- plain-language failure explanations
- workflow-status summaries
- safe next-action identifiers
- bounded run-error artifacts
- local recovery guidance

Part O owns the next adapter and AI workflow work:

- model capability profiles
- compact, balanced, and expanded rendering
- prompt template versioning
- AI-response validation
- retry and fallback policy
- browser, CLI, and VS Code delivery surfaces
- multi-turn session state
- user-level AI workflow settings

Part O must reuse Part M diagnostics rather than creating a competing failure
format.

## Remaining Roadmap Order

After Part M, the remaining roadmap order is:

- O - Adapter and AI Workflow Control
- N - UX / Workflow Polish
- Q - Workspace Intelligence
- P - User Flow / Journey Intelligence

O precedes N because UX should wrap the real adapter/model workflow. Q precedes
P because cross-repo journeys require workspace awareness.

Roadmap shorthand: M -> O -> N -> Q -> P. After M completion: O -> N -> Q -> P.

## Ownership Boundaries

M owns workflow state and diagnostics.

O owns adapter and AI workflow control, including adapters, model capability
profiles, prompts, AI response validation, retry, and delivery surfaces.

N owns UX/workflow polish.

Q owns workspace intelligence.

P owns user flow and journey intelligence.

M1, M2, M3, M4, M5, and M6 are complete.
