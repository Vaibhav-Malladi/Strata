import sys

from cli_help import print_usage
from commands.agent_prompt_command import write_agent_prompt_command
from commands.brief_command import write_brief
from commands.cycles_command import show_cycles
from commands.health_command import show_health
from commands.impact_command import show_impact
from commands.map_command import write_map
from commands.preflight_command import write_preflight
from commands.scan_command import write_graph
from commands.show_command import show_file, show_graph_summary
from commands.tests_for_command import show_tests_for


def main() -> None:
    args = sys.argv[1:]

    if not args:
        print_usage()
        return

    command = args[0]

    if command in {"help", "-h", "--help"}:
        print_usage()
        return

    if command == "scan":
        if len(args) == 1:
            write_graph(".")
            return
        if len(args) == 2:
            write_graph(args[1])
            return
        print_usage()
        return

    if command == "show":
        if len(args) == 1:
            show_graph_summary()
            return
        if len(args) == 2:
            show_file(args[1])
            return
        print_usage()
        return

    if command == "map":
        if len(args) == 1:
            write_map(".")
            return
        if len(args) == 2:
            write_map(args[1])
            return
        print_usage()
        return

    if command == "brief":
        if len(args) == 2:
            write_brief(".", args[1])
            return
        if len(args) == 3:
            write_brief(args[1], args[2])
            return
        print_usage()
        return

    if command == "cycles":
        if len(args) == 1:
            show_cycles(".")
            return
        if len(args) == 2:
            show_cycles(args[1])
            return
        print_usage()
        return

    if command == "health":
        if len(args) == 1:
            show_health(".")
            return
        if len(args) == 2:
            show_health(args[1])
            return
        print_usage()
        return

    if command == "impact":
        if len(args) == 2:
            show_impact(".", args[1])
            return
        if len(args) == 3:
            show_impact(args[1], args[2])
            return
        print_usage()
        return

    if command == "tests-for":
        if len(args) == 2:
            show_tests_for(".", args[1])
            return
        if len(args) == 3:
            show_tests_for(args[1], args[2])
            return
        print_usage()
        return

    if command == "preflight":
        if len(args) == 2:
            write_preflight(".", args[1])
            return
        if len(args) == 3:
            write_preflight(args[1], args[2])
            return
        print_usage()
        return

    if command == "agent-prompt":
        if len(args) == 3:
            write_agent_prompt_command(".", args[1], args[2])
            return
        if len(args) == 4:
            write_agent_prompt_command(args[1], args[2], args[3])
            return
        print_usage()
        return

    print_usage()


if __name__ == "__main__":
    main()