# Cost-Based Repository Intelligence

## Goal

Strata's cost-based repository intelligence engine prioritizes useful repository evidence before paying for deeper analysis. Each stage must justify its cost using deterministic, inspectable signals and bounded outputs.

## Current Scope

The current foundation walks repository trees, inventories files from metadata, scores path-derived relevance, estimates relative analysis cost, selects bounded candidates, and produces structured summaries. It operates entirely inside the core layer and does not read file contents.

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

### Candidate Engine Summary

The summary layer converts a selection into bounded structured data suitable for future diagnostics. It includes selection metadata and a configurable number of top candidates with capped explanations.

### Repository Inventory Collection

Repository inventory collection walks directories in deterministic order and creates `InventoryRecord` objects using path and stat metadata only. It prunes dependency trees, version-control metadata, caches, build outputs, and hidden paths by default, supports a validated file cap, and tolerates inaccessible entries.

### Repository Candidate Pipeline

The core pipeline connects bounded repository inventory collection to value-aware candidate selection and summary generation. Its result reports inventory and candidate limits, inventory truncation, selection metadata, and bounded explanations without invoking parsers or integration surfaces.

## Architecture Notes

The engine is organized as a one-way pipeline:

1. Repository collection discovers files in deterministic order and prunes noisy trees.
2. Inventory records capture metadata and path signals.
3. Cheap scoring estimates task relevance.
4. Cost estimation assigns a positive relative analysis cost.
5. Value ranking orders candidates by usefulness per cost.
6. Selection, pipeline, and summary helpers enforce output bounds.

The implementation is dependency-light, deterministic, and isolated in `strata.core`. Existing scanner, command, and context-generation behavior is unchanged.

## Safety Constraints

- Candidate scoring, cost estimation, selection, and summary generation do not open or read repository files.
- Repository collection uses directory walking and stat metadata only.
- Filesystem metadata is collected only by the inventory layer.
- Limits must be positive integers and are validated before selection or reporting.
- Generated and vendor signals reduce priority without silently removing files.
- Reasons remain attached to candidates so ranking decisions can be inspected.

## Deferred Capabilities

The foundation intentionally does not provide scanner or CLI integration, context-pack integration, persistent caching, tracing, representation selection, lazy outline extraction, deep scoring, framework-specific analysis, or flow intelligence.

## Validation

From the repository root, run the focused inventory and candidate tests with the project environment:

```powershell
& ..\.codex-venv\Scripts\python.exe -c "from tests.test_inventory import TESTS as inventory; from tests.test_candidates import TESTS as candidates; from tests.test_candidate_pipeline import TESTS as pipeline; tests = [*inventory, *candidates, *pipeline]; [test() for test in tests]; print(f'{len(tests)} focused tests passed')"
```

Run broader project validation separately when preparing a merge or release.

## Follow-Ups

Future work can define representation choices for selected files, add cache and trace contracts, and expose bounded diagnostics through supported command and context surfaces. Those capabilities should retain the same cost accounting, deterministic ordering, and content-read boundaries.
