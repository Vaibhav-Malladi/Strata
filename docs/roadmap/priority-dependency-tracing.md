# Part H — Priority Import and Dependency Tracing

## H1: Dependency Edge Schema and Trace Contract

H1 defines the library-level contract that later Part H batches will produce
and Part I will consume. It deliberately contains no import parser, framework
linker, graph traversal, or CLI integration.

The contract lives in `strata.core.dependency_tracing`. A directed dependency
edge contains:

- repository-relative source and target files;
- a bounded edge type: `import`, `re_export`, `route`, `template`, `style`,
  `config`, or `unknown`;
- a bounded priority: `critical`, `high`, `medium`, or `low`;
- a human-readable reason;
- Part G-aligned confidence metadata: `unknown`, `low`, `medium`, or `high`;
- a finite, non-negative estimated cost.

Paths are normalized to forward-slash repository-relative form. Absolute paths
and parent traversal are rejected. Edges sort deterministically by semantic
priority and stable tie-breakers; only exactly identical edges are deduplicated.

`DependencyTraceReport` carries normalized seed files, sorted edges, skipped
items, warnings, and an optional Part G `StageReport` cost summary. Its
JSON-ready shape is the stable handoff to Part I, so later tracing producers can
evolve without forcing Part I to understand parser-specific internal values.

Confidence is metadata only. It is not an additive score, multiplier, priority
boost, or substitute for the explicit edge priority.

## H2: Direct Python Import Edges

H2 adds `strata.core.python_dependency_edges`, a standard-library-only AST
extractor for direct imports in one Python source file. It supports absolute and
relative `import` and `from ... import ...` forms, including aliases, and emits
only H1 `DependencyEdge` values whose target resolves inside the supplied
repository root. It checks the repository root plus existing `src/` and `lib/`
source roots, preferring `module.py` over `module/__init__.py`.

Exact module and imported-child matches are medium priority with high
confidence. A symbol imported from a resolved containing module is low priority
with medium confidence because static analysis cannot prove that the attribute
exists. Estimated cost is `1.0` per emitted edge as an initial lightweight AST
unit; confidence remains metadata only.

Unresolved imports, including external and installed packages, are recorded as
deterministic skipped items and are never followed. Syntax errors produce an
empty trace with a deterministic warning. Target code is not read, imported, or
executed. H2 performs no dependency traversal and has no CLI or product wiring.

## H3: Direct JavaScript and TypeScript Edges

H3 adds `strata.core.js_ts_dependency_edges`, a standard-library-only
lightweight lexical extractor for static imports, side-effect imports,
re-exports, simple string-literal dynamic imports, and simple string-literal
CommonJS `require` calls. It reads one bounded JS/TS source file and emits H1
`DependencyEdge` values for direct relationships only.

Resolution is deliberately relative-only. Exact `.ts`, `.tsx`, `.js`, `.jsx`,
`.mjs`, and `.cjs` files are supported, followed by extension probing in that
order. Directory imports probe `index.ts`, `index.tsx`, `index.js`, and
`index.jsx`. Every resolved target must remain inside the repository root.
Target contents are never read or executed.

Static imports and re-exports are medium priority with high confidence. Dynamic
imports and CommonJS requires are low priority with medium confidence.
Estimated cost is `1.0` per emitted edge. External packages, `node_modules`,
unresolved paths, path aliases, and unsupported specifiers become deterministic
skipped items rather than fabricated edges. Existing alias resolution is not
reused because it performs broader repository/config/package discovery than
H3's bounded direct-edge contract permits.

H3 does not traverse dependencies, resolve installed packages, or wire edges
into product workflows.

## H4: Direct Trace Orchestration

H4 adds `strata.core.dependency_trace_runner`. The runner accepts repository-
relative seed files, normalizes and deduplicates them, applies a default cap of
20 seeds, and dispatches `.py` files to H2 and `.ts`, `.tsx`, `.js`, `.jsx`,
`.mjs`, and `.cjs` files to H3. Callers may lower or remove the cap and may
restrict the supported extension set.

Seed processing follows normalized lexical order so cap behavior is stable.
Unsupported extensions, missing files, unsafe paths, unreadable files, and
over-cap seeds become deterministic skipped items. Child skips and warnings are
qualified with their seed path. Extracted edges are merged and deduplicated
using H1 helpers.

The resulting H1 `DependencyTraceReport` includes selected seeds, direct edges,
skips, warnings, and an aggregate `StageReport`. Measurement sums source bytes,
source files touched, elapsed extraction time, and estimated cost across unique
edges. Discovered target files are never dispatched, read, or executed: H4 is
not recursive traversal and has no product or CLI wiring.

## H5: Priority-Bounded Traversal

H5 adds `strata.core.dependency_traversal`, which repeatedly invokes the H4
direct-edge runner only for files admitted to a deterministic priority
frontier. The initial defaults are maximum depth `2`, maximum visited files
`40`, maximum edges `100`, and maximum estimated edge cost `100.0`. Every cap is
explicitly configurable; the cost cap may be disabled with `None`.

Seeds are normalized, deduplicated, and ordered lexically. Discovered files are
visited by H1 edge priority (`critical`, `high`, `medium`, then `low`), with
depth and path as stable tie-breakers. Confidence remains metadata and never
changes frontier order or cost. Cycles, duplicate files, and duplicate edges
are suppressed.

Missing, unsafe, unsupported, unresolved, external, over-depth, over-file,
over-edge, and over-cost work is not followed. Target contents are read only if
the target reaches an allowed frontier position that requires direct-edge
extraction; depth-boundary leaves are recorded without being opened. No broad
repository scan, installed-package lookup, `node_modules` traversal, network
access, or code execution occurs.

`DependencyTraversalReport` wraps the H1 `DependencyTraceReport` with stable
visited-file order and per-file depth metadata. Its aggregate `StageReport`
records visited and inspected files, edges, bytes, elapsed extraction time,
estimated edge cost, skips, and warnings. H5 has no CLI or product wiring.

## H6: Dependency Priority and Cost Policy

H6 centralizes policy in `strata.core.dependency_priority`. Priority order is
`critical`, `high`, `medium`, then `low`. Exact imports and re-exports remain
medium priority; symbol-import fallbacks, dynamic imports, and CommonJS
requires remain low priority. This preserves H2-H5 behavior while giving later
edge producers one bounded vocabulary.

Traversal orders edges by priority, estimated cost, depth, and stable paths.
Current import and re-export edges cost `1.0` relative unit, preserving the H5
cap behavior. The policy defines finite non-negative base costs for every H1
edge type. Unresolved and unsupported targets use an explicit `skip` fallback.
Confidence is metadata only: it is absent from priority, cost, and traversal
keys and never acts as a score, multiplier, or boost.

## H7: Part G Fixture Evaluation

H7 adds `strata.core.dependency_trace_evaluation`. For every Part G manifest
task, the unchanged current candidate baseline supplies a deterministic ranked
pool. The first supported baseline candidate is the default trace seed. “Before”
metrics grade that seed context at K; “after” metrics grade bounded visited-file
order at the same K. The full baseline ranking is retained in each report for
auditability. This measures tracing's marginal contribution without changing
or replacing candidate selection.

Task reports include fixture/task identity, baseline paths, seeds, visited
files, edges, Part G metrics before and after, deltas, warnings, skips, and a
cost-bearing `StageReport`. The aggregate reports average critical recall,
useful coverage, distractor rate, and context waste; total missed critical
files; files touched; and estimated edge cost. Every report is deterministic
and JSON-ready.

Tracing “appears to earn its cost” only when critical recall, missed critical,
or useful coverage improves; critical quality does not regress; distractor and
waste rates do not increase; and measured edge cost is positive. Otherwise the
conclusion explicitly records no improvement, mixed evidence, or regression.
With the current five fixtures and default K=3/one-seed policy, critical recall
averages `0.5` before and `0.7` after, missed critical files fall from `3` to
`2`, useful coverage remains `0.2`, and distractor/waste rates remain `0.0` at
an estimated edge cost of `1.0`. The improvement occurs in one Angular task;
the other four tasks are unchanged, so this is bounded fixture evidence rather
than a general product claim.

## Deferred Work

Angular and React linking, candidate-selection changes, and product workflow
wiring remain later work. H8 final contract/handoff also remains deferred.
H1-H7 add no third-party parser dependency.
