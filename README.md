# Strata

**Strata helps you use AI coding tools more accurately and safely.**

It scans your codebase, builds focused context for your task, helps your AI tool produce a patch, lets you review the patch, and applies it only after you confirm it.

Strata is built for one simple idea:

> **Preflight before editing. Verify after editing.**

Strata does **not** commit or push automatically.
Strata does **not** apply changes unless you explicitly run `strata apply`.
Strata does **not** call an AI service unless you configure an adapter or workflow that does so.

---

## What Strata Actually Does

When people use AI coding tools, two common problems happen.

### Problem 1: The AI gets too much or wrong context

Large projects have many files. If an AI tool reads too much, it can get confused. If it reads too little, it may miss the important file.

Strata helps by scanning your repository and preparing **focused context** for the specific task you asked about.

### Problem 2: AI edits are hard to inspect

Some AI coding tools produce a patch. Some edit files directly. Either way, you need to know what changed before trusting it.

Strata helps by keeping the workflow reviewable:

* it prepares focused context before AI work,
* it expects a patch when possible,
* it reports direct edits when a tool changes files directly,
* it lets you review before applying,
* it never commits or pushes for you.

---

## Quickstart: Simple Workflow

The beginner workflow is four commands:

```powershell
strata start
strata ask "fix the login bug"
strata review
strata apply
```

| Step               | What happens                                                           |
| ------------------ | ---------------------------------------------------------------------- |
| `strata start`     | Scans your repo and prepares Strata.                                   |
| `strata ask "..."` | Builds focused context and asks or helps your AI tool produce a patch. |
| `strata review`    | Shows what the AI wants to change before applying it.                  |
| `strata apply`     | Applies the patch only after confirmation.                             |

Strata does not commit or push. That remains your decision.

---

## Install

### Requirements

* Python 3.10+
* `rich>=13`

### Local development install

```powershell
git clone https://github.com/Vaibhav-Malladi/Strata.git
cd Strata
py -m pip install -e .
strata help
```

If the `strata` command is not available in your shell yet, use:

```powershell
py cli.py help
```

---

## Connecting Your AI Tool

Strata can work with different AI coding workflows.

Some users prefer to copy and paste prompts manually. Others use command-line tools like Aider, Codex CLI, Ollama, or an OpenAI-compatible endpoint.

---

### Option 1: Manual Paste Workflow

Use this if you work with:

* ChatGPT
* Claude
* Copilot Chat
* any AI tool where you paste text manually

This is the safest default workflow.

```powershell
strata ask "fix the login bug"
```

Strata writes:

```text
.aidc/agent_prompt.md
```

Open that file, paste it into your AI tool, and ask the AI to return a **unified diff** patch.

Save the AI’s patch here:

```text
.aidc/agent_patch.diff
```

Then run:

```powershell
strata review
strata apply
```

---

### Option 2: Aider

Use this if you use Aider as your AI coding CLI.

```powershell
strata setup --aider
strata ask "fix the login bug"
strata review
strata apply
```

Aider is a command-family adapter. Some AI CLIs can edit files directly depending on their settings. If that happens, Strata can write a direct-edit report:

```text
.aidc/direct_edit.diff
```

That makes the change reviewable even when the tool did not produce `.aidc/agent_patch.diff`.

---

### Option 3: Codex CLI

Use this if you use Codex CLI.

```powershell
strata setup --codex-cli
strata ask "fix the login bug"
strata review
strata apply
```

Codex CLI is also a command-family adapter. As with Aider, if it edits files directly instead of writing a patch, Strata can report those direct edits through:

```text
.aidc/direct_edit.diff
```

---

### Option 4: Ollama

Use this if you run local models through Ollama.

```powershell
strata setup --ollama
strata config set model qwen2.5-coder
strata ask "fix the login bug"
strata review
strata apply
```

Ollama support uses the native Ollama endpoint:

```text
/api/generate
```

Recommended local models:

* `qwen2.5-coder`
* `qwen2.5-coder:7b`

Strata still keeps the patch workflow explicit. It asks for a patch, writes the result to `.aidc/agent_patch.diff`, and waits for you to review and apply.

---

### Option 5: OpenAI-Compatible HTTP Endpoint

Use this if you have a local or cloud endpoint that follows the OpenAI-compatible chat completions style.

```powershell
strata setup --http
strata config set base_url http://localhost:1234/v1
strata config set api_key_env OPENAI_API_KEY
strata ask "fix the login bug"
strata review
strata apply
```

Important:

```text
api_key_env
```

stores only the environment variable name. It should not store the actual secret key.

---

## What You See in the Terminal

Strata uses a Rich-powered terminal UI with banners, cards, tables, and clear status messages.

It can show:

* current workflow status,
* next recommended command,
* patch review status,
* context efficiency estimates,
* direct-edit warnings,
* test progress,
* gate results.

In interactive terminals, Strata can show progress indicators. In CI and non-interactive terminals, it falls back to plain readable output.

Useful environment variables:

| Variable                 | Effect                                                    |
| ------------------------ | --------------------------------------------------------- |
| `STRATA_PLAIN=1`         | Use plain text output.                                    |
| `STRATA_NO_COLOR=1`      | Disable Strata colors.                                    |
| `NO_COLOR=1`             | Disable colors using the standard environment convention. |
| `STRATA_NO_SPINNER=1`    | Disable spinners and animations.                          |
| `STRATA_FORCE_SPINNER=1` | Force spinner behavior in unusual terminals.              |

---

## Context Efficiency

Strata tries to reduce the amount of unnecessary code sent to the AI.

After building focused context, Strata can show a card like:

```text
Context Efficiency
  Source files scanned        141
  Files included              10
  Full source estimate        ~269,825 tokens
  Strata context estimate     ~808 tokens
  Estimated context reduction ~99%
  Note                        Actual AI token usage may vary by adapter.
```

This is an estimate, not a guarantee.

The metric means:

* Strata scanned the repo.
* Strata selected only the files likely to matter.
* The context pack is smaller than sending everything.
* Actual AI token usage can vary depending on the adapter or AI tool.

---

## Supported Languages

| Language / Framework    | Support level               |
| ----------------------- | --------------------------- |
| Python                  | Strongest support           |
| JavaScript / TypeScript | Good heuristic support      |
| React                   | Detected where recognizable |
| Angular                 | Detected where recognizable |

JavaScript and TypeScript support includes lightweight handling for:

* relative imports,
* extensionless imports,
* index files,
* path aliases,
* simple workspace references,
* barrel re-exports.

It is not a full TypeScript compiler replacement.

---

## Files Strata Creates

Strata writes local workflow files inside:

```text
.aidc/
```

Common files:

| File                           | Purpose                                              |
| ------------------------------ | ---------------------------------------------------- |
| `.aidc/config.json`            | Local Strata settings for this repo.                 |
| `.aidc/agent_prompt.md`        | Prompt/context to give your AI tool.                 |
| `.aidc/agent_patch.diff`       | Patch returned by the AI tool.                       |
| `.aidc/direct_edit.diff`       | Report created when an AI tool edits files directly. |
| `.aidc/graph.json`             | Repository structure graph.                          |
| `.aidc/context_pack.md`        | Focused context for the task.                        |
| `.aidc/gate_report.md`         | Readiness report before commit.                      |
| `.aidc/diff_report.md`         | Structural diff report.                              |
| `.aidc/verification_report.md` | Verification report.                                 |
| `.aidc/project_map.md`         | Human-readable project map.                          |
| `.aidc/routes.md`              | Route report, where supported.                       |

The `.aidc/` folder is local workflow output. Generally, do not commit it unless you intentionally decide to track a specific generated report.

---

## Safety Model

Strata is designed around a patch-first safety model.

### What Strata does

* prepares focused context,
* asks for or helps collect a patch,
* validates patch safety,
* shows review output,
* applies only when you explicitly run apply,
* reports direct edits from tools that bypass patch creation.

### What Strata does not do

* does not secretly edit files,
* does not apply patches during `ask`,
* does not commit,
* does not push,
* does not store secret API keys,
* does not replace your test suite.

### Patch safety

Strata rejects dangerous patch paths such as:

```text
.git/
.env
.ssh/
.aidc/config.json
```

You can validate without applying:

```powershell
strata apply --dry-run
```

Then apply only when ready:

```powershell
strata apply
```

---

# Power User and Developer Reference

Everything below is for users who want more control over Strata’s workflow.

---

## Setup Presets

```powershell
strata setup
strata setup --manual
strata setup --command
strata setup --http
strata setup --ollama
strata setup --aider
strata setup --codex-cli
strata setup --show
```

| Preset                     | Use it when                                                   |
| -------------------------- | ------------------------------------------------------------- |
| `strata setup`             | You want the setup wizard.                                    |
| `strata setup --manual`    | You copy prompts into ChatGPT, Claude, or Copilot manually.   |
| `strata setup --command`   | You use a local command that writes `.aidc/agent_patch.diff`. |
| `strata setup --http`      | You use an OpenAI-compatible endpoint.                        |
| `strata setup --ollama`    | You use a local Ollama model.                                 |
| `strata setup --aider`     | You use Aider.                                                |
| `strata setup --codex-cli` | You use Codex CLI.                                            |
| `strata setup --show`      | You want to inspect current config.                           |

---

## Adapter Reference

| Adapter                  | Family        | Status       | Behavior                                                              |
| ------------------------ | ------------- | ------------ | --------------------------------------------------------------------- |
| `prompt_file`            | `prompt_file` | Stable       | Writes `.aidc/agent_prompt.md`; user pastes manually.                 |
| `command`                | `command`     | Stable       | Runs a configured local command and expects `.aidc/agent_patch.diff`. |
| `aider`                  | `command`     | Stable       | Aider preset in the command family.                                   |
| `codex_cli`              | `command`     | Stable       | Codex CLI preset in the command family.                               |
| `ollama`                 | `http`        | Stable       | Uses Ollama’s native `/api/generate` endpoint.                        |
| `openai_compatible_http` | `http`        | Experimental | Uses an OpenAI-compatible HTTP endpoint.                              |

---

## Config Reference

Show current config:

```powershell
strata config
```

Create config if missing:

```powershell
strata config init
```

Common config examples:

```powershell
strata config set adapter command
strata config set command "py examples\fake_ai_patch_writer.py"
strata config set command_timeout_seconds 120

strata config set adapter openai_compatible_http
strata config set base_url http://localhost:1234/v1
strata config set api_key_env OPENAI_API_KEY
strata config set http_timeout_seconds 120

strata config set adapter ollama
strata config set model qwen2.5-coder

strata config set auto_snapshot false
strata config set auto_verify true
strata config set require_gate true
```

Supported config keys include:

| Key                               | Meaning                                             |
| --------------------------------- | --------------------------------------------------- |
| `adapter`                         | Adapter type or preset.                             |
| `prompt_path`                     | Path to generated AI prompt.                        |
| `model`                           | Model name for compatible adapters.                 |
| `command`                         | Local command for command adapter.                  |
| `command_timeout_seconds`         | Timeout for command execution.                      |
| `base_url`                        | HTTP adapter base URL.                              |
| `api_key_env`                     | Environment variable name for API key.              |
| `http_timeout_seconds`            | Timeout for HTTP adapter.                           |
| `auto_snapshot`                   | Whether prepare can create snapshots automatically. |
| `auto_verify`                     | Whether review can run verification automatically.  |
| `require_gate_pass_before_commit` | Whether gate is required by local workflow policy.  |

---

## Full Command Reference

| Command                                   | Purpose                                                             |
| ----------------------------------------- | ------------------------------------------------------------------- |
| `strata start [root]`                     | Prepare Strata for the repository and show readiness.               |
| `strata ask "<task>" [root]`              | Prepare context, ask AI for a patch, and collect the result safely. |
| `strata review [root]`                    | Inspect and validate the patch before applying it.                  |
| `strata apply [--dry-run] [--yes] [root]` | Validate or apply the generated patch.                              |
| `strata setup [--preset]`                 | Configure Strata adapter settings.                                  |
| `strata config [root]`                    | Show workflow config.                                               |
| `strata config init [root]`               | Create `.aidc/config.json` if missing.                              |
| `strata config set <key> <value> [root]`  | Set a workflow config value.                                        |
| `strata run "<task>" [root]`              | Advanced workflow shell.                                            |
| `strata prepare "<task>" [root]`          | Generate task context and prompt files.                             |
| `strata doctor adapter`                   | Validate configured adapter and contract.                           |
| `strata execute [--dry-run] [root]`       | Run the configured adapter and produce a patch.                     |
| `strata patch [root]`                     | Inspect the generated patch.                                        |
| `strata gate`                             | Check repository readiness before commit.                           |
| `strata scan`                             | Build `.aidc/graph.json`.                                           |
| `strata context "<task>"`                 | Generate a focused context pack.                                    |
| `strata preflight "<task>"`               | Generate `.aidc/preflight.md`.                                      |
| `strata agent-prompt "<task>" <agent>`    | Generate `.aidc/agent_prompt.md`.                                   |
| `strata snapshot`                         | Save a structural snapshot.                                         |
| `strata diff`                             | Compare the latest snapshot with current structure.                 |
| `strata verify`                           | Verify structure against latest snapshot.                           |
| `strata status`                           | Check generated Strata output status.                               |
| `strata map`                              | Generate `.aidc/project_map.md`.                                    |
| `strata routes`                           | Generate `.aidc/routes.md` and `.aidc/routes.json`.                 |
| `strata cycles`                           | Inspect repository cycles.                                          |
| `strata health`                           | Run a repository health check.                                      |
| `strata impact`                           | Summarize change impact.                                            |
| `strata tests-for`                        | Suggest tests related to a path or task.                            |
| `strata brief`                            | Generate a concise task brief.                                      |
| `strata show`                             | Show saved graph summary or file details.                           |
| `strata help`                             | Show CLI help text.                                                 |

---

## Advanced Manual Execute Workflow

Use this when you want full control over each step.

```powershell
strata config set adapter command
strata config set command "py examples\fake_ai_patch_writer.py"

strata run "fix helper bug"
strata doctor adapter
strata execute
strata patch
strata apply --dry-run
strata apply
strata review

py tests.py
py tests\run.py

$env:PYTHONIOENCODING="utf-8"
strata gate

git status --short
git add <files-you-reviewed>
git commit -m "Fix helper bug"
```

Avoid committing before tests and gate pass.

---

## Testing Strata Itself

Run:

```powershell
py tests.py
py tests\run.py
```

Expected result:

```text
All tests passed.
```

For a final readiness check:

```powershell
$env:PYTHONIOENCODING="utf-8"
strata gate
```

---

## V6 Release Summary

Strata V6 focuses on making the workflow guided, safer, and easier to understand.

V6 added:

* guided workflow commands,
* beginner-friendly `strata` entrypoint,
* clearer Next/Fix guidance,
* inline patch review after `strata ask`,
* estimated context reduction metrics,
* direct-edit reporting through `.aidc/direct_edit.diff`,
* preserved advanced commands for power users.

---

## Roadmap

Planned future work includes:

* undo and history support,
* balanced and fast workflow modes,
* machine-readable JSON/plain output,
* watch mode and CI hooks,
* deeper monorepo support,
* model-specific token and cost reporting,
* Rust and Java language support.

These are planned items, not current behavior.

---

## What Strata Is For

Strata is useful when you want better repository context before and after AI-assisted edits.

It helps answer questions like:

* What files matter for this task?
* What imports what?
* What routes exist?
* What could break if this file changes?
* What tests should I run?
* What context should I give my AI assistant?
* What exactly changed after the AI worked?

Strata is useful for:

* AI-assisted coding workflows,
* local-first repository inspection,
* pre-edit context packs,
* post-edit review,
* patch-first workflows,
* Python projects,
* JavaScript and TypeScript projects.

---

## What Strata Is Not

Strata is not:

* an autonomous coding agent,
* an IDE,
* an LLM,
* a cloud indexing platform,
* a replacement for tests,
* a replacement for compiler-grade analysis tools,
* a tool that commits or pushes code for you.

---

## Core Promise

Strata keeps AI coding work inspectable.

It helps you prepare better context before AI edits and verify what happened after AI edits, while keeping the final decision in your hands.
