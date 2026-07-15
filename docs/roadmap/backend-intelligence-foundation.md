# Backend Intelligence Foundation

## Goal

The Backend Intelligence Foundation gives Strata a stable, deterministic way to describe backend route and service relationships before any framework-specific discovery exists. Part I remains the canonical context artifact and token firewall layer; backend findings defined here are only raw relationship contracts until later context code chooses how to present them.

## K1 Scope

K1 is contract-only. It defines stable constants, JSON-ready relationship fields, deterministic ordering, and simple grouping helpers for backend route/service relationships.

K1 does not implement framework detection or extraction, does not scan repositories, does not read source files, does not parse package manifests, and does not integrate backend findings into canonical context artifacts.

## Contract

The contract can represent Python and JavaScript/TypeScript backend relationships across FastAPI, Flask, Django, Django REST Framework, Express, NestJS, generic backends, and unknown frameworks.

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
5. K5 Django/DRF.
6. K6 Express.
7. K7 NestJS.
8. K8 Backend evaluation/docs.

## Validation

From the repository root, run:

```powershell
py tests.py
py tests\run.py
```

The K1 contract tests lock stable constants, JSON-ready output, confidence vocabulary, deterministic ordering, deterministic grouping, and the absence of framework parser/scanner/detector APIs.
