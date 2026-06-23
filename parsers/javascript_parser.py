import os
import re


IMPORT_FROM_PATTERN = re.compile(
    r'^\s*import\s+.+?\s+from\s+[\'"]([^\'"]+)[\'"]'
)

IMPORT_SIDE_EFFECT_PATTERN = re.compile(
    r'^\s*import\s+[\'"]([^\'"]+)[\'"]'
)

REQUIRE_PATTERN = re.compile(
    r'^\s*(?:const|let|var)\s+.+?\s*=\s*require\([\'"]([^\'"]+)[\'"]\)'
)

FUNCTION_PATTERN = re.compile(
    r'^\s*(?:export\s+)?(?:default\s+)?function\s+([A-Za-z_$][\w$]*)\s*\('
)

ARROW_FUNCTION_PATTERN = re.compile(
    r'^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:\([^)]*\)|[A-Za-z_$][\w$]*)(?:\s*:\s*[^=]+)?\s*=>'
)

FUNCTION_EXPRESSION_PATTERN = re.compile(
    r'^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*function\b'
)

CLASS_PATTERN = re.compile(
    r'^\s*(?:export\s+)?(?:default\s+)?class\s+([A-Za-z_$][\w$]*)\b'
)


def _empty_result(path: str) -> dict:
    return {
        "path": os.path.normpath(path),
        "language": "javascript",
        "imports": [],
        "import_details": [],
        "classes": [],
        "functions": [],
        "exports": [],
    }


def _add_import(result: dict, name: str, line_number: int) -> None:
    result["imports"].append(name)
    result["import_details"].append(
        {
            "name": name,
            "line": line_number,
        }
    )


def _add_symbol(items: list[dict], name: str, line_number: int) -> None:
    items.append(
        {
            "name": name,
            "line": line_number,
            "end_line": line_number,
        }
    )


def _detect_export(line: str, result: dict, line_number: int) -> None:
    stripped = line.strip()

    if not stripped.startswith("export"):
        return

    result["exports"].append(
        {
            "line": line_number,
            "text": stripped,
        }
    )


def parse_file(path: str) -> dict:
    """
    Parse one JavaScript file using lightweight standard-library regex rules.

    This is not a full JavaScript AST parser.
    It extracts useful repository-intelligence signals:
    - imports
    - require calls
    - classes
    - functions
    - exported declarations
    """

    result = _empty_result(path)

    try:
        with open(path, "r", encoding="utf-8") as file:
            lines = file.readlines()

    except OSError as error:
        result["error"] = {
            "type": "read_error",
            "message": str(error),
        }
        return result

    for index, line in enumerate(lines, start=1):
        import_match = IMPORT_FROM_PATTERN.match(line)
        side_effect_match = IMPORT_SIDE_EFFECT_PATTERN.match(line)
        require_match = REQUIRE_PATTERN.match(line)

        if import_match:
            _add_import(result, import_match.group(1), index)
        elif side_effect_match:
            _add_import(result, side_effect_match.group(1), index)
        elif require_match:
            _add_import(result, require_match.group(1), index)

        function_match = FUNCTION_PATTERN.match(line)
        arrow_match = ARROW_FUNCTION_PATTERN.match(line)
        expression_match = FUNCTION_EXPRESSION_PATTERN.match(line)
        class_match = CLASS_PATTERN.match(line)

        if function_match:
            _add_symbol(result["functions"], function_match.group(1), index)
        elif arrow_match:
            _add_symbol(result["functions"], arrow_match.group(1), index)
        elif expression_match:
            _add_symbol(result["functions"], expression_match.group(1), index)

        if class_match:
            _add_symbol(result["classes"], class_match.group(1), index)

        _detect_export(line, result, index)

    return result