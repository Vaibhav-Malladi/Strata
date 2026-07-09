"""Bounded, targeted discovery for explicitly requested package imports."""

import json
import re
from dataclasses import dataclass, field
from itertools import islice
from pathlib import Path
from typing import Any, Iterable

from strata.core.internal_library_resolution import (
    InternalLibraryResolution,
    LibraryResolutionEvidence,
    LibraryResolutionSafety,
    LibraryVersionMetadata,
    normalize_package_name,
    sort_resolution_results,
)


@dataclass(frozen=True, slots=True)
class InternalLibraryDiscoveryLimits:
    """Hard limits for one targeted discovery request."""

    max_package_json_bytes: int = 64 * 1024
    max_declaration_files: int = 16
    max_declaration_bytes: int = 512 * 1024
    max_vendor_candidate_roots: int = 10
    max_package_root_entries: int = 128
    max_archive_entries_per_root: int = 128

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if value <= 0:
                raise ValueError(f"{name} must be positive")


DEFAULT_DISCOVERY_LIMITS = InternalLibraryDiscoveryLimits()


@dataclass(slots=True)
class _Work:
    files_inspected: int = 0
    bytes_read: int = 0
    declaration_bytes: int = 0
    skipped_items: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class _DirectoryEvidence:
    root: Path
    package_json_path: Path | None
    declarations: tuple[Path, ...]
    version: LibraryVersionMetadata
    notes: tuple[str, ...]


def discover_internal_libraries(
    repo_root: str | Path,
    import_names: Iterable[str],
    limits: InternalLibraryDiscoveryLimits = DEFAULT_DISCOVERY_LIMITS,
) -> tuple[InternalLibraryResolution, ...]:
    """Discover only the package roots named by ``import_names``.

    No recursive traversal, archive opening, internet access, or model call is
    performed. Multiple subpath imports for one package share one lookup.
    """

    root = Path(repo_root)
    if not root.is_dir():
        raise ValueError("repo_root must be an existing directory")
    if not isinstance(limits, InternalLibraryDiscoveryLimits):
        raise TypeError("limits must be InternalLibraryDiscoveryLimits")
    if isinstance(import_names, (str, bytes)):
        raise TypeError("import_names must be an iterable of package imports")
    try:
        requested = tuple(import_names)
    except TypeError as error:
        raise TypeError("import_names must be an iterable of package imports") from error

    grouped: dict[str, set[str]] = {}
    for import_name in requested:
        package_name = normalize_package_name(import_name)
        grouped.setdefault(package_name, set()).add(import_name.replace("\\", "/"))

    resolved_root = root.resolve()
    results = (
        _discover_one(resolved_root, package_name, tuple(sorted(imports)), limits)
        for package_name, imports in sorted(grouped.items())
    )
    return sort_resolution_results(results)


def _discover_one(
    root: Path,
    package_name: str,
    import_paths: tuple[str, ...],
    limits: InternalLibraryDiscoveryLimits,
) -> InternalLibraryResolution:
    work = _Work()
    package_parts = tuple(package_name.split("/"))
    node_root = root.joinpath("node_modules", *package_parts)
    node_evidence = (
        _inspect_package_directory(root, node_root, limits, work)
        if _safe_directory(root, node_root, work)
        else None
    )
    if node_evidence and node_evidence.declarations:
        return _result_for_directory(
            root,
            package_name,
            import_paths,
            node_evidence,
            work,
            classification="resolved_node_modules_declaration",
            vendor=False,
        )

    vendor_evidence: list[_DirectoryEvidence] = []
    vendor_candidates = _vendor_directory_candidates(root, package_name)
    if len(vendor_candidates) > limits.max_vendor_candidate_roots:
        work.skipped_items.append("vendor candidate root cap reached")
    for candidate in vendor_candidates[: limits.max_vendor_candidate_roots]:
        if _safe_directory(root, candidate, work):
            evidence = _inspect_package_directory(root, candidate, limits, work)
            vendor_evidence.append(evidence)
            if evidence.declarations:
                return _result_for_directory(
                    root,
                    package_name,
                    import_paths,
                    evidence,
                    work,
                    classification="resolved_vendor_directory_declaration",
                    vendor=True,
                )

    archive = _find_archive(root, package_name, limits, work)
    if archive is not None:
        archive_path, version = archive
        return InternalLibraryResolution(
            library_name=package_name,
            classification="resolved_vendor_zip_reference",
            source_availability="zip_reference_only",
            version=version,
            evidence=LibraryResolutionEvidence(
                import_paths=import_paths,
                archive_path=_relative(archive_path, root),
                notes=("archive recorded without extraction",),
            ),
            safety=_safety(work),
            usage_inference_required=True,
        )

    opaque = node_evidence or (vendor_evidence[0] if vendor_evidence else None)
    if opaque is not None:
        is_vendor = opaque is not node_evidence
        return InternalLibraryResolution(
            library_name=package_name,
            classification="opaque_private_package",
            source_availability=(
                "metadata_only" if opaque.package_json_path is not None else "unavailable"
            ),
            version=opaque.version,
            evidence=LibraryResolutionEvidence(
                import_paths=import_paths,
                resolved_path=None if is_vendor else _relative(opaque.root, root),
                package_json_path=(
                    None
                    if opaque.package_json_path is None
                    else _relative(opaque.package_json_path, root)
                ),
                vendor_path=_relative(opaque.root, root) if is_vendor else None,
                notes=opaque.notes,
            ),
            safety=_safety(work),
            usage_inference_required=True,
            diagnostic_notes=("package exists without readable declarations",),
        )

    return InternalLibraryResolution(
        library_name=package_name,
        classification="missing_package",
        source_availability="unavailable",
        evidence=LibraryResolutionEvidence(import_paths=import_paths),
        safety=_safety(work),
        usage_inference_required=True,
        diagnostic_notes=("no targeted package, vendor, or archive candidate exists",),
    )


def _inspect_package_directory(
    repo_root: Path,
    package_root: Path,
    limits: InternalLibraryDiscoveryLimits,
    work: _Work,
) -> _DirectoryEvidence:
    package_json = package_root / "package.json"
    metadata = _read_package_json(repo_root, package_json, limits, work)
    version = LibraryVersionMetadata()
    notes: list[str] = []
    package_json_path = None
    declaration_targets: set[Path] = {
        package_root / "index.d.ts",
        package_root / "public-api.d.ts",
    }

    if metadata is not None:
        package_json_path = package_json
        metadata_name = metadata.get("name")
        if isinstance(metadata_name, str) and metadata_name.strip():
            notes.append(f"package name: {metadata_name.strip()}")
        metadata_version = metadata.get("version")
        if isinstance(metadata_version, str) and metadata_version.strip():
            version = LibraryVersionMetadata(
                version=metadata_version.strip(),
                version_source="package_json",
                version_confidence="high",
            )
        for field_name in ("types", "typings"):
            target = metadata.get(field_name)
            if isinstance(target, str) and target.strip():
                safe_target = _safe_child(package_root, target.strip())
                if safe_target is None:
                    work.skipped_items.append(
                        f"unsafe {field_name} declaration target in {_relative(package_json, repo_root)}"
                    )
                else:
                    declaration_targets.add(safe_target)
        for field_name in ("module", "main"):
            value = metadata.get(field_name)
            if isinstance(value, str) and value.strip():
                notes.append(f"{field_name}: {value.strip()}")

    declaration_targets.update(
        _direct_declaration_candidates(repo_root, package_root, limits, work)
    )
    declarations = _record_declarations(
        repo_root, declaration_targets, limits, work
    )
    return _DirectoryEvidence(
        root=package_root,
        package_json_path=package_json_path,
        declarations=declarations,
        version=version,
        notes=tuple(notes),
    )


def _read_package_json(
    repo_root: Path,
    path: Path,
    limits: InternalLibraryDiscoveryLimits,
    work: _Work,
) -> dict[str, Any] | None:
    work.files_inspected += 1
    if not path.is_file():
        return None
    relative = _relative(path, repo_root)
    if not _safe_file(repo_root, path):
        work.skipped_items.append(f"package metadata escapes repository: {relative}")
        return None
    try:
        if path.stat().st_size > limits.max_package_json_bytes:
            work.skipped_items.append(f"package.json byte cap exceeded: {relative}")
            return None
        with path.open("rb") as stream:
            content = stream.read(limits.max_package_json_bytes)
        work.bytes_read += len(content)
        value = json.loads(content.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        work.warnings.append(f"could not read package metadata {relative}: {type(error).__name__}")
        return None
    if not isinstance(value, dict):
        work.warnings.append(f"package metadata is not an object: {relative}")
        return None
    return value


def _direct_declaration_candidates(
    repo_root: Path,
    package_root: Path,
    limits: InternalLibraryDiscoveryLimits,
    work: _Work,
) -> tuple[Path, ...]:
    try:
        iterator = package_root.iterdir()
        entries = list(islice(iterator, limits.max_package_root_entries + 1))
    except OSError as error:
        work.warnings.append(
            f"could not inspect package root {_relative(package_root, repo_root)}: {type(error).__name__}"
        )
        return ()
    if len(entries) > limits.max_package_root_entries:
        work.skipped_items.append(
            f"package root entry cap reached: {_relative(package_root, repo_root)}"
        )
        entries = entries[: limits.max_package_root_entries]
    return tuple(
        sorted(
            (entry for entry in entries if entry.name.endswith(".d.ts")),
            key=lambda item: item.name,
        )
    )


def _record_declarations(
    repo_root: Path,
    candidates: Iterable[Path],
    limits: InternalLibraryDiscoveryLimits,
    work: _Work,
) -> tuple[Path, ...]:
    recorded: list[Path] = []
    for candidate in sorted(set(candidates), key=lambda item: item.as_posix()):
        work.files_inspected += 1
        if not candidate.is_file():
            continue
        relative = _relative(candidate, repo_root)
        if not _safe_file(repo_root, candidate):
            work.skipped_items.append(f"declaration escapes repository: {relative}")
            continue
        if len(recorded) >= limits.max_declaration_files:
            work.skipped_items.append("declaration file cap reached")
            break
        try:
            size = candidate.stat().st_size
            if work.declaration_bytes + size > limits.max_declaration_bytes:
                work.skipped_items.append(f"declaration byte cap exceeded: {relative}")
                continue
            with candidate.open("rb") as stream:
                content = stream.read(size)
            work.declaration_bytes += len(content)
            work.bytes_read += len(content)
            recorded.append(candidate)
        except OSError as error:
            work.warnings.append(
                f"could not inspect declaration {relative}: {type(error).__name__}"
            )
    return tuple(recorded)


def _vendor_directory_candidates(root: Path, package_name: str) -> tuple[Path, ...]:
    leaf = package_name.split("/")[-1]
    package_parts = tuple(package_name.split("/"))
    prefixes = (("vendor",), ("third_party",), ("libs",), ("libs", "dist"), ("dist",))
    candidates: list[Path] = []
    for prefix in prefixes:
        candidates.append(root.joinpath(*prefix, *package_parts))
        if len(package_parts) > 1:
            candidates.append(root.joinpath(*prefix, leaf))
    return tuple(dict.fromkeys(candidates))


def _find_archive(
    root: Path,
    package_name: str,
    limits: InternalLibraryDiscoveryLimits,
    work: _Work,
) -> tuple[Path, LibraryVersionMetadata] | None:
    leaf = package_name.split("/")[-1]
    candidates: list[Path] = []
    for relative_root in ("vendor", "third_party", "libs"):
        archive_root = root / relative_root
        if not _safe_directory(root, archive_root, work):
            continue
        for extension in (".zip", ".tgz", ".tar.gz"):
            exact = archive_root / f"{leaf}{extension}"
            work.files_inspected += 1
            if exact.is_file():
                candidates.append(exact)
        try:
            entries = list(
                islice(archive_root.iterdir(), limits.max_archive_entries_per_root + 1)
            )
        except OSError as error:
            work.warnings.append(
                f"could not inspect archive root {relative_root}: {type(error).__name__}"
            )
            continue
        if len(entries) > limits.max_archive_entries_per_root:
            work.skipped_items.append(f"archive entry cap reached: {relative_root}")
            entries = entries[: limits.max_archive_entries_per_root]
        for entry in sorted(entries, key=lambda item: item.name):
            work.files_inspected += 1
            if entry.is_file() and _archive_version(entry.name, leaf) is not None:
                candidates.append(entry)

    if not candidates:
        return None
    archive = tuple(dict.fromkeys(candidates))[0]
    guessed_version = _archive_version(archive.name, leaf)
    version = (
        LibraryVersionMetadata()
        if guessed_version is None
        else LibraryVersionMetadata(guessed_version, "filename", "low")
    )
    return archive, version


def _archive_version(filename: str, leaf: str) -> str | None:
    stem = filename
    for extension in (".tar.gz", ".zip", ".tgz"):
        if stem.endswith(extension):
            stem = stem[: -len(extension)]
            break
    else:
        return None
    match = re.fullmatch(rf"{re.escape(leaf)}-(\d[0-9A-Za-z.+_-]*)", stem)
    return None if match is None else match.group(1)


def _result_for_directory(
    repo_root: Path,
    package_name: str,
    import_paths: tuple[str, ...],
    directory: _DirectoryEvidence,
    work: _Work,
    *,
    classification: str,
    vendor: bool,
) -> InternalLibraryResolution:
    declaration_paths = tuple(_relative(path, repo_root) for path in directory.declarations)
    return InternalLibraryResolution(
        library_name=package_name,
        classification=classification,
        source_availability="declaration_only",
        version=directory.version,
        evidence=LibraryResolutionEvidence(
            import_paths=import_paths,
            resolved_path=None if vendor else _relative(directory.root, repo_root),
            package_json_path=(
                None
                if directory.package_json_path is None
                else _relative(directory.package_json_path, repo_root)
            ),
            declaration_paths=declaration_paths,
            vendor_path=_relative(directory.root, repo_root) if vendor else None,
            notes=directory.notes,
        ),
        safety=_safety(work),
        context_paths=declaration_paths,
    )


def _safe_directory(repo_root: Path, path: Path, work: _Work) -> bool:
    if not path.is_dir():
        return False
    try:
        path.resolve().relative_to(repo_root)
    except (OSError, ValueError):
        work.skipped_items.append(f"directory escapes repository: {_relative(path, repo_root)}")
        return False
    return True


def _safe_child(parent: Path, relative_value: str) -> Path | None:
    value = Path(relative_value.replace("\\", "/"))
    if value.is_absolute():
        return None
    candidate = (parent / value).resolve()
    try:
        candidate.relative_to(parent.resolve())
    except ValueError:
        return None
    return candidate


def _safe_file(repo_root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(repo_root)
    except (OSError, ValueError):
        return False
    return True


def _relative(path: Path, repo_root: Path) -> str:
    return path.relative_to(repo_root).as_posix()


def _safety(work: _Work) -> LibraryResolutionSafety:
    return LibraryResolutionSafety(
        files_inspected=work.files_inspected,
        bytes_read=work.bytes_read,
        skipped_items=tuple(work.skipped_items),
        warnings=tuple(work.warnings),
    )
