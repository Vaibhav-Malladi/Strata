# Frontend Intelligence Documentation and Role Taxonomy

## Goal

Frontend intelligence will give Strata a bounded, explainable way to identify and connect useful React and Angular evidence. Every analysis step must earn its cost, with cheap path-derived signals preceding any future content-aware work.

## Current Scope

This branch establishes a dependency-light frontend role taxonomy and path-only helpers for identifying likely frontend candidates. The taxonomy includes pages, components, templates, styles, hooks, services, API clients, routes, state stores, forms, tests, configuration, assets, and unknown files.

Role inference is approximate by design. It uses normalized path segments, filenames, naming conventions, and extensions without reading file contents. Angular guards and resolvers are classified as services because they provide injectable application behavior; future route analysis may attach route relationships separately.

## Planned Milestones

1. Establish path-derived React and Angular role detection.
2. Add bounded starting-file selection using explainable relevance and cost signals.
3. Link React components, hooks, and API clients through lightweight evidence.
4. Link Angular components with templates and styles, then add service, module, and route awareness.
5. Extract frontend event bindings with explicit limits and inspectable evidence.

Each milestone should remain independently testable and should introduce deeper analysis only when cheaper signals are insufficient.

## Safety Constraints

- Role taxonomy helpers use path, filename, and extension signals only.
- Taxonomy inference does not open, read, or stat files.
- The foundation does not require a TypeScript compiler API, language server, parser stack, AST dependency, or other heavy dependency.
- Heuristics are deterministic, approximate, and clearly described as path-derived.
- Future analysis must be lazy, bounded, explainable, and dependency-light.
- Framework-specific work must preserve core-layer dependency direction and avoid implicit integration side effects.

## Deferred Capabilities

This branch intentionally does not add React or Angular starting-file selection, component or template linking, route tracing, event binding extraction, content parsing, or framework graph construction. It also does not integrate frontend roles with scanners, CLI commands, context packs, candidate pipelines, caches, tracing, adapters, patch workflows, or the representation ladder.

## Validation

From the repository root, run only the focused taxonomy tests for this change:

```powershell
..\.codex-venv\Scripts\python.exe -c "from tests import test_frontend_roles as module; [test() for test in module.TESTS]"
```

The taxonomy suite is also registered with the project's custom test runner for later full validation.

## Risks and Follow-Ups

Path-derived conventions can misclassify unconventional repositories and cannot prove framework semantics. Future milestones should retain `unknown` as a safe outcome, attach reasons to richer classifications, measure false positives against representative React and Angular layouts, and define strict work budgets before reading content. Framework linking will require explicit precedence rules for barrel exports, aliases, generated files, colocated tests, Angular standalone components, and route-level lazy loading.
