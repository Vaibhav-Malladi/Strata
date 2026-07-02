# Frontend Intelligence Foundation

## Goal

The frontend intelligence foundation gives Strata a bounded, deterministic, and explainable way to identify likely React and Angular evidence before any deeper analysis. Every analysis step must earn its cost, so inexpensive inventory and path signals precede future content-aware work.

## Final Scope

This branch delivers a dependency-light core foundation for frontend role inference, candidate relevance, framework detection, framework-specific starting-file selection, normalized selection, automatic framework resolution, and structured reporting. All behavior is driven by existing inventory metadata, paths, filenames, extensions, folder conventions, configuration filenames, and task text.

The foundation supports React and Angular independently and together in monorepos. Its classifications and confidence labels are intentionally approximate and retain inspectable reasons.

## Architecture

### Role Taxonomy

The shared role taxonomy classifies likely pages, components, templates, styles, hooks, services, API clients, routes, state stores, forms, tests, configuration files, assets, and unknown files. Inference uses normalized path, filename, and extension conventions only.

### Candidate Role Signals

Candidate scoring incorporates bounded frontend role signals when task vocabulary makes them relevant. Direct task-role matches receive a stronger boost than general frontend relevance. Existing generated, vendor, and test behavior remains authoritative, and each contribution is recorded as a human-readable reason.

### React Starting-File Selection

React selection ranks JavaScript and TypeScript candidates using existing candidate scores, React-oriented extensions, inferred roles, folder conventions, filenames, and task terms. Results are capped, deterministically ordered, and include roles, scores, confidence labels, and reasons. Generated and vendor paths are excluded; tests are eligible only for test-oriented tasks.

### Angular Starting-File Selection

Angular selection recognizes component, template, style, service, guard, interceptor, route, module, pipe, and directive conventions. It combines these filename patterns with shared roles, Angular-oriented folders, extensions, candidate scores, and task terms. It applies the same bounded, deterministic, generated-file, and test-file contracts as React selection.

### Frontend Framework Detection

Framework detection identifies likely React and Angular repositories from inventory paths and configuration filenames. Evidence categories are counted once to prevent repository size from inflating confidence, reporting reasons are capped, and React and Angular may both be detected. Strong configuration names outweigh generic extension signals.

### Normalized Starting-File Pipeline

The normalized pipeline materializes an inventory once, runs explicitly enabled selectors, merges results, deduplicates paths, and retains the stronger framework score with an inspectable note. The result reports resolved frameworks, files considered, selected files, the applied limit, and truncation state.

### Automatic Framework Mode

When callers explicitly request `auto` mode, the pipeline uses framework detection and runs only the resolved selectors. A repository with no detected framework returns a valid empty selection. Mixing `auto` with explicit framework names is rejected to keep semantics unambiguous.

### Summary and Reporting

Structured summaries preserve framework, count, limit, and truncation metadata while exposing configurable caps for top files and reasons per file. Summary generation is a pure projection of an existing selection and does not rescore or reorder files.

## Safety Guarantees

- Frontend intelligence uses path, filename, extension, folder, inventory, configuration-name, and task-text signals only.
- Role inference, framework detection, selectors, normalized pipelines, and summaries do not open, read, or stat repository paths.
- The foundation does not parse `package.json` or any other file content.
- No TypeScript compiler API, language server, AST stack, parser module, or heavy dependency is required.
- Selection limits and summary caps must be positive integers and are validated before work proceeds.
- Ordering and tie-breaking are deterministic, including Windows-style path handling.
- Generated, vendor, build, and minified files are demoted by candidate scoring or excluded by starting-file selectors.
- Test and specification files are excluded from ordinary starting-file selection and become eligible only for test-oriented tasks.
- Empty inventories and inventories without detected frameworks produce valid empty results.
- Frontend core modules remain isolated from CLI, scanner, context-pack, adapter, patch, cache, and tracing layers.

## Deferred Capabilities

This branch intentionally does not provide CLI or context-pack integration, React component and hook linking, Angular component-template-style linking, event binding extraction, import tracing, route tracing, dependency injection analysis, the representation ladder, persistent caching, parser integration, or backend analysis.

## Validation

From the repository root, run:

```powershell
py tests.py
py tests\run.py
strata gate
```

The frontend role, framework, selector, pipeline, summary, and architecture contract suites are registered with the project test runner.

## Follow-Up Milestones

1. Add bounded React component, hook, API-client, and state relationships with explicit evidence and work budgets.
2. Add bounded Angular component-template-style and service relationships without introducing mandatory compiler dependencies.
3. Add frontend event binding extraction with deterministic caps and source attribution.
4. Add import and route tracing only where cheaper signals cannot answer the task.
5. Evaluate supported CLI and context-pack presentation after core contracts and output formats stabilize.
6. Introduce caching or richer representations only when measured reuse justifies their cost.

## Risks

Path-derived conventions can misclassify unconventional repositories and cannot prove framework semantics. Future work should preserve `unknown` as a safe outcome, measure false positives against representative repositories, retain explicit content-read boundaries, and keep every deeper analysis step bounded and explainable.
