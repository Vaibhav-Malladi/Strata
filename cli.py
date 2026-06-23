import sys

from cli_help import print_usage
from commands.agent_prompt_command import write_agent_prompt_command
from commands.brief_command import write_brief
from commands.config_command import (
    write_config_command,
    write_config_init_command,
    write_config_set_command,
)
from commands.context_command import write_context
from commands.cycles_command import show_cycles
from commands.diff_command import write_diff_command
from commands.gate_command import write_gate_command
from commands.health_command import show_health
from commands.impact_command import show_impact
from commands.map_command import write_map
from commands.preflight_command import write_preflight
from commands.snapshot_command import write_snapshot_command
from commands.verify_command import write_verify_command
from commands.routes_command import write_routes
from commands.scan_command import write_graph
from commands.show_command import show_file, show_graph_summary
from commands.status_command import show_status
from commands.tests_for_command import show_tests_for


def main() -> int:
    args = sys.argv[1:]

    if not args:
        print_usage()
        return 0

    command = args[0]

    if command in {"help", "-h", "--help"}:
        print_usage()
        return 0

    if command == "scan":
        if len(args) == 1:
            return _exit_code(write_graph("."))
        if len(args) == 2:
            return _exit_code(write_graph(args[1]))
        print_usage()
        return 1

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

    if command == "context":
        if len(args) == 2:
            return _exit_code(write_context(".", args[1]))
        if len(args) == 3:
            return _exit_code(write_context(args[1], args[2]))
        print_usage()
        return 1

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


if __name__ == "__main__":
    sys.exit(main())
