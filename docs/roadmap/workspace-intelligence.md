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
