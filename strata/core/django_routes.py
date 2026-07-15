"""Deterministic Django/DRF route extraction from supplied Python source text."""

import ast

from strata.core.backend_relationships import (
    BACKEND_CONFIDENCE_HIGH,
    BACKEND_CONFIDENCE_LOW,
    BACKEND_CONFIDENCE_MEDIUM,
    BACKEND_FRAMEWORK_DJANGO,
    BACKEND_FRAMEWORK_DJANGO_REST_FRAMEWORK,
    BACKEND_RELATIONSHIP_BACKEND_ROUTE,
    BACKEND_RELATIONSHIP_ROUTE_HANDLER,
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


_DJANGO_URL_CALLS = {"path", "re_path", "url"}
_DRF_REASON_API_VIEW = "drf_api_view"
_DJANGO_REASON_URLPATTERN = "django_urlpattern"
_DRF_REASON_ROUTER_REGISTER = "drf_router_register"
_DRF_REASON_CLASS_VIEW = "drf_class_view"
_METHOD_ORDER = (
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
_INCLUDE_WARNING = "Django include target is not resolved across files."
_DYNAMIC_METHOD_WARNING = (
    "Dynamic DRF api_view methods ignored; only literal method names are supported."
)


def infer_django_routes(source_path: str, source_text: str) -> list[BackendRelationship]:
    """Infer Django/DRF relationships from supplied Python source text."""

    parse_result = parse_python_backend_source(source_text, source_path=source_path)
    if not parse_result.ok or parse_result.tree is None:
        return []

    relationships: list[BackendRelationship] = []
    for node in ast.walk(parse_result.tree):
        if isinstance(node, ast.Call):
            relationships.extend(
                _relationships_from_call(parse_result.source_path, node)
            )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            relationships.extend(
                _relationships_from_function_decorators(
                    source_path=parse_result.source_path,
                    source_text=source_text,
                    node=node,
                )
            )
        elif isinstance(node, ast.ClassDef):
            relationships.extend(_drf_class_view_relationship(parse_result.source_path, node))

    return list(sort_backend_relationships(relationships))


def _relationships_from_call(
    source_path: str,
    node: ast.Call,
) -> tuple[BackendRelationship, ...]:
    call_name = _call_name(node)
    if call_name in _DJANGO_URL_CALLS:
        return _django_urlpattern_relationship(source_path, node, call_name)
    if call_name.endswith(".register"):
        return _drf_router_register_relationship(source_path, node, call_name)
    return ()


def _django_urlpattern_relationship(
    source_path: str,
    node: ast.Call,
    call_name: str,
) -> tuple[BackendRelationship, ...]:
    route_path = literal_route_path_from_decorator(node)
    if route_path.route_path is None:
        return ()

    view = _argument(node, 1)
    target_symbol = _symbol_name(view)
    warnings = route_path.warnings
    confidence = BACKEND_CONFIDENCE_HIGH
    http_method = HTTP_METHOD_ANY
    if _is_include_call(view):
        target_symbol = _include_target(view) or "include"
        warnings = (*warnings, _INCLUDE_WARNING)
        confidence = BACKEND_CONFIDENCE_LOW

    return (
        build_backend_relationship_from_route_facts(
            source_path=source_path,
            framework=BACKEND_FRAMEWORK_DJANGO,
            relationship_type=BACKEND_RELATIONSHIP_BACKEND_ROUTE,
            route_path=route_path.route_path,
            http_method=http_method,
            handler_symbol=target_symbol,
            target_path=source_path,
            target_symbol=target_symbol,
            confidence=confidence,
            evidence=(_format_evidence(_line_number(node), f"call {call_name}"),),
            warnings=warnings,
            reason=_DJANGO_REASON_URLPATTERN,
        ),
    )


def _relationships_from_function_decorators(
    *,
    source_path: str,
    source_text: str,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> tuple[BackendRelationship, ...]:
    relationships: list[BackendRelationship] = []
    for decorator in node.decorator_list:
        decorator_name = normalize_decorator_name(decorator)
        if decorator_name != "api_view":
            continue
        methods, warnings = _literal_methods_from_first_arg(decorator)
        if not methods:
            methods = (HTTP_METHOD_UNKNOWN,)
        evidence = build_python_backend_evidence(
            source_path=source_path,
            node=node,
            decorator=decorator,
            source=source_text,
            decorator_name=decorator_name,
            warnings=warnings,
        )
        evidence_text = _format_evidence(
            evidence.line_number,
            f"decorator {decorator_name}",
        )
        for method in methods:
            relationships.append(
                build_backend_relationship_from_route_facts(
                    source_path=source_path,
                    framework=BACKEND_FRAMEWORK_DJANGO_REST_FRAMEWORK,
                    relationship_type=BACKEND_RELATIONSHIP_ROUTE_HANDLER,
                    route_path=None,
                    http_method=method,
                    handler_symbol=node.name,
                    target_path=source_path,
                    target_symbol=node.name,
                    confidence=BACKEND_CONFIDENCE_HIGH,
                    evidence=(evidence_text,),
                    warnings=warnings,
                    reason=_DRF_REASON_API_VIEW,
                )
            )
    return tuple(relationships)


def _drf_router_register_relationship(
    source_path: str,
    node: ast.Call,
    call_name: str,
) -> tuple[BackendRelationship, ...]:
    route_path = literal_route_path_from_decorator(node)
    if route_path.route_path is None:
        return ()
    target_symbol = _symbol_name(_argument(node, 1))
    return (
        build_backend_relationship_from_route_facts(
            source_path=source_path,
            framework=BACKEND_FRAMEWORK_DJANGO_REST_FRAMEWORK,
            relationship_type=BACKEND_RELATIONSHIP_BACKEND_ROUTE,
            route_path=route_path.route_path,
            http_method=HTTP_METHOD_ANY,
            handler_symbol=target_symbol,
            target_path=source_path,
            target_symbol=target_symbol,
            confidence=BACKEND_CONFIDENCE_MEDIUM,
            evidence=(_format_evidence(_line_number(node), f"call {call_name}"),),
            warnings=route_path.warnings,
            reason=_DRF_REASON_ROUTER_REGISTER,
        ),
    )


def _drf_class_view_relationship(
    source_path: str,
    node: ast.ClassDef,
) -> tuple[BackendRelationship, ...]:
    base_names = tuple(
        name
        for name in (_dotted_name(base) for base in node.bases)
        if name is not None
    )
    if not any(_is_drf_class_base(name) for name in base_names):
        return ()
    base_label = next(name for name in base_names if _is_drf_class_base(name))
    return (
        build_backend_relationship_from_route_facts(
            source_path=source_path,
            framework=BACKEND_FRAMEWORK_DJANGO_REST_FRAMEWORK,
            relationship_type=BACKEND_RELATIONSHIP_ROUTE_HANDLER,
            route_path=None,
            http_method=HTTP_METHOD_ANY,
            handler_symbol=node.name,
            target_path=source_path,
            target_symbol=node.name,
            confidence=BACKEND_CONFIDENCE_MEDIUM,
            evidence=(_format_evidence(_line_number(node), f"class {base_label}"),),
            reason=_DRF_REASON_CLASS_VIEW,
        ),
    )


def _literal_methods_from_first_arg(
    decorator: ast.AST,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if not isinstance(decorator, ast.Call) or not decorator.args:
        return ((), ())

    node = decorator.args[0]
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
    warnings = (_DYNAMIC_METHOD_WARNING,) if dynamic_seen else ()
    return methods, warnings


def _call_name(node: ast.Call) -> str:
    return _dotted_name(node.func) or ""


def _dotted_name(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value)
        if parent:
            return f"{parent}.{node.attr}"
        return node.attr
    return None


def _argument(node: ast.Call, index: int) -> ast.AST | None:
    if index < len(node.args):
        return node.args[index]
    return None


def _symbol_name(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _symbol_name(node.value)
        if parent:
            return f"{parent}.{node.attr}"
        return node.attr
    if isinstance(node, ast.Call) and _call_name(node) == "include":
        return _include_target(node)
    return None


def _is_include_call(node: ast.AST | None) -> bool:
    return isinstance(node, ast.Call) and _call_name(node) == "include"


def _is_drf_class_base(name: str) -> bool:
    return name in {"APIView", "viewsets.ModelViewSet", "ModelViewSet"} or name.endswith(
        ".APIView"
    )


def _include_target(node: ast.Call) -> str | None:
    first = _argument(node, 0)
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value
    return "include"


def _line_number(node: ast.AST) -> int | None:
    value = getattr(node, "lineno", None)
    return value if isinstance(value, int) and value > 0 else None


def _format_evidence(line_number: int | None, label: str) -> str:
    line = "unknown" if line_number is None else str(line_number)
    return f"line {line} {label}"
