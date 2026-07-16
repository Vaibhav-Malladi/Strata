from __future__ import annotations

import sys

from strata.commands.cli_help import print_guided_entrypoint, print_usage
from strata.commands.agent_prompt_command import write_agent_prompt_command
from strata.commands.brief_command import write_brief
from strata.commands.config_command import (
    write_config_command,
    write_config_init_command,
    write_config_set_command,
)
from strata.commands.ask_command import write_ask_command
from strata.commands.context_command import write_context
from strata.commands.cycles_command import show_cycles
from strata.commands.diff_command import write_diff_command
from strata.commands.doctor_command import write_doctor_command
from strata.commands.gate_command import write_gate_command
from strata.commands.health_command import show_health
from strata.commands.impact_command import show_impact
from strata.commands.execute_command import write_execute_command
from strata.commands.apply_command import write_apply_command, write_apply_dry_run_command
from strata.commands.map_command import write_map
from strata.commands.patch_command import write_patch_command
from strata.commands.prepare_command import write_prepare_command
from strata.commands.review_command import write_review_command
from strata.commands.preflight_command import write_preflight
from strata.commands.run_command import write_run_command
from strata.commands.settings_command import write_settings_command, write_settings_set_command
from strata.commands.start_command import write_start_command
from strata.commands.setup_command import (
    setup_aider,
    write_setup_ai_command,
    setup_codex_cli,
    setup_command,
    setup_http,
    setup_manual,
    setup_ollama,
    setup_show,
    write_setup_command,
)
from strata.commands.snapshot_command import write_snapshot_command
from strata.commands.verify_command import write_verify_command
from strata.commands.routes_command import write_routes
from strata.commands.scan_command import write_graph
from strata.commands.show_command import show_file, show_graph_summary
from strata.commands.status_command import show_status
from strata.commands.tests_for_command import show_tests_for
from strata.commands.help_topics import print_help_topic


def main() -> int:
    args = sys.argv[1:]

    if not args:
        print_guided_entrypoint()
        return 0

    command = args[0]

    if command == "help":
        if len(args) == 1:
            print_usage()
            return 0
        if len(args) == 2:
            return _exit_code(print_help_topic(args[1]))
        print_usage()
        return 1

    if command in {"-h", "--help"}:
        print_usage()
        return 0

    if command == "scan":
        force = False
        positionals: list[str] = []

        for arg in args[1:]:
            if arg == "--force":
                force = True
                continue

            if arg.startswith("-"):
                print_usage()
                return 1

            positionals.append(arg)

        if len(positionals) > 1:
            print_usage()
            return 1

        root = positionals[0] if positionals else "."
        return _exit_code(write_graph(root, force=force))

    if command == "start":
        return _exit_code(_handle_start_command(args[1:]))

    if command == "settings":
        return _exit_code(_handle_settings_command(args[1:]))

    if command == "ask":
        return _exit_code(write_ask_command(".", *args[1:]))

    if command == "show":
        if len(args) == 1:
            show_graph_summary()
            return 0
        if len(args) == 2:
            show_file(args[1])
            return 0
        print_usage()
        return 1

    if command == "map":
        if len(args) == 1:
            return _exit_code(write_map("."))
        if len(args) == 2:
            return _exit_code(write_map(args[1]))
        print_usage()
        return 1

    if command == "routes":
        if len(args) == 1:
            return _exit_code(write_routes("."))
        if len(args) == 2:
            return _exit_code(write_routes(args[1]))
        print_usage()
        return 1

    if command == "diff":
        if len(args) == 1:
            return _exit_code(write_diff_command("."))
        if len(args) == 2:
            return _exit_code(write_diff_command(args[1]))
        print_usage()
        return 1

    if command == "patch":
        if len(args) == 1:
            return _exit_code(write_patch_command("."))
        if len(args) == 2:
            return _exit_code(write_patch_command(args[1]))
        print_usage()
        return 1

    if command == "apply":
        return _exit_code(_handle_apply_command(args[1:]))

    if command == "execute":
        return _exit_code(_handle_execute_command(args[1:]))

    if command == "doctor":
        return _exit_code(write_doctor_command(*args[1:]))

    if command == "snapshot":
        if len(args) == 1:
            return _exit_code(write_snapshot_command("."))
        if len(args) == 2:
            return _exit_code(write_snapshot_command(args[1]))
        print_usage()
        return 1

    if command == "verify":
        if len(args) == 1:
            return _exit_code(write_verify_command("."))
        if len(args) == 2:
            return _exit_code(write_verify_command(args[1]))
        print_usage()
        return 1

    if command == "gate":
        if len(args) == 1:
            return _exit_code(write_gate_command("."))
        if len(args) == 2:
            return _exit_code(write_gate_command(args[1]))
        print_usage()
        return 1

    if command == "review":
        if len(args) == 1:
            return _exit_code(write_review_command("."))
        if len(args) == 2:
            return _exit_code(write_review_command(args[1]))
        print_usage()
        return 1

    if command == "setup":
        return _exit_code(_handle_setup_command(args[1:]))

    if command == "config":
        if len(args) == 1:
            return _exit_code(write_config_command("."))
        if len(args) == 2:
            if args[1] == "init":
                return _exit_code(write_config_init_command("."))
            if args[1] == "set":
                print_usage()
                return 1
            return _exit_code(write_config_command(args[1]))
        if len(args) == 3 and args[1] == "init":
            return _exit_code(write_config_init_command(args[2]))
        if len(args) == 4 and args[1] == "set":
            return _exit_code(write_config_set_command(args[2], args[3], "."))
        if len(args) == 5 and args[1] == "set":
            return _exit_code(write_config_set_command(args[2], args[3], args[4]))
        print_usage()
        return 1

    if command == "brief":
        if len(args) == 2:
            return _exit_code(write_brief(".", args[1]))
        if len(args) == 3:
            return _exit_code(write_brief(args[1], args[2]))
        print_usage()
        return 1

    if command == "cycles":
        if len(args) == 1:
            return _exit_code(show_cycles("."))
        if len(args) == 2:
            return _exit_code(show_cycles(args[1]))
        print_usage()
        return 1

    if command == "health":
        if len(args) == 1:
            return _exit_code(show_health("."))
        if len(args) == 2:
            return _exit_code(show_health(args[1]))
        print_usage()
        return 1

    if command == "impact":
        if len(args) == 2:
            return _exit_code(show_impact(".", args[1]))
        if len(args) == 3:
            return _exit_code(show_impact(args[1], args[2]))
        print_usage()
        return 1

    if command == "tests-for":
        if len(args) == 2:
            return _exit_code(show_tests_for(".", args[1]))
        if len(args) == 3:
            return _exit_code(show_tests_for(args[1], args[2]))
        print_usage()
        return 1

    if command == "preflight":
        if len(args) == 2:
            return _exit_code(write_preflight(".", args[1]))
        if len(args) == 3:
            return _exit_code(write_preflight(args[1], args[2]))
        print_usage()
        return 1

    if command == "prepare":
        return _exit_code(write_prepare_command(".", *args[1:]))

    if command == "run":
        return _exit_code(write_run_command(".", *args[1:]))

    if command == "context":
        return _exit_code(write_context(".", *args[1:]))

    if command == "agent-prompt":
        if len(args) == 3:
            write_agent_prompt_command(".", args[1], args[2])
            return 0
        if len(args) == 4:
            write_agent_prompt_command(args[1], args[2], args[3])
            return 0
        print_usage()
        return 1

    if command == "status":
        if len(args) == 1:
            show_status(".")
            return 0
        if len(args) == 2:
            show_status(args[1])
            return 0
        print_usage()
        return 1

    print_usage()
    return 1


def _exit_code(result) -> int:
    if result is None:
        return 0

    return result


def _handle_apply_command(args: list[str]) -> int:
    dry_run = False
    yes = False
    positionals: list[str] = []

    for arg in args:
        if arg == "--dry-run":
            dry_run = True
            continue

        if arg == "--yes":
            yes = True
            continue

        if arg.startswith("-"):
            print_usage()
            return 1

        positionals.append(arg)

    if len(positionals) > 1:
        print_usage()
        return 1

    root = positionals[0] if positionals else "."

    if dry_run:
        return write_apply_dry_run_command(root)

    return write_apply_command(root, yes=yes)


def _handle_start_command(args: list[str]) -> int:
    continue_action = False
    positionals: list[str] = []

    for arg in args:
        if arg == "--continue":
            if continue_action:
                print_usage()
                return 1
            continue_action = True
            continue
        if arg.startswith("-"):
            print_usage()
            return 1
        positionals.append(arg)

    if len(positionals) > 1:
        print_usage()
        return 1

    root = positionals[0] if positionals else "."
    return write_start_command(root, continue_action=continue_action)


def _handle_settings_command(args: list[str]) -> int:
    if not args:
        return write_settings_command(".")

    if len(args) == 3 and args[0] == "set":
        return write_settings_set_command(args[1], args[2], ".")

    print_usage()
    return 1


def _handle_ask_command(args: list[str]) -> int:
    return _exit_code(write_ask_command(".", *args))


def _handle_execute_command(args: list[str]) -> int:
    dry_run = False
    positionals: list[str] = []

    for arg in args:
        if arg == "--dry-run":
            dry_run = True
            continue

        if arg.startswith("-"):
            print_usage()
            return 1

        positionals.append(arg)

    if len(positionals) > 1:
        print_usage()
        return 1

    root = positionals[0] if positionals else "."
    return write_execute_command(root, dry_run=dry_run)


def _handle_setup_command(args: list[str]) -> int:
    preset: str | None = None
    show = False
    guided_ai = False
    guided_ai_check = False
    positionals: list[str] = []

    for arg in args:
        if arg == "--check":
            if preset is not None or show:
                print_usage()
                return 1
            guided_ai_check = True
            continue

        if arg == "ai":
            if preset is not None or show or guided_ai or positionals:
                print_usage()
                return 1
            guided_ai = True
            continue

        if arg == "--manual":
            preset = _set_preset(preset, "manual")
            if preset is None:
                return 1
            continue

        if arg == "--command":
            preset = _set_preset(preset, "command")
            if preset is None:
                return 1
            continue

        if arg == "--aider":
            preset = _set_preset(preset, "aider")
            if preset is None:
                return 1
            continue

        if arg == "--codex-cli":
            preset = _set_preset(preset, "codex_cli")
            if preset is None:
                return 1
            continue

        if arg == "--http":
            preset = _set_preset(preset, "http")
            if preset is None:
                return 1
            continue

        if arg == "--ollama":
            preset = _set_preset(preset, "ollama")
            if preset is None:
                return 1
            continue

        if arg == "--show":
            if preset is not None:
                print_usage()
                return 1
            show = True
            continue

        if arg.startswith("-"):
            print_usage()
            return 1

        positionals.append(arg)

    if len(positionals) > 1:
        print_usage()
        return 1

    root = positionals[0] if positionals else "."

    if show:
        return _setup_exit_code(setup_show(root))

    if guided_ai_check and not guided_ai:
        print_usage()
        return 1

    if guided_ai:
        return write_setup_ai_command(root, check=guided_ai_check)

    if preset == "manual":
        return _setup_exit_code(setup_manual(root))

    if preset == "command":
        return _setup_exit_code(setup_command(root))

    if preset == "aider":
        return _setup_exit_code(setup_aider(root))

    if preset == "codex_cli":
        return _setup_exit_code(setup_codex_cli(root))

    if preset == "http":
        return _setup_exit_code(setup_http(root))

    if preset == "ollama":
        return _setup_exit_code(setup_ollama(root))

    return write_setup_command(root)


def _set_preset(current: str | None, next_preset: str) -> str | None:
    if current is None:
        return next_preset

    if current == next_preset:
        return current

    print_usage()
    return None


def _setup_exit_code(result: dict) -> int:
    status = str(result.get("status", "")).lower()

    if status in {"configured", "needs_input"}:
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
