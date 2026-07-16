# User Flow/Journey Intelligence

Part P defines how Strata will explain a complete user-facing action across
frontend, backend, data, external, and cross-repository boundaries.

Workspace Intelligence comes first because a journey often leaves one
repository. Part Q supplies repository IDs, repository roles, cross-repository
reference evidence, shared-contract findings, dependency graph identities, and
workspace readiness. Part P can attach those identities without making a
workspace graph mandatory for single-repository journeys.

## P1 - Journey Contracts And Foundations

P1 introduces stable, JSON-ready contracts for user journey data. It is the
foundation future batches will populate; it does not discover or trace journeys.

The `JourneyRequest` contract records the user action being traced. It preserves
the original task, rejects empty tasks, normalizes starting repository IDs and
relative paths, exposes compact deterministic task keywords, and can carry
optional route, UI, symbol, path, and destination hints.

Journey entry points describe where a user-facing action begins. They use a
bounded entry-point type vocabulary such as `ui_event`, `route`, `component`,
`button`, `message_event`, `api_request`, `explicit_symbol`,
`explicit_path`, and `unknown`. Each entry point records repository, path,
optional symbol, label, origin, confidence, bounded evidence, and metadata.

Journey steps describe meaningful stages of an action. P1 defines bounded step
types for user actions, frontend handlers and services, API clients and
requests, workspace boundaries, backend routes and handlers, authentication,
authorization, validation, business logic, data access, queues, external
services, iframe and message events, responses, frontend completion, rendering,
and unknown stages. Step IDs are deterministic and based on repository, path,
symbol, step type, and an optional semantic discriminator.

P1 also defines high-level phases so long journeys can be summarized without
duplicating phase mappings. Canonical phase derivation maps examples such as
`user_action` to `entry`, `component_method` to `frontend`, `api_request` to
`boundary`, `backend_handler` to `backend`, `database_access` to `data`,
`external_service` to `external`, `response` to `response`, and
`frontend_update` to `frontend_completion`.

Transitions connect steps with a directed relationship. The bounded transition
vocabulary includes calls, handlers, route transitions, imports, dispatches,
state reads and writes, API requests and responses, navigation, rendering,
message sends and receives, embeds, cross-repository crossings, inferred links,
and unknown links. Transitions can attach Part Q relationship types, workspace
graph edge identities, and shared-contract names when those are already known.

Gaps record unresolved parts of the trace. P1 keeps gaps separate from confirmed
steps or transitions. Gap reasons include missing entry points or symbols,
unknown target repositories or paths, unresolved dynamic calls, runtime routes,
dependencies, ambiguous API or message targets, unresolved framework bindings,
external boundaries, cap exhaustion, unsupported languages or patterns,
unreadable or skipped sources, and unknown causes.

Confidence uses the established `low`, `medium`, and `high` labels with scores
from `0.0` to `1.0`. P1 validates confidence only. It does not calculate
framework-specific confidence, use embeddings, or call a model.

Evidence follows Part Q conventions where architecture permits. Journey
evidence records signal type, repository ID, normalized path, concise redacted
summary, strength, optional symbol and line number, optional related repository
and path, and deterministic metadata. Evidence is deduplicated, sorted, capped,
and redacted for obvious credential-like keys and values.

The top-level result includes schema version, request, entry points, steps,
transitions, gaps, diagnostics, summary, readiness, and metadata. Readiness
values are `complete`, `partial`, `blocked`, `not_found`, and `unsupported`.
The summary counts entries, steps, transitions, repositories, cross-repository
transitions, gaps, confidence buckets, and key phases.

P1 enforces conservative bounds:

- maximum entry points: 20
- maximum journey steps: 150
- maximum transitions: 300
- maximum gaps: 100
- maximum diagnostics: 200
- maximum evidence per entry point, step, transition, or gap: 8

When caps are reached, P1 truncates deterministically, emits diagnostics, and
records omitted counts in result metadata.

Deterministic identities are part of the contract. Entry points use repository,
path, symbol, and type. Steps use repository, path, symbol, step type, and an
optional semantic discriminator. Transitions use source step ID, target step ID,
and transition type. Gaps use reason, source step ID, repository, path, and
symbol. Exact duplicates deduplicate; conflicting records sharing an identity
produce diagnostics rather than silently overwriting the first record.

P1 supports both single-repository and cross-repository results. A workspace
graph is not required. When Workspace Intelligence has already produced graph
node IDs, graph edge IDs, relationship types, or shared-contract names, the
journey contracts can attach them as optional identifiers.

P1 does not:

- scan files
- detect UI entry points
- extract Angular or React events
- extract HTML buttons
- extract routes
- trace frontend calls
- resolve API requests
- trace backend handlers
- inspect databases or sessions
- traverse workspace graphs
- rank journeys
- add journey data to AI context
- add CLI commands or guided workflow integration

## Planned Batch Sequence

P1 defines contracts, deterministic identities, bounds, diagnostics, summaries,
confidence, and evidence foundations.

P2 will add entry-point candidate extraction for supported frontend surfaces.

P3 will trace frontend event handlers, component methods, services, state
updates, routes, API clients, iframe sends, and message sends.

P4 will connect frontend boundaries to backend routes and workspace
relationships using Part Q evidence.

P5 will trace backend route handlers through services, authorization,
validation, business logic, persistence, queues, and external services.

P6 will resolve responses back through frontend completion, navigation, render,
message receive, and iframe receive stages.

P7 will integrate journey results with context budgeting and selection without
weakening existing token, path, symlink, dirty-tree, scope, and apply safety
protections.

P8 will add user-facing presentation, diagnostics explanations, and guided
workflow surfaces after the journey contracts and tracing behavior are stable.

Part P is not complete after P1. P1 only establishes the contracts future
batches will populate.
