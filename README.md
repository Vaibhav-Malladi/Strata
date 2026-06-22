# Strata

Strata is a lightweight repository structure and dependency inspector.

It scans a Python codebase, extracts files/classes/functions/imports, builds a dependency graph, and saves the result to:

```text
.aidc/graph.json
```

Strata is currently at:

```text
MVP v0.1
```

---

## What Strata Does

Strata helps answer questions like:

```text
What files exist in this repo?
Which functions and classes are inside each file?
Which files import other local files?
Which imports are external or unresolved?
Where are unresolved imports located?
```

It is designed to become the foundation for a future AI coding assistant that can understand a project before editing it.

---

## Current Scope

Strata v0.1 supports:

```text
Python repository scanning
Python AST parsing
File/function/class extraction
Import extraction
Internal dependency edge detection
Standard-library import classification
Unresolved import detection
Unresolved import line numbers
Graph validation
Pretty CLI output
Colored terminal output
Scanning current folder
Scanning a custom folder path
Saved graph inspection
Single-file graph inspection
No external dependencies
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

---

## Commands

### Show help

```powershell
py cli.py help
```

### Scan the current project

```powershell
py cli.py scan
```

This scans the current folder and writes:

```text
.aidc/graph.json
```

### Scan a specific folder

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

### Show the saved graph summary

```powershell
py cli.py show
```

### Show one file from the graph

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

Warnings
─────────────────
  Unresolved imports found in tmp_repo\main.py:
  ! missing_module at line 3

Outgoing dependencies
─────────────────────
  tmp_repo\main.py -> tmp_repo\helper.py [helper]

Incoming dependencies
─────────────────────
  none
```

---

## Running Tests

Run:

```powershell
py tests.py
```

Expected output:

```text
All tests passed.
```

Recommended full verification:

```powershell
py tests.py
py cli.py help
py cli.py scan
py cli.py show
py cli.py show tmp_repo/main.py
py cli.py scan tmp_repo
py cli.py show
```

---

## Project Files

```text
cli.py
```

Command-line interface for scanning and viewing the graph.

```text
scanner.py
```

Walks the repository, scans supported files, resolves imports, and builds dependency edges.

```text
python_parser.py
```

Parses Python files using the standard-library `ast` module.

```text
languages.py
```

Routes files to the correct parser based on file extension.

```text
graph.py
```

Validates graph structure and catches broken graph data.

```text
tests.py
```

Lightweight no-framework test runner using `assert`.

```text
tmp_repo/
```

Small controlled test repository used by the test suite.

---

## Output File

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

Each file entry contains:

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

Imports that point to another scanned file in the repo.

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

Strata v0.1 does not yet support:

```text
JavaScript or TypeScript parsing
Third-party package detection
Package-aware Python import resolution
Graph visualization
Function-level dependency edges
AI-generated summaries
Memory or abstraction layers
Automatic code editing
Configuration files
```

These are intentionally deferred until after MVP v0.1.

---

## MVP v0.1 Status

Strata MVP v0.1 is complete when:

```text
py tests.py
```

prints:

```text
All tests passed.
```

and the following commands work:

```powershell
py cli.py help
py cli.py scan
py cli.py scan tmp_repo
py cli.py show
py cli.py show tmp_repo/main.py
```

Current status:

```text
MVP v0.1 complete
```
