from __future__ import annotations

from strata.commands.cli_ui import bold
from strata.utils.output import print_banner

from strata.core.status import analyze_status


def print_guided_entrypoint(root: str = ".") -> None:
    print_banner(compact=False)
    print()

    print("Strata helps you understand a repository and safely work through AI-assisted code changes.")
    print()

    print(bold("Start here:"))
    print("  strata start")
    print("  Strata will show your current status and one recommended next step.")
    print()

    print(bold("Follow up:"))
    for line in [
        "Run `strata start --continue` when you want Strata to attempt that step.",
        "Repository-changing actions still require confirmation.",
        "Run `strata settings` whenever you want to change workflow preferences.",
        "If `strata` does not work in another terminal, run `strata doctor install`.",
    ]:
        print(f"  {line}")
    print()

    print(bold("Connect AI:"))
    for line in _connect_ai_overview_lines(include_help_hint=False):
        print(f"  {line}")
    print()

    print(bold("Primary workflow:"))
    for command, description in _primary_workflow_lines():
        print(f"  {command}")
        print(f"    {description}")
    print()

    print(bold("Settings:"))
    for command, description in _settings_lines():
        print(f"  {command}")
        print(f"    {description}")

    print()
    print(bold("Current state"))
    print(f"  {_current_state(root)}")
    print()
    print(bold("Next:"))
    print(f"  {_recommended_next_command(root)}")
    print()
    print(bold("Advanced:"))
    print("  Run `strata help` to see all advanced commands.")


def print_usage() -> None:
    print_banner(compact=False)
    print()

    print("Strata helps you understand a repository and safely work through AI-assisted code changes.")
    print()
    print("Start here:")
    print("  strata start")
    print("  Strata will show your current status and one recommended next step.")
    print()

    print("Install and runtime:")
    print("  PyPI package: strata-repo-intel")
    print("  CLI command: strata")
    print("  Install: pipx install strata-repo-intel")
    print("  Alternative: python -m pip install --user strata-repo-intel")
    print("  Strata requires Python 3.13+; analyzed projects may target older Python versions.")
    print("  Add `.aidc/` to `.gitignore`; generated files may contain code excerpts or AI prompts.")
    print()

    print("Connect AI:")
    for line in _connect_ai_overview_lines(include_help_hint=True):
        print(f"  {line}")
    print()

    print("Primary workflow:")
    for command, description in _primary_workflow_lines():
        print(f"  {command}")
        print(f"    {description}")
    print()

    print("Settings:")
    for command, description in _settings_lines():
        print(f"  {command}")
        print(f"    {description}")
    print()

    print("Root path forms:")
    for line in _workflow_root_forms():
        print(f"  {line}")
    print()

    print("Selected-file examples:")
    print('  strata ask --file LoginForm "fix validation"')
    print('  strata run --file run_command "fix dry run output" --dry-run')
    print('  strata ask --file run_command --file ask_command "compare these flows"')
    print()

    print("Budgeted context examples:")
    print('  strata context --budget small "fix dry run plan output"')
    print('  strata context --format json --budget small "fix login button not disabling"')
    print('  strata ask --file run_command --budget small "fix dry run plan output"')
    print('  strata run --file LoginButton --budget small "fix disabled state" --dry-run')
    print('  strata prepare --budget small "fix validation"')
    print()

    print("Usage:")
    print("  strata <command> [args]")
    print("  strata help")
    print()

    print("Advanced commands:")
    for line, description in _advanced_command_entries():
        print(f"  {line}")
        if description:
            print(f"    {description}")
    print()

    print("Install help:")
    print("  If `strata` is unavailable, check PATH or reinstall `strata-repo-intel`.")
    print("  Supported agents: generic, local, aider, chatgpt")


def _main_workflow_lines() -> list[tuple[str, str]]:
    return _primary_workflow_lines()


def _primary_workflow_lines() -> list[tuple[str, str]]:
    return [
        ("strata start [path]", "Show the current workflow status and one recommended next step."),
        ("strata start --continue [path]", "Attempt the recommended next step. Repository-changing actions still require confirmation."),
    ]


def _settings_lines() -> list[tuple[str, str]]:
    return [
        ("strata settings", "View current workflow settings."),
        ("strata settings set capability <value>", "Change capability selection: auto, unknown, weak, medium, strong."),
        ("strata settings set surface <value>", "Change delivery surface: browser_copy, cli, vscode."),
        ("strata settings set mode <value>", "Change workflow mode: manual, hybrid, auto."),
    ]


def _connect_ai_overview_lines(include_help_hint: bool) -> list[str]:
    return [
        "Run `strata setup` for initial configuration and environment readiness.",
        "Run `strata setup ai` for guided setup with safe credential handling.",
        "You can change capability, delivery surface, or workflow mode later with `strata settings`.",
        "Strata stores only environment variable names for API keys; secrets stay in your environment.",
        "`strata settings` shows workflow preferences, not secret values.",
        "`strata setup --manual`",
        "  Browser AI: use ChatGPT, Claude, Gemini, or Copilot Chat.",
        "  Strata writes `.aidc/agent_prompt.md`; you paste it into the AI and save the returned diff as `.aidc/agent_patch.diff`.",
        "`strata setup --ollama`",
        "  Local AI with Ollama. Requires Ollama running and an installed model.",
        "`strata setup --codex-cli`",
        "  Use Codex CLI through Strata's command adapter.",
        "`strata setup --aider`",
        "  Use Aider through Strata's command adapter.",
        "`strata setup --command`",
        "  Use any custom CLI command that reads `.aidc/agent_prompt.md` and returns a patch.",
        "`strata setup --http`",
        "  Use an OpenAI-compatible HTTP API. Strata stores only the environment variable name for the key.",
        "  Strata can help save the key to your user environment on Windows.",
        "Then run `strata doctor adapter` if you want a readiness check, and use `strata start` for the normal workflow.",
        *(
            [
                "For step-by-step help, run `strata help setup`, `strata help ask`, or `strata help manual`.",
            ]
            if include_help_hint
            else []
        ),
    ]


def _advanced_command_entries() -> list[tuple[str, str | None]]:
    return [
        ("strata scan [path] [--force]", "Build or refresh the full repo scan; `--force` ignores a fresh cache."),
        ("strata show [path]", None),
        ("strata map [path]", None),
        ("strata routes [path]", None),
        ("strata diff [path]", None),
        ("strata patch [root]", None),
        ('strata ask [--file <reference>]... "<task>" [path]', "Prepare context for your configured AI mode and collect a safe patch."),
        ("strata review [path]", "Inspect and validate the patch before applying."),
        ("strata apply [--yes] [--dry-run] [path]", "Validate or apply the generated patch."),
        ("strata execute", "Run the configured command adapter and produce .aidc/agent_patch.diff."),
        ("strata execute <root>", None),
        ("strata doctor adapter", None),
        ("strata doctor adapter <root>", None),
        ("strata doctor install", "Check PATH, Python, and local install wiring."),
        ("strata snapshot [path]", None),
        ("strata verify", None),
        ("strata verify <root>", None),
        ("strata gate", None),
        ("strata gate <root>", None),
        ("strata setup", None),
        ("strata setup ai", None),
        ("strata setup ai --check", None),
        ("strata setup --manual", None),
        ("strata setup --command", None),
        ("strata setup --aider", None),
        ("strata setup --codex-cli", None),
        ("strata setup --http", None),
        ("strata setup --ollama", None),
        ("strata setup --show", None),
        ("strata config [root]", None),
        ("strata config init [root]", None),
        ("strata config set <key> <value> [root]", None),
        ("strata config set mode hybrid", None),
        ("strata config set agent codex", None),
        ("strata config set auto_snapshot false", None),
        ("strata config set command_timeout_seconds 120", None),
        ("strata config set http_timeout_seconds 120", None),
        ("strata config set http_timeout 120", None),
        ("strata config set base_url http://localhost:1234/v1", None),
        ("strata config set api_key_env OPENAI_API_KEY", None),
        ('strata brief "<task>"', None),
        ('strata brief <path> "<task>"', None),
        ("strata cycles [path]", None),
        ("strata health [path]", None),
        ("strata impact <file>", None),
        ("strata impact <root> <file>", None),
        ("strata tests-for <file>", None),
        ("strata tests-for <root> <file>", None),
        ('strata preflight "<task>"', None),
        ('strata preflight <root> "<task>"', None),
        ('strata context [--budget <preset|tokens>] [--format <markdown|json>] "<task>" [root]', "Compile budget-aware Markdown or JSON context. Use `ask` or `run --file` for selected-file anchoring."),
        ('strata prepare "<task>"', None),
        ('strata prepare "<task>" <root>', None),
        ('strata run [--file <reference>]... "<task>"', "Prepare context, request a patch, review it, and end with `strata apply` as the next step."),
        ('strata run "<task>" <root>', None),
        ('strata run --file <reference> --file <reference> "<task>"', None),
        ('strata run --type <task_type> "<task>"', None),
        ('strata run --type <task_type> "<task>" <root>', None),
        ('strata run --fast "<task>"', "Same guided flow, but asks before applying a validated patch."),
        ('strata run --fast "<task>" <root>', None),
        ('strata run --dry-run "<task>"', None),
        ('strata run --dry-run --type <task_type> "<task>"', None),
        ('strata run "<task>" --dry-run', None),
        ('strata run "<task>" --type <task_type>', None),
        ('strata run "<task>" --fast', None),
        ('strata run "<task>" --fast <root>', None),
        ('strata agent-prompt "<task>" <agent>', None),
        ('strata agent-prompt <root> "<task>" <agent>', None),
        ("strata status [path]", "Show generated files and full repo scan freshness."),
        ("strata help scan", "Explain scan freshness, interrupted scans, and `--force`."),
        ("strata help status", "Explain generated-file status and full repo readiness."),
        ("strata help context", "Explain budgeted context generation and the prompt estimate."),
        ("strata help prepare", "Explain prompt preparation and the budgeted content estimate."),
        ("strata help", None),
        ("strata apply --dry-run", None),
        ("strata apply --dry-run <root>", None),
        ("strata apply --yes <root>", None),
    ]


def _workflow_root_forms() -> list[str]:
    return [
        'strata start <root>',
        'strata start --continue <root>',
        'strata ask "<task>" <root>',
        "strata review <root>",
        "strata apply --dry-run <root>",
        "strata apply --yes <root>",
    ]


def _current_state(root: str) -> str:
    try:
        status = analyze_status(root)
    except Exception:
        return "unknown"

    state = str(status.get("state", "unknown")).strip()
    if not state:
        return "unknown"

    return state


def _recommended_next_command(root: str) -> str:
    state = _current_state(root)

    if state == "current":
        return 'Run `strata ask "your task"`.'

    return "Run `strata start`."
