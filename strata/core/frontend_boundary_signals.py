"""Infer Module Federation and custom-element boundary signals from one string.

J6 identifies likely frontend app boundaries inside supplied source/config/
template text only. It does not scan repositories, read webpack configs, or
perform workspace/cross-repo resolution.
"""

import re
from typing import Any

from strata.core.frontend_relationships import (
    FRONTEND_FRAMEWORKS as _FRONTEND_FRAMEWORKS,
    FrontendRelationship,
    create_frontend_relationship as _create_frontend_relationship,
    sort_frontend_relationships as _sort_frontend_relationships,
)


MAX_BOUNDARY_EVIDENCE_CHARS = 220
MAX_EXPRESSION_CHARS = 900

_REMOTES_OBJECT_PATTERN = re.compile(
    r"\bremotes\s*:\s*\{(?P<body>[\s\S]{0,1400}?)\}"
)
_REMOTES_ARRAY_PATTERN = re.compile(
    r"\bremotes\s*:\s*\[(?P<body>[\s\S]{0,1400}?)\]"
)
_EXPOSES_OBJECT_PATTERN = re.compile(
    r"\bexposes\s*:\s*\{(?P<body>[\s\S]{0,1400}?)\}"
)
_OBJECT_STRING_ENTRY_PATTERN = re.compile(
    r"(?P<key>['\"]?[A-Za-z0-9_./@$-]+['\"]?)\s*:\s*"
    r"(?P<quote>['\"])(?P<value>[^'\"]+)(?P=quote)"
)
_STRING_LITERAL_PATTERN = re.compile(r"(?P<quote>['\"])(?P<value>[^'\"]+)(?P=quote)")
_LOAD_REMOTE_PATTERN = re.compile(r"\bloadRemoteModule\s*\(")
_DYNAMIC_IMPORT_PATTERN = re.compile(
    r"\bimport\s*\(\s*(?P<quote>['\"`])(?P<path>.*?)(?P=quote)\s*\)",
    re.DOTALL,
)
_REMOTE_ENTRY_LITERAL_PATTERN = re.compile(
    r"(?P<quote>['\"`])(?P<value>[^'\"`]*remoteEntry\.js[^'\"`]*)"
    r"(?P=quote)"
)
_CUSTOM_DEFINE_PATTERN = re.compile(
    r"\bcustomElements\s*\.\s*define\s*\(\s*"
    r"(?P<quote>['\"`])(?P<tag>[a-z][a-z0-9]*-[a-z0-9._-]+)(?P=quote)"
)
_CREATE_ELEMENT_PATTERN = re.compile(
    r"\bdocument\s*\.\s*createElement\s*\(\s*"
    r"(?P<quote>['\"`])(?P<tag>[a-z][a-z0-9]*-[a-z0-9._-]+)(?P=quote)"
)
_TAG_PATTERN = re.compile(r"<\s*(?!/)(?P<tag>[a-z][a-z0-9]*-[a-z0-9._-]+)\b")
_LOAD_REMOTE_FIELD_TEMPLATE = (
    r"\b{}\s*:\s*(?P<quote>['\"])(?P<value>[^'\"]+)(?P=quote)"
)
_CUSTOM_ELEMENTS_SCHEMA_PATTERN = re.compile(r"\bCUSTOM_ELEMENTS_SCHEMA\b")
_NORMAL_HTML_TAGS = {
    "a",
    "article",
    "aside",
    "button",
    "div",
    "footer",
    "form",
    "header",
    "input",
    "label",
    "main",
    "nav",
    "option",
    "section",
    "select",
    "span",
    "textarea",
}


def infer_frontend_boundary_signals(
    source_path: str,
    source_text: str,
    framework: str | None = None,
) -> tuple[FrontendRelationship, ...]:
    """Infer Module Federation and custom-element boundary relationships."""

    _validate_source_text(source_text)
    normalized_framework = _normalize_framework(framework, source_path)
    observations: dict[tuple[str, str | None, str | None, str], dict[str, Any]] = {}
    defined_custom_elements = _defined_custom_elements(source_text)

    _collect_remotes_object(observations, source_path, source_text, normalized_framework)
    _collect_remotes_array(observations, source_path, source_text, normalized_framework)
    _collect_exposes_object(observations, source_path, source_text, normalized_framework)
    _collect_load_remote_module(
        observations,
        source_path,
        source_text,
        normalized_framework,
    )
    _collect_dynamic_federated_imports(
        observations,
        source_path,
        source_text,
        normalized_framework,
    )
    _collect_remote_entry_literals(
        observations,
        source_path,
        source_text,
        normalized_framework,
    )
    _collect_custom_element_definitions(
        observations,
        source_path,
        source_text,
        normalized_framework,
    )
    _collect_document_create_element(
        observations,
        source_path,
        source_text,
        normalized_framework,
    )
    _collect_template_custom_elements(
        observations,
        source_path,
        source_text,
        normalized_framework,
        defined_custom_elements,
    )
    _collect_custom_elements_schema(
        observations,
        source_path,
        source_text,
        normalized_framework,
    )

    relationships = [
        _create_frontend_relationship(
            framework=normalized_framework,
            source_path=source_path,
            target_path=key[1],
            target_symbol=key[2],
            relationship_type=key[0],
            confidence=values["confidence"],
            evidence=tuple(sorted(values["evidence"])),
            warnings=tuple(sorted(values["warnings"])),
            reason=values["reason"],
        )
        for key, values in observations.items()
    ]
    return _sort_frontend_relationships(relationships)


def _collect_remotes_object(
    observations: dict[tuple[str, str | None, str | None, str], dict[str, Any]],
    source_path: str,
    source_text: str,
    framework: str,
) -> None:
    for match in _REMOTES_OBJECT_PATTERN.finditer(source_text):
        body = match.group("body")
        for entry in _OBJECT_STRING_ENTRY_PATTERN.finditer(body):
            remote_name = _strip_quotes(entry.group("key"))
            value = entry.group("value")
            _add_observation(
                observations,
                source_path,
                framework,
                relationship_type="module_federation_remote",
                target_path=value,
                target_symbol=remote_name,
                confidence="high",
                evidence=_evidence(source_text, match.start(), match.end()),
                warnings=(),
                reason="Module Federation remotes object declares a remote.",
            )


def _collect_remotes_array(
    observations: dict[tuple[str, str | None, str | None, str], dict[str, Any]],
    source_path: str,
    source_text: str,
    framework: str,
) -> None:
    for match in _REMOTES_ARRAY_PATTERN.finditer(source_text):
        for literal in _STRING_LITERAL_PATTERN.finditer(match.group("body")):
            value = literal.group("value")
            _add_observation(
                observations,
                source_path,
                framework,
                relationship_type="module_federation_remote",
                target_path=value,
                target_symbol=_remote_name_from_value(value),
                confidence="high",
                evidence=_evidence(source_text, match.start(), match.end()),
                warnings=(),
                reason="Module Federation remotes array declares a remote.",
            )


def _collect_exposes_object(
    observations: dict[tuple[str, str | None, str | None, str], dict[str, Any]],
    source_path: str,
    source_text: str,
    framework: str,
) -> None:
    for match in _EXPOSES_OBJECT_PATTERN.finditer(source_text):
        body = match.group("body")
        for entry in _OBJECT_STRING_ENTRY_PATTERN.finditer(body):
            _add_observation(
                observations,
                source_path,
                framework,
                relationship_type="module_federation_remote",
                target_path=entry.group("value"),
                target_symbol=_strip_quotes(entry.group("key")),
                confidence="high",
                evidence=_evidence(source_text, match.start(), match.end()),
                warnings=(),
                reason="Module Federation exposes object declares an exposed module.",
            )


def _collect_load_remote_module(
    observations: dict[tuple[str, str | None, str | None, str], dict[str, Any]],
    source_path: str,
    source_text: str,
    framework: str,
) -> None:
    for match in _LOAD_REMOTE_PATTERN.finditer(source_text):
        expression = source_text[match.start() : match.start() + MAX_EXPRESSION_CHARS]
        remote_name = _field_value(expression, "remoteName")
        remote_entry = _field_value(expression, "remoteEntry")
        exposed_module = _field_value(expression, "exposedModule")
        target_symbol = remote_name or exposed_module or "loadRemoteModule"
        target_path = remote_entry or exposed_module
        _add_observation(
            observations,
            source_path,
            framework,
            relationship_type="module_federation_remote",
            target_path=target_path,
            target_symbol=target_symbol,
            confidence="high",
            evidence=_evidence(source_text, match.start()),
            warnings=(),
            reason="loadRemoteModule call references a Module Federation remote.",
        )


def _collect_dynamic_federated_imports(
    observations: dict[tuple[str, str | None, str | None, str], dict[str, Any]],
    source_path: str,
    source_text: str,
    framework: str,
) -> None:
    for match in _DYNAMIC_IMPORT_PATTERN.finditer(source_text):
        value = match.group("path")
        if not _looks_federated_import(value):
            continue
        _add_observation(
            observations,
            source_path,
            framework,
            relationship_type="module_federation_remote",
            target_path=value,
            target_symbol=value.split("/", 1)[0],
            confidence="medium",
            evidence=_evidence(source_text, match.start(), match.end()),
            warnings=(),
            reason="Dynamic import looks like a Module Federation remote import.",
        )


def _collect_remote_entry_literals(
    observations: dict[tuple[str, str | None, str | None, str], dict[str, Any]],
    source_path: str,
    source_text: str,
    framework: str,
) -> None:
    for match in _REMOTE_ENTRY_LITERAL_PATTERN.finditer(source_text):
        value = match.group("value")
        _add_observation(
            observations,
            source_path,
            framework,
            relationship_type="module_federation_remote",
            target_path=value,
            target_symbol=_remote_name_from_value(value),
            confidence="medium",
            evidence=_evidence(source_text, match.start(), match.end()),
            warnings=("remoteEntry.js literal found without full remote config context.",),
            reason="remoteEntry.js literal suggests a Module Federation boundary.",
        )


def _collect_custom_element_definitions(
    observations: dict[tuple[str, str | None, str | None, str], dict[str, Any]],
    source_path: str,
    source_text: str,
    framework: str,
) -> None:
    for match in _CUSTOM_DEFINE_PATTERN.finditer(source_text):
        _add_observation(
            observations,
            source_path,
            framework,
            relationship_type="custom_element_usage",
            target_path=None,
            target_symbol=match.group("tag"),
            confidence="high",
            evidence=_evidence(source_text, match.start(), match.end()),
            warnings=(),
            reason="customElements.define explicitly defines a custom element.",
        )


def _collect_document_create_element(
    observations: dict[tuple[str, str | None, str | None, str], dict[str, Any]],
    source_path: str,
    source_text: str,
    framework: str,
) -> None:
    for match in _CREATE_ELEMENT_PATTERN.finditer(source_text):
        _add_observation(
            observations,
            source_path,
            framework,
            relationship_type="custom_element_usage",
            target_path=None,
            target_symbol=match.group("tag"),
            confidence="medium",
            evidence=_evidence(source_text, match.start(), match.end()),
            warnings=(),
            reason="document.createElement references a custom-element-like tag.",
        )


def _collect_template_custom_elements(
    observations: dict[tuple[str, str | None, str | None, str], dict[str, Any]],
    source_path: str,
    source_text: str,
    framework: str,
    defined_custom_elements: set[str],
) -> None:
    for match in _TAG_PATTERN.finditer(source_text):
        tag = match.group("tag")
        if tag in _NORMAL_HTML_TAGS or tag in defined_custom_elements:
            continue
        _add_observation(
            observations,
            source_path,
            framework,
            relationship_type="custom_element_usage",
            target_path=None,
            target_symbol=tag,
            confidence="low",
            evidence=_evidence(source_text, match.start(), match.end()),
            warnings=("Hyphenated tag may be a custom element; confirm ownership later.",),
            reason="Hyphenated template tag suggests custom element usage.",
        )


def _collect_custom_elements_schema(
    observations: dict[tuple[str, str | None, str | None, str], dict[str, Any]],
    source_path: str,
    source_text: str,
    framework: str,
) -> None:
    for match in _CUSTOM_ELEMENTS_SCHEMA_PATTERN.finditer(source_text):
        _add_observation(
            observations,
            source_path,
            framework,
            relationship_type="custom_element_usage",
            target_path=None,
            target_symbol="CUSTOM_ELEMENTS_SCHEMA",
            confidence="medium",
            evidence=_evidence(source_text, match.start(), match.end()),
            warnings=(),
            reason="Angular CUSTOM_ELEMENTS_SCHEMA allows custom elements.",
        )


def _add_observation(
    observations: dict[tuple[str, str | None, str | None, str], dict[str, Any]],
    source_path: str,
    framework: str,
    *,
    relationship_type: str,
    target_path: str | None,
    target_symbol: str | None,
    confidence: str,
    evidence: str,
    warnings: tuple[str, ...],
    reason: str,
) -> None:
    key = (relationship_type, target_path, target_symbol, confidence)
    existing = observations.setdefault(
        key,
        {
            "framework": framework,
            "source_path": source_path,
            "evidence": set(),
            "warnings": set(),
            "confidence": confidence,
            "reason": reason,
        },
    )
    existing["evidence"].add(evidence)
    existing["warnings"].update(warnings)


def _defined_custom_elements(source_text: str) -> set[str]:
    return {
        match.group("tag")
        for match in _CUSTOM_DEFINE_PATTERN.finditer(source_text)
    }


def _field_value(text: str, field_name: str) -> str | None:
    pattern = re.compile(_LOAD_REMOTE_FIELD_TEMPLATE.format(re.escape(field_name)))
    match = pattern.search(text)
    return None if match is None else match.group("value")


def _looks_federated_import(value: str) -> bool:
    if value.startswith((".", "/", "@", "~")):
        return False
    if "://" in value or "/" not in value:
        return False
    first, rest = value.split("/", 1)
    return bool(first and rest and re.match(r"^[A-Za-z][A-Za-z0-9_-]*$", first))


def _remote_name_from_value(value: str) -> str:
    if "@" in value:
        name = value.split("@", 1)[0]
        if name:
            return name
    cleaned = value.replace("\\", "/").rstrip("/")
    if "/" in cleaned:
        if cleaned.endswith("remoteEntry.js"):
            return cleaned.rsplit("/", 1)[-2]
        return cleaned.split("/", 1)[0]
    return cleaned


def _strip_quotes(value: str) -> str:
    stripped = value.strip()
    if (
        len(stripped) >= 2
        and stripped[0] in {"'", '"'}
        and stripped[-1] == stripped[0]
    ):
        return stripped[1:-1]
    return stripped


def _evidence(text: str, start: int, end: int | None = None) -> str:
    if end is None:
        end = min(len(text), start + MAX_BOUNDARY_EVIDENCE_CHARS)
    snippet = " ".join(text[start:end].split())
    if len(snippet) <= MAX_BOUNDARY_EVIDENCE_CHARS:
        return snippet
    return f"{snippet[: MAX_BOUNDARY_EVIDENCE_CHARS - 3]}..."


def _normalize_framework(framework: str | None, source_path: str) -> str:
    if framework is None:
        return _infer_framework(source_path)
    if not isinstance(framework, str):
        raise TypeError("framework must be a string when provided")
    if framework not in _FRONTEND_FRAMEWORKS:
        allowed = ", ".join(_FRONTEND_FRAMEWORKS)
        raise ValueError(f"framework must be one of: {allowed}")
    return framework


def _infer_framework(source_path: str) -> str:
    path = source_path.replace("\\", "/").lower()
    if path.endswith((".tsx", ".jsx")):
        return "react"
    if path.endswith(".html") or ".component." in path or "angular" in path:
        return "angular"
    return "generic_frontend"


def _validate_source_text(value: Any) -> None:
    if not isinstance(value, str):
        raise TypeError("source_text must be a string")
