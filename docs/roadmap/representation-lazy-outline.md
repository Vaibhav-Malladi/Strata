# Representation and Lazy Outline Layer

Part I introduces Strata's token-control and context-contract layer. Its purpose is to make AI-ready context clearer without growing prompts by default.

## I1: Context Artifact Contract

I1 is contract-only. It defines the canonical context artifacts:

- `.aidc/context/strata_context.md`
- `.aidc/context/run_state.json`

`strata_context.md` separates trusted Strata/user instructions from untrusted repository-derived content. `Task` and `Suggested Instructions` are trusted. `Relevant Files`, `Dependency Traces`, `Internal Library APIs`, and `Cross-Repo / External App References` live inside the repository-content boundary. `Scope Guard` and `Warnings` are trusted Strata summaries after that boundary.

`run_state.json` defines the stable run-state shape used by later work, including workspace placeholders (`workspace_mode`, `workspace`, `cross_repo_references`) and internal library placeholders (`internal_libraries`).

I1 does not implement budget allocation, token estimation, symbol slicing, lazy outlines, frontend deep linking, backend intelligence, workspace scanning, adapter workflows, model calls, or CLI workflow changes.

## I2: Run State and Baseline Safety

I2 extends the same canonical `.aidc/context/run_state.json` contract so Strata can remember what baseline it gave to an AI run.

For a normal repository, Strata records the current `HEAD` commit as `baseline_commit`, marks `baseline_commit_attached` as `true`, and records an attached baseline status. For a repository with no commits, `baseline_commit` is `null`; if `HEAD` is attached to an unborn branch, `baseline_commit_attached` remains `true`, but review diff is marked unavailable until a commit exists. For detached `HEAD`, Strata records the current commit, marks `baseline_commit_attached` as `false`, and warns that review can compare against the commit while branch tracking is detached.

I2 also adds a small stored-baseline validation helper for later review flows. Missing, invalid, or unreachable stored commits return a safe unavailable status and a warning asking the user to re-run context before review diff. The helper does not crash on ordinary git edge cases.

No competing state artifacts are introduced; `run_state.json` remains the single machine-readable state contract for Part I.

## Later Part I Batches

Later batches can build on this contract to add representation tiers, budget profiles, lazy outline policy, and richer workspace intelligence while preserving the same artifact names and trust boundaries.
