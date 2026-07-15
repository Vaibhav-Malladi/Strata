# Adapter and AI Workflow Control

Part O defines the adapter and AI workflow control foundations that sit after
the canonical context and workflow-state contracts. Its purpose is to let
Strata shape future AI workflow guidance from capability-first data while
preserving Part I as the token firewall and reusing Part M diagnostics for
workflow failures.

## Batch Status

- O1 - Capability Profile Foundation - implemented.
- O2 - Context Pack Rendering Layer - implemented.
- O3 - Prompt Template System - implemented.
- O4 - AI Response Validation and Recovery - implemented.
- O5 - Delivery Surface Adapters - implemented.
- O6 - Multi-turn Session State - implemented.
- O7 - User Settings and Capability Override - implemented.

## Capability-First Design

Capability tier drives rendering decisions. Delivery surface is secondary, and
model names are not core logic.

Capability tiers do not identify exact model brands or versions. Users should
not need to choose an exact model every run. O1 describes internal capability
categories only:

- `unknown`
- `weak`
- `medium`
- `strong`

The stable deterministic order is `unknown`, `weak`, `medium`, `strong`.

## Capability Profile Fields

O1 defines an immutable profile contract with these fields:

- `tier`
- `context_window_class`
- `instruction_adherence`
- `diff_reliability`
- `structured_output_reliability`
- `multi_file_reasoning`
- `needs_explicit_steps`
- `needs_diff_example`
- `preferred_context_variant`
- `max_recommended_files`

Bounded profile vocabularies keep the contract deterministic:

- `context_window_class`: `small`, `medium`, `large`, `unknown`
- reliability fields: `low`, `medium`, `high`, `unknown`
- `preferred_context_variant`: `compact`, `balanced`, `expanded`

## Built-In Profiles

The built-in `weak` profile is compact and conservative. It requests explicit
steps and a diff example, records lower diff and structured-output reliability,
and recommends a small bounded file count.

The built-in `medium` profile is balanced. It uses moderate reliability values,
does not require a diff example, and recommends a moderate bounded file count.

The built-in `strong` profile is expanded. It uses high reliability values,
does not require explicit step scaffolding or diff examples, and recommends a
larger file count that remains below the hard upper bound.

The built-in `unknown` profile is conservative. It uses the balanced context
variant, unknown capability values, explicit guidance, a diff example, and a
bounded file count safe for browser workflows where model capability is not
known. Unknown is not treated as strong.

## Conservative Unknown Fallback

O1 exposes a conservative unknown fallback profile for later workflow code. It
does not implement automatic model detection, model-name mapping, adapter
metadata inspection, or provider lookup.

## Bounded File Recommendations

`max_recommended_files` must be a positive integer and cannot exceed `40`.
Malformed values raise `ValueError`; they are not silently clamped.

This recommendation is guidance for later Part O rendering decisions. It does
not change Part I context selection, token counting, or artifact authority.

## User Override Boundary

O1 allows only small pure overrides that return a new immutable profile:

- `preferred_context_variant`
- `max_recommended_files`

O1 does not persist user settings, read `~/.strata/settings.json`, or allow
users to override internal reliability claims.

## Token-Firewall Boundary

Part I remains the token firewall. It alone decides what enters canonical
context artifacts such as:

- `.aidc/context/strata_context.md`
- `.aidc/context/context_pack.json`
- `.aidc/context/run_state.json`

O1 does not increase default context size, mutate context packs, allocate
tokens, or render prompts.

## Diagnostic Boundary

Part M owns workflow state, diagnostics, explanations, status summaries, and
recovery artifacts. O1 uses ordinary constructor and lookup validation with
`ValueError` for invalid profile inputs. Later Part O workflow failures should
reuse Part M diagnostics rather than creating a competing failure format.

## Explicit Non-Goals

O1 does not call models.

O1 does not render prompts.

O1 does not select delivery surfaces.

O1 does not persist user settings.

O1 does not add provider registries, model-name mappings, API calls, API keys,
pricing data, latency policy, retry behavior, response parsing, telemetry, or
background services.

## Context Pack Rendering Layer

O2 renders approved canonical context for different model capability profiles.
It defines three rendering variants:

- `compact`
- `balanced`
- `expanded`

Profile-driven selection uses O1 `preferred_context_variant` values:

- `weak` -> `compact`
- `medium` -> `balanced`
- `strong` -> `expanded`
- `unknown` -> `balanced`

Unknown remains conservative and never silently receives expanded output.

O2 renders approved canonical context. O2 does not discover new evidence. O2
does not change Part I budgets. O2 does not write canonical context artifacts.
O2 does not call models. O2 does not implement delivery adapters. Part I
remains the token firewall.

## Rendering Behavior

Compact rendering is for weak or small models. It prefers explicit instructions,
fewer files, path plus role, concise summaries, selected symbols, and omission
metadata. It does not include full file contents.

Balanced rendering is the default for medium and unknown capability. It includes
top relevant files, concise summaries, selected symbols or outlines when already
approved, bounded relationships, clear task instructions, and omission metadata.

Expanded rendering is for strong capability. It may preserve richer approved
file evidence such as excerpts or whole-file content when Part I already
approved that representation. Expanded remains bounded by Part I evidence, Part
L scale principles, and the O1 profile file limit.

## File and Relationship Limits

O2 selects rendered files deterministically from canonical approved items. It
uses existing priority and score evidence where present, falls back to path
tie-breaking, and respects `max_recommended_files`. Compact uses a stricter
file cap for concise rendering.

Relationships are rendered only from approved canonical relationship evidence.
They are sorted deterministically, exactly deduplicated, and capped by variant:
compact is smaller than balanced, and balanced is smaller than expanded.

## Representation Downgrade Only

O2 may downgrade how approved evidence is displayed, such as full content to
summary, summary to symbols or outline, or outline to path-only. O2 never
upgrades evidence beyond the representation approved by Part I.

Path-only items remain path-only. Skipped items do not become rendered content;
they are represented only through omission metadata.

## Omission and Budget Metadata

O2 returns bounded omission metadata for file limits, relationship limits,
representation downgrades, and unsupported optional item shapes. It does not
expose full omitted content or long omitted file lists.

O2 reuses canonical Part I budget summary fields as metadata. It does not
recalculate token budgets, claim exact rendered token counts, or create a second
budget authority.

## Markdown Rendering

O2 provides a deterministic pure Markdown renderer for rendered context packs.
The Markdown contains task, instructions, approved files, relationships, budget
metadata, and omitted evidence.

The Markdown renderer does not print, write files, detect terminal width, emit
ANSI output, call models, or use provider-specific formatting.

## Prompt Boundary

O2 is not the prompt template system. It does not create prompt template files,
include unified-diff examples, select delivery surfaces, parse AI responses,
retry model calls, or persist settings. O3 owns prompt templates.

## Prompt Template System

O3 consumes O2 rendered context and turns it into deterministic model-facing
prompts. O3 does not discover or add evidence. O3 does not change Part I
budgets. O3 does not call AI models. O3 does not validate AI responses. O3
does not implement delivery adapters. Part I remains the token firewall.

O3 defines trusted built-in prompt templates in Strata code. Repository
configuration cannot rewrite trusted safety text, and O3 does not load remote
templates, execute template code, use template inheritance, or add a templating
dependency.

## Template IDs and Versions

O3 uses stable capability-based template IDs:

- `weak_patch`
- `medium_patch`
- `strong_patch`
- `unknown_patch`

The prompt-template schema version is `1`, and each built-in template records a
stable template version of `1`.

Template selection is capability-tier based:

- `weak` -> `weak_patch`
- `medium` -> `medium_patch`
- `strong` -> `strong_patch`
- `unknown` -> `unknown_patch`

Unknown is conservative and never silently selects the strong template. Template
selection does not inspect model names, providers, delivery surfaces,
environment variables, or adapter configuration.

## Template Behavior

Weak prompts are explicit and procedural. They include step-by-step guidance,
scope boundaries, approved-evidence rules, a unified-diff requirement, and a
small static synthetic unified-diff example.

Unknown prompts are conservative. They include explicit scope and safety rules,
the unified-diff requirement, insufficient-evidence guidance, and the same small
static synthetic diff example.

Medium prompts are the default. They include the task, O2 rendered context,
scope boundaries, concise safety rules, and a unified-diff requirement without a
diff example.

Strong prompts are shorter but still safe. They keep approved-context scope,
repository-relative unified-diff output, no invented files, and no out-of-scope
changes.

## Variables and Placeholder Safety

O3 allows only this bounded variable vocabulary:

- `task`
- `rendered_context`
- `approved_file_count`
- `relationship_count`
- `omission_count`
- `profile_tier`
- `context_variant`

Template substitution is simple and explicit. Missing required variables,
unsupported variables, unsupported placeholders, and unresolved placeholders
raise `ValueError`. O3 does not use `eval`, execute expressions, or silently
accept arbitrary variable names.

## Section Ordering and Metadata

Prompt sections render in deterministic order:

1. role / purpose
2. task
3. instructions
4. approved context
5. scope
6. output format
7. safety
8. diff example, only for weak and unknown templates

O3 inserts O2 rendered context through the O2 Markdown renderer so it does not
create a second context serializer.

Prompt metadata is compact and deterministic. It records approved file count,
relationship count, omission count, whether a diff example is included, whether
explicit steps are needed, static instruction character count, rendered context
character count, and prompt character count. These are character counts only;
O3 does not claim exact token counts or create a second token-budget authority.

## Prompt Safety Boundary

All built-in templates require valid unified-diff output with repository-relative
paths. The response must modify only approved files unless an allowed related or
new file is explicitly listed in the supplied context. O3 tells the model not to
mix Markdown explanation into the diff because response validation belongs to
O4.

O3 does not parse AI responses, validate patches, retry failed responses, create
browser-copy files, pipe to CLI commands, add VS Code adapters, create sessions,
persist settings, add provider registries, map model names, or include API keys.

## AI Response Validation and Recovery

O4 validates AI-generated patch responses before any review or application
step. It accepts raw response text plus explicit approved scope lists and
returns a deterministic JSON-ready validation result.

The validation result records:

- `status`
- `is_valid`
- `failure_types`
- `diagnostics`
- `patch`
- `target_files`
- `change_summary`
- `retry`
- `metadata`

Accepted responses use `accepted_for_review`. This means the response is
structurally valid, inside scope, and ready for human or workflow review. It
does not mean the patch is approved, applied, or safe to merge.

O4 uses this bounded failure vocabulary:

- `empty_response`
- `no_diff`
- `malformed_diff`
- `out_of_scope_files`
- `blocked_new_files`
- `unsafe_path`
- `excessive_changes`
- `injection_detected`

Malformed arguments raise `ValueError`. Ordinary invalid AI responses return
structured validation results with Part M diagnostic events.

## Response Scope and Limits

O4 reuses the existing patch validator for unified-diff structure and unsafe
path checks. Paths must remain repository-relative. Absolute paths, parent
traversal, forbidden repository metadata, and dangerous path targets are
reported as `unsafe_path`.

Existing file targets must be in the approved files or expected related files
provided by the caller. New file targets must be explicitly listed as allowed
new files. Out-of-scope existing changes report `out_of_scope_files`, while
unapproved creations report `blocked_new_files`.

O4 also enforces bounded response size by file count and total changed lines.
Responses above those limits report `excessive_changes`.

## Suspicious Instruction Detection

O4 scans prose-like response text outside diff header and changed-line syntax
for a small suspicious-instruction vocabulary. Matches such as attempts to
ignore approved scope, bypass review, force apply, or reveal prompts report
`injection_detected`.

Suspicious instruction detection is conservative and response-local. It does
not inspect the filesystem, call models, use providers, or infer user intent
outside the supplied response text.

## Retry Boundary

O4 may recommend one retry for correctable response-shape failures:

- `no_diff`
- `malformed_diff`
- `out_of_scope_files`
- `blocked_new_files`
- `excessive_changes`

Retries are not recommended for `empty_response`, `unsafe_path`, or
`injection_detected`. O4 only returns retry guidance. It does not perform the
retry, call an AI model, or redesign the workflow loop.

## O4 Boundaries

O4 does not apply patches.

O4 does not approve patches.

O4 does not call models or delivery adapters.

O4 does not create browser-copy files, pipe responses to CLI commands, add VS
Code adapters, create sessions, persist settings, map model names, or add
provider registries.

Part I remains the token firewall. O4 validates responses against caller-supplied
scope; it does not expand canonical context, discover new evidence, alter token
budgets, or mutate Part I artifacts.

## Delivery Surface Adapters

O5 packages an existing O3 prompt for user-facing delivery surfaces. It answers
how the same trusted Strata prompt should be presented to a consuming surface;
it does not create or change the prompt.

O5 supports exactly these delivery surfaces:

- `browser_copy`
- `cli`
- `vscode`

Surfaces describe transfer behavior only. They do not identify model brands,
providers, chats, terminals, editors, or exact runtime integrations.

## Delivery Payload Contract

O5 returns a deterministic JSON-ready payload with these fields:

- `schema_version`
- `surface`
- `content_type`
- `prompt`
- `instructions`
- `metadata`

The payload metadata copies compact O3 prompt facts:

- `template_id`
- `template_version`
- `profile_tier`
- `context_variant`
- `prompt_character_count`
- `manual_transfer_required`

The `vscode` surface also includes `display_title` with the value `Strata patch
request`.

## Prompt Integrity

O5 preserves `prompt_result["prompt"]` exactly as the payload `prompt`. It does
not prepend, append, wrap, escape, normalize, shorten, or duplicate the prompt.
Surface instructions stay in the separate `instructions` collection.

O3 remains the authority for model-facing task, scope, safety, and unified-diff
instructions. O5 instructions describe only how to transfer the prompt and
return the response.

## Surface Behavior

`browser_copy` uses `text/plain`, marks `manual_transfer_required` as true, and
provides concise manual copy, submit, and response-return instructions. It does
not access the clipboard, open browser tabs, create HTML, identify browsers, or
identify models.

`cli` uses `text/plain`, marks `manual_transfer_required` as false, and provides
adapter-neutral instructions to send the complete prompt, capture the complete
response, and pass the response to Strata validation. It does not execute
subprocesses, construct provider-specific commands, create shell scripts,
inspect environment variables, or store API keys.

`vscode` uses `application/vnd.strata.prompt+json`, marks
`manual_transfer_required` as false, and includes small metadata useful to a
future editor UI. It does not import VS Code APIs, create extension files, add
TypeScript, read the active editor, inspect workspace files, send editor
messages, or implement a side panel.

## O5 Boundaries

O5 does not call models.

O5 does not validate responses.

O5 does not apply patches.

O5 does not implement real browser, CLI-provider, or VS Code integrations.

O5 does not write session state, persist settings, add provider registries,
detect model names, add API keys, access the network, emit telemetry, or run
background services.

## Multi-Turn Session State

O6 tracks one bounded AI patch interaction after an O3 prompt and O5 delivery
payload have been prepared. It preserves continuity across prompt preparation,
delivery, response receipt, response validation, one optional retry, terminal
acceptance or rejection, and explicit closure.

O6 uses these session statuses:

- `prepared`
- `delivered`
- `response_received`
- `retry_ready`
- `accepted_for_review`
- `rejected`
- `closed`

The caller supplies the `session_id`. O6 does not generate timestamps, random
IDs, UUIDs, or persistent session filenames.

## Session Contract

O6 returns a deterministic JSON-ready state mapping with these fields:

- `schema_version`
- `session_id`
- `status`
- `task`
- `profile_tier`
- `surface`
- `template_id`
- `template_version`
- `context_variant`
- `turn_count`
- `retry_count`
- `max_retries`
- `turns`
- `latest_validation`
- `closed_reason`
- `metadata`

The state stores compact prompt and delivery metadata such as prompt character
count, delivery surface, and whether manual transfer is required. It does not
store the complete prompt.

## Transition Rules

O6 allows only these state transitions:

- `prepared` -> `delivered`
- `delivered` -> `response_received`
- `retry_ready` -> `response_received`
- `response_received` -> `accepted_for_review`
- `response_received` -> `retry_ready`
- `response_received` -> `rejected`
- `accepted_for_review` -> `closed`
- `rejected` -> `closed`

Invalid transitions raise `ValueError`. O6 does not silently repair invalid
state, reset counters, or move directly from validation to `closed`.

## Retry And History Bounds

O6 supports only `max_retries` values of `0` or `1`. With one retry enabled, a
session can contain at most two response turns.

Each turn stores only:

- turn number
- response character count
- validation status
- failure types
- retry allowed flag

O6 does not store response text. It appends a retry turn only when a second
response is actually recorded. A retry recommendation after the retry limit is
exhausted transitions to `rejected`.

## Validation Summary Boundary

O6 accepts compact O4-style validation result mappings but does not import O4 or
perform response validation. It reads only validation status, validity,
failure types, retry metadata, change summary, and target files.

The latest validation summary omits full patch text, full diagnostics, complete
AI responses, and complete prompts. Target-file summaries are deterministic and
bounded, with a count and truncation flag when needed.

## Part M Boundary

Part M remains the authority for general Strata workflow state, diagnostics,
explanations, status summaries, and recovery artifacts. O6 tracks AI interaction
turns within a run only.

O6 does not replace Part M workflow state.

O6 does not modify canonical `.aidc/context/run_state.json`.

O6 does not create another canonical repository-run artifact.

O6 does not persist sessions yet.

## O6 Boundaries

O6 does not call models.

O6 does not deliver prompts.

O6 does not validate or apply patches.

O6 does not regenerate prompts or perform automatic retries.

O6 does not add command wiring, session files, databases, settings persistence,
provider or model detection, API keys, telemetry, or background services.

## User Settings and Capability Override

O7 defines a pure JSON-ready user-settings contract for capability selection,
delivery-surface preference, and the bounded profile overrides supported by O1.
It does not read, write, or persist settings.

O7 supports this capability-selection vocabulary:

- `auto`
- `unknown`
- `weak`
- `medium`
- `strong`

`auto` uses a caller-supplied detected capability tier when one is available.
If the caller cannot supply a reliable detected tier, `auto` resolves to the
conservative unknown profile. An explicitly detected `unknown` tier resolves to
unknown with selection source `detected`.

Manual selections `unknown`, `weak`, `medium`, and `strong` always use that
tier and ignore any caller-supplied detected tier.

## Settings Contract

O7 settings contain:

- `schema_version`
- `capability_selection`
- `delivery_surface`
- `profile_overrides`

The default settings use `auto`, the conservative `browser_copy` delivery
surface, and an empty override mapping. `browser_copy` is the default because it
is the safest existing O5 surface: it requires manual transfer and no runtime
integration.

Settings can be changed after initial setup through pure update helpers.
Partial updates preserve unchanged fields. A supplied `profile_overrides`
mapping replaces the previous override mapping completely, so `{}` clears prior
overrides.

## Capability Resolution

O7 returns a deterministic capability-resolution result with:

- `selected_tier`
- `selection_source`
- `profile`
- `profile_overrides_applied`
- `metadata`

Selection sources are:

- `manual`
- `detected`
- `unknown_fallback`

O7 reuses O1 built-in profiles, the conservative unknown profile, O1 profile
serialization, and O1 override validation. It applies overrides only after the
base profile is selected.

Supported profile overrides remain exactly the bounded O1 override surface:

- `preferred_context_variant`
- `max_recommended_files`

O7 does not permit capability-tier overrides, provider or model names, file
limits above O1 bounds, or unknown override fields.

## Delivery Preference Boundary

O7 validates the stored delivery surface against the O5 vocabulary:

- `browser_copy`
- `cli`
- `vscode`

O7 stores only the preference. It does not build delivery payloads, send
prompts, access clipboards, launch browsers, inspect CLIs, or call VS Code APIs.

## O7 Boundaries

O7 does not detect model brands.

O7 does not inspect browser, CLI, or VS Code state.

O7 does not store secrets, API keys, tokens, passwords, credentials, user-home
paths, or environment-variable values.

O7 does not persist settings yet.

O7 does not add command or onboarding wiring.

O7 does not call models, execute delivery, validate responses, persist
sessions, apply patches, add telemetry, or run background services.

## Part O Completion Summary

Part O now provides the adapter and AI workflow-control foundations:

- O1 defines capability profiles and bounded profile overrides.
- O2 renders approved context by capability profile.
- O3 builds trusted versioned prompts.
- O4 validates AI responses in the patch layer.
- O5 packages prompts for delivery surfaces.
- O6 tracks bounded in-memory AI interaction state.
- O7 defines pure user settings for capability and delivery preferences.

These foundations remain deliberately non-invasive. They do not call models,
detect providers, persist sessions or settings, apply patches, replace Part I
context authority, or replace Part M workflow-state diagnostics.
