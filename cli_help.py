from cli_ui import bold
from ui import print_banner

from status import analyze_status


def print_guided_entrypoint(root: str = ".") -> None:
    print_banner(compact=False)
    print()

    print(bold("New here?"))
    for line in [
        "1. Run `strata start`",
        "2. Run `strata setup`",
        '3. Run `strata run "your task"`',
        "If `strata` does not work in another terminal, run `strata doctor install`.",
    ]:
        print(f"  {line}")
    print()

    print(bold("Connect AI:"))
    for line in _connect_ai_overview_lines(include_help_hint=False):
        print(f"  {line}")
    print()

    print(bold("Main workflow:"))
    for index, (command, description) in enumerate(_main_workflow_lines(), start=1):
        print(f"  {index}. {command}")
        print(f"     {description}")
        if index != 4:
            print()

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

    print("Connect AI:")
    for line in _connect_ai_overview_lines(include_help_hint=True):
        print(f"  {line}")
    print()

    print("Main workflow:")
    for command, description in _main_workflow_lines():
        print(f"  {command}")
        print(f"    {description}")
    print()

    print("Root path forms:")
    for line in _workflow_root_forms():
        print(f"  {line}")
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

    print("Legacy / fallback:")
    print("Legacy fallback: use `py cli.py ...` if the `strata` entry point is unavailable.")
    print("  Supported agents: generic, local, aider, chatgpt")


def _main_workflow_lines() -> list[tuple[str, str]]:
    return [
        ("strata start [path]", "Set up Strata and understand this project."),
        ('strata ask "<task>" [path]', "Prepare context for your configured AI mode and collect a safe patch."),
        ("strata review [path]", "Inspect and validate the patch before applying."),
        ("strata apply [--yes] [--dry-run] [path]", "Validate or apply the generated patch."),
    ]


def _connect_ai_overview_lines(include_help_hint: bool) -> list[str]:
    return [
        "Run `strata setup` to choose how Strata talks to AI.",
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
        "  Use an OpenAI-compatible HTTP API.",
        'Then run `strata ask "fix bug"`, `strata review`, `strata apply --dry-run`, and `strata apply`.',
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
        ("strata scan [path]", None),
        ("strata show [path]", None),
        ("strata map [path]", None),
        ("strata routes [path]", None),
        ("strata diff [path]", None),
        ("strata patch [root]", None),
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
        ('strata context "<task>"', None),
        ('strata context <root> "<task>"', None),
        ('strata prepare "<task>"', None),
        ('strata prepare "<task>" <root>', None),
        ('strata run "<task>"', "Prepare context, request a patch, review it, and end with `strata apply` as the next step."),
        ('strata run "<task>" <root>', None),
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
        ("strata status [path]", None),
        ("strata help", None),
        ("strata apply --dry-run", None),
        ("strata apply --dry-run <root>", None),
        ("strata apply --yes <root>", None),
    ]


def _workflow_root_forms() -> list[str]:
    return [
        'strata start <root>',
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
