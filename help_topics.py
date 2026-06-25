from __future__ import annotations

from ui import build_section, print_command_header

_HELP_TOPIC_ALIASES = {
    "setup": "setup",
    "configure": "setup",
    "config-ai": "setup",
    "ask": "ask",
    "manual": "manual",
    "browser": "manual",
    "chatgpt": "manual",
    "claude": "manual",
    "gemini": "manual",
    "ollama": "ollama",
    "local": "ollama",
    "command": "command",
    "cli": "command",
    "codex": "command",
    "codex-cli": "command",
    "aider": "command",
    "claude-cli": "command",
    "http": "http",
    "api": "http",
    "openai": "http",
    "review": "review",
    "apply": "apply",
    "run": "run",
    "context": "context",
    "prepare": "prepare",
    "doctor": "doctor",
    "install": "doctor",
    "gate": "gate",
    "start": "start",
    "scan": "scan",
    "status": "status",
}


def print_help_topic(topic: str) -> int:
    normalized = str(topic or "").strip().lower()
    canonical = _HELP_TOPIC_ALIASES.get(normalized)

    if canonical is None:
        print(f"Unknown help topic: {topic}")
        print("Try `strata help` for available commands.")
        return 1

    print_command_header("Help", canonical, mode="compact")
    print()
    _HELP_TOPIC_RENDERERS[canonical]()
    return 0


def _render_setup_help() -> None:
    _print_intro("Setup chooses how Strata talks to AI.")
    _print_lines(
        "Quick picks",
        [
            "`strata setup` - recommended first time.",
            "`strata setup ai` - guided setup with safe credential handling.",
            "`strata setup ai --check` - guided readiness check without prompts.",
            "`strata setup --manual` - safest no-key browser AI path.",
            "`strata setup --ollama` - local model path.",
            "`strata setup --codex-cli` - Codex CLI through the command adapter.",
            "`strata setup --aider` - Aider through the command adapter.",
            "`strata setup --command` - any custom CLI command.",
            "`strata setup --http` - an OpenAI-compatible HTTP API; Strata stores only the environment variable name for the key.",
            "Strata can help save the key to your user environment on Windows.",
        ],
    )
    _print_lines(
        "Check current setup",
        [
            "`strata doctor adapter`",
            "`strata setup --show`",
        ],
    )


def _render_manual_help() -> None:
    _print_intro("Manual/browser AI is the safest first-time mode. No API key or local model required.")
    _print_steps(
        "Beginner flow",
        [
            "Run `strata setup --manual`.",
            'Run `strata ask "fix bug"`.',
            "Open `.aidc/agent_prompt.md`.",
            "Paste it into ChatGPT, Claude, Gemini, or Copilot Chat.",
            "Ask for only a unified diff, with no markdown fences.",
            "Save the returned diff as `.aidc/agent_patch.diff`.",
            "Run `strata review`.",
            "Run `strata apply --dry-run`.",
            "Run `strata apply`.",
            "Run your project tests, then `strata gate`.",
        ],
    )


def _render_ollama_help() -> None:
    _print_intro("Ollama is for local models. Ollama must be running, and the exact model tag matters.")
    _print_steps(
        "Beginner flow",
        [
            "Install and start Ollama separately.",
            "Pull or install a model.",
            "Run `ollama list` to check the exact model name.",
            "Run `strata setup --ollama`.",
            "If needed, set the exact model tag: `strata config set model qwen2.5-coder:14b`.",
            "Run `strata doctor adapter`.",
            'Then run `strata ask "fix bug"`.',
            "Run `strata review`.",
            "Run `strata apply --dry-run`.",
            "Run `strata apply`.",
        ],
    )
    _print_lines(
        "Notes",
        [
            "The exact model tag matters, including suffixes such as `:14b`.",
            "Strata uses the configured local Ollama endpoint when the adapter is set up that way.",
        ],
    )


def _render_command_help() -> None:
    _print_intro(
        "Command adapters are for CLI tools like Codex CLI, Claude CLI, Aider, or a custom script."
    )
    _print_lines(
        "Use it when",
        [
            "The tool can read `.aidc/agent_prompt.md` or receive Strata's prepared prompt.",
            "Prefer patch-first output.",
            "If the tool edits files directly, Strata may produce `.aidc/direct_edit.diff`.",
        ],
    )
    _print_lines(
        "Examples",
        [
            "`strata setup --codex-cli`",
            "`strata setup --aider`",
            "`strata setup --command`",
            '`strata config set command "<your command here>"`',
        ],
    )
    _print_intro("Use the command your tool supports for reading or receiving `.aidc/agent_prompt.md`.")
    _print_lines(
        "After that",
        [
            "Inspect `git diff`, run tests, and finish with `strata gate`.",
        ],
    )


def _render_http_help() -> None:
    _print_intro("This mode is for OpenAI-compatible HTTP APIs.")
    _print_lines(
        "Do this",
        [
            "`strata setup ai`",
            "`strata setup ai --check`",
            "`strata setup --http`",
            "`strata config set base_url http://localhost:1234/v1`",
            "`strata config set api_key_env OPENAI_API_KEY`",
            "`strata config set model <model-name>`",
            "`strata doctor adapter`",
        ],
    )
    _print_intro("Do not hardcode a real API key. Set `api_key_env` to the environment variable name instead.")
    _print_intro("Strata will check whether the variable is found or missing without showing the value.")
    _print_intro("Strata stores only the variable name and can help save the key to your user environment on Windows.")


def _render_ask_help() -> None:
    _print_intro("Ask prepares context and uses your configured AI mode. If nothing is configured, run `strata setup`.")
    _print_lines(
        "What happens",
        [
            "It prepares the prompt and context for the configured AI mode.",
            "It does not apply changes directly.",
            "Depending on mode, Strata writes `.aidc/agent_prompt.md` or expects `.aidc/agent_patch.diff`.",
        ],
    )
    _print_lines(
        "Selected-file context",
        [
            "If you already know the important file, anchor context with `--file LoginForm` or `--file run_command.py`.",
            "Use repeated `--file` flags for more than one file.",
            "Add `--budget small` when you want a preset cap for the generated prompt content.",
            "Add `--budget 3000` when you want a direct token target.",
            'Example: `strata ask --file run_command --file ask_command "compare these flows"`.',
        ],
    )
    _print_lines(
        "Next commands",
        [
            "`strata review`",
            "`strata apply --dry-run`",
            "`strata apply`",
        ],
    )


def _render_review_help() -> None:
    _print_intro("Review inspects `.aidc/agent_patch.diff` before apply.")
    _print_lines(
        "Checks",
        [
            "Patch validity.",
            "Patch targets.",
            "Whether the patch is safe to read before apply.",
            "Review is read-only.",
        ],
    )
    _print_lines("Next", ["`strata apply --dry-run`"])


def _render_apply_help() -> None:
    _print_intro("Apply is the point where files may change.")
    _print_lines(
        "Good habit",
        [
            "Run `strata apply --dry-run` first.",
            "Then run `strata apply`.",
            "After that, run your project tests and `strata gate`.",
            "Do not commit until tests pass.",
        ],
    )


def _render_run_help() -> None:
    _print_intro("Run is the guided one-command flow for prepare, review, and safe apply handoff.")
    _print_lines(
        "Default",
        [
            "Run `strata run \"fix bug\"` to prepare context, ask the adapter for a patch, and review it before applying anything.",
            "The final next step is `strata apply`.",
        ],
    )
    _print_lines(
        "Selected-file context",
        [
            "If you already know the file, run `strata run --file LoginForm \"fix bug\"` or `strata run --file run_command \"fix dry run output\" --dry-run`.",
            "Use repeated `--file` flags to anchor multiple files before the task.",
            "Try `strata run --budget small --dry-run \"fix bug\"` when you want a budgeted preview.",
            'Example: `strata run --file app.py --file helper.py "refactor this flow"`.',
        ],
    )
    _print_lines(
        "Fast mode",
        [
            "Run `strata run --fast \"fix bug\"` to ask for one final confirmation before applying a validated patch.",
            "Strata never commits or pushes automatically.",
        ],
    )


def _render_context_help() -> None:
    _print_intro("Context builds focused repository context and shows the budgeted summary before you hand it to AI.")
    _print_lines(
        "Examples",
        [
            'Run `strata context --budget 3000 "fix the checkout discount bug"` for a direct token target.',
            'Run `strata context --budget small "fix the checkout discount bug"` for a preset budget cap.',
        ],
    )
    _print_lines(
        "What to expect",
        [
            "Strata writes `.aidc/context_pack.md`.",
            "The budget summary shows the generated prompt content estimate when it is available.",
            "Actual AI token usage may still vary by adapter.",
        ],
    )


def _render_prepare_help() -> None:
    _print_intro("Prepare writes the repo graph, context pack, and agent prompt without running the AI adapter.")
    _print_lines(
        "Examples",
        [
            'Run `strata prepare --budget small "fix the checkout discount bug"` to cap the generated prompt content.',
            'Run `strata prepare "fix the checkout discount bug"` if you do not need a budget preset.',
        ],
    )
    _print_lines(
        "What to expect",
        [
            "Strata writes `.aidc/context_pack.md` and `.aidc/agent_prompt.md`.",
            "The budget summary matches the generated prompt content estimate when available.",
            "Then paste `.aidc/agent_prompt.md` into your AI tool.",
        ],
    )


def _render_scan_help() -> None:
    _print_intro("Scan builds Strata's full repo context. Focused mode still works if the scan is missing or stale.")
    _print_lines(
        "Scan states",
        [
            "Fresh means the full repo context is ready.",
            "Stale means the repo changed since the last scan.",
            "Interrupted means the previous scan did not finish.",
        ],
    )
    _print_lines(
        "Use it",
        [
            "Run `strata scan` to build or refresh repo context.",
            "Run `strata scan --force` to ignore any fresh cache and rebuild.",
            "If a previous scan was interrupted, rerun `strata scan` to recover and clear the temp marker.",
        ],
    )
    _print_lines(
        "Focused mode",
        [
            "Ask and run can still work without a full scan.",
            "When the scan is missing, stale, or interrupted, Strata uses focused context and suggests `strata scan`.",
        ],
    )


def _render_status_help() -> None:
    _print_intro("Status shows whether Strata outputs are current and whether full repo context is ready.")
    _print_lines(
        "Scan readiness",
        [
            "Fresh means the full repo context is ready.",
            "Stale means the repo changed since the last scan; run `strata scan`.",
            "Interrupted means the previous scan did not finish; run `strata scan`.",
            "Missing means focused mode is available, but full repo context needs `strata scan`.",
        ],
    )
    _print_lines(
        "Use it",
        [
            "Run `strata status` to check generated files and scan freshness.",
            "Run `strata start` if you want the beginner entrypoint with setup guidance.",
        ],
    )


def _render_doctor_help() -> None:
    _print_intro("Doctor helps diagnose install, PATH, and adapter setup problems.")
    _print_lines(
        "Install diagnostics",
        [
            "`strata doctor install`",
            "Checks the Python executable and version.",
            "Checks whether `strata` is on PATH with `shutil.which(\"strata\")`.",
            "Shows the current working directory and import status.",
        ],
    )
    _print_lines(
        "Windows tips",
        [
            "Run `py -m pip install -e .` for local development.",
            "If `strata` is not on PATH yet, try `py -m strata` from the repo root.",
            "Restart the VS Code terminal after PATH changes.",
            "If PowerShell works but VS Code does not, close and reopen VS Code.",
        ],
    )
    _print_lines(
        "Adapter checks",
        [
            "`strata doctor adapter`",
            "It shows whether the API key env is found or missing without printing the secret.",
            "Run it after `strata setup ai` if you want a quick readiness check.",
        ],
    )


def _render_gate_help() -> None:
    _print_intro("Gate is the final validation summary.")
    _print_lines(
        "It writes",
        [
            "`.aidc/gate_report.md`",
            "`.aidc/gate_report.json`",
        ],
    )
    _print_lines(
        "Remember",
        [
            "Gate does not replace your project tests.",
            "Run project tests before commit.",
        ],
    )


def _render_start_help() -> None:
    _print_intro("Start is the beginner entrypoint after Strata is installed in a project.")
    _print_lines(
        "It helps you",
        [
            "Scan the repository.",
            "Build the repo snapshot cache.",
            "Detect when files changed while Strata was scanning.",
            "See whether the full repo context is fresh, stale, missing, or interrupted.",
            "Check whether setup is ready.",
            "Move toward setup, ask, review, apply, and gate.",
        ],
    )
    _print_lines(
        "Scan readiness",
        [
            "Run `strata scan` to refresh repo context.",
            "Run `strata scan --force` to ignore a fresh cache and rebuild.",
            "Focused mode still works when the scan is missing or stale.",
        ],
    )
    _print_lines(
        "If Strata is not on PATH",
        [
            "Run `strata doctor install`.",
            "Then rerun `strata start` from the project directory.",
        ],
    )


def _print_intro(text: str) -> None:
    print(text)
    print()


def _print_lines(title: str, lines: list[str]) -> None:
    print(build_section(title))
    for line in lines:
        print(f"  {line}")
    print()


def _print_steps(title: str, steps: list[str]) -> None:
    print(build_section(title))
    for index, step in enumerate(steps, start=1):
        print(f"  {index}. {step}")
    print()


_HELP_TOPIC_RENDERERS = {
    "setup": _render_setup_help,
    "manual": _render_manual_help,
    "ollama": _render_ollama_help,
    "command": _render_command_help,
    "http": _render_http_help,
    "ask": _render_ask_help,
    "context": _render_context_help,
    "prepare": _render_prepare_help,
    "scan": _render_scan_help,
    "status": _render_status_help,
    "review": _render_review_help,
    "apply": _render_apply_help,
    "run": _render_run_help,
    "doctor": _render_doctor_help,
    "gate": _render_gate_help,
    "start": _render_start_help,
}
