import os
import re

from parsers.javascript_parser import (
    IMPORT_FROM_PATTERN,
    IMPORT_SIDE_EFFECT_PATTERN,
    REQUIRE_PATTERN,
    FUNCTION_PATTERN,
    ARROW_FUNCTION_PATTERN,
    FUNCTION_EXPRESSION_PATTERN,
    CLASS_PATTERN,
    ROUTE_PATTERN,
)


INTERFACE_PATTERN = re.compile(
    r"^\s*(?:export\s+)?interface\s+([A-Za-z_$][\w$]*)\b"
)

TYPE_PATTERN = re.compile(
    r"^\s*(?:export\s+)?type\s+([A-Za-z_$][\w$]*)\b"
)

ENUM_PATTERN = re.compile(
    r"^\s*(?:export\s+)?enum\s+([A-Za-z_$][\w$]*)\b"
)

ANGULAR_HINT_PATTERNS = [
    "@Component",
    "@Injectable",
    "@NgModule",
    "@Directive",
    "@Pipe",
    'from "@angular/core"',
    "from '@angular/core'",
]

REACT_HINT_PATTERNS = [
    'from "react"',
    "from 'react'",
    "React.",
    "useState",
    "useEffect",
]


def _empty_result(path: str) -> dict:
    return {
        "path": os.path.normpath(path),
        "language": "typescript",
        "imports": [],
        "import_details": [],
        "classes": [],
        "functions": [],
        "exports": [],
        "interfaces": [],
        "types": [],
        "enums": [],
        "routes": [],
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

def _detect_route(line: str, result: dict, line_number: int) -> None:
    route_match = ROUTE_PATTERN.match(line)

    if not route_match:
        return

    receiver = route_match.group(1)
    method = route_match.group(2).upper()
    route_path = route_match.group(3)

    result["routes"].append(
        {
            "method": method,
            "path": route_path,
            "line": line_number,
            "source": f"{receiver}.{method.lower()}",
        }
    )

def _detect_framework(source: str) -> str | None:
    for pattern in ANGULAR_HINT_PATTERNS:
        if pattern in source:
            return "angular"

    for pattern in REACT_HINT_PATTERNS:
        if pattern in source:
            return "react"

    return None


def parse_file(path: str) -> dict:
    """
    Parse one TypeScript file using lightweight standard-library regex rules.

    This is not a full TypeScript AST parser.
    It extracts useful repository-intelligence signals:
    - imports
    - require calls
    - classes
    - functions
    - interfaces
    - type aliases
    - enums
    - exported declarations
    - basic React/Angular framework hints
    """

    result = _empty_result(path)

    try:
        with open(path, "r", encoding="utf-8") as file:
            source = file.read()

    except OSError as error:
        result["error"] = {
            "type": "read_error",
            "message": str(error),
        }
        return result

    framework = _detect_framework(source)

    if framework is not None:
        result["framework"] = framework

    lines = source.splitlines()

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
        interface_match = INTERFACE_PATTERN.match(line)
        type_match = TYPE_PATTERN.match(line)
        enum_match = ENUM_PATTERN.match(line)

        if function_match:
            _add_symbol(result["functions"], function_match.group(1), index)
        elif arrow_match:
            _add_symbol(result["functions"], arrow_match.group(1), index)
        elif expression_match:
            _add_symbol(result["functions"], expression_match.group(1), index)

        if class_match:
            _add_symbol(result["classes"], class_match.group(1), index)

        if interface_match:
            _add_symbol(result["interfaces"], interface_match.group(1), index)

        if type_match:
            _add_symbol(result["types"], type_match.group(1), index)

        if enum_match:
            _add_symbol(result["enums"], enum_match.group(1), index)

        _detect_export(line, result, index)
        _detect_route(line, result, index)

    return result