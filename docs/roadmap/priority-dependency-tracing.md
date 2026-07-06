# Part H - Priority Import and Dependency Tracing

Status: final foundation contract. H1-H7 are implemented; H8 locks their
interfaces, policy, safety boundaries, evidence, and handoff to Part I.

Part H is library-level only. It does not change candidate scoring or candidate
selection, and it has no CLI or product workflow wiring.

## Contract Surface

| Module | Final responsibility |
| --- | --- |
| `strata.core.dependency_tracing` | H1 immutable edge and direct-trace contracts, path validation, deterministic sorting, deduplication, and JSON conversion |
| `strata.core.python_dependency_edges` | H2 direct Python import extraction |
| `strata.core.js_ts_dependency_edges` | H3 direct JavaScript/TypeScript import and re-export extraction |
| `strata.core.dependency_trace_runner` | H4 deterministic direct extraction from selected seed files |
| `strata.core.dependency_traversal` | H5 priority-bounded traversal and traversal report |
| `strata.core.dependency_priority` | H6 authoritative priority, cost, fallback, and traversal-order policy |
| `strata.core.dependency_trace_evaluation` | H7 deterministic Part G fixture evaluation |

All public reports are immutable and/or expose stable JSON-ready `to_dict()`
representations. Parser-specific internal values are not part of the handoff.

## H1 Edge and Report Contracts

### `DependencyEdge`

A dependency edge is directed from an importing/exporting source file to one
resolved repository-local target file. It contains exactly:

- `source_file` and `target_file`: normalized forward-slash paths relative to
  the supplied repository root;
- `edge_type`: `import`, `re_export`, `route`, `template`, `style`, `config`, or
  `unknown`;
- `priority`: `critical`, `high`, `medium`, or `low`;
- `reason`: stable human-readable extraction evidence;
- `confidence`: `unknown`, `low`, `medium`, or `high` metadata;
- `estimated_cost`: a finite non-negative relative cost.

Absolute paths, root escapes, empty paths, negative/non-finite costs, and
out-of-vocabulary values are rejected. Edges are sorted by semantic priority
and deterministic tie-breakers. Deduplication removes only exactly identical
edges.

### `DependencyTraceReport`

The direct trace envelope contains normalized seed files, sorted/deduplicated
edges, skipped items, warnings, and an optional `StageReport`. Warnings and
skips are explicit evidence: an absent edge does not prove that no dependency
exists.

## H2 Python Extraction Policy

`extract_python_import_edges()` uses only the Python standard-library AST and
reads only the selected Python source file. It never imports or executes source
or target modules and never reads target contents.

Supported direct forms include:

- `import package`, `import package.module`, and aliases;
- `from package import name` and `from package.module import name`;
- `from ... import *` resolved to its containing module;
- safe relative imports such as `from . import helper` and
  `from ..utils import thing`.

Internal absolute imports search the repository root and existing `src/` and
`lib/` source roots. Resolution prefers `package/module.py` and then
`package/module/__init__.py`. Imported child modules are preferred when present;
otherwise a resolved containing module is retained as lower-certainty symbol
evidence.

Installed packages, external modules, unsafe paths, and unresolved imports are
not followed and produce deterministic skipped items. Syntax errors produce an
empty trace with a warning. Python extraction is internal-only resolution.

## H3 JavaScript and TypeScript Extraction Policy

`extract_js_ts_import_edges()` uses standard-library lightweight lexical
scanning and a bounded source read. It supports:

- default, named, and namespace static imports;
- side-effect imports;
- named and star re-exports;
- simple string-literal `import("./module")` calls;
- simple string-literal CommonJS `require("./module")` calls.

Resolution is relative-only. It accepts `.ts`, `.tsx`, `.js`, `.jsx`, `.mjs`,
and `.cjs`, probing in that order when an extension is omitted. Directory
resolution supports `index.ts`, `index.tsx`, `index.js`, and `index.jsx`.

Part H performs no `node_modules` traversal and no installed-package or bare
package resolution. It does not resolve `react`, `lodash`, `@angular/core`,
tsconfig aliases, workspace packages, computed specifiers, or other unsupported
forms. External, alias-like, unsafe, and unresolved imports become deterministic
skipped items rather than fabricated edges. Targets must resolve inside the
repository root; target contents are never read or executed.

## H4 Seed Orchestration Policy

`run_dependency_trace()` accepts a repository root, relative seed paths, an
optional seed cap, and an optional supported-extension policy. Seeds are
normalized, deduplicated, and processed in lexical order. The default maximum
is `20` seed files; callers may lower it or explicitly use `None`.

`.py` seeds dispatch to H2. `.ts`, `.tsx`, `.js`, `.jsx`, `.mjs`, and `.cjs`
seeds dispatch to H3. Unsupported, missing, unsafe, unreadable, and over-cap
seeds are skipped deterministically. Child edges are merged with H1 helpers.
H4 extracts direct edges only and never dispatches discovered targets.

## H5 Traversal and Report Contract

`traverse_dependencies()` follows resolved targets only after they enter an
allowed frontier. The authoritative defaults are:

- maximum depth: `2`;
- maximum visited files: `40`;
- maximum edges: `100`;
- maximum estimated cost: `100.0` relative units.

The cost cap may be disabled with `None`; the other caps remain explicit.
Cycles, duplicate files, and duplicate edges cannot expand traversal. A target
at the depth boundary may be recorded as visited without opening it. No target
is read until direct extraction is required at an admitted frontier position.

`DependencyTraversalReport` wraps an H1 `DependencyTraceReport` and adds stable
`visited_files` order plus `file_depths`. Its convenience properties expose
seeds, edges, skips, warnings, and the aggregate `StageReport`. Its `to_dict()`
shape is the primary Part I handoff.

## H6 Priority, Cost, Confidence, and Fallback Policy

Priority order is exactly `critical > high > medium > low`. Seeds enter before
discovered targets. Frontier order is priority, estimated cost, depth, and
stable path tie-breakers.

Exact imports and re-exports are `medium`; symbol-import fallbacks, dynamic
imports, and CommonJS requires are `low`. Current emitted import and re-export
edges cost `1.0` relative unit. The central policy defines finite non-negative
base costs for every H1 edge type. These costs bound work; they are not relevance
scores.

Confidence is metadata only. It is not an additive score, multiplier, priority
boost, cost adjustment, or traversal tie-breaker. Unresolved and unsupported
targets use the explicit `skip` fallback and are never represented by invented
target paths.

## StageReport Measurement

Direct extraction, seed orchestration, traversal, and evaluation use Part G's
`strata.core.stage_report.StageReport`. Reports account for inputs, outputs,
metrics, warnings, skipped items, confidence metadata, elapsed milliseconds,
bytes read, and files touched.

Traversal cost is the sum of accepted unique edge costs. `files_touched` counts
source files actually inspected, not merely discovered depth-boundary leaves.
Zero elapsed time remains the deterministic default when no clock is injected.

## H7 Evaluation and Current Evidence

`evaluate_dependency_tracing()` evaluates every applicable Part G manifest task
without mutating the candidate engine. The unchanged current baseline supplies
a ranked pool; the first supported baseline candidate is the default seed.
Before metrics grade seed context at K, and after metrics grade bounded visited
order at the same K. The complete baseline ranking is retained for auditability.

Task reports include fixture/task identity, baseline paths, seeds, visited
files, traced edges, Part G metrics before and after, deltas, warnings, skips,
and a cost-bearing `StageReport`. The aggregate includes:

- average critical recall before and after;
- total missed critical files before and after;
- average useful coverage, distractor rate, and context waste before and after;
- total files touched and total estimated edge cost;
- an evidence-based conclusion and whether tracing appears to earn its cost.

The conclusion rule requires a critical-recall, missed-critical, or useful-
coverage improvement; no critical-quality regression; no distractor or context-
waste increase; and positive measured cost. Otherwise the report states no
improvement, mixed evidence, or regression rather than forcing a positive
result.

With the current five Part G tasks at K=`3` and one seed, average critical recall
changes from `0.5` to `0.7`, missed critical files from `3` to `2`, useful
coverage remains `0.2`, and distractor/context-waste rates remain `0.0`.
Tracing touches `6` source files and accepts `1.0` estimated cost unit. The gain
comes from one Angular task; four tasks are unchanged. Under the stated rule,
tracing appears to earn its bounded fixture cost. This is synthetic fixture
evidence, not a general product benchmark.

## Safety Boundaries and Deferred Work

Part H uses no network, model calls, third-party parser, code execution, broad
traversal scan, installed-package resolution, or target-content read before
frontier admission. Symlink targets must remain inside the repository root.

There is no CLI/product wiring yet and no candidate behavior changes. Real
GitHub repository benchmarking is not part of Part H. Representation and lazy
outline work belong to Part I; frontend deep linking belongs to Part J; backend
intelligence belongs to Part K.

## Part I Handoff

Part I should consume `DependencyTraversalReport.to_dict()` or the equivalent
immutable properties. In particular it should:

1. use `visited_files` and `file_depths` as bounded file-selection evidence;
2. use H1 edges, priorities, reasons, and costs as relationship provenance;
3. preserve repository-relative paths and deterministic order;
4. surface warnings and skipped items instead of treating unresolved imports as
   proof of no dependency;
5. use `StageReport` bytes/files/cost fields when applying representation
   budgets;
6. keep confidence descriptive and separate from selection/scoring math;
7. avoid depending on extractor internals or re-resolving imports differently.

Part I may decide how much representation to allocate to each admitted file,
but it should not silently broaden Part H's traversal caps or safety boundary.
