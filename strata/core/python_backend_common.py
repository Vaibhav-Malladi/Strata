"""Framework-neutral Python backend extraction primitives.

K2 intentionally stops at reusable AST and contract helpers. FastAPI, Flask,
and Django/DRF route extraction belong to later Part K batches.
"""

import ast
from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any

from strata.core.backend_relationships import (
    BACKEND_CONFIDENCE_UNKNOWN,
    BACKEND_FRAMEWORKS,
    BACKEND_FRAMEWORK_UNKNOWN,
    BACKEND_RELATIONSHIP_ROUTE_HANDLER,
    BACKEND_RELATIONSHIP_TYPES,
    HTTP_METHOD_ANY,
    HTTP_METHOD_DELETE,
    HTTP_METHOD_GET,
    HTTP_METHOD_HEAD,
    HTTP_METHOD_OPTIONS,
    HTTP_METHOD_PATCH,
    HTTP_METHOD_POST,
    HTTP_METHOD_PUT,
    HTTP_METHOD_UNKNOWN,
    HTTP_METHODS,
    BackendRelationship,
)


PYTHON_BACKEND_SYMBOL_HANDLER = "handler"
PYTHON_BACKEND_SYMBOL_SERVICE = "service"
PYTHON_BACKEND_SYMBOL_MODEL = "model"
PYTHON_BACKEND_SYMBOL_UNKNOWN = "unknown"
PYTHON_BACKEND_SYMBOL_KINDS = (
    PYTHON_BACKEND_SYMBOL_HANDLER,
    PYTHON_BACKEND_SYMBOL_SERVICE,
    PYTHON_BACKEND_SYMBOL_MODEL,
    PYTHON_BACKEND_SYMBOL_UNKNOWN,
)

_HTTP_METHOD_BY_NAME = {
    "get": HTTP_METHOD_GET,
    "post": HTTP_METHOD_POST,
    "put": HTTP_METHOD_PUT,
    "patch": HTTP_METHOD_PATCH,
    "delete": HTTP_METHOD_DELETE,
    "options": HTTP_METHOD_OPTIONS,
    "head": HTTP_METHOD_HEAD,
}
_ROUTE_PATH_KEYWORDS = ("path", "rule", "route")


@dataclass(frozen=True, slots=True)
class PythonBackendParseResult:
    """Safe result for parsing already-provided Python source text."""

    source_path: str
    ok: bool
    tree: ast.Module | None = None
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_path",
            _normalize_source_path(self.source_path),
        )
        if not isinstance(self.ok, bool):
            raise TypeError("ok must be a bool")
        if self.tree is not None and not isinstance(self.tree, ast.Module):
            raise TypeError("tree must be an ast.Module or None")
        object.__setattr__(
            self,
            "warnings",
            _validate_messages(self.warnings, "warnings"),
        )
        object.__setattr__(
            self,
            "errors",
            _validate_messages(self.errors, "errors"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a stable JSON-ready summary without serializing the AST."""

        body = () if self.tree is None else tuple(self.tree.body)
        return {
            "source_path": self.source_path,
            "ok": self.ok,
            "body_count": len(body),
            "top_level_symbols": [
                node.name
                for node in body
                if isinstance(
                    node,
                    (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
                )
            ],
            "warnings": list(self.warnings),
            "errors": list(self.errors),
        }


@dataclass(frozen=True, slots=True)
class PythonRoutePathLiteral:
    """Literal route path found on a decorator, or a safe unknown result."""

    route_path: str | None
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "route_path",
            _normalize_optional_text(self.route_path, "route_path"),
        )
        object.__setattr__(
            self,
            "warnings",
            _validate_messages(self.warnings, "warnings"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "route_path": self.route_path,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class PythonBackendSymbol:
    """Stable symbol candidate from a Python function or class AST node."""

    name: str
    symbol_type: str
    candidate_kind: str
    line_number: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _validate_nonempty_text(self.name, "name"))
        object.__setattr__(
            self,
            "symbol_type",
            _validate_choice(self.symbol_type, "symbol_type", ("function", "class")),
        )
        object.__setattr__(
            self,
            "candidate_kind",
            _validate_choice(
                self.candidate_kind,
                "candidate_kind",
                PYTHON_BACKEND_SYMBOL_KINDS,
            ),
        )
        object.__setattr__(
            self,
            "line_number",
            _validate_optional_positive_int(self.line_number, "line_number"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "symbol_type": self.symbol_type,
            "candidate_kind": self.candidate_kind,
            "line_number": self.line_number,
        }


@dataclass(frozen=True, slots=True)
class PythonBackendEvidence:
    """Small JSON-ready source evidence entry for later framework extractors."""

    source_path: str
    line_number: int | None = None
    decorator_name: str | None = None
    decorator_text: str | None = None
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_path",
            _normalize_source_path(self.source_path),
        )
        object.__setattr__(
            self,
            "line_number",
            _validate_optional_positive_int(self.line_number, "line_number"),
        )
        object.__setattr__(
            self,
            "decorator_name",
            _normalize_optional_text(self.decorator_name, "decorator_name"),
        )
        object.__setattr__(
            self,
            "decorator_text",
            _normalize_optional_text(self.decorator_text, "decorator_text"),
        )
        object.__setattr__(
            self,
            "warnings",
            _validate_messages(self.warnings, "warnings"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "line_number": self.line_number,
            "decorator_name": self.decorator_name,
            "decorator_text": self.decorator_text,
            "warnings": list(self.warnings),
        }


def parse_python_backend_source(
    source: str,
    *,
    source_path: str = "<memory>",
) -> PythonBackendParseResult:
    """Parse already-provided Python source without reading the filesystem."""

    if not isinstance(source, str):
        raise TypeError("source must be a string")
    try:
        tree = ast.parse(source, filename=source_path)
    except SyntaxError as error:
        location = f"line {error.lineno}" if error.lineno is not None else "unknown line"
        return PythonBackendParseResult(
            source_path=source_path,
            ok=False,
            warnings=("Python source could not be parsed.",),
            errors=(f"SyntaxError: {error.msg} at {location}",),
        )
    return PythonBackendParseResult(source_path=source_path, ok=True, tree=tree)


def normalize_decorator_name(decorator: ast.AST | None) -> str:
    """Return a stable dotted decorator name such as ``app.get`` or ``api_view``."""

    if decorator is None:
        return "unknown"
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    return _dotted_name(target) or "unknown"


def literal_route_path_from_decorator(
    decorator: ast.AST | None,
) -> PythonRoutePathLiteral:
    """Return only string-literal route paths from a decorator call."""

    if not isinstance(decorator, ast.Call):
        return PythonRoutePathLiteral(None)

    for value in decorator.args:
        literal = _string_literal(value)
        if literal is not None:
            return PythonRoutePathLiteral(literal)
        if _looks_like_route_expression(value):
            return PythonRoutePathLiteral(
                None,
                warnings=("Dynamic route path ignored; only string literals are supported.",),
            )

    for keyword in decorator.keywords:
        if keyword.arg not in _ROUTE_PATH_KEYWORDS:
            continue
        literal = _string_literal(keyword.value)
        if literal is not None:
            return PythonRoutePathLiteral(literal)
        return PythonRoutePathLiteral(
            None,
            warnings=("Dynamic route path ignored; only string literals are supported.",),
        )

    return PythonRoutePathLiteral(None)


def normalize_http_method(method: str | None, *, explicit_any: bool = False) -> str:
    """Normalize a method token to the K1 HTTP method vocabulary."""

    if method is None:
        return HTTP_METHOD_UNKNOWN
    if not isinstance(method, str):
        raise TypeError("method must be a string or None")

    text = method.strip()
    if not text:
        return HTTP_METHOD_UNKNOWN
    lowered = text.lower()
    if lowered in _HTTP_METHOD_BY_NAME:
        return _HTTP_METHOD_BY_NAME[lowered]
    if lowered == "route" and explicit_any:
        return HTTP_METHOD_ANY
    if text in HTTP_METHODS:
        return text
    return HTTP_METHOD_UNKNOWN


def python_backend_symbol_from_node(
    node: ast.AST,
    *,
    candidate_kind: str | None = None,
) -> PythonBackendSymbol | None:
    """Return a handler/service/model candidate from a function or class node."""

    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return PythonBackendSymbol(
            name=node.name,
            symbol_type="function",
            candidate_kind=candidate_kind or PYTHON_BACKEND_SYMBOL_HANDLER,
            line_number=getattr(node, "lineno", None),
        )
    if isinstance(node, ast.ClassDef):
        return PythonBackendSymbol(
            name=node.name,
            symbol_type="class",
            candidate_kind=candidate_kind or _class_candidate_kind(node.name),
            line_number=getattr(node, "lineno", None),
        )
    return None


def python_backend_symbols_from_tree(
    tree: ast.Module | None,
) -> tuple[PythonBackendSymbol, ...]:
    """Collect stable top-level Python backend symbol candidates."""

    if tree is None:
        return ()
    if not isinstance(tree, ast.Module):
        raise TypeError("tree must be an ast.Module or None")

    symbols: list[PythonBackendSymbol] = []
    for node in tree.body:
        symbol = python_backend_symbol_from_node(node)
        if symbol is not None:
            symbols.append(symbol)
    return tuple(symbols)


def build_python_backend_evidence(
    *,
    source_path: str,
    node: ast.AST | None = None,
    decorator: ast.AST | None = None,
    source: str | None = None,
    decorator_name: str | None = None,
    decorator_text: str | None = None,
    warnings: tuple[str, ...] = (),
) -> PythonBackendEvidence:
    """Build source evidence from already-available AST/source facts."""

    line_number = _line_number(decorator) or _line_number(node)
    name = decorator_name
    if name is None and decorator is not None:
        name = normalize_decorator_name(decorator)

    text = decorator_text
    if text is None and source is not None and decorator is not None:
        segment = ast.get_source_segment(source, decorator)
        text = segment.strip() if segment else None

    return PythonBackendEvidence(
        source_path=source_path,
        line_number=line_number,
        decorator_name=name,
        decorator_text=text,
        warnings=warnings,
    )


def build_backend_relationship_from_route_facts(
    *,
    source_path: str,
    framework: str = BACKEND_FRAMEWORK_UNKNOWN,
    relationship_type: str = BACKEND_RELATIONSHIP_ROUTE_HANDLER,
    route_path: str | None = None,
    http_method: str = HTTP_METHOD_UNKNOWN,
    handler_symbol: str | None = None,
    target_path: str | None = None,
    target_symbol: str | None = None,
    service_symbol: str | None = None,
    model_symbol: str | None = None,
    confidence: str = BACKEND_CONFIDENCE_UNKNOWN,
    evidence: tuple[str, ...] = (),
    warnings: tuple[str, ...] = (),
    reason: str = "",
) -> BackendRelationship:
    """Create a K1 relationship from explicit route facts supplied by a caller."""

    return BackendRelationship(
        framework=_validate_choice(framework, "framework", BACKEND_FRAMEWORKS),
        relationship_type=_validate_choice(
            relationship_type,
            "relationship_type",
            BACKEND_RELATIONSHIP_TYPES,
        ),
        source_path=source_path,
        target_path=target_path,
        target_symbol=target_symbol,
        route_path=route_path,
        http_method=normalize_http_method(http_method),
        handler_symbol=handler_symbol,
        service_symbol=service_symbol,
        model_symbol=model_symbol,
        confidence=confidence,
        evidence=evidence,
        warnings=warnings,
        reason=reason,
    )


def python_backend_parse_result_to_dict(
    result: PythonBackendParseResult,
) -> dict[str, Any]:
    if not isinstance(result, PythonBackendParseResult):
        raise TypeError("result must be a PythonBackendParseResult")
    return result.to_dict()


def python_backend_symbol_to_dict(symbol: PythonBackendSymbol) -> dict[str, Any]:
    if not isinstance(symbol, PythonBackendSymbol):
        raise TypeError("symbol must be a PythonBackendSymbol")
    return symbol.to_dict()


def python_backend_evidence_to_dict(evidence: PythonBackendEvidence) -> dict[str, Any]:
    if not isinstance(evidence, PythonBackendEvidence):
        raise TypeError("evidence must be a PythonBackendEvidence")
    return evidence.to_dict()


def _dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value)
        if parent:
            return f"{parent}.{node.attr}"
        return node.attr
    if isinstance(node, ast.Subscript):
        return _dotted_name(node.value)
    return None


def _string_literal(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _looks_like_route_expression(node: ast.AST) -> bool:
    return isinstance(
        node,
        (
            ast.BinOp,
            ast.Call,
            ast.FormattedValue,
            ast.JoinedStr,
            ast.Name,
            ast.Subscript,
        ),
    )


def _class_candidate_kind(name: str) -> str:
    lowered = name.lower()
    if lowered.endswith("service"):
        return PYTHON_BACKEND_SYMBOL_SERVICE
    if lowered.endswith("model") or lowered.endswith("schema"):
        return PYTHON_BACKEND_SYMBOL_MODEL
    return PYTHON_BACKEND_SYMBOL_UNKNOWN


def _line_number(node: ast.AST | None) -> int | None:
    if node is None:
        return None
    value = getattr(node, "lineno", None)
    return value if isinstance(value, int) and value > 0 else None


def _normalize_source_path(value: Any) -> str:
    if not isinstance(value, str):
        raise TypeError("source_path must be a string")
    text = value.strip()
    if not text:
        raise ValueError("source_path must be a non-empty string")
    if text.startswith("<") and text.endswith(">"):
        return text
    if text != value or "\x00" in text:
        raise ValueError("source_path must not contain whitespace padding or null bytes")

    windows_path = PureWindowsPath(text)
    posix_text = text.replace("\\", "/")
    posix_path = PurePosixPath(posix_text)
    if posix_path.is_absolute() or windows_path.is_absolute() or windows_path.drive:
        raise ValueError("source_path must be relative")
    if ".." in posix_path.parts:
        raise ValueError("source_path must not escape its root with '..'")

    normalized = posix_path.as_posix()
    if normalized in ("", "."):
        raise ValueError("source_path must identify a repository file")
    return normalized


def _normalize_optional_text(value: Any, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string or None")
    text = value.strip()
    if text != value:
        raise ValueError(f"{name} must not have surrounding whitespace")
    return text or None


def _validate_nonempty_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    if value != value.strip():
        raise ValueError(f"{name} must not have surrounding whitespace")
    return value


def _validate_messages(value: Any, name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        raise TypeError(f"{name} must be an iterable of strings")
    try:
        messages = tuple(value)
    except TypeError as error:
        raise TypeError(f"{name} must be an iterable of strings") from error
    for index, message in enumerate(messages):
        _validate_nonempty_text(message, f"{name}[{index}]")
    return messages


def _validate_optional_positive_int(value: Any, name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer or None")
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _validate_choice(value: Any, name: str, allowed: tuple[str, ...]) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if value not in allowed:
        raise ValueError(f"{name} must be one of: {', '.join(allowed)}")
    return next(item for item in allowed if item == value)
