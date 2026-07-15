"""Lightweight React relationship inference from one source string.

J4 works from supplied React/JS/TS source text only. It does not parse Babel or
TypeScript, scan repositories, traverse route graphs, or resolve aliases.
"""

import re
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any

from strata.core.frontend_relationships import (
    FrontendRelationship,
    create_frontend_relationship as _create_frontend_relationship,
    normalize_relative_path,
    sort_frontend_relationships as _sort_frontend_relationships,
)


MAX_REACT_EVIDENCE_CHARS = 220
MAX_LAZY_EXPRESSION_CHARS = 900

_JSX_COMPONENT_PATTERN = re.compile(r"<\s*(?!/)(?P<name>[A-Z][A-Za-z0-9_$.]*)\b")
_HOOK_CALL_PATTERN = re.compile(r"(?<![\w$])(?P<name>use[A-Z][\w$]*)\s*\(")
_FETCH_CALL_PATTERN = re.compile(r"(?<![\w$.])fetch\s*\(")
_CLIENT_MEMBER_CALL_PATTERN = re.compile(
    r"(?<![\w$])(?P<object>(?:api|client|service)|"
    r"[A-Za-z_$][\w$]*(?:api|Api|API|client|Client|service|Service))"
    r"\s*\.\s*(?P<method>[A-Za-z_$][\w$]*)\s*\("
)
_CLIENT_FUNCTION_CALL_PATTERN = re.compile(
    r"(?<![\w$])(?P<name>[A-Za-z_$][\w$]*(?:Api|API|Client|Service))\s*\("
)
_LAZY_PATTERN = re.compile(r"(?<![\w$.])(?:React\.)?lazy\s*\(")
_IMPORT_PATTERN = re.compile(
    r"import\s*\(\s*(?P<quote>['\"`])(?P<path>.*?)(?P=quote)\s*\)",
    re.DOTALL,
)
_ASSIGNMENT_SYMBOL_PATTERN = re.compile(
    r"(?:const|let|var)\s+(?P<symbol>[A-Z][A-Za-z0-9_$]*)\s*=\s*$"
)
_FUNCTION_HOOK_PATTERN = re.compile(r"function\s+use[A-Z][A-Za-z0-9_$]*\s*\(")
_HTML_LIKE_COMPONENTS = {"Fragment", "React.Fragment", "StrictMode", "React.StrictMode"}
_BUILTIN_HOOKS = {
    "useActionState",
    "useCallback",
    "useContext",
    "useDebugValue",
    "useDeferredValue",
    "useEffect",
    "useId",
    "useImperativeHandle",
    "useInsertionEffect",
    "useLayoutEffect",
    "useMemo",
    "useOptimistic",
    "useReducer",
    "useRef",
    "useState",
    "useSyncExternalStore",
    "useTransition",
}


def infer_react_links(
    source_path: str,
    source_text: str,
    repo_root: str | None = None,
) -> tuple[FrontendRelationship, ...]:
    """Infer React component, hook, API-client, and lazy import relationships."""

    normalized_source = normalize_relative_path(source_path)
    _validate_source_text(source_text)
    if repo_root is not None:
        _validate_repo_root(repo_root)

    source_is_hook = _source_is_hook(normalized_source, source_text)
    relationships: list[FrontendRelationship] = []
    relationships.extend(_jsx_component_links(normalized_source, source_text))
    relationships.extend(_hook_links(normalized_source, source_text, source_is_hook))
    relationships.extend(
        _api_client_links(normalized_source, source_text, source_is_hook)
    )
    relationships.extend(_lazy_links(normalized_source, source_text, repo_root))
    return _sort_frontend_relationships(set(relationships))


def _jsx_component_links(
    source_path: str,
    source_text: str,
) -> tuple[FrontendRelationship, ...]:
    links = []
    for match in _JSX_COMPONENT_PATTERN.finditer(source_text):
        raw_name = match.group("name")
        if raw_name in _HTML_LIKE_COMPONENTS:
            continue
        target_symbol = raw_name.rsplit(".", 1)[-1]
        links.append(
            _create_frontend_relationship(
                framework="react",
                source_path=source_path,
                target_symbol=target_symbol,
                relationship_type="component_child_component",
                confidence="high",
                evidence=(_evidence(source_text, match.start(), match.end()),),
                warnings=(),
                reason="React JSX references an uppercase child component tag.",
            )
        )
    return tuple(links)


def _hook_links(
    source_path: str,
    source_text: str,
    source_is_hook: bool,
) -> tuple[FrontendRelationship, ...]:
    links = []
    for match in _HOOK_CALL_PATTERN.finditer(source_text):
        name = match.group("name")
        if name in _BUILTIN_HOOKS or _is_hook_definition_context(
            source_text, match.start()
        ):
            continue
        reason = (
            "React hook calls another hook."
            if source_is_hook
            else "React component calls a hook."
        )
        links.append(
            _create_frontend_relationship(
                framework="react",
                source_path=source_path,
                target_symbol=name,
                relationship_type="hook_component",
                confidence="high",
                evidence=(_evidence(source_text, match.start(), match.end()),),
                warnings=(),
                reason=reason,
            )
        )
    return tuple(links)


def _api_client_links(
    source_path: str,
    source_text: str,
    source_is_hook: bool,
) -> tuple[FrontendRelationship, ...]:
    relationship_type = "hook_api_client" if source_is_hook else "component_api_client"
    reason = (
        "React hook calls an API/client-like function."
        if source_is_hook
        else "React component calls an API/client-like function."
    )
    links = []

    for match in _FETCH_CALL_PATTERN.finditer(source_text):
        links.append(
            _api_relationship(
                source_path,
                relationship_type,
                "fetch",
                source_text,
                match.start(),
                match.end(),
                reason,
            )
        )

    for match in _CLIENT_MEMBER_CALL_PATTERN.finditer(source_text):
        links.append(
            _api_relationship(
                source_path,
                relationship_type,
                f"{match.group('object')}.{match.group('method')}",
                source_text,
                match.start(),
                match.end(),
                reason,
            )
        )

    for match in _CLIENT_FUNCTION_CALL_PATTERN.finditer(source_text):
        if _is_function_definition_context(source_text, match.start()):
            continue
        links.append(
            _api_relationship(
                source_path,
                relationship_type,
                match.group("name"),
                source_text,
                match.start(),
                match.end(),
                reason,
            )
        )

    return tuple(links)


def _api_relationship(
    source_path: str,
    relationship_type: str,
    target_symbol: str,
    source_text: str,
    start: int,
    end: int,
    reason: str,
) -> FrontendRelationship:
    return _create_frontend_relationship(
        framework="react",
        source_path=source_path,
        target_symbol=target_symbol,
        relationship_type=relationship_type,
        confidence="medium",
        evidence=(_evidence(source_text, start, end),),
        warnings=(),
        reason=reason,
    )


def _lazy_links(
    source_path: str,
    source_text: str,
    repo_root: str | None,
) -> tuple[FrontendRelationship, ...]:
    links = []
    for match in _LAZY_PATTERN.finditer(source_text):
        expression = _expression_window(source_text, match.start())
        target_symbol = _lazy_assignment_symbol(source_text, match.start())
        import_match = _IMPORT_PATTERN.search(expression)
        if import_match is None:
            links.append(
                _unresolved_lazy_relationship(
                    source_path,
                    target_symbol or "unresolved lazy component",
                    _evidence(source_text, match.start()),
                    ("React lazy import metadata is malformed.",),
                )
            )
            continue

        target_path, target_warning = _resolve_react_relative_target(
            source_path,
            import_match.group("path"),
            repo_root,
        )
        evidence = _evidence(
            source_text,
            match.start(),
            match.start() + min(len(expression), MAX_REACT_EVIDENCE_CHARS),
        )
        if target_path is None:
            links.append(
                _unresolved_lazy_relationship(
                    source_path,
                    target_symbol or "unresolved lazy component",
                    evidence,
                    (target_warning,),
                )
            )
            continue

        links.append(
            _create_frontend_relationship(
                framework="react",
                source_path=source_path,
                target_path=target_path,
                target_symbol=target_symbol,
                relationship_type="react_route_component",
                confidence="high" if target_symbol else "medium",
                evidence=(evidence,),
                warnings=()
                if target_symbol
                else ("React lazy component target symbol was not found.",),
                reason="React lazy metadata references a lazy component import.",
            )
        )
    return tuple(links)


def _unresolved_lazy_relationship(
    source_path: str,
    target_symbol: str,
    evidence: str,
    warnings: tuple[str, ...],
) -> FrontendRelationship:
    return _create_frontend_relationship(
        framework="react",
        source_path=source_path,
        target_symbol=target_symbol,
        relationship_type="react_route_component",
        confidence="low",
        evidence=(evidence,),
        warnings=warnings,
        reason="React lazy import metadata could not be resolved safely.",
    )


def _source_is_hook(source_path: str, source_text: str) -> bool:
    filename = source_path.rsplit("/", 1)[-1]
    stem = filename.rsplit(".", 1)[0]
    return bool(re.match(r"use[A-Z]", stem)) or bool(
        _FUNCTION_HOOK_PATTERN.search(source_text)
    )


def _is_hook_definition_context(source_text: str, start: int) -> bool:
    prefix = source_text[max(0, start - 24) : start]
    return bool(re.search(r"(?:function|const|let|var)\s+$", prefix))


def _is_function_definition_context(source_text: str, start: int) -> bool:
    prefix = source_text[max(0, start - 24) : start]
    return bool(re.search(r"(?:function|const|let|var)\s+$", prefix))


def _lazy_assignment_symbol(source_text: str, start: int) -> str | None:
    prefix = source_text[max(0, start - 120) : start]
    match = _ASSIGNMENT_SYMBOL_PATTERN.search(prefix)
    if match is None:
        return None
    return match.group("symbol")


def _expression_window(source_text: str, start: int) -> str:
    return source_text[start : start + MAX_LAZY_EXPRESSION_CHARS]


def _resolve_react_relative_target(
    source_path: str,
    target_value: str,
    repo_root: str | None,
) -> tuple[str | None, str]:
    value = str(target_value)
    if not value or not value.strip() or value != value.strip() or "\x00" in value:
        return None, "React lazy import path is empty or unsafe."

    if _is_absolute_or_non_relative_target(value):
        return None, _target_warning(
            value,
            "is not a repository-relative target",
            repo_root,
        )

    source_dir = PurePosixPath(source_path).parent
    stack = [part for part in source_dir.parts if part not in ("", ".")]
    for part in PurePosixPath(value.replace("\\", "/")).parts:
        if part in ("", "."):
            continue
        if part == "..":
            if not stack:
                return None, _target_warning(
                    value,
                    "would traverse outside the repository",
                    repo_root,
                )
            stack.pop()
            continue
        stack.append(part)

    if not stack:
        return None, "React lazy import path does not identify a file."
    return normalize_relative_path("/".join(stack)), ""


def _is_absolute_or_non_relative_target(value: str) -> bool:
    windows_path = PureWindowsPath(value)
    posix_value = value.replace("\\", "/")
    posix_path = PurePosixPath(posix_value)
    return (
        posix_path.is_absolute()
        or windows_path.is_absolute()
        or bool(windows_path.drive)
        or "://" in value
        or value.startswith("~")
    )


def _target_warning(value: str, reason: str, repo_root: str | None) -> str:
    if repo_root is None:
        return f"React lazy import {value!r} {reason}."
    return f"React lazy import {value!r} {reason} for repo_root {repo_root!r}."


def _evidence(text: str, start: int, end: int | None = None) -> str:
    if end is None:
        end = min(len(text), start + MAX_REACT_EVIDENCE_CHARS)
    snippet = " ".join(text[start:end].split())
    if len(snippet) <= MAX_REACT_EVIDENCE_CHARS:
        return snippet
    return f"{snippet[: MAX_REACT_EVIDENCE_CHARS - 3]}..."


def _validate_source_text(value: Any) -> None:
    if not isinstance(value, str):
        raise TypeError("source_text must be a string")


def _validate_repo_root(value: Any) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("repo_root must be a non-empty string when provided")
    if value != value.strip() or "\x00" in value:
        raise ValueError("repo_root must not contain padding or null bytes")
