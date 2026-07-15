# Performance and Scale Hardening

## Goal

Part L makes Strata fast, bounded, and reliable on larger repositories without increasing prompt size by default. Part I remains the token firewall; performance work must measure and respect context size before any deeper optimization changes are made.

## L1 Scope

L1 is measurement and harness only. It defines a stable performance budget profile, deterministic repository-size classification, count-based budget summaries, and synthetic count fixtures that can model larger repositories without creating large directory trees.

L1 does not clone real repositories, add real-repo UAT, run huge tests, add wall-clock timing assertions, call models, use the internet, generate `.aidc/context` artifacts, change Part I contracts, rewrite extractors, or optimize cache and relationship extraction behavior. Real repo UAT is not part of L1.

## Roadmap

1. L1 Performance budget and benchmark harness.
2. L2 Incremental scan/cache primitives.
3. L3 Bounded relationship extraction.
4. L4 Large repo stress fixtures.
5. L5 Performance diagnostics/reporting.
6. L6 Final scale hardening docs.

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
