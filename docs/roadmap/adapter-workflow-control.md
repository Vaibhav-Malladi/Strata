# Adapter and AI Workflow Control

Part O defines the adapter and AI workflow control foundations that sit after
the canonical context and workflow-state contracts. Its purpose is to let
Strata shape future AI workflow guidance from capability-first data while
preserving Part I as the token firewall and reusing Part M diagnostics for
workflow failures.

## Batch Status

- O1 - Capability Profile Foundation - implemented.
- O2 - Context Pack Rendering Layer - not implemented.
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
