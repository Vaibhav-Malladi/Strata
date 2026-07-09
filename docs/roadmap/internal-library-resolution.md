# Internal Library Resolution Foundation

Plain name: Understand private/company libraries.

## Goal

Strata should recognize private library imports honestly and safely. Enterprise
Angular and React repositories often import shared UI kits, design systems, or
platform wrappers such as `@company/master-library`. A useful answer may be
repository source, TypeScript alias source, declaration files, an extracted
vendor copy, an archive reference, package metadata, or a clear statement that
no readable source is available.

The foundation prevents these cases from collapsing into one vague
"unresolved" bucket while keeping discovery bounded and deterministic.

## Bridge-1: resolution contract

Bridge-1 added immutable, JSON-ready contracts in
`strata/core/internal_library_resolution.py`:

- `LibraryVersionMetadata`
- `LibraryResolutionEvidence`
- `LibraryResolutionSafety`
- `InternalLibraryResolution`

It also added normalization, validation, deterministic sorting, and
deduplication helpers. The contract is filesystem-free: creating, sorting, and
merging results does not inspect a repository.

Supported classifications:

- `resolved_repo_source`
- `resolved_tsconfig_alias_source`
- `resolved_node_modules_declaration`
- `resolved_vendor_directory_declaration`
- `resolved_vendor_zip_reference`
- `external_public_package`
- `opaque_private_package`
- `unresolved_alias`
- `missing_package`

Source availability values:

- `source_available`
- `declaration_only`
- `zip_reference_only`
- `metadata_only`
- `unavailable`
- `unknown`

Version metadata records `version`, `version_source`, and
`version_confidence`. Version confidence is metadata only. It does not rank,
score, or reorder library results.

## Bridge-2: targeted package and vendor discovery

Bridge-2 added bounded discovery in
`strata/core/internal_library_discovery.py` for imports explicitly supplied by a
caller.

Node package policy:

- Normalize subpath imports such as `@company/master-library/dropdown` to the
  package root `@company/master-library`.
- Check only the exact targeted path under `node_modules`.
- Never enumerate or scan the `node_modules` root.
- Read `package.json` only under a byte cap.
- Use `types`, `typings`, `index.d.ts`, `public-api.d.ts`, and a capped set of
  direct package-root `.d.ts` files as declaration evidence.
- Record declaration paths and bounded cost metadata, but do not parse `.d.ts`
  content.

Vendor directory policy:

- Check deterministic candidates under `vendor`, `third_party`, `libs`,
  `libs/dist`, and `dist`.
- Do not recursively search vendor trees.
- Treat vendor package metadata and declarations as bounded evidence.
- If a package or vendor copy exists without readable declarations, classify it
  as `opaque_private_package`.

Zip/archive policy:

- Detect targeted `.zip`, `.tgz`, and `.tar.gz` archive references.
- Do not open, inspect, or extract archives by default.
- A version-shaped archive filename may produce low-confidence version metadata
  with `filename` as the source.
- Archive-only evidence is classified as `resolved_vendor_zip_reference` with
  `zip_reference_only` source availability.

Safety and honesty rules:

- Discovery only checks explicit import names provided by the caller.
- Broad `node_modules` scans are not allowed.
- Archive extraction is not a default behavior.
- Declaration parsing is not implemented yet.
- Source-unavailable cases stay honest: opaque packages and missing packages
  remain explicit instead of being treated as resolved source.
- Path escapes and unsafe declaration targets are skipped and recorded in
  safety metadata.

## Bridge-3: evidence and docs lock

Bridge-3 adds fixture-style evidence tests that exercise Bridge-1 and Bridge-2
together against tiny repository layouts. These tests prove:

- a task-relevant explicit import resolves to a targeted `node_modules` package
  with package version and declaration evidence;
- scoped package subpath imports resolve to the scoped package root;
- extracted vendor directories with declarations resolve as vendor declaration
  evidence;
- extracted vendor directories without declarations become opaque private
  packages;
- archive references are detected without extraction or content reads;
- versioned archive filenames produce low-confidence version metadata;
- missing packages remain `missing_package`;
- multiple imports for the same library dedupe to one result while retaining
  import evidence;
- declaration caps record skipped items and bounded cost metadata;
- unsafe declaration path escapes are skipped safely;
- unrelated `node_modules` packages are not inspected or included;
- result dictionaries are deterministic and JSON-ready.

No production flow is wired by this bridge. Bridge-3 closes the foundation with
evidence, documentation, and handoff language before later context work begins.

## Handoffs

Part I decides how these results appear in `strata_context.md`. It can use
`context_paths`, declaration evidence, source availability, and diagnostic notes
to represent internal libraries in generated context.

Part J may infer frontend usage from consuming templates and code when source
or declarations are missing. `usage_inference_required` marks those cases
without pretending that Strata has source.

Part M may include internal library findings in diagnostics and review state,
including classifications, bounded-work metadata, skipped items, warnings, and
source-unavailable explanations.

Part Q owns Workspace Intelligence. This foundation is not Workspace
Intelligence. Iframe-hosted apps, multi-repo local ports, `postMessage`
contracts, cross-repo shared configs, and cross-repo detection are deferred to
Q.

## Non-goals

This foundation does not:

- parse `.d.ts` API signatures;
- infer Angular or React consuming-code APIs;
- implement TypeScript alias resolution;
- detect cross-repo workspaces;
- create `strata_context.md`;
- create `run_state.json`;
- wire discovery into the CLI or product flow;
- change candidate selection;
- unzip archives;
- call models or the internet;
- add heavy dependencies.
