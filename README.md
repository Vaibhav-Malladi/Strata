# Strata

Strata is a local-first repository intelligence CLI for AI-assisted coding workflows. It is deterministic, works on local repository data, and helps create context packs, snapshots, structural diffs, verification reports, and gate reports.

Strata does **not** call an LLM. Strata does **not** edit files for you. It helps humans and AI coding agents understand repository structure and risk before and after edits.

**Core message:** Preflight before editing. Verify after editing.

---

## Status

```text
v0.4.3
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

## Quick Start

```powershell
strata scan
strata context "change login page"
strata snapshot

# make edits with your AI coding tool, Codex, or editor

strata diff
strata verify
strata gate
strata status
```

- `strata scan` builds the repository graph in `.aidc/graph.json`.
- `strata context "change login page"` writes a deterministic task context pack.
- `strata snapshot` saves a baseline for later diff and verify runs.
- `strata diff` compares the latest snapshot with the current repository structure.
- `strata verify` checks whether the edit introduced risky structural changes.
- `strata gate` checks whether the repository looks safe enough to commit.
- `strata status` reports whether generated outputs are current, incomplete, or stale.

---

## AI Coding Safety Loop

Before editing:

- run `strata scan`
- run `strata context "task"`
- run `strata snapshot`

After editing:

- run `strata diff`
- run `strata verify`
- run `strata gate`

What that means:

- `snapshot` saves a baseline for the repository structure.
- `diff` shows structural changes since that baseline.
- `verify` checks whether the edit introduced risky structural changes.
- `gate` checks whether the repository is currently safe enough before commit.

---

## Command Summary

| Command | Purpose |
|---|---|
| `strata scan` | Build `.aidc/graph.json`. |
| `strata show` | Show the saved graph summary or file details. |
| `strata map` | Generate `.aidc/project_map.md`. |
| `strata routes` | Generate `.aidc/routes.md` and `.aidc/routes.json`. |
| `strata context "task"` | Generate a compact deterministic context pack. |
| `strata preflight "task"` | Generate `.aidc/preflight.md` for a task. |
| `strata snapshot` | Save a structural snapshot under `.aidc/snapshots/`. |
| `strata diff` | Compare the latest snapshot with the current repository structure. |
| `strata verify` | Verify current structure against the latest snapshot. |
| `strata gate` | Check current repository readiness before commit. |
| `strata status` | Check generated Strata output status. |
| `strata help` | Show the CLI help text. |

---

## Generated Files

Common `.aidc` outputs:

```text
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
.aidc/agent_prompt.md
```

These files are generated reports and should generally not be edited manually.

---

## Current Language Support

- Python support is strongest.
- JavaScript and TypeScript parsing exists in lightweight form.
- React and Angular hints are detected where the parser can recognize them.

Strata does not claim full Rust, Java, or framework coverage unless the parser actually supports it.

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

## What Strata Is For

Strata is designed for developers who want better repository context before editing with AI tools. It helps answer questions like:

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

