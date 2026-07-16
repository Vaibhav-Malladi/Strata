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

P2 adds selected-file entry-point candidate extraction for supported frontend
surfaces.

P3 adds selected-file frontend tracing for event handlers, component methods,
service-like calls, state updates, navigation, and API request steps.

P4 adds selected-file frontend-to-backend API boundary linking using backend
route extraction and optional Part Q relationship evidence.

P5 will trace backend route handlers through services, authorization,
validation, business logic, persistence, queues, and external services.

P6 will resolve responses back through frontend completion, navigation, render,
message receive, and iframe receive stages.

P7 will integrate journey results with context budgeting and selection without
weakening existing token, path, symlink, dirty-tree, scope, and apply safety
protections.

P8 will add user-facing presentation, diagnostics explanations, and guided
workflow surfaces after the journey contracts and tracing behavior are stable.

Part P is not complete after Mega Batch A. P1-P4 establish contracts,
selected-file entry detection, selected-file frontend tracing, and selected-file
API boundary linking; later batches still need backend trace depth, context
integration, ranking, and user-facing presentation.

## P2 - User-Action Entry-Point Detection

P2 detects likely journey starting points from explicitly selected frontend
files. The caller supplies repository ID, repository root, and selected paths;
P2 does not choose files automatically and does not recursively scan a
repository.

Supported selected file types are HTML, Angular templates, JavaScript,
TypeScript, JSX, TSX, and JSON. P2 looks for lightweight static signals:

- button and link text
- form submit bindings
- Angular `(click)`, `(submit)`, and keyboard handlers
- `routerLink` and `href` route hints
- React `onClick`, `onSubmit`, `onChange`, and keyboard handlers
- JSX route declarations
- named and exported JS/TS symbols
- message event listeners and senders
- explicit request paths, symbols, route hints, and UI hints

Matching is deterministic and lexical. Exact explicit symbols, selected paths,
UI labels, and route hints outrank handler-name and keyword overlap. Dynamic
template bindings are reported as diagnostics rather than resolved
speculatively.

P2 reads only bounded selected files, skips symlinks, rejects paths outside the
repository root, caps file count and bytes per file, redacts concise evidence,
and emits P1-compatible `JourneyEntryPoint` records.

## P3 - Frontend Flow Tracing

P3 traces frontend flow from supplied P2 entry points through explicitly
selected frontend files. It produces a P1 `UserJourneyResult` with frontend
steps, directed transitions, gaps, diagnostics, and deterministic summaries.

Supported lightweight relationships include:

- Angular template event binding to component method
- component method to local or service-like function
- service function to `HttpClient` request
- React event handler to local function
- handler to API helper, `fetch`, axios-like call, or `HttpClient`
- state setter and `dispatch` updates
- simple navigation calls
- direct JS/TS function calls

P3 does not execute hooks, infer runtime component trees, implement full Angular
dependency injection, resolve arbitrary imports, or trace backend logic.
Computed calls and unresolved symbols become safe gaps such as
`dynamic_call_unresolved`, `symbol_not_found`, or `step_cap_reached`.

Default bounds keep tracing conservative: selected files only, 512 KB per file,
100 steps, 200 transitions, trace depth 8, and 12 outgoing links per step.

## P4 - Frontend-To-Backend API Boundary Linking

P4 links frontend API request steps to likely backend routes from explicitly
selected backend files or already supplied route-like data. It consumes P3
steps and transitions, optional Part Q workspace graph data, known backend
URLs, and known backend ports. It does not run workspace discovery or scan
backend repositories broadly.

Frontend request extraction uses P3 API request metadata when available,
including literal HTTP method, URL, and normalized route path from `fetch`,
axios-like calls, Angular `HttpClient`, and simple API helper methods.

Backend route extraction is selected-file only and supports:

- Python FastAPI and Flask-style decorators
- simple Django `path(...)` declarations
- Go `http.HandleFunc` and common router method/path registrations
- Express-style `app.get/post/put/delete/patch` and `router.*` declarations

Route matching uses HTTP method, normalized route path, parameterized route
segments, known backend URLs, known ports, and optional Part Q `calls_api`
workspace graph edges. Exact method and route matches are strongest.
Parameterized route matches are degraded and diagnosed. Ambiguous routes,
unknown targets, mismatched ports, or missing backend routes become diagnostics
and gaps instead of speculative cross-repository edges.

When a match is strong enough, P4 adds an `api_request` continuation,
`workspace_boundary` step, `backend_route` step, and cross-repository
transitions such as `sends_request`, `crosses_repository`, `routes_to`, and
`receives_request`. The boundary transitions attach the Part Q `calls_api`
relationship type where appropriate.

Mega Batch A still does not trace backend handlers and services beyond route
detection, trace database or session logic, assemble complete workspace
journeys, rank journey alternatives, integrate journeys with AI context
budgets, add CLI commands, or finish Part P.
