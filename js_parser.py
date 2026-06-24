from __future__ import annotations

import os
import re
from pathlib import Path


JS_TS_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}

REACT_HOOK_NAMES = {
    "useCallback",
    "useContext",
    "useDeferredValue",
    "useEffect",
    "useId",
    "useImperativeHandle",
    "useLayoutEffect",
    "useMemo",
    "useReducer",
    "useRef",
    "useState",
    "useSyncExternalStore",
    "useTransition",
}

BACKEND_ROUTE_METHODS = {
    "get",
    "post",
    "put",
    "patch",
    "delete",
    "options",
    "head",
    "all",
}

ES_IMPORT_PATTERN = re.compile(
    r"(?ms)^\s*import\s+(?P<clause>.+?)\s+from\s+[\"'](?P<source>[^\"']+)[\"']"
)

SIDE_EFFECT_IMPORT_PATTERN = re.compile(
    r"(?m)^\s*import\s+[\"'](?P<source>[^\"']+)[\"']"
)

REQUIRE_ASSIGNMENT_PATTERN = re.compile(
    r"(?m)^\s*(?:const|let|var)\s+(?P<lhs>.+?)\s*=\s*require\(\s*[\"'](?P<source>[^\"']+)[\"']\s*\)"
)

BARE_REQUIRE_PATTERN = re.compile(
    r"(?m)^\s*require\(\s*[\"'](?P<source>[^\"']+)[\"']\s*\)"
)

FUNCTION_DECL_PATTERN = re.compile(
    r"(?m)^(?P<indent>\s*)(?P<export>export\s+)?(?P<default>default\s+)?(?P<async>async\s+)?function\s+(?P<name>[A-Za-z_$][\w$]*)\s*\("
)

ARROW_DECL_PATTERN = re.compile(
    r"(?m)^(?P<indent>\s*)(?P<export>export\s+)?(?P<default>default\s+)?(?:const|let|var)\s+(?P<name>[A-Za-z_$][\w$]*)\s*=\s*(?P<async>async\s+)?(?:\((?P<params>[^)]*)\)|(?P<single>[A-Za-z_$][\w$]*))\s*(?::\s*[^=]+?)?\s*=>"
)

FUNCTION_EXPRESSION_PATTERN = re.compile(
    r"(?m)^(?P<indent>\s*)(?P<export>export\s+)?(?P<default>default\s+)?(?:const|let|var)\s+(?P<name>[A-Za-z_$][\w$]*)\s*=\s*(?P<async>async\s+)?function\b"
)

CLASS_DECL_PATTERN = re.compile(
    r"(?m)^(?P<indent>\s*)(?P<export>export\s+)?(?P<default>default\s+)?class\s+(?P<name>[A-Za-z_$][\w$]*)\b(?P<extends>[^\{]*)"
)

INTERFACE_PATTERN = re.compile(
    r"(?m)^(?P<indent>\s*)(?P<export>export\s+)?interface\s+(?P<name>[A-Za-z_$][\w$]*)\b"
)

TYPE_PATTERN = re.compile(
    r"(?m)^(?P<indent>\s*)(?P<export>export\s+)?type\s+(?P<name>[A-Za-z_$][\w$]*)\b"
)

ENUM_PATTERN = re.compile(
    r"(?m)^(?P<indent>\s*)(?P<export>export\s+)?enum\s+(?P<name>[A-Za-z_$][\w$]*)\b"
)

EXPORT_NAMED_PATTERN = re.compile(
    r"(?ms)^\s*export\s*\{\s*(?P<specs>.+?)\s*\}(?:\s*from\s*[\"'](?P<source>[^\"']+)[\"'])?"
)

EXPORT_STAR_PATTERN = re.compile(
    r"(?m)^\s*export\s*\*\s*from\s*[\"'](?P<source>[^\"']+)[\"']"
)

EXPORT_DEFAULT_IDENTIFIER_PATTERN = re.compile(
    r"(?m)^\s*export\s+default\s+(?P<name>(?!function\b|class\b)[A-Za-z_$][\w$]*)\b"
)

EXPORT_CONST_PATTERN = re.compile(
    r"(?m)^\s*export\s+(?:const|let|var)\s+(?P<name>[A-Za-z_$][\w$]*)\b"
)

MODULE_EXPORTS_PATTERN = re.compile(
    r"(?m)^\s*module\.exports\s*="
)

EXPORTS_ASSIGNMENT_PATTERN = re.compile(
    r"(?m)^\s*exports\.(?P<name>[A-Za-z_$][\w$]*)\s*="
)

BACKEND_ROUTE_PATTERN = re.compile(
    r"(?m)^\s*(?P<receiver>[A-Za-z_$][\w$]*)\s*\.\s*(?P<method>get|post|put|patch|delete|options|head|all)\s*\(\s*[\"'](?P<path>[^\"']+)[\"']"
)

ANGULAR_DECORATOR_PATTERN = re.compile(
    r"(?ms)@(?P<decorator>Component|Injectable|NgModule|Directive|Pipe)\s*\(\s*(?P<meta>\{.*?\})\s*\)\s*(?:(?:export\s+)?default\s+)?(?:export\s+)?class\s+(?P<name>[A-Za-z_$][\w$]*)\b"
)

ANGULAR_ROUTE_PATTERN = re.compile(
    r"(?m)\bpath\s*:\s*[\"'](?P<path>[^\"']*)[\"']"
)

JSX_PATTERN = re.compile(r"<[A-Za-z][\w:-]*(?:\s|/|>)")

REACT_HOOK_CALL_PATTERN = re.compile(
    r"\b(?P<name>" + "|".join(sorted(REACT_HOOK_NAMES)) + r")\s*\("
)

CUSTOM_HOOK_DECL_PATTERN = re.compile(
    r"(?m)^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+(?P<name>use[A-Z][A-Za-z0-9_]*)\s*\("
)

CUSTOM_HOOK_ARROW_PATTERN = re.compile(
    r"(?m)^\s*(?:export\s+)?(?:const|let|var)\s+(?P<name>use[A-Z][A-Za-z0-9_]*)\s*=\s*(?:async\s+)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*(?::\s*[^=]+?)?\s*=>"
)

PATH_ALIAS_PREFIXES = ("@/", "~/")


def parse_js_file(path: str | Path) -> dict:
    """Parse a JavaScript or TypeScript file from disk."""

    path_obj = Path(path)
    language = _language_from_path(path_obj)
    result = _empty_result(path_obj, language)

    try:
        source = path_obj.read_text(encoding="utf-8")
    except OSError as error:
        _add_error(result, "read_error", str(error))
        return result

    return parse_js_source(source, path=str(path_obj))


def parse_js_source(source: str, path: str | None = None) -> dict:
    """Parse JavaScript or TypeScript source from a string."""

    language = _language_from_path(path) if path else "javascript"
    result = _empty_result(path or "", language)

    try:
        clean_source = _strip_comments(source)
        file_extension = _file_extension(path or "")
        jsx_present = bool(JSX_PATTERN.search(clean_source))

        _parse_imports(clean_source, result)
        _parse_require_calls(clean_source, result)
        _parse_exports(clean_source, result)
        declarations = _parse_declarations(clean_source, result)
        _parse_route_calls(clean_source, result)
        _parse_angular_entities(clean_source, result)
        _parse_react_usage(clean_source, declarations, result, file_extension, jsx_present)
        _finalize_result(result)

    except Exception as error:  # pragma: no cover - defensive fallback
        _add_error(result, "parse_error", str(error))
        _finalize_result(result)

    return result


parse_file = parse_js_file


def _empty_result(path: str | Path, language: str) -> dict:
    normalized_path = _normalize_path(path)

    return {
        "path": normalized_path,
        "language": language,
        "framework": "",
        "frameworks": [],
        "imports": [],
        "import_details": [],
        "classes": [],
        "functions": [],
        "components": [],
        "hooks": [],
        "angular": {
            "components": [],
            "services": [],
            "modules": [],
            "directives": [],
            "pipes": [],
            "routes": [],
        },
        "routes": [],
        "exports": [],
        "symbols": [],
        "interfaces": [],
        "types": [],
        "enums": [],
        "errors": [],
    }


def _add_error(result: dict, error_type: str, message: str, line: int | None = None) -> None:
    error = {
        "type": error_type,
        "message": message,
    }

    if line is not None:
        error["line"] = line

    result["errors"].append(error)
    result["error"] = error


def _finalize_result(result: dict) -> None:
    result["imports"] = _dedupe_preserve_order([str(item) for item in result["imports"]])
    result["import_details"] = _sort_dicts_by_line(_dedupe_dicts(
        result["import_details"],
        ("name", "line", "kind", "source"),
    ))
    result["classes"] = _sort_dicts_by_line(_dedupe_dicts(
        result["classes"],
        ("name", "line", "kind", "exported", "default"),
    ))
    result["functions"] = _sort_dicts_by_line(_dedupe_dicts(
        result["functions"],
        ("name", "line", "kind", "exported", "default"),
    ))
    result["components"] = _sort_dicts_by_line(_dedupe_dicts(
        result["components"],
        ("name", "line", "kind", "confidence", "default", "exported"),
    ))
    result["hooks"] = _sort_dicts_by_line(_dedupe_dicts(
        result["hooks"],
        ("name", "line", "kind"),
    ))
    result["exports"] = _sort_dicts_by_line(_dedupe_dicts(
        result["exports"],
        ("name", "line", "kind", "source", "default"),
    ))
    result["symbols"] = _sort_dicts_by_line(_dedupe_dicts(
        result["symbols"],
        ("name", "line", "kind", "framework"),
    ))
    result["routes"] = _sort_dicts_by_line(_dedupe_dicts(
        result["routes"],
        ("method", "path", "line", "source"),
    ))
    result["interfaces"] = _sort_dicts_by_line(_dedupe_dicts(result["interfaces"], ("name", "line", "kind")))
    result["types"] = _sort_dicts_by_line(_dedupe_dicts(result["types"], ("name", "line", "kind")))
    result["enums"] = _sort_dicts_by_line(_dedupe_dicts(result["enums"], ("name", "line", "kind")))

    angular = result["angular"]
    for key in ("components", "services", "modules", "directives", "pipes", "routes"):
        angular[key] = _sort_dicts_by_line(_dedupe_dicts(angular[key], ("name", "line", "decorator", "path", "component")))

    frameworks = []
    for value in result["frameworks"]:
        text = str(value).strip().lower()
        if text and text not in frameworks:
            frameworks.append(text)

    result["frameworks"] = frameworks
    result["framework"] = frameworks[0] if frameworks else ""


def _parse_imports(clean_source: str, result: dict) -> None:
    consumed_spans: list[tuple[int, int]] = []

    for match in ES_IMPORT_PATTERN.finditer(clean_source):
        start, end = match.span()
        consumed_spans.append((start, end))

        clause = match.group("clause").strip()
        source = match.group("source").strip()
        line = _line_number(clean_source, start)
        type_only = clause.startswith("type ")

        imported_names: list[str] = []
        local_names: list[str] = []
        default_name = ""
        namespace_name = ""

        if type_only:
            clause = clause[5:].strip()

        parts = _split_top_level_commas(clause)

        for index, part in enumerate(parts):
            stripped = part.strip()

            if not stripped:
                continue

            if stripped.startswith("* as "):
                namespace_name = stripped[5:].strip()
                local_names.append(namespace_name)
                continue

            if stripped.startswith("{") and stripped.endswith("}"):
                for imported_name, local_name in _parse_named_imports(stripped[1:-1]):
                    imported_names.append(imported_name)
                    local_names.append(local_name)
                continue

            if index == 0 and not default_name:
                default_name = stripped
                local_names.append(default_name)
                imported_names.append("default")
                continue

            if stripped.startswith("type "):
                stripped = stripped[5:].strip()

            if stripped:
                imported_names.append(stripped)
                local_names.append(stripped)

        kind = "type_import" if type_only else "es_import"

        _record_import(
            result,
            source=source,
            line=line,
            kind=kind,
            imported_names=imported_names,
            local_names=local_names,
            default_name=default_name or None,
            namespace_name=namespace_name or None,
        )

    for match in SIDE_EFFECT_IMPORT_PATTERN.finditer(clean_source):
        start = match.start()
        line = _line_number(clean_source, start)
        source = match.group("source").strip()

        if _span_overlaps_any(start, match.end(), consumed_spans):
            continue

        _record_import(
            result,
            source=source,
            line=line,
            kind="side_effect",
            imported_names=[],
            local_names=[],
        )


def _parse_require_calls(clean_source: str, result: dict) -> None:
    for match in REQUIRE_ASSIGNMENT_PATTERN.finditer(clean_source):
        source = match.group("source").strip()
        lhs = match.group("lhs").strip()
        line = _line_number(clean_source, match.start())
        imported_names: list[str] = []
        local_names: list[str] = []

        if lhs.startswith("{") and lhs.endswith("}"):
            for imported_name, local_name in _parse_named_imports(lhs[1:-1]):
                imported_names.append(imported_name)
                local_names.append(local_name)
        else:
            local_name = _first_identifier(lhs)
            if local_name:
                local_names.append(local_name)

        _record_import(
            result,
            source=source,
            line=line,
            kind="require",
            imported_names=imported_names,
            local_names=local_names,
        )

    for match in BARE_REQUIRE_PATTERN.finditer(clean_source):
        source = match.group("source").strip()
        line = _line_number(clean_source, match.start())

        _record_import(
            result,
            source=source,
            line=line,
            kind="require",
            imported_names=[],
            local_names=[],
        )


def _parse_exports(clean_source: str, result: dict) -> None:
    for match in EXPORT_NAMED_PATTERN.finditer(clean_source):
        specs = match.group("specs").strip()
        source = match.group("source")
        line = _line_number(clean_source, match.start())

        for exported_name, original_name in _parse_export_specifiers(specs):
            result["exports"].append(
                {
                    "name": exported_name,
                    "local_name": original_name,
                    "kind": "reexport" if source else "named_export",
                    "source": source or "",
                    "line": line,
                    "default": False,
                }
            )

    for match in EXPORT_STAR_PATTERN.finditer(clean_source):
        result["exports"].append(
            {
                "name": "*",
                "kind": "reexport_all",
                "source": match.group("source").strip(),
                "line": _line_number(clean_source, match.start()),
                "default": False,
            }
        )

    for match in EXPORT_DEFAULT_IDENTIFIER_PATTERN.finditer(clean_source):
        result["exports"].append(
            {
                "name": match.group("name"),
                "kind": "default",
                "source": "",
                "line": _line_number(clean_source, match.start()),
                "default": True,
            }
        )

    for match in EXPORT_CONST_PATTERN.finditer(clean_source):
        result["exports"].append(
            {
                "name": match.group("name"),
                "kind": "const",
                "source": "",
                "line": _line_number(clean_source, match.start()),
                "default": False,
            }
        )

    for match in MODULE_EXPORTS_PATTERN.finditer(clean_source):
        result["exports"].append(
            {
                "name": "module.exports",
                "kind": "module_exports",
                "source": "",
                "line": _line_number(clean_source, match.start()),
                "default": False,
            }
        )

    for match in EXPORTS_ASSIGNMENT_PATTERN.finditer(clean_source):
        result["exports"].append(
            {
                "name": match.group("name"),
                "kind": "exports_assignment",
                "source": "",
                "line": _line_number(clean_source, match.start()),
                "default": False,
            }
        )


def _parse_declarations(clean_source: str, result: dict) -> list[dict]:
    declarations: list[dict] = []

    for match in FUNCTION_DECL_PATTERN.finditer(clean_source):
        declarations.append(
            _record_function_like(
                result,
                clean_source,
                match,
                name=match.group("name"),
                kind="function",
                is_class=False,
                async_flag=bool(match.group("async")),
                exported=bool(match.group("export")),
                default=bool(match.group("default")),
                start_index=match.start(),
            )
        )

    for match in FUNCTION_EXPRESSION_PATTERN.finditer(clean_source):
        declarations.append(
            _record_function_like(
                result,
                clean_source,
                match,
                name=match.group("name"),
                kind="function_expression",
                is_class=False,
                async_flag=bool(match.group("async")),
                exported=bool(match.group("export")),
                default=bool(match.group("default")),
                start_index=match.start(),
            )
        )

    for match in ARROW_DECL_PATTERN.finditer(clean_source):
        declarations.append(
            _record_function_like(
                result,
                clean_source,
                match,
                name=match.group("name"),
                kind="arrow",
                is_class=False,
                async_flag=bool(match.group("async")),
                exported=bool(match.group("export")),
                default=bool(match.group("default")),
                start_index=match.start(),
                concise_body=_arrow_body_snippet(clean_source, match.end()),
            )
        )

    for match in CLASS_DECL_PATTERN.finditer(clean_source):
        class_name = match.group("name")
        extends_clause = (match.group("extends") or "").strip()
        line = _line_number(clean_source, match.start())
        block = _extract_block_after(clean_source, match.end())
        end_line = block["end_line"] if block else line
        class_item = {
            "name": class_name,
            "line": line,
            "end_line": end_line,
            "kind": "class",
            "exported": bool(match.group("export")),
            "default": bool(match.group("default")),
        }

        if extends_clause:
            class_item["extends"] = extends_clause.strip()

        result["classes"].append(class_item)
        result["symbols"].append(
            {
                "name": class_name,
                "line": line,
                "kind": "class",
                "exported": bool(match.group("export")),
                "default": bool(match.group("default")),
                "framework": "",
            }
        )
        declarations.append(class_item)

        if _is_react_class_component(class_name, extends_clause):
            _record_component(
                result,
                name=class_name,
                line=line,
                kind="class",
                exported=bool(match.group("export")),
                default=bool(match.group("default")),
                confidence="high",
            )
            _add_framework(result, "react")

        if bool(match.group("export")) or bool(match.group("default")):
            result["exports"].append(
                {
                    "name": class_name,
                    "kind": "class",
                    "source": "",
                    "line": line,
                    "default": bool(match.group("default")),
                }
            )

    for match in INTERFACE_PATTERN.finditer(clean_source):
        item = {
            "name": match.group("name"),
            "line": _line_number(clean_source, match.start()),
            "end_line": _line_number(clean_source, match.start()),
            "kind": "interface",
            "exported": bool(match.group("export")),
        }
        result["interfaces"].append(item)
        result["symbols"].append(
            {
                "name": item["name"],
                "line": item["line"],
                "kind": "interface",
                "framework": "",
            }
        )

    for match in TYPE_PATTERN.finditer(clean_source):
        item = {
            "name": match.group("name"),
            "line": _line_number(clean_source, match.start()),
            "end_line": _line_number(clean_source, match.start()),
            "kind": "type",
            "exported": bool(match.group("export")),
        }
        result["types"].append(item)
        result["symbols"].append(
            {
                "name": item["name"],
                "line": item["line"],
                "kind": "type",
                "framework": "",
            }
        )

    for match in ENUM_PATTERN.finditer(clean_source):
        item = {
            "name": match.group("name"),
            "line": _line_number(clean_source, match.start()),
            "end_line": _line_number(clean_source, match.start()),
            "kind": "enum",
            "exported": bool(match.group("export")),
        }
        result["enums"].append(item)
        result["symbols"].append(
            {
                "name": item["name"],
                "line": item["line"],
                "kind": "enum",
                "framework": "",
            }
        )

    for function in list(result["functions"]):
        if _is_custom_hook_name(function["name"]):
            _record_hook(
                result,
                name=function["name"],
                line=function["line"],
                kind="custom",
            )

    for arrow in [item for item in declarations if item.get("kind") == "arrow"]:
        if _is_custom_hook_name(arrow["name"]):
            _record_hook(
                result,
                name=arrow["name"],
                line=arrow["line"],
                kind="custom",
            )

    return declarations


def _parse_route_calls(clean_source: str, result: dict) -> None:
    for match in BACKEND_ROUTE_PATTERN.finditer(clean_source):
        method = match.group("method").upper()
        route_path = match.group("path").strip()
        receiver = match.group("receiver")
        line = _line_number(clean_source, match.start())

        result["routes"].append(
            {
                "method": method,
                "path": route_path,
                "line": line,
                "source": f"{receiver}.{method.lower()}",
            }
        )


def _parse_angular_entities(clean_source: str, result: dict) -> None:
    angular_seen = False

    for match in ANGULAR_DECORATOR_PATTERN.finditer(clean_source):
        angular_seen = True
        decorator = match.group("decorator")
        metadata = match.group("meta")
        name = match.group("name")
        line = _line_number(clean_source, match.start())
        details = _parse_angular_metadata(metadata)
        item = {
            "name": name,
            "decorator": decorator,
            "line": line,
            "framework": "angular",
            "confidence": "high",
        }
        item.update(details)

        bucket = _angular_bucket_name(decorator)
        result["angular"][bucket].append(item)
        result["symbols"].append(
            {
                "name": name,
                "line": line,
                "kind": decorator.lower(),
                "framework": "angular",
            }
        )

    for match in ANGULAR_ROUTE_PATTERN.finditer(clean_source):
        angular_seen = True
        line = _line_number(clean_source, match.start())
        window = clean_source[match.start() : match.start() + 300]
        component_match = re.search(r"\bcomponent\s*:\s*([A-Za-z_$][\w$]*)", window)
        redirect_match = re.search(r"\bredirectTo\s*:\s*[\"']([^\"']+)[\"']", window)
        route = {
            "name": match.group("path"),
            "path": match.group("path"),
            "line": line,
            "component": "",
        }

        if component_match:
            route["component"] = component_match.group(1)

        if redirect_match:
            route["redirectTo"] = redirect_match.group(1)

        result["angular"]["routes"].append(route)

    if angular_seen:
        _add_framework(result, "angular")


def _parse_react_usage(
    clean_source: str,
    declarations: list[dict],
    result: dict,
    file_extension: str,
    jsx_present: bool,
) -> None:
    react_seen = file_extension in {".jsx", ".tsx"}

    for import_detail in list(result["import_details"]):
        source = str(import_detail.get("source", import_detail.get("name", "")))
        imported_names = [str(name) for name in import_detail.get("imported_names", [])]
        local_names = [str(name) for name in import_detail.get("local_names", [])]

        if source == "react":
            react_seen = True
            for name in imported_names + local_names:
                if name in REACT_HOOK_NAMES:
                    _record_hook(
                        result,
                        name=name,
                        line=int(import_detail.get("line", 0) or 0),
                        kind="imported",
                    )

    for match in REACT_HOOK_CALL_PATTERN.finditer(clean_source):
        react_seen = True
        _record_hook(
            result,
            name=match.group("name"),
            line=_line_number(clean_source, match.start()),
            kind="call",
        )

    for declaration in declarations:
        name = declaration.get("name", "")
        kind = declaration.get("kind", "")
        line = int(declaration.get("line", 0) or 0)
        exported = bool(declaration.get("exported"))
        default = bool(declaration.get("default"))
        body = declaration.get("body", "")
        concise_body = declaration.get("concise_body", "")

        if file_extension in {".jsx", ".tsx"}:
            react_seen = True

        if _looks_like_react_component(
            name=name,
            kind=kind,
            body=body,
            concise_body=concise_body,
            file_extension=file_extension,
            jsx_present=jsx_present,
        ):
            react_seen = True
            _record_component(
                result,
                name=name,
                line=line,
                kind="class" if kind == "class" else ("arrow" if kind == "arrow" else "function"),
                exported=exported,
                default=default,
                confidence=_component_confidence(body, concise_body, file_extension, jsx_present),
            )

    if react_seen or jsx_present:
        _add_framework(result, "react")


def _record_import(
    result: dict,
    *,
    source: str,
    line: int,
    kind: str,
    imported_names: list[str],
    local_names: list[str],
    default_name: str | None = None,
    namespace_name: str | None = None,
) -> None:
    result["imports"].append(source)
    import_detail = {
        "name": source,
        "source": source,
        "line": line,
        "kind": kind,
        "imported_names": _dedupe_preserve_order(imported_names),
        "local_names": _dedupe_preserve_order(local_names),
    }

    if default_name:
        import_detail["default_name"] = default_name

    if namespace_name:
        import_detail["namespace"] = namespace_name

    result["import_details"].append(import_detail)

    if source == "react":
        _add_framework(result, "react")

    if source.startswith("@angular/"):
        _add_framework(result, "angular")


def _record_component(
    result: dict,
    *,
    name: str,
    line: int,
    kind: str,
    exported: bool,
    default: bool,
    confidence: str,
) -> None:
    component = {
        "name": name,
        "line": line,
        "kind": kind,
        "exported": exported,
        "default": default,
        "confidence": confidence,
        "framework": "react",
    }
    result["components"].append(component)
    result["symbols"].append(
        {
            "name": name,
            "line": line,
            "kind": "component",
            "framework": "react",
        }
    )


def _record_hook(result: dict, *, name: str, line: int, kind: str) -> None:
    hook = {
        "name": name,
        "line": line,
        "kind": kind,
    }
    result["hooks"].append(hook)
    result["symbols"].append(
        {
            "name": name,
            "line": line,
            "kind": "hook",
            "framework": "react",
        }
    )


def _record_function_like(
    result: dict,
    clean_source: str,
    match: re.Match,
    *,
    name: str,
    kind: str,
    is_class: bool,
    async_flag: bool,
    exported: bool,
    default: bool,
    start_index: int,
    concise_body: str = "",
) -> dict:
    line = _line_number(clean_source, start_index)
    body = ""
    end_line = line
    block = _extract_block_after(clean_source, match.end())

    if block:
        body = block["body"]
        end_line = block["end_line"]
    elif concise_body:
        body = concise_body

    item = {
        "name": name,
        "line": line,
        "end_line": end_line,
        "kind": kind,
        "async": async_flag,
        "exported": exported,
        "default": default,
    }

    if is_class:
        result["classes"].append(item)
        result["symbols"].append(
            {
                "name": name,
                "line": line,
                "kind": "class",
                "framework": "",
            }
        )
    else:
        result["functions"].append(item)
        result["symbols"].append(
            {
                "name": name,
                "line": line,
                "kind": "function",
                "framework": "",
            }
        )

    item["body"] = body
    item["concise_body"] = concise_body

    if is_class:
        return item

    if kind == "function" and (exported or default):
        result["exports"].append(
            {
                "name": name,
                "kind": "function",
                "source": "",
                "line": line,
                "default": default,
            }
        )

    return item


def _parse_angular_metadata(metadata: str) -> dict:
    details: dict = {}

    selector = _extract_quoted_value(metadata, "selector")
    template_url = _extract_quoted_value(metadata, "templateUrl")
    provided_in = _extract_quoted_value(metadata, "providedIn")
    standalone = _extract_boolean_value(metadata, "standalone")
    style_urls = _extract_string_list(metadata, "styleUrls")

    if selector is not None:
        details["selector"] = selector

    if template_url is not None:
        details["templateUrl"] = template_url

    if provided_in is not None:
        details["providedIn"] = provided_in

    if standalone is not None:
        details["standalone"] = standalone

    if style_urls is not None:
        details["styleUrls"] = style_urls

    return details


def _split_top_level_commas(text: str) -> list[str]:
    parts = []
    current = []
    depth = 0
    string_delimiter = ""
    escape = False

    for char in text:
        if string_delimiter:
            current.append(char)

            if escape:
                escape = False
                continue

            if char == "\\":
                escape = True
                continue

            if char == string_delimiter:
                string_delimiter = ""

            continue

        if char in {'"', "'", "`"}:
            string_delimiter = char
            current.append(char)
            continue

        if char in "({[":
            depth += 1
            current.append(char)
            continue

        if char in ")}]":
            depth = max(0, depth - 1)
            current.append(char)
            continue

        if char == "," and depth == 0:
            part = "".join(current).strip()
            if part:
                parts.append(part)
            current = []
            continue

        current.append(char)

    final_part = "".join(current).strip()
    if final_part:
        parts.append(final_part)

    return parts


def _parse_named_imports(text: str) -> list[tuple[str, str]]:
    results = []

    for part in _split_top_level_commas(text):
        spec = part.strip()

        if not spec:
            continue

        if spec.startswith("type "):
            spec = spec[5:].strip()

        if " as " in spec:
            imported_name, local_name = [piece.strip() for piece in spec.split(" as ", 1)]
        else:
            imported_name = spec
            local_name = spec

        if imported_name:
            results.append((imported_name, local_name))

    return results


def _parse_export_specifiers(text: str) -> list[tuple[str, str]]:
    results = []

    for part in _split_top_level_commas(text):
        spec = part.strip()

        if not spec:
            continue

        if " as " in spec:
            original_name, exported_name = [piece.strip() for piece in spec.split(" as ", 1)]
        else:
            original_name = spec
            exported_name = spec

        if original_name:
            results.append((exported_name, original_name))

    return results


def _extract_quoted_value(text: str, key: str) -> str | None:
    pattern = re.compile(rf"\b{re.escape(key)}\s*:\s*[\"']([^\"']+)[\"']")
    match = pattern.search(text)
    if match:
        return match.group(1)
    return None


def _extract_boolean_value(text: str, key: str) -> bool | None:
    pattern = re.compile(rf"\b{re.escape(key)}\s*:\s*(true|false)\b")
    match = pattern.search(text)
    if match:
        return match.group(1) == "true"
    return None


def _extract_string_list(text: str, key: str) -> list[str] | None:
    pattern = re.compile(rf"\b{re.escape(key)}\s*:\s*\[(?P<body>.*?)\]", re.S)
    match = pattern.search(text)
    if not match:
        return None

    body = match.group("body")
    values = []
    for value_match in re.finditer(r"[\"']([^\"']+)[\"']", body):
        values.append(value_match.group(1))

    return values


def _extract_block_after(source: str, start_index: int) -> dict | None:
    open_index = source.find("{", start_index)
    if open_index == -1:
        return None

    close_index = _find_matching_brace(source, open_index)
    if close_index is None:
        return None

    body = source[open_index + 1 : close_index]
    return {
        "body": body,
        "start_index": open_index,
        "end_index": close_index,
        "end_line": _line_number(source, close_index),
    }


def _find_matching_brace(source: str, open_index: int) -> int | None:
    depth = 0
    string_delimiter = ""
    escape = False

    for index in range(open_index, len(source)):
        char = source[index]

        if string_delimiter:
            if escape:
                escape = False
                continue

            if char == "\\":
                escape = True
                continue

            if char == string_delimiter:
                string_delimiter = ""

            continue

        if char in {'"', "'", "`"}:
            string_delimiter = char
            continue

        if char == "{":
            depth += 1
            continue

        if char == "}":
            depth -= 1
            if depth == 0:
                return index

    return None


def _arrow_body_snippet(source: str, after_index: int) -> str:
    remainder = source[after_index:].lstrip()
    if not remainder:
        return ""

    first_line = remainder.splitlines()[0] if remainder else ""
    return first_line.strip()


def _is_react_class_component(name: str, extends_clause: str) -> bool:
    if not name or not name[0].isupper():
        return False

    normalized_extends = extends_clause.replace(" ", "")
    if "React.Component" in normalized_extends or "React.PureComponent" in normalized_extends:
        return True

    if re.search(r"(?<!\w)Component\b", extends_clause):
        return True

    return False


def _looks_like_react_component(
    *,
    name: str,
    kind: str,
    body: str,
    concise_body: str,
    file_extension: str,
    jsx_present: bool,
) -> bool:
    if not name or not name[0].isupper():
        return False

    body_text = f"{body}\n{concise_body}".strip()

    if kind == "class":
        return _is_react_class_component(name, body_text)

    if _contains_jsx(body_text):
        return True

    if file_extension in {".jsx", ".tsx"}:
        return True

    if jsx_present:
        return True

    return False


def _contains_jsx(text: str) -> bool:
    return bool(JSX_PATTERN.search(text))


def _component_confidence(
    body: str,
    concise_body: str,
    file_extension: str,
    jsx_present: bool,
) -> str:
    body_text = f"{body}\n{concise_body}".strip()

    if _contains_jsx(body_text):
        return "high"

    if file_extension in {".jsx", ".tsx"}:
        return "high" if jsx_present else "medium"

    if jsx_present:
        return "medium"

    return "low"


def _is_custom_hook_name(name: str) -> bool:
    return bool(name) and name.startswith("use") and len(name) > 3 and name[3].isupper()


def _angular_bucket_name(decorator: str) -> str:
    mapping = {
        "Component": "components",
        "Injectable": "services",
        "NgModule": "modules",
        "Directive": "directives",
        "Pipe": "pipes",
    }
    return mapping.get(decorator, "components")


def _add_framework(result: dict, framework: str) -> None:
    if framework not in result["frameworks"]:
        result["frameworks"].append(framework)


def _parse_angular_routes_from_metadata(metadata: str, line: int) -> list[dict]:
    routes = []
    for match in ANGULAR_ROUTE_PATTERN.finditer(metadata):
        routes.append(
            {
                "name": match.group("path"),
                "path": match.group("path"),
                "line": line,
                "component": "",
            }
        )
    return routes


def _record_angular_routes(result: dict, metadata: str, line: int) -> None:
    for route in _parse_angular_routes_from_metadata(metadata, line):
        result["angular"]["routes"].append(route)


def _language_from_path(path: str | Path | None) -> str:
    ext = _file_extension(path or "")
    if ext in {".ts", ".tsx"}:
        return "typescript"
    return "javascript"


def _file_extension(path: str | Path | None) -> str:
    if not path:
        return ""
    return Path(str(path)).suffix.lower()


def _normalize_path(path: str | Path) -> str:
    if path is None or path == "":
        return ""
    return os.path.normpath(str(path))


def _line_number(source: str, index: int) -> int:
    return source.count("\n", 0, index) + 1


def _strip_comments(source: str) -> str:
    result = []
    index = 0
    length = len(source)
    state = "code"
    string_delimiter = ""

    while index < length:
        char = source[index]
        next_char = source[index + 1] if index + 1 < length else ""

        if state == "code":
            if char == "/" and next_char == "/":
                state = "line_comment"
                index += 2
                continue

            if char == "/" and next_char == "*":
                state = "block_comment"
                index += 2
                continue

            if char in {'"', "'", "`"}:
                state = "string"
                string_delimiter = char
                result.append(char)
                index += 1
                continue

            result.append(char)
            index += 1
            continue

        if state == "string":
            result.append(char)
            if char == "\\":
                if index + 1 < length:
                    result.append(source[index + 1])
                    index += 2
                    continue
            elif char == string_delimiter:
                state = "code"
            index += 1
            continue

        if state == "line_comment":
            if char == "\n":
                result.append(char)
                state = "code"
            index += 1
            continue

        if state == "block_comment":
            if char == "\n":
                result.append(char)
            elif char == "*" and next_char == "/":
                state = "code"
                index += 2
                continue
            index += 1
            continue

    return "".join(result)


def _span_overlaps_any(start: int, end: int, spans: list[tuple[int, int]]) -> bool:
    for span_start, span_end in spans:
        if start < span_end and end > span_start:
            return True
    return False


def _first_identifier(text: str) -> str:
    match = re.search(r"[A-Za-z_$][\w$]*", text)
    return match.group(0) if match else ""


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _dedupe_dicts(items: list[dict], fields: tuple[str, ...]) -> list[dict]:
    seen = set()
    result = []

    for item in items:
        key = tuple(item.get(field) for field in fields)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)

    return result


def _sort_dicts_by_line(items: list[dict]) -> list[dict]:
    return sorted(
        items,
        key=lambda item: (
            int(item.get("line", 0) or 0),
            str(item.get("name", "")),
            str(item.get("kind", "")),
        ),
    )
