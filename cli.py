import sys

from commands.brief_command import write_brief
from commands.cycles_command import show_cycles
from commands.health_command import show_health
from commands.impact_command import show_impact
from commands.map_command import write_map
from commands.preflight_command import write_preflight
from commands.scan_command import write_graph
from commands.show_command import show_file, show_graph_summary
from commands.tests_for_command import show_tests_for

from cli_ui import bold, cyan, dim


def print_usage() -> None:
    print(bold(cyan("Strata")))
    print(dim("Repository structure and dependency inspector"))
    print()
    print(bold("Usage"))
    print("  py cli.py scan")
    print("  py cli.py scan <path>")
    print("  py cli.py show")
    print("  py cli.py show <path>")
    print("  py cli.py map")
    print("  py cli.py map <path>")
    print('  py cli.py brief "<task>"')
    print('  py cli.py brief <path> "<task>"')
    print("  py cli.py cycles")
    print("  py cli.py cycles <path>")
    print("  py cli.py health")
    print("  py cli.py health <path>")
    print("  py cli.py impact <file>")
    print("  py cli.py impact <root> <file>")
    print("  py cli.py tests-for <file>")
    print("  py cli.py tests-for <root> <file>")
    print('  py cli.py preflight "<task>"')
    print('  py cli.py preflight <root> "<task>"')
    print("  py cli.py help")
    print()
    print(bold("Examples"))
    print("  py cli.py scan")
    print("  py cli.py scan tmp_repo")
    print("  py cli.py show")
    print("  py cli.py show tmp_repo/main.py")
    print("  py cli.py map")
    print("  py cli.py map tmp_repo")
    print('  py cli.py brief "add map command tests"')
    print('  py cli.py brief tmp_repo "add unresolved import warning"')
    print("  py cli.py cycles")
    print("  py cli.py cycles tmp_repo")
    print("  py cli.py health")
    print("  py cli.py health tmp_repo")
    print("  py cli.py impact helper.py")
    print("  py cli.py impact tmp_repo helper.py")
    print("  py cli.py tests-for map_writer.py")
    print("  py cli.py tests-for tmp_repo helper.py")
    print('  py cli.py preflight "add map command tests"')
    print('  py cli.py preflight tmp_repo "change helper behavior"')


def main() -> int:
    if len(sys.argv) == 2:
        command = sys.argv[1]

        if command == "scan":
            return write_graph(".")

        if command == "show":
            return show_graph_summary()

        if command == "map":
            return write_map(".")

        if command == "cycles":
            return show_cycles(".")

        if command == "health":
            return show_health(".")

        if command in {"help", "--help", "-h"}:
            print_usage()
            return 0

    if len(sys.argv) == 3:
        command = sys.argv[1]

        if command == "scan":
            return write_graph(sys.argv[2])

        if command == "show":
            return show_file(sys.argv[2])

        if command == "map":
            return write_map(sys.argv[2])

        if command == "brief":
            return write_brief(".", sys.argv[2])

        if command == "cycles":
            return show_cycles(sys.argv[2])

        if command == "health":
            return show_health(sys.argv[2])

        if command == "impact":
            return show_impact(".", sys.argv[2])

        if command == "tests-for":
            return show_tests_for(".", sys.argv[2])

        if command == "preflight":
            return write_preflight(".", sys.argv[2])

    if len(sys.argv) == 4:
        command = sys.argv[1]

        if command == "brief":
            return write_brief(sys.argv[2], sys.argv[3])

        if command == "impact":
            return show_impact(sys.argv[2], sys.argv[3])

        if command == "tests-for":
            return show_tests_for(sys.argv[2], sys.argv[3])

        if command == "preflight":
            return write_preflight(sys.argv[2], sys.argv[3])

    print_usage()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())