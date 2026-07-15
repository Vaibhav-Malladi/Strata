"""Deterministic Express route extraction from supplied JavaScript/TypeScript."""

import re

from strata.core.backend_relationships import (
    BACKEND_CONFIDENCE_HIGH,
    BACKEND_FRAMEWORK_EXPRESS,
    BACKEND_RELATIONSHIP_BACKEND_ROUTE,
    BackendRelationship,
    sort_backend_relationships,
)
from strata.core.python_backend_common import normalize_http_method


_METHOD_NAMES = ("get", "post", "put", "patch", "delete", "options", "head")
_METHOD_PATTERN = "|".join(_METHOD_NAMES)
_STRING = r"(?P<quote>['\"`])(?P<path>(?:(?!\1).)*?)(?P=quote)"
_CALL_RE = re.compile(
    rf"\b(?P<receiver>app|router)\s*\.\s*(?P<method>{_METHOD_PATTERN})"
    rf"\s*\(\s*{_STRING}\s*,\s*(?P<handler>[^)\n;]+)",
    re.DOTALL,
)
_CHAIN_RE = re.compile(
    rf"\b(?P<receiver>app|router)\s*\.\s*route\s*\(\s*{_STRING}\s*\)"
    rf"(?P<chain>(?:\s*\.\s*(?:{_METHOD_PATTERN})\s*\([^)]*\))+)",
    re.DOTALL,
)
_CHAIN_METHOD_RE = re.compile(
    rf"\.\s*(?P<method>{_METHOD_PATTERN})\s*\(\s*(?P<handler>[^)\n;]*)\)",
    re.DOTALL,
)
_IDENTIFIER = r"[A-Za-z_$][A-Za-z0-9_$]*"
_MEMBER_RE = re.compile(rf"^\s*(?P<name>{_IDENTIFIER}(?:\s*\.\s*{_IDENTIFIER})*)")
_FUNCTION_RE = re.compile(rf"^\s*(?:async\s+)?function\s+(?P<name>{_IDENTIFIER})\b")


def infer_express_routes(source_path: str, source_text: str) -> list[BackendRelationship]:
    """Infer Express backend_route relationships from supplied JS/TS source text."""

    if not isinstance(source_text, str):
        raise TypeError("source_text must be a string")

    relationships: list[BackendRelationship] = []
    for match in _CALL_RE.finditer(source_text):
        relationships.extend(_relationship_from_call(source_path, source_text, match))
    for match in _CHAIN_RE.finditer(source_text):
        relationships.extend(_relationships_from_chain(source_path, source_text, match))
    return list(sort_backend_relationships(relationships))


def _relationship_from_call(
    source_path: str,
    source_text: str,
    match: re.Match,
) -> tuple[BackendRelationship, ...]:
    path = match.group("path")
    if _is_dynamic_template(path):
        return ()
    method = match.group("method")
    call_name = f"{match.group('receiver')}.{method}"
    return (
        _build_relationship(
            source_path=source_path,
            route_path=path,
            method=method,
            handler_symbol=_handler_symbol(match.group("handler")),
            evidence=_format_evidence(_line_number(source_text, match.start()), call_name),
            reason="express_route_call",
        ),
    )


def _relationships_from_chain(
    source_path: str,
    source_text: str,
    match: re.Match,
) -> tuple[BackendRelationship, ...]:
    path = match.group("path")
    if _is_dynamic_template(path):
        return ()

    relationships: list[BackendRelationship] = []
    for method_match in _CHAIN_METHOD_RE.finditer(match.group("chain")):
        method = method_match.group("method")
        call_name = f"{match.group('receiver')}.route.{method}"
        relationships.append(
            _build_relationship(
                source_path=source_path,
                route_path=path,
                method=method,
                handler_symbol=_handler_symbol(method_match.group("handler")),
                evidence=_format_evidence(
                    _line_number(source_text, match.start() + method_match.start()),
                    call_name,
                ),
                reason="express_chained_route",
            )
        )
    return tuple(relationships)


def _build_relationship(
    *,
    source_path: str,
    route_path: str,
    method: str,
    handler_symbol: str | None,
    evidence: str,
    reason: str,
) -> BackendRelationship:
    return BackendRelationship(
        framework=BACKEND_FRAMEWORK_EXPRESS,
        relationship_type=BACKEND_RELATIONSHIP_BACKEND_ROUTE,
        source_path=source_path,
        target_path=source_path,
        target_symbol=handler_symbol,
        route_path=route_path,
        http_method=normalize_http_method(method),
        handler_symbol=handler_symbol,
        confidence=BACKEND_CONFIDENCE_HIGH,
        evidence=(evidence,),
        reason=reason,
    )


def _handler_symbol(value: str) -> str | None:
    function_match = _FUNCTION_RE.match(value)
    if function_match:
        return function_match.group("name")
    member_match = _MEMBER_RE.match(value)
    if not member_match:
        return None
    return member_match.group("name").replace(" ", "")


def _is_dynamic_template(path: str) -> bool:
    return "${" in path


def _line_number(source_text: str, index: int) -> int:
    return source_text.count("\n", 0, index) + 1


def _format_evidence(line_number: int, call_name: str) -> str:
    return f"line {line_number} call {call_name}"
