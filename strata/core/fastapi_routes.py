"""Deterministic FastAPI route extraction from supplied Python source text."""

import ast

from strata.core.backend_relationships import (
    BACKEND_CONFIDENCE_HIGH,
    BACKEND_FRAMEWORK_FASTAPI,
    BACKEND_RELATIONSHIP_BACKEND_ROUTE,
    HTTP_METHOD_ANY,
    HTTP_METHOD_UNKNOWN,
    BackendRelationship,
    sort_backend_relationships,
)
from strata.core.python_backend_common import (
    build_backend_relationship_from_route_facts,
    build_python_backend_evidence,
    literal_route_path_from_decorator,
    normalize_decorator_name,
    normalize_http_method,
    parse_python_backend_source,
)


_FASTAPI_METHOD_NAMES = (
    "get",
    "post",
    "put",
    "patch",
    "delete",
    "options",
    "head",
)
_FASTAPI_METHODS_KEYWORD = "methods"
_FASTAPI_REASON = "fastapi_decorator"


def infer_fastapi_routes(source_path: str, source_text: str) -> list[BackendRelationship]:
    """Infer FastAPI backend_route relationships from supplied Python source text."""

    parse_result = parse_python_backend_source(source_text, source_path=source_path)
    if not parse_result.ok or parse_result.tree is None:
        return []

    relationships: list[BackendRelationship] = []
    for node in ast.walk(parse_result.tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            relationships.extend(
                _relationships_from_decorator(
                    source_path=parse_result.source_path,
                    source_text=source_text,
                    node=node,
                    decorator=decorator,
                )
            )

    return list(sort_backend_relationships(relationships))


def _relationships_from_decorator(
    *,
    source_path: str,
    source_text: str,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    decorator: ast.AST,
) -> tuple[BackendRelationship, ...]:
    decorator_name = normalize_decorator_name(decorator)
    route_path = literal_route_path_from_decorator(decorator)
    if route_path.route_path is None:
        return ()

    method_names = _http_methods_from_decorator(decorator, decorator_name)
    if not method_names:
        return ()

    evidence = build_python_backend_evidence(
        source_path=source_path,
        node=node,
        decorator=decorator,
        source=source_text,
        decorator_name=decorator_name,
        warnings=route_path.warnings,
    )
    evidence_text = _format_evidence(evidence.line_number, evidence.decorator_name)

    relationships: list[BackendRelationship] = []
    for method in method_names:
        warnings = route_path.warnings
        if method == HTTP_METHOD_UNKNOWN:
            warnings = (
                *warnings,
                "Unsupported FastAPI api_route method ignored by HTTP normalizer.",
            )
        relationships.append(
            build_backend_relationship_from_route_facts(
                source_path=source_path,
                framework=BACKEND_FRAMEWORK_FASTAPI,
                relationship_type=BACKEND_RELATIONSHIP_BACKEND_ROUTE,
                route_path=route_path.route_path,
                http_method=method,
                handler_symbol=node.name,
                target_path=source_path,
                target_symbol=node.name,
                confidence=BACKEND_CONFIDENCE_HIGH,
                evidence=(evidence_text,),
                warnings=warnings,
                reason=_FASTAPI_REASON,
            )
        )
    return tuple(relationships)


def _http_methods_from_decorator(
    decorator: ast.AST,
    decorator_name: str,
) -> tuple[str, ...]:
    method_name = _decorator_method_name(decorator_name)
    if method_name in _FASTAPI_METHOD_NAMES and "." in decorator_name:
        return (normalize_http_method(method_name),)
    if method_name != "api_route" or "." not in decorator_name:
        return ()
    methods = _api_route_methods(decorator)
    if not methods:
        return (HTTP_METHOD_ANY,)
    return methods


def _decorator_method_name(decorator_name: str) -> str:
    if "." not in decorator_name:
        return decorator_name
    return decorator_name.rsplit(".", 1)[1]


def _api_route_methods(decorator: ast.AST) -> tuple[str, ...]:
    if not isinstance(decorator, ast.Call):
        return ()
    for keyword in decorator.keywords:
        if keyword.arg == _FASTAPI_METHODS_KEYWORD:
            return _literal_methods(keyword.value)
    return ()


def _literal_methods(node: ast.AST) -> tuple[str, ...]:
    values: list[str] = []
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        values.append(node.value)
    elif isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        for item in node.elts:
            if isinstance(item, ast.Constant) and isinstance(item.value, str):
                values.append(item.value)

    normalized = tuple(normalize_http_method(value) for value in values)
    return tuple(
        method
        for method in (
            "GET",
            "POST",
            "PUT",
            "PATCH",
            "DELETE",
            "OPTIONS",
            "HEAD",
            HTTP_METHOD_ANY,
            HTTP_METHOD_UNKNOWN,
        )
        if method in normalized
    )


def _format_evidence(line_number: int | None, decorator_name: str | None) -> str:
    line = "unknown" if line_number is None else str(line_number)
    name = decorator_name or "unknown"
    return f"line {line} decorator {name}"
