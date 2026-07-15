"""Deterministic Flask route extraction from supplied Python source text."""

import ast
from dataclasses import dataclass

from strata.core.backend_relationships import (
    BACKEND_CONFIDENCE_HIGH,
    BACKEND_FRAMEWORK_FLASK,
    BACKEND_RELATIONSHIP_BACKEND_ROUTE,
    HTTP_METHOD_GET,
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


_FLASK_METHOD_NAMES = (
    "get",
    "post",
    "put",
    "patch",
    "delete",
    "options",
    "head",
)
_FLASK_METHODS_KEYWORD = "methods"
_FLASK_REASON = "flask_decorator"
_METHOD_ORDER = (
    "GET",
    "POST",
    "PUT",
    "PATCH",
    "DELETE",
    "OPTIONS",
    "HEAD",
    HTTP_METHOD_UNKNOWN,
)
_DYNAMIC_METHOD_WARNING = (
    "Dynamic Flask route methods ignored; only literal method names are supported."
)
_UNSUPPORTED_METHOD_WARNING = (
    "Unsupported Flask route method ignored by HTTP normalizer."
)


@dataclass(frozen=True, slots=True)
class _FlaskMethods:
    methods: tuple[str, ...]
    warnings: tuple[str, ...] = ()


def infer_flask_routes(source_path: str, source_text: str) -> list[BackendRelationship]:
    """Infer Flask backend_route relationships from supplied Python source text."""

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

    methods = _http_methods_from_decorator(decorator, decorator_name)
    if not methods.methods:
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
    for method in methods.methods:
        warnings = (*route_path.warnings, *methods.warnings)
        if method == HTTP_METHOD_UNKNOWN and _UNSUPPORTED_METHOD_WARNING not in warnings:
            warnings = (*warnings, _UNSUPPORTED_METHOD_WARNING)
        relationships.append(
            build_backend_relationship_from_route_facts(
                source_path=source_path,
                framework=BACKEND_FRAMEWORK_FLASK,
                relationship_type=BACKEND_RELATIONSHIP_BACKEND_ROUTE,
                route_path=route_path.route_path,
                http_method=method,
                handler_symbol=node.name,
                target_path=source_path,
                target_symbol=node.name,
                confidence=BACKEND_CONFIDENCE_HIGH,
                evidence=(evidence_text,),
                warnings=warnings,
                reason=_FLASK_REASON,
            )
        )
    return tuple(relationships)


def _http_methods_from_decorator(
    decorator: ast.AST,
    decorator_name: str,
) -> _FlaskMethods:
    method_name = _decorator_method_name(decorator_name)
    if "." not in decorator_name:
        return _FlaskMethods(())
    if method_name in _FLASK_METHOD_NAMES:
        return _FlaskMethods((normalize_http_method(method_name),))
    if method_name != "route":
        return _FlaskMethods(())

    explicit = _route_methods(decorator)
    if explicit is None:
        return _FlaskMethods((HTTP_METHOD_GET,))
    return explicit


def _decorator_method_name(decorator_name: str) -> str:
    if "." not in decorator_name:
        return decorator_name
    return decorator_name.rsplit(".", 1)[1]


def _route_methods(decorator: ast.AST) -> _FlaskMethods | None:
    if not isinstance(decorator, ast.Call):
        return None
    for keyword in decorator.keywords:
        if keyword.arg == _FLASK_METHODS_KEYWORD:
            return _literal_methods(keyword.value)
    return None


def _literal_methods(node: ast.AST) -> _FlaskMethods:
    values: list[str] = []
    dynamic_seen = False
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        values.append(node.value)
    elif isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        for item in node.elts:
            if isinstance(item, ast.Constant) and isinstance(item.value, str):
                values.append(item.value)
            else:
                dynamic_seen = True
    else:
        dynamic_seen = True

    normalized = tuple(normalize_http_method(value) for value in values)
    methods = tuple(method for method in _METHOD_ORDER if method in normalized)
    warnings: tuple[str, ...] = ()
    if dynamic_seen:
        warnings = (*warnings, _DYNAMIC_METHOD_WARNING)
    if HTTP_METHOD_UNKNOWN in methods:
        warnings = (*warnings, _UNSUPPORTED_METHOD_WARNING)
    if not methods and dynamic_seen:
        methods = (HTTP_METHOD_UNKNOWN,)
    return _FlaskMethods(methods, warnings)


def _format_evidence(line_number: int | None, decorator_name: str | None) -> str:
    line = "unknown" if line_number is None else str(line_number)
    name = decorator_name or "unknown"
    return f"line {line} decorator {name}"
