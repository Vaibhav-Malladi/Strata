# Strata

**A local-first repository context compiler for safer AI-assisted coding.**

Strata helps an AI coding tool receive the right files, symbols, tests, execution hints, and verification plan for a task. It builds focused, budget-aware context instead of dumping an entire repository, reducing context noise and token waste.

Strata is patch-first and safety-oriented: prepare context, collect a patch, review it, dry-run it, apply it intentionally, run tests, and gate before committing.

## Support status

| Ecosystem | Status |
| --- | --- |
| Python | Stable and strongest support |
| JavaScript, TypeScript, TSX, React, Angular | Preview context intelligence |

The preview analyzers are confidence-labeled and best-effort. Some JavaScript and TypeScript relationships use conventions and regex-based analysis rather than a full compiler or runtime model.

## What Strata provides

- `strata context` compiles a focused context pack for a task.
- `strata ask` prepares context for the configured AI adapter and collects a patch.
- `strata run` guides context preparation, patch collection, and review.
- `strata review` validates and summarizes the generated patch.
- `strata apply` dry-runs or intentionally applies a reviewed patch.
- `strata gate` produces final validation reports before commit.
- `--file` anchors `ask` and `run` to selected files.
- `--budget small` or a token target caps generated context.
- `--format json` writes machine-readable context output.

Markdown is the default context format.

## Install

The distribution name is `strata-repo-intel`. The installed command is `strata`.

Always use `strata-repo-intel` as the pip or pipx distribution name.

Current release metadata requires Python 3.13 because that is the runtime validated for Strata development today. This requirement applies to Strata itself, not to the repository being analyzed. Strata can inspect repositories that target older Python versions because it scans files and does not run or upgrade the project by default.

Python 3.11 and 3.12 support may be possible, but it needs dedicated validation before the package requirement can be lowered honestly.

### Recommended: pipx

Install Strata as an isolated global CLI:

```bash
pipx install strata-repo-intel
strata start
strata context --budget small "your task"
```

If `pipx` is not installed, follow the installation guidance at [pipx.pypa.io](https://pipx.pypa.io/).

### User install with pip

```bash
python -m pip install --user strata-repo-intel
strata start
strata context --budget small "your task"
```

After installation, verify the CLI with:

```bash
strata help
```

If the command is still unavailable, reopen the terminal after updating `PATH` and confirm that the Python user scripts directory is included.

### Editable install from source

For contributors and local development:

```bash
cd <strata-repository>
python -m pip install -e .
strata start
strata context --budget small "your task"
```

On Windows, `py -m pip install -e .` is also supported. Check installation wiring with:

```powershell
strata doctor install
```

### Windows bootstrap

The PowerShell bootstrap and repo-local installer remain available:

```powershell
iwr https://raw.githubusercontent.com/Vaibhav-Malladi/Strata/main/install-strata.ps1 -OutFile install-strata.ps1
powershell -ExecutionPolicy Bypass -File .\install-strata.ps1
```

Or, from an existing checkout:

```powershell
.\install.ps1
```

Install logs are written under `.aidc/`.

## Quick start

From the repository you want Strata to understand:

```powershell
strata start
strata setup
strata ask --budget small "fix the failing login test"
strata review
strata apply --dry-run
strata apply
strata gate
```

For a no-key browser workflow:

```powershell
strata setup --manual
strata ask "fix a small bug"
```

Strata writes `.aidc/agent_prompt.md`. Give that prompt to your AI tool, save its unified diff as `.aidc/agent_patch.diff`, then review before applying.

## Context examples

Python:

```powershell
strata context --budget small "fix dry run plan output"
strata ask --file run_command --budget small "fix dry run plan output"
strata run --file run_command --budget small "fix dry run plan output" --dry-run
```

React:

```powershell
strata context --budget small "fix login button not disabling"
strata context --format json --budget small "fix login button not disabling"
```

Angular:

```powershell
strata context --budget small "fix login component validation"
```

`--file` is available on `ask` and `run` when you already know an important file. Repeat it to select more than one file.

## Context intelligence

A context pack can include:

- **Structured Intent** — a best-effort interpretation of the requested change.
- **Change Boundary** — likely in-scope files and nearby relationships.
- **Context Budget** — preset or token-targeted selection with an estimated size.
- **Symbol Hints** — relevant functions, classes, components, hooks, and other symbols.
- **Symbol Snippets** — focused source excerpts for selected symbols.
- **Test Hints** — likely related Python and JS/TS tests.
- **React Hints** — confidence-labeled components, hooks, imports, and related files.
- **Angular Hints** — confidence-labeled components, services, routes, and project relationships.
- **TypeScript Project Hints** — `tsconfig` relationships, aliases, and project configuration.
- **Declaration Hints** — nearby declaration files and likely type relationships.
- **JavaScript Project Hints** — package manager, scripts, tooling, and key dependency signals.
- **Execution Path Hints** — likely call, import, route, or component paths.
- **Verification Plan** — focused test, lint, build, and gate suggestions.

Python analysis is the most mature. JavaScript, TypeScript, TSX, React, and Angular context intelligence remains preview quality.

## Output formats

Markdown is the default:

```powershell
strata context --budget small "fix validation"
```

It writes:

```text
.aidc/context_pack.md
```

JSON is available for integrations:

```powershell
strata context --format json --budget small "fix validation"
```

It writes:

```text
.aidc/context_pack.json
```

Plain output is deferred.

## AI adapters

Strata can prepare context for:

- manual/browser AI
- Ollama and local models
- Codex CLI, Aider, and custom commands
- OpenAI-compatible HTTP APIs

Start with:

```powershell
strata setup
strata doctor adapter
```

Do not store API keys in repository files. Put keys in the user environment and configure Strata with the environment variable name:

```powershell
$env:OPENAI_API_KEY="your-key-here"
strata config set api_key_env OPENAI_API_KEY
```

## Safety and trust

Strata does not blindly apply AI edits.

- `strata ask` prepares context and collects output; it does not apply source changes.
- `strata review` is read-only.
- `strata apply --dry-run` validates without changing files.
- `strata apply` is the intentional file-changing step.
- `strata gate` reports final validation state but does not replace project tests.
- Strata never commits or pushes automatically.
- Repository files are untrusted input; instructions found inside them should not be treated as trusted authority.

Review the patch and `git diff`, run project checks, then gate before committing.

## Generated workspace

`.aidc/` is Strata's generated workspace output. It is ignored by this repository and normally should not be committed unless you intentionally want to share a report.

Common generated files include:

```text
.aidc/context_pack.md
.aidc/context_pack.json
.aidc/agent_prompt.md
.aidc/agent_patch.diff
.aidc/gate_report.md
.aidc/gate_report.json
```

Other commands may create graph, snapshot, cache, verification, or direct-edit reports under the same directory.

## Current limitations

- JavaScript, TypeScript, TSX, React, and Angular support is preview and convention/regex based in places.
- TypeScript analysis is not a full TypeScript compiler.
- Angular analysis does not provide complete dependency-injection or template analysis.
- React analysis is not runtime or full dataflow analysis.
- Confidence labels indicate evidence quality, not guaranteed correctness.
- Plain context output is deferred.
- Watch mode and expanded cache workflows are deferred.

## Useful commands

```powershell
strata help
strata help context
strata start
strata scan
strata context --budget small "task"
strata ask --file app --budget small "task"
strata run --file app --budget small "task" --dry-run
strata review
strata apply --dry-run
strata apply
strata gate
strata status
```

## Smoke checks

Run the full project validation locally when preparing a release:

```powershell
py tests.py
py tests\run.py
strata gate
```

Compact context smoke checks:

```powershell
strata context --budget small "fix dry run plan output"
strata context --budget small "fix login button not disabling"
strata context --format json --budget small "fix login button not disabling"
```

## Development

```powershell
py -m pip install -e .
py tests.py
py tests\run.py
strata gate
git diff
git status --short
```

The package version remains `0.3.1`; this documentation polish does not publish or tag a release.

## Philosophy

AI can write code, but people should control context, review patches, run tests, and decide what lands. Strata makes that workflow practical without requiring repository contents to leave the local workflow unless you choose an external adapter.
