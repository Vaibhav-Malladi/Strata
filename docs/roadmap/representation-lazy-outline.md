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

## I3: Representation Tiers

I3 defines the representation ladder Strata will use before later batches decide when to downgrade content:

- whole file (`full content`)
- symbol slice (`useful symbols`)
- method/class slice (`relevant method/class only`)
- file outline (`outline`)
- path-only with reason (`path and reason only`)
- skipped with reason (`skipped`)

The contract records represented items as deterministic JSON-ready dictionaries with path, tier, source type, reason, optional priority/score, optional token placeholder fields, warnings, and supplied content or excerpts. Source types are limited to candidate, trace, internal library, warning, and workspace placeholder.

Rendered represented items live in the `Relevant Files` section, which remains inside the untrusted repository-content boundary from I1. I3 does not read files, estimate tokens, allocate budgets, extract symbols, or choose lazy downgrade policy.

## I4: Budget Profile and Token Firewall

I4 adds trusted token-firewall metadata without implementing allocation. The budget profile records target context tokens, reserved output tokens, maximum context-pack tokens, tokenizer strategy, and safety margin. Defaults are conservative and stdlib-only.

The budget summary records estimated used tokens, representation counts, largest token-savings records, skipped or downgraded records, and warnings. It is always renderable and belongs to trusted Strata metadata outside the untrusted repository-content boundary.

Token estimates are approximate and intentionally conservative: Strata should overestimate rather than underestimate. Model-aware tokenizer behavior belongs to later adapter work. I4 does not read files, scan repositories, choose downgrades, extract symbols, generate lazy outlines, or allocate budget.

## I5: Lazy Outline Policy

I5 adds deterministic policy primitives for falling through the representation ladder when content does not fit or extraction fails. The downgrade path is whole file to symbol slice to method/class slice to file outline to path-only. Path-only is terminal unless the item is explicitly skipped because it is irrelevant, unsafe, missing, or unavailable; skipped is terminal.

Symbol extraction failures are modeled as data, not implemented as parsing: syntax error, parse timeout over five seconds, empty extraction result for a file over 100 lines, exception, and unsafe decode. A failure produces a clear reason and warning and falls through to the next lighter tier without crashing context generation.

I5 does not read files, parse ASTs, scan repositories, allocate budget, pack tokens, or choose complete representation plans. Later batches can use these policy contracts when real outline generation exists.

## I6: Adapter-Neutral Output and Part I Handoff

I6 finalizes Part I as one adapter-neutral context contract. The canonical artifacts remain `.aidc/context/strata_context.md` and `.aidc/context/run_state.json`. Browser AI, CLI AI, VS Code terminal, VS Code side chat, and a future VS Code extension must consume or derive output from those canonical artifacts rather than storing independent prompt or session files.

The context markdown is plain deterministic Markdown with visible trusted/untrusted boundaries. It is safe to open, copy, paste, or reference from a browser, terminal, VS Code terminal, or VS Code side chat without terminal-only assumptions or extension-specific duplicated intelligence.

Part I hands off to later roadmap work:

- Part J consumes represented frontend files and internal-library hints.
- Part K consumes represented backend files later.
- Part M consumes `run_state.json` and must not create competing session files.
- Part O may add model-aware and adapter-aware budget behavior later.
- Part Q consumes workspace placeholders later.

Part I does not implement browser automation, CLI AI integration, a VS Code extension, model-aware budgeting, frontend/backend/workspace intelligence, or generated context artifacts.

## Later Part I Batches

Later batches can build on this contract to add representation tiers, budget profiles, lazy outline policy, and richer workspace intelligence while preserving the same artifact names and trust boundaries.
