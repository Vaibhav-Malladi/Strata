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

## Q4 - Cross-Repository Reference Extraction

Q4 adds selected-file extraction only for concrete cross-repository reference
signals. Callers provide the repository ID, repository root, and bounded
selected paths; Q4 does not recursively discover files or choose candidates
automatically.

Reference records cover a bounded vocabulary: `localhost_url`,
`absolute_http_url`, `iframe_src`, `post_message_send`, `message_listener`,
`api_base_url`, `environment_url`, `route_constant`, and `shared_constant`.
Each record stores repository ID, normalized source path, raw and normalized
value, confidence, bounded Q3-compatible evidence, optional symbol, optional
line number, optional target repository ID, optional target hint, and
JSON-ready metadata.

Extraction is lightweight and language-aware for Python, JavaScript,
TypeScript, React JSX/TSX, Angular templates, HTML, Go, JSON, TOML, simple
YAML key/value lines, and `.env` files. It detects localhost and absolute
HTTP-family URLs, literal and bound iframe sources, postMessage senders,
message listeners, API and environment URL constants, route-like constants,
and shared string constants only when names indicate cross-repository
relevance.

Target matching is deterministic and local. Q4 may match references against
configured repository URLs or unique configured ports, leaves ambiguous or
unknown matches unset, and never uses network calls or DNS resolution.

Confidence is deterministic and capped by evidence quality. Literal URLs and
exact configured target matches are strongest, host/port matches are bounded,
dynamic expressions and wildcard postMessage origins are low confidence, and
ambiguous target matches produce diagnostics instead of target assignments.

Q4 applies selected-file, byte, reference, per-file reference, and diagnostic
caps. It emits stable diagnostics for unsafe paths, symlink escapes,
unsupported files, read or decode failures, malformed JSON or TOML,
conservative YAML parsing, caps, ambiguous or unknown targets, wildcard
postMessage origins, unresolved dynamic references, and secret redaction.

Secret-like values, secret-named configuration fields, credentialed URLs,
tokens, passwords, authorization values, cookies, and private keys are skipped
or redacted; raw secret values are not stored in reference metadata or
evidence.

Q4 can convert targeted references into Q3-compatible relationship hints for
API calls, iframe embeds, postMessage sends, and message receives. Q3 remains
responsible for merging and precedence.

Q4 does not build the workspace dependency graph or traverse relationships.
Q4 does not compare shared contracts, report mismatches, generate reports, or
write configuration. Q4 does not add findings to AI context.

## Q5 - Shared-Contract Comparison and Diagnostics

Q5 adds deterministic shared-contract comparison between configured Q1
`shared_contracts` and already-extracted Q4 reference records. Q5 accepts
workspace configuration, reference records, and optional explicit location
states from callers; Q5 reads no files directly, runs no extraction, discovers
no repositories, and selects no files automatically.

Q5 produces location-level and contract-level findings. Location findings
record the configured contract name, repository ID, path, optional symbol,
status, expected and allowed values, observed and normalized values, stable
reference keys, confidence, bounded evidence, and diagnostics. Contract
findings summarize the contract type, severity, normalization, derived status,
all location findings, distinct observed values, confidence, evidence, and
diagnostics.

Supported outcomes are bounded: `consistent`, `inconsistent`, `missing`,
`ambiguous`, `unreadable`, `skipped`, and `unsupported`. Contract-level status
is derived with deterministic precedence so mismatches are not hidden by
missing, skipped, unreadable, or unsupported locations.

Normalization follows the Q1 vocabulary: `exact`, `case_insensitive`,
`trimmed`, `url`, and `port`. URL normalization reuses Q4 loopback and
credential handling, while port normalization requires explicit valid ports.
Expected values remain canonical, allowed values are accepted alternatives,
and different normalized values across configured locations are reported as
cross-location disagreement.

Q5 maps Q1 contract types to Q4 references conservatively: authentication
headers, iframe URLs, API constants, route names, port numbers, message events,
and custom contracts require matching repository IDs, exact normalized paths,
and exact symbols when configured. Shared package contracts remain unsupported
until package extraction exists.

Confidence is deterministic and evidence is bounded. Exact repository,
path, and symbol matches score highest; path-only matches are lower;
ambiguous, missing, skipped, unreadable, or unsupported states carry explicit
diagnostics.

Sensitive configured or observed values are redacted. Secret-like values,
tokens, passwords, API keys, private keys, cookies, and credentials are not
serialized as normal comparison values.

Q5 applies contract, location, observation, evidence, finding, and diagnostic
caps. It emits stable diagnostics for missing locations, ambiguous
observations, unreadable or skipped locations, unsupported comparisons,
value mismatches, cross-location mismatches, incompatible reference types,
missing symbols or paths, unsupported expected or allowed values,
normalization failures, invalid ports or URLs, duplicate contracts or
locations, evidence truncation, finding caps, diagnostic caps, and sensitive
value redaction.

Q5 changes no files, writes no configuration, and generates no reports.
Q5 does not add findings to AI context. Q5 does not build a dependency graph
or trace user journeys.
