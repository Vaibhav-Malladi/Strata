import ast


def parse_file(path: str) -> dict:
    """
    Parse one Python file and return basic structure information.

    This function does not understand the whole repository.
    It only reads one file and extracts:
    - imports
    - import line numbers
    - classes
    - functions
    - syntax errors
    """

    result = {
        "path": path,
        "language": "python",
        "imports": [],
        "import_details": [],
        "classes": [],
        "functions": [],
    }

    try:
        with open(path, "r", encoding="utf-8") as file:
            source = file.read()

        tree = ast.parse(source, filename=path)

    except SyntaxError as error:
        result["error"] = {
            "type": "syntax_error",
            "message": str(error),
            "line": error.lineno,
        }
        return result

    except OSError as error:
        result["error"] = {
            "type": "read_error",
            "message": str(error),
        }
        return result

    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                result["imports"].append(alias.name)
                result["import_details"].append(
                    {
                        "name": alias.name,
                        "line": node.lineno,
                    }
                )

        elif isinstance(node, ast.ImportFrom):
            if node.module:
                result["imports"].append(node.module)
                result["import_details"].append(
                    {
                        "name": node.module,
                        "line": node.lineno,
                    }
                )

        elif isinstance(node, ast.ClassDef):
            result["classes"].append(
                {
                    "name": node.name,
                    "line": node.lineno,
                    "end_line": getattr(node, "end_lineno", node.lineno),
                }
            )

        elif isinstance(node, ast.FunctionDef):
            result["functions"].append(
                {
                    "name": node.name,
                    "line": node.lineno,
                    "end_line": getattr(node, "end_lineno", node.lineno),
                }
            )

    return result