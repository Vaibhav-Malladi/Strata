# Performance and Scale Hardening

## Goal

Part L makes Strata fast, bounded, and reliable on larger repositories without increasing prompt size by default. Part I remains the token firewall; performance work must measure and respect context size before any deeper optimization changes are made.

## L1 Scope - Complete

L1 complete.

L1 is measurement and harness only. It defines a stable performance budget profile, deterministic repository-size classification, count-based budget summaries, and synthetic count fixtures that can model larger repositories without creating large directory trees.

L1 does not clone real repositories, add real-repo UAT, run huge tests, add wall-clock timing assertions, call models, use the internet, generate `.aidc/context` artifacts, change Part I contracts, rewrite extractors, or optimize cache and relationship extraction behavior. Real repo UAT is not part of L1.

## L2 Scope - Implemented

L2 implemented.

L2 defines safe cache reuse primitives for incremental scan/cache work. It adds deterministic file/input fingerprinting from supplied file facts, scan-option fingerprinting, cache metadata creation, cache key generation, TTL checks from supplied timestamps, reuse decisions, safe invalidation reason codes, and JSON-ready diagnostics summaries.

L2 is primitives only. It does not yet perform broad scanner integration, does not rewrite scanner behavior, does not read actual repository files in tests, does not scan real repositories, and does not create generated `.aidc/context` artifacts.

Caching reduces repeated local work. It does not expand prompt size, bypass Part I, or change the token firewall.

## L3 Scope - Implemented

L3 implemented.

L3 adds relationship caps and bounded summaries for already-created frontend/backend relationship payloads. It defines a stable relationship limit profile, generic payload normalization, deterministic ordering, duplicate counting, warning truncation, summary payload bounds, and drop reason codes for total, per-source, per-target, per-framework, per-type, route-path, malformed-record, and summary-payload limits.

L3 is primitives first. It does not yet perform broad extractor rewrites, does not scan repositories, does not read files, and does not call frontend/backend extractors. Broad extractor integration remains bounded/future work unless a later step adds a tiny safe hook.

Part I remains the token firewall. L3 reduces local extraction and diagnostic explosion, but it does not expand prompt content or change context artifact contracts.

## L4 Scope - Implemented

L4 implemented.

L4 adds synthetic count-only and small generated records for scale stress coverage. It defines deterministic repository shapes, in-memory synthetic file facts, named count-only stress scenarios, synthetic backend relationship records for Python, JavaScript/TypeScript, and Go frameworks, and a stress evaluation helper that combines the L1 budget, L2 cache, and L3 relationship limit primitives.

L4 does not create thousands of files, clone repositories, scan real repository directories, invoke extractors, read files, or run real repo UAT. The boundary is explicit: real cloned GitHub repo testing is not part of L4 and remains later product validation.

Part I remains the token firewall. L4 stress fixtures test local scale behavior but do not increase default prompt/context size.

## Roadmap

1. L1 Performance budget and benchmark harness - complete.
2. L2 Incremental scan/cache primitives - implemented.
3. L3 Bounded relationship extraction - implemented.
4. L4 Large repo stress fixtures - implemented.
5. L5 Performance diagnostics/reporting - pending.
6. L6 Final scale hardening docs - pending.

## Boundaries

- L2 owns cache invalidation and incremental scan/cache primitives.
- L3 owns bounded relationship extraction primitives; broader extractor optimization remains future bounded work.
- L4 owns synthetic/count-only scale fixtures; real repo UAT remains later validation.
- M/N own diagnostics and UX workflow changes.
- O owns adapter/model behavior.
- P owns user journey intelligence.
- Q owns workspace intelligence.
- Go remains in scope for synthetic count coverage; Java and Rust remain out of scope for Part L.

## Validation

From the repository root, run:

```powershell
py tests.py
py tests\run.py
```
