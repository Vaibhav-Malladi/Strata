import ast


HTTP_METHODS = {
    "get",
    "post",
    "put",
    "patch",
    "delete",
    "options",
    "head",
}


def _string_value(node: ast.AST) -> str | None:
    """
    Return a string value from an AST node if it is a literal string.
    """

    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value

    return None


def _method_list_value(node: ast.AST) -> list[str]:
    """
    Extract HTTP method names from a Flask methods=[...] argument.
    """

    if not isinstance(node, (ast.List, ast.Tuple)):
        return []

    methods = []

    for item in node.elts:
        value = _string_value(item)

        if value is not None:
            methods.append(value.upper())

    return methods


def _route_from_decorator(decorator: ast.AST, line_number: int) -> dict | None:
    """
    Detect backend route decorators from FastAPI, Flask, or APIRouter style.

    Supported examples:
    - @app.get("/health")
    - @router.post("/users")
    - @app.route("/login", methods=["GET", "POST"])
    """

    if not isinstance(decorator, ast.Call):
        return None

    if not isinstance(decorator.func, ast.Attribute):
        return None

    if not isinstance(decorator.func.value, ast.Name):
        return None

    receiver = decorator.func.value.id
    decorator_name = decorator.func.attr

    if decorator_name in HTTP_METHODS:
        if not decorator.args:
            return None

        route_path = _string_value(decorator.args[0])

        if route_path is None:
            return None

        return {
            "method": decorator_name.upper(),
            "path": route_path,
            "line": line_number,
            "source": f"@{receiver}.{decorator_name}",
        }

    if decorator_name == "route":
        if not decorator.args:
            return None

        route_path = _string_value(decorator.args[0])

        if route_path is None:
            return None

        methods = ["GET"]

        for keyword in decorator.keywords:
            if keyword.arg == "methods":
                parsed_methods = _method_list_value(keyword.value)

                if parsed_methods:
                    methods = parsed_methods

        return {
            "method": ",".join(methods),
            "path": route_path,
            "line": line_number,
            "source": f"@{receiver}.route",
        }

    return None


def _detect_routes(tree: ast.AST) -> list[dict]:
    """
    Detect backend route decorators from parsed Python AST.
    """

    routes = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        for decorator in node.decorator_list:
            route = _route_from_decorator(
                decorator,
                getattr(decorator, "lineno", node.lineno),
            )

            if route is not None:
                routes.append(route)

    return routes


def _empty_result(path: str) -> dict:
    return {
        "path": path,
        "language": "python",
        "imports": [],
        "import_details": [],
        "classes": [],
        "functions": [],
        "routes": [],
    }


def parse_file(path: str) -> dict:
    """
    Parse one Python file and return basic structure information.

    This function does not understand the whole repository.
    It only reads one file and extracts:
    - imports
    - import line numbers
    - classes
    - functions
    - backend routes
    - syntax errors
    """

    result = _empty_result(path)

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

    result["routes"] = _detect_routes(tree)

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

        elif isinstance(node, ast.AsyncFunctionDef):
            result["functions"].append(
                {
                    "name": node.name,
                    "line": node.lineno,
                    "end_line": getattr(node, "end_lineno", node.lineno),
                }
            )

    return result