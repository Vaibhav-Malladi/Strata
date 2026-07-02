# Frontend Intelligence Documentation and Role Taxonomy

## Goal

Frontend intelligence will give Strata a bounded, explainable way to identify and connect useful React and Angular evidence. Every analysis step must earn its cost, with cheap path-derived signals preceding any future content-aware work.

## Current Scope

This branch establishes a dependency-light frontend role taxonomy and path-only helpers for identifying likely frontend candidates. The taxonomy includes pages, components, templates, styles, hooks, services, API clients, routes, state stores, forms, tests, configuration, assets, and unknown files. Recognized frontend roles are connected to candidate scoring as a cheap, bounded signal: direct task-role matches receive a stronger boost than broader frontend-task relevance, and every boost includes an inspectable reason.

A React starting-file selector now builds on inventory metadata and cheap candidate scores. It returns a deterministic, bounded set of likely task entry points with roles, scores, confidence labels, and inspectable reasons. Generated and vendor records are excluded, while tests are eligible only when the task explicitly requests tests. Selection remains path-only and does not trace relationships between files.

An Angular starting-file selector applies the same bounded contract to component, template, style, service, guard, interceptor, route, module, pipe, and directive conventions. It uses filename suffixes, folders, shared frontend roles, and task text only. It does not read source content or connect related Angular files.

A normalized frontend starting-file pipeline runs explicitly enabled React and Angular selectors over one materialized inventory. It merges their bounded results, deduplicates paths, retains the stronger framework score with an inspectable note, and returns selection metadata including frameworks considered, files considered, limit, and truncation state. An `auto` mode resolves the enabled selectors through path-only framework detection; no detected framework produces an empty selection without fallback scanning.

Structured starting-file summaries preserve resolved framework and selection metadata while exposing a configurable number of top files with capped reasons. Summary generation is a deterministic projection of an existing selection and performs no repository work.

Frontend framework detection now identifies likely React and Angular repositories from inventory paths, conventional filenames, extensions, and configuration filenames. Evidence categories are counted once, reasons are capped, and confidence remains deterministic. The detector does not read `package.json` or any other file content and is connected to starting-file selection only when callers explicitly request `auto` mode.

Role inference is approximate by design. It uses normalized path segments, filenames, naming conventions, and extensions without reading file contents. Angular guards and resolvers are classified as services because they provide injectable application behavior; future route analysis may attach route relationships separately.

## Planned Milestones

1. Establish path-derived React and Angular role detection.
2. Establish bounded React starting-file selection using explainable path and task signals.
3. Establish bounded Angular starting-file selection using explainable path and task signals.
4. Normalize React and Angular starting-file results through a bounded frontend pipeline.
5. Detect likely React and Angular frameworks from bounded inventory signals.
6. Resolve starting-file selectors from detected frameworks when explicitly requested.
7. Provide bounded structured reporting for frontend starting-file selections.
8. Link React components, hooks, and API clients through lightweight evidence.
9. Link Angular components with templates and styles, then add service, module, and route awareness.
10. Extract frontend event bindings with explicit limits and inspectable evidence.

Each milestone should remain independently testable and should introduce deeper analysis only when cheaper signals are insufficient.

## Safety Constraints

- Role taxonomy helpers use path, filename, and extension signals only.
- Taxonomy inference does not open, read, or stat files.
- The foundation does not require a TypeScript compiler API, language server, parser stack, AST dependency, or other heavy dependency.
- Heuristics are deterministic, approximate, and clearly described as path-derived.
- Future analysis must be lazy, bounded, explainable, and dependency-light.
- Framework-specific work must preserve core-layer dependency direction and avoid implicit integration side effects.

## Deferred Capabilities

This branch intentionally does not enable automatic selector choice unless a caller requests `auto` mode and does not add React or Angular component and template linking, hook or service linking, dependency injection analysis, import or route tracing, event binding extraction, content parsing, or framework graph construction. Beyond cheap candidate scoring, bounded starting-file selection, and path-only framework detection, it does not integrate frontend intelligence with scanners, CLI commands, context packs, caches, tracing, adapters, patch workflows, or the representation ladder.

## Validation

From the repository root, run the focused taxonomy, framework, architecture, and pipeline tests:

```powershell
..\.codex-venv\Scripts\python.exe -c "from tests import test_candidate_architecture, test_frontend_frameworks, test_frontend_roles, test_frontend_starting_files; [test() for module in (test_candidate_architecture, test_frontend_frameworks, test_frontend_roles, test_frontend_starting_files) for test in module.TESTS]"
```

The focused suites are also registered with the project's custom test runner for later full validation.

## Risks and Follow-Ups

Path-derived conventions can misclassify unconventional repositories and cannot prove framework semantics. Future milestones should retain `unknown` as a safe outcome, attach reasons to richer classifications, measure false positives against representative React and Angular layouts, and define strict work budgets before reading content. Framework linking will require explicit precedence rules for barrel exports, aliases, generated files, colocated tests, Angular standalone components, and route-level lazy loading.
