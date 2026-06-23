# Strata

Strata is a local-first repository intelligence CLI for AI-assisted coding workflows. It scans the repo, creates deterministic context, prepares AI-coder prompts, snapshots structure, diffs after edits, verifies structural changes, and gates readiness before commit.

Strata does **not** edit source files by itself. Strata does **not** call cloud AI services automatically. It helps humans and AI coding tools understand repository structure and risk before and after edits.

**Core message:** Preflight before editing. Verify after editing.

---

## Status

```text
v0.5.0 / V4 workflow preview
```

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

---

## Recommended V4 Workflow

```powershell
cd D:\AI-PROJECT\strata
py -m pip install -e .

strata config init
strata config set mode hybrid
strata config set agent codex
strata config set auto_snapshot false

strata run "fix helper bug"
# Paste .aidc\agent_prompt.md into your AI coding tool.
# Then run strata review.

strata review
strata gate
```

## Model-agnostic Run Workflow

`strata run` is the recommended high-level workflow command for AI-assisted changes.
It does not lock Strata to one AI model or tool. Instead, it reads the local workflow
config, builds a deterministic task plan, runs prepare, and routes through the configured
adapter.

Today, the safe default adapter is `prompt_file`. That means Strata prepares
`.aidc/agent_prompt.md` and tells you where to paste it next. It does not execute AI
automatically yet.

Future adapter support may include `command`, `ollama`, `openai_compatible_http`,
`aider`, and `codex_cli`.

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

This only previews how a future command adapter would be called. It does not execute
the configured command, does not execute AI, and does not create or apply
`.aidc/agent_patch.diff`. It is useful for checking adapter configuration safely
before real execution support exists.

## Adapter Status

| Adapter | Status | Behavior |
|---|---|---|
| `prompt_file` | Implemented | Writes/uses `.aidc/agent_prompt.md`; user pastes it into an AI tool manually. |
| `command` | Dry-run preview | Shows the configured command, prompt path, and patch path without executing anything. Real execution is planned. |
| `ollama` | Planned | Future local model adapter. |
| `openai_compatible_http` | Planned | Future local/remote HTTP model adapter. |
| `aider` | Planned | Future Aider adapter. |
| `codex_cli` | Planned | Future Codex CLI adapter. |

### Command adapter dry-run

The `command` adapter can now preview its configured command without executing it.
This is useful when you want to verify the planned handoff before real execution is
implemented.

```powershell
strata config set adapter command
strata config set command "my-ai --prompt .aidc/agent_prompt.md"

strata run --dry-run "fix broken helper import"

strata config set adapter prompt_file
strata config set command null
```

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
```

Supported keys:

- `mode`: `manual` | `hybrid` | `auto`
- `agent`: `manual` | `local` | `codex` | `aider`
- `adapter`: `prompt_file` | `command` | `ollama` | `openai_compatible_http` | `aider` | `codex_cli`
- `prompt_path`: path to the generated AI prompt file; defaults to `.aidc/agent_prompt.md`
- `model`: optional model name for future adapters
- `command`: optional command string for the command adapter
- `auto_snapshot`: `true` | `false`
- `auto_verify`: `true` | `false`
- `require_gate_pass_before_commit`: `true` | `false`

Important notes:

- `mode=auto` is a stored config option for future workflows.
- It does not yet mean Strata will automatically run an AI coding agent.
- `agent=codex` currently means Strata generates Codex-ready prompt context.
- It does not yet execute Codex.

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

If review passes, inspect the reports and commit if expected. If review fails, inspect the generated reports and fix the issues. Review does not commit automatically.

---

## Command Summary

| Command | Purpose |
|---|---|
| `strata config [root]` | Show workflow config for the repository. |
| `strata config init [root]` | Create `.aidc/config.json` if missing; validate and preserve an existing valid config. |
| `strata config set <key> <value> [root]` | Set a workflow config value. |
| `strata run "<task>" [root]` | Model-agnostic workflow shell. Plans the task, prepares context, writes `.aidc/agent_prompt.md`, and routes through the configured adapter. Currently uses `prompt_file`, so AI is not executed automatically yet. |
| `strata prepare "<task>" [root]` | Generate task context and prompt files before editing. |
| `strata review [root]` | Run diff, verify, and gate after editing. |
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
- React and Angular hints may be detected where recognizable.

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
- `strata run` currently uses `prompt_file`, so AI is not executed automatically yet.
- `command` adapter has dry-run preview only; real command execution is planned but not implemented.
- Patch/apply flow is planned but not implemented.
- Other adapters such as `ollama`, `openai_compatible_http`, `aider`, and `codex_cli` are planned but not implemented.
- AI never commits changes; gate remains the safety boundary.
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
