# Cost-Based Repository Intelligence

## Goal

Strata's cost-based repository intelligence engine prioritizes useful repository evidence before paying for deeper analysis. Each stage must justify its cost using deterministic, inspectable signals and bounded outputs.

## Final Scope

This branch delivers a core-layer foundation that walks repository trees, inventories files from metadata, scores path-derived relevance, estimates relative analysis cost, selects bounded candidates, and produces structured summaries. It does not read file contents or alter existing integration surfaces.

## Completed Foundation

### Inventory Record Foundation

`InventoryRecord` captures relative path, extension, size, modification time, test and generated-file signals, folder role, and language guess. Creation uses filesystem metadata and path-derived classification without opening file contents.

### Cheap Path-Based Candidate Scoring

Cheap scoring compares normalized task terms with filenames, path segments, roles, languages, and extensions. Generated and vendor paths receive an explicit demotion. Every score retains human-readable reasons.

### Candidate Shortlist Foundation

The shortlist layer applies a validated top-K cap, preserves deterministic ordering and scoring reasons, and reports the number of files considered, candidates returned, cap used, and truncation state.

### Cost Model Foundation

The cost model estimates relative analysis expense from file size and existing test or generated-file signals. Value scores combine cheap relevance with estimated cost, favoring similarly relevant files that are cheaper to analyze.

### Inventory-to-Candidate Integration

The selection layer accepts inventory records and task text, applies value-aware ranking, and returns a bounded `CandidateSelection`. Generated, vendor, build, and minified files remain eligible but normally rank below relevant source files.

### Candidate Selection Summary

The summary layer converts a selection into bounded structured data suitable for future diagnostics. It includes selection metadata and a configurable number of top candidates with capped explanations.

### Repository Inventory and Candidate Pipeline

Repository inventory collection walks directories in deterministic order and creates `InventoryRecord` objects using path and stat metadata only. It prunes dependency trees, version-control metadata, caches, build outputs, and hidden paths by default, supports a validated file cap, and tolerates inaccessible entries.

The core pipeline connects bounded repository inventory collection to value-aware candidate selection and summary generation. Its result reports inventory and candidate limits, inventory truncation, selection metadata, and bounded explanations without invoking parsers or integration surfaces.

### Candidate Analysis Summary

The analysis summary produces a deterministic, bounded report for a completed repository candidate analysis. It distinguishes inventory truncation from candidate-selection truncation and exposes top candidate paths, cheap scores, analysis costs, value scores, and capped reasons in structured data.

## Architecture

The engine is organized as a one-way pipeline:

1. **Inventory:** Repository collection discovers files in deterministic order, prunes noisy trees, and records metadata and path-derived signals.
2. **Scoring:** Cheap scoring estimates task relevance from filenames, paths, roles, languages, and extensions.
3. **Shortlist:** Bounded shortlist helpers preserve deterministic ordering, reasons, caps, and truncation metadata.
4. **Cost and value:** Positive cost estimates and value scores favor relevant files that are cheaper to analyze.
5. **Candidate pipeline:** The pipeline connects repository inventory to value-aware candidate selection without parser or integration-layer dependencies.
6. **Summary and reporting:** Structured summaries expose bounded candidate details and distinguish inventory truncation from selection truncation.

The implementation is dependency-light, deterministic, and isolated in `strata.core`. Existing scanner, command, and context-generation behavior is unchanged.

## Safety Constraints

- Inventory collection uses directory walking and stat metadata only.
- Candidate scoring, cost estimation, selection, pipelines, and summaries do not open or read repository files.
- Caps are bounded, must be positive integers, and are validated before repository work where applicable.
- Inventory and candidate ordering is deterministic.
- Dependency trees, version-control metadata, caches, and build outputs are pruned during default repository collection.
- Generated and vendor records supplied to the candidate layer remain eligible but receive explicit relevance and cost penalties.
- Reasons remain attached to candidates so ranking decisions can be inspected.

## Deferred Capabilities

The foundation intentionally does not provide scanner or CLI integration, context-pack integration, persistent caching, tracing, representation selection, lazy outline extraction, deep scoring, framework-specific analysis, or flow intelligence.

## Validation

From the repository root, run the standard project validation commands:

```powershell
py tests.py
py tests\run.py
strata gate
```

The inventory, candidate, pipeline, and architecture contract suites are registered with the project test runner.

## Follow-Ups

Future milestones can introduce cache contracts, import tracing, a representation ladder, lazy outline extraction, framework analyzers, and supported CLI or context-pack integration. Each milestone should preserve bounded work, deterministic behavior, dependency direction, and explicit content-read boundaries.
