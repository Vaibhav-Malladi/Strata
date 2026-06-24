# Strata

Strata is a local-first repository intelligence CLI for AI-assisted coding workflows. It scans the repo, creates deterministic context, prepares AI-coder prompts, snapshots structure, diffs after edits, verifies structural changes, and gates readiness before commit.

Strata does **not** edit source files by itself. Strata does **not** call cloud AI services automatically. It helps humans and AI coding tools understand repository structure and risk before and after edits.

**Core message:** Preflight before editing. Verify after editing.

---

## Status

```text
v0.5.2 / Ollama adapter support
```

## Terminal UI

Strata now uses a Rich-powered terminal UI for cleaner banners, cards, and tables.
Progress indicators appear only in interactive terminals, while CI and non-TTY runs
stay plain and readable.

The command screens now use a fuller Strata wordmark, compact command headers for
doctor/patch/apply, a lifecycle panel for execute, and visible progress updates in
`py tests.py` and `py tests\run.py`. Test runs use a Rich progress bar in
interactive terminals and a periodic plain-text fallback in non-TTY runs.

Useful env vars:

- `STRATA_PLAIN=1`
- `STRATA_NO_SPINNER=1`
- `STRATA_FORCE_SPINNER=1`
- `STRATA_NO_COLOR=1`
- `NO_COLOR=1`

## Install / Local Development

Requirements:

- Python 3.10+
- No runtime dependencies

Recommended install:

```powershell
git clone https://github.com/Vaibhav-Malladi/Strata.git
cd Strata
py -m pip install -e .
strata help
```

Main workflow:

```powershell
strata <command>
```

Windows fallback:

```powershell
py cli.py help
```

Use the fallback if the `strata` console script is not available yet in your shell.

## Beginner Workflow

```powershell
strata start
strata ask "fix the login bug"
strata review
strata apply
```

This is the recommended beginner path:

- `start` prepares Strata for the repository.
- `ask` asks AI for a patch.
- `review` checks the patch before applying it.
- `apply` applies the approved patch.
- Strata does not commit or push automatically.

Run `strata` at any time to see the recommended next step.
After `strata ask` receives a patch, Strata shows a compact inline review so you can quickly see what changed before running a full review or applying.
Strata also shows an estimated context reduction after it builds focused context, so you can see how much repo content was intentionally left out. The numbers are estimates only, not exact token counts or cost savings.
Run `strata help` for advanced commands.

Manual mode note:

- If your adapter is `prompt_file`, `strata ask` writes `.aidc/agent_prompt.md`.
- Open that file in your AI tool, ask for a unified diff, save it to `.aidc/agent_patch.diff`, and then run `strata review`.

Advanced commands still exist for power users, including `setup`, `config`, `run`, `doctor`, `execute`, `patch`, `gate`, `scan`, `status`, and `context`.

## First-Time Setup

Use the setup wizard to configure Strata without editing config keys by hand:

```powershell
strata setup
```

Presets:

```powershell
strata setup --manual
strata setup --command
strata setup --http
strata setup --ollama
strata setup --show
```

Recommended choices:

- Manual if you copy prompts into ChatGPT, Claude, or Copilot.
- Command if a local CLI writes `.aidc/agent_patch.diff`.
- HTTP if you use an OpenAI-compatible local or cloud endpoint.
- Ollama if you want a local Qwen/Ollama workflow.

## Aider / Codex CLI Presets

Strata includes command-family presets for Aider and Codex CLI so setup is faster
and the expected workflow stays explicit.

Use them when your installed CLI can read `.aidc/agent_prompt.md` and write
`.aidc/agent_patch.diff` for Strata to inspect afterward:

```powershell
strata setup --aider
strata setup --codex-cli
```

Interactive setup also accepts the aliases `aider`, `codex`, `codex_cli`, and
`codex-cli`.

These presets are still conservative command-family entries. Many AI coding CLIs
can edit files directly depending on their configuration, so always verify the
command before running `strata execute`.
Some AI tools may edit files directly. Strata detects this and writes
`.aidc/direct_edit.diff` so the change is still reviewable.

Recommended flow:

```powershell
strata setup --aider
strata doctor adapter
strata execute --dry-run
strata execute
strata patch
strata apply --dry-run
strata apply
```

The same flow works for Codex CLI after `strata setup --codex-cli`.

---

## Advanced / Legacy Workflow

```powershell
cd D:\AI-PROJECT\strata
py -m pip install -e .

strata config init
strata config set mode hybrid
strata config set agent codex
strata config set auto_snapshot false
strata config set command_timeout_seconds 120

strata run "fix helper bug"
# Paste .aidc\agent_prompt.md into your AI coding tool.
# Then run strata review.

strata review
strata gate
```

## Model-agnostic Run Workflow

`strata run` remains the model-agnostic workflow shell for advanced users.
It does not lock Strata to one AI model or tool. Instead, it reads the local workflow
config, builds a deterministic task plan, runs prepare, and routes through the configured
adapter.

The safe default adapter is still `prompt_file`. That means Strata prepares
`.aidc/agent_prompt.md` and tells you where to paste it next. It does not execute AI
automatically.

If `adapter=command`, `strata run` still only prepares the workflow. Use
`strata doctor adapter` to check the configuration, then `strata execute` to produce
`.aidc/agent_patch.diff`.

Safe example:

```powershell
strata run "fix broken helper import"
```

Dry-run example:

```powershell
strata run --dry-run "fix broken helper import"
```

This shows the detected task type and planned steps. It does not write files, create
`.aidc`, run prepare, call adapters, or execute AI.

This does not execute the configured command adapter, and it does not create or apply
`.aidc/agent_patch.diff`.

## Patch-first Command Execution

`strata execute` runs the configured `command` adapter or experimental
`openai_compatible_http` adapter. Strata verifies the adapter contract and the patch
output, not whether the external tool is actually AI. Command execution is explicit,
separate from `strata run`, and patch application still requires `strata apply`.

Command execution has a timeout. It defaults to 120 seconds and can be adjusted in
local workflow config. `strata execute` may also show short stdout/stderr previews
from the command it ran, but it still does not apply patches automatically.

HTTP-family adapters now have an experimental execution path for
`openai_compatible_http`. `strata doctor adapter` still validates `base_url`,
`api_key_env`, and timeout config locally without reading the actual environment
variable or making any network call. The HTTP request/response contract helpers are
already in place, including the OpenAI-compatible URL, payload, and response-text
extraction shapes. `strata execute` can now POST to OpenAI-compatible chat
completion endpoints, extract a unified diff, write `.aidc/agent_patch.diff`, and
validate the patch. It still does not apply patches automatically. `ollama` remains
not implemented for execution in this batch.

Strata groups adapters into three families: `prompt_file`, `command`, and `http`.
Named adapters are presets or aliases that map onto one of those families.

`prompt_file` remains manual. `command` is the only family with real command-line
execution today, and `openai_compatible_http` adds experimental HTTP execution.
Command-family presets like `aider` and `codex_cli` are supported as
setup/doctor-friendly presets, but Strata still expects the external CLI to write
`.aidc/agent_patch.diff` and keeps patch application explicit.

Safe workflow:

1. configure adapter
2. run or prepare task
3. doctor check
4. execute adapter
5. inspect patch
6. dry-run apply
7. apply patch
8. review and gate
9. commit manually only after tests and gate pass

The configured adapter is expected to produce `.aidc/agent_patch.diff`.
The patch must be a safe unified diff. Validation rejects dangerous paths such as
`.git`, `.env`, `.ssh`, and `.aidc/config.json`.
`strata apply --dry-run` validates patch format and safety without applying.
`strata apply` applies only after validation.
Strata never commits automatically.

PowerShell example:

```powershell
strata config set adapter command
strata config set command "python fake_ai.py"
strata run "fix helper bug"
strata doctor adapter
strata execute
strata patch
strata apply --dry-run
strata apply
strata review
py tests.py
py tests\run.py
.\strata gate
git add .
git commit -m "Fix helper bug"
```

### Manual Smoke Test With Fake Command Adapter

Use this only as a local smoke test. The helper script is not a real AI tool; it
just writes a demo patch for `demo_patch_target.txt` into `.aidc/agent_patch.diff`.
It emits the create-file diff shape Strata can validate and apply today.

```powershell
strata config set adapter command
strata config set command "py examples\fake_ai_patch_writer.py"
strata run "create demo patch file"
strata doctor adapter
strata execute
strata patch
strata apply --dry-run
strata apply
strata review
```

If `py` is not registered on your Windows machine, use `python` or your local
repo interpreter path for the `command` value.

Cleanup:

```powershell
del demo_patch_target.txt
del .aidc\agent_patch.diff
```

## Adapter Status

| Adapter | Family | Status | Behavior |
|---|---|---|---|
| `prompt_file` | `prompt_file` | Implemented | Writes/uses `.aidc/agent_prompt.md`; user pastes it into an AI tool manually. |
| `command` | `command` | Implemented | Runs the configured command adapter and writes `.aidc/agent_patch.diff`. |
| `ollama` | `http` | Implemented | Uses Ollama's native `/api/generate` endpoint, writes `.aidc/agent_patch.diff`, and does not apply patches automatically. |
| `openai_compatible_http` | `http` | Experimental | OpenAI-compatible HTTP execution writes `.aidc/agent_patch.diff`, validates the patch, and still does not apply it automatically. |
| `aider` | `command` | Implemented | Command-family preset that writes `aider --message-file .aidc/agent_prompt.md`; verify it emits `.aidc/agent_patch.diff` before execute. |
| `codex_cli` | `command` | Implemented | Command-family preset that writes `codex --prompt-file .aidc/agent_prompt.md`; verify it emits `.aidc/agent_patch.diff` before execute. |

## Native Ollama Workflow

Ollama defaults to `http://localhost:11434` and uses the native `/api/generate`
endpoint. Strata asks Ollama for a unified diff patch, writes the result to
`.aidc/agent_patch.diff`, and still leaves patch application to `strata apply`.

Recommended local models:

- `qwen2.5-coder`
- `qwen2.5-coder:7b` if you already have it installed

Example:

```powershell
strata config set adapter ollama
strata config set model qwen2.5-coder
strata config set base_url null
strata run "fix helper bug"
strata doctor adapter
strata execute --dry-run
strata execute
strata patch
strata apply --dry-run
strata apply
strata review
```

If you want to point Strata at a different local Ollama server, set
`base_url` to that server's root URL. The adapter still expects unified diff
output and does not apply patches automatically.

Manual safety loop:

```powershell
strata scan
strata context "task"
strata preflight "task"
strata snapshot

# AI/user edits

strata diff
strata verify
strata gate
```

## Workflow Config

`.aidc/config.json` is local workflow config generated for the current repository and is not meant to be a shared project source file.

```powershell
strata config
strata config init
strata config set mode hybrid
strata config set agent codex
strata config set auto_snapshot false
strata config set auto_verify true
strata config set require_gate true
strata config set command_timeout_seconds 120
strata config set base_url http://localhost:1234/v1
strata config set api_key_env OPENAI_API_KEY
strata config set http_timeout_seconds 120
```

Supported keys:

- `mode`: `manual` | `hybrid` | `auto`
- `agent`: `manual` | `local` | `codex` | `aider`
- `adapter`: `prompt_file` | `command` | `ollama` | `openai_compatible_http` | `aider` | `codex_cli`
- `prompt_path`: path to the generated AI prompt file; defaults to `.aidc/agent_prompt.md`
- `model`: optional model name for future adapters
- `command`: optional command string for the command adapter
- `command_timeout_seconds`: optional command timeout in seconds, default `120`
- `base_url`: optional HTTP adapter base URL
- `api_key_env`: optional environment variable name that stores the API key, not the secret itself
- `http_timeout_seconds`: optional HTTP adapter timeout in seconds, default `120`
- `auto_snapshot`: `true` | `false`
- `auto_verify`: `true` | `false`
- `require_gate_pass_before_commit`: `true` | `false`

Important notes:

- `mode=auto` is a stored config option for future workflows.
- It does not yet mean Strata will automatically run an AI coding agent.
- `agent=codex` currently means Strata generates Codex-ready prompt context.
- It does not yet execute Codex.
- `prompt_file` stays manual even when `command` is configured.
- The named adapter value is checked against its family, so the docs and CLI can
  explain whether a configured adapter is manual, command-driven, or HTTP-shaped.
- `api_key_env` stores only the environment variable name. Do not put the secret
  value in config.
- `ollama` remains planned for execution in this batch.
- `openai_compatible_http` can execute against OpenAI-compatible chat completion
  endpoints and still keeps patch application separate.
- `strata doctor adapter` validates HTTP config only and does not make network calls.
- The HTTP adapter contract helpers build deterministic OpenAI-compatible request
  and response shapes locally, and `strata execute` now uses them for
  `openai_compatible_http`.

Example HTTP setup:

```powershell
strata config set adapter openai_compatible_http
strata config set base_url http://localhost:1234/v1
strata config set api_key_env OPENAI_API_KEY
strata config set http_timeout_seconds 120
strata run "fix helper bug"
strata doctor adapter
strata execute --dry-run
strata execute
strata patch
strata apply --dry-run
strata apply
strata review
```

This example shows the experimental HTTP execution flow. `strata execute --dry-run`
does not make a network call, and `strata execute` writes `.aidc/agent_patch.diff`
without applying it. Use `strata patch`, `strata apply --dry-run`, and
`strata apply` afterward.

---

## Prepare Before Editing

```powershell
strata prepare "fix login bug"
```

This does:

- scan
- context
- preflight
- agent-prompt
- snapshot only if `auto_snapshot=true`

This writes:

- `.aidc/graph.json`
- `.aidc/context_pack.md`
- `.aidc/preflight.md`
- `.aidc/agent_prompt.md`
- optional snapshot files

Paste `.aidc\agent_prompt.md` into your AI coding tool after running it.

---

## Review After Editing

```powershell
strata review
```

This does:

- diff
- verify if `auto_verify=true`
- gate

This writes:

- `.aidc/diff_report.md`
- `.aidc/diff_report.json`
- `.aidc/verification_report.md` if verify runs
- `.aidc/verification_report.json` if verify runs
- `.aidc/gate_report.md`
- `.aidc/gate_report.json`

If review passes, inspect the reports, run tests and gate, and then commit manually if expected. If review fails, inspect the generated reports and fix the issues. Review does not commit automatically.

---

## Command Summary

| Command | Purpose |
|---|---|
| `strata start [root]` | Prepare Strata for the repository and show readiness. |
| `strata ask "<task>" [root]` | Prepare context, ask AI for a patch, and collect the result safely. |
| `strata review [root]` | Inspect and validate the patch before applying it. |
| `strata apply [--yes] [--dry-run] [root]` | Validate or apply the generated patch. |
| `strata config [root]` | Show workflow config for the repository. |
| `strata config init [root]` | Create `.aidc/config.json` if missing; validate and preserve an existing valid config. |
| `strata config set <key> <value> [root]` | Set a workflow config value. |
| `strata run "<task>" [root]` | Model-agnostic workflow shell. Plans the task, prepares context, writes `.aidc/agent_prompt.md`, and routes through the configured adapter without executing commands automatically. |
| `strata prepare "<task>" [root]` | Generate task context and prompt files before editing. |
| `strata doctor adapter` | Validate the configured adapter and contract before execution. |
| `strata execute [--dry-run] [root]` | Run the configured command adapter or experimental OpenAI-compatible HTTP adapter and produce `.aidc/agent_patch.diff` without applying it. |
| `strata patch [root]` | Inspect the generated patch. |
| `strata apply --dry-run [root]` | Validate patch safety without applying it. |
| `strata scan` | Build `.aidc/graph.json`. |
| `strata context "task"` | Generate a compact deterministic context pack. |
| `strata preflight "task"` | Generate `.aidc/preflight.md` for a task. |
| `strata agent-prompt "<task>" <agent>` | Generate `.aidc/agent_prompt.md` for a task and agent. |
| `strata snapshot` | Save a structural snapshot under `.aidc/snapshots/`. |
| `strata diff` | Compare the latest snapshot with the current repository structure. |
| `strata verify` | Verify current structure against the latest snapshot. |
| `strata gate` | Check current repository readiness before commit. |
| `strata status` | Check generated Strata output status. |
| `strata map` | Generate `.aidc/project_map.md`. |
| `strata routes` | Generate `.aidc/routes.md` and `.aidc/routes.json`. |
| `strata cycles` | Inspect repository cycles. |
| `strata health` | Run a repository health check. |
| `strata impact` | Summarize change impact. |
| `strata tests-for` | Suggest tests related to a path or task. |
| `strata brief` | Generate a concise task brief. |
| `strata show` | Show the saved graph summary or file details. |
| `strata help` | Show the CLI help text. |

---

## Generated Files

Common `.aidc` outputs:

```text
.aidc/config.json
.aidc/agent_prompt.md
.aidc/graph.json
.aidc/context_pack.md
.aidc/preflight.md
.aidc/snapshots/latest.txt
.aidc/diff_report.md
.aidc/diff_report.json
.aidc/verification_report.md
.aidc/verification_report.json
.aidc/gate_report.md
.aidc/gate_report.json
.aidc/routes.md
.aidc/routes.json
.aidc/project_map.md
.aidc/task_brief.md
```

`.aidc/config.json` is local workflow config, not a shared project file.

Except for `.aidc/config.json`, these files are generated reports and should generally not be edited manually.

---

## Current Language Support

- Python support is strongest.
- JavaScript and TypeScript parsing exists in lightweight form.
- JS/TS resolution now covers relative imports, extensionless imports, index files,
  tsconfig/jsconfig path aliases, simple package and workspace references, and
  barrel re-export edges.
- The JS/TS resolver is heuristic and uses standard-library file inspection only;
  it does not implement full TypeScript compiler resolution.
- React and Angular hints may be detected where recognizable.
- Strata now reports repo intelligence summaries in CLI output and reports, so
  languages, frameworks, React components/hooks, Angular components/services/
  modules/routes, and alias/workspace import resolution are easier to spot.

Rust, Java, and full framework support are planned, not complete.

---

## Testing

Run:

```powershell
py tests.py
py tests\run.py
```

Expected result:

```text
All tests passed.
```

---

## Limitations / Roadmap

- `mode=auto` is planned workflow state, not autonomous execution.
- `strata run` prepares the workflow and does not execute commands automatically.
- `prompt_file` remains the manual default for the run workflow.
- `strata execute` runs the configured `command` adapter or experimental OpenAI-compatible HTTP adapter, and Strata still does not decide whether the external tool is AI.
- `strata execute` writes a patch; it does not apply patches automatically.
- `strata apply` is separate and explicit, and `--dry-run` validates patch safety without applying.
- Other direct integrations such as future agent backends remain planned; the `aider` and `codex_cli` presets are supported now, but the external CLI still owns patch creation.
- Strata never commits changes automatically; gate remains the safety boundary.
- Interactive setup prompts are not implemented yet.
- Richer language support is still growing.
- Optional spinners and animations are future polish work.
- Package structure cleanup may happen later.

Planned future improvements include:

- interactive setup
- agent adapters
- `strata run` adapter backends beyond `prompt_file`
- richer language support
- optional spinners and animations
- package structure cleanup

---

## What Strata Is For

Strata is designed for developers who want better repository context before and after editing with AI tools. It helps answer questions like:

- What files exist?
- What imports what?
- What routes exist?
- What files are relevant to this task?
- What could break if this file changes?
- What tests should I run?
- What context should I give an AI assistant?

It is useful for:

- AI-assisted coding workflows
- local-first repository inspection
- pre-edit context packs
- post-edit structural verification
- Python projects
- JavaScript and TypeScript projects

---

## What Strata Is Not

Strata is not:

- an autonomous coding agent
- an IDE
- an LLM
- a file editor
- a runtime monitor
- a cloud indexing platform
- a replacement for compiler-grade analysis tools

---

## Notes

- `strata scan` creates the repository graph used by most other commands.
- `strata snapshot` is the baseline for `strata diff` and `strata verify`.
- `strata gate` is useful when you want a readiness check without thinking about a snapshot.
- `strata status` helps confirm whether generated artifacts are current.
- `py cli.py ...` can be used if the console entry point is unavailable.
