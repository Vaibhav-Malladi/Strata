"""Lightweight Angular component template/style relationship inference.

J2 works from one supplied component source string. It does not scan
repositories, read linked files, parse TypeScript, or trace Angular routes.
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


MAX_STYLE_URLS = 20
MAX_EVIDENCE_CHARS = 160

_PROPERTY_PATTERN_TEMPLATE = r"(?<![\w$]){}\s*:"
_STRING_QUOTES = {"'", '"', "`"}


def infer_angular_component_links(
    source_path: str,
    source_text: str,
    repo_root: str | None = None,
) -> tuple[FrontendRelationship, ...]:
    """Infer Angular template/style relationships from one component source."""

    normalized_source = normalize_relative_path(source_path)
    _validate_source_text(source_text)
    if repo_root is not None:
        _validate_repo_root(repo_root)

    metadata, metadata_warning = _extract_component_metadata(source_text)
    if metadata is None:
        return ()

    relationships: list[FrontendRelationship] = []
    shared_warnings = (metadata_warning,) if metadata_warning else ()

    relationships.extend(
        _external_string_property_links(
            metadata,
            normalized_source,
            "templateUrl",
            "component_template",
            repo_root,
            shared_warnings,
        )
    )
    relationships.extend(
        _external_string_property_links(
            metadata,
            normalized_source,
            "styleUrl",
            "component_style",
            repo_root,
            shared_warnings,
        )
    )
    relationships.extend(
        _external_array_property_links(
            metadata,
            normalized_source,
            "styleUrls",
            "component_style",
            repo_root,
            shared_warnings,
        )
    )
    relationships.extend(
        _inline_string_property_links(
            metadata,
            normalized_source,
            "template",
            "component_template",
            "inline template",
            shared_warnings,
        )
    )
    relationships.extend(
        _inline_array_property_links(
            metadata,
            normalized_source,
            "styles",
            "component_style",
            "inline styles",
            shared_warnings,
        )
    )

    return _sort_frontend_relationships(relationships)


def _external_string_property_links(
    metadata: str,
    source_path: str,
    property_name: str,
    relationship_type: str,
    repo_root: str | None,
    shared_warnings: tuple[str, ...],
) -> tuple[FrontendRelationship, ...]:
    links = []
    for observation in _string_property_observations(metadata, property_name):
        if observation["value"] is None:
            links.append(
                _unresolved_relationship(
                    source_path,
                    relationship_type,
                    f"unresolved {property_name}",
                    property_name,
                    observation["evidence"],
                    (*shared_warnings, str(observation["warning"])),
                )
            )
            continue

        target_path, target_warning = _resolve_component_relative_target(
            source_path,
            str(observation["value"]),
            repo_root,
        )
        if target_path is None:
            links.append(
                _unresolved_relationship(
                    source_path,
                    relationship_type,
                    f"unresolved {property_name}",
                    property_name,
                    observation["evidence"],
                    (*shared_warnings, target_warning),
                )
            )
            continue

        links.append(
            _create_frontend_relationship(
                framework="angular",
                source_path=source_path,
                target_path=target_path,
                relationship_type=relationship_type,
                confidence="high",
                evidence=(str(observation["evidence"]),),
                warnings=shared_warnings,
                reason=f"Angular {property_name} metadata references an external file.",
            )
        )
    return tuple(links)


def _external_array_property_links(
    metadata: str,
    source_path: str,
    property_name: str,
    relationship_type: str,
    repo_root: str | None,
    shared_warnings: tuple[str, ...],
) -> tuple[FrontendRelationship, ...]:
    links = []
    for observation in _array_property_observations(metadata, property_name):
        values = observation["values"]
        if not values:
            links.append(
                _unresolved_relationship(
                    source_path,
                    relationship_type,
                    f"unresolved {property_name}",
                    property_name,
                    observation["evidence"],
                    (*shared_warnings, str(observation["warning"])),
                )
            )
            continue

        warnings = tuple(observation["warnings"])
        for value in values:
            target_path, target_warning = _resolve_component_relative_target(
                source_path,
                value,
                repo_root,
            )
            if target_path is None:
                links.append(
                    _unresolved_relationship(
                        source_path,
                        relationship_type,
                        f"unresolved {property_name}",
                        property_name,
                        observation["evidence"],
                        (*shared_warnings, *warnings, target_warning),
                    )
                )
                continue

            links.append(
                _create_frontend_relationship(
                    framework="angular",
                    source_path=source_path,
                    target_path=target_path,
                    relationship_type=relationship_type,
                    confidence="high",
                    evidence=(str(observation["evidence"]),),
                    warnings=(*shared_warnings, *warnings),
                    reason=(
                        f"Angular {property_name} metadata references an external file."
                    ),
                )
            )
    return tuple(links)


def _inline_string_property_links(
    metadata: str,
    source_path: str,
    property_name: str,
    relationship_type: str,
    target_symbol: str,
    shared_warnings: tuple[str, ...],
) -> tuple[FrontendRelationship, ...]:
    links = []
    for observation in _string_property_observations(metadata, property_name):
        warnings = shared_warnings
        confidence = "high"
        symbol = target_symbol
        reason = f"Angular {property_name} metadata defines {target_symbol}."
        if observation["value"] is None:
            warnings = (*warnings, str(observation["warning"]))
            confidence = "low"
            symbol = f"unresolved {property_name}"
            reason = f"Angular {property_name} metadata could not be read safely."
        links.append(
            _create_frontend_relationship(
                framework="angular",
                source_path=source_path,
                target_symbol=symbol,
                relationship_type=relationship_type,
                confidence=confidence,
                evidence=(str(observation["evidence"]),),
                warnings=warnings,
                reason=reason,
            )
        )
    return tuple(links)


def _inline_array_property_links(
    metadata: str,
    source_path: str,
    property_name: str,
    relationship_type: str,
    target_symbol: str,
    shared_warnings: tuple[str, ...],
) -> tuple[FrontendRelationship, ...]:
    links = []
    for observation in _array_property_observations(metadata, property_name):
        warnings = (*shared_warnings, *tuple(observation["warnings"]))
        confidence = "high"
        symbol = target_symbol
        reason = f"Angular {property_name} metadata defines {target_symbol}."
        if not observation["values"]:
            warnings = (*warnings, str(observation["warning"]))
            confidence = "low"
            symbol = f"unresolved {property_name}"
            reason = f"Angular {property_name} metadata could not be read safely."
        links.append(
            _create_frontend_relationship(
                framework="angular",
                source_path=source_path,
                target_symbol=symbol,
                relationship_type=relationship_type,
                confidence=confidence,
                evidence=(str(observation["evidence"]),),
                warnings=warnings,
                reason=reason,
            )
        )
    return tuple(links)


def _unresolved_relationship(
    source_path: str,
    relationship_type: str,
    target_symbol: str,
    property_name: str,
    evidence: Any,
    warnings: tuple[str, ...],
) -> FrontendRelationship:
    return _create_frontend_relationship(
        framework="angular",
        source_path=source_path,
        target_symbol=target_symbol,
        relationship_type=relationship_type,
        confidence="low",
        evidence=(str(evidence),),
        warnings=warnings,
        reason=f"Angular {property_name} metadata could not be resolved safely.",
    )


def _extract_component_metadata(source_text: str) -> tuple[str | None, str | None]:
    component_index = source_text.find("@Component")
    if component_index < 0:
        return None, None

    paren_index = source_text.find("(", component_index)
    if paren_index < 0:
        return (
            "",
            "Angular @Component decorator is malformed; opening parenthesis missing.",
        )

    brace_index = source_text.find("{", paren_index)
    if brace_index < 0:
        return "", "Angular @Component metadata is malformed; opening brace missing."

    closing_brace = _find_matching_delimiter(source_text, brace_index, "{", "}")
    if closing_brace < 0:
        return (
            source_text[brace_index + 1 :],
            "Angular @Component metadata is malformed; closing brace missing.",
        )
    return source_text[brace_index + 1 : closing_brace], None


def _string_property_observations(
    metadata: str,
    property_name: str,
) -> tuple[dict[str, Any], ...]:
    observations = []
    for match in _property_matches(metadata, property_name):
        value_start = _skip_whitespace(metadata, match.end())
        evidence = _evidence(metadata, match.start())
        if value_start >= len(metadata) or metadata[value_start] not in _STRING_QUOTES:
            observations.append(
                {
                    "value": None,
                    "evidence": evidence,
                    "warning": f"Angular {property_name} metadata is malformed.",
                }
            )
            continue
        value, value_end = _read_string_literal(metadata, value_start)
        if value_end < 0:
            observations.append(
                {
                    "value": None,
                    "evidence": evidence,
                    "warning": f"Angular {property_name} string is unterminated.",
                }
            )
            continue
        observations.append(
            {
                "value": value,
                "evidence": _evidence(metadata, match.start(), value_end + 1),
                "warning": None,
            }
        )
    return tuple(observations)


def _array_property_observations(
    metadata: str,
    property_name: str,
) -> tuple[dict[str, Any], ...]:
    observations = []
    for match in _property_matches(metadata, property_name):
        value_start = _skip_whitespace(metadata, match.end())
        evidence = _evidence(metadata, match.start())
        if value_start >= len(metadata) or metadata[value_start] != "[":
            observations.append(
                {
                    "values": (),
                    "evidence": evidence,
                    "warnings": (),
                    "warning": f"Angular {property_name} metadata is malformed.",
                }
            )
            continue

        value_end = _find_matching_delimiter(metadata, value_start, "[", "]")
        warnings: list[str] = []
        if value_end < 0:
            value_end = len(metadata) - 1
            warnings.append(f"Angular {property_name} array is unterminated.")

        array_text = metadata[value_start : value_end + 1]
        values = _string_literals_in(array_text)
        if len(values) > MAX_STYLE_URLS:
            values = values[:MAX_STYLE_URLS]
            warnings.append(
                f"Angular {property_name} metadata exceeded {MAX_STYLE_URLS} entries."
            )
        observations.append(
            {
                "values": tuple(values),
                "evidence": _evidence(metadata, match.start(), value_end + 1),
                "warnings": tuple(warnings),
                "warning": f"Angular {property_name} metadata has no string entries.",
            }
        )
    return tuple(observations)


def _resolve_component_relative_target(
    source_path: str,
    target_value: str,
    repo_root: str | None,
) -> tuple[str | None, str]:
    value = str(target_value)
    if not value or not value.strip() or value != value.strip() or "\x00" in value:
        return None, "Angular metadata target path is empty or unsafe."

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
        return None, "Angular metadata target path does not identify a file."
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
        return f"Angular metadata target {value!r} {reason}."
    return f"Angular metadata target {value!r} {reason} for repo_root {repo_root!r}."


def _property_matches(metadata: str, property_name: str):
    pattern = re.compile(_PROPERTY_PATTERN_TEMPLATE.format(re.escape(property_name)))
    return pattern.finditer(metadata)


def _skip_whitespace(text: str, index: int) -> int:
    while index < len(text) and text[index].isspace():
        index += 1
    return index


def _read_string_literal(text: str, start: int) -> tuple[str | None, int]:
    quote = text[start]
    index = start + 1
    value_chars = []
    while index < len(text):
        char = text[index]
        if char == "\\":
            if index + 1 < len(text):
                value_chars.append(text[index + 1])
                index += 2
                continue
        if char == quote:
            return "".join(value_chars), index
        value_chars.append(char)
        index += 1
    return None, -1


def _string_literals_in(text: str) -> tuple[str, ...]:
    values = []
    index = 0
    while index < len(text):
        if text[index] not in _STRING_QUOTES:
            index += 1
            continue
        value, end = _read_string_literal(text, index)
        if end < 0:
            break
        if value is not None:
            values.append(value)
        index = end + 1
    return tuple(values)


def _find_matching_delimiter(
    text: str,
    start: int,
    open_char: str,
    close_char: str,
) -> int:
    depth = 0
    index = start
    string_quote = ""
    in_line_comment = False
    in_block_comment = False

    while index < len(text):
        char = text[index]
        next_char = text[index + 1] if index + 1 < len(text) else ""

        if in_line_comment:
            if char in "\r\n":
                in_line_comment = False
            index += 1
            continue

        if in_block_comment:
            if char == "*" and next_char == "/":
                in_block_comment = False
                index += 2
                continue
            index += 1
            continue

        if string_quote:
            if char == "\\":
                index += 2
                continue
            if char == string_quote:
                string_quote = ""
            index += 1
            continue

        if char == "/" and next_char == "/":
            in_line_comment = True
            index += 2
            continue
        if char == "/" and next_char == "*":
            in_block_comment = True
            index += 2
            continue
        if char in _STRING_QUOTES:
            string_quote = char
            index += 1
            continue
        if char == open_char:
            depth += 1
        elif char == close_char:
            depth -= 1
            if depth == 0:
                return index
        index += 1

    return -1


def _evidence(text: str, start: int, end: int | None = None) -> str:
    if end is None:
        end = min(len(text), start + MAX_EVIDENCE_CHARS)
    snippet = " ".join(text[start:end].split())
    if len(snippet) <= MAX_EVIDENCE_CHARS:
        return snippet
    return f"{snippet[: MAX_EVIDENCE_CHARS - 3]}..."


def _validate_source_text(value: Any) -> None:
    if not isinstance(value, str):
        raise TypeError("source_text must be a string")


def _validate_repo_root(value: Any) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("repo_root must be a non-empty string when provided")
    if value != value.strip() or "\x00" in value:
        raise ValueError("repo_root must not contain padding or null bytes")
