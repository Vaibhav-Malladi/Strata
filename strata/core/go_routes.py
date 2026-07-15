"""Deterministic Go HTTP/router route extraction from supplied source text."""

import re

from strata.core.backend_relationships import (
    BACKEND_CONFIDENCE_HIGH,
    BACKEND_CONFIDENCE_MEDIUM,
    BACKEND_FRAMEWORK_GO,
    BACKEND_RELATIONSHIP_BACKEND_ROUTE,
    HTTP_METHOD_ANY,
    BackendRelationship,
    sort_backend_relationships,
)
from strata.core.go_backend_common import (
    extract_go_handler_symbol,
    extract_go_http_methods,
    go_evidence,
    go_string_literal,
    parse_go_backend_source,
)
from strata.core.python_backend_common import normalize_http_method


_HANDLE_RE = re.compile(
    r"\b(?P<receiver>http|mux)\.(?P<call>HandleFunc|Handle)\s*\((?P<args>[^)]*)\)"
)
_MUX_HANDLE_FUNC_RE = re.compile(
    r"\b(?P<receiver>r|router)\.HandleFunc\s*\((?P<args>[^)]*)\)\.Methods\s*\((?P<methods>[^)]*)\)"
)
_MUX_METHODS_FIRST_RE = re.compile(
    r"\b(?P<receiver>r|router)\.Methods\s*\((?P<methods>[^)]*)\)\.Path\s*\((?P<path>[^)]*)\)\.HandlerFunc\s*\((?P<handler>[^)]*)\)"
)
_CHI_RE = re.compile(
    r"\b(?P<receiver>r|router)\.(?P<method>Get|Post|Put|Patch|Delete)\s*\((?P<args>[^)]*)\)"
)
_ARG_SPLIT_RE = re.compile(r",(?![^()]*\))")


def infer_go_routes(source_path: str, source_text: str) -> list[BackendRelationship]:
    """Infer Go backend_route relationships from supplied Go source text."""

    parsed = parse_go_backend_source(source_path, source_text)
    relationships: list[BackendRelationship] = []

    for line in parsed.lines:
        relationships.extend(_standard_handle_relationships(parsed.source_path, line.line_number, line.text))
        relationships.extend(_mux_methods_relationships(parsed.source_path, line.line_number, line.text))
        relationships.extend(_mux_methods_first_relationships(parsed.source_path, line.line_number, line.text))
        relationships.extend(_chi_method_relationships(parsed.source_path, line.line_number, line.text))

    return list(sort_backend_relationships(relationships))


def _standard_handle_relationships(
    source_path: str,
    line_number: int,
    text: str,
) -> tuple[BackendRelationship, ...]:
    relationships: list[BackendRelationship] = []
    for match in _HANDLE_RE.finditer(text):
        args = _split_args(match.group("args"))
        if len(args) < 2:
            continue
        route_path = go_string_literal(args[0])
        if route_path is None:
            continue
        handler = extract_go_handler_symbol(args[1])
        confidence = BACKEND_CONFIDENCE_HIGH if match.group("receiver") == "http" else BACKEND_CONFIDENCE_MEDIUM
        relationships.append(
            _build_relationship(
                source_path=source_path,
                route_path=route_path,
                method=HTTP_METHOD_ANY,
                handler_symbol=handler,
                confidence=confidence,
                evidence=go_evidence(line_number, f"{match.group('receiver')}.{match.group('call')}"),
                reason="go_http_handle",
            )
        )
    return tuple(relationships)


def _mux_methods_relationships(
    source_path: str,
    line_number: int,
    text: str,
) -> tuple[BackendRelationship, ...]:
    relationships: list[BackendRelationship] = []
    for match in _MUX_HANDLE_FUNC_RE.finditer(text):
        args = _split_args(match.group("args"))
        if len(args) < 2:
            continue
        route_path = go_string_literal(args[0])
        if route_path is None:
            continue
        handler = extract_go_handler_symbol(args[1])
        for method in extract_go_http_methods(match.group("methods")):
            relationships.append(
                _build_relationship(
                    source_path=source_path,
                    route_path=route_path,
                    method=method,
                    handler_symbol=handler,
                    confidence=BACKEND_CONFIDENCE_HIGH,
                    evidence=go_evidence(line_number, f"{match.group('receiver')}.HandleFunc.Methods"),
                    reason="go_mux_methods",
                )
            )
    return tuple(relationships)


def _mux_methods_first_relationships(
    source_path: str,
    line_number: int,
    text: str,
) -> tuple[BackendRelationship, ...]:
    relationships: list[BackendRelationship] = []
    for match in _MUX_METHODS_FIRST_RE.finditer(text):
        route_path = go_string_literal(match.group("path"))
        if route_path is None:
            continue
        handler = extract_go_handler_symbol(match.group("handler"))
        for method in extract_go_http_methods(match.group("methods")):
            relationships.append(
                _build_relationship(
                    source_path=source_path,
                    route_path=route_path,
                    method=method,
                    handler_symbol=handler,
                    confidence=BACKEND_CONFIDENCE_HIGH,
                    evidence=go_evidence(line_number, f"{match.group('receiver')}.Methods.Path.HandlerFunc"),
                    reason="go_mux_methods",
                )
            )
    return tuple(relationships)


def _chi_method_relationships(
    source_path: str,
    line_number: int,
    text: str,
) -> tuple[BackendRelationship, ...]:
    relationships: list[BackendRelationship] = []
    for match in _CHI_RE.finditer(text):
        args = _split_args(match.group("args"))
        if len(args) < 2:
            continue
        route_path = go_string_literal(args[0])
        if route_path is None:
            continue
        handler = extract_go_handler_symbol(args[1])
        call_name = f"{match.group('receiver')}.{match.group('method')}"
        relationships.append(
            _build_relationship(
                source_path=source_path,
                route_path=route_path,
                method=match.group("method"),
                handler_symbol=handler,
                confidence=BACKEND_CONFIDENCE_HIGH,
                evidence=go_evidence(line_number, call_name),
                reason="go_chi_method",
            )
        )
    return tuple(relationships)


def _build_relationship(
    *,
    source_path: str,
    route_path: str,
    method: str,
    handler_symbol: str | None,
    confidence: str,
    evidence: str,
    reason: str,
) -> BackendRelationship:
    return BackendRelationship(
        framework=BACKEND_FRAMEWORK_GO,
        relationship_type=BACKEND_RELATIONSHIP_BACKEND_ROUTE,
        source_path=source_path,
        target_path=source_path,
        target_symbol=handler_symbol,
        route_path=route_path,
        http_method=method if method == HTTP_METHOD_ANY else normalize_http_method(method),
        handler_symbol=handler_symbol,
        confidence=confidence,
        evidence=(evidence,),
        reason=reason,
    )


def _split_args(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in _ARG_SPLIT_RE.split(value) if part.strip())
