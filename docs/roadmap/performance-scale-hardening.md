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

## Roadmap

1. L1 Performance budget and benchmark harness - complete.
2. L2 Incremental scan/cache primitives - implemented.
3. L3 Bounded relationship extraction - pending.
4. L4 Large repo stress fixtures - pending.
5. L5 Performance diagnostics/reporting - pending.
6. L6 Final scale hardening docs - pending.

## Boundaries

- L2 owns cache invalidation and incremental scan/cache primitives.
- L3 owns bounded relationship extraction and extractor optimization.
- L4 owns large stress fixture trees.
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
