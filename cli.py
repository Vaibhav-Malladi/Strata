import json
import os
import sys

from brief import write_task_brief
from graph import validate_graph
from map_writer import write_project_map
from scanner import scan_repo


OUTPUT_DIR = ".aidc"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "graph.json")
PROJECT_MAP_FILE = os.path.join(OUTPUT_DIR, "project_map.md")
TASK_BRIEF_FILE = os.path.join(OUTPUT_DIR, "task_brief.md")


USE_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def color(text: str, code: str) -> str:
    if not USE_COLOR:
        return text

    return f"\033[{code}m{text}\033[0m"


def green(text: str) -> str:
    return color(text, "32")


def yellow(text: str) -> str:
    return color(text, "33")


def red(text: str) -> str:
    return color(text, "31")


def cyan(text: str) -> str:
    return color(text, "36")


def dim(text: str) -> str:
    return color(text, "90")


def bold(text: str) -> str:
    return color(text, "1")


def normalize_path(path: str) -> str:
    return os.path.normpath(path)


def print_title(title: str) -> None:
    print()
    print(bold(cyan(title)))
    print(dim("─" * len(title)))


def print_kv(label: str, value) -> None:
    print(f"  {dim(label.ljust(18))} {value}")


def print_list(label: str, values: list[str]) -> None:
    if values:
        print_kv(label, ", ".join(values))
    else:
        print_kv(label, dim("none"))


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


def build_graph(root_path: str) -> dict | None:
    root_path = normalize_path(root_path)

    if not os.path.exists(root_path):
        print_title(red("Scan failed"))
        print_kv("Reason", f"path does not exist: {root_path}")
        return None

    if not os.path.isdir(root_path):
        print_title(red("Scan failed"))
        print_kv("Reason", f"path is not a directory: {root_path}")
        return None

    graph = scan_repo(root_path)
    problems = validate_graph(graph)

    if problems:
        print_title(red("Graph validation failed"))

        for problem in problems:
            print(f"  {red('✗')} {problem}")

        return None

    return graph


def save_graph(graph: dict) -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as file:
        json.dump(graph, file, indent=2)


def count_unresolved_imports(graph: dict) -> int:
    unresolved_count = 0

    for file_info in graph["files"]:
        unresolved_count += len(file_info["unresolved_imports"])

    return unresolved_count


def write_graph(root_path: str) -> int:
    graph = build_graph(root_path)

    if graph is None:
        return 1

    save_graph(graph)

    unresolved_count = count_unresolved_imports(graph)

    print_title(green("Scan complete"))
    print_kv("Output", OUTPUT_FILE)
    print_kv("Root", graph["root"])
    print_kv("Files", len(graph["files"]))
    print_kv("Edges", len(graph["edges"]))

    if unresolved_count:
        print_kv("Warnings", yellow(f"{unresolved_count} unresolved import(s)"))
    else:
        print_kv("Warnings", green("none"))

    return 0


def write_map(root_path: str) -> int:
    graph = build_graph(root_path)

    if graph is None:
        return 1

    save_graph(graph)
    write_project_map(graph, PROJECT_MAP_FILE)

    unresolved_count = count_unresolved_imports(graph)

    print_title(green("Project map generated"))
    print_kv("Graph", OUTPUT_FILE)
    print_kv("Project map", PROJECT_MAP_FILE)
    print_kv("Root", graph["root"])
    print_kv("Files", len(graph["files"]))
    print_kv("Edges", len(graph["edges"]))

    if unresolved_count:
        print_kv("Warnings", yellow(f"{unresolved_count} unresolved import(s)"))
    else:
        print_kv("Warnings", green("none"))

    return 0


def write_brief(root_path: str, task: str) -> int:
    graph = build_graph(root_path)

    if graph is None:
        return 1

    save_graph(graph)
    write_task_brief(graph, task, TASK_BRIEF_FILE)

    unresolved_count = count_unresolved_imports(graph)

    print_title(green("Task brief generated"))
    print_kv("Graph", OUTPUT_FILE)
    print_kv("Task brief", TASK_BRIEF_FILE)
    print_kv("Root", graph["root"])
    print_kv("Files", len(graph["files"]))
    print_kv("Edges", len(graph["edges"]))

    if unresolved_count:
        print_kv("Warnings", yellow(f"{unresolved_count} unresolved import(s)"))
    else:
        print_kv("Warnings", green("none"))

    return 0


def load_saved_graph() -> dict | None:
    if not os.path.exists(OUTPUT_FILE):
        print_title(red("No saved graph found"))
        print("  Run this first:")
        print()
        print("    py cli.py scan")
        return None

    with open(OUTPUT_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def show_graph_summary() -> int:
    graph = load_saved_graph()

    if graph is None:
        return 1

    print_title("Strata graph summary")
    print_kv("Schema version", graph["schema_version"])
    print_kv("Root", graph["root"])
    print_kv("Files", len(graph["files"]))
    print_kv("Edges", len(graph["edges"]))

    print_title("Files")

    for file_info in graph["files"]:
        has_warning = bool(file_info["unresolved_imports"])

        if has_warning:
            print(f"  {yellow('!')} {cyan(file_info['path'])}")
        else:
            print(f"  {green('•')} {cyan(file_info['path'])}")

        if file_info["classes"]:
            class_names = [item["name"] for item in file_info["classes"]]
            print(f"      {dim('classes')}             {', '.join(class_names)}")

        if file_info["functions"]:
            function_names = [item["name"] for item in file_info["functions"]]
            print(f"      {dim('functions')}           {', '.join(function_names)}")

        if file_info["external_imports"]:
            print(f"      {dim('external imports')}    {', '.join(file_info['external_imports'])}")

        if file_info["unresolved_imports"]:
            unresolved = ", ".join(file_info["unresolved_imports"])
            print(f"      {dim('unresolved imports')}  {yellow(unresolved)}")

    print_title("Dependency edges")

    if not graph["edges"]:
        print(f"  {dim('none')}")
    else:
        for edge in graph["edges"]:
            print(
                f"  {cyan(edge['from'])} "
                f"{dim('->')} "
                f"{cyan(edge['to'])} "
                f"{dim('[' + edge['import'] + ']')}"
            )

    return 0


def show_file(path: str) -> int:
    graph = load_saved_graph()

    if graph is None:
        return 1

    requested_path = normalize_path(path)
    matching_file = None

    for file_info in graph["files"]:
        saved_path = normalize_path(file_info["path"])

        if saved_path == requested_path or saved_path.endswith(requested_path):
            matching_file = file_info
            break

    if matching_file is None:
        print_title(red("File not found in graph"))
        print_kv("Requested", path)
        print()
        print("  Run a scan first, or check the file path:")
        print()
        print("    py cli.py scan")
        print("    py cli.py show")
        return 1

    print_title("File details")
    print_kv("Path", cyan(matching_file["path"]))
    print_kv("Language", matching_file["language"])

    class_names = [item["name"] for item in matching_file["classes"]]
    function_names = [item["name"] for item in matching_file["functions"]]

    print_list("Classes", class_names)
    print_list("Functions", function_names)
    print_list("Imports", matching_file["imports"])
    print_list("External imports", matching_file["external_imports"])

    if matching_file["unresolved_imports"]:
        print_kv("Unresolved imports", yellow(", ".join(matching_file["unresolved_imports"])))
    else:
        print_kv("Unresolved imports", green("none"))

    if matching_file["unresolved_import_details"]:
        print_title(yellow("Warnings"))
        print(f"  Unresolved imports found in {matching_file['path']}:")

        for import_detail in matching_file["unresolved_import_details"]:
            print(
                f"  {yellow('!')} {import_detail['name']} "
                f"{dim('at line')} {import_detail['line']}"
            )

    print_title("Outgoing dependencies")

    outgoing_edges = [
        edge for edge in graph["edges"]
        if normalize_path(edge["from"]) == normalize_path(matching_file["path"])
    ]

    if not outgoing_edges:
        print(f"  {dim('none')}")
    else:
        for edge in outgoing_edges:
            print(
                f"  {cyan(edge['from'])} "
                f"{dim('->')} "
                f"{cyan(edge['to'])} "
                f"{dim('[' + edge['import'] + ']')}"
            )

    print_title("Incoming dependencies")

    incoming_edges = [
        edge for edge in graph["edges"]
        if normalize_path(edge["to"]) == normalize_path(matching_file["path"])
    ]

    if not incoming_edges:
        print(f"  {dim('none')}")
    else:
        for edge in incoming_edges:
            print(
                f"  {cyan(edge['from'])} "
                f"{dim('->')} "
                f"{cyan(edge['to'])} "
                f"{dim('[' + edge['import'] + ']')}"
            )

    return 0


def main() -> int:
    if len(sys.argv) == 2:
        command = sys.argv[1]

        if command == "scan":
            return write_graph(".")

        if command == "show":
            return show_graph_summary()

        if command == "map":
            return write_map(".")

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

    if len(sys.argv) == 4:
        command = sys.argv[1]

        if command == "brief":
            return write_brief(sys.argv[2], sys.argv[3])

    print_usage()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())