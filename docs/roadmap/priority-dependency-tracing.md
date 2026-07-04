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

## Deferred Work

Python and JavaScript/TypeScript import parsing, Angular and React linking,
dependency traversal, candidate-selection changes, and product workflow wiring
begin in later batches. H1 performs none of that work and adds no parser
dependency.
