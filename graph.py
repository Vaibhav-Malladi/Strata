def validate_graph(graph: dict) -> list[str]:
    """
    Validate the basic structure of a Strata graph.

    Returns a list of problems.
    If the list is empty, the graph is valid.
    """

    problems = []

    if not isinstance(graph, dict):
        return ["graph must be a dictionary"]

    if "schema_version" not in graph:
        problems.append("graph is missing schema_version")
    elif graph["schema_version"] != 1:
        problems.append("graph schema_version must be 1")

    if "root" not in graph:
        problems.append("graph is missing root")

    if "files" not in graph:
        problems.append("graph is missing files")
        return problems

    if not isinstance(graph["files"], list):
        problems.append("graph files must be a list")
        return problems

    for index, file_info in enumerate(graph["files"]):
        if not isinstance(file_info, dict):
            problems.append(f"file entry {index} must be a dictionary")
            continue

        if "path" not in file_info:
            problems.append(f"file entry {index} is missing path")

        if "language" not in file_info:
            problems.append(f"file entry {index} is missing language")

        if "imports" not in file_info:
            problems.append(f"file entry {index} is missing imports")

        if "external_imports" not in file_info:
            problems.append(f"file entry {index} is missing external_imports")

        if "unresolved_imports" not in file_info:
            problems.append(f"file entry {index} is missing unresolved_imports")

        if "unresolved_import_details" not in file_info:
            problems.append(f"file entry {index} is missing unresolved_import_details")

        if "classes" not in file_info:
            problems.append(f"file entry {index} is missing classes")

        if "functions" not in file_info:
            problems.append(f"file entry {index} is missing functions")

    if "edges" not in graph:
        problems.append("graph is missing edges")
        return problems

    if not isinstance(graph["edges"], list):
        problems.append("graph edges must be a list")
        return problems

    file_paths = set()

    for file_info in graph["files"]:
        if isinstance(file_info, dict) and "path" in file_info:
            file_paths.add(file_info["path"])

    for index, edge in enumerate(graph["edges"]):
        if not isinstance(edge, dict):
            problems.append(f"edge entry {index} must be a dictionary")
            continue

        if "from" not in edge:
            problems.append(f"edge entry {index} is missing from")

        if "to" not in edge:
            problems.append(f"edge entry {index} is missing to")

        if "type" not in edge:
            problems.append(f"edge entry {index} is missing type")

        if "import" not in edge:
            problems.append(f"edge entry {index} is missing import")

        if "from" in edge and edge["from"] not in file_paths:
            problems.append(f"edge entry {index} has unknown from path")

        if "to" in edge and edge["to"] not in file_paths:
            problems.append(f"edge entry {index} has unknown to path")

    return problems