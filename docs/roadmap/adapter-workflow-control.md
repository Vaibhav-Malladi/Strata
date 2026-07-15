# Adapter and AI Workflow Control

Part O defines the adapter and AI workflow control foundations that sit after
the canonical context and workflow-state contracts. Its purpose is to let
Strata shape future AI workflow guidance from capability-first data while
preserving Part I as the token firewall and reusing Part M diagnostics for
workflow failures.

## Batch Status

- O1 - Capability Profile Foundation - implemented.
- O2 - Context Pack Rendering Layer - implemented.
- O3 - Prompt Template System - not implemented.
- O4 - AI Response Validation and Recovery - not implemented.
- O5 - Delivery Surface Adapters - not implemented.
- O6 - Multi-turn Session State - not implemented.
- O7 - User Settings and Capability Override - not implemented.

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
