# Strata

**Local-first repository intelligence for safer AI-assisted coding.**

Strata helps you use AI coding tools more safely by turning a messy codebase into focused context, routing that context to your chosen AI mode, collecting a patch, reviewing it, and applying it only after explicit confirmation.

Strata is built around one idea:

```text
AI should not blindly edit your repo.
It should receive focused context, produce a patch, and let you review before anything changes.
```

---

## Status

```text
Strata V6 / Guided Patch-First Workflow
Package version: 0.3.1
```

Current focus:

* guided beginner workflow
* patch-first AI coding
* local-first repo intelligence
* safer review/apply flow
* direct-edit detection
* context efficiency reporting
* Python, JavaScript, TypeScript, React, and Angular repo understanding

---

## What Strata Does

Strata scans your repository and helps answer:

```text
Which files matter for this task?
Which tests might be related?
Which routes/components/imports are connected?
What context should I give to the AI?
What patch did the AI produce?
Is the patch safe to review before applying?
```

Strata does **not** replace your AI model. It sits between your repo and your AI tool.

You can use Strata with:

* ChatGPT, Claude, Gemini, or Copilot Chat in a browser
* Ollama/local models
* Codex CLI
* Aider
* Claude CLI or other command-line AI tools
* OpenAI-compatible HTTP APIs
* custom shell commands

---

## What Strata Is Not

Strata is not a fully autonomous coding agent.

It does not automatically commit or push changes.

It does not secretly call an AI provider unless you configure an adapter that does so.

It does not apply changes when you run `strata ask`.

It only changes files when you explicitly run:

```powershell
strata apply
```

and only by applying a reviewed patch.

The normal safe workflow is:

```text
prepare context → ask AI → collect patch → review patch → dry-run apply → apply → test → gate → commit manually
```

---

## Install

Clone the repository and install it locally:

```powershell
git clone https://github.com/Vaibhav-Malladi/Strata.git
cd Strata
py -m pip install -e .
```

Check that the CLI works:

```powershell
strata help
```

If the `strata` entry point is not available, use the fallback form:

```powershell
py cli.py help
```

---

## Quickstart

Go to the project you want to work on:

```powershell
cd D:\projects\my-app
```

Start Strata:

```powershell
strata start
```

Choose how Strata should talk to AI:

```powershell
strata setup
```

For the safest first-time path, use manual/browser mode:

```powershell
strata setup --manual
```

Ask for a change:

```powershell
strata ask "fix the navbar not opening on mobile"
```

Review the patch:

```powershell
strata review
```

Dry-run the patch first:

```powershell
strata apply --dry-run
```

Apply only after review:

```powershell
strata apply
```

Run your project tests, then run Strata’s gate:

```powershell
strata gate
```

Commit manually only after you have reviewed the changes and tests pass.

---

## First-Time User Path

If you are new to Strata, use this flow:

```powershell
strata help setup
strata setup --manual
strata ask "fix a small bug"
strata review
strata apply --dry-run
strata apply
strata gate
```

The most beginner-friendly mode is manual/browser AI because it does not require an API key, local model, or CLI AI tool.

---

## Choosing How Strata Talks to AI

Before using `strata ask`, choose an AI mode.

Run:

```powershell
strata setup
```

Strata supports several modes.

---

### Option 1: Manual / Browser AI

Best for first-time users.

Use this if you want to use ChatGPT, Claude, Gemini, Copilot Chat, or any browser-based AI without setting up an API key or local model.

```powershell
strata setup --manual
```

Then run:

```powershell
strata ask "fix the navbar bug"
```

Strata prepares a focused prompt at:

```text
.aidc/agent_prompt.md
```

Open that file and paste it into your browser AI.

Ask the AI to return only a unified diff patch, with no markdown fences and no explanation.

Save the returned patch as:

```text
.aidc/agent_patch.diff
```

Then review and apply safely:

```powershell
strata review
strata apply --dry-run
strata apply
```

After applying, run your project tests and then:

```powershell
strata gate
```

Manual/browser mode is the safest first-time workflow because the AI cannot directly edit your files unless you copy the patch back yourself.

---

### Option 2: Ollama / Local AI

Use this if you want Strata to talk to a local Ollama model.

Make sure Ollama is installed, running, and has a model available.

Check installed models:

```powershell
ollama list
```

Configure Strata:

```powershell
strata setup --ollama
```

Set the exact model name if needed:

```powershell
strata config set model qwen2.5-coder:14b
```

The exact model tag matters. For example:

```text
qwen2.5-coder
qwen2.5-coder:14b
```

may not refer to the same installed model.

Check the adapter:

```powershell
strata doctor adapter
```

Then use the normal workflow:

```powershell
strata ask "fix the bug"
strata review
strata apply --dry-run
strata apply
```

---

### Option 3: Codex CLI, Aider, Claude CLI, or Custom Command

Use this if you want Strata to prepare focused repo context and pass it to another command-line AI tool.

Preset examples:

```powershell
strata setup --codex-cli
strata setup --aider
```

For a custom command:

```powershell
strata setup --command
strata config set command "<your command here>"
```

The command should use Strata’s prepared prompt from:

```text
.aidc/agent_prompt.md
```

The safest workflow is patch-first: the AI should return a patch into:

```text
.aidc/agent_patch.diff
```

If the external tool edits files directly instead of returning a patch, Strata may create a direct-edit safety report:

```text
.aidc/direct_edit.diff
```

Always inspect changes before committing:

```powershell
git diff
strata review
strata apply --dry-run
```

Then run your project tests and:

```powershell
strata gate
```

---

### Option 4: OpenAI-Compatible HTTP API

Use this if you have an OpenAI-compatible local or remote API endpoint.

```powershell
strata setup --http
strata config set base_url http://localhost:1234/v1
strata config set api_key_env OPENAI_API_KEY
strata config set model <model-name>
strata doctor adapter
```

Do not put real API keys directly into Strata config. Store the key in an environment variable and point Strata to the variable name.

Example:

```powershell
$env:OPENAI_API_KEY="your-key-here"
strata config set api_key_env OPENAI_API_KEY
```

Then use:

```powershell
strata ask "fix the bug"
strata review
strata apply --dry-run
strata apply
```

---

## Beginner Help Topics

Strata includes detailed help for common beginner questions.

Use:

```powershell
strata help <topic>
```

Examples:

```powershell
strata help setup
strata help manual
strata help ollama
strata help command
strata help http
strata help ask
strata help review
strata help apply
strata help gate
strata help start
```

Useful aliases include:

```powershell
strata help browser
strata help chatgpt
strata help claude
strata help gemini
strata help local
strata help codex
strata help aider
strata help openai
```

---

## Main Workflow

### 1. Start

```powershell
strata start
```

Use this after installing Strata in a project. It gives a guided overview of what to do next.

---

### 2. Configure AI

```powershell
strata setup
```

Use this to choose how Strata talks to AI.

Check current setup:

```powershell
strata setup --show
```

Check whether the configured adapter is usable:

```powershell
strata doctor adapter
```

---

### 3. Ask

```powershell
strata ask "fix the bug"
```

`ask` prepares focused context for your configured AI mode.

Depending on your setup, it may:

* prepare `.aidc/agent_prompt.md` for browser/manual use
* call an Ollama model
* call a command adapter
* call an HTTP adapter
* collect `.aidc/agent_patch.diff`

`strata ask` does not apply source changes by itself.

---

### 4. Review

```powershell
strata review
```

`review` inspects the generated patch.

It checks things like:

* whether a patch exists
* whether the patch looks valid
* which files it targets
* whether dry-run validation passes
* whether there is a direct-edit safety report

Read the review before applying anything.

---

### 5. Dry-Run Apply

```powershell
strata apply --dry-run
```

This validates whether the patch can be applied without actually changing files.

Use this before every real apply.

---

### 6. Apply

```powershell
strata apply
```

This is the step where files may change.

Strata asks for confirmation unless you pass:

```powershell
strata apply --yes
```

Do not use `--yes` casually. Prefer normal interactive confirmation.

---

### 7. Test

Run your project’s own checks.

For JavaScript or React projects:

```powershell
npm test
npm run build
```

For Python projects:

```powershell
py tests.py
```

Use whatever test/build/lint commands your project requires.

---

### 8. Gate

```powershell
strata gate
```

`gate` writes:

```text
.aidc/gate_report.md
.aidc/gate_report.json
```

Gate gives a final validation summary, but it does not replace your real project tests.

Only commit after:

```text
patch reviewed
dry-run passed
patch applied intentionally
project tests passed
strata gate passed
git diff reviewed
```

---

## Example: Browser AI Workflow

This is the safest workflow for new users.

```powershell
cd D:\projects\my-react-app

strata setup --manual
strata ask "fix the navbar not opening on mobile"
```

Open:

```text
.aidc/agent_prompt.md
```

Paste it into ChatGPT, Claude, Gemini, or Copilot Chat.

Ask:

```text
Return only a unified diff patch.
Do not include markdown fences.
Do not include explanations.
```

Save the returned patch to:

```text
.aidc/agent_patch.diff
```

Then:

```powershell
strata review
strata apply --dry-run
strata apply

npm test
npm run build

strata gate
git diff
```

If everything looks correct:

```powershell
git add <files-you-reviewed>
git commit -m "Fix mobile navbar"
```

Avoid:

```powershell
git add .
```

Prefer adding only reviewed files.

---

## Example: Ollama Workflow

Start Ollama separately if it is not already running.

Check models:

```powershell
ollama list
```

Configure Strata:

```powershell
strata setup --ollama
strata config set model qwen2.5-coder:14b
strata doctor adapter
```

Ask for a change:

```powershell
strata ask "fix the failing login test"
```

Review and apply:

```powershell
strata review
strata apply --dry-run
strata apply
```

Run tests and gate:

```powershell
npm test
npm run build
strata gate
```

---

## Example: Command Adapter Workflow

Use this for CLI tools such as Codex CLI, Aider, Claude CLI, or custom commands.

```powershell
strata setup --command
strata config set command "<your command here>"
strata doctor adapter
```

Then:

```powershell
strata ask "refactor the auth helper"
strata review
strata apply --dry-run
strata apply
```

If the command-line AI edits files directly, inspect:

```powershell
git diff
```

and check for:

```text
.aidc/direct_edit.diff
```

Then run tests and gate.

---

## Context Efficiency

Strata tries to reduce how much code you send to AI by selecting focused task context instead of dumping the whole repository.

Use:

```powershell
strata context "fix the checkout discount bug"
```

This can show a context efficiency summary, such as:

```text
Source files scanned
Files included
Full source estimate
Strata context estimate
Estimated context reduction
```

This estimate helps you understand how much context Strata selected.

Actual AI token usage may vary by adapter because some external AI tools may read or index files themselves.

---

## Supported Languages and Frameworks

Strata currently focuses on:

* Python
* JavaScript
* TypeScript
* React
* Angular

It can detect and reason about common structures such as:

* imports
* files
* functions
* classes
* routes
* components
* tests
* framework hints
* dependency relationships

Future versions may expand support for:

* more frontend frameworks
* monorepos
* deeper build/test integration

---

## Generated Files

Strata stores its working artifacts under:

```text
.aidc/
```

Common files include:

```text
.aidc/graph.json
.aidc/agent_prompt.md
.aidc/agent_patch.diff
.aidc/direct_edit.diff
.aidc/gate_report.md
.aidc/gate_report.json
.aidc/config.json
```

These files are used for repo intelligence, AI prompting, patch review, direct-edit detection, and validation reports.

---

## Safety Model

Strata’s safety model is:

```text
do not trust AI edits blindly
prefer patches over direct edits
show what will change
dry-run before applying
require explicit apply
run project tests
run gate
commit manually
```

Important safety behavior:

* `strata ask` does not apply changes directly.
* `strata review` inspects the patch.
* `strata apply --dry-run` validates without changing files.
* `strata apply` is the intentional file-changing step.
* `strata gate` writes final reports.
* Strata does not automatically commit or push.
* Direct-edit-capable adapters may be detected through `.aidc/direct_edit.diff`.

---

## Direct-Edit Safety

Some AI tools edit files directly instead of returning a patch.

Strata prefers patch-first output, but if a command adapter changes files directly, Strata can surface a direct-edit report:

```text
.aidc/direct_edit.diff
```

If you see a direct-edit report, inspect it carefully:

```powershell
git diff
```

Then run tests and gate before committing.

---

## Useful Commands

### Help

```powershell
strata help
strata help setup
strata help manual
strata help ollama
strata help command
strata help http
strata help ask
strata help review
strata help apply
strata help gate
```

### Guided Workflow

```powershell
strata start
strata setup
strata ask "fix bug"
strata review
strata apply --dry-run
strata apply
strata gate
```

### Setup

```powershell
strata setup
strata setup --manual
strata setup --ollama
strata setup --codex-cli
strata setup --aider
strata setup --command
strata setup --http
strata setup --show
```

### Adapter Checks

```powershell
strata doctor adapter
strata config
strata config set model <model-name>
strata config set command "<command>"
strata config set base_url <url>
strata config set api_key_env <ENV_VAR_NAME>
```

### Repo Intelligence

```powershell
strata scan
strata map
strata routes
strata context "task"
strata preflight "task"
strata impact <file>
strata tests-for <file>
strata cycles
strata health
```

### Patch Workflow

```powershell
strata patch
strata review
strata apply --dry-run
strata apply
strata apply --yes
```

### Reports

```powershell
strata gate
strata status
```

---

## Root Path Forms

Most commands can run from the current directory or accept a root path.

Examples:

```powershell
strata start <root>
strata ask "fix bug" <root>
strata review <root>
strata apply --dry-run <root>
strata gate <root>
strata context <root> "fix bug"
```

---

## Development

Install in editable mode:

```powershell
py -m pip install -e .
```

Run tests:

```powershell
py tests.py
py tests\run.py
```

Run gate:

```powershell
$env:PYTHONIOENCODING="utf-8"
strata gate
```

Expected local validation before committing:

```powershell
py -m pip install -e .
py tests.py
py tests\run.py
strata gate
git diff
git status --short
```

Commit only after tests and gate pass.

---

## Recommended Commit Workflow

After applying AI changes:

```powershell
git diff
py tests.py
py tests\run.py
strata gate
git status --short
```

Then add only the files you reviewed:

```powershell
git add path\to\file1.py path\to\file2.py
git commit -m "Describe the change"
```

Avoid:

```powershell
git add .
```

unless you intentionally reviewed every changed file.

---

## Roadmap

Possible future work:

* faster trusted workflow modes
* undo/history support
* machine-readable JSON output for automation
* richer CI integration
* deeper monorepo support
* more language support
* token/cost reporting
* optional local semantic search / hybrid RAG ranking
* better Claude/Codex/Aider presets
* release packaging and publishing

Hybrid RAG is a future candidate, not a replacement for Strata’s deterministic graph-based ranking. The likely direction is:

```text
graph-based repo intelligence + optional semantic search signal
```

---

## Philosophy

Strata is designed for people who want AI coding help without giving up control.

The core belief:

```text
AI can write code.
But humans should control context, review patches, run tests, and decide what lands.
```

Strata helps make that workflow practical.
