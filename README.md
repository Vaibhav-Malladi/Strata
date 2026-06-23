# Strata

Strata is a local-first repository intelligence CLI for AI-assisted software development.

It scans a codebase, builds a dependency graph, detects important source structure, and generates focused context reports that help humans and AI coding assistants understand a repository before making changes.

Strata does **not** edit code, run autonomous agents, upload repository data, or require cloud services. It produces inspectable local artifacts that can be used with tools such as ChatGPT, Aider, GitHub Copilot, Claude, Cursor, Cline, and local LLMs.

Core idea:

```text
Know your repository before your AI edits it.
```

---

## Status

```text
v0.3-alpha
```

Current scope:

- Python repository scanning
- JavaScript and TypeScript repository scanning
- JSX / TSX file support
- React framework hints
- Angular framework hints
- Python backend route detection
- JavaScript / TypeScript backend route detection
- Backend route map generation
- Dependency graph generation
- Project map generation
- Task-focused brief generation
- Dependency health checks
- Circular dependency detection
- Impact analysis
- Test suggestion mapping
- Preflight reports for AI-assisted edits
- Agent-specific prompt export
- Generated-output status checks

Current test expectation:

```text
All tests passed. (108 tests)
```

---

## What Strata Is For

Strata is designed for developers who use AI coding assistants and want better repository context before editing.

It helps answer:

```text
What files exist?
What imports what?
What routes exist?
What files are relevant to this task?
What could break if this file changes?
What tests should I run?
What context should I give an AI assistant?
```

Strata is especially useful for:

- Python CLI projects
- Python backend projects
- Flask / FastAPI-style APIs
- Node.js backend projects
- Express-style JavaScript APIs
- TypeScript backend projects
- React / Angular frontend projects
- small to medium full-stack repositories
- local LLM workflows
- Aider / ChatGPT / Copilot pre-edit context workflows

---

## What Strata Is Not

Strata is not:

- an autonomous coding agent
- an IDE
- a runtime monitor
- a security scanner
- a replacement for CodeQL, SonarQube, Sourcegraph, Aider, Copilot, or Cursor
- a cloud indexing platform
- a compiler-grade parser
- a production observability tool

Strata is a lightweight local intelligence layer that prepares repository context.

---

## Requirements

- Python 3.10+
- No external Python dependencies

On Windows, use:

```powershell
py
```

Check your Python version:

```powershell
py --version
```

### Windows Fallback

For a quick repo-root test, you can run `.\strata.cmd` from the repository root.

The main public workflow is the editable install shown below with `py -m pip install -e .` and the `strata` console script.

---

## Installation

Recommended install:

```powershell
git clone https://github.com/Vaibhav-Malladi/Strata.git
cd Strata
py -m pip install -e .
strata help
strata status
strata routes
```

This editable install exposes the `strata` console script from anywhere in the environment.

For a quick local Windows fallback, `strata.cmd` still works from the repo root, but it is not the main public install path.

Run the test suite:

```powershell
py tests.py
py tests\run.py
```

Expected output:

```text
All tests passed. (108 tests)
All tests passed. (108 tests)
```

---

## Quick Start

Generate a repository graph:

```powershell
py cli.py scan
```

Generate a project map:

```powershell
py cli.py map
```

Generate a backend route map:

```powershell
py cli.py routes
```

Create a pre-edit report for a task:

```powershell
py cli.py preflight "change user API behavior"
```

Generate a prompt for an AI coding assistant:

```powershell
py cli.py agent-prompt "change user API behavior" local
```

Check generated output status:

```powershell
py cli.py status
```

---

## Generated Outputs

Strata writes generated context files to `.aidc/`:

```text
.aidc/graph.json
.aidc/project_map.md
.aidc/task_brief.md
.aidc/preflight.md
.aidc/agent_prompt.md
.aidc/routes.md
.aidc/routes.json
```

These files are generated artifacts and normally should not be edited manually.

Recommended `.gitignore` entry:

```text
.aidc/
```

---

## CLI Commands

### Help

```powershell
py cli.py help
```

Displays all available commands.

---

### Scan

```powershell
py cli.py scan
py cli.py scan <path>
```

Scans a repository and writes:

```text
.aidc/graph.json
```

The graph includes:

- files
- languages
- imports
- import details
- external imports
- unresolved imports
- dependency edges
- classes
- functions
- TypeScript interfaces
- TypeScript type aliases
- TypeScript enums
- framework hints
- backend routes

---

### Show

```powershell
py cli.py show
py cli.py show <file>
```

Displays either a saved graph summary or details for a specific file from the graph.

Example:

```powershell
py cli.py show src\api.py
```

For files with backend routes, `show` displays route details directly.

---

### Map

```powershell
py cli.py map
py cli.py map <path>
```

Generates:

```text
.aidc/project_map.md
```

The project map summarizes:

- repository summary
- backend routes
- files
- languages
- framework hints
- symbols
- imports
- dependencies
- unresolved import warnings

---

### Routes

```powershell
py cli.py routes
py cli.py routes <path>
```

Generates:

```text
.aidc/routes.md
.aidc/routes.json
```

The route map includes:

- all detected backend routes
- route count
- route file locations
- route source expressions
- duplicate route warnings
- route files with unresolved imports
- AI notes for backend editing

Detected Python backend patterns include:

```python
@app.get("/health")
@router.post("/users")
@app.route("/login", methods=["GET", "POST"])
```

Detected JavaScript / TypeScript backend patterns include:

```javascript
app.get("/health", handler)
router.post("/users", createUser)
router.put("/users/:id", updateUser)
router.delete("/users/:id", deleteUser)
```

---

### Brief

```powershell
py cli.py brief "<task>"
py cli.py brief <path> "<task>"
```

Generates:

```text
.aidc/task_brief.md
```

The task brief identifies files likely to be relevant to a task and includes:

- relevant files
- relevance reasons
- risks
- impact notes
- suggested tests
- AI-facing instructions

Relevance scoring is currently static and keyword-based.

---

### Cycles

```powershell
py cli.py cycles
py cli.py cycles <path>
```

Checks for circular dependencies in the repository graph.

---

### Health

```powershell
py cli.py health
py cli.py health <path>
```

Reports dependency health information, including:

- file count
- edge count
- unresolved imports
- cycle count
- top incoming dependencies
- top outgoing dependencies

---

### Impact

```powershell
py cli.py impact <file>
py cli.py impact <path> <file>
```

Analyzes the likely effect of changing a file.

The report includes:

- direct dependents
- direct dependencies
- transitive dependents
- risk level
- summary

Risk levels are:

```text
low
medium
high
```

---

### Tests For

```powershell
py cli.py tests-for <file>
py cli.py tests-for <path> <file>
```

Suggests verification commands and related test files for a changed file.

Recommended commands are separated from related test files so the output stays runnable.

---

### Preflight

```powershell
py cli.py preflight "<task>"
py cli.py preflight <path> "<task>"
```

Generates:

```text
.aidc/preflight.md
```

The preflight report combines:

- task description
- repository summary
- repository health
- backend route summary
- relevant source files
- relevant test files
- entry points and runners
- impact notes
- verification plan
- AI agent instructions

This is the main command to run before giving a coding task to an AI assistant.

---

### Agent Prompt

```powershell
py cli.py agent-prompt "<task>" <agent>
py cli.py agent-prompt <path> "<task>" <agent>
```

Generates:

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

Prompt styles:

| Agent | Purpose |
|---|---|
| `generic` | Balanced general-purpose coding prompt |
| `local` | Compact prompt for smaller local models |
| `aider` | Concise edit-focused prompt |
| `chatgpt` | Fuller context prompt for ChatGPT-style assistants |

---

### Status

```powershell
py cli.py status
py cli.py status <path>
```

Checks whether generated Strata outputs are present and current.

Tracked generated files:

```text
.aidc/graph.json
.aidc/project_map.md
.aidc/task_brief.md
.aidc/preflight.md
.aidc/agent_prompt.md
.aidc/routes.md
.aidc/routes.json
```

Possible states:

```text
current
incomplete
stale
```

---

## Supported Languages and File Types

### Python

Supported extensions:

```text
.py
```

Detected:

- imports
- import line numbers
- classes
- functions
- async functions
- syntax errors
- read errors
- FastAPI-style routes
- Flask-style routes
- APIRouter-style routes

Python backend route examples:

```python
@app.get("/health")
def health_check():
    pass

@router.post("/users")
def create_user():
    pass

@app.route("/login", methods=["GET", "POST"])
def login():
    pass
```

---

### JavaScript

Supported extensions:

```text
.js
.jsx
.mjs
.cjs
```

Detected:

- ES imports
- side-effect imports
- CommonJS `require(...)`
- functions
- arrow functions
- function expressions
- classes
- exports
- relative import edges
- index file resolution
- package imports
- backend routes

JavaScript backend route examples:

```javascript
app.get("/health", healthCheck);
router.post("/users", createUser);
router.put("/users/:id", updateUser);
router.delete("/users/:id", deleteUser);
```

---

### TypeScript

Supported extensions:

```text
.ts
.tsx
```

Detected:

- imports
- `require(...)`
- functions
- arrow functions with return type annotations
- classes
- interfaces
- type aliases
- enums
- exports
- relative import edges
- index file resolution
- package imports
- React hints
- Angular hints
- backend routes

TypeScript examples:

```typescript
import { Component } from "@angular/core";

export interface User {}

type UserId = string;

export enum Role {
    Admin
}

export class UserService {}
```

---

## Framework Hints

Strata can detect lightweight framework hints.

React hints include patterns such as:

```text
react imports
React usage
useState
useEffect
TSX / JSX-style files
```

Angular hints include patterns such as:

```text
@Component
@Injectable
@NgModule
@Directive
@Pipe
@angular/core imports
```

Framework detection is intentionally lightweight and static.

---

## Import Classification

Strata classifies imports as:

| Type | Description |
|---|---|
| Internal | Import resolves to another scanned file |
| External | Import is treated as an external package or standard library import |
| Unresolved | Import cannot be resolved to a scanned file or known external category |

Python example:

```python
import helper
import os
import missing_module
```

If `helper.py` exists:

- `helper` becomes an internal dependency
- `os` is recorded as external
- `missing_module` is recorded as unresolved

JavaScript / TypeScript example:

```typescript
import React from "react";
import { helper } from "./helper";
import { missing } from "./missing";
```

If `helper.ts` exists:

- `react` is recorded as external
- `./helper` becomes an internal dependency
- `./missing` is recorded as unresolved

---

## Recommended Workflow

Before editing:

```powershell
py cli.py scan
py cli.py health
py cli.py routes
py cli.py preflight "describe the task"
py cli.py agent-prompt "describe the task" local
```

For a specific file change:

```powershell
py cli.py show path\to\file.py
py cli.py impact path\to\file.py
py cli.py tests-for path\to\file.py
```

For backend/API work:

```powershell
py cli.py routes
py cli.py preflight "change user API behavior"
py cli.py show path\to\api_file.py
```

After editing:

```powershell
py tests.py
py tests\run.py
py cli.py status
```

Future versions will add stronger post-edit verification.

---

## Project Structure

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
routes.py

commands/
  __init__.py
  scan_command.py
  map_command.py
  routes_command.py
  brief_command.py
  preflight_command.py
  cycles_command.py
  health_command.py
  impact_command.py
  tests_for_command.py
  show_command.py
  agent_prompt_command.py
  status_command.py

parsers/
  __init__.py
  python_parser.py
  javascript_parser.py
  typescript_parser.py

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
  test_backend_map.py
  test_brief.py
  test_brief_impact.py
  test_cycles.py
  test_health.py
  test_impact.py
  test_test_mapper.py
  test_preflight.py
  test_agent_export.py
  test_status.py
  test_languages.py
  test_javascript_parser.py
  test_typescript_parser.py
  test_multilang_scanner.py
  test_routes.py

tmp_repo/
  helper.py
  main.py
```

---

## Module Overview

| Module | Responsibility |
|---|---|
| `cli.py` | CLI routing |
| `cli_help.py` | Help text |
| `cli_ui.py` | Terminal formatting helpers |
| `cli_core.py` | Shared CLI filesystem and graph helpers |
| `python_parser.py` | Python AST parsing and Python backend route detection |
| `languages.py` | Source file language detection and parser routing |
| `scanner.py` | Repository scanning, import classification, and graph construction |
| `graph.py` | Graph validation |
| `map_writer.py` | Project map generation |
| `routes.py` | Backend route collection, route map reports, duplicate route warnings |
| `brief.py` | Task brief generation and relevance scoring |
| `brief_impact.py` | Impact notes for briefs |
| `cycles.py` | Circular dependency detection |
| `health.py` | Dependency health reporting |
| `impact.py` | File impact analysis |
| `test_mapper.py` | Test recommendation mapping |
| `preflight.py` | Combined pre-edit report generation |
| `agent_export.py` | Agent-specific prompt generation |
| `status.py` | Generated output status checks |

---

## Graph Model

The generated graph contains:

```text
schema_version
root
files
edges
```

Each file entry may include:

```text
path
language
framework
imports
import_details
external_imports
unresolved_imports
unresolved_import_details
classes
functions
interfaces
types
enums
exports
routes
error
```

Each route entry may include:

```text
method
path
line
source
```

Each dependency edge includes:

```text
from
to
type
import
```

---

## Ignored Directories

Strata ignores:

```text
.git
.venv
venv
__pycache__
.aidc
```

---

## Current Limitations

Strata currently does not provide:

- Java parsing
- Rust parsing
- package-aware Python dependency resolution
- full TypeScript AST parsing
- full JavaScript AST parsing
- symbol-level call graph analysis
- runtime tracing
- log analysis
- database schema analysis
- security vulnerability analysis
- graph visualization
- autonomous code editing
- cloud indexing
- CI/CD integration

The JavaScript and TypeScript parsers are intentionally lightweight and regex-based.

---

## Design Goals

Strata is intended to remain:

- local-first
- standard-library-only by default
- lightweight
- transparent
- inspectable
- agent-neutral
- easy to test
- useful for humans
- useful for small local models
- useful before AI-assisted edits

---

## Roadmap

Near-term:

```text
v0.3-alpha
- finish Python + JS/TS full-stack repository intelligence
- polish route map support
- update documentation
- tag release
```

Next major direction:

```text
v0.4 / V3
- snapshot before editing
- graph diff after editing
- verify report
- route changes after editing
- new unresolved import detection
- new cycle detection
- commit readiness summary
```

Future idea:

```text
Preflight before editing. Verify after editing.
```

---

## Verification Checklist

Before tagging or releasing:

```powershell
py tests.py
py tests\run.py
py cli.py help
py cli.py scan tmp_repo
py cli.py show tmp_repo/main.py
py cli.py map tmp_repo
py cli.py routes tmp_repo
py cli.py brief "change helper behavior"
py cli.py cycles tmp_repo
py cli.py health tmp_repo
py cli.py impact tmp_repo helper.py
py cli.py tests-for map_writer.py
py cli.py preflight "add map command tests"
py cli.py agent-prompt "add agent prompt command" local
py cli.py status
git status
```

Expected:

```text
All tests passed. (108 tests)
All tests passed. (108 tests)
```

---

## License

No license has been added yet.
