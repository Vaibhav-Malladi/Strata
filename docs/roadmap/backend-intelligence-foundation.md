# Backend Intelligence Foundation

## Goal

The Backend Intelligence Foundation gives Strata a stable, deterministic way to describe backend route and service relationships before any framework-specific discovery exists. Part I remains the canonical context artifact and token firewall layer; backend findings defined here are only raw relationship contracts until later context code chooses how to present them.

## K1 Scope

K1 is contract-only. It defines stable constants, JSON-ready relationship fields, deterministic ordering, and simple grouping helpers for backend route/service relationships.

K1 does not implement framework detection or extraction, does not scan repositories, does not read source files, does not parse package manifests, and does not integrate backend findings into canonical context artifacts.

## K2 Scope

K2 is common Python backend infrastructure only. It adds safe AST parsing for already-provided source text, decorator-name normalization, string-literal route path extraction, HTTP method normalization, Python function/class symbol candidates, source evidence helpers, and a conversion helper for explicit route facts supplied by later framework-specific producers.

K2 does not detect FastAPI, Flask, Django, or DRF routes. It does not scan repositories, read files, infer dynamic route strings, parse package manifests, or add framework-specific extraction APIs.

## K3 Scope

K3 covers FastAPI route extraction only, from supplied Python source text. It recognizes literal-path FastAPI-style method decorators and `api_route` method lists using the K2 AST helpers, then emits K1 `BackendRelationship` records.

K3 does not scan repositories, read files, import FastAPI, execute user code, infer dynamic route strings, or detect Flask, Django, or DRF routes. K4 Flask and K5 Django/DRF remain pending.

## K4 Scope

K4 covers Flask route extraction only, from supplied Python source text. It recognizes literal-path Flask app and Blueprint `.route` decorators, literal `methods` lists, and dotted Flask-style method shortcut decorators using the K2 AST helpers, then emits K1 `BackendRelationship` records.

K4 does not scan repositories, read files, import Flask, execute user code, infer dynamic route strings, or detect FastAPI, Django, or DRF routes. K5 Django/DRF remains pending.

## K5-K7 Scope

K5-K7 are implemented as a controlled source-text-only batch. K5 covers conservative Django URL patterns and DRF `api_view`/router hints from supplied Python source text. K6 covers literal Express app/router route calls and simple chained router routes from supplied JavaScript/TypeScript source text. K7 covers literal NestJS controller and HTTP method decorators from supplied TypeScript source text.

K5-K7 infer routes only from supplied source text. They do not scan repositories, read files, execute code, resolve imports, or require Django, DRF, Express, or NestJS to be installed. Cross-file route resolution, workspace linking, and frontend/backend journey linking remain future work. K8/K9 Go backend work remains pending, and K10 backend evaluation/docs remains pending.

## K8-K10 Scope

K8-K10 complete Part K. K8 adds a small Go backend common model for source-line handling, conservative function symbols, string literal extraction, handler symbols, explicit HTTP method evidence, and evidence strings. K9 adds Go HTTP/router route detection for standard library handlers, ServeMux-like calls, gorilla/mux-style method chains, and chi-style method calls from supplied source text only. K10 adds a data-only backend relationship summary for already-created `BackendRelationship` records.

Part K works from supplied source text only. It does not scan repositories, read files, execute code, resolve imports, perform cross-file route resolution, create context artifacts, implement workspace intelligence, or perform frontend/backend journey tracing. Go is included because it was explicitly reintroduced by product direction. Java and Rust remain out of scope.

Handoffs: L owns performance/cache hardening. M owns workflow state/diagnostics. Q owns workspace intelligence and cross-repo awareness. P owns user flow/journey intelligence and frontend-backend journey linking.

## Contract

The contract can represent Python, JavaScript/TypeScript, and Go backend relationships.

Backend scope includes:

- Python backend frameworks: FastAPI, Flask, Django/DRF.
- JavaScript/TypeScript backend frameworks: Express, NestJS.
- Go backend services: standard net/http and common router patterns later.
- Generic backend and unknown framework relationships when a later producer cannot classify the source more specifically.

Relationship records preserve:

- framework
- relationship type
- source and optional target path
- target, route, handler, service, and model symbols
- route path and HTTP method
- confidence
- evidence
- warnings
- reason

Confidence uses the shared vocabulary: `unknown`, `low`, `medium`, and `high`.

## Safety Guarantees

- K1 does not provide parser, scanner, detector, or extractor APIs.
- K1 does not perform filesystem traversal or file content reads.
- K1 does not parse `package.json`, `pyproject.toml`, or framework configuration.
- K1 does not perform frontend linking, user journey linking, workspace intelligence, model calls, internet calls, or daemon/background work.
- Ordering and grouping helpers are pure projections over already-created relationship objects.

## Roadmap

1. K1 Generic backend route/service contract.
2. K2 Python backend common model.
3. K3 FastAPI.
4. K4 Flask.
5. K5 Django/DRF - implemented.
6. K6 Express - implemented.
7. K7 NestJS - implemented.
8. K8 Go backend common model - implemented.
9. K9 Go HTTP/router detection - implemented.
10. K10 Backend evaluation/docs - implemented.

## Validation

From the repository root, run:

```powershell
py tests.py
py tests\run.py
```

The K1 contract tests lock stable constants, JSON-ready output, confidence vocabulary, deterministic ordering, deterministic grouping, and the absence of framework parser/scanner/detector APIs.
