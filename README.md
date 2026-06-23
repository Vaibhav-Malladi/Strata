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

strata prepare "fix helper bug"
# Paste .aidc\agent_prompt.md into your AI coding tool.
# Let Codex/Aider/your editor make changes.

strata review
strata gate
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
- `strata run` is not implemented yet.
- Agent adapters are not implemented yet.
- Interactive setup prompts are not implemented yet.
- Richer language support is still growing.
- Optional spinners and animations are future polish work.
- Package structure cleanup may happen later.

Planned future improvements include:

- interactive setup
- `strata run`
- agent adapters
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

