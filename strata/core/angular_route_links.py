"""Lightweight Angular route relationship inference from one source string.

J3 works from supplied route/config source text only. It does not parse
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


MAX_ROUTE_EVIDENCE_CHARS = 220
MAX_LAZY_EXPRESSION_CHARS = 900

_COMPONENT_PROPERTY_PATTERN = re.compile(
    r"(?<![\w$])component\s*:\s*(?P<symbol>[A-Za-z_$][\w$]*)"
)
_COMPONENT_MALFORMED_PATTERN = re.compile(r"(?<![\w$])component\s*:")
_LAZY_PROPERTY_PATTERN = re.compile(
    r"(?<![\w$])(?P<property>loadComponent|loadChildren)\s*:"
)
_IMPORT_PATTERN = re.compile(
    r"import\s*\(\s*(?P<quote>['\"`])(?P<path>.*?)(?P=quote)\s*\)",
    re.DOTALL,
)
_THEN_SYMBOL_PATTERN = re.compile(
    r"\.then\s*\(\s*(?P<module>[A-Za-z_$][\w$]*)\s*=>\s*"
    r"(?P=module)\.(?P<symbol>[A-Za-z_$][\w$]*)",
    re.DOTALL,
)
_SYMBOL_PATTERN = re.compile(r"[A-Za-z_$][\w$]*")


def infer_angular_route_links(
    source_path: str,
    source_text: str,
    repo_root: str | None = None,
) -> tuple[FrontendRelationship, ...]:
    """Infer route-to-component and route-to-lazy-target relationships."""

    normalized_source = normalize_relative_path(source_path)
    _validate_source_text(source_text)
    if repo_root is not None:
        _validate_repo_root(repo_root)

    relationships: list[FrontendRelationship] = []
    relationships.extend(_component_route_links(normalized_source, source_text))
    relationships.extend(_lazy_route_links(normalized_source, source_text, repo_root))
    return _sort_frontend_relationships(relationships)


def _component_route_links(
    source_path: str,
    source_text: str,
) -> tuple[FrontendRelationship, ...]:
    links = []
    valid_spans = set()
    for match in _COMPONENT_PROPERTY_PATTERN.finditer(source_text):
        valid_spans.add(match.start())
        symbol = match.group("symbol")
        links.append(
            _create_frontend_relationship(
                framework="angular",
                source_path=source_path,
                target_symbol=symbol,
                relationship_type="component_route",
                confidence="high",
                evidence=(_evidence(source_text, match.start(), match.end()),),
                warnings=(),
                reason="Angular route component metadata references a component symbol.",
            )
        )

    for match in _COMPONENT_MALFORMED_PATTERN.finditer(source_text):
        if match.start() in valid_spans:
            continue
        expression = _expression_window(source_text, match.start())
        if _looks_like_symbol_after_colon(expression):
            continue
        links.append(
            _unresolved_relationship(
                source_path,
                "component_route",
                "unresolved component",
                "component",
                _evidence(source_text, match.start()),
                ("Angular component route metadata is malformed.",),
            )
        )

    return tuple(links)


def _lazy_route_links(
    source_path: str,
    source_text: str,
    repo_root: str | None,
) -> tuple[FrontendRelationship, ...]:
    links = []
    for match in _LAZY_PROPERTY_PATTERN.finditer(source_text):
        property_name = match.group("property")
        expression = _expression_window(source_text, match.start())
        import_match = _IMPORT_PATTERN.search(expression)
        if import_match is None:
            links.append(
                _unresolved_relationship(
                    source_path,
                    "route_lazy_target",
                    f"unresolved {property_name}",
                    property_name,
                    _evidence(source_text, match.start()),
                    (f"Angular {property_name} metadata is malformed.",),
                )
            )
            continue

        target_path, target_warning = _resolve_route_relative_target(
            source_path,
            import_match.group("path"),
            repo_root,
        )
        then_match = _THEN_SYMBOL_PATTERN.search(expression[import_match.end() :])
        target_symbol = then_match.group("symbol") if then_match else None
        warnings: tuple[str, ...] = ()
        confidence = "high"
        if target_symbol is None:
            warnings = (
                f"Angular {property_name} lazy import target symbol was not found.",
            )
            confidence = "medium"

        if target_path is None:
            links.append(
                _unresolved_relationship(
                    source_path,
                    "route_lazy_target",
                    target_symbol or f"unresolved {property_name}",
                    property_name,
                    _evidence(
                        source_text,
                        match.start(),
                        match.start() + min(len(expression), MAX_ROUTE_EVIDENCE_CHARS),
                    ),
                    (*warnings, target_warning),
                )
            )
            continue

        links.append(
            _create_frontend_relationship(
                framework="angular",
                source_path=source_path,
                target_path=target_path,
                target_symbol=target_symbol,
                relationship_type="route_lazy_target",
                confidence=confidence,
                evidence=(
                    _evidence(
                        source_text,
                        match.start(),
                        match.start() + min(len(expression), MAX_ROUTE_EVIDENCE_CHARS),
                    ),
                ),
                warnings=warnings,
                reason=f"Angular {property_name} metadata references a lazy target.",
            )
        )

    return tuple(links)


def _unresolved_relationship(
    source_path: str,
    relationship_type: str,
    target_symbol: str,
    property_name: str,
    evidence: str,
    warnings: tuple[str, ...],
) -> FrontendRelationship:
    return _create_frontend_relationship(
        framework="angular",
        source_path=source_path,
        target_symbol=target_symbol,
        relationship_type=relationship_type,
        confidence="low",
        evidence=(evidence,),
        warnings=warnings,
        reason=f"Angular {property_name} route metadata could not be resolved safely.",
    )


def _expression_window(source_text: str, start: int) -> str:
    return source_text[start : start + MAX_LAZY_EXPRESSION_CHARS]


def _looks_like_symbol_after_colon(expression: str) -> bool:
    colon_index = expression.find(":")
    if colon_index < 0:
        return False
    after_colon = expression[colon_index + 1 :].lstrip()
    return bool(_SYMBOL_PATTERN.match(after_colon))


def _resolve_route_relative_target(
    source_path: str,
    target_value: str,
    repo_root: str | None,
) -> tuple[str | None, str]:
    value = str(target_value)
    if not value or not value.strip() or value != value.strip() or "\x00" in value:
        return None, "Angular lazy route import path is empty or unsafe."

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
        return None, "Angular lazy route import path does not identify a file."
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
        return f"Angular lazy route import {value!r} {reason}."
    return f"Angular lazy route import {value!r} {reason} for repo_root {repo_root!r}."


def _evidence(text: str, start: int, end: int | None = None) -> str:
    if end is None:
        end = min(len(text), start + MAX_ROUTE_EVIDENCE_CHARS)
    snippet = " ".join(text[start:end].split())
    if len(snippet) <= MAX_ROUTE_EVIDENCE_CHARS:
        return snippet
    return f"{snippet[: MAX_ROUTE_EVIDENCE_CHARS - 3]}..."


def _validate_source_text(value: Any) -> None:
    if not isinstance(value, str):
        raise TypeError("source_text must be a string")


def _validate_repo_root(value: Any) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("repo_root must be a non-empty string when provided")
    if value != value.strip() or "\x00" in value:
        raise ValueError("repo_root must not contain padding or null bytes")
