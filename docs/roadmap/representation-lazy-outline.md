# Representation and Lazy Outline Layer

Part I introduces Strata's token-control and context-contract layer. Its purpose is to make AI-ready context clearer without growing prompts by default.

## I1: Context Artifact Contract

I1 is contract-only. It defines the canonical context artifacts:

- `.aidc/context/strata_context.md`
- `.aidc/context/run_state.json`

`strata_context.md` separates trusted Strata/user instructions from untrusted repository-derived content. `Task` and `Suggested Instructions` are trusted. `Relevant Files`, `Dependency Traces`, `Internal Library APIs`, and `Cross-Repo / External App References` live inside the repository-content boundary. `Scope Guard` and `Warnings` are trusted Strata summaries after that boundary.

`run_state.json` defines the stable run-state shape used by later work, including workspace placeholders (`workspace_mode`, `workspace`, `cross_repo_references`) and internal library placeholders (`internal_libraries`).

I1 does not implement budget allocation, token estimation, symbol slicing, lazy outlines, frontend deep linking, backend intelligence, workspace scanning, adapter workflows, model calls, or CLI workflow changes.

## Later Part I Batches

Later batches can build on this contract to add representation tiers, budget profiles, lazy outline policy, and richer workspace intelligence while preserving the same artifact names and trust boundaries.
