# Changelog

## 0.4.1 - 2026-07-16

### Added

- Single guided workflow centered on `strata start`, including continuation support for prepared sessions.
- Repository and dependency intelligence for task-relevant files, symbols, imports, routes, dependencies, and likely verification points.
- Framework-aware frontend analysis for JavaScript, TypeScript, React, and Angular projects.
- Backend route and service analysis for Python, JavaScript, TypeScript, and Go services.
- Go support for backend route and relationship analysis.
- Workspace configuration, cross-repository relationships, shared-contract comparison, and workspace dependency graph support.
- User-action entry-point detection and frontend-to-backend journey tracing.
- Budgeted journey context for compact AI handoffs.

### Improved

- Budgeted AI context selection with ranked evidence, representation tiers, and bounded outputs.
- Readiness and diagnostics for workspace and journey intelligence.
- Safe patch review and application workflow, including dry-run review, scope checks, path safety, and explicit apply controls.
- README refresh for the package name, console command, guided workflow, supported targets, safety model, maturity, and limitations.

### Safety

- Generated Strata artifacts remain under `.aidc/` and should not be committed.
- Patch application continues to require explicit intent and validates paths, traversal attempts, symlink escapes, unsafe targets, and unexpected new files.
- Strata does not store API keys in the repository.

### Documentation

- Added release preparation notes, release limitations, and PyPI-safe README links.
- Added user-operated release documentation for validation, build inspection, TestPyPI, production upload, production verification, tagging, and release creation.
- Corrected CLI runtime wording to match Python 3.11, 3.12, and 3.13 support.

### Known limitations

- Controlled real-repository UAT and release hardening continue.
- Journeys are static explanations, not runtime traces.
- Dynamic framework behavior may remain approximate.
- Strata is not yet claimed as a fully production-proven autonomous coding system.
