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

## Deferred Work

JavaScript/TypeScript import parsing, Angular and React linking, dependency
traversal, candidate-selection changes, and product workflow wiring begin in
later batches. H1 and H2 add no third-party parser dependency.
