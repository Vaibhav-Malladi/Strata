# Bridge — Internal Library Resolution Foundation

## Goal

Help Strata understand what a private or company library import points to. Enterprise Angular and React repositories commonly import shared UI kits and design systems such as `@company/master-library`. The useful evidence may be repository source, a TypeScript alias, declarations, a vendor copy, an archive reference, package metadata, or simply the fact that nothing readable is available. Those outcomes should not all be reported as “unresolved.”

## Classification contract

Bridge-1 defines these stable outcomes:

- `resolved_repo_source`
- `resolved_tsconfig_alias_source`
- `resolved_node_modules_declaration`
- `resolved_vendor_directory_declaration`
- `resolved_vendor_zip_reference`
- `external_public_package`
- `opaque_private_package`
- `unresolved_alias`
- `missing_package`

Source availability separately records whether Strata has source, declarations only, an archive reference only, metadata only, nothing available, or an unknown state. Version, version source, and version confidence are retained as metadata. Confidence does not score, rank, or reorder results.

The contract can record vendor-directory and zip paths as bounded evidence. It does not discover vendor directories, inspect `node_modules`, open archives, or extract zip files. Archive extraction is not a default behavior. All discovery and parsing policy belongs to later, explicitly bounded work.

## Later handoff

Part I can use the context paths and readable evidence to represent a library or API surface in context. When declarations or source are unavailable, the `usage_inference_required` handoff allows Part J to infer frontend usage from repository call sites. Classification, bounded-work accounting, warnings, and diagnostic notes remain available for Part M diagnostics.

This bridge defines data contracts and validation only. It does not perform package lookup, resolve tsconfig aliases, parse declarations, infer template usage, create context packs, or change candidate behavior.

## Bridge-2: targeted package and vendor discovery

Bridge-2 consumes the contract for imports explicitly supplied by a caller. It normalizes a subpath such as `@company/master-library/button` to its package root and checks only that exact package under `node_modules`. It never enumerates the `node_modules` root or scans unrelated packages.

For a targeted package, discovery reads `package.json` under a strict byte cap. The package name, version, `types` or `typings` entrypoint, and useful `module` or `main` values become metadata. Package versions use `package_json` as their source. Declaration discovery checks the declared entrypoint, `index.d.ts`, `public-api.d.ts`, and a capped set of direct package-root declaration files. It records bounded paths and byte costs but does not parse declaration content.

Vendor lookup is similarly explicit and bounded. It checks normalized candidates under `vendor`, `third_party`, `libs`, `libs/dist`, and `dist`; it does not recursively search those trees. Zip, tgz, and tar.gz files are references only and are never opened or extracted. A version-shaped archive filename may provide low-confidence version metadata with `filename` as its source.

Hard limits cover package metadata bytes, declaration count and bytes, vendor candidates, direct package-root entries, and archive-root entries. Results distinguish readable node declarations, readable vendor declarations, archive references, opaque packages, and missing packages using Bridge-1 classifications. Bridge-3 can evaluate this evidence and lock the public diagnostics/documentation behavior before later context work begins.
