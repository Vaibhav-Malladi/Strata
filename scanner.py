import os
import sys

from languages import parse_source_file


IGNORED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".aidc",
}


def module_name_from_path(root_path: str, file_path: str) -> str:
    relative_path = os.path.relpath(file_path, root_path)
    without_extension = os.path.splitext(relative_path)[0]
    parts = without_extension.split(os.sep)
    return ".".join(parts)


def same_folder_module_path(file_path: str, import_name: str) -> str:
    folder = os.path.dirname(file_path)
    return os.path.normpath(os.path.join(folder, import_name + ".py"))


def is_stdlib_import(import_name: str) -> bool:
    top_level_name = import_name.split(".")[0]
    return top_level_name in sys.stdlib_module_names


def find_import_line(file_info: dict, import_name: str) -> int | None:
    for import_detail in file_info.get("import_details", []):
        if import_detail["name"] == import_name:
            return import_detail["line"]

    return None


def scan_repo(root_path: str) -> dict:
    """
    Scan a repository folder and parse all supported source files.
    """

    graph = {
        "schema_version": 1,
        "root": root_path,
        "files": [],
        "edges": [],
    }

    module_index = {}
    path_index = {}

    for current_dir, dir_names, file_names in os.walk(root_path):
        dir_names[:] = [
            name for name in dir_names
            if name not in IGNORED_DIRS
        ]

        for file_name in file_names:
            file_path = os.path.join(current_dir, file_name)
            file_path = os.path.normpath(file_path)

            parsed = parse_source_file(file_path)

            if parsed is not None:
                parsed["path"] = os.path.normpath(parsed["path"])
                parsed["external_imports"] = []
                parsed["unresolved_imports"] = []
                parsed["unresolved_import_details"] = []

                graph["files"].append(parsed)

                module_name = module_name_from_path(root_path, file_path)
                module_index[module_name] = file_path
                path_index[file_path] = file_path

    for file_info in graph["files"]:
        from_path = file_info["path"]

        for import_name in file_info["imports"]:
            target_path = None

            if import_name in module_index:
                target_path = module_index[import_name]
            else:
                same_folder_path = same_folder_module_path(from_path, import_name)

                if same_folder_path in path_index:
                    target_path = same_folder_path

            if target_path is not None:
                graph["edges"].append(
                    {
                        "from": from_path,
                        "to": target_path,
                        "type": "imports",
                        "import": import_name,
                    }
                )
            elif is_stdlib_import(import_name):
                file_info["external_imports"].append(import_name)
            else:
                file_info["unresolved_imports"].append(import_name)
                file_info["unresolved_import_details"].append(
                    {
                        "name": import_name,
                        "line": find_import_line(file_info, import_name),
                    }
                )

    return graph