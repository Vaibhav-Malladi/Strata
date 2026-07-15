"""Deterministic NestJS route extraction from supplied TypeScript source text."""

import re
from dataclasses import dataclass

from strata.core.backend_relationships import (
    BACKEND_CONFIDENCE_HIGH,
    BACKEND_FRAMEWORK_NESTJS,
    BACKEND_RELATIONSHIP_BACKEND_ROUTE,
    BackendRelationship,
    sort_backend_relationships,
)
from strata.core.python_backend_common import normalize_http_method


_METHOD_DECORATORS = {
    "Get": "GET",
    "Post": "POST",
    "Put": "PUT",
    "Patch": "PATCH",
    "Delete": "DELETE",
    "Options": "OPTIONS",
    "Head": "HEAD",
}
_DECORATOR_RE = re.compile(r"^\s*@(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*(?:\((?P<args>.*)\))?\s*$")
_CLASS_RE = re.compile(r"\bclass\s+[A-Za-z_][A-Za-z0-9_]*\b")
_METHOD_RE = re.compile(
    r"^\s*(?:public|private|protected|async|static|\s)*"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\("
)


@dataclass(frozen=True, slots=True)
class _ControllerState:
    prefix: str
    dynamic: bool


@dataclass(frozen=True, slots=True)
class _RouteDecorator:
    name: str
    method: str
    route_path: str
    line_number: int


def infer_nestjs_routes(source_path: str, source_text: str) -> list[BackendRelationship]:
    """Infer NestJS backend_route relationships from supplied TypeScript source."""

    if not isinstance(source_text, str):
        raise TypeError("source_text must be a string")

    relationships: list[BackendRelationship] = []
    pending_controller: _ControllerState | None = None
    controller = _ControllerState(prefix="", dynamic=False)
    pending_routes: list[_RouteDecorator] = []

    for line_number, line in enumerate(source_text.splitlines(), start=1):
        decorator = _DECORATOR_RE.match(line)
        if decorator:
            name = decorator.group("name")
            args = decorator.group("args")
            if name == "Controller":
                pending_controller = _controller_state(args)
                pending_routes = []
            elif name in _METHOD_DECORATORS:
                route = _literal_decorator_path(args)
                if route is not None:
                    pending_routes.append(
                        _RouteDecorator(
                            name=name,
                            method=_METHOD_DECORATORS[name],
                            route_path=route,
                            line_number=line_number,
                        )
                    )
            continue

        if _CLASS_RE.search(line):
            if pending_controller is not None:
                controller = pending_controller
            pending_controller = None
            pending_routes = []
            continue

        method = _METHOD_RE.match(line)
        if method and pending_routes:
            if not controller.dynamic:
                for route in pending_routes:
                    relationships.append(
                        _build_relationship(
                            source_path=source_path,
                            controller_prefix=controller.prefix,
                            route=route,
                            handler_symbol=method.group("name"),
                        )
                    )
            pending_routes = []

    return list(sort_backend_relationships(relationships))


def _build_relationship(
    *,
    source_path: str,
    controller_prefix: str,
    route: _RouteDecorator,
    handler_symbol: str,
) -> BackendRelationship:
    return BackendRelationship(
        framework=BACKEND_FRAMEWORK_NESTJS,
        relationship_type=BACKEND_RELATIONSHIP_BACKEND_ROUTE,
        source_path=source_path,
        target_path=source_path,
        target_symbol=handler_symbol,
        route_path=_join_paths(controller_prefix, route.route_path),
        http_method=normalize_http_method(route.method),
        handler_symbol=handler_symbol,
        confidence=BACKEND_CONFIDENCE_HIGH,
        evidence=(f"line {route.line_number} decorator {route.name}",),
        reason="nestjs_controller_route",
    )


def _controller_state(args: str | None) -> _ControllerState:
    route = _literal_decorator_path(args)
    if route is None and args and args.strip():
        return _ControllerState(prefix="", dynamic=True)
    return _ControllerState(prefix=route or "", dynamic=False)


def _literal_decorator_path(args: str | None) -> str | None:
    if args is None:
        return ""
    text = args.strip()
    if not text:
        return ""
    match = re.match(r"""^(['"`])(?P<path>.*)\1\s*$""", text)
    if not match:
        return None
    path = match.group("path")
    if "${" in path:
        return None
    return path


def _join_paths(prefix: str, route_path: str) -> str:
    parts = [
        part.strip("/")
        for part in (prefix, route_path)
        if part is not None and part.strip("/")
    ]
    if not parts:
        return "/"
    return "/" + "/".join(parts)
