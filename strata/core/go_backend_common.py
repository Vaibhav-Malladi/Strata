"""Small source-text helpers for Go backend route extraction."""

import re
from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any

from strata.core.python_backend_common import normalize_http_method


GO_DYNAMIC_STRING_WARNING = (
    "Dynamic Go route string ignored; only simple quoted string literals are supported."
)
GO_DYNAMIC_METHOD_WARNING = (
    "Dynamic Go HTTP method ignored; only simple quoted method literals are supported."
)

_FUNCTION_RE = re.compile(
    r"^\s*func\s+(?:\((?P<receiver>[^)]*)\)\s*)?(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\("
)
_GO_STRING_RE = re.compile(r'^\s*"(?P<value>(?:[^"\\]|\\.)*)"\s*$')
_HANDLER_RE = re.compile(
    r"^\s*(?P<name>[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)"
)


@dataclass(frozen=True, slots=True)
class GoSourceLine:
    source_path: str
    line_number: int
    text: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_path", normalize_go_source_path(self.source_path))
        object.__setattr__(self, "line_number", _positive_int(self.line_number, "line_number"))
        if not isinstance(self.text, str):
            raise TypeError("text must be a string")

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "line_number": self.line_number,
            "text": self.text,
        }


@dataclass(frozen=True, slots=True)
class GoFunctionSymbol:
    name: str
    receiver: str | None
    line_number: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _nonempty_string(self.name, "name"))
        object.__setattr__(self, "receiver", _optional_string(self.receiver, "receiver"))
        object.__setattr__(self, "line_number", _positive_int(self.line_number, "line_number"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "receiver": self.receiver,
            "line_number": self.line_number,
        }


@dataclass(frozen=True, slots=True)
class GoBackendParseResult:
    source_path: str
    lines: tuple[GoSourceLine, ...]
    functions: tuple[GoFunctionSymbol, ...]
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        source_path = normalize_go_source_path(self.source_path)
        object.__setattr__(self, "source_path", source_path)
        if not all(isinstance(line, GoSourceLine) for line in self.lines):
            raise TypeError("lines must contain GoSourceLine values")
        if not all(isinstance(symbol, GoFunctionSymbol) for symbol in self.functions):
            raise TypeError("functions must contain GoFunctionSymbol values")
        object.__setattr__(self, "warnings", _messages(self.warnings, "warnings"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "line_count": len(self.lines),
            "functions": [symbol.to_dict() for symbol in self.functions],
            "warnings": list(self.warnings),
        }


def parse_go_backend_source(source_path: str, source_text: str) -> GoBackendParseResult:
    """Create stable line and symbol records from supplied Go source text."""

    if not isinstance(source_text, str):
        raise TypeError("source_text must be a string")
    normalized_path = normalize_go_source_path(source_path)
    lines = tuple(
        GoSourceLine(normalized_path, index, text)
        for index, text in enumerate(source_text.splitlines(), start=1)
    )
    functions = tuple(
        symbol
        for line in lines
        for symbol in [_function_symbol_from_line(line)]
        if symbol is not None
    )
    return GoBackendParseResult(
        source_path=normalized_path,
        lines=lines,
        functions=functions,
    )


def normalize_go_source_path(value: Any) -> str:
    if not isinstance(value, str):
        raise TypeError("source_path must be a string")
    text = value.strip()
    if not text:
        raise ValueError("source_path must be a non-empty relative path")
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


def go_string_literal(value: str) -> str | None:
    """Return simple double-quoted Go string literals without guessing dynamics."""

    if not isinstance(value, str):
        raise TypeError("value must be a string")
    match = _GO_STRING_RE.match(value)
    if not match:
        return None
    return _unescape_basic_go_string(match.group("value"))


def extract_go_handler_symbol(value: str) -> str | None:
    """Extract simple handler identifiers or member selectors from Go call args."""

    if not isinstance(value, str):
        raise TypeError("value must be a string")
    match = _HANDLER_RE.match(value)
    if not match:
        return None
    name = match.group("name")
    if name in {"func", "nil"}:
        return None
    return name


def extract_go_http_methods(value: str) -> tuple[str, ...]:
    """Extract explicit quoted HTTP methods from source snippets."""

    if not isinstance(value, str):
        raise TypeError("value must be a string")
    methods: list[str] = []
    for match in re.finditer(r'"(?P<method>[A-Za-z]+)"', value):
        method = normalize_http_method(match.group("method"))
        if method != "unknown" and method not in methods:
            methods.append(method)
    return tuple(methods)


def go_evidence(line_number: int, pattern_name: str) -> str:
    return f"line {_positive_int(line_number, 'line_number')} call {_nonempty_string(pattern_name, 'pattern_name')}"


def go_backend_parse_result_to_dict(result: GoBackendParseResult) -> dict[str, Any]:
    if not isinstance(result, GoBackendParseResult):
        raise TypeError("result must be a GoBackendParseResult")
    return result.to_dict()


def _function_symbol_from_line(line: GoSourceLine) -> GoFunctionSymbol | None:
    match = _FUNCTION_RE.match(line.text)
    if not match:
        return None
    return GoFunctionSymbol(
        name=match.group("name"),
        receiver=_normalize_receiver(match.group("receiver")),
        line_number=line.line_number,
    )


def _normalize_receiver(value: str | None) -> str | None:
    if not value:
        return None
    pieces = value.replace("*", " ").split()
    if not pieces:
        return None
    return pieces[-1]


def _unescape_basic_go_string(value: str) -> str:
    return (
        value.replace(r"\/", "/")
        .replace(r"\"", '"')
        .replace(r"\n", "\n")
        .replace(r"\t", "\t")
        .replace(r"\\", "\\")
    )


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _nonempty_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    if value != value.strip():
        raise ValueError(f"{name} must not have surrounding whitespace")
    return value


def _optional_string(value: Any, name: str) -> str | None:
    if value is None:
        return None
    return _nonempty_string(value, name)


def _messages(value: Any, name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        raise TypeError(f"{name} must be an iterable of strings")
    try:
        messages = tuple(value)
    except TypeError as error:
        raise TypeError(f"{name} must be an iterable of strings") from error
    for index, message in enumerate(messages):
        _nonempty_string(message, f"{name}[{index}]")
    return messages
