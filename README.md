# Strata

Strata is a local repository-intelligence and safe AI coding workflow that builds focused context, traces related code, and helps review and apply AI-generated changes with clear scope controls.

**Status:** Strata is feature-complete for its current roadmap and has extensive automated validation. It is entering controlled real-repository UAT and release hardening; public production hardening is still in progress.

## Why Strata

AI coding tools often see too little context, too much context, or the wrong context. Large repositories make that problem worse: important frontend, backend, test, workspace, and configuration relationships are easy to miss, while dumping the whole repo wastes tokens and can confuse the model.

Strata is built around a simple promise:

Understand the repository first. Give the AI only the most relevant context. Review and apply changes safely.

It combines repository intelligence, bounded context packs, guided workflow state, and patch review so developers can keep AI-assisted changes scoped, explainable, and intentional.

## How It Works

1. Scan and understand the repository structure, files, symbols, imports, routes, and likely verification points.
2. Select and rank task-relevant files, symbols, relationships, and related tests.
3. Build a compact context pack for the configured AI workflow.
4. Review the proposed patch against expected scope, related files, and safety checks.
5. Apply intentionally, then verify through Strata's reports and your project checks.

Workspace and journey intelligence can connect related repositories and trace application flows across UI actions, API or message boundaries, backend handlers, services, and response paths. These are static explanations with confidence and gaps, not runtime traces.

## Quick Start

The PyPI package is `strata-repo-intel`; the CLI command is `strata`. Strata itself requires Python 3.13 or newer. The repositories it analyzes can target older runtimes.

Recommended install on Windows PowerShell:

```powershell
pipx install strata-repo-intel
strata doctor install
```

From the repository you want Strata to understand:

```powershell
cd path\to\your-repository
strata setup
strata start
```

`strata start` is the normal entry point. It shows current workflow status and one recommended next step. In an interactive terminal, it can continue step by step; repository-changing actions still require confirmation.

If you prefer the PowerShell bootstrap installer:

```powershell
iwr https://raw.githubusercontent.com/Vaibhav-Malladi/Strata/main/install-strata.ps1 -OutFile install-strata.ps1
powershell -ExecutionPolicy Bypass -File .\install-strata.ps1
```

For local development from a checkout:

```powershell
py -m pip install -e .
strata doctor install
strata start
```

Generated Strata files live under `.aidc/`. Add `.aidc/` to the analyzed repository's `.gitignore`; context packs, prompts, patches, and reports may contain code excerpts or task details.

## Core Capabilities

### Repository Intelligence

Strata discovers files, symbols, imports, routes, dependencies, framework hints, likely tests, and task-relevant starting points. It favors deterministic static analysis, bounded evidence, and explainable confidence over opaque indexing.

### Focused AI Context

Context packs are budget-aware and task-ranked. Strata selects relevant source excerpts, symbols, related files, test hints, verification guidance, and relationship evidence while keeping Part I context artifacts as the token firewall. Representation tiers and caps help keep large repositories usable with both strong and smaller models.

### Safe Patch Workflow

Strata is patch-first by default. It prepares context, collects or records an AI patch, reviews the patch, supports dry runs, blocks unsafe paths, warns about dirty trees or stale patches, controls allowed new files, and applies changes only through explicit confirmation. Application uses repository-relative paths, symlink escape protection, rollback on failure, and atomic file replacement where supported.

### Frontend and Backend Understanding

Strata analyzes Python, JavaScript, TypeScript, Angular, React, and Go code. It can identify components, hooks, services, routes, API clients, backend route handlers, services, repository/database calls, response handling, and API boundaries with confidence-labeled evidence.

### Workspace Intelligence

For applications split across repositories, Strata can represent related repositories, roles, explicit relationships, shared contracts, cross-repository references, and workspace dependency graphs. Workspace intelligence is designed to enrich context without silently inventing authoritative relationships.

### User Journey Intelligence

Strata can explain user-facing actions as static journeys: UI entry points, frontend flow, API or message boundaries, backend handlers and services, data or external calls, response paths, confidence, diagnostics, and unresolved gaps. Journeys help an AI see the shape of a change without pretending to execute the application.

## Supported Targets

Strata currently analyzes:

- Python
- JavaScript
- TypeScript
- Angular
- React
- Go

Strata itself is implemented primarily in Python. Java and Rust analysis are not currently supported. Some JavaScript, TypeScript, and framework inference is intentionally approximate, convention-based, and confidence-labeled.

## Safety Model

Strata is designed to assist, not silently take control.

It runs locally by default, builds bounded selected context, keeps generated artifacts under `.aidc/`, and uses explicit review before apply. Patch validation checks for malformed diffs, absolute paths, traversal attempts, dangerous targets, symlink escapes, blocked new files, and scope mismatches. `strata apply --dry-run` validates without changing files; `strata apply` requires explicit intent and refuses to proceed on a dirty tree.

Strata does not commit or push. It does not guarantee a correct AI patch. Developers remain responsible for reviewing `git diff`, running project checks, and deciding what lands.

Secrets should remain in your machine or user environment. Strata stores environment variable names for API keys, not secret values in the repository configuration.

## AI And Model Compatibility

Strata is adapter-neutral. It can support manual browser workflows, CLI-based assistants, IDE-oriented workflows, local models through Ollama, command adapters such as Codex CLI or Aider, and OpenAI-compatible HTTP endpoints.

The important design point is that users should not have to redescribe the model for every task. Strata uses configured adapter and workflow settings, then builds bounded context that remains useful across different model strengths and across model changes between sessions.

## Current Maturity

| Area | Status |
| --- | --- |
| Current roadmap implementation | Complete |
| Automated tests and safety gate | Strong |
| Synthetic multi-language coverage | Complete |
| Controlled real-repository UAT | Next |
| Public production release | Not yet |

Strata should be treated as ready for controlled real-repository UAT, not as a fully production-proven autonomous coding system.

## Limitations

Static analysis cannot resolve every runtime path, dynamic framework convention, dependency-injection edge, generated route, or reflection-heavy call. JavaScript, TypeScript, and framework extraction may be approximate. User journeys are static explanations, not runtime traces. Real-repository UAT is still pending.

Strata reduces context waste and review risk, but it does not eliminate hallucinations or guarantee that an AI-generated patch is correct. Review and validation remain part of the workflow.

## Documentation

- [Runtime compatibility](docs/runtime-compatibility.md)
- [V6 release notes](docs/v6_release_notes.md)
- [V7 roadmap](docs/v7_roadmap.md)
- [Frontend intelligence roadmap](docs/roadmap/frontend-intelligence.md)
- [Backend intelligence foundation](docs/roadmap/backend-intelligence-foundation.md)
- [Workspace intelligence roadmap](docs/roadmap/workspace-intelligence.md)
- [User journey intelligence roadmap](docs/roadmap/user-flow-journey-intelligence.md)

For CLI help, run:

```powershell
strata help
strata help setup
strata help ask
```

## Contributing

Strata does not currently have a separate contributing guide. For now:

- Open an issue before broad architectural changes.
- Keep changes focused and easy to review.
- Preserve safety checks and architecture invariants.
- Add focused tests for behavior changes.
- Avoid broad refactors mixed with feature or documentation work.

## License

Strata is released under the [MIT License](LICENSE).
