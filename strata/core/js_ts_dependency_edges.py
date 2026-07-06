"""Direct, lightweight JavaScript and TypeScript dependency edge extraction."""

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from strata.core.dependency_tracing import (
    DependencyEdge,
    DependencyTraceReport,
    create_dependency_edge,
    normalize_relative_path,
)
from strata.core.stage_report import StageReport


JS_TS_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
DIRECTORY_INDEX_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx")
DEFAULT_MAX_SOURCE_BYTES = 1024 * 1024
_EDGE_ESTIMATED_COST = 1.0

_STATIC_IMPORT_RE = re.compile(
    r"\bimport\s+(?P<clause>[^;\"']+?)\s+from\s*"
    r"(?P<quote>[\"'])(?P<specifier>[^\"'\r\n]+)(?P=quote)",
    re.MULTILINE,
)
_SIDE_EFFECT_IMPORT_RE = re.compile(
    r"\bimport\s*(?P<quote>[\"'])(?P<specifier>[^\"'\r\n]+)(?P=quote)"
)
_RE_EXPORT_RE = re.compile(
    r"\bexport\s+(?P<clause>\*(?:\s+as\s+[\w$]+)?|\{[^}]*\})\s+from\s*"
    r"(?P<quote>[\"'])(?P<specifier>[^\"'\r\n]+)(?P=quote)",
    re.MULTILINE,
)
_DYNAMIC_IMPORT_RE = re.compile(
    r"\bimport\s*\(\s*(?P<quote>[\"'])"
    r"(?P<specifier>[^\"'\r\n]+)(?P=quote)\s*\)"
)
_REQUIRE_RE = re.compile(
    r"(?<![\w$.])require\s*\(\s*(?P<quote>[\"'])"
    r"(?P<specifier>[^\"'\r\n]+)(?P=quote)\s*\)"
)


@dataclass(frozen=True, slots=True)
class _ImportReference:
    position: int
    specifier: str
    edge_type: str
    form: str
    statement: str
    priority: str
    confidence: str


def extract_js_ts_import_edges(
    repo_root: str | Path,
    source_file: str | Path,
    *,
    max_source_bytes: int = DEFAULT_MAX_SOURCE_BYTES,
) -> DependencyTraceReport:
    """Extract resolved direct imports and re-exports from one JS/TS file."""

    root = _validate_root(repo_root)
    source_path = normalize_relative_path(str(source_file))
    if PurePosixPath(source_path).suffix.lower() not in JS_TS_EXTENSIONS:
        raise ValueError("source_file must identify a JavaScript or TypeScript file")
    if "node_modules" in PurePosixPath(source_path).parts:
        raise ValueError("source_file must not be inside node_modules")
    _validate_max_source_bytes(max_source_bytes)
    source_target = _resolve_source(root, source_path)

    with source_target.open("rb") as handle:
        content = handle.read(max_source_bytes + 1)
    if len(content) > max_source_bytes:
        return _skipped_source_report(
            source_path,
            reason="oversized_source",
            warning=f"source exceeds {max_source_bytes} byte limit",
            bytes_read=len(content),
        )
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return _skipped_source_report(
            source_path,
            reason="decode_error",
            warning="source is not valid UTF-8",
            bytes_read=len(content),
        )

    references = _extract_references(text)
    edges: list[DependencyEdge] = []
    skipped_items: list[str] = []
    for reference in references:
        if not _is_relative_specifier(reference.specifier):
            skipped_items.append(
                f"unsupported non-relative import: {reference.specifier}"
            )
            continue
        target = _resolve_relative_specifier(
            root,
            source_target.parent,
            reference.specifier,
        )
        if target is None:
            skipped_items.append(
                f"unresolved relative import: {reference.specifier}"
            )
            continue
        edges.append(
            _edge(
                source_path,
                target,
                edge_type=reference.edge_type,
                priority=reference.priority,
                confidence=reference.confidence,
                reason=f"JS/TS {reference.form}: {reference.statement}",
            )
        )

    skipped = tuple(sorted(set(skipped_items)))
    return DependencyTraceReport(
        seed_files=(source_path,),
        edges=tuple(edges),
        skipped_items=skipped,
        stage_report=_stage_report(
            source_path,
            edge_count=len(set(edges)),
            bytes_read=len(content),
            skipped_items=skipped,
            confidence="medium",
        ),
    )


def _extract_references(text: str) -> tuple[_ImportReference, ...]:
    code_positions = _code_positions(text)
    references: list[_ImportReference] = []
    patterns = (
        (_RE_EXPORT_RE, "re_export", "re-export", "medium", "high"),
        (_STATIC_IMPORT_RE, "import", "static import", "medium", "high"),
        (_SIDE_EFFECT_IMPORT_RE, "import", "side-effect import", "medium", "high"),
        (_DYNAMIC_IMPORT_RE, "import", "dynamic import", "low", "medium"),
        (_REQUIRE_RE, "import", "CommonJS require", "low", "medium"),
    )
    for pattern, edge_type, form, priority, confidence in patterns:
        for match in pattern.finditer(text):
            if not code_positions[match.start()]:
                continue
            references.append(
                _ImportReference(
                    position=match.start(),
                    specifier=match.group("specifier"),
                    edge_type=edge_type,
                    form=form,
                    statement=_compact_statement(match.group(0)),
                    priority=priority,
                    confidence=confidence,
                )
            )
    return tuple(
        sorted(
            set(references),
            key=lambda item: (
                item.position,
                item.edge_type,
                item.specifier,
                item.form,
                item.statement,
            ),
        )
    )


def _code_positions(text: str) -> tuple[bool, ...]:
    """Mark positions outside comments and quoted/template string bodies."""

    positions = [True] * (len(text) + 1)
    index = 0
    state = "code"
    quote = ""
    while index < len(text):
        character = text[index]
        following = text[index + 1] if index + 1 < len(text) else ""
        if state == "code":
            if character == "/" and following == "/":
                positions[index] = positions[index + 1] = False
                index += 2
                state = "line_comment"
                continue
            if character == "/" and following == "*":
                positions[index] = positions[index + 1] = False
                index += 2
                state = "block_comment"
                continue
            if character in ("'", '"', "`"):
                positions[index] = False
                quote = character
                state = "string"
        elif state == "line_comment":
            positions[index] = False
            if character in ("\r", "\n"):
                state = "code"
        elif state == "block_comment":
            positions[index] = False
            if character == "*" and following == "/":
                positions[index + 1] = False
                index += 2
                state = "code"
                continue
        else:
            positions[index] = False
            if character == "\\":
                if index + 1 < len(text):
                    positions[index + 1] = False
                    index += 2
                    continue
            elif character == quote:
                state = "code"
        index += 1
    return tuple(positions)


def _resolve_relative_specifier(
    root: Path,
    importer_directory: Path,
    specifier: str,
) -> str | None:
    normalized = specifier.replace("\\", "/")
    specifier_path = PurePosixPath(normalized)
    if (
        not normalized
        or "node_modules" in specifier_path.parts
        or "?" in normalized
        or "#" in normalized
    ):
        return None

    base = importer_directory.joinpath(*specifier_path.parts)
    candidates: list[Path] = []
    if base.suffix.lower() in JS_TS_EXTENSIONS:
        candidates.append(base)
    elif base.suffix:
        return None
    else:
        candidates.extend(base.with_suffix(extension) for extension in JS_TS_EXTENSIONS)
        candidates.extend(
            base / f"index{extension}" for extension in DIRECTORY_INDEX_EXTENSIONS
        )

    for candidate in candidates:
        target = _safe_existing_file(root, candidate)
        if target is not None:
            return target.relative_to(root).as_posix()
    return None


def _safe_existing_file(root: Path, candidate: Path) -> Path | None:
    try:
        resolved = candidate.resolve(strict=True)
        relative = resolved.relative_to(root)
    except (FileNotFoundError, OSError, ValueError):
        return None
    if "node_modules" in relative.parts or not resolved.is_file():
        return None
    return resolved


def _is_relative_specifier(specifier: str) -> bool:
    return specifier.startswith("./") or specifier.startswith("../")


def _validate_root(repo_root: str | Path) -> Path:
    root = Path(repo_root)
    if not root.exists():
        raise FileNotFoundError(f"repository root does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"repository root is not a directory: {root}")
    return root.resolve()


def _resolve_source(root: Path, source_path: str) -> Path:
    candidate = root.joinpath(*PurePosixPath(source_path).parts)
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except FileNotFoundError as error:
        raise FileNotFoundError(f"source file does not exist: {source_path}") from error
    except (OSError, ValueError) as error:
        raise ValueError("source_file must resolve inside the repository root") from error
    if not resolved.is_file():
        raise ValueError("source_file must identify a regular file")
    return resolved


def _validate_max_source_bytes(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("max_source_bytes must be an integer")
    if value <= 0:
        raise ValueError("max_source_bytes must be greater than zero")


def _edge(
    source_file: str,
    target_file: str,
    *,
    edge_type: str,
    priority: str,
    confidence: str,
    reason: str,
) -> DependencyEdge:
    return create_dependency_edge(
        source_file=source_file,
        target_file=target_file,
        edge_type=edge_type,
        priority=priority,
        reason=reason,
        confidence=confidence,
        estimated_cost=_EDGE_ESTIMATED_COST,
    )


def _compact_statement(value: str) -> str:
    return " ".join(value.split())


def _skipped_source_report(
    source_path: str,
    *,
    reason: str,
    warning: str,
    bytes_read: int,
) -> DependencyTraceReport:
    skipped_item = f"{source_path}: {reason}"
    return DependencyTraceReport(
        seed_files=(source_path,),
        skipped_items=(skipped_item,),
        warnings=(warning,),
        stage_report=_stage_report(
            source_path,
            edge_count=0,
            bytes_read=bytes_read,
            skipped_items=(skipped_item,),
            warnings=(warning,),
            confidence="low",
        ),
    )


def _stage_report(
    source_path: str,
    *,
    edge_count: int,
    bytes_read: int,
    skipped_items: tuple[str, ...] = (),
    warnings: tuple[str, ...] = (),
    confidence: str,
) -> StageReport:
    return StageReport(
        "js_ts_import_edge_extraction",
        inputs={"source_file": source_path},
        outputs={"edge_count": edge_count},
        warnings=warnings,
        skipped_items=skipped_items,
        confidence=confidence,
        bytes_read=bytes_read,
        files_touched=1,
    )
