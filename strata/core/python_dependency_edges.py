"""Direct, AST-based Python import edge extraction."""

import ast
from pathlib import Path, PurePosixPath

from strata.core.dependency_tracing import (
    DependencyEdge,
    DependencyTraceReport,
    create_dependency_edge,
    normalize_relative_path,
)
from strata.core.dependency_priority import (
    estimate_dependency_cost,
    priority_for_evidence,
)
from strata.core.stage_report import StageReport


_COMMON_SOURCE_ROOTS = ("src", "lib")


def extract_python_import_edges(
    repo_root: str | Path,
    source_file: str | Path,
) -> DependencyTraceReport:
    """Extract resolved direct imports from one Python source file.

    Target modules are inspected by path only; they are never read, imported, or
    executed. Unresolved imports are recorded as skipped items without creating
    a synthetic edge.
    """

    root = _validate_root(repo_root)
    source_path = normalize_relative_path(str(source_file))
    if PurePosixPath(source_path).suffix.lower() != ".py":
        raise ValueError("source_file must identify a Python file")
    source_target = _resolve_source(root, source_path)

    content = source_target.read_bytes()
    try:
        tree = ast.parse(content, filename=source_path)
    except SyntaxError as error:
        warning = _syntax_warning(error)
        return DependencyTraceReport(
            seed_files=(source_path,),
            skipped_items=(f"{source_path}: syntax_error",),
            warnings=(warning,),
            stage_report=_stage_report(
                source_path,
                edge_count=0,
                bytes_read=len(content),
                skipped_items=(f"{source_path}: syntax_error",),
                warnings=(warning,),
                confidence="low",
            ),
        )

    search_roots = _module_search_roots(root)
    edges: list[DependencyEdge] = []
    skipped_items: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                target = _resolve_absolute_module(root, search_roots, alias.name)
                import_text = _import_alias_text(alias)
                if target is None:
                    skipped_items.append(f"unresolved import: {import_text}")
                    continue
                edges.append(
                    _edge(
                        source_path,
                        target,
                        reason=f"Python import: {import_text}",
                        evidence_kind="exact_import",
                        confidence="high",
                    )
                )
        elif isinstance(node, ast.ImportFrom):
            _extract_from_import(
                root,
                search_roots,
                source_path,
                node,
                edges,
                skipped_items,
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
            confidence="high",
        ),
    )


def _extract_from_import(
    root: Path,
    search_roots: tuple[Path, ...],
    source_path: str,
    node: ast.ImportFrom,
    edges: list[DependencyEdge],
    skipped_items: list[str],
) -> None:
    base_parts = _from_import_base(source_path, node)
    if base_parts is None:
        for alias in node.names:
            skipped_items.append(
                f"unresolved import: {_from_alias_text(node, alias)}"
            )
        return

    for alias in node.names:
        import_text = _from_alias_text(node, alias)
        child_parts = (*base_parts, alias.name) if alias.name != "*" else None
        child_target = _resolve_module_parts(
            root,
            search_roots,
            child_parts,
            relative=node.level > 0,
        )
        if child_target is not None:
            edges.append(
                _edge(
                    source_path,
                    child_target,
                    reason=f"Python import: {import_text}",
                    evidence_kind="exact_import",
                    confidence="high",
                )
            )
            continue

        base_target = _resolve_module_parts(
            root,
            search_roots,
            base_parts,
            relative=node.level > 0,
        )
        if base_target is None:
            skipped_items.append(f"unresolved import: {import_text}")
            continue
        edges.append(
            _edge(
                source_path,
                base_target,
                reason=f"Python import: {import_text}",
                evidence_kind="symbol_import",
                confidence="medium",
            )
        )


def _from_import_base(
    source_path: str,
    node: ast.ImportFrom,
) -> tuple[str, ...] | None:
    module_parts = tuple(node.module.split(".")) if node.module else ()
    if node.level == 0:
        return module_parts

    source_parts = PurePosixPath(source_path).parts
    package_parts = source_parts[:-1]
    parents_to_climb = node.level - 1
    if not package_parts or parents_to_climb >= len(package_parts):
        return None
    if parents_to_climb:
        package_parts = package_parts[:-parents_to_climb]
    return (*package_parts, *module_parts)


def _resolve_absolute_module(
    root: Path,
    search_roots: tuple[Path, ...],
    module_name: str,
) -> str | None:
    return _resolve_module_parts(
        root,
        search_roots,
        tuple(module_name.split(".")),
        relative=False,
    )


def _resolve_module_parts(
    root: Path,
    search_roots: tuple[Path, ...],
    module_parts: tuple[str, ...] | None,
    *,
    relative: bool,
) -> str | None:
    if not module_parts or any(
        not part or part in (".", "..") for part in module_parts
    ):
        return None
    roots = (root,) if relative else search_roots
    for search_root in roots:
        module_base = search_root.joinpath(*module_parts)
        for candidate in (
            module_base.with_suffix(".py"),
            module_base / "__init__.py",
        ):
            target = _safe_existing_file(root, candidate)
            if target is not None:
                return target.relative_to(root).as_posix()
    return None


def _safe_existing_file(root: Path, candidate: Path) -> Path | None:
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (FileNotFoundError, OSError, ValueError):
        return None
    if not resolved.is_file():
        return None
    return resolved


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


def _module_search_roots(root: Path) -> tuple[Path, ...]:
    roots = [root]
    for name in _COMMON_SOURCE_ROOTS:
        candidate = root / name
        if candidate.is_dir() and not candidate.is_symlink():
            roots.append(candidate)
    return tuple(roots)


def _edge(
    source_file: str,
    target_file: str,
    *,
    reason: str,
    evidence_kind: str,
    confidence: str,
) -> DependencyEdge:
    return create_dependency_edge(
        source_file=source_file,
        target_file=target_file,
        edge_type="import",
        priority=priority_for_evidence(evidence_kind),
        reason=reason,
        confidence=confidence,
        estimated_cost=estimate_dependency_cost("import", evidence_kind),
    )


def _import_alias_text(alias: ast.alias) -> str:
    suffix = f" as {alias.asname}" if alias.asname else ""
    return f"import {alias.name}{suffix}"


def _from_alias_text(node: ast.ImportFrom, alias: ast.alias) -> str:
    prefix = "." * node.level + (node.module or "")
    suffix = f" as {alias.asname}" if alias.asname else ""
    return f"from {prefix} import {alias.name}{suffix}"


def _syntax_warning(error: SyntaxError) -> str:
    line = error.lineno if error.lineno is not None else "unknown"
    return f"syntax error at line {line}: {error.msg}"


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
        "python_import_edge_extraction",
        inputs={"source_file": source_path},
        outputs={"edge_count": edge_count},
        warnings=warnings,
        skipped_items=skipped_items,
        confidence=confidence,
        bytes_read=bytes_read,
        files_touched=1,
    )
