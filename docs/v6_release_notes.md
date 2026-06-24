# Strata V6 Release Notes

Strata V6 turns the project into a guided, patch-first AI coding workflow. It helps you prepare focused context, ask an AI for a patch, review the patch before applying it, and keep the human in control of every edit. The release also adds clearer guidance, a more beginner-friendly entrypoint, and direct-edit reporting for tools that may change files without producing a patch first.

## Main Workflow

1. `strata start`
2. `strata ask "fix the login bug"`
3. `strata review`
4. `strata apply`

## Major Features

### 1. Guided workflow commands

`strata start`, `strata ask`, `strata review`, and `strata apply` provide a simple, patch-first path for everyday work.

### 2. Guided entrypoint

Running `strata` with no arguments shows the recommended next step instead of requiring users to know the full command set up front.

### 3. Inline patch review

After `strata ask`, Strata shows a compact inline review so you can inspect patch status and next steps immediately.

### 4. Context efficiency metric

Strata reports an estimated context reduction after it builds focused context, so users can see how much repository content was intentionally left out.

### 5. Direct-edit safety report

If a command-style tool edits files directly instead of producing `.aidc/agent_patch.diff`, Strata writes `.aidc/direct_edit.diff` so the change is still reviewable.

### 6. Preserved advanced commands

Power users still have access to advanced commands such as `run`, `doctor`, `patch`, `gate`, `scan`, `status`, and related workflow tools.

## Safety Model

- Patch-first by default.
- `strata ask` does not apply changes.
- `strata apply` requires explicit user intent.
- Strata does not commit automatically.
- Direct edits are reported instead of being hidden.

## Known Limitations

- Context and token numbers are estimates only.
- Actual AI token usage may vary by adapter.
- The direct-edit report is not a full undo mechanism.
- Fast or trust-mode workflows are not implemented yet.
- JSON agent output is not implemented yet.
