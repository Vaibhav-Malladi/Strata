# Strata

**Know before you edit.**

Strata is a local-first repository intelligence layer for AI coding agents.

It scans a Python codebase, builds a dependency graph, and generates focused context that can be used before editing code with tools like Aider, ChatGPT, Claude, Copilot, local models, or other AI coding assistants.

Strata is **not** an autonomous coding agent.

It does not edit files by itself.  
It helps humans and AI coding tools understand a repository before making changes.

---

## Current Version

```text
Strata v0.2-alpha
```

This is the current V2 feature set.  
Do not treat this as final `v0.2` until final smoke checks and release tagging are complete.

---

## What Strata Does

Strata helps answer questions like:

```text
What files exist in this repo?
Which functions and classes are inside each file?
Which files import other local files?
Which imports are external or unresolved?
Which files are most relevant for this task?
What might break if I edit this file?
Which tests should I run after changing this file?
Are there circular dependencies?
Is the repository dependency graph healthy?
Are generated Strata context files missing or stale?
What prompt should I give to an AI coding assistant?
```

Strata is designed for:

```text
local-first AI coding workflows
small local model support
low-token context generation
safe pre-edit planning
repository structure inspection
impact analysis
verification planning
agent-ready prompt generation
```

---

## Core Positioning

```text
Strata tells your coding assistant what it needs to know before it edits.
```

It is useful when working with:

```text
Aider
ChatGPT
Claude
GitHub Copilot
local LLMs
manual code review
repository refactoring
test planning
```

---

## Requirements

Use Python 3.10 or newer.

On Windows, use:

```powershell
py
```

instead of:

```powershell
python
```

because `python` may point to an older installed version.

Check your version:

```powershell
py --version
```

Strata currently uses only the Python standard library.

No external dependencies are required.

---

## Quick Start

From the project root:

```powershell
py cli.py help
py cli.py scan
py cli.py map
py cli.py health
py cli.py preflight "add tests for map command"
```

Generated files are written under:

```text
.aidc/
```

---

## Generated Files

Strata can generate:

```text
.aidc/graph.json
.aidc/project_map.md
.aidc/task_brief.md
.aidc/preflight.md
.aidc/agent_prompt.md
```

These files are generated context outputs and should normally not be edited manually.

---

## Commands

### Show help

```powershell
py cli.py help
```

Shows all available commands.

---

### Scan repository

```powershell
py cli.py scan
```

Scan the current folder and write:

```text
.aidc/graph.json
```

Scan a specific folder:

```powershell
py cli.py scan tmp_repo
```

Example output:

```text
Scan complete
──────────────────────
  Output             .aidc\graph.json
  Root               tmp_repo
  Files              2
  Edges              1
  Warnings           1 unresolved import(s)
```

---

### Show saved graph summary

```powershell
py cli.py show
```

Shows summary information from the saved graph.

---

### Show one file from graph

```powershell
py cli.py show tmp_repo/main.py
```

Example output:

```text
File details
────────────
  Path               tmp_repo\main.py
  Language           python
  Classes            App
  Functions          run
  Imports            os, helper, missing_module
  External imports   os
  Unresolved imports missing_module
```

---

### Generate project map

```powershell
py cli.py map
```

Generate:

```text
.aidc/project_map.md
```

For a specific folder:

```powershell
py cli.py map tmp_repo
```

The project map includes:

```text
repository summary
file list
symbols
imports
external imports
unresolved imports
incoming dependencies
outgoing dependencies
warnings
```

---

### Generate task brief

```powershell
py cli.py brief "change helper behavior"
```

Generate:

```text
.aidc/task_brief.md
```

For a specific folder:

```powershell
py cli.py brief tmp_repo "change helper behavior"
```

The task brief includes:

```text
task summary
relevant files
relevance reasons
risks
impact notes
suggested tests
AI agent instructions
```

Current relevance scoring is keyword-based.  
It matches task words against file paths, symbols, imports, and known command-related terms.

---

### Check dependency cycles

```powershell
py cli.py cycles
```

For a specific folder:

```powershell
py cli.py cycles tmp_repo
```

Reports circular dependencies detected in the repository graph.

---

### Check dependency health

```powershell
py cli.py health
```

For a specific folder:

```powershell
py cli.py health tmp_repo
```

Reports:

```text
file count
edge count
unresolved imports
cycle count
top incoming dependencies
top outgoing dependencies
overall dependency health status
```

---

### Analyze impact of changing a file

```powershell
py cli.py impact helper.py
```

For a specific folder:

```powershell
py cli.py impact tmp_repo helper.py
```

Impact analysis reports:

```text
direct dependents
direct dependencies
transitive dependents
risk level
summary
```

Risk levels:

```text
low
medium
high
```

---

### Suggest tests for a changed file

```powershell
py cli.py tests-for map_writer.py
```

For a specific folder:

```powershell
py cli.py tests-for tmp_repo helper.py
```

This recommends verification commands and likely related test files.

Example command suggestions may include:

```powershell
py tests.py
py cli.py map tmp_repo
py cli.py health tmp_repo
```

---

### Generate preflight report

```powershell
py cli.py preflight "add tests for map command"
```

For a specific folder:

```powershell
py cli.py preflight tmp_repo "change helper behavior"
```

Generate:

```text
.aidc/preflight.md
```

Preflight is the main V2 super-command.

It combines:

```text
repository summary
repository health
relevant source files
relevant test files
entry points / runners
impact notes
verification plan
AI agent instructions
```

Use this before giving an AI coding assistant a task.

---

### Generate agent-specific prompt

```powershell
py cli.py agent-prompt "add tests for map command" local
```

For a specific folder:

```powershell
py cli.py agent-prompt tmp_repo "change helper behavior" aider
```

Generate:

```text
.aidc/agent_prompt.md
```

Supported agents:

```text
generic
local
aider
chatgpt
```

Agent prompt styles:

```text
generic  -> balanced general-purpose prompt
local    -> compact prompt for smaller local models
aider    -> concise edit-focused prompt
chatgpt  -> fuller context prompt for ChatGPT-style assistants
```

This command helps adapt Strata context to different coding assistant workflows.

---

### Check generated output status

```powershell
py cli.py status
```

For a specific folder:

```powershell
py cli.py status tmp_repo
```

Reports whether generated Strata outputs are:

```text
current
incomplete
stale
```

The status command checks:

```text
.aidc/graph.json
.aidc/project_map.md
.aidc/task_brief.md
.aidc/preflight.md
.aidc/agent_prompt.md
```

If generated files are missing or older than source files, Strata recommends regeneration steps.

---

## Recommended Workflow

Before editing a repository with an AI coding assistant:

```powershell
py cli.py scan
py cli.py health
py cli.py preflight "describe your task here"
py cli.py agent-prompt "describe your task here" local
```

After editing:

```powershell
py tests.py
py tests\run.py
py cli.py status
```

For a specific changed file:

```powershell
py cli.py impact path\to\file.py
py cli.py tests-for path\to\file.py
```

---

## Running Tests

Run the compatibility test entry point:

```powershell
py tests.py
```

Run the modular test runner directly:

```powershell
py tests\run.py
```

Expected current output:

```text
All tests passed. (70 tests)
```

The exact number may increase as new features are added.

Recommended verification:

```powershell
py tests.py
py tests\run.py
py cli.py help
py cli.py scan tmp_repo
py cli.py show tmp_repo/main.py
py cli.py map tmp_repo
py cli.py brief "change helper behavior"
py cli.py cycles tmp_repo
py cli.py health tmp_repo
py cli.py impact tmp_repo helper.py
py cli.py tests-for map_writer.py
py cli.py preflight "add map command tests"
py cli.py agent-prompt "add agent prompt command" local
py cli.py status
```

---

## Project Structure

Approximate source layout:

```text
cli.py
cli_help.py
cli_ui.py
cli_core.py

python_parser.py
languages.py
scanner.py
graph.py

map_writer.py
brief.py
brief_impact.py
cycles.py
health.py
impact.py
test_mapper.py
preflight.py
agent_export.py
status.py

commands/
  __init__.py
  scan_command.py
  map_command.py
  brief_command.py
  preflight_command.py
  cycles_command.py
  health_command.py
  impact_command.py
  tests_for_command.py
  show_command.py
  agent_prompt_command.py
  status_command.py

tests.py

tests/
  __init__.py
  helpers.py
  run.py
  test_parser.py
  test_scanner.py
  test_graph.py
  test_cli_core.py
  test_map_writer.py
  test_brief.py
  test_brief_impact.py
  test_cycles.py
  test_health.py
  test_impact.py
  test_test_mapper.py
  test_preflight.py
  test_agent_export.py
  test_status.py

tmp_repo/
  helper.py
  main.py
```

---

## Main Module Responsibilities

### `cli.py`

Routes command-line arguments to command handlers.

### `cli_help.py`

Prints CLI usage and command help.

### `cli_ui.py`

Shared terminal formatting helpers.

### `cli_core.py`

Shared CLI filesystem and graph helpers.

### `python_parser.py`

Parses Python files using the standard-library `ast` module.

Detects:

```text
imports
classes
functions
syntax errors
line numbers
```

### `languages.py`

Routes supported source files to the correct parser.

Currently Python only.

### `scanner.py`

Walks a repository and builds graph data.

It detects:

```text
Python files
classes
functions
imports
internal dependencies
external imports
unresolved imports
```

### `graph.py`

Validates graph structure and schema.

### `map_writer.py`

Generates `.aidc/project_map.md`.

### `brief.py`

Generates task-specific context and ranks relevant files.

### `brief_impact.py`

Adds impact notes to task briefs.

### `cycles.py`

Finds circular dependencies.

### `health.py`

Generates dependency health summaries.

### `impact.py`

Analyzes the impact of changing a file.

### `test_mapper.py`

Suggests verification commands for changed files.

### `preflight.py`

Generates the combined pre-edit report.

### `agent_export.py`

Generates agent-specific prompts.

### `status.py`

Checks whether generated Strata outputs are missing or stale.

---

## Graph Output

After scanning, Strata writes:

```text
.aidc/graph.json
```

The graph contains:

```text
schema_version
root
files
edges
```

Each file entry may contain:

```text
path
language
imports
import_details
external_imports
unresolved_imports
unresolved_import_details
classes
functions
```

Each dependency edge contains:

```text
from
to
type
import
```

---

## Import Classification

Strata classifies imports into three groups.

### Internal imports

Imports that point to another scanned file in the repository.

Example:

```python
import helper
```

If `helper.py` exists, Strata creates an edge:

```text
main.py -> helper.py
```

### External imports

Imports from the Python standard library.

Example:

```python
import os
import json
import sys
```

These are recorded as external imports and do not create dependency edges.

### Unresolved imports

Imports that cannot be matched to scanned files or the standard library.

Example:

```python
import missing_module
```

These are recorded with line numbers:

```text
missing_module at line 3
```

---

## Ignored Folders

Strata ignores common generated or environment folders:

```text
.git
.venv
venv
__pycache__
.aidc
```

---

## Current Limitations

Strata currently focuses on Python repositories.

It does not yet support:

```text
JavaScript or TypeScript parsing
third-party package metadata analysis
package-aware Python import resolution
graph visualization
symbol-level call graph analysis
automatic code editing
cloud indexing
autonomous agent execution
configuration files
```

These are intentionally deferred.

---

## Design Principles

Strata should remain:

```text
local-first
standard-library-only
lightweight
transparent
agent-neutral
incremental
inspectable
easy to test
easy to reason about
```

Development priorities:

```text
practical repository understanding
low hallucination risk
small local model compatibility
low token usage
safe AI-assisted editing
repeatable verification
```

---

## Release Status

Current status:

```text
v0.2-alpha feature set complete through V2.6
```

Before tagging final `v0.2`, run final smoke checks and confirm a clean Git state.

Do not tag final `v0.2` until:

```text
README is updated
tests pass
CLI smoke checks pass
git status is clean
release tag is created and pushed
```

Planned final tag:

```powershell
git tag v0.2
git push origin v0.2
```
