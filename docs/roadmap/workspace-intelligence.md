# Workspace Intelligence

Part Q adds cross-repository awareness for applications made from related
repositories such as a frontend, backend, shared library, authentication
service, gateway, worker, or infrastructure repository.

## Q1 - Workspace Configuration And Data Contracts

Q1 defines the foundational `.aidc/config.json` workspace contract only. The
optional top-level `workspace` block records:

- `schema_version`
- workspace `name`
- configured `repositories`
- explicit repository `relationships`
- configured `shared_contracts`

Repository entries use stable user-facing IDs, normalized configuration paths,
bounded roles, optional display names, known ports, and known URLs.

Relationship entries are explicit configuration values between repository IDs.
They use a bounded relationship-type vocabulary and do not infer or traverse a
graph.

`shared_contracts` represent configured values that should remain consistent
across repositories. Each entry records a name, contract type, expected scalar
value, one or more locations, optional allowed scalar values, severity, and
normalization mode. Locations identify a configured repository ID, a normalized
relative path, and an optional symbol.

All Q1 paths are configuration references only. Repository paths and shared
contract locations are normalized for deterministic serialization. Q1 does not read cross-repository files, resolve symbols, inspect URLs, make network requests, compare values, report contract mismatches, infer relationships, build dependency graphs, or add workspace information to AI context.

Q1 does not implement automatic workspace discovery, sibling repository
searching, multi-repository scanning, iframe or API URL extraction, postMessage
analysis, shared constant extraction, context-budget integration, guided CLI
changes, or User Flow/Journey Intelligence.

## Q2 - Workspace Repository Discovery Suggestions

Q2 adds a bounded discovery layer that suggests nearby repositories which may
belong to the same application workspace. These results are suggestions only:
Q2 does not alter `.aidc/config.json`, accept discovered repositories
automatically, add new commands, or make suggested repositories authoritative.

Discovery inspects only conservative local scope: the current repository's
bounded search root, direct sibling directories, and at most one explicitly
supplied search root. It skips ignored generated or dependency directories,
does not follow symlinks, does not make network requests, and does not run
project code.

Q2 uses cheap manifest and configuration signals only:

- sibling proximity
- `.git` repository markers
- project manifests such as `package.json`, `pyproject.toml`, `go.mod`, and
  `angular.json`
- explicit local path references in small workspace/config files such as
  `package.json`, `go.work`, `pnpm-workspace.yaml`, and Docker Compose files
- simple repository-name similarity

Each suggestion includes a normalized path, suggested ID, display name,
probable role, confidence label, bounded confidence score, concise evidence,
warnings, and discovery source. Confidence is deterministic: explicit
workspace-file membership, local path dependencies, and Docker Compose build
contexts are strong evidence; sibling proximity, `.git`, and name similarity
are weak and cannot produce high confidence by themselves.

Q2 applies a candidate cap and an evidence cap per candidate. When either cap
is reached, the discovery result records a stable diagnostic or warning instead
of silently hiding truncation.

Q2 does not perform deep cross-repository source scanning. It does not extract
runtime URLs, iframe sources, postMessage usage, route names, shared constants,
or API references, and it does not compare shared contracts, build a dependency
graph, write reports, or add workspace evidence to AI context.

## Q3 - Repository Roles And Relationship Evidence Contracts

Q3 defines canonical role assessments and canonical relationship candidates for
combining Q1 configuration with already-produced Q2 discovery suggestions or
caller-supplied inferred relationship hints.

Role assessments use the Q1 repository-role vocabulary and record repository
ID, role, origin, confidence, bounded evidence, warnings, and optional suggested
role. Explicit configured non-unknown roles remain authoritative. Explicit
`unknown` roles remain safe defaults while discovered or inferred evidence may
be retained as suggestions.

Relationship candidates use the Q1 relationship-type vocabulary and record
source repository ID, target repository ID, relationship type, origin,
confidence, bounded evidence, warnings, and optional description. Explicit
configured relationships take precedence over inferred candidates. Matching
inferred evidence may enrich an explicit relationship, while conflicting
inferred relationship types produce diagnostics instead of replacing explicit
configuration.

Q3 uses deterministic deduplication identities. Directional relationships use
`source_repository_id`, `target_repository_id`, and `relationship_type`.
`shares_contract_with` is treated as symmetric for duplicate detection only;
directional types such as `calls_api`, `imports_package`, `depends_on`,
`sends_messages_to`, and `receives_messages_from` remain direction-sensitive.

Evidence is confidence-aware and bounded. Evidence items record signal type,
source repository, source path, summary, strength, optional target repository,
optional referenced path, and bounded metadata. Role evidence and relationship
evidence caps produce stable truncation diagnostics rather than silently
discarding information.

Q3 adds conflict and ambiguity diagnostics for unknown repository references,
conflicting role evidence, conflicting relationships, duplicate relationships,
self-relationships, missing targets, unsupported types, evidence truncation,
candidate caps, and diagnostic caps.

Q3 does not build a dependency graph, traverse relationships, write workspace
reports, alter configuration, or discover repositories.
Q3 does not extract cross-repository source references.
It does not compare shared contracts and does not add workspace evidence to AI
context.
