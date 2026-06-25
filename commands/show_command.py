from cli_core import load_saved_graph, normalize_path
from cli_ui import (
    green,
    yellow,
    red,
    cyan,
    dim,
    print_title,
    print_kv,
    print_list,
)


def show_graph_summary() -> int:
    graph = load_saved_graph()

    if graph is None:
        return 1

    print_title("Strata graph summary")
    print_kv("Schema version", graph["schema_version"])
    print_kv("Root", graph["root"])
    print_kv("Files", len(graph["files"]))
    print_kv("Edges", len(graph["edges"]))
    print_kv("Backend routes", _count_routes(graph["files"]))

    print_title("Files")

    for file_info in graph["files"]:
        has_warning = bool(file_info.get("unresolved_imports", []))

        if has_warning:
            print(f"  {yellow('!')} {cyan(file_info['path'])}")
        else:
            print(f"  {green('•')} {cyan(file_info['path'])}")

        if file_info.get("language"):
            print(f"      {dim('language')}            {file_info['language']}")

        if file_info.get("framework"):
            print(f"      {dim('framework')}           {file_info['framework']}")

        if file_info.get("classes"):
            class_names = [item["name"] for item in file_info["classes"]]
            print(f"      {dim('classes')}             {', '.join(class_names)}")

        if file_info.get("functions"):
            function_names = [item["name"] for item in file_info["functions"]]
            print(f"      {dim('functions')}           {', '.join(function_names)}")

        if file_info.get("interfaces"):
            interface_names = [item["name"] for item in file_info["interfaces"]]
            print(f"      {dim('interfaces')}          {', '.join(interface_names)}")

        if file_info.get("types"):
            type_names = [item["name"] for item in file_info["types"]]
            print(f"      {dim('types')}               {', '.join(type_names)}")

        if file_info.get("enums"):
            enum_names = [item["name"] for item in file_info["enums"]]
            print(f"      {dim('enums')}               {', '.join(enum_names)}")

        if file_info.get("routes"):
            route_labels = [
                f"{route.get('method', '')} {route.get('path', '')}"
                for route in file_info["routes"]
            ]
            print(f"      {dim('routes')}              {', '.join(route_labels)}")

        if file_info.get("external_imports"):
            print(f"      {dim('external imports')}    {', '.join(file_info['external_imports'])}")

        if file_info.get("unresolved_imports"):
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
        print("    strata scan")
        print("    strata show")
        return 1

    print_title("File details")
    print_kv("Path", cyan(matching_file["path"]))
    print_kv("Language", matching_file["language"])

    if matching_file.get("framework"):
        print_kv("Framework hint", matching_file["framework"])

    class_names = [item["name"] for item in matching_file.get("classes", [])]
    function_names = [item["name"] for item in matching_file.get("functions", [])]
    interface_names = [item["name"] for item in matching_file.get("interfaces", [])]
    type_names = [item["name"] for item in matching_file.get("types", [])]
    enum_names = [item["name"] for item in matching_file.get("enums", [])]

    print_list("Classes", class_names)
    print_list("Functions", function_names)
    print_list("Interfaces", interface_names)
    print_list("Types", type_names)
    print_list("Enums", enum_names)
    print_list("Imports", matching_file.get("imports", []))
    print_list("External imports", matching_file.get("external_imports", []))

    _print_routes(matching_file.get("routes", []))

    if matching_file.get("unresolved_imports"):
        print_kv("Unresolved imports", yellow(", ".join(matching_file["unresolved_imports"])))
    else:
        print_kv("Unresolved imports", green("none"))

    if matching_file.get("unresolved_import_details"):
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


def _count_routes(files: list[dict]) -> int:
    count = 0

    for file_info in files:
        count += len(file_info.get("routes", []))

    return count


def _print_routes(routes: list[dict]) -> None:
    print_title("Backend routes")

    if not routes:
        print(f"  {dim('none')}")
        return

    for route in routes:
        method = route.get("method", "")
        route_path = route.get("path", "")
        line = route.get("line", "")
        source = route.get("source", "")

        print(
            f"  {green(method)} "
            f"{cyan(route_path)} "
            f"{dim('at line')} {line} "
            f"{dim('[' + source + ']')}"
        )
