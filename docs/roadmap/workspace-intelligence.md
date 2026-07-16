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
