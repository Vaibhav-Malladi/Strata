"""Infer frontend usage of known or private-looking internal libraries.

J5 consumes one supplied source/template string and optional Bridge-style hints.
It does not discover libraries, scan repositories, read package metadata, or
resolve aliases.
"""

import re
from typing import Any, Iterable

from strata.core.frontend_relationships import (
    FRONTEND_FRAMEWORKS as _FRONTEND_FRAMEWORKS,
    FrontendRelationship,
    create_frontend_relationship as _create_frontend_relationship,
    sort_frontend_relationships as _sort_frontend_relationships,
)


MAX_INTERNAL_USAGE_EVIDENCE_CHARS = 180

_PRIVATE_PACKAGE_PREFIXES = ("@company/", "@org/", "@internal/", "@enterprise/")
_COMPANY_SYMBOL_PREFIXES = ("company", "org", "internal", "enterprise")
_IMPORT_FROM_PATTERN = re.compile(
    r"\bimport\s+(?P<imports>[\s\S]{0,240}?)\s+from\s+"
    r"(?P<quote>['\"])(?P<package>[^'\"]+)(?P=quote)"
)
_SIDE_EFFECT_IMPORT_PATTERN = re.compile(
    r"\bimport\s*(?P<quote>['\"])(?P<package>[^'\"]+)(?P=quote)"
)
_REQUIRE_PATTERN = re.compile(
    r"\brequire\s*\(\s*(?P<quote>['\"])(?P<package>[^'\"]+)(?P=quote)\s*\)"
)
_TAG_PATTERN = re.compile(r"<\s*(?!/)(?P<tag>[A-Za-z][A-Za-z0-9_.-]*)\b")
_BOUND_ATTRIBUTE_PATTERN = re.compile(r"\[(?P<name>[A-Za-z][A-Za-z0-9_-]*)\]")
_BARE_ATTRIBUTE_PATTERN = re.compile(r"\s(?P<name>[A-Za-z][A-Za-z0-9_-]*)\s*(?:=|>|/>)")
_PIPE_PATTERN = re.compile(r"\|\s*(?P<name>[A-Za-z_$][A-Za-z0-9_$]*)")
_CONSTRUCTOR_PATTERN = re.compile(r"\bconstructor\s*\((?P<params>[\s\S]{0,500}?)\)")
_TYPE_SYMBOL_PATTERN = re.compile(r":\s*(?P<symbol>[A-Za-z_$][A-Za-z0-9_$]*)")
_CALL_PATTERN_TEMPLATE = r"(?<![\w$]){}\s*(?:\.|\()"


def infer_frontend_internal_library_usage(
    source_path: str,
    source_text: str,
    known_internal_packages: Iterable[str] | None = None,
    known_internal_symbols: Iterable[str] | None = None,
    framework: str | None = None,
) -> tuple[FrontendRelationship, ...]:
    """Infer internal library usage relationships from one frontend source."""

    _validate_source_text(source_text)
    normalized_framework = _normalize_framework(framework, source_path)
    packages = _normalize_text_items(
        known_internal_packages or (),
        "known_internal_packages",
    )
    symbols = _normalize_text_items(
        known_internal_symbols or (),
        "known_internal_symbols",
    )
    symbol_lookup = _symbol_lookup(symbols)

    observations: dict[tuple[str, str | None, str | None, str], dict[str, Any]] = {}
    _collect_import_usage(
        observations,
        source_path,
        source_text,
        normalized_framework,
        packages,
    )
    _collect_template_and_jsx_usage(
        observations,
        source_path,
        source_text,
        normalized_framework,
        symbol_lookup,
    )
    _collect_pipe_usage(
        observations,
        source_path,
        source_text,
        normalized_framework,
        symbol_lookup,
    )
    _collect_injected_service_usage(
        observations,
        source_path,
        source_text,
        normalized_framework,
        symbol_lookup,
    )
    _collect_known_symbol_calls(
        observations,
        source_path,
        source_text,
        normalized_framework,
        symbols,
    )

    relationships = [
        _create_frontend_relationship(
            framework=normalized_framework,
            source_path=source_path,
            target_path=key[1],
            target_symbol=key[2],
            relationship_type="internal_library_usage",
            confidence=values["confidence"],
            evidence=tuple(sorted(values["evidence"])),
            warnings=tuple(sorted(values["warnings"])),
            reason=values["reason"],
        )
        for key, values in observations.items()
    ]
    return _sort_frontend_relationships(relationships)


def _collect_import_usage(
    observations: dict[tuple[str, str | None, str | None, str], dict[str, Any]],
    source_path: str,
    source_text: str,
    framework: str,
    known_packages: tuple[str, ...],
) -> None:
    for match in _IMPORT_FROM_PATTERN.finditer(source_text):
        package = match.group("package")
        symbols = _imported_symbols(match.group("imports"))
        _add_import_observations(
            observations,
            source_path,
            framework,
            package,
            symbols,
            _evidence(source_text, match.start(), match.end()),
            known_packages,
        )

    for pattern in (_SIDE_EFFECT_IMPORT_PATTERN, _REQUIRE_PATTERN):
        for match in pattern.finditer(source_text):
            package = match.group("package")
            _add_import_observations(
                observations,
                source_path,
                framework,
                package,
                (),
                _evidence(source_text, match.start(), match.end()),
                known_packages,
            )


def _add_import_observations(
    observations: dict[tuple[str, str | None, str | None, str], dict[str, Any]],
    source_path: str,
    framework: str,
    package: str,
    imported_symbols: tuple[str, ...],
    evidence: str,
    known_packages: tuple[str, ...],
) -> None:
    is_known = _matches_known_package(package, known_packages)
    is_private_guess = _looks_private_package(package)
    if not is_known and not is_private_guess:
        return

    confidence = "high" if is_known else "low"
    reason = (
        "Frontend source imports an explicitly known internal package."
        if is_known
        else "Frontend source imports a private-looking package prefix."
    )
    warnings = (
        ()
        if is_known
        else ("Prefix-based internal package guess; confirm with Bridge resolution.",)
    )
    symbols = imported_symbols or (None,)
    for symbol in symbols:
        _add_observation(
            observations,
            source_path,
            framework,
            target_path=package,
            target_symbol=symbol,
            confidence=confidence,
            evidence=evidence,
            warnings=warnings,
            reason=reason,
        )


def _collect_template_and_jsx_usage(
    observations: dict[tuple[str, str | None, str | None, str], dict[str, Any]],
    source_path: str,
    source_text: str,
    framework: str,
    symbol_lookup: dict[str, str],
) -> None:
    for match in _TAG_PATTERN.finditer(source_text):
        raw = match.group("tag")
        symbol = _known_symbol_for(raw, symbol_lookup)
        if symbol is not None:
            _add_known_symbol_observation(
                observations,
                source_path,
                framework,
                symbol,
                _evidence(source_text, match.start(), match.end()),
                "Frontend template/JSX uses a known internal component or selector.",
            )
            continue
        if _looks_private_selector(raw):
            _add_prefix_guess_observation(
                observations,
                source_path,
                framework,
                raw,
                _evidence(source_text, match.start(), match.end()),
                "Frontend template/JSX uses a private-looking selector prefix.",
            )

    for pattern in (_BOUND_ATTRIBUTE_PATTERN, _BARE_ATTRIBUTE_PATTERN):
        for match in pattern.finditer(source_text):
            raw = match.group("name")
            symbol = _known_symbol_for(raw, symbol_lookup)
            if symbol is None:
                if _looks_private_selector(raw):
                    _add_prefix_guess_observation(
                        observations,
                        source_path,
                        framework,
                        raw,
                        _evidence(source_text, match.start(), match.end()),
                        "Frontend template uses a private-looking directive prefix.",
                    )
                continue
            _add_known_symbol_observation(
                observations,
                source_path,
                framework,
                symbol,
                _evidence(source_text, match.start(), match.end()),
                "Frontend template uses a known internal directive symbol.",
            )


def _collect_pipe_usage(
    observations: dict[tuple[str, str | None, str | None, str], dict[str, Any]],
    source_path: str,
    source_text: str,
    framework: str,
    symbol_lookup: dict[str, str],
) -> None:
    for match in _PIPE_PATTERN.finditer(source_text):
        raw = match.group("name")
        symbol = _known_symbol_for(raw, symbol_lookup)
        if symbol is None:
            continue
        _add_known_symbol_observation(
            observations,
            source_path,
            framework,
            symbol,
            _evidence(source_text, match.start(), match.end()),
            "Frontend template uses a known internal pipe symbol.",
        )


def _collect_injected_service_usage(
    observations: dict[tuple[str, str | None, str | None, str], dict[str, Any]],
    source_path: str,
    source_text: str,
    framework: str,
    symbol_lookup: dict[str, str],
) -> None:
    for constructor_match in _CONSTRUCTOR_PATTERN.finditer(source_text):
        params = constructor_match.group("params")
        for type_match in _TYPE_SYMBOL_PATTERN.finditer(params):
            symbol = _known_symbol_for(type_match.group("symbol"), symbol_lookup)
            if symbol is None:
                continue
            start = constructor_match.start() + type_match.start()
            end = constructor_match.start() + type_match.end()
            _add_known_symbol_observation(
                observations,
                source_path,
                framework,
                symbol,
                _evidence(source_text, start, end),
                "Frontend code injects a known internal service symbol.",
            )


def _collect_known_symbol_calls(
    observations: dict[tuple[str, str | None, str | None, str], dict[str, Any]],
    source_path: str,
    source_text: str,
    framework: str,
    known_symbols: tuple[str, ...],
) -> None:
    for symbol in known_symbols:
        pattern = re.compile(_CALL_PATTERN_TEMPLATE.format(re.escape(symbol)))
        for match in pattern.finditer(source_text):
            _add_known_symbol_observation(
                observations,
                source_path,
                framework,
                symbol,
                _evidence(source_text, match.start(), match.end()),
                "Frontend code calls a known internal hook/service/client symbol.",
            )


def _add_known_symbol_observation(
    observations: dict[tuple[str, str | None, str | None, str], dict[str, Any]],
    source_path: str,
    framework: str,
    symbol: str,
    evidence: str,
    reason: str,
) -> None:
    _add_observation(
        observations,
        source_path,
        framework,
        target_path=None,
        target_symbol=symbol,
        confidence="medium",
        evidence=evidence,
        warnings=(),
        reason=reason,
    )


def _add_prefix_guess_observation(
    observations: dict[tuple[str, str | None, str | None, str], dict[str, Any]],
    source_path: str,
    framework: str,
    symbol: str,
    evidence: str,
    reason: str,
) -> None:
    _add_observation(
        observations,
        source_path,
        framework,
        target_path=None,
        target_symbol=symbol,
        confidence="low",
        evidence=evidence,
        warnings=(
            "Prefix-based internal symbol guess; confirm with Bridge resolution.",
        ),
        reason=reason,
    )


def _add_observation(
    observations: dict[tuple[str, str | None, str | None, str], dict[str, Any]],
    source_path: str,
    framework: str,
    *,
    target_path: str | None,
    target_symbol: str | None,
    confidence: str,
    evidence: str,
    warnings: tuple[str, ...],
    reason: str,
) -> None:
    key = (source_path, target_path, target_symbol, confidence)
    existing = observations.setdefault(
        key,
        {
            "framework": framework,
            "evidence": set(),
            "warnings": set(),
            "confidence": confidence,
            "reason": reason,
        },
    )
    existing["evidence"].add(evidence)
    existing["warnings"].update(warnings)


def _imported_symbols(imports_text: str) -> tuple[str, ...]:
    text = " ".join(imports_text.split())
    symbols: list[str] = []
    named_match = re.search(r"\{(?P<named>.*?)\}", text)
    if named_match:
        for item in named_match.group("named").split(","):
            name = item.strip()
            if not name:
                continue
            if " as " in name:
                name = name.rsplit(" as ", 1)[-1].strip()
            symbols.append(name)

    prefix = text.split("{", 1)[0].strip().rstrip(",")
    if prefix.startswith("* as "):
        symbols.append(prefix.rsplit(" ", 1)[-1])
    elif prefix and prefix not in {"type"}:
        first = prefix.split(",", 1)[0].strip()
        if first and first not in {"type"}:
            symbols.append(first)
    return tuple(sorted(set(symbols)))


def _matches_known_package(package: str, known_packages: tuple[str, ...]) -> bool:
    return any(
        package == known or package.startswith(f"{known}/")
        for known in known_packages
    )


def _looks_private_package(package: str) -> bool:
    return package.startswith(_PRIVATE_PACKAGE_PREFIXES)


def _looks_private_selector(value: str) -> bool:
    normalized = value.replace("_", "-").lower()
    return any(
        normalized.startswith(f"{prefix}-") or normalized.startswith(prefix)
        for prefix in _COMPANY_SYMBOL_PREFIXES
    )


def _known_symbol_for(value: str, symbol_lookup: dict[str, str]) -> str | None:
    for variant in _symbol_variants(value):
        if variant in symbol_lookup:
            return symbol_lookup[variant]
    return None


def _symbol_lookup(symbols: tuple[str, ...]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for symbol in symbols:
        for variant in _symbol_variants(symbol):
            lookup.setdefault(variant, symbol)
    return lookup


def _symbol_variants(value: str) -> tuple[str, ...]:
    raw = str(value)
    without_pipe = raw[:-4] if raw.endswith("Pipe") else raw
    variants = {
        raw,
        raw.lower(),
        _to_kebab_case(raw),
        _to_camel_case(raw),
        without_pipe,
        without_pipe.lower(),
        _to_kebab_case(without_pipe),
        _to_camel_case(without_pipe),
    }
    return tuple(sorted(item for item in variants if item))


def _to_kebab_case(value: str) -> str:
    normalized = value.replace("_", "-").replace(".", "-")
    normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", normalized)
    return normalized.lower()


def _to_camel_case(value: str) -> str:
    parts = re.split(r"[-_\s.]+", value)
    if not parts:
        return value
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


def _evidence(text: str, start: int, end: int | None = None) -> str:
    if end is None:
        end = min(len(text), start + MAX_INTERNAL_USAGE_EVIDENCE_CHARS)
    snippet = " ".join(text[start:end].split())
    if len(snippet) <= MAX_INTERNAL_USAGE_EVIDENCE_CHARS:
        return snippet
    return f"{snippet[: MAX_INTERNAL_USAGE_EVIDENCE_CHARS - 3]}..."


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
    if path.endswith(".html") or ".component." in path:
        return "angular"
    return "generic_frontend"


def _normalize_text_items(values: Any, name: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{name} must be an iterable of strings")
    try:
        items = tuple(values)
    except TypeError as error:
        raise TypeError(f"{name} must be an iterable of strings") from error
    normalized = []
    for item in items:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{name} items must be non-empty strings")
        if item != item.strip() or "\x00" in item:
            raise ValueError(f"{name} items must not contain padding or null bytes")
        normalized.append(item)
    return tuple(sorted(set(normalized)))


def _validate_source_text(value: Any) -> None:
    if not isinstance(value, str):
        raise TypeError("source_text must be a string")
