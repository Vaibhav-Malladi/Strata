# Strata

Strata is a local-first Python CLI tool for understanding repository structure before making code changes.

It scans Python projects, builds a dependency graph, and generates focused reports for humans and AI coding assistants.

Strata does **not** edit code, run autonomous agents, or require cloud services. It produces inspectable repository context that can be used with tools such as Aider, ChatGPT, Claude, GitHub Copilot, and local LLMs.

---

## Status

```text
v0.2
```

Current scope:

- Python repository scanning
- Dependency graph generation
- Project map generation
- Task-focused brief generation
- Dependency health checks
- Cycle detection
- Impact analysis
- Test suggestion mapping
- Preflight reports for AI-assisted edits
- Agent-specific prompt export
- Generated-output status checks

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

---

## Installation

Clone the repository:

```powershell
git clone https://github.com/Vaibhav-Malladi/Strata.git
cd Strata
```

Run the test suite:

```powershell
py tests.py
py tests\run.py
```

Expected output:

```text
All tests passed. (70 tests)
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

Create a pre-edit report for a task:

```powershell
py cli.py preflight "add tests for map command"
```

Generate a prompt for an AI coding assistant:

```powershell
py cli.py agent-prompt "add tests for map command" local
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
```

These files are generated artifacts and normally should not be edited manually.

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

Scans a Python repository and writes:

```text
.aidc/graph.json
```

The graph includes files, imports, classes, functions, unresolved imports, and dependency edges.

---

### Show

```powershell
py cli.py show
py cli.py show <file>
```

Displays either a saved graph summary or details for a specific file from the graph.

Example:

```powershell
py cli.py show tmp_repo/main.py
```

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

The project map summarizes files, symbols, imports, dependencies, and warnings.

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

The task brief identifies files likely to be relevant to a task and includes risks, impact notes, suggested tests, and AI-facing instructions.

Relevance scoring is currently keyword-based.

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

- repository summary
- repository health
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

Possible states:

```text
current
incomplete
stale
```

---

## Recommended Workflow

Before editing:

```powershell
py cli.py scan
py cli.py health
py cli.py preflight "describe the task"
py cli.py agent-prompt "describe the task" local
```

For a specific file change:

```powershell
py cli.py impact path\to\file.py
py cli.py tests-for path\to\file.py
```

After editing:

```powershell
py tests.py
py tests\run.py
py cli.py status
```

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

commands/
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

## Module Overview

| Module | Responsibility |
|---|---|
| `cli.py` | CLI routing |
| `cli_help.py` | Help text |
| `cli_ui.py` | Terminal formatting helpers |
| `cli_core.py` | Shared CLI filesystem and graph helpers |
| `python_parser.py` | Python AST parsing |
| `languages.py` | Source file language routing |
| `scanner.py` | Repository scanning and graph construction |
| `graph.py` | Graph validation |
| `map_writer.py` | Project map generation |
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
imports
import_details
external_imports
unresolved_imports
unresolved_import_details
classes
functions
```

Each dependency edge includes:

```text
from
to
type
import
```

---

## Import Classification

Strata classifies imports as:

| Type | Description |
|---|---|
| Internal | Import resolves to another scanned file |
| External | Import belongs to the Python standard library |
| Unresolved | Import cannot be resolved to a scanned file or standard-library module |

Example:

```python
import helper
import os
import missing_module
```

If `helper.py` exists:

- `helper` becomes an internal dependency
- `os` is recorded as external
- `missing_module` is recorded as unresolved

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

## Limitations

Strata currently does not support:

- JavaScript or TypeScript parsing
- third-party package metadata analysis
- package-aware Python import resolution
- graph visualization
- symbol-level call graph analysis
- automatic code editing
- autonomous agent execution
- configuration files

---

## Design Goals

Strata is intended to remain:

- local-first
- standard-library-only
- lightweight
- inspectable
- agent-neutral
- easy to test
- useful for both humans and AI coding assistants

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
All tests passed. (70 tests)
```

and:

```text
nothing to commit, working tree clean
```

---

## License

No license has been added yet.
